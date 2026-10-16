# -*- coding: utf-8 -*-
"""跨屏拖拽的缝上通道：临时合法域 + advance 后按实际位置移交 + 原子换帧。

旧实现的三处几何缺陷（用户/主代理定位，本文件逐条钉住）：

1. **按光标落点提前移交**：路由在事件时刻用"光标 − 抓取偏移"的目标落点判身体中心，
   而弹簧档（``drag_physics``）的实际位移发生在 ``sprite.advance`` 里——身体还没过缝
   就被换到另一块屏，随后被那块屏的可用区钳住（实测跨屏那一帧跳 +1169 px）。
2. **单矩形钳制域**：跨屏时这只正跨在两块屏的缝上，任何单矩形域都会在缝上把它钳住。
3. **移交顺序**：``set_bounds(新矩形)`` 会先用**旧局部坐标**补一次钳制，再 ``set_pos``
   减 delta 又被钳一次——两次钳制叠起来就是那一跳。

本文件的判据（三条都只看**全局坐标**，不掺局部坐标）：

- 无 tick 时光标大跳不得提前移交，弹簧档的实际位置也不得因它移动；
- 逐 tick 的全局轨迹必须与"同一块大屏上没有内缝"的参考轨迹一致（缝对轨迹不可见）；
- 移交那一拍是**原子全局恒等换帧**（``old_origin + pos == new_origin + pos``），
  弹簧目标 / 轨迹样本 / 速度一律不变；
- 合法域只按**真实相接**的屏展开：错位拼接的空洞不是合法位置，斜对角的屏不算相接；
- 开关关着时不得因为拖拽而多建窗。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QRect, QRectF
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_menu_facade as fac
import tests.test_overlay_hosts_multiscreen as hosts_mod
from pet.overlay_shell import OverlayShell
from pet.pet_sprite import PetSprite
from tests.test_overlay_hosts_multiscreen import (
    FakeScreen, _hittable, _move, _press, _release)

app = QApplication.instance() or QApplication([])

TICK_S = 1 / 60.0


def _shell(tmp_path, screen, values=None, *, switch=True):
    # hosts 的 _make_shell 会把 allow_cross_screen 默认成 True（那个文件整体测"允许
    # 跨屏"），这里要能显式关掉，故先放进 values 再传。
    values = {"allow_cross_screen": switch, **dict(values or {})}
    return hosts_mod._make_shell(tmp_path, screen, values)


def _install(monkeypatch, screens):
    """屏枚举喂假屏（只补**类级** Qt API，不碰实例属性——实例 patch 会泄漏）。"""
    monkeypatch.setattr(QGuiApplication, "screens", staticmethod(lambda: list(screens)))
    monkeypatch.setattr(QGuiApplication, "primaryScreen",
                        staticmethod(lambda: screens[0]))


def _tick(shell, dt=TICK_S):
    """一个真 tick 的两段：仿真段 + 推进段（推进段收尾才跑跨屏路由）。"""
    shell.driver.tick_sim(dt)
    shell.driver.advance_overlays(dt)


def _global(shell, sprite):
    host = shell.host_for_sprite(sprite)
    return QPointF(host.overlay.geometry().topLeft()) + QPointF(sprite.pos)


def _global_target(shell, sprite):
    """弹簧目标的**全局等价位置**（换帧后局部值必须变，全局值必须不变）。"""
    target = getattr(sprite, "_drag_spring_target", None)
    if target is None:
        return None
    host = shell.host_for_sprite(sprite)
    return QPointF(host.overlay.geometry().topLeft()) + QPointF(target)


def _global_trail(shell, sprite):
    """拖拽轨迹样本的**全局等价** (x, y) 列表（换帧后全局值必须不变）。"""
    host = shell.host_for_sprite(sprite)
    origin = QPointF(host.overlay.geometry().topLeft())
    return [(origin.x() + row[1], origin.y() + row[2]) for row in sprite.drag_trail]


def _two_screens(height=1080, avail_height=1040):
    a = FakeScreen((0, 0, 1920, height), (0, 0, 1920, avail_height), name="DISPLAY1")
    b = FakeScreen((1920, 0, 1920, height), (1920, 0, 1920, avail_height), name="DISPLAY2")
    return a, b


def _grab(shell, sprite, at=None):
    """在 sprite 当前宿主窗里按下（返回 (overlay, origin, cursor)）。"""
    overlay = shell.host_for_sprite(sprite).overlay
    origin = QPointF(overlay.geometry().topLeft())
    _hittable(sprite)
    hit = QPointF(sprite.rect().center()) if at is None else QPointF(at)
    overlay.mousePressEvent(_press(hit, origin + hit))
    return overlay, origin, origin + hit


# ---------------------------------------------------------------- 1. 无 tick 不提前移交
def test_cursor_jump_without_tick_neither_transfers_nor_moves_a_spring_pet(
        tmp_path, monkeypatch):
    """光标一步跨到另一块屏、但**一个 tick 都没跑**：不换宿主，弹簧档位置不动。

    弹簧档的实际位移只在 advance 里发生——没有 tick 就没有位移，路由当然也不该
    发生（旧实现正是在这一帧按光标落点提前换了宿主）。
    """
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a, {"drag_physics": True})
    try:
        main = shell.sprite
        main.set_pos(QPointF(300.0, 600.0))
        overlay, origin, cursor = _grab(shell, main)
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))   # 过阈值：真拖拽
        _tick(shell)                                             # 弹簧开始跟
        before_global = _global(shell, main)

        cursor = QPointF(origin.x() + 2600.0, cursor.y())        # 一步跨到副屏深处
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))

        assert shell.host_for_sprite(main).screen is a, (
            "没有 tick 就不许移交：弹簧档的实际位移还没发生")
        assert _global(shell, main) == before_global, (
            "弹簧档的实际位置只在 advance 里变；事件本身不得移动它")
        assert main._drag_spring_target is not None, "前提：弹簧目标已更新（这才是事件的作用）"

        # 弹簧要好几拍才把身体推进邻屏：每一拍的位移都不许超过"到目标的剩余距离"
        # （超过就是一次瞬移），换宿主那一拍同样是原子的
        spring_before = _global_target(shell, main)
        velocity_before = QPointF(main.velocity)
        moved_tick = None
        for tick in range(1, 120):
            prev_global = _global(shell, main)
            lag = abs(QPointF(main._drag_spring_target).x() - main.pos.x())
            _tick(shell)
            step = abs(_global(shell, main).x() - prev_global.x())
            assert step <= lag + 4.0, (
                f"第 {tick} 拍位移 {step} 明显超过剩余滞后 {lag}（瞬移，不是弹簧）")
            if shell.host_for_sprite(main).screen is b:
                moved_tick = tick
                break
        assert moved_tick is not None and moved_tick > 1, (
            "弹簧档必须等身体真的进了邻屏才移交（不是光标一过缝就换）")
        assert _global_target(shell, main) == spring_before, (
            "弹簧目标的**全局**位置不许被改写（换帧只换局部表示）")
        assert QPointF(main.velocity) == velocity_before, "速度不许被改写"
    finally:
        hosts_mod._cleanup(shell)


def test_seam_trajectory_matches_a_seamless_screen(tmp_path, monkeypatch):
    """逐 tick 全局轨迹 == 同一块大屏（没有内缝）上的参考轨迹。

    缝对轨迹必须是**不可见**的：同样的光标路径、同样的 tick 节奏，跨两块屏的宠与
    在一块 3840 宽屏上的宠每一拍都应落在同一个全局位置（1:1 档两块的可用区并集与
    那块大屏逐位相同，弹簧档的目标点也相同）。
    """
    samples_seam = []
    samples_ref = []

    def run(screens, out, tmp, physics):
        _install(monkeypatch, screens)
        shell = _shell(tmp, screens[0], {"drag_physics": physics})
        try:
            main = shell.sprite
            main.set_pos(QPointF(300.0, 600.0))
            overlay, origin, cursor = _grab(shell, main)
            overlay.mouseMoveEvent(_move(cursor - origin, cursor))
            _tick(shell)
            for step in range(90):
                cursor = QPointF(cursor.x() + 32.0, cursor.y())
                overlay.mouseMoveEvent(_move(cursor - origin, cursor))
                _tick(shell)
                out.append(round(_global(shell, main).x(), 3))
            overlay.mouseReleaseEvent(_release(cursor - origin, cursor))
            return shell
        finally:
            pass

    a, b = _two_screens()
    big = FakeScreen((0, 0, 3840, 1080), (0, 0, 3840, 1040), name="BIG")
    seam_shell = run([a, b], samples_seam, tmp_path / "seam", physics=False)
    ref_shell = run([big], samples_ref, tmp_path / "ref", physics=False)
    try:
        assert len(samples_seam) == len(samples_ref) == 90
        assert samples_seam == pytest.approx(samples_ref, abs=0.001), (
            "跨缝轨迹必须与无内缝参考逐拍一致（差一点点就是钳制/提前移交留下的位移）")
    finally:
        hosts_mod._cleanup(seam_shell)
        hosts_mod._cleanup(ref_shell)


def test_transfer_frame_is_a_global_identity_reframe(tmp_path, monkeypatch):
    """移交那一拍是原子换帧：全局位置、弹簧目标、轨迹样本逐位不变。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a, {"drag_physics": True})
    try:
        main = shell.sprite
        main.set_pos(QPointF(300.0, 600.0))
        overlay, origin, cursor = _grab(shell, main)
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)

        cursor = QPointF(origin.x() + 2400.0, cursor.y())
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))

        # 先把"路由"从 tick 里摘出来：advance 只走弹簧（不判移交），量到的位移
        # 就是弹簧那一拍的正常量；再单独调一次路由，量移交本身带来的位移。
        shell.driver.set_post_advance(None)
        try:
            for _ in range(200):
                shell.driver.advance_overlays(TICK_S)
                host = shell.host_for_sprite(main)
                body = QRectF(main.body_rect()).translated(
                    host.overlay.geometry().topLeft())
                if shell._screen_fully_containing(body) is b:
                    break
            else:
                pytest.fail("弹簧跑满 200 拍身体仍未整块进入副屏")

            before_global = _global(shell, main)
            spring_before = _global_target(shell, main)
            velocity_before = QPointF(main.velocity)
            trail_before = _global_trail(shell, main)

            assert shell.route_seam_after_advance() is None  # 顶层入口不返回值
            host = shell.host_for_sprite(main)
            assert host.screen is b, "身体整块进邻屏 → 移交"
            assert _global(shell, main) == before_global, (
                "原子换帧：移交本身一个像素都不许移动这只（全局位置逐位不变）")
            assert _global_target(shell, main) == spring_before, (
                "弹簧目标的全局位置不许被改写")
            assert QPointF(main.velocity) == velocity_before, "速度不许被改写"
            assert _global_trail(shell, main) == pytest.approx(trail_before, abs=1e-6), (
                "轨迹样本的全局位置不许被改写")
        finally:
            shell.driver.set_post_advance(
                lambda _dt: shell.route_seam_after_advance())
    finally:
        hosts_mod._cleanup(shell)


