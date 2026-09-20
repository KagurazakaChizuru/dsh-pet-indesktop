# -*- coding: utf-8 -*-
"""果冻墙（灵动岛本进程直连碰撞）：FLAG_STATIC 弹性规则 + 本地检测/结算。"""
from __future__ import annotations

import math
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from pet import collision
from pet import window_placement
from pet.collision_ipc import _KNOWN_FLAGS_MASK
from pet.config import Config
from pet.dynamic_island import DynamicIsland
from pet.island_collision import IslandCollisionBody, _segment_circle_entry


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pet(runtime_id="pet", x=100.0, y=100.0, vx=-600.0, flags=0) -> collision.MemberState:
    return collision.MemberState(
        runtime_id=runtime_id, x=x, y=y, radius_x=50.0, radius_y=50.0,
        vx=vx, vy=0.0, flags=collision.FLAG_VISIBLE | collision.FLAG_COLLISION_ENABLED | flags,
    )


def _island_state(flags=collision.FLAG_STATIC) -> collision.MemberState:
    return collision.MemberState(
        runtime_id="island", x=200.0, y=100.0, radius_x=100.0, radius_y=22.0,
        vx=0.0, vy=0.0, is_infinite_mass=True,
        flags=collision.FLAG_VISIBLE | collision.FLAG_COLLISION_ENABLED | flags,
    )


# ------------------------------------------------------------ 弹性规则（通用求解器）
def test_static_wall_boosts_restitution_pet_bounces_off_faster():
    """FLAG_STATIC 静态岛加速弹开（e=1.3）：撞岛比撞墙弹得更快，像撞弹床。"""
    pet = _pet(vx=600.0)  # 桌宠在岛左侧，向右（+x）撞岛
    island = _island_state()
    # nx=-1：法线从 A(岛) 指向 B(桌宠)，接近速度 vn = 600*(-1) < 0
    jn, dvx_a, _dvy_a, dvx_b, _dvy_b = collision.solve_collision_impulse(
        island, pet, -1.0, 0.0,
        restitution=0.82, friction=0.08, impulse_cap=9000.0)
    assert jn > 0
    assert dvx_a == 0.0  # 岛无限质量，不动
    # e=1.3 加速反弹：桌宠末速 = 600 * (-1.3) = -780（比入射更快地弹回）
    assert pet.vx + dvx_b < -600.0


def test_static_wall_low_speed_contact_stays_dead():
    """低速贴上岛不抖动：接近速度低于阈值仍 e=0（只挡不弹）。"""
    pet = _pet(vx=50.0)  # 低于 IMPULSE_MIN_APPROACH_SPEED(80)
    island = _island_state()
    _jn, _dva, _dva2, dvx_b, _dvb = collision.solve_collision_impulse(
        island, pet, -1.0, 0.0,
        restitution=0.82, friction=0.08, impulse_cap=9000.0)
    # e=0：仅消除接近速度，不反转、不加速
    assert abs(pet.vx + dvx_b) < 1e-6


def test_static_flag_in_known_mask():
    assert _KNOWN_FLAGS_MASK & collision.FLAG_STATIC == collision.FLAG_STATIC


def test_segment_circle_entry_swept():
    """扫掠 TOI：线段进入圆返回最早时刻；未进入返回 None。"""
    assert _segment_circle_entry((0.0, 0.0), (100.0, 0.0), (50.0, 0.0), 10.0) == 0.4
    assert _segment_circle_entry((0.0, 0.0), (100.0, 0.0), (50.0, 8.0), 10.0) is not None
    assert _segment_circle_entry((0.0, 0.0), (100.0, 0.0), (50.0, 30.0), 10.0) is None
    assert _segment_circle_entry((5.0, 5.0), (5.0, 5.0), (5.0, 5.0), 3.0) == 0.0  # 起点在内


# ------------------------------------------------------------ 本地碰撞体
class FakePhysicsTimer:
    def __init__(self):
        self.started = False

    def start(self):
        self.started = True


