# -*- coding: utf-8 -*-
"""O5 后台常驻门控：DSH 桥接读方 / 进程级共享全屏 watcher。

默认配置下这两项都该真正停下来（现状是**无条件**常驻）：

1. DSH 桥目录的唯一读方 ``DshMonitor``（1.5s 一轮的桥目录轮询 + 3s 一节拍的
   端口探活 + dsh_state 收敛器，全部在它自己的 worker 线程里）的全部输出只喂
   DSH 联动管线——DSH 联动没开时它读的桥接插件根本没装，纯空转。
   门 = ``agent_link.dsh``（``AgentLinkManager.apply_config`` 按它启停监视器）。
2. overlay 拓扑下进程级共享全屏 watcher 的扇出目标是 sprite 世界的壳，而该壳
   **刻意不暴露** ``_watch_required`` / ``_cursor_hidden_passthrough_enabled``
   / ``auto_hide_fullscreen``（overlay 自持 ``FullscreenCursorWatcher``）——
   ``_any_wants()`` 恒 False → 常驻线程每秒空醒。overlay 拓扑不启该线程。

装配口径：真 AppShell + 真 Config + 真共享子系统/跟踪器，真 ``AppShell.start()``；
只有"起桌宠"那一层（建窗口/合成窗、托盘、会话结束探测器、灵动岛、可选服务）
置空——与 ``tests/test_desktop_pet_features.py`` 的 ``owner.start()`` 同款边界。
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import pet.app as app_mod
import pet.overlay_shell as overlay_shell_mod
from pet import harness_launcher
from pet.app import AppShell
from pet.config import Config

app = QApplication.instance() or QApplication([])


class _StubWin:
    """legacy 窗替身：只提供共享全屏 watcher 自省需要的读取面。"""

    def __init__(self, *, watch: bool = True):
        self._watch = watch
        self.auto_hide_fullscreen = False

    def _watch_required(self):
        return self._watch

    def _cursor_hidden_passthrough_enabled(self):
        return False

    def isVisible(self):
        return True


class _StubOverlayShell:
    """overlay 壳替身：真实壳不暴露 ``_watch_required`` 一族（sprite 世界自持）。"""

    def __init__(self, qapp, instance, **kwargs):
        self.qapp = qapp
        self.instance = instance
        self.kwargs = kwargs
        self.started = 0

    def start(self):
        self.started += 1

    def set_file_interpret_offer(self, offer):
        pass


def _start_shell(tmp_path, monkeypatch, *, dsh=False, topology="legacy",
                 win=None, ui_stub=True):
    """真 AppShell.start()（"起桌宠"那一层置空）。

    默认显式走 ``legacy`` 拓扑：不建 OverlayShell / 素材库（起桌宠那一层），
    与本文件被测的三件事（跟踪器门、共享全屏 watcher 门、应用链计数）无关；
    overlay 分支专门由 ``test_overlay_topology_skips_shared_fullscreen_watcher``
    用壳替身覆盖。
    """
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", topology)
    config = Config(base=tmp_path)
    if dsh:
        agent_cfg = dict(config.get("agent_link") or {})
        agent_cfg["dsh"] = True
        config.set("agent_link", agent_cfg)
    assert config.save()  # 落盘：外部变更监视的前提
    shell = AppShell(app, config)
    if ui_stub:
        shell.instance._create_ui = lambda cid: None
        shell.instance._apply_spawn_offset = lambda: None
        shell.instance._sync_animation_prewarm = lambda: None
        shell.instance._refresh_chat_windows = lambda: None
        shell._apply_balance_timer = lambda: None
        shell._sync_dynamic_island = lambda: None
        shell._install_session_watcher = lambda: None
        shell._sync_todo_service = lambda: None
        shell._sync_chime_service = lambda: None
        shell._sync_festival_service = lambda: None
    if win is not None:
        shell.instance.win = win
    monkeypatch.setattr(app_mod.QTimer, "singleShot", lambda *a, **k: None)
    shell.start()
    return shell


def _pump(seconds: float) -> None:
    """有界泵事件循环（不赌时序：只用来让已排队的信号/定时器跑完）。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _save_external(config) -> None:
    """外部保存（有界重试）。

    Windows 上 ``os.replace`` 偶发被瞬时占用拒绝（``Config.save`` 内部只 warning
    一次级失败；同族测试 ``test_config_watcher_reloads_and_applies_external_change``
    同样见过），失败时文件未替换 → 重试是同一件事的第二次尝试，不是时间赌注。
    """
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if config.save():
            return
        time.sleep(0.05)
    raise AssertionError("外部保存重试 10s 仍失败（Config.save 返回 False）")


# ---------------------------------------------------------------- DSH 桥接读方门
def _dsh_monitor(shell):
    return shell._shared.agent_link.monitors["dsh"]


def test_default_config_keeps_dsh_monitor_stopped(tmp_path, monkeypatch):
    """默认配置（agent_link 四 agent 全关）：读方不启，零端口探测。"""
    connects: list[int] = []
    monkeypatch.setattr(harness_launcher, "is_running",
                        lambda port: connects.append(port) or False)
    shell = _start_shell(tmp_path, monkeypatch)
    monitor = _dsh_monitor(shell)
    assert monitor._running is False, "默认配置下 DSH 读方不得启动"
    assert connects == [], "读方未启动就不得发起 loopback 端口探测"
    _pump(0.2)
    assert connects == [], "监视器未启动，后续也不得自启探测"


