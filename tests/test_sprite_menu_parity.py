# -*- coding: utf-8 -*-
"""overlay 右键菜单 parity：模板感知 + legacy 清单一项不缺（机器比对）。

比对基准是**真实 PetWindow**：构造一个 PetWindow，按 ``app.py::_wire_window``
的原样接线（聊天/余额/看屏/待办/报时/节日/生小肥鱼…）注入回调，再用**同一个
建造器**（``build_legacy_menu`` / ``build_modern_menu``）在同一份 Config、同一
平台上建菜单；overlay 侧用 ``build_sprite_full_menu`` 按 ``context_menu_template``
建。断言 overlay 树**逐项包含**基准树（同一父路径、兄弟顺序保持），且多出来的
条目只允许 overlay 特有项。

基准用真 PetWindow 而不是替身，正是为了防"两边都少同一项"的自证：基准里
出现什么，由 legacy 建造器 + 真实窗口面决定；facade 缺任何一面都会在这里红。

覆盖：
1. legacy 模板 ≡ build_legacy_menu(PetWindow)（条件显示项对齐：聊天门/win32 门）；
2. modern 模板 ≡ build_modern_menu(PetWindow)（注册表 + 用户编排 + 图标分组）；
3. 显式清单：用户点名的缺失条目（AI 对话/黄金回旋/显示本轮消费/音乐子菜单/
   边缘探头/大小/DeepSeek Harness/打开网页版 DeepSeek/主动识屏/Agent 联动/
   切换菜单模板）逐项在树里；
4. 无聊天变体：聊天门条目在两侧一起消失；
5. 音乐服务不可达 → 整组隐藏；
6. 点击路由：每项落到与 legacy 窗侧同一服务方法（等价性见 sprite_menu_facade
   的方法 docstring）；
7. close_on_trigger 命令在菜单关闭后必须派发（overlay 此前整类静默失效）。

纪律：offscreen；同步直调，不 sleep 赌时序。
"""
from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

import tests.test_context_menu_lifecycle as lc
import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_menu_facade as fac
from pet.catalog import CANVAS_W, SCALE_STEPS
from pet.config import Config
from pet.context_menu import load_menu_template
from pet.context_menus import build_legacy_menu, build_modern_menu
from pet.overlay_shell import OverlayShell
from pet.pet_sprite import PetSprite
from pet.sprite_menu_facade import SpriteMenuFacade, build_sprite_full_menu

app = QApplication.instance() or QApplication([])

# 素材池：两侧同源（分类逻辑不是本测试对象；内容一致才能比较动画分类子树）
POOLS = {
    "idles": ["idle1"],
    "turns": ["turn1"],
    "moves": ["walk"],
    "clicks": ["click1"],
    "acts": ["act1"],
}

# overlay 特有的额外条目（仅这三项允许出现在基准之外）
ALLOWED_EXTRAS = frozenset({"退出这只", "桌宠设置", "隐藏桌宠"})

# 用户点名的缺失条目（legacy 清单 → overlay 菜单必须逐项存在）
REQUIRED_LABELS = (
    "AI 对话",
    "黄金回旋",
    "显示本轮消费",
    "音乐",
    "边缘探头",
    "大小",
    "DeepSeek Harness",
    "打开网页版 DeepSeek",
    "主动识屏",
    "Agent 联动",
    "切换到新版菜单",
)
MUSIC_LABELS = (
    "让人家歇一会儿嘛（暂停 / 播放）",
    "给主人换一首（切歌）",
    "人家想再听刚才那首（上一首）",
    "人家今天不唱了（退出音乐模式）",
    "打开网易云音乐给主人放歌",
    "打开QQ音乐给主人放歌",
)
CHAT_GATED_LABELS = ("AI 对话", "AI 设置", "看看屏幕", "主动识屏", "DeepSeek 余额")
# Windows 专有项：主动识屏 v1 依赖 win32 前台窗口/截屏能力（vision.py /
# proactive.py 仅 win32 起监视器），菜单注册处 shared.add_proactive_menu 与
# registry proactive_screen 均按 sys.platform == "win32" 门控——posix 上
# 两侧建造器都不产出该项，期望模板须按平台分流（test_menu_layout.py 同先例）。
WIN32_ONLY_LABELS = ("主动识屏",)


