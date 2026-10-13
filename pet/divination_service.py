# -*- coding: utf-8 -*-
"""抽签服务：**定今日签 → 摇签动作 → 气泡 → 语音**（GUI 线程）。

为什么独立成一个服务
--------------------
抽签是**用户主动触发**的一次性动作，不需要自己的定时器、不需要状态机；它复用的只有
三条既有能力：① 角色动作池（``win.request_link_anim``，与节日提醒同一处入口）；
② 气泡（与节日提醒同一套门禁与降级链）；③ 音频通道（``AppShell.ensure_audio_channel``，
进程内唯一音频出口，结构上保证不叠音）。

第五轮（她 2026-10-13：「抽签每天只能抽一次」）起改口径：**一天一支今日签**，
签号由当天日期确定性推出（见 ``pet.divination.daily_draw``），当天再点只重复显示
同一支；"今天抽过没有"以本机记录文件最后一条的日期为准，所以换进程/重启也算数。
仍然**没有定时器、没有任何个人信息**：没有任何一条记录离开本机。

与已归档的占星功能（`.scratch/fortune-astrology`）相比，这里不吃生日/出生地，
吃的只有一个"今天是几号"。

分层同 ``festival_service``：**顶层不 import Qt**（惰性引入），Qt 只出现在窗口能力里。
"""

from __future__ import annotations

import json
import logging
import os
import random
from datetime import date, datetime
from pathlib import Path

from . import divination_quotes as quotes
from .divination import (
    DEFAULT_DIVINATION_CONFIG,
    RECENT_DAYS,
    bubble_text,
    daily_draw,
    draw,
    normalize_divination_config,
    recent_days,
    speech_text,
    speech_title,
)
from .divination_quotes import ANIMATION_CANDIDATES

logger = logging.getLogger(__name__)

#: 本机抽签记录的文件名（放 config 目录，**不进仓库**）。
_HISTORY_NAME = "divination-history.jsonl"

#: 同一天再点「抽支签」时气泡上补的一句（第五轮每日一签）。
_REPEAT_NOTE = "今天已经抽过啦，还是这一支"


def history_file(config_dir) -> Path | None:
    """抽签记录文件路径（拿不到 config 目录时返回 ``None``）。"""
    if not config_dir:
        return None
    return Path(config_dir) / _HISTORY_NAME


def records(config_dir) -> list[dict]:
    """读全部抽签记录（时间正序）；坏行跳过，读不到就返回空表。"""
    path = history_file(config_dir)
    if path is None or not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                out.append(item)
    except Exception:
        logger.exception("抽签记录读取失败")
        return []
    return out


def record_day(item: dict):
    """记录里的本机自然日（``2026-10-13T09:12:00`` → ``date``）；认不出返回 ``None``。

    老格式与新格式只差 ``ts``，这条解析对两边都成立——**已有记录不用迁移**。
    """
    stamp = str(item.get("ts", ""))
    try:
        return datetime.fromisoformat(stamp).date()
    except (TypeError, ValueError):
        return None


def recent_numbers(config_dir, day, days) -> set[int]:
    """最近 ``days`` 天（不含 ``day`` 当天）抽过的签号——「一轮不重复」的跨天形态。"""
    wanted = {item for item in recent_days(day, days)}
    found: set[int] = set()
    for item in records(config_dir):
        if record_day(item) in wanted:
            try:
                found.add(int(item.get("no")))
            except (TypeError, ValueError):
                continue
    return found


def last_record(config_dir) -> dict | None:
    """读记录里的最后一条（设置页「最近抽到」用——设置跑在独立进程，只能走文件）。"""
    items = records(config_dir)
    return items[-1] if items else None


def _merge_record(item: dict) -> dict:
    """把记录里的签号/吉凶补回完整签（记录只存 ``ts/no/level``，念不出来）。

    签库是常量且"只追加不改号"，所以按号回查一定命中；万一那一号不在签库里
    （手工改过签库），退回记录本身——宁可少念两句，也不要在点击路径上抛。
    """
    try:
        number = int(item.get("no"))
    except (TypeError, ValueError):
        return dict(item)
    for stick in quotes.STICKS:
        if int(stick["no"]) == number:
            return {**dict(stick), "ts": item.get("ts")}
    logger.warning("记录里的第 %s 签不在签库里，只按记录显示", item.get("no"))
    return dict(item)