# ---------------------------------------------------------------- 4. 只有真相接的屏相连
def _drag_to(shell, sprite, target_global):
    overlay, origin, cursor = _grab(shell, sprite)
    overlay.mouseMoveEvent(_move(cursor - origin, cursor))
    _tick(shell)
    overlay.mouseMoveEvent(_move(target_global - origin, target_global))
    _tick(shell)
    return overlay, origin


def test_touching_group_requires_a_shared_edge(tmp_path, monkeypatch):
    """斜对角、只差一个像素都不算相接：那只宠不许被送到隔着空洞的屏上。"""
    a = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040), name="A")
    # 右下方错位一块屏：与 A 既不共享竖边也不共享横边（只有角点相接）
    diagonal = FakeScreen((1930, 1000, 1920, 1080), (1930, 1000, 1920, 1040), name="D")
    _install(monkeypatch, [a, diagonal])
    shell = _shell(tmp_path, a)
    try:
        assert [s.name() for s in shell._screen_touch_group(a)] == ["A"], (
            "角点相接不是相接（否则外接矩形里的空洞会变成通道）")

        main = shell.sprite
        main.set_pos(QPointF(300.0, 600.0))
        overlay, origin = _drag_to(shell, main, QPointF(2200.0, 600.0))
        assert shell.host_for_sprite(main).screen is a, "隔空洞的屏不算通道"
        assert len(shell.hosts()) == 1, "隔着空洞不许建窗"
        body = QRectF(main.body_rect()).translated(
            shell.host_for_sprite(main).overlay.geometry().topLeft())
        assert QRect(0, 0, 1920, 1040).contains(
            QRect(int(body.x()), int(body.y()),
                  main.body_rect().width(), main.body_rect().height())), (
            "没能过去的那只必须仍完整落在自己的可用区里")
    finally:
        hosts_mod._cleanup(shell)


