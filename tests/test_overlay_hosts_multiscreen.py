# -*- coding: utf-8 -*-
"""多屏独立落位：一屏一个宿主（一张 overlay + 一份屏局部仿真控制器）。

契约（2026-10-15 用户口径）：每只宠可**独立**放到任意显示器；仍然只有一个进程、
一个 tick 时钟、一套共享服务；被占用的每块屏各有一张 overlay。sprite 坐标是屏
局部坐标（= 全局 - 屏原点），故行为/碰撞/物理/探头逐屏一份——两块屏上局部坐标
相同的两只宠在桌面几何上相距上千像素，混进同一个世界就会被判成接触。

本机通常只有一块屏，故这里用**假双屏**驱动真实的宿主创建、跨屏移交与拖拽链路；
真实跨缝手感（半只宠被缝裁掉的短暂瞬间、异 DPI 观感）留多显示器实机验收。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_menu_facade as fac
from pet.overlay_shell import OverlayShell
from pet.pet_sprite import PetSprite

app = QApplication.instance() or QApplication([])


class FakeScreen(QObject):
    """带名字的假屏：宿主按 ``name()`` 命中位置记忆，故必须实现它。"""

    geometryChanged = Signal(QRect)
    availableGeometryChanged = Signal(QRect)

    def __init__(self, geo, avail, *, dpr=1.0, refresh=60.0, name="A"):
        super().__init__()
        self._geo = QRect(*geo)
        self._avail = QRect(*avail)
        self._dpr = float(dpr)
        self._refresh = float(refresh)
        self._name = name

    def set_rects(self, geo, avail, *, dpr=None):
        self._geo = QRect(*geo)
        self._avail = QRect(*avail)
        if dpr is not None:
            self._dpr = float(dpr)

    def geometry(self):
        return QRect(self._geo)

    def availableGeometry(self):
        return QRect(self._avail)

    def devicePixelRatio(self):
        return self._dpr

    def refreshRate(self):
        return self._refresh

    def name(self):
        return self._name


def _two_screens():
    """左右并排的两块屏：A 原点 (0,0)，B 原点 (1920,0)。"""
    a = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040), name="A")
    b = FakeScreen((1920, 0, 1920, 1080), (1920, 0, 1920, 1040), name="B")
    return a, b


def _three_screens():
    """再并一块 C（原点 3840,0）：回收类用例需要"还有别的宿主"才走得下去。"""
    a, b = _two_screens()
    c = FakeScreen((3840, 0, 1920, 1080), (3840, 0, 1920, 1040), name="C")
    return a, b, c


def _global_of(host, sprite):
    """sprite 的全局左上角（宿主窗口原点 + 局部坐标）。"""
    return QPointF(host.overlay.geometry().topLeft()) + QPointF(sprite.pos)


def _install_screens(monkeypatch, *screens):
    """屏枚举喂假屏：跨屏路由（``QGuiApplication.screens``）与位置记忆都读它。

    只换**类级** Qt API：屏枚举在产品里走 ``QGuiApplication.screens()``。不去动
    ``QApplication`` 实例上的同名属性——那个实例是全会话共用的，monkeypatch 对
    PySide6 实例的还原只会把记录到的值（此时已是类级补丁）重新塞成实例属性，
    泄漏到下一条用例。
    """
    monkeypatch.setattr(QGuiApplication, "screens",
                        staticmethod(lambda: list(screens)))
    monkeypatch.setattr(QGuiApplication, "primaryScreen",
                        staticmethod(lambda: screens[0]))


def _make_shell(tmp_path, screen, values=None):
    # 本文件测的就是"允许跨屏"下的多屏合同：开关是全局键、重启级（进程内快照），
    # 不在这台"机器"上显式开启的话，壳体只会在启动那块屏建窗，全部多屏断言都
    # 无从成立（默认关 = 单显示器口径）。显式值优先，便于单条用例反向覆盖。
    values = {"allow_cross_screen": True, **(values or {})}
    config = cap.CapConfig(tmp_path, values)
    from pet import pet_profiles

    values_pet = {key: value for key, value in (values or {}).items()
                  if key in pet_profiles.PER_PET_KEYS}
    pet_profiles.write_profile_settings(tmp_path, 0, values_pet or {"scale": 0.5})
    shell = OverlayShell(
        app, cap.CapInstance(config), screen=screen,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    lib = fac.RichLibrary()
    shell.lib = lib
    shell.sprite.library = lib
    shell._create_main_library = fac.RichLibrary
    shell.overlay.click_feedback = None  # 点击音效与多屏语义无关，先摘掉
    return shell


def _hittable(sprite):
    """让 sprite 的命中图就位（``sprite_at`` 逐像素判据要能命中）。"""
    sprite.bind_clip("idle1")
    sprite._rebuild_pixmap()


def _cleanup(shell):
    shell.stop()
    shell.overlay.close()
    shell._delete_runtime_marker()


def _press(local, global_pos):
    return QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(local), QPointF(global_pos),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)


def _move(local, global_pos):
    return QMouseEvent(
        QEvent.Type.MouseMove, QPointF(local), QPointF(global_pos),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)


def _release(local, global_pos):
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(local), QPointF(global_pos),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier)


def _painted(overlay, canvas) -> bool:
    """在该 overlay 上真跑一次瞄准 UI 绘制，返回"是否画了内容"。

    画布由调用方持有：``QPainter`` 活过临时 ``QPixmap`` 会访问违例。
    """
    painter = QPainter(canvas)
    try:
        return bool(overlay._paint_slingshot(painter))
    finally:
        painter.end()


def _tick(shell, dt=1 / 60.0):
    """一个真 tick 的两段（推进段收尾才跑跨屏路由）。"""
    shell.driver.tick_sim(dt)
    shell.driver.advance_overlays(dt)


def _right_press(local, global_pos):
    return QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(local), QPointF(global_pos),
        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier)


def _drag_across(shell, sprite, *, steps=16, step_px=40):
    """把 sprite 从 A 拖到 B（真鼠标事件序列 + 每步一个 tick）。

    跨屏移交由"全部 overlay advance 之后"的钩子按**这一拍的实际身体位置**判，
    所以每一步都要走一个真 tick（仿真段 + 推进段）——这正是窗口在拖拽期间一直在
    跑的那个时钟。

    返回 (落点全局坐标, A 窗局部坐标)；光标从按下点起每步向右 ``step_px``，默认
    共 640px——落点深入 B，抓取偏移不会被左缘钳制掩盖。
    """
    overlay_a = shell.host_for_sprite(sprite).overlay
    origin_a = QPointF(overlay_a.geometry().topLeft())
    _hittable(sprite)
    hit = QPointF(sprite.rect().center())
    overlay_a.mousePressEvent(_press(hit, origin_a + hit))
    cursor = origin_a + hit
    for _ in range(steps):
        cursor = QPointF(cursor.x() + step_px, cursor.y())
        overlay_a.mouseMoveEvent(_move(cursor - origin_a, cursor))
        shell.driver.tick_sim(1 / 60.0)
        shell.driver.advance_overlays(1 / 60.0)
    return cursor, cursor - origin_a


# ---------------------------------------------------------------- 宿主（公开面）
def test_host_for_sprite_exposes_screen_overlay_and_bounds(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        host = shell.host_for_sprite(shell.sprite)
        assert host.screen is a
        assert host.overlay is shell.overlay
        assert host.bounds == shell._bounds == QRect(0, 0, 1920, 1040)
        # 单屏用户：整组只有这一块屏的宿主
        assert shell.hosts() == [host]
    finally:
        _cleanup(shell)


def test_move_sprite_to_screen_migrates_only_that_pet(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        main = shell.sprite
        _hittable(main)
        _hittable(child)
        main_pos = QPointF(main.pos)
        child_global = _global_of(shell.host_for_sprite(child), child)

        assert shell.move_sprite_to_screen(
            child, b, global_pos=QPointF(2100, 300)) is True

        host_b = shell.host_for_sprite(child)
        assert host_b.screen is b
        assert host_b.overlay is not shell.overlay
        assert child in host_b.overlay.sprites
        assert child not in shell.overlay.sprites
        assert child.home_screen is b
        # 另一只一分不动、仍在自己那块屏上
        assert main.pos == main_pos
        assert shell.host_for_sprite(main).screen is a
        # 给了 global_pos：落在该全局位置（局部坐标差了整整一屏）
        assert _global_of(host_b, child) == QPointF(2100, 300)
        assert child.pos.x() == pytest.approx(180, abs=1.0)
        # 没给 global_pos = 只换坐标系：保持全局位置，越出那块屏就按新屏边界钳入
        #（与拖拽落位同一口径：B 上的 2100 落到 A 只能贴 A 的右缘）
        assert shell.move_sprite_to_screen(child, a) is True
        host_a = shell.host_for_sprite(child)
        assert host_a.screen is a
        assert _global_of(host_a, child).x() == pytest.approx(
            a.availableGeometry().right() + 1 - child.rect().width(), abs=2.0)
        assert shell._screen is a
    finally:
        _cleanup(shell)


def test_equal_local_coordinates_on_two_screens_do_not_collide(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        shell.move_sprite_to_screen(child, b)
        main = shell.sprite
        host_a = shell.host_for_sprite(main)
        host_b = shell.host_for_sprite(child)
        assert host_a.collision is not host_b.collision, "碰撞世界逐屏一份"

        # 两只摆在各自屏的**同一个局部坐标**上（真机上相距 1920px）
        same = QPointF(400, 300)
        main.set_pos(QPointF(same))
        child.set_pos(QPointF(same))

        events = []
        host_a.collision.add_collision_listener(events.append)
        host_b.collision.add_collision_listener(events.append)
        shell.driver.tick_sim(1 / 60.0)

        assert events == [], "两块屏上的同局部坐标不是接触"
        assert main.pos == same and child.pos == same
        # 反例（改造前是同一个世界）：喂进**一个**世界就会判成接触并互相推开
        host_b.collision.tick([main, child], 1 / 60.0)
        assert main.pos != same or child.pos != same
    finally:
        _cleanup(shell)


# ---------------------------------------------------------------- 跨屏拖拽
def test_drag_across_screens_transfers_only_the_dragged_pet(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        main = shell.sprite
        _hittable(child)
        child.set_pos(QPointF(200, 700))
        # 子宠先放到 B：这样 A 只剩主宠，一次跨屏拖拽正好把 A 拖空。
        # 落点选在 B 的**右侧远处**（局部 (1480, 200)），刻意避开主宠被拖进来时
        # 走的那条通道（缝附近、局部 y≈859）：拖鱼撞鱼**本来就会把旁边的宠撞开**
        # （见 tests/test_drag_collision_velocity.py），那是另一条独立且正确的行为，
        # 不是"被移交带动"。实测（60 次 × 16 拍）：坐在通道上会被撞开 14–90px，
        # 坐在远处则一步不动（0.00px）；本用例要判的是后者。
        assert shell.move_sprite_to_screen(
            child, b, global_pos=QPointF(3400, 200)) is True
        host_child = shell.host_for_sprite(child)
        child_global = _global_of(host_child, child)
        overlay_a = shell.overlay
        geometry_a = overlay_a.geometry()

        cursor, _ = _drag_across(shell, main)

        host_b = shell.host_for_sprite(main)
        assert host_b.screen is b, "身体中心过缝即换宿主"
        assert host_b is host_child
        assert main in host_b.overlay.sprites
        assert main not in overlay_a.sprites
        assert main.home_screen is b
        # 拖拽期间源窗不拆：这次输入会话还握在它手里（拆了会话就再也收不了尾）
        assert overlay_a in shell.driver.overlays
        assert overlay_a._mouse_grab is main
        # 只迁这一只：子宠的屏归属与成员表一分不变；位置只允许它自己的正常走动
        # （逐拍 tick 里行为链的位移，约 1px/拍），不得被这次移交带动，也不得被
        # 带到别的屏的域里去
        child_moved = _global_of(host_child, child) - child_global
        assert (child_moved.x(), child_moved.y()) == pytest.approx((0.0, 0.0), abs=24.0), (
            f"子宠被这次移交带动了 {child_moved}")
        body_child = QRectF(child.body_rect()).translated(
            host_child.overlay.geometry().topLeft())
        assert QRect(1920, 0, 1920, 1040).contains(
            QRect(int(body_child.x()), int(body_child.y()),
                  child.body_rect().width(), child.body_rect().height())), (
            "子宠必须仍完整落在它自己那块屏的可用区里")
        # 挂接点没变：两张窗口各自钉在自己那块屏上（拖拽移动的是绘制，不是窗口）
        assert overlay_a.geometry() == geometry_a
        assert host_b.overlay.geometry() == b.geometry()

        overlay_a.mouseReleaseEvent(_release(cursor, cursor))

        # 松手落在光标处（B 局部坐标），且抓取偏移不变（宠没从光标下错位）
        expected_local = cursor - QPointF(host_b.overlay.geometry().topLeft())
        assert main.rect().center().x() == pytest.approx(
            expected_local.x(), abs=4.0)
        # 源屏空了 → 那张窗口收掉，家顺位搬到仍在用的那张（self.overlay 跟随）
        assert shell.hosts() == [host_b]
        assert shell.overlay is host_b.overlay
    finally:
        _cleanup(shell)


def test_cross_screen_drag_keeps_release_velocity_sane(tmp_path, monkeypatch):
    """换屏不改手感：松手初速按真实手势估（跨屏这一跳不得被当成甩动）。"""
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a, {"drag_physics": True})
    try:
        main = shell.sprite
        overlay_a = shell.overlay
        origin_a = QPointF(overlay_a.geometry().topLeft())
        _hittable(main)
        hit = QPointF(main.rect().center())
        overlay_a.mousePressEvent(_press(hit, origin_a + hit))
        trail_samples = []
        for step in range(1, 26):
            cursor = QPointF(1700 + 40 * step, 400)
            overlay_a.mouseMoveEvent(_move(cursor - origin_a, cursor))
            shell.driver.tick_sim(1 / 60.0)
            shell.driver.advance_overlays(1 / 60.0)
            trail_samples.append(step)
        host_b = shell.host_for_sprite(main)
        assert host_b.screen is b, "身体整块进入邻屏后应当移交"
        # 轨迹样本整体换帧：相邻样本差仍是每步 40px（没有被拼成跨屏的一跳）
        trail = main.drag_trail
        assert len(trail) >= 2
        deltas = [abs(trail[i + 1][1] - trail[i][1]) for i in range(len(trail) - 1)]
        # 首个差值含"按下点 → 第一帧光标"的固有位移，只看其后：每步都是 40px
        assert deltas[1:] == pytest.approx([40.0] * (len(deltas) - 1)),             f"轨迹样本帧内一致，实测 {deltas}"
        cursor = QPointF(1700 + 40 * 25, 400)
        overlay_a.mouseReleaseEvent(_release(cursor - origin_a, cursor))
        # 反例锚点：换帧不得把轨迹拼成一跳（否则 estimate_release_velocity 会
        # 把这一跳当成甩动；trail 已在断言段逐差核对）
        # 拖动物理开着：手没在收尾瞬间暴冲 → 松手不是"甩出去"的暴速
        speed = (main.velocity.x() ** 2 + main.velocity.y() ** 2) ** 0.5
        assert speed < 3000.0
    finally:
        _cleanup(shell)


def test_transfer_keeps_clip_and_driver_running(tmp_path, monkeypatch):
    """移交不是退出：clip 不释放、成员不注销、共享驱动器继续驱动两张窗。"""
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        _hittable(child)
        shell.move_sprite_to_screen(child, b)
        clip = child._clip
        assert clip is not None
        closed: list = []
        child.close = lambda *a, **k: closed.append(1)
        removed: list = []
        shell.host_for_sprite(child).overlay.add_sprite_removed_listener(
            lambda sprite: removed.append(sprite))

        shell.move_sprite_to_screen(child, a)

        assert closed == [] and removed == []
        assert child._clip is clip
        assert shell.overlay in shell.driver._overlays
        assert shell.host_for_sprite(child).overlay in shell.driver._overlays
    finally:
        _cleanup(shell)


def test_dpr_follows_the_target_screen(tmp_path, monkeypatch):
    a, b = _two_screens()
    b.set_rects((1920, 0, 1920, 1080), (1920, 0, 1920, 1040), dpr=2.0)
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        assert child.dpr == 1.0
        shell.move_sprite_to_screen(child, b)
        assert child.dpr == 2.0
    finally:
        _cleanup(shell)


def test_stop_of_one_window_does_not_stop_the_shared_driver(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        shell.move_sprite_to_screen(child, b)
        shell.start()  # 起表（进程级一个 QTimer）
        host_b = shell.host_for_sprite(child)
        assert shell.driver.timer.isActive() is True

        host_b.overlay.close()

        assert shell.driver.timer.isActive() is True, "关一张窗不停整组时钟"
        assert shell.overlay in shell.driver._overlays
    finally:
        _cleanup(shell)


# ---------------------------------------------------------------- 屏事件
def test_primary_screen_change_does_not_move_pets(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        shell.move_sprite_to_screen(child, b)
        main_pos, child_pos = QPointF(shell.sprite.pos), QPointF(child.pos)
        overlay_a, overlay_b = shell.overlay, shell.host_for_sprite(child).overlay

        shell.handle_primary_screen_changed(b)

        assert shell.overlay is overlay_a
        assert shell.host_for_sprite(child).overlay is overlay_b
        assert shell.sprite.pos == main_pos
        assert child.pos == child_pos
    finally:
        _cleanup(shell)


def test_unplugging_one_screen_moves_only_its_pets(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        shell.spawn_pet()
        first, second = shell._spawned
        shell.move_sprite_to_screen(second, b)
        main = shell.sprite
        main_pos = QPointF(main.pos)
        first_pos = QPointF(first.pos)

        shell.handle_screen_removed(b)

        assert shell.host_for_screen(b) is None, "拔掉的屏不留宿主/窗口"
        assert shell.host_for_sprite(second).screen is a
        assert second in shell.overlay.sprites
        # 别的屏上的宠一分不动
        assert main.pos == main_pos and first.pos == first_pos
    finally:
        _cleanup(shell)


def test_unplugging_the_main_screen_rebuilds_it_on_a_survivor(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        shell.move_sprite_to_screen(child, b)
        overlay_a = shell.overlay

        shell.handle_screen_removed(a)

        assert shell.overlay is not overlay_a
        assert shell._screen is b
        assert shell.sprite in shell.overlay.sprites
        assert shell.sprite.home_screen is b
    finally:
        _cleanup(shell)


# ---------------------------------------------------------------- 位置记忆（逐宠）
def test_profile_records_the_pets_own_screen(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        slot = shell._spawned_slots[child]
        shell.move_sprite_to_screen(child, b)
        child.set_pos(QPointF(600, 500))

        shell.save_spawned_positions()

        from pet import pet_profiles
        geometry = dict(pet_profiles.read_slot_snapshot(tmp_path, slot).profile.data)
        assert geometry["screen_name"] == "B"
        host_b = shell.host_for_sprite(child)
        body = child.body_rect()
        cx = body.x() + body.width() / 2.0
        assert geometry["rx"] == pytest.approx(
            (cx - host_b.bounds.left()) / host_b.bounds.width(), abs=0.01)
    finally:
        _cleanup(shell)


def test_restore_puts_each_pet_back_on_its_own_screen(tmp_path, monkeypatch):
    """重启复活：按各宠档案里的 ``screen_name`` 回到各自那块屏。"""
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    from pet import pet_profiles

    # 复活路径同样只在"允许跨屏"下按各宠记忆的屏分窗
    config = cap.CapConfig(tmp_path, {"allow_cross_screen": True})
    pet_profiles.write_profile_settings(tmp_path, 0, {"scale": 0.5})
    pet_profiles.write_profile_settings(tmp_path, 1, {"scale": 0.5})
    pet_profiles.save_active_set(tmp_path, [0, 1], on_broken="backup-overwrite")
    pet_profiles.write_profile_geometry(
        tmp_path, 1, {"rx": 0.25, "ry": 0.75, "screen_name": "B"})
    shell = OverlayShell(
        app, cap.CapInstance(config), screen=a,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    try:
        shell._create_main_library = fac.RichLibrary
        assert shell.sprite is not None
        child = shell._spawned[0]
        host_b = shell.host_for_sprite(child)
        assert host_b.screen is b
        assert host_b.overlay is not shell.overlay
        body = child.body_rect()
        cx = body.x() + body.width() / 2.0
        cy = body.y() + body.height() / 2.0
        assert cx == pytest.approx(
            host_b.bounds.left() + 0.25 * host_b.bounds.width(), abs=2.0)
        assert cy == pytest.approx(
            host_b.bounds.top() + 0.75 * host_b.bounds.height(), abs=2.0)
    finally:
        _cleanup(shell)


def test_main_pet_restored_to_its_saved_screen_re_sites_the_home_window(
        tmp_path, monkeypatch):
    """主宠记着副屏：主宿主（``self.overlay``）搬到那块屏，而不是把宠丢过去。"""
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    from pet import pet_profiles

    # 复活路径同样只在"允许跨屏"下按各宠记忆的屏分窗
    config = cap.CapConfig(tmp_path, {"allow_cross_screen": True})
    pet_profiles.write_profile_settings(tmp_path, 0, {"scale": 0.5})
    pet_profiles.write_profile_geometry(
        tmp_path, 0, {"rx": 0.5, "ry": 0.5, "screen_name": "B"})
    shell = OverlayShell(
        app, cap.CapInstance(config), screen=a,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    try:
        shell._create_main_library = fac.RichLibrary
        assert len(shell.hosts()) == 1, "主宠那块屏就是家的位置，不额外多一张窗"
        host = shell.host_for_sprite(shell.sprite)
        assert host.screen is b
        assert shell.overlay is host.overlay
        assert shell._screen is b
        assert shell._bounds == QRect(0, 0, 1920, 1040)
    finally:
        _cleanup(shell)


# ---------------------------------------------------------------- 逐屏外围
def test_bubble_anchor_uses_the_pets_own_screen_origin(tmp_path, monkeypatch):
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        shell.move_sprite_to_screen(child, b)
        child.set_pos(QPointF(300, 400))

        follower = shell._bubble_for(child)
        assert follower is not None
        body = child.body_rect()
        expected = QRect(QPointF(1920, 0).toPoint() + body.topLeft(), body.size())
        assert follower.anchor() == expected
        assert shell.bubble_anchor_rect_for(getattr(follower, "bubble", None)) == expected
    finally:
        _cleanup(shell)


def test_island_wall_binds_to_the_islands_own_screen_host(tmp_path, monkeypatch):
    """岛只有一座：它的墙只挂到岛所在那块屏的世界（不复制到别的屏）。"""
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        child = shell._spawned[0]
        shell.move_sprite_to_screen(child, b)
        host_b = shell.host_for_sprite(child)

        class _Island:
            def __init__(self, screen):
                self._screen = screen

            def _current_screen(self):
                return self._screen

        shell.attach_island(_Island(b))

        assert shell.island_bridge is not None
        assert shell._island_host is host_b
        assert shell.island_bridge.core._world is host_b.collision  # noqa: SLF001
        shell.attach_island(_Island(a))
        assert shell._island_host is shell.host_for_sprite(shell.sprite)
    finally:
        shell.attach_island(None)
        _cleanup(shell)


def test_island_wall_waits_for_a_host_on_its_screen(tmp_path, monkeypatch):
    """岛在一块还没有宠的屏上：先不挂墙；那块屏有宠了再把墙挂过去。

    绝不允许"没有宿主就挂到主宿主"——局部坐标不同源，那等于在另一块屏上凭空
    多出一堵墙。
    """
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        host_a = shell.host_for_sprite(shell.sprite)

        class _Island:
            def __init__(self, screen):
                self._screen = screen

            def _current_screen(self):
                return self._screen

        island = _Island(b)
        shell.attach_island(island)

        assert getattr(shell, "island_bridge", None) is None
        assert shell._island_host is None
        assert not any(host.collision._static_members for host in shell.hosts())

        # 这块屏第一次有宠 → 宿主建出来 → 墙补挂到它自己的世界上
        main = shell.sprite
        assert shell.move_sprite_to_screen(main, b) is True
        host_b = shell.host_for_sprite(main)
        assert host_b.screen is b
        assert host_b is not host_a
        assert shell.island_bridge is not None
        assert shell._island_host is host_b
        assert shell.island_bridge.core._world is host_b.collision  # noqa: SLF001
    finally:
        shell.attach_island(None)
        _cleanup(shell)


# ---------------------------------------------------------------- 跨屏组合手势
def test_slingshot_gesture_after_crossing_uses_one_coordinate_system(
        tmp_path, monkeypatch):
    """跨屏拖到副屏后、**同一次 grab** 里点右键进弹弓：输入与预览同一坐标系。

    grab 留在按下窗（A），而 sprite 已经在 B：喂原始 ``event.position()`` 会把 A 的
    局部坐标与 B 上这只的坐标混起来（差整整一个屏原点）——拉拽预览按 B 的锚点画在
    A 的坐标系里，取消后恢复的抓取偏移也错一个屏原点（下一次移动这只被甩一整块屏）。
    这里钉三件事：瞄准会话可用、UI 归**持这只的那张窗**画、恢复拖拽后位移量不变。
    """
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        main = shell.sprite
        main.set_pos(QPointF(200.0, 700.0))
        overlay_a = shell.overlay
        origin_a = QPointF(overlay_a.geometry().topLeft())
        cursor, local_a = _drag_across(shell, main, steps=30, step_px=60)
        host_b = shell.host_for_sprite(main)
        assert host_b.screen is b, "前提：这只已经跨到副屏，而 grab 还在 A 窗"
        assert b.geometry().contains(cursor.toPoint()), "前提：光标确实落在副屏上"
        assert overlay_a._mouse_grab is main

        # 同一次 grab 里点右键 = 进瞄准（会话活在共用控制器上）
        overlay_a.mousePressEvent(_right_press(local_a, cursor))
        slingshot = shell._slingshot
        assert slingshot.aiming is True
        assert slingshot.sprite is main
        assert slingshot.anchor == QPointF(main.pos), "锚点就是这只在它自己坐标系里的位置"
        # 进去时的光标也必须是 B 的坐标系：与锚点同源，才不会有整屏偏移
        assert (slingshot.anchor_cursor - slingshot.anchor).manhattanLength() < (
            main.rect().width() + main.rect().height()), (
            "锚点光标与锚点同系（差一块屏的原点就会大得离谱）")

        # 光标在 A 窗里向左挪 60px：拉拽矢量 = 60px（方向与坐标系无关；
        # 60 在弹弓拉拽上限之内，不会被钳掉而掩盖算错坐标系的可能）
        pull_cursor = cursor - QPointF(60.0, 0.0)
        overlay_a.mouseMoveEvent(_move(pull_cursor - origin_a, pull_cursor))
        assert slingshot.pull.x() == pytest.approx(60.0, abs=1.0)
        assert slingshot.pull.y() == pytest.approx(0.0, abs=1.0)

        # 瞄准 UI 归持这只的那张窗画：A 窗不画（否则带/预览落在错的屏上）
        canvas = QPixmap(16, 16)   # 画布要活到 painter 结束（临时对象会崩）
        assert _painted(host_b.overlay, canvas) is True
        assert _painted(overlay_a, canvas) is False
        assert shell.host_for_sprite(main).overlay._slingshot_dirty.isEmpty() is False
        assert overlay_a._slingshot_dirty.isEmpty() is True

        # 再点右键 = 取消并就地恢复拖拽：抓取偏移按当前光标重建（不差一个屏原点）
        overlay_a.mousePressEvent(_right_press(pull_cursor - origin_a, pull_cursor))
        assert slingshot.aiming is False

        before = _global_of(shell.host_for_sprite(main), main)
        next_cursor = pull_cursor + QPointF(40.0, 0.0)
        overlay_a.mouseMoveEvent(_move(next_cursor - origin_a, next_cursor))
        after = _global_of(shell.host_for_sprite(main), main)
        assert (after - before).x() == pytest.approx(40.0, abs=2.0), (
            "恢复拖拽后跟着光标走：错一个屏原点会整块屏地甩出去")

        overlay_a.mouseReleaseEvent(_release(next_cursor - origin_a, next_cursor))
    finally:
        _cleanup(shell)


# ---------------------------------------------------------------- 跨屏与弹簧拖拽
def test_crossing_with_drag_physics_keeps_the_spring_lag(tmp_path, monkeypatch):
    """拖动物理开着时跨屏：逐拍连续、滞后保留，**不**瞬移到光标处。

    移交发生在"全部 overlay advance 之后"（弹簧的实际位移也在 advance 里），所以这
    里每一拍都走一个真 tick：跨屏那一拍只允许出现弹簧自己的位移（**不超过到目标的
    剩余滞后**），换宿主后滞后仍然存在（不是被抹平后从光标处重新开始）。
    跨屏域/原子换帧/轨迹一致这些更细的判据在 ``tests/test_overlay_seam_passage.py``。
    """
    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a, {"drag_physics": True})
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 600.0))
        overlay_a = shell.overlay
        origin_a = QPointF(overlay_a.geometry().topLeft())
        _hittable(main)
        hit = QPointF(main.rect().center())
        overlay_a.mousePressEvent(_press(hit, origin_a + hit))
        cursor = origin_a + hit
        for _ in range(5):
            cursor = QPointF(cursor.x() + 40.0, cursor.y())
            overlay_a.mouseMoveEvent(_move(cursor - origin_a, cursor))
        assert shell.host_for_sprite(main).screen is a
        assert (QPointF(main._drag_spring_target) - QPointF(main.pos)).x() > 100.0, (
            "前提：弹簧滞后已经攒出来（拖动确实落后于目标）")

        # 一大步跨过缝，然后逐拍推进：每一拍的位移都不许超过当时的剩余滞后
        cursor = QPointF(cursor.x() + 1400.0, cursor.y())
        overlay_a.mouseMoveEvent(_move(cursor - origin_a, cursor))
        lag_at_cross = None
        for tick in range(1, 120):
            prev = _global_of(shell.host_for_sprite(main), main)
            lag = abs(QPointF(main._drag_spring_target).x() - main.pos.x())
            _tick(shell)
            step = abs(_global_of(shell.host_for_sprite(main), main).x() - prev.x())
            assert step <= lag + 4.0, (
                f"第 {tick} 拍位移 {step} 明显超过剩余滞后 {lag}（那是瞬移不是弹簧）")
            if shell.host_for_sprite(main).screen is b:
                lag_at_cross = lag
                break
        assert shell.host_for_sprite(main).screen is b, "身体整块进副屏后应当移交"
        assert lag_at_cross is not None and lag_at_cross > 0.0, (
            "过缝那一刻滞后仍在（没有被抹平）")

        before_release = _global_of(shell.host_for_sprite(main), main)
        overlay_a.mouseReleaseEvent(_release(cursor - origin_a, cursor))
        after_release = _global_of(shell.host_for_sprite(main), main)
        assert (after_release - before_release).manhattanLength() < 2.0, (
            "松手不得把这只从当前位置挪到光标处")
        assert main.interaction_state in ("normal", "thrown")
    finally:
        _cleanup(shell)


# ---------------------------------------------------------------- runtime 标记监听
def test_main_pet_position_listener_follows_its_own_window(tmp_path, monkeypatch):
    """主宠移到副屏后：位置监听挂在**那些这只的窗**上，标记照旧随位置更新。

    老写法挂 ``self.overlay``（主宿主那张窗）：主宠跨屏后那张窗不再驱动它，标记
    永不更新；主宿主被回收时连注册一起丢掉。
    """
    from pet import slot_manager

    a, b = _two_screens()
    _install_screens(monkeypatch, a, b)
    shell = _make_shell(tmp_path, a)
    try:
        main = shell.sprite
        overlay_a = shell.overlay
        assert shell._on_main_sprite_moved in overlay_a._position_listeners.get(main, [])

        assert shell.move_sprite_to_screen(main, b) is True
        host_b = shell.host_for_sprite(main)
        assert shell._on_main_sprite_moved in host_b.overlay._position_listeners.get(
            main, []), "监听要挂在持有这只的那张窗上"
        assert shell._on_main_sprite_moved not in overlay_a._position_listeners.get(
            main, []), "旧窗上的影子注册要摘掉"

        def marker_x():
            path = slot_manager.runtime_marker_path(
                shell._config.dir, shell._config.instance_id, versioned=True)
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload["x"]

        main.set_pos(QPointF(600.0, 500.0))

        def drift_and_fanout(dx):
            """让这只真动起来并跑一次推进段：位置通知就在这一段扇出。

            先把位置写好再跑推进段是**不会**触发通知的（推进段比的是这一次
            advance 前后的矩形），所以这里给一段真速度让它在该次 advance 里位移。
            """
            shell._last_marker_write = 0.0
            main.set_velocity(QPointF(dx * 60.0, 0.0))
            shell.driver.advance_overlays(1 / 60.0)
            main.set_velocity(QPointF(0.0, 0.0))

        drift_and_fanout(200.0)
        first = marker_x()
        drift_and_fanout(400.0)
        second = marker_x()
        assert second - first == pytest.approx(400.0, abs=8.0), (
            "标记跟着这只在副屏上的位置走（挂错窗就永远不动）")

        # 主宿主那张窗被回收（A 上没宠）之后，标记照旧更新——监听不在它身上
        shell._reap_empty_hosts()
        assert shell.host_for_screen(a) is None, "前提：A 那块窗已经收掉"
        drift_and_fanout(200.0)
        third = marker_x()
        assert third - second == pytest.approx(200.0, abs=8.0), (
            "回收 A 窗不得带走这只的标记监听")
    finally:
        _cleanup(shell)


# ---------------------------------------------------------------- 拔屏时的在途会话
def test_screen_removed_without_any_fallback_screen_finishes_the_grab(
        tmp_path, monkeypatch):
    """拔屏且**没有**兜底屏可迁：在途会话仍要走完 grab 收尾协议。

    ``_fallback_screen`` 返回 None（这是唯一的活动屏）时 ``_migrate_to_screen``
    首行就返回——这条路径**没有**随后的 show() 收敛兜底（穿透修复报告 §三 记的
    正是它），grab 收尾的壳层通知因此是冲刷穿透待办的唯一时机：漏掉就
    ``_converge_pending`` 与 ``_auto_cursor_hidden`` 一起永久滞留（看得见点不到）。
    """
    a = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040), name="only")
    _install_screens(monkeypatch, a)            # 只有这一块屏：拔了就没兜底
    shell = _make_shell(tmp_path, a, {"mouse_through": False})
    try:
        overlay = shell.overlay
        released: list = []
        shell.sprite.on_release = released.append
        shell._on_cursor_visibility_changed("HIDDEN")     # 自动穿透（生产置位路径）
        assert overlay.mouse_through is True
        overlay._mouse_grab = shell.sprite
        overlay._press_click_only = True
        shell._converge_auto_cursor_hidden()              # 收敛撞上 grab → 记待办
        assert shell._converge_pending is True

        shell.handle_screen_removed(a)

        assert shell.overlay is overlay                   # 前提：没兜底屏 → 没迁移
        assert released == [QPointF(shell.sprite.pos)]    # 会话只松一次手
        assert overlay._mouse_grab is None
        assert overlay._press_click_only is False
        assert shell._converge_pending is False           # 待办被补做
        assert shell._auto_cursor_hidden is False
        assert overlay.mouse_through is False
    finally:
        _cleanup(shell)


def test_screen_removed_finishes_only_that_windows_session(tmp_path, monkeypatch):
    """拔屏只收那块屏窗口的会话，别的窗口的在途 grab 一个字段都不动。

    构造的是跨屏拖拽进行中的真实形态：输入会话留在 A 窗（按下窗）而被抓的宠身体
    已经在 B 上——A 窗的 sprite 表已空、``_mouse_grab`` 还握着它。此刻拔掉 A 屏：
    A 的会话按协议收尾（收尾通知里就顺手回收了这块空宿主一次），拔屏处置不得再
    回收第二次；C 窗上另一只在途会话全程不许被打断。
    """
    a, b, c = _three_screens()
    _install_screens(monkeypatch, a, b, c)
    shell = _make_shell(tmp_path, a)
    try:
        shell.spawn_pet()
        shell.spawn_pet()
        first, second = shell._spawned
        _hittable(first)
        _hittable(second)
        shell.move_sprite_to_screen(first, b)
        shell.move_sprite_to_screen(second, c)
        main = shell.sprite
        host_a = shell.host_for_sprite(main)
        overlay_a = shell.overlay
        _drag_across(shell, main)                 # A 窗按住 → 身体过缝 → 归 B
        host_b = shell.host_for_sprite(main)
        assert host_b.screen is b
        assert overlay_a.sprites == [], "前提：A 窗的 sprite 表已空（会话还握着）"
        assert overlay_a._mouse_grab is main
        released: list = []
        main.on_release = released.append

        # C 窗上另一只在途会话（合成形态：同一时刻生产上只能有一只按着）
        host_c = shell.host_for_sprite(second)
        overlay_c = host_c.overlay
        overlay_c._mouse_grab = second
        overlay_c._press_global = QPointF(7, 9).toPoint()
        other_releases: list = []
        second.on_release = other_releases.append

        shell.handle_screen_removed(a)

        assert released == [QPointF(main.pos)]    # A 的会话收尾一次（不重复 release）
        assert overlay_a._mouse_grab is None
        assert overlay_a._press_click_only is False
        assert overlay_a._drag_committed is False
        assert overlay_a._press_global is None
        assert host_a not in shell.hosts(), "A 的空宿主只回收一次（不重复回收）"
        assert shell.host_for_screen(a) is None
        assert shell.hosts() == [host_b, host_c]
        # 别的窗口的会话不被打断
        assert overlay_c._mouse_grab is second
        assert overlay_c._press_global == QPointF(7, 9).toPoint()
        assert other_releases == []
        assert shell.host_for_sprite(first).screen is b
        assert shell.host_for_sprite(second).screen is c
    finally:
        _cleanup(shell)
