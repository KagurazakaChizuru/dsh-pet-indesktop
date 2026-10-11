# -*- coding: utf-8 -*-
"""自有功能（进程内 DLC）与 Core 之间的**公开接入面**。

出处：上游 `docs/plugin-phase-01-foundation/PLUGIN-DLC-ARCHITECTURE.md`
§5.1（进程内功能型 DLC）与 §6（API 与信任边界）——原文要求：

    「进程内 DLC 必须通过公开 API 接入，**不得依赖 `PetApp`、`PetWindow` 私有字段**。」

本仓库此前的自有功能是直接摸的：`app.win.show_bubble` / `win._speech_bubble` /
`win.visible_content_rect` / `win.acts` / `win.request_link_anim` / `win.switch_clip`
/ `app.config` / `app.system_notify`。R1/R2 的做法是把这些**收成 context 上的
一组方法**，功能侧只认 context；Core 侧（`AppShell`）负责把真实实现注入进来。

因此本模块**零 Qt**、只依赖注入进来的可调用对象，可以脱离 GUI 直接单测。
注入项一律可为 ``None``（功能必须自己降级，不许假设 Core 一定提供）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

#: 气默认时长（各功能自己的时长会被 Core 侧的实现用上）
DEFAULT_BUBBLE_MS = 8_000


@dataclass(frozen=True)
class FeatureContext:
    """Core 提供给自有功能的全部能力（只读、可注入、零 Qt）。

    字段都是**函数**而不是对象：这样 Core 不必把 `PetWindow` 交出去，
    功能也拿不到任何可以越界改状态的句柄。
    """

    feature_id: str = ""
    #: 读配置：等价于 `config.get(key, default)`（插件配置最终应进 `plugins.<id>`）
    config_get: Callable[[str, Any], Any] | None = None
    #: 窗口是否可见（不可见时功能应当只记账不出声）
    is_visible: Callable[[], bool] | None = None
    #: 显示气泡（Core 的直接通道）
    show_bubble: Callable[[str, int], Any] | None = None
    #: 气泡兜底通道（直写失败时用）
    show_bubble_fallback: Callable[[str, int], Any] | None = None
    #: 当前是否被遮挡/在飞（Core 的门禁）
    bubble_blocked: Callable[[], bool] | None = None
    #: 可用动作名池
    animations: Callable[[], Any] | None = None
    #: 播放一次性动画（Core 负责排队/回退语义）
    play_animation: Callable[[str], Any] | None = None
    #: 用 Core 的音频通道说一句
    speak: Callable[[str], Any] | None = None
    #: 系统通知
    notify: Callable[[str, str], Any] | None = None
    #: 运行期数据目录（`config.dir`，功能不要把数据写进仓库）
    data_dir: Callable[[], Any] | None = None
    #: 其它由 Core 显式开放的能力（键名即合同，别拿它当后门）
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------ 便捷读法
    def config(self, key: str, default: Any = None) -> Any:
        if not callable(self.config_get):
            return default
        try:
            return self.config_get(key, default)
        except Exception:
            return default

    def flag(self, key: str, default: bool = True) -> bool:
        return bool(self.config(key, default))

    def visible(self) -> bool:
        if not callable(self.is_visible):
            return False
        try:
            return bool(self.is_visible())
        except Exception:
            return False

    def available_animations(self) -> set[str]:
        if not callable(self.animations):
            return set()
        try:
            return {str(name) for name in (self.animations() or ())}
        except Exception:
            return set()

    def blocked(self) -> bool:
        if not callable(self.bubble_blocked):
            return False
        try:
            return bool(self.bubble_blocked())
        except Exception:
            return False

    # ------------------------------------------------------------ 动作（全部吞异常）
    def bubble(self, text: str, duration_ms: int = DEFAULT_BUBBLE_MS) -> bool:
        """出气泡：直写 → 兜底通道；两条都不成返回 False（功能可再退系统通知）。"""
        if not text:
            return False
        for channel in (self.show_bubble, self.show_bubble_fallback):
            if not callable(channel):
                continue
            try:
                channel(text, duration_ms)
                return True
            except Exception:
                continue
        return False

    def animate(self, name: str) -> bool:
        if not callable(self.play_animation) or not name:
            return False
        try:
            self.play_animation(name)
            return True
        except Exception:
            return False

    def say(self, text: str) -> bool:
        if not callable(self.speak) or not text:
            return False
        try:
            self.speak(text)
            return True
        except Exception:
            return False

    def tell(self, title: str, message: str) -> bool:
        if not callable(self.notify):
            return False
        try:
            self.notify(title, message)
            return True
        except Exception:
            return False

    def data_path(self) -> Any:
        if not callable(self.data_dir):
            return None
        try:
            return self.data_dir()
        except Exception:
            return None