def test_touching_group_follows_real_edges_on_all_four_sides(tmp_path, monkeypatch):
    """左右上下（含负坐标）的真相接都算通道：身体整块过去就换宿主。"""
    cases = [
        ("right", FakeScreen((1920, 0, 1920, 1080), (1920, 0, 1920, 1040), name="R")),
        ("left", FakeScreen((-1920, 0, 1920, 1080), (-1920, 0, 1920, 1040), name="L")),
        ("below", FakeScreen((0, 1080, 1920, 1080), (0, 1080, 1920, 1040), name="B")),
        ("above", FakeScreen((0, -1080, 1920, 1080), (0, -1080, 1920, 1040), name="T")),
    ]
    for name, neighbour in cases:
        a = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040), name="A")
        _install(monkeypatch, [a, neighbour])
        shell = _shell(tmp_path / name, a)
        try:
            group = shell._screen_touch_group(a)
            assert len(group) == 2, f"{name}: 真相接应当成组"
            main = shell.sprite
            main.set_pos(QPointF(600.0, 500.0))
            body = main.body_rect()
            target = {
                "right": QPointF(2600.0, 500.0),
                "left": QPointF(-1300.0, 500.0),
                "below": QPointF(600.0, 1600.0),
                "above": QPointF(600.0, -600.0),
            }[name]
            # 拖进邻屏深处（身体整块过去）：逐拍朝目标推进
            overlay, origin, cursor = _grab(shell, main)
            overlay.mouseMoveEvent(_move(cursor - origin, cursor))
            _tick(shell)
            start = QPointF(cursor)
            for step in range(1, 61):
                cursor = start + (target - start) * (step / 60.0)
                overlay.mouseMoveEvent(_move(cursor - origin, cursor))
                _tick(shell)
            host = shell.host_for_sprite(main)
            assert host.screen is neighbour, f"{name}: 身体整块进入邻屏后应当换宿主"
            body_global = QRectF(main.body_rect()).translated(
                shell.host_for_sprite(main).overlay.geometry().topLeft())
            assert QRect(neighbour.availableGeometry()).contains(
                QRect(int(body_global.x()), int(body_global.y()),
                      main.body_rect().width(), main.body_rect().height())), (
                f"{name}: 换了宿主后身体在邻屏可用区内")
            overlay.mouseReleaseEvent(_release(cursor - origin, cursor))
        finally:
            hosts_mod._cleanup(shell)


