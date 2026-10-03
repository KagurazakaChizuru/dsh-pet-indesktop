# -*- coding: utf-8 -*-
"""屏迁移两缺陷回归：可见性/clip 暂停（缺陷 24）+ 比例位置被旧边界截断（缺陷 25）。

**缺陷 24**（实机探针：迁移后 ``overlay.isVisible()=True`` 而
``sprite.clip_paused=True`` —— 宠物冻在首帧、行为照常推着它动）：
``_migrate_to_screen`` 对 ``was_started`` 的壳无条件 ``show()``，用户隐藏
（托盘 ``set_pet_visible(False)`` / 全屏避让 ``_auto_hidden``）中的窗口被迁移
重新显示出来；而这条路径不恢复 clip 暂停，隐藏期被压住的播放节拍留在暂停。
契约：迁移前不可见 → 不 show、不动 clip 暂停（等真正的显示路径放行）；
迁移前可见 → show + 续播节拍。

**缺陷 25**：``_migrate_sprite_position`` 先从旧位置取比例（必须——先换边界时
``PetSprite.set_bounds`` 会就地钳一次），但落点仍走 ``sprite.set_pos``，受
**旧**边界钳制，``_apply_bounds`` 之后才换新边界：从小屏/低分迁到大屏/高分时
靠右/靠下的宠物先被旧边界截掉，扩边界后不恢复（实测宽 1000→1600：期望中心
x≈1358，实得旧边界钳出的 744+128）。契约：比例取自旧边界，落点钳在新边界下。

纪律：offscreen；真壳 + 真 PetSprite + 真 FrameSeqClip（节拍断言看真实 QTimer
是否激活）；同步直调 handler / 真信号推进，不 sleep。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, QPointF, QRect, Signal
from PySide6.QtWidgets import QApplication

import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_menu_facade as fac
from pet.frameseq_clip import FrameSeqClip
from pet.overlay_shell import OverlayShell
from pet.pet_sprite import PetSprite
from tests.test_frameseq_clip import _make_frames
from tests.test_overlay_geometry_parity import _place_center, _ratio_of

app = QApplication.instance() or QApplication([])


class FakeScreen(QObject):
    """假屏：显式 set_rects + 真实 Qt 信号（走产品真接线，不直调 handler）。"""

    geometryChanged = Signal(QRect)
    availableGeometryChanged = Signal(QRect)

    def __init__(self, geo, avail, *, dpr=1.0, refresh=60.0, name="mig-screen"):
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


def _make_shell(tmp_path, screen, values=None):
    config = cap.CapConfig(tmp_path, values)
    shell = OverlayShell(
        app, cap.CapInstance(config), screen=screen,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    lib = fac.RichLibrary()
    shell.lib = lib
    shell.sprite.library = lib
    return shell


def _make_clip_shell(tmp_path, screen=None):
    """主宠绑**真** FrameSeqClip 的壳：播放节拍断言看真实 QTimer，不看替身标记。

    隐藏/挂起的暂停链路（``sprite.pause_clip`` → ``clip.pause`` → 停表）只有真
    clip 才能观测；替身 FakeClip 的 ``pause`` 是空实现，暂停态可由 ``clip_paused``
    自证，但"节拍真的在跑"必须看真定时器。
    """
    shell = _make_shell(tmp_path, screen or FakeScreen((0, 0, 1000, 600),
                                                       (0, 0, 1000, 600)))
    frames_dir = tmp_path / "idle1"
    _make_frames(frames_dir)
    clip = FrameSeqClip(frames_dir)
    shell.lib._clips["idle1"] = clip
    assert shell.sprite.bind_clip("idle1") is True, "前提：真 clip 起播被接受"
    assert clip._timer.isActive() is True, "前提：起播后播放节拍在跑"
    return shell, clip


def _migrate(shell):
    """按真实入口迁移到主屏（fake screen → primaryScreen）。"""
    primary = app.primaryScreen()
    old = shell.overlay
    shell._migrate_to_screen(primary)
    assert shell.overlay is not old, "前提：迁移确实重建了 overlay"
    return old


def _teardown(shell, clip=None):
    shell.stop()
    shell.overlay.close()
    if clip is not None:
        clip.close()
    shell._delete_runtime_marker()


# ---------------------------------------------------------------- 缺陷 24：隐藏中迁移
def test_migrate_while_hidden_keeps_window_hidden_and_clips_paused(tmp_path):
    """托盘隐藏中迁移：不得 show、不得解除 clip 暂停（宠物不冻着乱跑）。"""
    shell, clip = _make_clip_shell(tmp_path)
    try:
        shell.start()
        assert shell.overlay.isVisible() is True
        shell.set_pet_visible(False)              # 托盘隐藏：整窗 hide + 逐只 pause
        assert shell.overlay.isVisible() is False
        assert shell.sprite.clip_paused is True
        assert clip._timer.isActive() is False

        _migrate(shell)

        assert shell.overlay.isVisible() is False, "隐藏中迁移不得把窗口显示出来"
        assert shell.sprite.clip_paused is True, "隐藏中迁移不得解除 clip 暂停"
        assert clip._timer.isActive() is False, "隐藏期零帧推进：迁移后也不得起表"
        # 隐藏分支不调 ``overlay.start()`` 的安全性：驱动器是进程级且新 overlay
        # 在构造时已 attach，旧 overlay 关闭时成员数不会归零——时钟必须照跑、
        # 新窗必须仍在成员里（隐藏期的档位/锁屏探测都挂在它上面）。
        assert shell.overlay in shell.driver._overlays, "新 overlay 必须仍被驱动器驱动"
        assert shell.driver.timer.isActive() is True, "迁移重建不得让 tick 时钟停摆"
    finally:
        _teardown(shell, clip)


def test_showing_after_hidden_migration_resumes_clip_cadence(tmp_path):
    """隐藏迁移只"顺延放行"：真正的显示路径（``set_pet_visible(True)``）恢复节拍。"""
    shell, clip = _make_clip_shell(tmp_path)
    try:
        shell.start()
        shell.set_pet_visible(False)
        _migrate(shell)

        shell.set_pet_visible(True)

        assert shell.overlay.isVisible() is True
        assert shell.sprite.clip_paused is False
        assert clip._timer.isActive() is True, "显示路径必须把迁移期压住的节拍放行"
    finally:
        _teardown(shell, clip)


# ---------------------------------------------------------------- 缺陷 24：全屏避让中迁移
def test_migrate_while_auto_hidden_does_not_show_window(tmp_path):
    """全屏避让（``_auto_hidden``）中迁移：不 show、clip 保持暂停。"""
    shell, clip = _make_clip_shell(tmp_path)
    try:
        shell.start()
        shell._on_fullscreen_changed(True)        # 全屏出现 → 自动隐藏 + 逐只 pause
        assert shell._auto_hidden is True
        assert shell.overlay.isVisible() is False

        _migrate(shell)

        assert shell._auto_hidden is True, "迁移不改全屏避让状态（仍由 watcher 重评）"
        assert shell.overlay.isVisible() is False, "全屏避让中迁移不得 show"
        assert shell.sprite.clip_paused is True
        assert clip._timer.isActive() is False
    finally:
        _teardown(shell, clip)


# ---------------------------------------------------------------- 缺陷 24：可见中迁移
def test_migrate_while_visible_keeps_window_shown_and_clips_running(tmp_path):
    """可见中迁移：窗口保持显示且播放节拍仍在跑（不得被闸门误压成暂停）。"""
    shell, clip = _make_clip_shell(tmp_path)
    try:
        shell.start()
        assert shell.overlay.isVisible() is True
        assert shell.sprite.clip_paused is False

        _migrate(shell)

        assert shell.overlay.isVisible() is True
        assert shell.sprite.clip_paused is False, "可见迁移必须保持续播"
        assert shell.sprite._clip is clip, "前提：迁移不换绑 clip"
        assert clip._timer.isActive() is True
    finally:
        _teardown(shell, clip)


# ---------------------------------------------------------------- 缺陷 25：小屏 → 大屏
def test_growing_bounds_keep_right_bottom_ratio(tmp_path):
    """可用区变大（同屏几何变化）：靠右/靠下的宠物比例位置不得被旧边界截断。

    旧序（比例 → ``set_pos`` 受旧边界钳 → ``_apply_bounds``）下，本夹具的落点
    是旧边界钳出的左上 (744, 456)；正确落点 (1230, 646) 只在**新**边界下合法。
    """
    screen = FakeScreen((0, 0, 1000, 600), (0, 0, 1000, 600))
    shell = _make_shell(tmp_path, screen, {"scale": 0.4})
    try:
        old_bounds = QRect(shell._bounds)
        sprite = shell.sprite
        placed = _place_center(sprite,
                               old_bounds.x() + 0.85 * old_bounds.width(),
                               old_bounds.y() + 0.8 * old_bounds.height())
        rx, ry = _ratio_of(placed, old_bounds)
        assert 0.8 < rx < 0.9, "夹具前提：靠右但未贴边（旧边界内合法）"
        assert 0.75 < ry < 0.85, "夹具前提：靠下但未贴边（旧边界内合法）"

        screen.set_rects((0, 0, 1600, 900), (0, 0, 1600, 900))
        screen.geometryChanged.emit(screen.geometry())   # 真信号接线

        new_bounds = QRect(shell._bounds)
        assert new_bounds == QRect(0, 0, 1600, 900)
        rect = sprite.rect()
        assert rect.center().x() == pytest.approx(
            new_bounds.x() + rx * new_bounds.width(), abs=2.0), "比例位置必须在新边界下落地"
        assert rect.center().y() == pytest.approx(
            new_bounds.y() + ry * new_bounds.height(), abs=2.0)
        # 反例锚点：先受旧边界钳制会把落点钉在 old_w - rect.w(=744) 附近
        assert rect.left() > old_bounds.width() - rect.width(), "不得停在旧边界钳出的位置"
    finally:
        shell._delete_runtime_marker()


def test_migrate_to_bigger_screen_keeps_ratio(tmp_path):
    """跨屏迁移（``_migrate_to_screen``）走同一 helper：扩屏同样不得被旧边界截断。"""
    small = FakeScreen((0, 0, 1000, 600), (0, 0, 1000, 600), name="small")
    big = FakeScreen((0, 0, 1600, 900), (0, 0, 1600, 900), name="big")
    shell = _make_shell(tmp_path, small, {"scale": 0.4})
    try:
        old_bounds = QRect(shell._bounds)
        sprite = shell.sprite
        placed = _place_center(sprite,
                               old_bounds.x() + 0.85 * old_bounds.width(),
                               old_bounds.y() + 0.8 * old_bounds.height())
        rx, ry = _ratio_of(placed, old_bounds)

        shell._migrate_to_screen(big)

        new_bounds = QRect(shell._bounds)
        assert new_bounds == QRect(0, 0, 1600, 900)
        rect = sprite.rect()
        assert rect.center().x() == pytest.approx(
            new_bounds.x() + rx * new_bounds.width(), abs=2.0)
        assert rect.center().y() == pytest.approx(
            new_bounds.y() + ry * new_bounds.height(), abs=2.0)
    finally:
        shell.overlay.close()
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- 缺陷 25：大屏 → 小屏
def test_shrinking_bounds_still_clamp_into_new_bounds(tmp_path):
    """大屏 → 小屏：比例落点越界时仍按**新**边界钳制（钳制不因换序被跳过）。"""
    screen = FakeScreen((0, 0, 1600, 900), (0, 0, 1600, 900))
    shell = _make_shell(tmp_path, screen, {"scale": 0.4})
    try:
        old_bounds = QRect(shell._bounds)
        sprite = shell.sprite
        placed = _place_center(sprite,
                               old_bounds.x() + 0.92 * old_bounds.width(),
                               old_bounds.y() + 0.9 * old_bounds.height())
        rx, ry = _ratio_of(placed, old_bounds)

        screen.set_rects((0, 0, 1000, 600), (0, 0, 1000, 600))
        screen.availableGeometryChanged.emit(screen.availableGeometry())

        new_bounds = QRect(shell._bounds)
        assert new_bounds == QRect(0, 0, 1000, 600)
        rect = sprite.rect()
        assert rect.right() <= new_bounds.right(), "身体必须完整落在新可用区内"
        assert rect.bottom() <= new_bounds.bottom()
        # 比例理想值越界 → 钳到新右/下界（与 PetSprite._clamp_axis 同口径）
        assert rect.left() == pytest.approx(new_bounds.width() - rect.width(), abs=2.0)
        assert rect.top() == pytest.approx(new_bounds.height() - rect.height(), abs=2.0)
        assert rect.center().x() < new_bounds.x() + rx * new_bounds.width()
        assert rect.center().y() < new_bounds.y() + ry * new_bounds.height()
    finally:
        shell._delete_runtime_marker()
