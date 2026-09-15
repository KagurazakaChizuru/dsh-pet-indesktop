"""整点报时调度服务（AppShell 持有，GUI 线程）。

模式对齐 todo_reminder.py：
- QTimer 秒级 tick，每次重读 config（内存 dict），设置保存后 1 秒内生效；
- 命中报时点 → 气泡（show_bubble）+ 可选语音（edge-tts）；
- 配置里 enabled 被关闭时，下个 tick 自停 timer，不占用资源。
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt

from .chime_clock import (
    ChimeStore,
    chime_text,
    clean_chime_data,
    current_chime_keys,
    default_chime_data,
    quotes_path,
)
from .chime_tts import ChimeTts, DEFAULT_VOICE

logger = logging.getLogger(__name__)

TICK_INTERVAL_MS = 1000
BUBBLE_DURATION_MS = 8000


class ChimeService:
    """整点报时服务：构造后调用 start() 开始调度，stop() 停止。"""

    def __init__(self, app) -> None:
        self._app = app
        self._cfg: dict = dict(default_chime_data())
        self._last_keys: set[str] = set()
        self._tts: ChimeTts | None = None
        self._store: ChimeStore | None = None
        self._timer = QTimer()
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.timeout.connect(self._on_tick)

    # ---------------- 生命周期

    def start(self) -> None:
        self.apply_config()
        if not self._timer.isActive():
            self._timer.start()
        self._on_tick()

    def stop(self) -> None:
        self._timer.stop()
        self._last_keys.clear()

    def apply_config(self) -> None:
        """重读配置（保存设置后调用 / 每次 tick 也会自刷新）。"""
        config = getattr(self._app, "config", None)
        raw = config.get("chime") if config is not None else None
        self._cfg = clean_chime_data(raw if raw is not None else None)

    # ---------------- 设置页交互

    def preview(self, text: str) -> None:
        """试听：用当前配置的音色与音量合成并播放。"""
        cfg = self._cfg
        self._speak(text, cfg)

    # ---------------- 调度

    def _on_tick(self) -> None:
        config = getattr(self._app, "config", None)
        raw = config.get("chime") if config is not None else None
        self._cfg = clean_chime_data(raw if raw is not None else None)
        cfg = self._cfg
        if not cfg.get("enabled"):
            # 配置里被关闭：自停，等下次 start() 再拉起
            if self._timer.isActive():
                self._timer.stop()
            self._last_keys.clear()
            return
        now = datetime.now()
        keys = current_chime_keys(now, cfg)
        fires = keys - self._last_keys
        self._last_keys = keys
        for key in fires:
            try:
                self._notify(key, now, cfg)
            except Exception:
                logger.exception("整点报时触发失败: %s", key)

    def _notify(self, key: str, now: datetime, cfg: dict) -> None:
        if key.startswith("custom:"):
            kind = "custom"
        elif key.startswith("interval:"):
            kind = "interval"
        else:
            kind = "hour"
        store = self._store_for(cfg)
        quote = store.pick_quote(bool(cfg.get("quote_enabled", True)))
        text = chime_text(now, cfg, quote=quote, kind=kind)
        # 气泡
        win = getattr(self._app, "win", None)
        if win is not None and getattr(win, "isVisible", lambda: False)():
            try:
                win.show_bubble(text, duration_ms=BUBBLE_DURATION_MS)
            except Exception:
                logger.exception("气泡展示失败")
        # 语音
        if cfg.get("speech_enabled", True):
            self._speak(text, cfg)

    # ---------------- 内部

    def _store_for(self, cfg: dict) -> ChimeStore:
        config = getattr(self._app, "config", None)
        config_dir = getattr(config, "dir", Path("."))
        instance_id = str(getattr(config, "instance_id", "") or "")
        path = quotes_path(config_dir, instance_id)
        if self._store is None or self._store.path != path:
            self._store = ChimeStore(path)
        return self._store

    def _speak(self, text: str, cfg: dict) -> None:
        try:
            if self._tts is None:
                config = getattr(self._app, "config", None)
                config_dir = getattr(config, "dir", Path("."))
                self._tts = ChimeTts(Path(config_dir) / "chime_tts_cache")
            voice = str(cfg.get("voice_custom") or cfg.get("voice") or DEFAULT_VOICE)
            volume = float(cfg.get("volume", 1.0))
            rate = int(cfg.get("rate", 0) or 0)
            pitch = int(cfg.get("pitch", 0) or 0)
            self._tts.speak(text, voice=voice, volume=volume, rate=rate, pitch=pitch)
        except Exception:
            logger.exception("语音播报失败")