def test_switch_off_drag_opens_no_domain_and_no_window(tmp_path, monkeypatch):
    """开关关着：拖拽不开跨屏域、不建第二张窗（默认态与旧行为逐位相同）。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a, switch=False)
    try:
        main = shell.sprite
        main.set_pos(QPointF(300.0, 600.0))
        overlay, origin, cursor = _grab(shell, main)
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)
        cursor = QPointF(origin.x() + 2600.0, cursor.y())
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)

        assert getattr(main, "_clamp_rects", None) is None, "关着时不开跨屏域"
        assert len(shell.hosts()) == 1, "关着时不许因为拖拽多建窗"
        assert shell.host_for_sprite(main).screen is a
    finally:
        hosts_mod._cleanup(shell)


def test_domain_narrows_once_the_body_is_fully_inside_one_screen(tmp_path, monkeypatch):
    """身体整块落在某块屏可用区内 → 收窄回常规单屏钳制（过渡结束）。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a)
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 500.0))
        overlay, origin, cursor = _grab(shell, main)
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)
        cursor = QPointF(origin.x() + 1000.0, cursor.y())
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        assert getattr(main, "_clamp_rects", None) is not None, "拖拽中域是开的"
        _tick(shell)
        assert getattr(main, "_clamp_rects", None) is not None, (
            "拖拽没收尾 → 域一直开着（通道要开满整场拖拽）")
        cursor = QPointF(origin.x() + 2200.0, cursor.y())
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)
        host = shell.host_for_sprite(main)
        assert host.screen is b, "身体整块进副屏 → 移交"
        assert getattr(main, "_clamp_rects", None) is not None, (
            "还在拖拽 → 域保持开着（收域只在松手后、且身体已合法时）")
        overlay.mouseReleaseEvent(_release(cursor - origin, cursor))
        _tick(shell)
        assert getattr(main, "_clamp_rects", None) is None, (
            "松手后身体已整块在副屏内 → 域收窄（回到常规单屏钳制）")
        host = shell.host_for_sprite(main)
        assert host.screen is b
        assert host.bounds == shell._local_bounds(b), "收窄后用该屏可用区当钳制域"
    finally:
        hosts_mod._cleanup(shell)


