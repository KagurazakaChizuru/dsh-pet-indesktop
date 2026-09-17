# -*- coding: utf-8 -*-
"""节日提醒服务：调度 + 气泡落地（服务层）。

分层约定与 voice_chime_service.py 一致：
  - **模块顶层不 import Qt**：QTimer 在 ``__init__`` 内惰性导入，使本模块
    可被无 GUI 环境导入（也便于纯逻辑测试引用常量）。
  - 服务不继承 QObject，由 AppShell 持有引用保证生命周期。
  - 全部逻辑跑在 GUI 线程（只有一个 QTimer），无跨线程对象，因此不需要
    语音报时那套 _AudioBridge 信号桥（本功能不合成音频，只出气泡）。

为什么 tick 是 30s 而不是 60s：提醒时间点是精确到分钟的，60s 间隔在边界
抖动下可能整分钟跳过；30s 保证任意分钟至少被采样两次，且开销可忽略。
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from .festival import (
    NO_FESTIVAL_TEXT,
    build_festival_text,
    normalize_festival_config,
    reminder_slot,
    startup_slot,
    today_festival,
)
from .festival_animations import pick_animation
logger = logging.getLogger(__name__)


class FestivalReminderService:
    """节日提醒服务（AppShell 持有，GUI 线程）。"""

    TICK_INTERVAL_MS = 30_000
    BUBBLE_DURATION_MS = 12_000

    def __init__(self, app) -> None:
        from PySide6.QtCore import QTimer

        self._app = app
        # 契约形状由纯逻辑层定义（enabled/cn/solar_terms/west/mode/count/times/...）
        self._cfg: dict = normalize_festival_config(None)
        # 当天已触发的槽位；跨天自动清空（槽位本身含日期，这里只是防集合无界增长）
        self._slot_day: date | None = None
        self._fired: set[str] = set()
        # 节日动画的「当天已确认播出」记账：{(日期, 节日id), ...}，跨天自动清空。
        # 用 (日期, 节日id) 而不是只按日期：当天中途改配置导致命中节日变化时，
        # 新节日仍然能播（否则会出现"气泡说生日、动画还是上午那个节日"）。
        self._anim_day: str | None = None
        self._anim_played: set[tuple[str, str]] = set()
        self._timer = QTimer()
        self._timer.setInterval(self.TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------ 生命周期
    def start(self) -> None:
        self.apply_config()
        self._catch_up()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def is_running(self) -> bool:
        """调度 tick 是否在跑（AppShell 的懒启停门控据此决定重启还是只刷配置）。"""
        return bool(self._timer.isActive())

    def apply_config(self) -> None:
        """重读配置。

        统一走纯逻辑层 normalize_festival_config：清洗/钳制只有一处实现，
        且 config.json 被手改成非法值时回落默认而不是抛异常（本方法在
        start() 路径上执行，抛异常等于功能在启动期直接失败）。
        """
        config = getattr(self._app, "config", None)
        self._cfg = normalize_festival_config(config if config is not None else {})

    # ------------------------------------------------------------ 对外入口
    def remind_now(self, now: datetime | None = None) -> None:
        """手动提醒「今日节日」（右键菜单入口）。

        与语音报时的 say_now 同约定：**无视总开关**，由用户主动发起即执行；
        当天没有任何节日/节气时给出明确文案而不是静默无反应。

        ``now`` 仅供测试注入（生产路径取系统当前时间），与 ``_on_tick`` 同构。
        """
        self.apply_config()
        now = now or datetime.now()
        text = build_festival_text(now.date(), self._cfg, 0) or NO_FESTIVAL_TEXT
        self._bubble(text)
        self._speak(text)
        # 手动入口**每次都播**（force=True）：否则"想看一眼中秋动画"会因为当天已自动
        # 播过而毫无反应，与试听"立刻演示一次"的语义不符。
        self._play_festival_anim(now.date(), force=True)

    def should_speak_at(self, chime_slot: str) -> bool:
        """本分钟是否该让报时让位（由 AppShell 注入到报时服务的 yield_slot 钩子）。

        报时每次到点前先问这一句，因此让位判定**与两个服务 QTimer 的触发先后
        无关**——不会出现「报时先响、节日后响」于是两个都说的竞态。这正是不能
        靠节日去"抢"通道的原因。

        入参是报时槽位（``YYYY-MM-DDTHH:MM``，报时侧还可能带 ``#schedule`` 后缀，
        故只取前 16 位）；返回 True 表示节日语音要在这一分钟说话，报时应放弃该槽位。

        **现读配置而不是用构造期缓存的 ``_cfg``**：报时服务可能在本服务的
        ``apply_config()`` 之前就 tick 一次（AppShell.start 的装配顺序、以及用户
        恰好在节假日整点启动），用缓存值会让让位判定在该窗口内失效，从而两个
        功能同时出声。这里每次从 app.config 重新清洗，代价是每分钟至多一次。
        """
        config = getattr(self._app, "config", None)
        cfg = normalize_festival_config(config if config is not None else {})
        if not (cfg.get("enabled") and cfg.get("speak")):
            return False
        try:
            when = datetime.strptime(str(chime_slot)[:16], "%Y-%m-%dT%H:%M")
        except (TypeError, ValueError):
            return False
        return bool(reminder_slot(when, cfg))

    # ------------------------------------------------------------ 调度
    def _catch_up(self) -> None:
        """启动补提醒：当天有节日且已过首个提醒点时，立即补报一次。

        桌宠不保证常驻，用户可能中午才开机；没有这一步，当天的提醒点
        全部错过后就再也收不到，功能体感等于失效。
        """
        now = datetime.now()
        slot = startup_slot(now, self._cfg)
        if not slot or slot in self._fired:
            return
        self._roll_day(now.date())
        self._fired.add(slot)
        text = build_festival_text(now.date(), self._cfg, 0)
        if text:
            self._bubble(text)
            self._speak(text)
            self._play_festival_anim(now.date())

    def _on_tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        if not self._cfg.get("enabled"):
            return
        self._roll_day(now.date())
        slot = reminder_slot(now, self._cfg)
        if not slot or slot in self._fired:
            return
        self._fired.add(slot)
        # 当天第几次提醒：作为文案索引，使同一天多次提醒轮到不同句子。
        index = len(self._fired) - 1
        text = build_festival_text(now.date(), self._cfg, index)
        if text:
            self._bubble(text)
            self._speak(text)
            self._play_festival_anim(now.date())

    def _roll_day(self, today: date) -> None:
        if self._slot_day != today:
            self._slot_day = today
            self._fired = set()

    # ------------------------------------------------------------ 语音
    def _speak(self, text: str) -> None:
        """经语音报时服务的音频通道播报节日提醒。

        刻意**不自建播放器**：报时服务是进程内唯一的音频通道，共用它才能在结构上
        保证不叠音（详情见 voice_chime_service.speak 的说明）。通道不存在或播放
        失败都只降级为"有气泡没声音"，不影响提醒本身。
        """
        if not self._cfg.get("speak") or not text:
            return
        getter = getattr(self._app, "ensure_audio_channel", None)
        if not callable(getter):
            logger.warning("音频通道不可用，节日提醒仅出气泡")
            return
        try:
            channel = getter()
        except Exception:
            logger.exception("获取音频通道失败，节日提醒仅出气泡")
            return
        if channel is None:
            logger.warning("音频通道为空，节日提醒仅出气泡")
            return
        try:
            channel.speak(text, log_tag="节日提醒")
        except Exception:
            logger.exception("节日提醒语音播报失败")

    # ------------------------------------------------------------ 动画
    def _play_festival_anim(self, day: date, *, force: bool = False) -> None:
        """让桌宠播一段与今日节日匹配的内置动画（素材缺失时静默跳过）。

        - **只播主窗**（与 ``_bubble`` 同口径）：多开的小肥鱼不跟着播。
        - **当天只播第一次**（``force=False``）：一天最多 6 次提醒，每次都播同一段
          「吃月饼」会很吵；手动「今日节日」与设置页试听传 ``force=True``，每次都播。
        - **优先 ``request_link_anim``**：正在播的一次性动作（动作池/点击回应/移动）
          不被打断，节日动画排队等它播完；退化到 ``switch_clip(link_request=True)``。
        - **名字先按当前角色的动作池过滤**（``festival_animations.pick_animation``）：
          换角色或外部角色包缺这段素材时静默 no-op，而不是每次提醒都打一条
          "动画启动被拒绝"的 warning。动画播完的收尾（进 gap、回默认链）由窗口负责，
          服务侧不做任何善后。
        """
        if not self._cfg.get("animation"):
            return
        # 与 build_festival_text 同口径取 hits[0]：一天命中多个节日时，
        # 动画必须和文案指向同一个节日。
        festival = today_festival(day, self._cfg)
        if festival is None:
            return
        today = day.isoformat()
        if self._anim_day != today:  # 跨天复位（记账集合只保留当天）
            self._anim_day = today
            self._anim_played.clear()
        key = (today, festival.id)
        if not force and key in self._anim_played:
            return
        win = getattr(self._app, "win", None)
        if win is None or not win.isVisible():
            return
        name = pick_animation(festival.id, getattr(win, "acts", None) or ())
        if not name:
            return
        play = getattr(win, "request_link_anim", None)
        if callable(play):
            play(name)
            # 只有**确认真的上了屏**才记账：request_link_anim 在窗口正播一次性动作时
            # 只是排队，队里的请求可能被 request_link_idle（Agent 回 idle）或新的联动
            # 动作覆盖掉。没确认就留给下一个提醒点补播——宁可同一天补播一次，
            # 也不要当天一次都不播。
            if getattr(win, "anim", None) == name:
                self._anim_played.add(key)
            return
        switch = getattr(win, "switch_clip", None)
        if callable(switch):
            if switch(name, link_request=True) is not False:
                self._anim_played.add(key)

    # ------------------------------------------------------------ 提示
    def _bubble(self, text: str) -> None:
        """桌宠气泡展示节日提醒。

        与语音报时同策略：设置窗口打开等场景下 ``win.show_bubble`` 会被抑制，
        而节日提醒是用户主动关注的事件（一天只有一两次），此时退到桌宠气泡位
        直接展示，避免"弹一下就没了"；两者都不可用时再退到系统通知。
        """
        if not text:
            return
        app = self._app
        win = getattr(app, "win", None)
        if win is not None and win.isVisible():
            suppressed = bool(getattr(win, "_bubble_suppressed", False))
            if not suppressed:
                try:
                    win.show_bubble(text, duration_ms=self.BUBBLE_DURATION_MS)
                    return
                except Exception:
                    logger.exception("节日提醒气泡展示失败")
            try:
                bubble = getattr(win, "_speech_bubble", None)
                rect = win.visible_content_rect()
                scale = getattr(win, "scale", 1.0)
                if bubble is not None and rect is not None:
                    bubble.show_text(
                        text,
                        rect,
                        self.BUBBLE_DURATION_MS,
                        pet_scale=scale,
                        subtitle="",
                    )
                    return
            except Exception:
                logger.exception("节日提醒气泡降级展示失败")
        notify = getattr(app, "system_notify", None)
        if callable(notify):
            try:
                notify("节日提醒", text)
            except Exception:
                logger.exception("节日提醒桌面通知失败")