class FakeWin:
    """最小桌宠窗口桩：本地结算触及的全部属性/方法。"""

    def __init__(self, x: float, y: float, vx: float = 0.0, vy: float = 0.0,
                 size: int = 120, visible: bool = True, *, w: int | None = None,
                 h: int | None = None, screen_w: int = 2560, screen_h: int = 1440):
        self._x, self._y = x, y
        self._size = size
        self._w = w if w is not None else size
        self._h = h if h is not None else size
        self._screen_w, self._screen_h = screen_w, screen_h
        self._visible = visible
        self._phys_vel = [vx, vy]
        self._phys_pos = [x, y]
        self._interaction_state = "IDLE"
        self._physics_mode = ""
        self._physics_timer = FakePhysicsTimer()
        self._throw_speed_cap = 4800.0
        self._throw_egg = None
        self._edge_probe = None
        self._squash_active = False
        self._hidden_paused = False
        self._last_physics_tick_time = None
        self.cfg = SimpleNamespace(get=lambda k, d=None: d)
        self.sounds = 0
        self.squashes = 0
        self.entered_modes = []

    def isVisible(self):
        return self._visible

    def collision_content_rect(self) -> QRect:
        return QRect(int(self._x), int(self._y), self._w, self._h)

    def x(self):
        return int(self._x)

    def y(self):
        return int(self._y)

    def move(self, x, y):
        self._x, self._y = float(x), float(y)

    def _collision_clamp_pos(self, x, y):
        x = 0.0 if x == float("-inf") else (float(self._screen_w) if x == float("inf") else x)
        y = 0.0 if y == float("-inf") else (float(self._screen_h) if y == float("inf") else y)
        return x, y

    def _cancel_move(self):
        pass

    def _cancel_animation_gap(self):
        pass

    def _play_collision_sound(self):
        self.sounds += 1

    def _enter_physics_mode(self, mode):
        self._physics_mode = mode
        self.entered_modes.append(mode)

    def _start_squash(self):
        self.squashes += 1


