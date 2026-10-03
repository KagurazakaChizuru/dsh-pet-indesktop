# -*- coding: utf-8 -*-
"""overlay 拓扑下的 app 级宿主回退（批 B3）聚焦测试。

背景：overlay 拓扑不建 ``PetWindow``（``PetInstance.win`` / ``AppShell.win`` 恒
None），而一批 app 级服务仍只认 ``win``：完整聊天窗打不开、报时/节日/待办落到
系统通知、定时余额直接 return、省电开关保存后不生效、隐藏提示读不到托盘、设置页
已开时静默无反应。

装配口径：**真 AppShell + 真 PetInstance + 真 OverlayShell 最小构造**（屏/sprite
工厂替身，同 ``tests/test_overlay_*.py`` 的 ``_make_shell``）；只有素材库
（ffmpeg 子进程）、网络线程与凭据库是不可在单测里跑的边界，用替身。
``PetInstance`` 走真实实现（``open_chat`` / ``_sync_animation_prewarm`` /
``_notify_pet_hidden``），不 mock 产品对象。

纪律：offscreen；同步直调，不 sleep 赌时序。
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

import pet.app as app_mod
import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_menu_facade as fac
from pet.app import AppShell, PetInstance
from pet.config import Config
from pet.festival_service import FestivalReminderService
from pet.overlay_shell import OverlayShell, _SettingsIdentity
from pet.pet_sprite import PetSprite
from pet.todo_reminder import TodoReminderService
from pet.voice_chime_service import VoiceChimeService

app = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- 装配
class _HostLibrary(fac.RichLibrary):
    """素材库替身：媒体解码（ffmpeg 子进程）是单测跑不了的边界。

    只比 ``RichLibrary`` 多记 ``set_prewarm_enabled``（A4 的观测点）。
    """

    def __init__(self) -> None:
        super().__init__()
        self.prewarm_calls: list[tuple[bool, object]] = []

    def set_prewarm_enabled(self, enabled, *, visible=None) -> None:
        self.prewarm_calls.append((bool(enabled), visible))


class _HostInstance(PetInstance):
    """真 PetInstance（聊天/预热/隐藏提示全走产品实现），只换掉素材库这一边界。"""

    def __init__(self, shell, config) -> None:
        super().__init__(shell, config)
        self.libraries: list[_HostLibrary] = []

    def _create_library(self, character_id):
        lib = _HostLibrary()
        self.libraries.append(lib)
        return lib


def _make_overlay_app(tmp_path, *, chat_ui_style: str | None = None):
    """真 AppShell + 真 PetInstance + 真 OverlayShell（sprite 工厂真 PetSprite）。

    共享子系统注入与自言自语朗读接线逐条对齐 ``AppShell.start()`` 的 overlay 分支
    （不注入的话壳是"空转形态"，与实机运行形态不一致）。
    """
    config = Config(base=tmp_path)
    if chat_ui_style is not None:
        config.set("chat_ui_style", chat_ui_style)
    shell = AppShell(app, config)
    inst = _HostInstance(shell, config)
    shell.instance = inst
    shell._instances = [inst]
    overlay = OverlayShell(
        app, inst, screen=cap.FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040)),
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale),
        agent_link_manager=shell._shared.agent_link,
        proactive_watcher=shell._shared.proactive)
    overlay.on_self_talk_speak = shell.speak_self_talk
    shell._overlay_shell = overlay
    return shell, inst, overlay


def _teardown(overlay) -> None:
    overlay._teardown_settings_command_watch()
    overlay._delete_runtime_marker()
    if getattr(overlay, "tray", None) is not None:
        overlay.tray.hide()


# ---------------------------------------------------------------- A1 完整聊天窗
def test_full_chat_opens_with_overlay_host(tmp_path):
    """``OverlayShell.open_full_chat``（菜单/快速气泡「全文见聊天窗」入口）在
    overlay 拓扑下必须真开出聊天窗，且以壳为 pet 形锚点。"""
    shell, inst, overlay = _make_overlay_app(tmp_path)
    try:
        assert inst.win is None, "overlay 拓扑不建 PetWindow（前置不成立）"
        overlay.overlay.show()

        overlay.open_full_chat()

        assert inst.modern_chat_window is not None, "完整聊天窗在 overlay 下打不开"
        assert inst.chat_window is inst.modern_chat_window
        host = inst.modern_chat_window.pet_link.pet_window
        assert host is not None, "聊天窗必须拿到 pet 形宿主（否则定位/头像全丢）"
        assert host.visible_content_rect().isValid(), "宿主身体框无效（定位会退化）"
    finally:
        _teardown(overlay)


def test_classic_chat_dispatcher_opens_with_overlay_host(tmp_path):
    """``PetInstance.open_chat`` 的 classic 分支同样要能在 overlay 下开出。"""
    shell, inst, overlay = _make_overlay_app(tmp_path, chat_ui_style="classic")
    try:
        overlay.overlay.show()

        inst.open_chat()

        assert inst.legacy_chat_window is not None
        assert inst.chat_window is inst.legacy_chat_window
        assert inst.legacy_chat_window.pet_link.pet_window is not None
    finally:
        _teardown(overlay)


# ---------------------------------------------------------------- A2 提醒落气泡
def _bubble_text(overlay) -> str:
    bubble = overlay._speech_bubble
    assert bubble is not None, "壳上应该有真气泡控件"
    return str(bubble._raw_text)


def test_todo_reminder_bubbles_on_overlay_host(tmp_path):
    """待办提醒宿主 = 壳：气泡出现在桌宠头顶，而不是退回系统通知。"""
    shell, inst, overlay = _make_overlay_app(tmp_path)
    try:
        overlay.overlay.show()
        service = TodoReminderService(shell)
        service.apply_config()

        service._notify_fire({"title": "站会", "time": "10:00"})

        assert "站会" in _bubble_text(overlay)
        assert shell._toast_windows == [], "落了气泡就不该再弹系统通知"
    finally:
        _teardown(overlay)


def test_voice_chime_and_festival_bubble_on_overlay_host(tmp_path):
    """报时/节日提醒宿主 = 壳（此前 win 恒 None → 直接落系统通知）。"""
    shell, inst, overlay = _make_overlay_app(tmp_path)
    try:
        overlay.overlay.show()
        chime = VoiceChimeService(shell)
        chime.apply_config()
        festival = FestivalReminderService(shell)
        festival.apply_config()

        chime._bubble("现在是上午九点整。")
        assert "九点" in _bubble_text(overlay)

        festival._bubble("今天是春节。")
        assert "春节" in _bubble_text(overlay)
        assert shell._toast_windows == [], "落了气泡就不该再弹系统通知"
    finally:
        _teardown(overlay)


class _NoThread:
    """网络/线程边界替身：余额查询的 HTTP 线程不在单测里跑。"""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def start(self) -> None:
        pass


# ---------------------------------------------------------------- A3 定时余额
def test_show_balance_uses_overlay_host(tmp_path, monkeypatch):
    """``show_balance`` 的 ``parent or instance.win`` 在 overlay 恒 None → 回退壳。"""
    shell, inst, overlay = _make_overlay_app(tmp_path)
    try:
        overlay.overlay.show()
        monkeypatch.setattr(app_mod.threading, "Thread", _NoThread)
        monkeypatch.setattr(shell.config, "resolve_api_key", lambda provider: "")
        assert shell._balance_busy is False

        shell.show_balance()

        assert shell._balance_busy is True, "余额链路在 overlay 下被提前 return 掉了"
        app.processEvents()          # 派发 singleShot 的"让我看看余额…"气泡
        assert "余额" in _bubble_text(overlay)
        # 异步结果回填同样走壳（缓存/网络两条路径共用 _show_balance_payload）
        shell._balance_bridge.done.emit(True, {"text": "余额 12.34", "info": {"total": 12.34}})
        assert "12.34" in _bubble_text(overlay)
    finally:
        _teardown(overlay)


# ---------------------------------------------------------------- A4 预热开关
def test_prewarm_sync_reaches_overlay_libraries(tmp_path):
    """省电模式保存后 ``_sync_animation_prewarm`` 必须落到 sprite 壳的库上
    （主宠 + 已生子宠），此前 overlay 下 win=None 直接 return。"""
    shell, inst, overlay = _make_overlay_app(tmp_path)
    try:
        main_lib = overlay.lib
        assert isinstance(main_lib, _HostLibrary), "主库必须来自本用例的替身（前置不成立）"
        overlay.spawn_pet()
        assert overlay._spawned, "spawn_pet 未产出子宠（用例前置不成立）"
        child_lib = overlay._spawned_libs[overlay._spawned[0]]

        inst._sync_animation_prewarm()          # 省电关（默认）→ 预热开
        assert main_lib.prewarm_calls == [(True, False)]
        assert child_lib.prewarm_calls == [(True, False)]

        inst.config.set("idle_low_fps_enabled", True)
        inst.config.save()
        inst._sync_animation_prewarm()          # 保存后立即生效，不必等下次启动

        assert main_lib.prewarm_calls[-1][0] is False
        assert child_lib.prewarm_calls[-1][0] is False
    finally:
        _teardown(overlay)


# ---------------------------------------------------------------- A5 隐藏指路
def test_hidden_hint_uses_overlay_tray(tmp_path, monkeypatch):
    """隐藏桌宠后的「点托盘恢复」提示：overlay 下托盘挂在壳上。"""
    shell, inst, overlay = _make_overlay_app(tmp_path)
    try:
        assert overlay.tray is not None, "测试环境应能建出托盘对象"
        assert shell.tray is overlay.tray, "AppShell.tray 在 overlay 下必须看向壳的托盘"
        messages: list[tuple] = []
        monkeypatch.setattr(overlay.tray, "showMessage",
                            lambda *args, **kwargs: messages.append(args))

        inst._notify_pet_hidden()

        assert messages, "隐藏后必须给出恢复入口提示"
        assert "托盘" in messages[0][1]
    finally:
        _teardown(overlay)


# ---------------------------------------------------------------- A6 设置页占用
def test_settings_already_open_hints_user(tmp_path, monkeypatch):
    """设置页已开着时不许静默 return True：同一只 / 另一只都要有可见提示。"""
    shell, inst, overlay = _make_overlay_app(tmp_path)
    launched: list = []
    monkeypatch.setattr(
        shell, "_launch_settings_process",
        lambda instance=None, **kwargs: launched.append(instance) or True)
    lock = QLockFile(str(shell.config.dir / "settings.lock"))
    try:
        assert shell.open_settings_process(inst) is True     # 首次：真拉起
        assert launched == [inst]
        shell._settings_launch_at = time.monotonic() - 10.0  # 走出"刚拉起"窗口
        assert lock.tryLock(0), "模拟独立设置进程已建锁（前置不成立）"

        before = len(shell._toast_windows)
        assert shell.open_settings_process(inst) is True     # 同一只：不重复拉起 + 提示
        assert launched == [inst]
        same = shell._toast_windows[before:]
        assert same and "已经打开" in same[0]._message

        before = len(shell._toast_windows)
        assert shell.open_settings_process(_SettingsIdentity("slot-2")) is True
        assert launched == [inst]
        other = shell._toast_windows[before:]
        assert other and "先关闭" in other[0]._message
        assert other[0]._message != same[0]._message, "两只宠的提示必须区分"
    finally:
        lock.unlock()
        _teardown(overlay)


# ---------------------------------------------------------------- 回归护栏
def test_win_consumers_stay_safe_with_overlay_host(tmp_path):
    """A2 的消费者审计：``self.win`` 在 overlay 下改指壳后，另两个消费点仍安全。

    ``app.win`` 只有三处消费（三个提醒服务之外）：

    - ``_dsh_link_manager``：壳持有的是同一个共享 agent_link（DSH 离线收口照常）；
    - ``open_todo_panel``：壳是 QObject，不能当 QDialog 的 parent（必须回落 None）。
    """
    shell, inst, overlay = _make_overlay_app(tmp_path)
    try:
        assert shell.win is overlay
        assert shell._dsh_link_manager() is shell._shared.agent_link

        shell.open_todo_panel()

        assert shell.todo_panel is not None
    finally:
        if shell.todo_panel is not None:
            shell.todo_panel.close()
            shell.todo_panel = None
        _teardown(overlay)


def test_legacy_topology_hosts_unchanged(tmp_path):
    """无 overlay 壳时 ``win`` / ``tray`` 逐位不变（legacy 逃生门路径）。"""
    shell = AppShell(app, Config(base=tmp_path))
    sentinel = object()
    try:
        shell.instance.win = sentinel
        assert shell.win is sentinel
        marking = object()
        shell.tray = marking
        assert shell.tray is marking
    finally:
        shell.instance.win = None


# ---------------------------------------------------------------- O5 指令通道归属
def test_settings_command_belongs_to_overlay_host_not_app(tmp_path):
    """overlay 拓扑下「退出子肥鱼」指令由壳独占消费，AppShell 不得抢先摘走。

    两条 watcher 盯同一个配置目录，都调 ``consume_command``（**消费即删**）。
    AppShell 侧的 ``clear_spawned_pets`` / slot 身份在 overlay 下都没有目标
    （子宠是 sprite，不在 ``_instances`` 里），谁先跑谁把指令摘走 → 设置页
    「一键退出子肥鱼」静默失效。故 app 侧在 overlay 拓扑下必须让路。
    """
    from pet import overlay_settings_command as cmd

    shell, inst, overlay = _make_overlay_app(tmp_path)
    try:
        shell._install_config_watcher()          # app 侧 watcher（真装、真盯同一目录）
        overlay.spawn_pet()
        assert overlay._spawned, "用例前置：有子宠才谈得上退出"
        config_dir = overlay._config.dir
        # 两条 watcher 并存且职责不同：app 侧 = 主配置外部修改 → 应用链，
        # 壳侧 = 设置指令 + per-slot 签名。两者都保留（去重的是指令消费，不是 watcher）。
        assert shell._config_watcher is not None
        assert overlay._command_watcher is not None
        assert str(config_dir) in shell._config_watcher.directories()
        assert str(config_dir) in overlay._command_watcher.directories()
        assert cmd.write_command(config_dir, cmd.CMD_EXIT_SPAWNED_PETS)
        # app 侧 watcher 槽（QFileSystemWatcher.directoryChanged 的真实接线点）
        shell._on_config_dir_changed(str(config_dir))
        assert cmd.command_path(config_dir).exists(), \
            "AppShell 把指令摘走了：壳侧再也消费不到（overlay 下它没有目标可执行）"
        shell._poll_settings_process()          # 3s 轮询兜底同样不得摘走
        assert cmd.command_path(config_dir).exists(), "轮询兜底路径也摘走了指令"
        # 壳侧照常消费并真的退出那只子肥鱼
        overlay._on_settings_command_dir_changed(str(config_dir))
        assert overlay._spawned == []
    finally:
        shell._teardown_config_watcher()
        _teardown(overlay)