# ---------------------------------------------------------------- 5. 松手 / 弹弓跨缝
def _drag_to_straddle(shell, sprite, *, extra=0.0):
    """拖到"身体正跨在缝上"的位置（左缘在 A、右缘在 B），返回 (overlay, origin, cursor)。

    ``extra`` = 在跨缝位置基础上再往右多拖的像素（0 = 正好卡在缝上）。
    """
    overlay, origin, cursor = _grab(shell, sprite)
    overlay.mouseMoveEvent(_move(cursor - origin, cursor))
    _tick(shell)
    body = sprite.body_rect()
    # 目标：身体左缘刚好落在缝左边半个身体宽的位置（身体横跨 1920）
    want_body_left = 1920.0 - body.width() / 2.0 + extra
    want_pos_x = want_body_left - (body.x() - sprite.rect().x())
    want_cursor_x = want_pos_x + sprite._drag_offset.x()
    cursor = QPointF(origin.x() + want_cursor_x, cursor.y())
    overlay.mouseMoveEvent(_move(cursor - origin, cursor))
    _tick(shell)
    return overlay, origin, cursor


def test_release_straddling_the_seam_neither_snaps_nor_closes_the_domain(
        tmp_path, monkeypatch):
    """松手时身体正跨在缝上：位置不许跳，域也不许当场收回（否则就是第二次 snap）。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a)
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 500.0))
        overlay, origin, cursor = _drag_to_straddle(shell, main, extra=-20.0)
        host = shell.host_for_sprite(main)
        body = QRectF(main.body_rect()).translated(host.overlay.geometry().topLeft())
        assert body.left() < 1920.0 < body.left() + body.width(), (
            "前提：身体正跨在缝上（两边各有一部分）")
        assert getattr(main, "_clamp_rects", None) is not None, "拖拽中域是开的"

        before = _global(shell, main)
        overlay.mouseReleaseEvent(_release(cursor - origin, cursor))
        assert _global(shell, main) == before, "松手本身不许移动这只"
        assert getattr(main, "_clamp_rects", None) is not None, (
            "身体还在缝上 → 域必须留着（当场收回就是把跨缝的身体钳进一块屏 = 第二次 snap）")

        # 松手后跑几拍：这只仍完整可见/合法（不落在屏间空洞里），位置连续
        prev = _global(shell, main)
        for _ in range(10):
            _tick(shell)
            host = shell.host_for_sprite(main)
            body = QRectF(main.body_rect()).translated(host.overlay.geometry().topLeft())
            covered = any(
                QRectF(s.availableGeometry()).intersects(body)
                for s in (a, b))
            assert covered, "身体必须仍落在有显示器的地方"
            step = abs(_global(shell, main).x() - prev.x())
            assert step <= 40.0, f"松手后每拍位移 {step} 过大（有人把它钳回去了）"
            prev = _global(shell, main)
    finally:
        hosts_mod._cleanup(shell)


def test_release_inside_one_screen_closes_the_domain_without_moving(tmp_path, monkeypatch):
    """身体整块落在某块屏内时松手：域当场收窄，且一个像素都不移动。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a)
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 500.0))
        overlay, origin, cursor = _grab(shell, main)
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)
        cursor = QPointF(origin.x() + 1000.0, cursor.y())
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)
        before = _global(shell, main)
        overlay.mouseReleaseEvent(_release(cursor - origin, cursor))
        _tick(shell)
        assert _global(shell, main) == before, "收窄域不许带来任何位移"
        assert getattr(main, "_clamp_rects", None) is None, "身体已合法 → 收窄"
        assert shell.host_for_sprite(main).screen is a
    finally:
        hosts_mod._cleanup(shell)