# ---------------------------------------------------------------- 假件
class _StubAppShell:
    """AppShell 服务面替身：只记调用（真实路由目标见 facade 方法 docstring）。

    刻意**不**用 ``__getattr__`` 兜底：兜底会让任意属性探测都"可调用"，
    把宿主判定（``install_music_lyric`` 之类）伪装成存在。
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def show_balance(self, parent=None):
        self._record("show_balance", parent)

    def check_update(self, parent=None):
        self._record("check_update", parent)

    def open_todo_panel(self):
        self._record("open_todo_panel")

    def trigger_voice_chime_now(self, text=""):
        self._record("trigger_voice_chime_now", text)

    def toggle_voice_chime(self):
        self._record("toggle_voice_chime")

    def trigger_festival_now(self):
        self._record("trigger_festival_now")

    def toggle_festival_reminder(self):
        self._record("toggle_festival_reminder")

    def open_settings_process(self, instance=None):
        self._record("open_settings_process", instance)
        return True


class _StubInstance(cap.CapInstance):
    """PetInstance 面替身：聊天/设置/角色库 + 进程级 shell。"""

    enable_chat = True

    def __init__(self, config, *, chat=True) -> None:
        super().__init__(config)
        self.enable_chat = bool(chat)
        self.shell = _StubAppShell()
        self.calls: list[tuple] = []

    def open_chat(self):
        self.calls.append(("open_chat",))

    def open_chat_settings(self):
        self.calls.append(("open_chat_settings",))

    def sync_look_to_chat(self, user_text, reply):
        self.calls.append(("sync_look_to_chat", user_text, reply))

    def _create_library(self, character_id):
        return fac.RichLibrary()


class _RefLibrary(lc.FakeLibrary):
    """基准 PetWindow 的素材库（真 PetWindow 构造要求 names()）。"""

    def __init__(self) -> None:
        super().__init__()
        self._clips["act1"] = lc.FakeClip()
        self.character_id = ""


class _NoChatInstance(_StubInstance):
    def __init__(self, config) -> None:
        super().__init__(config, chat=False)


# ---------------------------------------------------------------- 装配
def _make_overlay(tmp_path, *, template, chat=True, values=None):
    config = Config(base=tmp_path)
    for key, value in (values or {}).items():
        config.set(key, value)
    config.set("context_menu_template", template)
    instance = _StubInstance(config, chat=chat)
    screen = cap.FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    shell = OverlayShell(
        app, instance, screen=screen,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    return shell, instance, config


def _reference_window(config, *, chat=True):
    """真实 PetWindow + app.py 同款接线（``_wire_window`` 的逐点对照）。"""
    win = lc.PetWindow(_RefLibrary(), config)
    for key, pool in POOLS.items():
        setattr(win, key, list(pool))
    win.on_open_chat = (lambda: None) if chat else None
    win.on_open_chat_settings = (lambda: None) if chat else None
    win.on_show_balance = (lambda parent=None: None) if chat else None
    win.on_look_screen = win.look_at_screen if chat else None
    win.on_open_modern_settings = lambda: None
    win.on_open_legacy_settings = None          # app.py:457 恒注入 None
    win.on_spawn_pet = lambda: None
    win.on_clear_spawned_pets = lambda: None
    win.on_check_update = lambda parent=None: None
    win.on_open_todo_panel = lambda: None
    win.on_voice_chime_now = lambda text="": None
    win.on_toggle_voice_chime = lambda: None
    win.on_festival_now = lambda: None
    win.on_toggle_festival = lambda: None
    win.on_switch_character = lambda character_id: None
    return win


def _reference_menu(win, config, template_id):
    from PySide6.QtWidgets import QMenu

    menu = QMenu()
    template = load_menu_template(template_id)
    if template_id == "legacy":
        build_legacy_menu(menu, win, template)
    else:
        build_modern_menu(menu, win, template)
    return menu


# ---------------------------------------------------------------- 树比对
def _children(container):
    items = []
    for action in container.actions():
        if action.isSeparator():
            continue
        items.append((action.text(), action.menu()))
    return items


def _assert_reference_contained(overlay, reference, path=(), allowed=ALLOWED_EXTRAS):
    """基准树逐项包含在 overlay 树里（同父路径 + 兄弟顺序保持），额外项受限。"""
    ref_items = _children(reference)
    ov_items = _children(overlay)
    ov_texts = [text for text, _ in ov_items]
    cursor = 0
    for text, ref_sub in ref_items:
        found = None
        for index in range(cursor, len(ov_texts)):
            if ov_texts[index] == text:
                found = index
                break
        assert found is not None, (
            f"overlay 菜单缺项 {path + (text,)}；同级实际 = {ov_texts[cursor:]}")
        if ref_sub is not None:
            ov_sub = ov_items[found][1]
            assert ov_sub is not None, f"{path + (text,)} 在 overlay 侧不是子菜单"
            _assert_reference_contained(
                ov_sub, ref_sub, path + (text,), allowed)
        cursor = found + 1
    ref_texts = {text for text, _ in ref_items}
    extras = [text for text in ov_texts if text not in ref_texts]
    assert set(extras) <= set(allowed), f"{path} 出现未预期条目：{extras}"


def _find(container, label: str):
    for action in container.actions():
        if action.text() == label:
            return action
    raise AssertionError(
        f"菜单缺项 {label}；实际 = {[a.text() for a in container.actions()]}")


def _flatten(container, path=()):
    entries = []
    for action in container.actions():
        if action.isSeparator():
            continue
        entries.append(path + (action.text(),))
        if action.menu() is not None:
            entries.extend(_flatten(action.menu(), path + (action.text(),)))
    return entries


def _all_labels(container):
    return {path[-1] for path in _flatten(container)}


# ---------------------------------------------------------------- 1/2. 模板 parity
def test_legacy_template_tree_matches_reference_petwindow(tmp_path):
    shell, _instance, config = _make_overlay(tmp_path, template="legacy")
    win = _reference_window(config)
    try:
        reference = _reference_menu(win, config, "legacy")
        overlay = build_sprite_full_menu(shell)
        _assert_reference_contained(overlay, reference)
    finally:
        win.close()
        shell._delete_runtime_marker()


def test_modern_template_tree_matches_reference_petwindow(tmp_path):
    shell, _instance, config = _make_overlay(tmp_path, template="modern")
    win = _reference_window(config)
    try:
        reference = _reference_menu(win, config, "modern")
        overlay = build_sprite_full_menu(shell)
        _assert_reference_contained(overlay, reference)
        # 现代布局确实生效：分组子菜单 + 样式标记（不是被 legacy 布局冒充）
        assert "桌宠控制" in _all_labels(overlay)
        assert overlay.property("menuStyle") == "modern"
    finally:
        win.close()
        shell._delete_runtime_marker()


def test_legacy_template_is_flat_and_modern_is_grouped(tmp_path):
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    try:
        legacy = build_sprite_full_menu(shell)
        # 旧版：动画分类/窗口能力平铺在根层
        root = [a.text() for a in legacy.actions() if not a.isSeparator()]
        assert "回到右下角" in root and "播放速率" in root
        assert "桌宠控制" not in root
        shell._config.set("context_menu_template", "modern")
        modern = build_sprite_full_menu(shell)
        root = [a.text() for a in modern.actions() if not a.isSeparator()]
        assert "桌宠控制" in root and "工具与帮助" in root
        assert "回到右下角" not in root          # 收进分组子菜单
    finally:
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- 3. 显式清单
def test_legacy_template_missing_entries_all_present(tmp_path):
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    try:
        menu = build_sprite_full_menu(shell)
        labels = _all_labels(menu)
        expected = REQUIRED_LABELS
        if sys.platform != "win32":
            expected = tuple(
                label for label in REQUIRED_LABELS if label not in WIN32_ONLY_LABELS)
            for label in WIN32_ONLY_LABELS:
                assert label not in labels, f"posix 不应出现 Windows 专有项：{label}"
        for label in expected:
            assert label in labels, f"legacy 模板缺项：{label}"
        # overlay 侧保留的、legacy.py 没有的三个入口（删掉就是实机可见回退）
        for label in ("桌宠设置", "隐藏桌宠"):
            assert label in labels, f"legacy 模板缺项：{label}"
        music = _find(menu, "音乐").menu()
        assert music is not None
        music_labels = [a.text() for a in music.actions() if not a.isSeparator()]
        for label in MUSIC_LABELS:
            assert label in music_labels, f"音乐子菜单缺项：{label}"
    finally:
        shell._delete_runtime_marker()


def test_modern_template_exposes_same_capabilities(tmp_path):
    shell, _instance, _config = _make_overlay(tmp_path, template="modern")
    try:
        menu = build_sprite_full_menu(shell)
        labels = _all_labels(menu)
        for label in ("AI 对话", "播放动画", "切换角色", "播放速率", "大小", "音乐",
                      "拖动物理", "边缘探头", "黄金回旋", "显示本轮消费", "桌宠设置"):
            assert label in labels, f"modern 模板缺项：{label}"
        controls = _find(menu, "桌宠控制").menu()
        assert _find(controls, "生小肥鱼") is not None
        tools = _find(menu, "工具与帮助").menu()
        for label in ("DeepSeek Harness", "打开网页版 DeepSeek", "GitHub 项目页"):
            assert _find(tools, label) is not None
    finally:
        shell._delete_runtime_marker()


def test_harness_launcher_gets_widget_dialog_parent(tmp_path, monkeypatch):
    """harness 四个入口的模态父必须是 QWidget（facade 不能当 QMessageBox parent）。

    同时锁住宿主形气泡面：``launch_harness_gui`` 用 ``parent.show_bubble`` 反馈。
    """
    from PySide6.QtWidgets import QWidget

    import pet.context_menus.shared as shared_mod

    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    captured: list[tuple] = []
    bubbles: list[tuple] = []
    try:
        monkeypatch.setattr(
            shared_mod, "launch_harness_gui",
            lambda parent=None, action="start", target="auto": captured.append(
                (parent, action, target)))
        monkeypatch.setattr(
            shell, "show_bubble",
            lambda text, duration_ms=3200, **kw: bubbles.append((text, duration_ms)))
        facade = SpriteMenuFacade(shell)
        facade.show_bubble("宿主形气泡", 1234)
        assert bubbles == [("宿主形气泡", 1234)]

        menu = build_sprite_full_menu(shell)
        harness = _find(menu, "DeepSeek Harness").menu()
        for action in harness.actions():
            action.trigger()            # 菜单未弹出 → 回调立即执行
        assert [(action, target) for _, action, target in captured] == [
            ("start", "web"), ("start", "desktop"), ("restart", "auto"), ("stop", "auto"),
        ]
        assert all(isinstance(parent, QWidget) for parent, _, _ in captured)
        assert all(parent is shell.overlay for parent, _, _ in captured)
    finally:
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- 4. 聊天门
def test_chat_gated_entries_follow_chat_availability(tmp_path):
    shell, _instance, config = _make_overlay(tmp_path, template="legacy", chat=False)
    win = _reference_window(config, chat=False)
    try:
        reference = _reference_menu(win, config, "legacy")
        overlay = build_sprite_full_menu(shell)
        _assert_reference_contained(overlay, reference)
        labels = _all_labels(overlay)
        assert "AI 对话" not in labels and "AI 设置" not in labels
        assert "DeepSeek Harness" not in labels and "主动识屏" not in labels
        # 与基准逐点一致：基准也不含这些
        assert set(CHAT_GATED_LABELS).isdisjoint(_all_labels(reference))
    finally:
        win.close()
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- 5. 音乐服务门
def test_music_group_hidden_when_service_unavailable(tmp_path, monkeypatch):
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    try:
        assert "音乐" in _all_labels(build_sprite_full_menu(shell))
        monkeypatch.setattr(SpriteMenuFacade, "_music_host", lambda self: None)
        assert "音乐" not in _all_labels(build_sprite_full_menu(shell))
    finally:
        shell._delete_runtime_marker()


def test_music_service_host_is_the_overlay_shell(tmp_path):
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    try:
        facade = SpriteMenuFacade(shell)
        assert facade.music_service_available is True
        controller = facade.install_music_lyric()
        assert controller is shell._music_lyric
        assert shell.install_music_lyric() is controller      # 幂等
        assert facade._music_lyric is controller
    finally:
        shell.shutdown_music_lyric()
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- 6. 点击路由
def test_menu_routes_legacy_service_semantics(tmp_path, monkeypatch):
    """逐项点击路由：每项落到与 legacy 窗侧同一服务/同一配置键。"""
    shell, instance, config = _make_overlay(tmp_path, template="legacy")
    manager_calls: list[tuple] = []
    watcher_calls: list[str] = []
    spin_calls: list[str] = []
    reopened: list = []
    try:
        shell.agent_link_manager = type("_M", (), {
            "set_enabled": lambda self, key, on: (
                manager_calls.append((key, on)), True)[1]})()
        shell.proactive_watcher = type("_W", (), {
            "apply_config": lambda self: watcher_calls.append("apply")})()
        monkeypatch.setattr(shell, "trigger_golden_spin",
                            lambda sprite=None: spin_calls.append(sprite))
        monkeypatch.setattr(shell.overlay, "reopen_context_menu",
                            lambda menu: reopened.append(menu))

        menu = build_sprite_full_menu(shell)
        # AI 对话 / AI 设置 → PetInstance（无聊天变体整条不显示）
        _find(menu, "AI 对话").trigger()
        _find(menu, "AI 设置").trigger()
        assert ("open_chat",) in instance.calls
        assert ("open_chat_settings",) in instance.calls
        # 黄金回旋 → 壳的 sprite 版旋转（作用对象 = 被点 sprite；主宠菜单 = 主 sprite）
        _find(menu, "黄金回旋").trigger()
        assert spin_calls == [shell.sprite]
        # 边缘探头 → config 键（探头世界每 tick 热读）；勾选动作 = toggled
        probe = _find(menu, "边缘探头")
        probe.setChecked(True)
        assert config.get("edge_probe_enabled") is True
        # 显示本轮消费 → agent_cost_enabled（agent_link 结算时读）
        cost = _find(menu, "显示本轮消费")
        cost.setChecked(True)
        assert config.get("agent_cost_enabled") is True
        # 大小四档 → sprite scale setter + 主配置（主宠菜单：作用对象 = 主 sprite）
        size = _find(menu, "大小").menu()
        target = next(a for a in size.actions() if a.text().endswith("px"))
        target.trigger()
        px = int(target.text()[:-2])
        expected_scale = next(s for s in SCALE_STEPS
                              if int(round(CANVAS_W * s)) == px)
        assert abs(shell.sprite.scale - expected_scale) < 1e-9
        assert config.get("scale") == shell.sprite.scale
        # 主动识屏 → proactive_screen 配置 + 共享监视器 apply_config
        # （Windows 专有：posix 菜单按设计不含该项，路由无从点击）
        if sys.platform == "win32":
            proactive_menu = _find(menu, "主动识屏").menu()
            _find(proactive_menu, "开启主动识屏").setChecked(True)
            assert config.get("proactive_screen", {}).get("enabled") is True
            assert watcher_calls, "主动识屏开关必须让共享监视器重读配置"
        # Agent 联动 → 共享 manager.set_enabled
        link_menu = _find(menu, "Agent 联动").menu()
        _find(link_menu, "Claude Code").setChecked(True)
        assert manager_calls == [("claude", True)]
        # 切换到新版菜单 → 配置 + 原地重开
        switch = _find(menu, "切换到新版菜单")
        switch.trigger()
        assert config.get("context_menu_template") == "modern"
        assert reopened == [menu]
    finally:
        shell._delete_runtime_marker()


def test_menu_agent_link_rolls_back_when_manager_refuses(tmp_path):
    """set_enabled 返回 False（拒绝授权）→ 菜单勾选态回滚（legacy 同语义）。"""
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")

    class _Refusing:
        def set_enabled(self, key, on):
            return False

    try:
        shell.agent_link_manager = _Refusing()
        facade = SpriteMenuFacade(shell)
        action = QAction("Claude Code")
        action.setCheckable(True)
        action.setChecked(True)
        facade.toggle_agent_link("claude", True, action)
        assert action.isChecked() is False
    finally:
        shell._delete_runtime_marker()


def test_menu_exit_this_kept_for_multi_pet(tmp_path):
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    try:
        shell.spawn_pet()
        menu = build_sprite_full_menu(shell, shell._spawned[0])
        assert _find(menu, "退出这只") is not None
        labels = [a.text() for a in menu.actions()]
        assert labels.index("退出这只") < labels.index("退出")
    finally:
        shell.clear_spawned_pets()
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- 7. 菜单关闭后派发
def test_close_on_trigger_commands_dispatch_after_menu_exec(tmp_path):
    """close_on_trigger 命令必须派发（此前 overlay 整类静默失效）。"""
    shell, _instance, _config = _make_overlay(tmp_path, template="modern")
    calls: list[str] = []

    class _Menu:
        _deferred_callbacks = [lambda: calls.append("hidden")]

        def exec(self, *_args):
            return None

    try:
        shell.overlay._full_menu_builder = lambda target: _Menu()
        shell.overlay._dispatch_deferred_menu_callbacks(_Menu())
        assert calls == []                       # 0ms 定时器：菜单关闭后派发
        app.processEvents()
        assert calls == ["hidden"]
    finally:
        shell._delete_runtime_marker()


def test_open_full_menu_at_rebuilds_menu_at_position(tmp_path, monkeypatch):
    """模板切换后的原位重开：同一位置、同一被点 sprite 重新建菜单。"""
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    from PySide6.QtCore import QPoint

    seen: list = []
    shell.sprite.bind_clip("idle1")
    shell.sprite._rebuild_pixmap()
    anchor = shell.overlay.mapToGlobal(shell.sprite.rect().center())

    class _Menu:
        def exec(self, pos):
            seen.append(("exec", QPoint(pos)))

        def close(self):
            seen.append(("close", None))

        def pos(self):
            return QPoint(anchor)

    try:
        target_sprite = shell.sprite
        shell.overlay._full_menu_builder = (
            lambda target: seen.append(("build", target)) or _Menu())
        shell.overlay.reopen_context_menu(_Menu())
        assert ("close", None) in seen
        # 重开走 10ms 定时器：轮询状态 + 宽预算（不赌固定 sleep）
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            app.processEvents()
            if any(item[0] == "build" for item in seen):
                break
            time.sleep(0.005)
        builds = [item for item in seen if item[0] == "build"]
        assert builds and builds[0][1] is target_sprite
        assert any(item[0] == "exec" for item in seen)
    finally:
        shell._delete_runtime_marker()


def test_close_on_trigger_action_defers_then_dispatches(tmp_path, monkeypatch):
    """真实弹出菜单里点 close_on_trigger 条目：命令被挂起 → 关闭后派发。

    这条锁的是 overlay 此前整类静默失效的缺陷（defer_menu_callback 挂了却没人
    派发）；直接走 QMenu.popup() + action.trigger()，不 mock 挂起机制。
    """
    from PySide6.QtCore import QPoint

    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    hidden: list[bool] = []
    try:
        monkeypatch.setattr(shell, "set_pet_visible",
                            lambda visible: hidden.append(visible))
        menu = build_sprite_full_menu(shell)
        action = _find(menu, "隐藏桌宠")
        assert action.property("closeOnTrigger") is True
        menu.popup(QPoint(20, 20))
        app.processEvents()
        assert menu.isVisible(), "offscreen 下 popup 必须真的可见（否则测不到挂起）"
        action.trigger()
        assert hidden == [], "菜单可见时命令必须挂起（deferred），不能同步执行"
        shell.overlay._dispatch_deferred_menu_callbacks(menu)
        app.processEvents()
        assert hidden == [False]
        menu.close()
    finally:
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- 8. 菜单入口的服务等价物
def test_golden_spin_rotates_once_and_restores(tmp_path):
    """「黄金回旋」→ sprite 整帧旋转一圈（golden_spin 常量 + 缓动）。"""
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")
    try:
        sprite = shell.sprite
        shell.trigger_golden_spin()
        assert shell._golden_spin_timer is not None
        assert shell._golden_spin_timer.isActive()
        assert sprite.throw_rotation == 0.0
        # 中途：缓动后应落在 (0, -360) 之间（逆时针）
        shell._golden_spin_started = time.monotonic() - 0.2
        shell._advance_golden_spin()
        assert -360.0 < sprite.throw_rotation < 0.0
        # 超过单圈时长：停表 + 回正
        shell._golden_spin_started = time.monotonic() - 1.0
        shell._advance_golden_spin()
        assert not shell._golden_spin_timer.isActive()
        assert sprite.throw_rotation == 0.0
    finally:
        shell._delete_runtime_marker()


def test_golden_spin_skips_while_throw_egg_active(tmp_path):
    """探头/彩蛋在跑时不叠加旋转（PetWindow「探头激活时不叠加」同纪律）。"""
    shell, _instance, _config = _make_overlay(tmp_path, template="legacy")

    class _BusyEgg:
        active = True

    try:
        shell._throw_egg = _BusyEgg()
        shell.trigger_golden_spin()
        assert shell._golden_spin_timer is None or not shell._golden_spin_timer.isActive()
    finally:
        shell._delete_runtime_marker()


def test_look_screen_throttles_and_syncs_reply(tmp_path, monkeypatch):
    """「看看屏幕」：忙碌/冷却提示 + worker 结果回 GUI（sync_look_to_chat）。"""
    shell, instance, _config = _make_overlay(tmp_path, template="modern")
    started: list = []

    class _Thread:
        def __init__(self, *args, **kwargs):
            started.append(kwargs.get("target"))

        def start(self):
            pass

    try:
        monkeypatch.setattr("pet.overlay_shell.threading.Thread", _Thread)
        assert shell.on_look_synced is not None
        shell.show_bubble  # 确保气泡面存在（首次冒泡惰性建气泡）
        shell.look_at_screen()
        assert shell._look_busy is True
        assert started, "worker 线程必须被启动"
        # 忙碌期再点：提示而不重复起线程
        shell.look_at_screen()
        assert len(started) == 1
        # worker 回报：忙碌复位 + 同步进聊天（on_look_synced 路由）
        shell._on_look_done("我看到了浏览器", "[看看屏幕] 前台窗口：chrome", False)
        assert shell._look_busy is False
        assert ("sync_look_to_chat", "[看看屏幕] 前台窗口：chrome",
                "我看到了浏览器") in instance.calls
        # 冷却期：不重复起线程
        shell.look_at_screen()
        assert len(started) == 1
    finally:
        shell._delete_runtime_marker()


def test_music_lyric_host_degrades_without_config(tmp_path):
    """歌词宿主默认不装（配置关）→ 不起轮询线程；开启后可幂等装上。"""
    shell, _instance, config = _make_overlay(tmp_path, template="legacy")
    try:
        shell.sync_music_lyric()
        assert shell._music_lyric is None
        config.set("music_lyric_enabled", True)
        shell.sync_music_lyric()
        assert shell._music_lyric is not None
        shell.shutdown_music_lyric()
    finally:
        shell._delete_runtime_marker()