def desktop_dir() -> Path | None:
    """她的真桌面目录。

    优先读注册表 ``User Shell Folders`` 的 Desktop（她这台被 360 搬到了 `H:\\360MoveData\\...`，
    `~\\Desktop` 只是个空壳），拿不到再退 `~\\Desktop`。
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Desktop")
            path = Path(os.path.expandvars(str(value)))
            if path.is_dir():
                return path
    except Exception:
        pass
    fallback = Path.home() / "Desktop"
    return fallback if fallback.is_dir() else None


def _fallback_sound() -> Path | None:
    """内置摇签音效（`assets/sounds/start.wav`）——`resolve_builtin_sound` 认不出来时的兜底。"""
    path = Path(__file__).resolve().parent.parent / "assets" / "sounds" / "start.wav"
    return path if path.exists() else None


class DivinationService:
    """抽签的展示与朗读（AppShell 持有，懒创建）。"""

    BUBBLE_DURATION_MS = 12_000

    def __init__(self, app) -> None:
        self._app = app
        self._cfg: dict = dict(DEFAULT_DIVINATION_CONFIG)
        # 第五轮（她 2026-10-13：「抽签每天只能抽一次」）：「今日签」按日期确定取号，
        # 配额以**本机记录文件**为准（换进程/重启都算数），这两个字段只是当天缓存。
        self._last_day: date | None = None
        self._last_stick: dict | None = None

    # ------------------------------------------------------------ 配置
    def apply_config(self) -> None:
        config = getattr(self._app, "config", None)
        self._cfg = normalize_divination_config(config if config is not None else {})

    def config(self) -> dict:
        return dict(self._cfg)

    def drawn_this_round(self) -> int:
        """第五轮起不再有"一轮"概念（一天一支），保留此方法只为兼容调试调用。"""
        return 0

    def drawn_today(self) -> dict | None:
        """今天已经抽过的那支（内存里有就返回；没有返回 ``None``）。"""
        return dict(self._last_stick) if self._last_stick else None

    # ------------------------------------------------------------ 对外入口
    def draw_now(self, rng: random.Random | None = None, *, speak: bool | None = None,
                 day: date | None = None) -> dict:
        """抽「今日签」并播出去（右键菜单「抽支签」的入口）。

        与语音报时的 ``say_now``、节日提醒的 ``remind_now`` 同约定：**无视总开关**，
        用户主动发起即执行。返回抽到的那支签（用例据此断言，不依赖窗口行为）。

        **每天一支**（她 2026-10-13 的口径）：当天第一次＝今日签（正式的那支，
        写记录、上上才落签卡）；当天再点＝显示**同一支** + 一句"今天已经抽过啦"，
        不重新摇签、不重复记账、不重复落卡。次日按本机自然日换新签。
        ``day`` 可注入（用例跨日）；它同时决定"今日"的判定、记录时间戳与签卡文件名。
        ``rng`` 在每日一签下用不到（取号由日期决定），保留只为不破坏既有调用点。
        """
        self.apply_config()
        today = day or date.today()
        is_new, stick, repeated = self._daily(today)
        self._animate()
        self._sound()
        note = _REPEAT_NOTE if repeated else ""
        self._bubble(bubble_text(stick, today, note=note), stick)
        want_speak = self._cfg.get("speak", True) if speak is None else speak
        if want_speak:
            self._speak(speech_text(stick, today))
        if is_new:
            self._record(stick, today)
            if str(stick.get("level")) == "上上":
                self._save_card(stick, today)
        return stick

    # ------------------------------------------------------------ 今日签（配额）
    def _daily(self, today: date) -> tuple[bool, dict, bool]:
        """定今天的签：``(是否新抽, 签, 是否重复点)``。

        判定顺序：① 内存缓存（同一天的第二次点击，连文件都不用读）；② 本机记录最后
        一条的日期（跨进程/重启也算数，且**不依赖签库里还有那支**——记录里的号直接
        拿来显示）；③ 都没有才按日期取新签——取号时避开最近 ``RECENT_DAYS`` 天抽过的。
        """
        config_dir = self._history_dir()
        history = records(config_dir)
        if history:
            last_day = record_day(history[-1])
            if last_day is not None and self._last_day != last_day:
                self._last_day, self._last_stick = last_day, _merge_record(history[-1])
        if self._last_day == today and self._last_stick:
            return False, dict(self._last_stick), True
        stick = daily_draw(today, recent=recent_numbers(config_dir, today, RECENT_DAYS))
        self._last_day, self._last_stick = today, dict(stick)
        return True, stick, False

    # ------------------------------------------------------------ 摇签音效
    def _sound(self) -> None:
        """摇签的这一下给个声响（复用点击音效的播放器与音量，不新增通道）。

        受「摇签动作」开关与「点击音效」总开关/音量约束——她本来就用小黄鸭那套音效包，
        风格一致；任一不可用就安静跳过。
        """
        if not self._cfg.get("animation", True):
            return
        config = getattr(self._app, "config", None)
        getter = getattr(config, "get", None)
        if callable(getter) and not bool(getter("click_sound_enabled", True)):
            return
        try:
            from . import click_sound

            source = click_sound.resolve_builtin_sound("start") or _fallback_sound()
            if source is None:
                return
            volume = float(getter("click_sound_volume", 1.0)) if callable(getter) else 1.0
            click_sound.play_click_sound(source, volume=volume)
        except Exception:
            logger.exception("抽签音效播放失败")

    # ------------------------------------------------------------ 抽签记录
    def _record(self, stick: dict, day: date | None = None) -> None:
        """把这一签追加到本机记录（`<config.dir>/divination-history.jsonl`，best-effort）。

        记录只在本机、进不了仓库；设置页「最近抽到」读同一个文件（设置跑在独立进程里，
        所以走文件而不是内存）。**每天只追加一条**（当日再点不写第二条），
        字段仍是 ``ts/no/level`` 三个——老记录不用迁移。
        ``ts`` 的日期部分就是服务层判定"今天抽过没有"的依据（换进程也算数），
        所以 ``day``（用例注入的"今天"）要写进去，不能写真实系统日期。
        """
        path = history_file(self._history_dir())
        if path is None:
            return
        today = day or date.today()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps({
                "ts": datetime.combine(today, datetime.now().time()).isoformat(timespec="seconds"),
                "no": int(stick["no"]),
                "level": str(stick["level"]),
            }, ensure_ascii=False)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            logger.exception("抽签记录写入失败")

    def _history_dir(self):
        config = getattr(self._app, "config", None)
        return getattr(config, "dir", None)

    # ------------------------------------------------------------ 上上签卡
    def _save_card(self, stick: dict, day: date | None = None) -> None:
        """抽到上上时落一张签卡到她的真桌面（best-effort，失败只记日志）。"""
        try:
            from .divination_card import render_card

            target_dir = desktop_dir()
            if target_dir is None:
                return
            stamp = (day or date.today()).isoformat()
            render_card(stick, target_dir / f"签卡-第{int(stick['no'])}签-{stamp}.png")
        except Exception:
            logger.exception("上上签卡生成失败")

    # ------------------------------------------------------------ 摇签动作
    def _animate(self) -> None:
        """抽签时请角色动一下（与节日提醒同一处入口与同一套保护）。

        口径照 ``festival_service._play_animation``：**只在窗口可见且有动作池时**动手；
        优先 ``request_link_anim``（正在播的一次性动作不被打断，排队等它播完），
        退化到 ``switch_clip(link_request=True)``；动作池里一个候选都没有就安静跳过。
        """
        if not self._cfg.get("animation", True):
            return
        win = getattr(self._app, "win", None)
        if win is None or not win.isVisible():
            return
        available = set(getattr(win, "acts", None) or ())
        if not available:
            return
        name = next((candidate for candidate in ANIMATION_CANDIDATES if candidate in available), None)
        if name is None:
            return
        play = getattr(win, "request_link_anim", None)
        if callable(play):
            try:
                play(name)
                return
            except Exception:
                logger.exception("抽签动画播放失败（request_link_anim）")
        switch = getattr(win, "switch_clip", None)
        if callable(switch):
            try:
                switch(name, link_request=True)
            except TypeError:
                try:
                    switch(name)
                except Exception:
                    logger.exception("抽签动画播放失败（switch_clip）")
            except Exception:
                logger.exception("抽签动画播放失败（switch_clip）")

    # ------------------------------------------------------------ 气泡
    def _bubble(self, text: str, stick: dict | None = None) -> None:
        """展示气泡：与节日提醒同一套门禁与降级链（直写 → 气泡位 → 系统通知）。"""
        if not text:
            return
        from . import window_alerts

        app = self._app
        win = getattr(app, "win", None)
        if win is not None and win.isVisible():
            if window_alerts.sprite_in_flight(win):
                return
            if not window_alerts.bubble_blocked(win):
                try:
                    win.show_bubble(text, duration_ms=self.BUBBLE_DURATION_MS)
                    return
                except Exception:
                    logger.exception("抽签气泡展示失败")
            try:
                bubble = getattr(win, "_speech_bubble", None)
                rect = win.visible_content_rect()
                scale = getattr(win, "scale", 1.0)
                if bubble is not None and rect is not None:
                    bubble.show_text(text, rect, self.BUBBLE_DURATION_MS,
                                     pet_scale=scale, subtitle="")
                    return
            except Exception:
                logger.exception("抽签气泡降级展示失败")
        notify = getattr(app, "system_notify", None)
        if callable(notify):
            try:
                notify(speech_title(stick) if stick else "抽签", text)
            except Exception:
                logger.exception("抽签桌面通知失败")

    # ------------------------------------------------------------ 语音
    def _speak(self, text: str) -> None:
        """经既有音频通道朗读（与节日提醒/语音报时同一条路，不自建播放器）。"""
        if not text:
            return
        getter = getattr(self._app, "ensure_audio_channel", None)
        if not callable(getter):
            logger.warning("音频通道不可用，抽签仅出气泡")
            return
        try:
            channel = getter()
        except Exception:
            logger.exception("获取音频通道失败，抽签仅出气泡")
            return
        if channel is None:
            logger.warning("音频通道为空，抽签仅出气泡")
            return
        try:
            channel.speak(text, log_tag="抽签")
        except Exception:
            logger.exception("抽签语音播报失败")

    # ------------------------------------------------------------ 设置页预览
    def preview_text(self, rng: random.Random | None = None) -> str:
        """设置页/用例预览用：抽一支并返回气泡文本（不碰窗口）。

        预览**刻意走真随机**（不走 :func:`pet.divination.daily_draw`）：它只是给设置页
        看文案长什么样，不该占掉当天的今日签，也不该写记录。
        """
        self.apply_config()
        stick = draw(rng)
        return bubble_text(stick)