def test_slingshot_over_the_seam_keeps_the_open_domain(tmp_path, monkeypatch):
    """跨缝时进瞄准 / 发射 / 取消：域保持开着，位移只来自弹弓自己的物理。"""
    from tests.test_overlay_hosts_multiscreen import _right_press

    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a, {"drag_physics": True})
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 500.0))
        assert shell.move_sprite_to_screen(main, b, global_pos=QPointF(2000.0, 500.0)) is True
        overlay_b = shell.host_for_sprite(main).overlay
        origin_b = QPointF(overlay_b.geometry().topLeft())
        _hittable(main)
        hit = QPointF(main.rect().center())
        overlay_b.mousePressEvent(_press(hit, origin_b + hit))
        _tick(shell)
        cursor = origin_b + hit + QPointF(30.0, 0.0)
        overlay_b.mouseMoveEvent(_move(cursor - origin_b, cursor))
        _tick(shell)
        assert getattr(main, "_clamp_rects", None) is not None, "拖拽中域是开的"

        # 进瞄准：位置定锚不动、域保持开着
        anchor = _global(shell, main)
        overlay_b.mousePressEvent(_right_press(cursor - origin_b, cursor))
        assert shell._slingshot.aiming is True
        assert _global(shell, main) == anchor, "进瞄准不许移动这只"
        assert getattr(main, "_clamp_rects", None) is not None, "瞄准期间域不许被收"

        # 再点右键取消（就地恢复拖拽）：位置不跳，域仍开着
        overlay_b.mousePressEvent(_right_press(cursor - origin_b, cursor))
        assert shell._slingshot.aiming is False
        assert _global(shell, main) == anchor, "取消瞄准不许移动这只"
        assert getattr(main, "_clamp_rects", None) is not None

        # 松手：位置不跳，域按"身体是否已合法"决定去留
        before = _global(shell, main)
        overlay_b.mouseReleaseEvent(_release(cursor - origin_b, cursor))
        assert _global(shell, main) == before, "松手不许移动这只"
    finally:
        hosts_mod._cleanup(shell)


def test_straddling_pet_is_not_hauled_back_by_the_host_controllers(tmp_path, monkeypatch):
    """跨缝松手后，本屏的行为/物理控制器不许把它硬拽回本屏（第二次 snap 的另一半）。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a)
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 500.0))
        overlay, origin, cursor = _drag_to_straddle(shell, main, extra=-20.0)
        overlay.mouseReleaseEvent(_release(cursor - origin, cursor))
        host = shell.host_for_sprite(main)
        body = QRectF(main.body_rect()).translated(host.overlay.geometry().topLeft())
        assert body.left() < 1920.0, "前提：身体仍有一半在原屏"
        # 行为控制器（每 tick 都对正常态 sprite 调 _clamp_into_bounds）不许在这里钳
        for _ in range(20):
            _tick(shell)
        host = shell.host_for_sprite(main)
        body = QRectF(main.body_rect()).translated(host.overlay.geometry().topLeft())
        assert min(abs(body.left() - 1920.0), abs(body.left() + body.width() - 1920.0)) < (
            body.width()), "这只仍应停在缝附近（被拽回本屏就是硬钳）"
    finally:
        hosts_mod._cleanup(shell)


# ---------------------------------------------------------------- 6. 跨缝只读投影
def _composite(shell, screens):
    """把各窗的内容拼成一张"全局桌面"图（每窗按自己原点贴到对应位置）。

    投影正确时，拼出来的图应当与"同一块大屏、同一位置"的参考图**逐像素一致**
    （同 DPR、同素材、同位置；差异只可能来自拼接本身）。
    """
    from PySide6.QtGui import QImage, QPainter

    left = min(s.geometry().x() for s in screens)
    top = min(s.geometry().y() for s in screens)
    right = max(s.geometry().x() + s.geometry().width() for s in screens)
    bottom = max(s.geometry().y() + s.geometry().height() for s in screens)
    canvas = QImage(right - left, bottom - top, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(0)
    painter = QPainter(canvas)
    try:
        for host in shell.hosts():
            geo = host.overlay.geometry()
            pix = host.overlay.grab()
            painter.drawImage(geo.x() - left, geo.y() - top, pix.toImage())
    finally:
        painter.end()
    return canvas


def _body_pixels(canvas, body_global, alpha_min=128):
    """全局身体框内 alpha≥阈值 的像素占比（判断"这只在图上画出来了多少"）。"""
    hits = 0
    total = 0
    for x in range(int(body_global.left()), int(body_global.left() + body_global.width()), 4):
        for y in range(int(body_global.top()), int(body_global.top() + body_global.height()), 4):
            total += 1
            if canvas.pixelColor(x, y).alpha() >= alpha_min:
                hits += 1
    return hits / max(1, total)


def test_projection_makes_the_straddling_pet_fully_visible(tmp_path, monkeypatch):
    """身体跨缝时：两个窗拼起来这只**完整可见**（不是被缝裁掉一半）。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a)
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 400.0))
        overlay, origin, cursor = _drag_to_straddle(shell, main)
        host = shell.host_for_sprite(main)
        body = QRectF(main.body_rect()).translated(host.overlay.geometry().topLeft())
        assert body.left() < 1920.0 < body.left() + body.width(), "前提：身体跨在缝上"

        for host_ in shell.hosts():
            host_.overlay.grab()  # 先把两个窗都画过一遍（offscreen 下 grab 触发 paintEvent）
        canvas = _composite(shell, [a, b])
        covered = _body_pixels(canvas, body)
        assert covered > 0.6, (
            f"跨缝的身体在拼接图上只画出了 {covered:.0%}——投影没接上（缝那边是空的）")
        # 反例锚点：投影确实落在邻窗里（不是只靠本窗画出来的那一半）
        neighbour = shell.host_for_screen(b)
        assert neighbour is not None, "跨缝期间邻窗必须存在（投影画在那儿）"
        assert neighbour.overlay.projection_offset(main) is not None, "邻窗应当登记了这只的投影"
        assert neighbour.overlay.sprites == [], "邻窗只是画投影，不持有这只 sprite"
    finally:
        hosts_mod._cleanup(shell)


