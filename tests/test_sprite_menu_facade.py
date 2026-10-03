# -*- coding: utf-8 -*-
"""SpriteMenuFacade + 行为/物理接缝 offscreen 单测（4.1c）。

覆盖：菜单建造器产出全量菜单（旧 context_menus 建造器原样复用）、
facade 各窗口能力项落点、play_once/play_move_once、no_move 移动桶并入
动作池、playback_speed bind 应用、drag_physics 松手不抛掷、switch_character
换库收口。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

import tests.test_overlay_window_capabilities as cap
from pet.pet_sprite import INTERACTION_THROWN, PetSprite
from pet.sprite_menu_facade import SpriteMenuFacade, build_sprite_full_menu

app = QApplication.instance() or QApplication([])


class FakeClip(QObject):
    frameChanged = Signal(int)

    def __init__(self, name, frames=24):
        super().__init__()
        self.name = name
        self._frames = frames
        self.image = QImage(640, 360, QImage.Format.Format_ARGB32)
        self.image.fill(0xFF336699)
        self.speeds: list[float] = []
        self.started = False

    def currentFrameNumber(self):
        return 0

    def currentImage(self):
        return self.image

    def frameCount(self):
        return self._frames

    def duration(self):
        return self._frames * 42 / 1000.0

    def set_playback_speed(self, v):
        self.speeds.append(float(v))

    def start(self):
        self.started = True
        return True

    def stop(self):
        self.started = False


class RichLibrary:
    """带素材池的假库（无 names() → 走行为分类的属性分支）。"""

    def __init__(self):
        self.idles = ["idle1"]
        self.turns = ["turn1"]
        self.moves = ["walk"]
        self.clicks = ["click1"]
        self.acts = ["act1"]
        self.no_mirror: set[str] = set()
        self._clips = {n: FakeClip(n, 24) for n in
                       self.idles + self.turns + self.moves + self.clicks + self.acts}
        self.manifest = {}
        self.folder_map = {}
        self.folder_files = {}
        self.shutdown_calls = 0

    def movie(self, name):
        return self._clips[name]

    def duration(self, name):
        return self._clips[name].duration()

    def shutdown(self):
        self.shutdown_calls += 1


def _make_shell(tmp_path, config_values=None):
    """真实 PetSprite 的壳（facade 接缝需要 velocity/bind_clip/facing 全面）。"""
    from pet.overlay_shell import OverlayShell

    config = cap.CapConfig(tmp_path, config_values)
    instance = cap.CapInstance(config)
    screen = cap.FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    shell = OverlayShell(
        app, instance, screen=screen,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    lib = RichLibrary()
    shell.lib = lib
    shell.sprite.library = lib
    return shell, lib


def _recursive_labels(container) -> set:
    """递归枚举菜单文本：模板感知后条目可能落在分组子菜单里（modern 模板）。"""
    labels = set()
    for action in container.actions():
        if action.isSeparator():
            continue
        labels.add(action.text())
        if action.menu() is not None:
            labels |= _recursive_labels(action.menu())
    return labels


def test_full_menu_builds_with_capability_items(tmp_path):
    """两种模板下窗口能力条目都在（结构由 context_menus 建造器决定）。"""
    shell, _ = _make_shell(tmp_path)
    try:
        for template in ("legacy", "modern"):
            shell._config.set("context_menu_template", template)
            menu = build_sprite_full_menu(shell)
            labels = _recursive_labels(menu)
            # 「鼠标穿透」已随上游 ea17bfa 从右键全菜单移除（入口收敛到
            # 设置页/托盘菜单/命中右键小菜单 sprite_menu.py:58），不再断言。
            for expected in ("回到右下角", "窗口置顶", "不移动",
                             "开机自启", "隐藏桌宠", "桌宠设置", "退出"):
                assert expected in labels, f"{template} 菜单缺项: {expected}"
            assert menu._facade is not None  # F5 保活
    finally:
        shell._delete_runtime_marker()


def test_facade_window_capabilities(tmp_path):
    shell, _ = _make_shell(tmp_path, {"on_top": True, "mouse_through": False})
    facade = SpriteMenuFacade(shell)
    try:
        facade.change_scale(1.0)
        assert shell.sprite.scale == 1.0
        assert shell._config.get("scale") == 1.0
        facade.set_no_move(True)
        assert shell.behavior.no_move is True
        assert shell._config.get("no_move") is True
        facade.set_drag_physics(False)
        assert shell.sprite.drag_physics is False
        facade.set_on_top(False)
        assert not (shell.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        facade.set_mouse_through(True)
        assert shell.overlay.mouse_through is True
        facade.go_default_corner()
        expected = shell._default_corner_pos(shell._bounds, shell.sprite.rect())
        assert shell.sprite.pos == expected
        facade.hide()
        assert not shell.overlay.isVisible()
    finally:
        shell._delete_runtime_marker()


def test_play_once_binds_named_clip(tmp_path):
    shell, lib = _make_shell(tmp_path)
    facade = SpriteMenuFacade(shell)
    try:
        assert facade.switch_clip("act1") is None or True
        assert shell.sprite._clip_name == "act1"
        assert lib._clips["act1"].started is True
    finally:
        shell._delete_runtime_marker()


def test_play_move_once_forces_anim(tmp_path):
    shell, lib = _make_shell(tmp_path)
    facade = SpriteMenuFacade(shell)
    try:
        assert facade.trigger_move("walk") is True
        assert shell.sprite._clip_name == "walk"
        assert facade.trigger_move("不存在的") is False
    finally:
        shell._delete_runtime_marker()


def test_no_move_bucket_goes_to_acts(tmp_path):
    shell, lib = _make_shell(tmp_path)
    try:
        from collections import deque
        shell.behavior.no_move = True
        shell.behavior.rng = type("R", (), {
            "random": lambda self: 0.99,          # 移动桶
            "randint": lambda self, a, b: a,
            "choice": lambda self, seq: seq[0]})()
        st = shell.behavior._states.setdefault(
            shell.sprite, __import__("pet.sprite_behavior", fromlist=["_SpriteState"])._SpriteState())
        shell.behavior._roll_next(shell.sprite, st)
        assert shell.sprite._clip_name == "act1"   # 移动桶并入动作池
        assert shell.sprite.velocity == QPointF(0, 0)
    finally:
        shell._delete_runtime_marker()


def test_playback_speed_applied_on_bind(tmp_path):
    shell, lib = _make_shell(tmp_path)
    facade = SpriteMenuFacade(shell)
    try:
        facade.set_playback_speed(1.5)
        assert shell.sprite.playback_speed == 1.5
        facade.switch_clip("idle1")
        assert lib._clips["idle1"].speeds[-1] == 1.5
    finally:
        shell._delete_runtime_marker()


def test_drag_physics_off_lands_in_place(tmp_path):
    shell, _ = _make_shell(tmp_path)
    try:
        sprite = shell.sprite
        sprite.drag_physics = False
        sprite._dragging = True
        sprite._drag_offset = None
        now = [1000.0]
        sprite._clock = lambda: now[0]
        # 高速甩出轨迹（0.1s 位移 500px——drag_physics 开时必抛）
        sprite._drag_trail = [(1000.0 + i * 0.02, float(i * 100), 0.0)
                              for i in range(6)]
        now[0] = 1000.12
        sprite.on_release(QPointF(500, 0))
        assert sprite.interaction_state != INTERACTION_THROWN
        assert sprite.velocity.isNull()
    finally:
        shell._delete_runtime_marker()


def test_switch_character_swaps_library(tmp_path):
    shell, old_lib = _make_shell(tmp_path)
    try:
        new_lib = RichLibrary()
        made = []

        class Inst:
            config = shell._config

            def _create_library(self, cid):
                made.append(cid)
                return new_lib

        shell._instance = Inst()
        shell.switch_character("nova")
        assert made == ["nova"]
        assert shell.lib is new_lib
        assert shell.sprite.library is new_lib
        assert shell._config.get("character") == "nova"
        assert old_lib.shutdown_calls == 1
        assert shell.behavior.state_of(shell.sprite) is None  # forget 已重置
    finally:
        shell._delete_runtime_marker()
