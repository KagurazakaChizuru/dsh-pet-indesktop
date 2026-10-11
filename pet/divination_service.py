# -*- coding: utf-8 -*-
"""抽签服务：**抽 → 摇签动作 → 气泡 → 语音**（GUI 线程）。

为什么独立成一个服务
--------------------
抽签是**用户主动触发**的一次性动作，不需要自己的定时器、不需要状态机；它复用的只有
三条既有能力：① 角色动作池（``win.request_link_anim``，与节日提醒同一处入口）；
② 气泡（与节日提醒同一套门禁与降级链）；③ 音频通道（``AppShell.ensure_audio_channel``，
进程内唯一音频出口，结构上保证不叠音）。

与已归档的占星功能（`.scratch/fortune-astrology`）相比，这里**没有定时器、没有
日期种子、没有任何个人信息**：签是抽的，抽完就完。

分层同 ``festival_service``：**顶层不 import Qt**（惰性引入），Qt 只出现在窗口能力里。
"""

from __future__ import annotations

import logging
import random
from datetime import date

from .divination import (
    DEFAULT_DIVINATION_CONFIG,
    bubble_text,
    draw,
    normalize_divination_config,
    speech_text,
    speech_title,
)
from .divination_quotes import ANIMATION_CANDIDATES

logger = logging.getLogger(__name__)


class DivinationService:
    """抽签的展示与朗读（AppShell 持有，懒创建）。"""

    BUBBLE_DURATION_MS = 12_000

    def __init__(self, app) -> None:
        self._app = app
        self._cfg: dict = dict(DEFAULT_DIVINATION_CONFIG)

    # ------------------------------------------------------------ 配置
    def apply_config(self) -> None:
        config = getattr(self._app, "config", None)
        self._cfg = normalize_divination_config(config if config is not None else {})

    def config(self) -> dict:
        return dict(self._cfg)

    # ------------------------------------------------------------ 对外入口
    def draw_now(self, rng: random.Random | None = None, *, speak: bool | None = None,
                 day: date | None = None) -> dict:
        """抽一支签并播出去（右键菜单「抽支签」的入口）。

        与语音报时的 ``say_now``、节日提醒的 ``remind_now`` 同约定：**无视总开关**，
        用户主动发起即执行。返回抽到的那支签（用例据此断言，不依赖窗口行为）。

        ``day`` 只影响「今日宜穿色」那一行（黄历按日柱算；签名本身与日期无关）。
        """
        self.apply_config()
        today = day or date.today()
        stick = draw(rng)
        self._animate()
        self._bubble(bubble_text(stick, today), stick)
        want_speak = self._cfg.get("speak", True) if speak is None else speak
        if want_speak:
            self._speak(speech_text(stick, today))
        return stick

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
        """设置页/用例预览用：抽一支并返回气泡文本（不碰窗口）。"""
        self.apply_config()
        stick = draw(rng)
        return bubble_text(stick)
