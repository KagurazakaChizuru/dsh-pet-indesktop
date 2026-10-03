# -*- coding: utf-8 -*-
"""Phase 4.1b 窗口能力 parity offscreen 单测（QT_QPA_PLATFORM=offscreen 可跑）。

每条对应一条「旧语义 = 新行为」（pet/window.py / pet/window_screen.py）：
- FullscreenCursorWatcher：全屏探测翻转、配置门关停即恢复、光标 HIDDEN
  0.2s 去抖、探针异常不翻转；
- OverlayShell：on_top 应用与持久化、有效穿透 = 用户 OR 光标自动、
  全屏隐藏/恢复、拖拽滞留冲刷、runtime 避让标记写/更新/删除、托盘显隐。

纪律：探测函数注入假探针、假钟注入；同步直调 handler，不 sleep 赌时序。
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRect, Qt, Signal
from PySide6.QtWidgets import QApplication

from pet.overlay_peripherals import FullscreenCursorWatcher
from pet.overlay_shell import OverlayShell

app = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- 假件
class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, s):
        self.now += s


class FakeScreen(QObject):
    geometryChanged = Signal(QRect)
    availableGeometryChanged = Signal(QRect)
    refreshRateChanged = Signal(float)

    def __init__(self, geo, avail, *, dpr=1.0, refresh=60.0):
        super().__init__()
        self._geo = QRect(*geo)
        self._avail = QRect(*avail)
        self._dpr = float(dpr)
        self._refresh = float(refresh)

    def geometry(self):
        return QRect(self._geo)

    def availableGeometry(self):
        return QRect(self._avail)

    def devicePixelRatio(self):
        return self._dpr

    def refreshRate(self):
        return self._refresh

    def set_refresh(self, rate):
        """同分辨率下切刷新率（60↔165/180）：触发 refreshRateChanged。"""
        self._refresh = float(rate)
        self.refreshRateChanged.emit(self._refresh)


class CapSprite:
    SIZE = (120, 80)

    def __init__(self, lib, pos, scale):
        self.lib = lib
        self.pos = QPointF(pos)
        self.scale = scale
        self.home_screen = None
        self.interaction_state = "normal"
        self.dragging = False

    def rect(self):
        return QRect(int(self.pos.x()), int(self.pos.y()), *self.SIZE)

    def body_rect(self):
        r = self.rect()
        return QRect(r.x() + 10, r.y() + 10, r.width() - 20, r.height() - 20)

    def set_dpr(self, dpr):
        pass

    def set_bounds(self, bounds):
        pass

    def set_pos(self, pos):
        self.pos = QPointF(pos)

    def advance(self, dt):
        return None

    def paint(self, painter):
        pass

    def alpha_at(self, local):
        return 0

    def on_release(self, pos):
        pass


class CapLibrary:
    def __init__(self):
        self.manifest = {}
        self.folder_map = {}
        self.folder_files = {}

    def names(self):
        return []

    def stop_all_clips(self):
        pass

    def pause_warm(self):
        pass


class CapConfig:
    def __init__(self, tmp_path: Path, values=None):
        self._values = dict(values or {})
        self.dir = tmp_path
        self.instance_id = ""
        self.saved = 0

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value

    def save(self):
        self.saved += 1


class CapInstance:
    def __init__(self, config):
        self.config = config

    def _create_library(self, character_id):
        return CapLibrary()


def _make_shell(tmp_path, config_values=None, screen=None):
    config = CapConfig(tmp_path, config_values)
    instance = CapInstance(config)
    screen = screen or FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    shell = OverlayShell(
        app, instance, screen=screen,
        sprite_factory=lambda lib, pos, scale: CapSprite(lib, pos, scale))
    return shell


def _markers(config_dir: Path):
    return list(config_dir.glob("pet-runtime-v2-*.json"))


# ---------------------------------------------------------------- watcher 单元
def test_watcher_fullscreen_flip_and_gate():
    state = {"hit": False}
    w = FullscreenCursorWatcher(fullscreen_probe=lambda: state["hit"],
                                cursor_probe=lambda: "UNKNOWN")
    hits = []
    w.fullscreen_changed.connect(hits.append)
    w.set_fullscreen_enabled(True)
    state["hit"] = True
    w._poll_fullscreen()
    assert hits == [True]
    state["hit"] = False
    w._poll_fullscreen()
    assert hits == [True, False]
    # 配置门：开着时被隐藏（hit=True），关门 → 立即恢复 False 并停表
    state["hit"] = True
    w._poll_fullscreen()
    assert hits[-1] is True
    w.set_fullscreen_enabled(False)
    assert hits[-1] is False
    assert not w._fs_timer.isActive()
    w.stop()


def test_watcher_cursor_debounce_and_gate():
    clock = FakeClock()
    state = {"vis": "HIDDEN"}
    w = FullscreenCursorWatcher(fullscreen_probe=lambda: False,
                                cursor_probe=lambda: state["vis"],
                                clock=clock)
    events = []
    w.cursor_visibility_changed.connect(events.append)
    w.set_cursor_enabled(True)
    w._poll_cursor()                 # t=100：首次 HIDDEN，开始计时
    assert events == []
    clock.advance(0.1)
    w._poll_cursor()                 # 0.1s < 0.2s：仍不报
    assert events == []
    clock.advance(0.15)
    w._poll_cursor()                 # 0.25s ≥ 0.2s：报 HIDDEN
    assert events == ["HIDDEN"]
    state["vis"] = "SHOWING"
    w._poll_cursor()
    assert events == ["HIDDEN", "SHOWING"]
    # 配置门：关门 → 恢复 SHOWING 并停表
    w.set_cursor_enabled(False)
    assert events[-1] == "SHOWING"
    assert not w._cursor_timer.isActive()
    w.stop()


def test_watcher_probe_exception_keeps_state():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            return True
        raise RuntimeError("probe boom")

    w = FullscreenCursorWatcher(fullscreen_probe=flaky,
                                cursor_probe=lambda: "UNKNOWN")
    hits = []
    w.fullscreen_changed.connect(hits.append)
    w.set_fullscreen_enabled(True)
    w._poll_fullscreen()
    w._poll_fullscreen()             # 异常：不翻转
    assert hits == [True]
    assert w._fs_last is True
    w.stop()


# ---------------------------------------------------------------- shell 能力
def test_on_top_applied_from_config_and_persisted(tmp_path):
    shell = _make_shell(tmp_path, {"on_top": False})
    flags = shell.overlay.windowFlags()
    assert not (flags & Qt.WindowType.WindowStaysOnTopHint)
    shell.set_on_top(True)
    assert shell.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert shell._config.get("on_top") is True
    assert shell._config.saved >= 1
    shell._delete_runtime_marker()


def test_effective_through_is_user_or_auto(tmp_path):
    shell = _make_shell(tmp_path, {"mouse_through": False})
    assert shell.overlay.mouse_through is False
    # 用户开（菜单直写收编）
    shell.overlay.set_mouse_through(True)
    assert shell._user_mouse_through is True
    assert shell._config.get("mouse_through") is True
    assert shell.overlay.mouse_through is True
    # 用户关、光标自动开（HIDDEN 事件）→ 仍然有效
    shell.overlay.set_mouse_through(False)
    shell._on_cursor_visibility_changed("HIDDEN")
    assert shell._auto_cursor_hidden is True
    assert shell.overlay.mouse_through is True
    # 光标恢复 → 全关
    shell._on_cursor_visibility_changed("SHOWING")
    assert shell.overlay.mouse_through is False
    shell._delete_runtime_marker()


def test_cursor_restore_pending_flushed_on_grab_finished(tmp_path):
    shell = _make_shell(tmp_path, {"mouse_through": False})
    shell._on_cursor_visibility_changed("HIDDEN")
    assert shell.overlay.mouse_through is True
    # 拖拽中收到 SHOWING → 滞留
    shell.overlay._mouse_grab = object()
    shell._on_cursor_visibility_changed("SHOWING")
    assert shell._cursor_restore_pending is True
    assert shell.overlay.mouse_through is True   # 滞留未解除
    shell.overlay._mouse_grab = None
    shell._on_grab_finished()
    assert shell._cursor_restore_pending is False
    assert shell.overlay.mouse_through is False
    shell._delete_runtime_marker()


def test_fullscreen_hides_and_restores(tmp_path):
    shell = _make_shell(tmp_path, {"auto_hide_fullscreen": True})
    shell.overlay.show()
    shell._on_fullscreen_changed(True)
    assert shell._auto_hidden is True
    assert not shell.overlay.isVisible()
    shell._on_fullscreen_changed(False)
    assert shell._auto_hidden is False
    assert shell.overlay.isVisible()
    shell.overlay.close()
    shell._delete_runtime_marker()


def test_fullscreen_hidden_stays_when_config_off(tmp_path):
    shell = _make_shell(tmp_path, {"auto_hide_fullscreen": False})
    # 配置关 → watcher 全屏门未启用（计时器未开）
    assert not shell._watcher._fs_timer.isActive()
    shell._delete_runtime_marker()


def test_runtime_marker_lifecycle(tmp_path):
    shell = _make_shell(tmp_path)
    shell.start()
    markers = _markers(tmp_path)
    assert len(markers) == 1
    data = json.loads(markers[0].read_text(encoding="utf-8"))
    body = shell.sprite.body_rect()
    origin = shell.overlay.geometry().topLeft()
    assert (data["x"], data["y"]) == (origin.x() + body.x(), origin.y() + body.y())
    assert (data["w"], data["h"]) == (body.width(), body.height())
    # 移动 → 节流后更新
    shell.sprite.set_pos(QPointF(500, 400))
    shell._last_marker_write = 0.0
    shell._on_main_sprite_moved(shell.sprite)
    data2 = json.loads(markers[0].read_text(encoding="utf-8"))
    assert (data2["x"], data2["y"]) == (origin.x() + 500 + 10, origin.y() + 400 + 10)
    shell.stop()
    assert _markers(tmp_path) == []


def test_tray_toggle_visibility(tmp_path):
    shell = _make_shell(tmp_path)
    shell.overlay.show()
    shell._toggle_pet_visible()
    assert not shell.overlay.isVisible()
    shell._toggle_pet_visible()
    assert shell.overlay.isVisible()
    shell.overlay.close()
    shell._delete_runtime_marker()


def test_refresh_settings_reapplies(tmp_path):
    shell = _make_shell(tmp_path, {"mouse_through": False, "on_top": True})
    shell._config.set("mouse_through", True)
    shell._config.set("on_top", False)
    shell.refresh_settings()
    assert shell.overlay.mouse_through is True
    assert not (shell.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    shell._delete_runtime_marker()


def test_refresh_rate_change_rewires_tick_interval(tmp_path):
    """同分辨率切刷新率（60→180Hz）时 refreshRateChanged 应让 tick 间隔立即重读。

    回归：此前只接 geometryChanged，同分辨率模式切换不重读刷新率，
    运行中的桌宠卡在 16ms(60Hz) 档直到重启（任务A 实锤缺口）。
    """
    screen = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040), refresh=60.0)
    shell = _make_shell(tmp_path, {"on_top": False}, screen=screen)
    shell.start()
    driver = shell.overlay.tick_driver
    assert driver._timer.interval() == 16
    screen.set_refresh(180.0)
    assert driver._timer.interval() == 6
    shell._delete_runtime_marker()