class VirtualWin(FakeWin):
    """带 #137 视口模型接口的桌宠桩：虚拟位置 = 实际 + 绘制偏移。

    _move_window_towards 记录虚拟目标并让窗口跟到该虚拟位置（模拟统一出口
    的「窗口钳回 + 偏移」语义），供「贴边命中走虚拟坐标」回归使用。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._draw_delta = QPoint(-80, 0)  # 贴左缘：虚拟 = 实际 - 80
        self.moves: list[tuple[float, float]] = []

    def _virtual_pos(self):
        return QPoint(int(self._x) + self._draw_delta.x(),
                      int(self._y) + self._draw_delta.y())

    def _move_window_towards(self, x, y, body_bounds=None):
        self.moves.append((float(x), float(y)))
        self._x = x - self._draw_delta.x()
        self._y = y - self._draw_delta.y()


def _make_body(tmp_path: Path, pets=()):
    cfg = Config(base=tmp_path)
    cfg.set("dynamic_island", {"enabled": True, "x": 400, "y": 300})
    island = DynamicIsland(cfg)
    body = IslandCollisionBody(island, cfg, pets_provider=lambda: list(pets))
    return island, body


def test_body_start_stop_lifecycle(tmp_path):
    _qapp()
    island, body = _make_body(tmp_path)
    try:
        island.show()
        body.start()
        assert body._running and body._timer.isActive()
        body.stop()
        assert not body._running and not body._timer.isActive()
    finally:
        island.hide()
        island.deleteLater()


def test_fast_pet_bounces_off_island(tmp_path):
    """高速撞岛：本地结算 e=1.3 弹回 + 进抛掷物理 + 音效 + 岛播 bump。"""
    _qapp()
    # 岛在 (400,300)（体育场轴 [422,634], y=322, r=22）；肥鱼贴岛左缘向右撞
    win = FakeWin(x=300.0, y=260.0, vx=600.0)
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        bumps = []
        island.bump = lambda *args: bumps.append(args)
        body._running = True
        now = time.monotonic()
        # 注入上帧：50ms 前在 (330,320) → 实测速度 600px/s 向右
        body._pet_prev[id(win)] = (330.0, 320.0)
        body._pet_prev_ts[id(win)] = now - 0.05
        body._tick()
        assert win._phys_vel[0] < 0.0  # 被弹回左侧
        # e=1.3 加速：末速率 = 600*1.3
        assert abs(win._phys_vel[0]) > 600.0
        assert win._interaction_state == "THROWN"
        assert "throw" in win.entered_modes
        assert win.sounds == 1
        assert len(bumps) == 1
        _strength, dir_x, _dir_y = bumps[0]
        assert dir_x > 0.0  # 岛被向右顶
    finally:
        island.hide()
        island.deleteLater()


def test_swept_hit_catches_tunneling_pet(tmp_path):
    """上一帧还在岛左侧远处、这一帧已在岛右侧：扫掠仍判定命中（防隧道），
    且被放回来路一侧。"""
    _qapp()
    win = FakeWin(x=700.0, y=260.0, vx=4800.0)  # 岛在 400,300；这帧已穿过
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        now = time.monotonic()
        # 100ms 前在岛左侧 (260,320)：合法高速甩出（4800px/s）不被瞬移守卫误杀
        body._pet_prev[id(win)] = (260.0, 320.0)
        body._pet_prev_ts[id(win)] = now - 0.1
        body._tick()
        assert win._interaction_state == "THROWN"  # 被拦下结算
        assert win._phys_vel[0] < 0.0  # 弹回来路
        # TOI 放回：位于岛体左侧（来路一侧），不在右侧
        assert win.collision_content_rect().center().x() < 400
    finally:
        island.hide()
        island.deleteLater()


def test_slow_contact_separates_without_bounce(tmp_path):
    """低速贴上（相对接近 <20px/s）：只推出不弹飞、不进抛掷、不响。"""
    _qapp()
    win = FakeWin(x=340.0, y=285.0, vx=5.0)  # 与岛左缘轻贴
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        bumps = []
        island.bump = lambda *args: bumps.append(args)
        now = time.monotonic()
        # 上帧同位（50ms 无位移）→ 实测速度 0
        rect = win.collision_content_rect()
        body._pet_prev[id(win)] = (float(rect.center().x()), float(rect.center().y()))
        body._pet_prev_ts[id(win)] = now - 0.05
        old_x = win._x
        body._tick()
        assert win._interaction_state == "IDLE"  # 不弹飞
        assert win.sounds == 0
        assert bumps == []
        assert win._x != old_x  # 但被推出重叠区
    finally:
        island.hide()
        island.deleteLater()


def test_dragged_pet_and_hidden_pet_skipped(tmp_path):
    """拖拽中的桌宠（用户在摆放）与隐藏的桌宠不参与结算。"""
    _qapp()
    dragged = FakeWin(x=340.0, y=285.0, vx=600.0)
    dragged._physics_mode = "drag"
    hidden = FakeWin(x=340.0, y=285.0, vx=600.0, visible=False)
    island, body = _make_body(tmp_path, pets=[dragged, hidden])
    try:
        island.show()
        body._running = True
        body._tick()
        assert dragged._interaction_state == "IDLE"
        assert hidden._interaction_state == "IDLE"
    finally:
        island.hide()
        island.deleteLater()


def test_hit_cooldown_per_pet(tmp_path):
    """0.15s 命中冷却：同一只桌宠连着两次接近只结算一次。"""
    _qapp()
    win = FakeWin(x=300.0, y=260.0, vx=600.0)
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        now = time.monotonic()
        body._pet_prev[id(win)] = (330.0, 320.0)
        body._pet_prev_ts[id(win)] = now - 0.05
        body._tick()
        first_v = win._phys_vel[0]
        # 冷却内再来一次接近（重新注入接近轨迹）
        body._pet_prev[id(win)] = (330.0, 320.0)
        body._pet_prev_ts[id(win)] = time.monotonic() - 0.05
        win._x, win._y = 300.0, 260.0
        body._tick()
        assert win._phys_vel[0] == first_v
    finally:
        island.hide()
        island.deleteLater()


def test_dragging_island_slaps_stationary_pet(tmp_path):
    """拖着岛扫鱼：岛速参与相对速度，静止的鱼被拍飞（深度重叠按相对运动解围）。"""
    _qapp()
    win = FakeWin(x=560.0, y=285.0, vx=0.0)  # 静止在岛右端上方
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        # 模拟岛正被向右拖（速度 800px/s）；鱼静止（实测位移 0）
        body._vx, body._vy = 800.0, 0.0
        now = time.monotonic()
        rect = win.collision_content_rect()
        body._pet_prev[id(win)] = (float(rect.center().x()), float(rect.center().y()))
        body._pet_prev_ts[id(win)] = now - 0.05
        body._check_pet(win, body._island_stadium(), island.geometry(), now, set())
        assert win._phys_vel[0] > 0.0  # 向右飞出去
        assert win._interaction_state == "THROWN"
    finally:
        island.hide()
        island.deleteLater()


def test_in_zone_slow_drift_never_rebounces(tmp_path):
    """已在岛区内低速漂移的桌宠只被推出、绝不二次弹飞（entry-based 反弹回归）。

    30Hz 判定下"区内被判定反弹 → 反弹速度不足以离区 → 下一帧再判定"的鬼畜
    抽搐根因：上一帧已在区内（was_inside）、相对速度 120px/s（超 20 接近阈值、
    低于拖岛拍鱼的 150 横扫阈值）——旧实现会再命中（THROWN+响），新实现只分离。
    """
    _qapp()
    win = FakeWin(x=443.0, y=290.0)  # 中心 (503, 350)，位于岛轴 [422,634] 内
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        now = time.monotonic()
        # 上一帧中心 (497,350) 已在区内；本帧 (503,350) → 6px/0.05s=120px/s 向内漂
        body._pet_prev[id(win)] = (497.0, 350.0)
        body._pet_prev_ts[id(win)] = now - 0.05
        old_y = win._y
        body._tick()
        assert win._interaction_state == "IDLE"  # 未重进 throw
        assert win.entered_modes == []
        assert win.sounds == 0
        assert win._y != old_y  # 但被推出重叠区（只挡不弹）
    finally:
        island.hide()
        island.deleteLater()


def test_island_velocity_estimate_zero_when_still(tmp_path):
    """岛不动时速度估计为 0（静止噪声不拍鱼）。"""
    _qapp()
    island, body = _make_body(tmp_path)
    try:
        island.show()
        body._update_motion()
        body._update_motion()
        assert body._vx == 0.0 and body._vy == 0.0
    finally:
        island.hide()
        island.deleteLater()


def test_island_velocity_survives_high_freq_submit(tmp_path):
    """拖拽中高频几何回调（dt<0.01）不再把岛速清零（实机回归）。

    旧逻辑在 dt<0.01 时清零并刷新采样点：拖拽的 mouseMove 频率远超
    30Hz，岛速被反复清零，"拖岛拍鱼"退化成只推挤不弹飞。
    """
    _qapp()
    island, body = _make_body(tmp_path)
    try:
        island.show()
        rect = island.geometry()
        now = time.monotonic()
        # 上一次有效采样：50ms 前、中心靠左 40px → 拖拽速度约 800px/s
        body._last_center = (float(rect.center().x()) - 40.0,
                             float(rect.center().y()))
        body._last_motion_ts = now - 0.05
        body._update_motion()
        assert math.isclose(body._vx, 800.0, rel_tol=0.05)
        sampled_ts = body._last_motion_ts
        # 紧跟一波高频回调（间隔远小于 10ms）：速度保留、采样点不刷新
        for _ in range(5):
            body._update_motion()
        assert math.isclose(body._vx, 800.0, rel_tol=0.05)
        assert body._last_motion_ts == sampled_ts
    finally:
        island.hide()
        island.deleteLater()


def test_docked_strip_skips_collision(tmp_path):
    """停靠细条态不结算碰撞：16×64 竖条与 stadium 水平轴假设不符（幻影墙），
    且贴屏边细条碰撞价值低；悬停滑出恢复胶囊后照常结算。"""
    _qapp()
    win = FakeWin(x=60.0, y=478.0, vx=-600.0)
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        island._mode = "docked"
        island._hover_peek = False
        body._running = True
        body._tick()
        assert win._interaction_state == "IDLE"  # 细条态不结算
        # 悬停滑出（几何动画进行中）同样不结算
        island._hover_peek = True
        island._geo_to = QRect(16, 440, 260, 44)
        body._tick()
        assert win._interaction_state == "IDLE"
    finally:
        island.hide()
        island.deleteLater()


def test_island_teleport_does_not_launch_pet(tmp_path):
    """岛瞬移（配置变更/换屏/夹回屏幕）不产生拍鱼速度（跳变守卫）。"""
    _qapp()
    island, body = _make_body(tmp_path)
    try:
        island.show()
        body._update_motion()          # 建立采样基线
        body._last_motion_ts -= 0.1    # 模拟 100ms 间隔
        island.move(island.x() + 800, island.y())  # 瞬移 800px
        body._update_motion()
        assert body._vx == 0.0 and body._vy == 0.0
        # 守卫只重置采样点：下一次正常拖拽估计不受影响
        body._last_motion_ts -= 0.1
        island.move(island.x() + 30, island.y())   # 30px/100ms = 300px/s
        body._update_motion()
        assert math.isclose(body._vx, 300.0, rel_tol=0.2)
    finally:
        island.hide()
        island.deleteLater()


def test_separation_cancels_pet_move_plan(tmp_path):
    """岛推出桌宠前取消其自主移动计划（否则 33ms 后移动插值覆盖分离位置）。"""
    _qapp()
    win = FakeWin(x=560.0, y=285.0, vx=0.0)  # 静止贴在岛右端
    island, body = _make_body(tmp_path, pets=[win])
    cancels = {"move": 0, "gap": 0}
    win._cancel_move = lambda: cancels.__setitem__("move", cancels["move"] + 1)
    win._cancel_animation_gap = lambda: cancels.__setitem__("gap", cancels["gap"] + 1)
    try:
        island.show()
        body._running = True
        now = time.monotonic()
        rect = win.collision_content_rect()
        body._pet_prev[id(win)] = (float(rect.center().x()), float(rect.center().y()))
        body._pet_prev_ts[id(win)] = now - 0.05
        body._check_pet(win, body._island_stadium(), island.geometry(), now, set())
        assert cancels["move"] >= 1 and cancels["gap"] >= 1
    finally:
        island.hide()
        island.deleteLater()


def test_island_hit_ignores_pet_global_collision_switch(tmp_path):
    """桌宠全局碰撞开关（多开桌宠之间碰撞）不否决果冻墙——岛只由自己的开关管。"""
    _qapp()
    win = FakeWin(x=560.0, y=285.0, vx=-600.0)
    win.cfg = SimpleNamespace(
        get=lambda k, d=None: False if k == "collision_enabled" else d)
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        now = time.monotonic()
        rect = win.collision_content_rect()
        body._pet_prev[id(win)] = (float(rect.center().x()) + 40.0,
                                   float(rect.center().y()))
        body._pet_prev_ts[id(win)] = now - 0.05
        body._check_pet(win, body._island_stadium(), island.geometry(), now, set())
        assert win._interaction_state == "THROWN"
    finally:
        island.hide()
        island.deleteLater()


def test_island_resize_does_not_inject_phantom_speed(tmp_path):
    """窗口尺寸变化（展开/收起卡片等）只重置采样点——窗口中心平移不是岛速。"""
    _qapp()
    island, body = _make_body(tmp_path)
    try:
        island.show()
        body._update_motion()           # 建立基线（含尺寸）
        body._last_motion_ts -= 0.05
        # 岛处于 setFixedSize 状态，先解锁再 resize（否则 resize 是 no-op，
        # 测试空转——判别力：删掉 size 守卫后，中心平移 +40px/50ms=800px/s
        # 会让 _vx 非零，断言判红）
        island.setMinimumSize(0, 0)
        island.setMaximumSize(16777215, 16777215)
        island.resize(island.width() + 80, island.height())  # 纯 resize
        body._update_motion()
        assert body._vx == 0.0 and body._vy == 0.0
    finally:
        island.hide()
        island.deleteLater()


# ------------------------------------------------------------ issue #146 后续修复回归
def test_tall_pet_separates_at_half_width_not_half_height(tmp_path):
    """高瘦桌宠贴岛侧壁：分离距离按横向半宽（椭圆代理），不再按身高一半的胖圆。

    回归：旧实现 pet_radius=max(w,h)/2，shenshen 0.72 下横向凭空粗 19px
    （1.5 下 40px），贴岛侧壁时被推得离岛更远（「碰撞体积比岛本身大得多」）。
    """
    _qapp()
    # 高瘦身体 156×194（横向半宽 78、纵向半高 97），中心与岛轴同高（纯横向分离）
    win = FakeWin(x=300.0, y=225.0, w=156, h=194)
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        now = time.monotonic()
        rect = win.collision_content_rect()
        body._pet_prev[id(win)] = (float(rect.center().x()), float(rect.center().y()))
        body._pet_prev_ts[id(win)] = now - 0.05
        body._tick()  # 静止轻贴 → 只分离
        ax0, _ax1, ay, rr, _h = body._island_stadium()
        assert win._interaction_state == "IDLE"
        # 分离后中心距轴 = 横向半宽 78 + 岛半径 22 + 1
        center_x = win.collision_content_rect().center().x()
        assert abs(center_x - (ax0 - (78.0 + rr + 1.0))) < 2.0
        # 旧胖圆口径会把中心推到 ax0 - (97+22+1)，多出 19px——断言没被推那么远
        assert center_x > ax0 - (97.0 + rr + 1.0) + 1.0
    finally:
        island.hide()
        island.deleteLater()


def test_throw_mode_pet_separates_without_rehit(tmp_path):
    """抛掷物理中的桌宠：岛只挡不弹（不叠加冲量/不进第二次 throw/不响）。

    多重回弹根因回归：撞飞后桌宠在岛↔屏幕边缘间往返时，若每次接近都重新
    命中结算，会连环弹。物理期间只分离——用高速接近姿态判别（旧实现会命中）。
    """
    _qapp()
    win = FakeWin(x=300.0, y=260.0, vx=600.0)
    win._physics_mode = "throw"
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        bumps = []
        island.bump = lambda *args: bumps.append(args)
        now = time.monotonic()
        # 50ms 前在 (330,320) → 实测 600px/s 向右高速接近（旧实现会重新命中）
        body._pet_prev[id(win)] = (330.0, 320.0)
        body._pet_prev_ts[id(win)] = now - 0.05
        body._tick()
        assert win._interaction_state == "IDLE"  # 未重进 throw
        assert win.entered_modes == []
        assert win.sounds == 0
        assert bumps == []
    finally:
        island.hide()
        island.deleteLater()


def test_hit_and_separation_use_virtual_coordinates(tmp_path):
    """贴边（delta≠0）被岛撞：抛掷起点与分离位移都落在虚拟坐标上（#137 口径）。

    回归：旧实现写实际窗口位置，_phys_pos 与分离目标都差一个绘制偏移，throw
    从错误位置起跳（贴边命中后出现「意料之外」的轨迹/连环弹）。
    """
    _qapp()
    win = VirtualWin(x=340.0, y=285.0, vx=600.0)
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        body._running = True
        now = time.monotonic()
        body._pet_prev[id(win)] = (370.0, 320.0)
        body._pet_prev_ts[id(win)] = now - 0.05
        body._tick()
        assert win._interaction_state == "THROWN"
        # 抛掷起点 = 虚拟坐标（= 实际 + 绘制偏移），不是实际窗口位置
        vp = win._virtual_pos()
        assert abs(win._phys_pos[0] - vp.x()) < 2.0, \
            f"_phys_pos.x={win._phys_pos[0]} 应为虚拟 {vp.x()}（旧实现写成实际 {win.x()}）"
        assert abs(win._phys_pos[1] - vp.y()) < 2.0
        # 分离经统一出口（虚拟坐标）落窗，而不是直接 move 实际位置
        assert win.moves, "分离应经 _move_window_towards 落窗"
        vx2, vy2 = win._virtual_pos().x(), win._virtual_pos().y()
        assert abs(win.moves[-1][0] - vx2) < 2.0 and abs(win.moves[-1][1] - vy2) < 2.0
    finally:
        island.hide()
        island.deleteLater()


def test_hit_geometry_independent_of_screen_size(tmp_path):
    """不同分辨率屏幕：岛命中/分离几何与屏幕尺寸无关（只依赖岛几何与桌宠椭圆）。"""
    _qapp()
    for screen_w, screen_h in ((1024, 768), (1920, 1080), (3840, 2160)):
        win = FakeWin(x=300.0, y=260.0, vx=600.0,
                      screen_w=screen_w, screen_h=screen_h)
        island, body = _make_body(tmp_path, pets=[win])
        try:
            island.show()
            body._running = True
            now = time.monotonic()
            body._pet_prev[id(win)] = (330.0, 320.0)
            body._pet_prev_ts[id(win)] = now - 0.05
            body._tick()
            assert win._interaction_state == "THROWN"
            assert win._phys_vel[0] < 0.0  # 弹回来路
        finally:
            island.hide()
            island.deleteLater()


# ------------------------------------------------------------ 同步硬墙（屏幕边界式位置钳制）
class _ClampScreen:
    def name(self):
        return "big"

    def availableGeometry(self):
        return QRect(0, 0, 3840, 2160)

    def devicePixelRatio(self):
        return 1.0


class ClampWin:
    """统一位置出口（move_window_towards）的窗口桩：全窗口即身体（无 body_box）。"""

    def __init__(self, x: float, y: float, w: int, h: int):
        self._x, self._y = x, y
        self._w, self._h = w, h
        self.scale = 1.0
        self._capture_headroom = 0
        self._draw_delta = QPoint(0, 0)
        self._collision_local_bounds = None
        self.cfg = SimpleNamespace(get=lambda k, d=None: d)
        self._screen = _ClampScreen()

    def _screen_available(self, *_a, **_k):
        return self._screen

    def pos(self):
        return QPoint(self._x, self._y)

    def move(self, x, y):
        self._x, self._y = int(x), int(y)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def _sync_mask(self):
        pass

    def update(self):
        pass

    def _schedule_position_sync(self):
        pass

    def _submit_collision_state(self, *_a, **_k):
        pass


def _assert_body_out_of_stadium(win, body, msg=""):
    """断言身体框（全窗口）中心到岛轴的距离 >= 矩形径向半径 + 岛半径 + 1。"""
    stadium = body._island_stadium()
    ax0, ax1, ay, rr, _h = stadium
    center_x = win.x() + win._draw_delta.x() + win._w / 2.0
    center_y = win.y() + win._draw_delta.y() + win._h / 2.0
    closest_x = min(max(center_x, ax0), ax1)
    dx, dy = center_x - closest_x, center_y - ay
    dist = math.hypot(dx, dy)
    assert dist > 1e-9, f"身体中心不应恰好落在岛轴上：{msg}"
    nx, ny = dx / dist, dy / dist
    radial = min((win._w / 2) / max(abs(nx), 1e-9),
                 (win._h / 2) / max(abs(ny), 1e-9))
    assert dist >= radial + rr + 1.0 - 1e-6, (
        f"身体框未被钳出岛区：中心距轴 {dist:.1f} < 径向 {radial:.1f} + 岛半径 {rr} + 1（{msg}）"
    )


def test_synchronous_clamp_keeps_body_out_of_island(tmp_path):
    """同步硬墙：统一位置出口在每次落窗前把身体框钳出岛碰撞区（像屏幕边界墙）。

    30Hz 判定有采样间隙（帧间可钻进区→被弹→速度不足离区→再判定→抽搐）；
    同步钳制在 move_window_towards 里逐次落窗，身体框根本不进入岛区，从源头
    杜绝穿透与抽搐。这里目标位置让身体中心落在岛轴上，应被钳到岛外。
    """
    _qapp()
    island, body = _make_body(tmp_path)
    try:
        island.show()
        body._running = True
        win = ClampWin(1000, 1000, 200, 100)
        win._island_clamp_body = body._clamp_body
        stadium = body._island_stadium()
        ax0, ax1, ay, rr, _h = stadium
        target_cx = (ax0 + ax1) / 2.0
        window_placement.move_window_towards(
            win, target_cx - win._w / 2.0, ay - win._h / 2.0)
        _assert_body_out_of_stadium(win, body, "落点恰在岛轴")
    finally:
        island.hide()
        island.deleteLater()


def test_no_island_clamp_without_hook(tmp_path):
    """无 hook（岛碰撞关闭）时 move_window_towards 不钳制——行为与改造前一致。"""
    _qapp()
    island, body = _make_body(tmp_path)
    try:
        island.show()
        body._running = True
        win = ClampWin(1000, 1000, 200, 100)
        stadium = body._island_stadium()
        ax0, ax1, ay, _rr, _h = stadium
        target_cx = (ax0 + ax1) / 2.0
        window_placement.move_window_towards(
            win, target_cx - win._w / 2.0, ay - win._h / 2.0)
        center_x = win.x() + win._draw_delta.x() + win._w / 2.0
        center_y = win.y() + win._draw_delta.y() + win._h / 2.0
        # 统一出口对坐标取整（int(round)），容差放 1px
        assert abs(center_x - target_cx) < 1.0
        assert abs(center_y - ay) < 1.0
    finally:
        island.hide()
        island.deleteLater()


def test_clamp_hook_registered_and_cleared_by_lifecycle(tmp_path):
    """start 给桌宠挂同步硬墙 hook，stop 清除（岛碰撞关闭后不设墙）。"""
    _qapp()
    win = ClampWin(1000, 1000, 200, 100)
    island, body = _make_body(tmp_path, pets=[win])
    try:
        island.show()
        assert getattr(win, "_island_clamp_body", None) is None
        body.start()
        # 绑定方法每次访问是新对象，比 __func__
        assert win._island_clamp_body.__func__ is body._clamp_body.__func__
        body.stop()
        assert win._island_clamp_body is None
    finally:
        island.hide()
        island.deleteLater()