def test_projection_host_is_kept_until_the_transition_ends(tmp_path, monkeypatch):
    """投影期间邻窗不许被回收；过渡结束（域收窄、投影摘掉）后恢复可回收。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a)
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 400.0))
        overlay, origin, cursor = _drag_to_straddle(shell, main)
        host = shell.host_for_sprite(main)
        body = QRectF(main.body_rect()).translated(host.overlay.geometry().topLeft())
        assert body.left() < 1920.0 < body.left() + body.width(), "前提：身体跨在缝上"
        neighbour = shell.host_for_screen(b)
        assert neighbour is not None and neighbour.overlay.projection_offset(main) is not None, (
            "前提：邻窗正在画这只的投影")
        assert host.screen is a

        shell._reap_empty_hosts()
        assert shell.host_for_screen(b) is not None, "有投影的窗不许被回收"
        assert shell.host_for_screen(b).overlay.sprites == [], "它只是画投影，不持有 sprite"

        # 继续拖到 B 深处 → 身体整块进 B → 收窄域并摘掉投影
        cursor = QPointF(origin.x() + 2400.0, cursor.y())
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)
        assert shell.host_for_sprite(main).screen is b, "身体整块进 B"
        overlay.mouseReleaseEvent(_release(cursor - origin, cursor))
        _tick(shell)
        assert getattr(main, "_clamp_rects", None) is None, "身体整块在 B → 收窄域"
        assert shell.host_for_screen(a) is None or not shell.host_for_screen(a).overlay._projections, (
            "过渡结束：投影必须摘掉")
        shell._reap_empty_hosts()
        assert shell.host_for_screen(a) is None, "过渡结束后空窗照旧回收"
    finally:
        hosts_mod._cleanup(shell)


def test_switch_off_never_projects_and_never_creates_a_window(tmp_path, monkeypatch):
    """关闭跨屏：拖拽全程不投影、不建第二张窗（默认态与旧行为逐位相同）。"""
    a, b = _two_screens()
    _install(monkeypatch, [a, b])
    shell = _shell(tmp_path, a, switch=False)
    try:
        main = shell.sprite
        main.set_pos(QPointF(600.0, 400.0))
        overlay, origin, cursor = _grab(shell, main)
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)
        cursor = QPointF(origin.x() + 2600.0, cursor.y())
        overlay.mouseMoveEvent(_move(cursor - origin, cursor))
        _tick(shell)
        assert len(shell.hosts()) == 1, "关闭态不许建窗"
        assert not shell.overlay._projections, "关闭态不投影"
        _tick(shell)
        assert not shell.overlay._projections
    finally:
        hosts_mod._cleanup(shell)