def test_dsh_link_enabled_starts_monitor(tmp_path, monkeypatch):
    """DSH 联动开启：读方照常跑（功能不变），worker 线程存活。"""
    monkeypatch.setattr(harness_launcher, "is_running", lambda port: False)
    shell = _start_shell(tmp_path, monkeypatch, dsh=True)
    monitor = _dsh_monitor(shell)
    assert monitor._running is True
    assert monitor._worker is not None and monitor._worker.is_alive()


def test_malformed_agent_link_config_keeps_monitor_stopped(tmp_path, monkeypatch):
    """脏配置（agent_link 不是 dict）：门判假、不抛，读方保持不跑。"""
    shell = _start_shell(tmp_path, monkeypatch)
    shell.config.data["agent_link"] = "broken"
    assert shell._dsh_tracker_wanted() is False
    shell._shared.agent_link.apply_config()
    assert _dsh_monitor(shell)._running is False


def test_gated_monitor_still_drives_offline_dismiss(tmp_path, monkeypatch):
    """门开时行为与现在一致：收敛器 offline 仍收口常驻审批/问题气泡。"""
    monkeypatch.setattr(harness_launcher, "is_running", lambda port: False)
    shell = _start_shell(tmp_path, monkeypatch, dsh=True)
    manager = shell._shared.agent_link
    dismissed: list[bool] = []
    monkeypatch.setattr(manager, "dismiss_all_interactions",
                        lambda: dismissed.append(True))
    _dsh_monitor(shell).dsh_state_changed.emit("thinking", "offline", "")
    app.processEvents()
    assert dismissed, "DSH 离线必须照常收口常驻气泡"


def test_disabling_dsh_link_stops_monitor_on_apply_config(tmp_path, monkeypatch):
    """关掉 DSH 联动 → apply_config（设置保存链的终点）同步停读方。"""
    monkeypatch.setattr(harness_launcher, "is_running", lambda port: False)
    shell = _start_shell(tmp_path, monkeypatch, dsh=True)
    monitor = _dsh_monitor(shell)
    assert monitor._running is True

    agent_cfg = dict(shell.config.get("agent_link") or {})
    agent_cfg["dsh"] = False
    shell.config.set("agent_link", agent_cfg)
    shell._shared.agent_link.apply_config()

    assert monitor._running is False, "关掉 DSH 联动后读方必须停"
    assert monitor._worker is None or not monitor._worker.is_alive()


def test_enabling_dsh_link_starts_monitor_on_apply_config(tmp_path, monkeypatch):
    """反向：运行期打开 DSH 联动 → apply_config 立即拉起读方。"""
    monkeypatch.setattr(harness_launcher, "is_running", lambda port: False)
    shell = _start_shell(tmp_path, monkeypatch)
    monitor = _dsh_monitor(shell)
    assert monitor._running is False

    agent_cfg = dict(shell.config.get("agent_link") or {})
    agent_cfg["dsh"] = True
    shell.config.set("agent_link", agent_cfg)
    shell._shared.agent_link.apply_config()

    assert monitor._running is True
    assert monitor._worker is not None and monitor._worker.is_alive()


# ---------------------------------------------------------------- 共享全屏 watcher
def test_overlay_topology_skips_shared_fullscreen_watcher(tmp_path, monkeypatch):
    """overlay 拓扑：进程级共享全屏 watcher 不启线程（壳自持探测）。"""
    monkeypatch.setattr(overlay_shell_mod, "OverlayShell", _StubOverlayShell)
    shell = _start_shell(tmp_path, monkeypatch, topology="overlay")
    assert shell._overlay_shell is not None, "用例前置：overlay 壳已接管"
    fs = shell._shared.fs
    assert fs._thread is None, "overlay 拓扑下共享全屏 watcher 不得起线程"


def test_legacy_topology_still_starts_shared_fullscreen_watcher(tmp_path, monkeypatch):
    """legacy 拓扑逐位不变：有窗需要时照常起共享探测线程。"""
    shell = _start_shell(tmp_path, monkeypatch, topology="legacy",
                         win=_StubWin())
    fs = shell._shared.fs
    assert fs._thread is not None and fs._thread.is_alive()
    assert fs._any_wants() is True, "legacy 窗 _watch_required 为真时必须真探测"
    fs.stop()
    fs._thread.join(timeout=5.0)


# ---------------------------------------------------------------- 一次保存一次应用
def test_one_settings_save_applies_external_change_exactly_once(tmp_path, monkeypatch):
    """一次外部设置保存 → 恰好一次 _apply_external_config_change。"""
    shell = _start_shell(tmp_path, monkeypatch, win=_StubWin())
    applies: list[int] = []
    shell._apply_external_config_change = lambda: applies.append(1)
    external = Config(base=tmp_path)
    external.set("pnpm_bin", "C:/tools/pnpm.cmd")
    _save_external(external)

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and not applies:
        app.processEvents()
        time.sleep(0.02)
    _pump(0.8)  # 去抖窗口（300ms）之后的余量：不得出现第二次
    assert len(applies) == 1, f"一次保存触发了 {len(applies)} 次应用链"
    assert shell.config.get("pnpm_bin") == "C:/tools/pnpm.cmd"
