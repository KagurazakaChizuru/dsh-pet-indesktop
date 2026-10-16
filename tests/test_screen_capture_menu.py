# -*- coding: utf-8 -*-
"""「截图」右键菜单接线：注册项、模板位置、单一入口与可用性（offscreen）。

交互模型在 2026-10-14 重做过：菜单只负责**开始框选**，框完松手由覆盖层动作条
决定做什么。所以这里钉死四件事：

1. **它真的在树上**：注册表有 ``screen_capture`` 这一项、默认模板把它排在
   「看看屏幕」之后（都是屏幕类入口），老用户布局（模板里没这个节点）也会被
   合并策略补上——不然"升级后入口不见了"；
2. **只有一个叶子**「框选识屏…」：不再有"提取文字/翻译/问答"三条（那三个选择
   挪到了动作条上，菜单不该预先替用户押注）；
3. **入口不押注引擎**：以前三条叶子各自判可用性、各写置灰原因，现在无论引擎在
   不在都是同一个可点的叶子（置灰与原因搬到了动作条的「翻译」按钮上）；
4. **点击路由到宿主**：打到 ``on_screen_capture``。宿主没有这个面（纯桌宠变体）
   ＝能力不可用，整组不出现；名字对不上就是"入口在、点了没反应"，而只比对菜单
   树的用例抓不到，所以另有一条直查两个真实宿主的用例。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from pet import menu_layout  # noqa: E402
from pet.context_menu import populate_context_menu  # noqa: E402
from pet.context_menus import registry as registry_mod  # noqa: E402
from pet.screen_capture import actions as actions_mod  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolate_os_touching_menus(monkeypatch):
    """默认菜单里另有开机自启/角色清单两处系统面：按 test_menu_layout 的既有口径
    打桩，免得测截图入口时先在别的入口上炸。"""
    from pet import catalog
    from pet.context_menus import shared as menu_shared

    monkeypatch.setattr(menu_shared.autostart_mod, "is_enabled", lambda: False)
    monkeypatch.setattr(catalog, "list_available_characters", lambda: ["shenshen"])


class _FakeConfig:
    def __init__(self) -> None:
        self.values = {
            "context_menu_layout": None,
            "context_menu_appearance": {"theme": "light"},
            "character": "shenshen",
            "agent_link": {},
        }

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self) -> None:
        return None


class _FakePet:
    """只提供截图入口的宿主替身（其余菜单项靠 ``__getattr__`` 兜底）。

    数值/清单属性照抄 ``tests/test_menu_layout.py`` 的 FakePet：默认菜单的其它
    建造器（播放速率 / 动画分类 / 大小 / 桌宠控制）会读它们，替身缺一个就会在
    别处先炸，测不到本片要验的东西。

    ``chat=False`` 模拟"没有聊天能力"的宿主——注意它现在**只影响聊天入口**：
    截图入口只有一个面，不再随聊天能力有无而增删叶子。
    """

    playback_speed = scale = 1.0
    drag_physics = no_move = mouse_through = False
    idles = ["待机"]
    turns = moves = clicks = acts = []

    def __init__(self, *, chat: bool = True, surfaces: bool = True) -> None:
        self.cfg = _FakeConfig()
        self.calls: list[str] = []
        if surfaces:
            self.on_screen_capture = lambda: self.calls.append("capture")
        self.on_open_chat = (lambda: None) if chat else None

    def icon_pixmap(self, size: int = 64):
        from PySide6.QtGui import QPixmap

        pixmap = QPixmap(size, size)
        pixmap.fill()
        return pixmap

    def __getattr__(self, name):
        # 宿主没接这套面：三级入口名字一个都不许被兜底成一个假回调。
        if name == "on_screen_capture" or name.startswith("on_screen_capture_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None


def _screen_capture_action(pet=None):
    """「截图」在菜单上是一个**直接动作**（不套子菜单——只有一个选项没必要，实机反馈）。"""
    menu = QMenu()
    populate_context_menu(menu, pet or _FakePet())
    action = next(
        (item for item in menu.actions() if item.text() == "截图提问"), None
    )
    assert action is not None, "截图入口没出现在右键菜单上"
    assert action.menu() is None, "单一选项不该再套一层子菜单"
    return action


def test_registry_registers_the_screen_capture_group():
    assert "screen_capture" in registry_mod.MENU_ACTIONS.ids
    assert registry_mod.ACTION_LABELS["screen_capture"] == "截图提问"
    assert registry_mod.ACTION_ICONS["screen_capture"] == "size"


def test_default_layout_puts_the_group_right_after_look_screen():
    layout = menu_layout.load_default_menu_layout("modern-default-v1")
    ids = [
        node.get("id") for node in layout["nodes"]
        if isinstance(node, dict) and node.get("type") == "action"
    ]
    assert "screen_capture" in ids
    assert ids.index("screen_capture") == ids.index("look_screen") + 1


def test_saved_user_layout_gets_the_new_entry_merged_in(tmp_path):
    """老用户布局（存盘时还没有截图）必须被合并策略补上，不许静默消失。"""
    old_layout = {
        "schema_version": 1,
        "layout_id": "user",
        "nodes": [
            {"type": "action", "id": "ojingjing", "visible": True},
            {"type": "action", "id": "look_screen", "visible": True},
            {"type": "action", "id": "modern_settings", "visible": True},
            {"type": "action", "id": "quit", "visible": True},
        ],
    }
    result = menu_layout.resolve_menu_layout(
        old_layout,
        registered_actions=registry_mod.MENU_ACTIONS.ids,
        available_actions=registry_mod.MENU_ACTIONS.ids,
    )
    ids = [node.get("id") for node in result.nodes]
    assert "screen_capture" in ids
    assert ids.index("screen_capture") == ids.index("look_screen") + 1


# ------------------------------------------------------------------ 单一入口


def test_the_single_leaf_starts_a_selection_and_routes_to_the_host():
    pet = _FakePet()
    leaf = _screen_capture_action(pet)

    assert leaf.text() == "截图提问"
    assert leaf.isEnabled() is True
    leaf.trigger()
    assert pet.calls == ["capture"]


def test_the_leaf_does_not_gate_on_the_engines(monkeypatch):
    """引擎在不在都是同一个可点的叶子：动作（与"能不能做"）在松手后才定。

    打桩是**刻意的**：菜单这一层不该再问引擎可用性。哪天有人把这条依赖加回来，
    叶子会重新置灰、这条就红——这正是本用例要拦住的回归。
    """
    monkeypatch.setattr(actions_mod, "ocr_engine_available", lambda: False)
    monkeypatch.setattr(actions_mod, "translation_engine_available", lambda: False)
    pet = _FakePet()
    leaf = _screen_capture_action(pet)

    assert leaf.isEnabled() is True
    # 可用态不再挂"为什么用不了"的说明：两条旧的置灰原因都不许出现在这里
    # （「翻译」现在真的接了；真值在 reasons.py，动作条上才用它）。
    from pet.screen_capture import reasons as reasons_mod

    assert "尚未接入" not in leaf.toolTip()
    assert reasons_mod.TRANSLATION_UNAVAILABLE_REASON not in leaf.toolTip()
    leaf.trigger()
    assert pet.calls == ["capture"]


def test_the_entry_survives_without_a_chat_capability():
    """没有聊天能力时入口照样在：能不能问答是运行时的事，不拿它删入口。

    （旧契约里「问答」叶子在无聊天能力时整条消失；单一入口之后"整组出不出现"
    只取决于宿主有没有 ``on_screen_capture`` 这一个面。问答通道不可用时如实
    报一句在结果浮层上——见 ``test_screen_capture_actions.py``。）
    """
    pet = _FakePet(chat=False)
    leaf = _screen_capture_action(pet)

    leaf.trigger()
    assert pet.calls == ["capture"]


def test_group_is_hidden_when_the_host_has_no_screen_capture_surface():
    """宿主没接这套回调（纯桌宠变体）= 能力不可用 → 整组不出现。"""
    menu = QMenu()
    populate_context_menu(menu, _FakePet(surfaces=False))
    assert "截图提问" not in [action.text() for action in menu.actions()]


def test_real_hosts_expose_the_single_entry():
    """入口在两个真实宿主上都接了线（只查菜单树会漏：两边同时缺也"自证"通过）。

    单窗拓扑 = ``PetWindow``；sprite 拓扑 = ``OverlayShell``（``SpriteMenuFacade``
    只是每次右键重建的转发面，真正的长期宿主是壳）。``on_screen_capture`` 缺了，
    菜单上那组就会因为"能力不可用"整组消失，而只比对菜单树的用例抓不到。

    **顺带钉旧名字必须死透**：三个老回调（``on_screen_capture_ocr`` / ``_translate``
    / ``_ask``）只要还留一个，宿主→动作的连接就还停在旧契约上（菜单照旧能用，
    静默地少调一层）。
    """
    from pet.overlay_shell import OverlayShell
    from pet.sprite_menu_facade import SpriteMenuFacade
    from pet.window import PetWindow

    retired = ("on_screen_capture_ocr", "on_screen_capture_translate", "on_screen_capture_ask")
    for host in (PetWindow, OverlayShell, SpriteMenuFacade):
        assert isinstance(getattr(host, "on_screen_capture", None), property), (
            f"{host.__name__}.on_screen_capture 没接线")
        for name in retired:
            assert not hasattr(host, name), f"{host.__name__}.{name} 是旧契约的残留"
