# -*- coding: utf-8 -*-
"""灵动岛碰撞（本进程直连版，同步硬墙）。

为什么把 30Hz 检测/结算删掉（issue #146 实机教训）：岛作为位置硬墙后，
30Hz 采样判定反而引入抖动——桌宠帧间钻进岛区、在区内被判定反弹、反弹速度
不足离场、下一帧再判定（分离还会把跟踪中心重置成"区外"，让 1~2px 回渗被当
"新鲜进入"再弹）——velocity 反弹在 30Hz 下修不干净，只好整个删掉。改成屏幕
边界同款机制：

- 岛是同步位置硬墙：身体框任何移动（拖拽/漫游/抛掷/落位）只要会进岛区，
  就在统一位置出口 move_window_towwards 里被钳出（岛碰撞体通过 host 上的
  _island_clamp_body hook 注册/清除，无岛时 no-op）。身体框根本不进入岛区，
  没有采样间隙、没有 velocity 反馈循环，从源头杜绝穿透与抽搐；
- 岛被拖到桌宠身上（岛动而桌宠没动）：on_geometry_changed → submit 事件
  驱动把被压住的桌宠经统一出口推出，无定时器，与同步墙同口径；
- 抛掷中撞岛：在墙处把速度沿墙法线反射（口径与屏幕边缘 throw_step 的
  RESTITUTION 一致）并钉住物理位置——像撞屏幕边缘一样弹开，不会物理空间
  穿过岛、视觉却被钉在墙上。

低占用：无定时器，只在每次落窗时做一次几何查询。
"""
from __future__ import annotations

import logging
import math

from PySide6.QtCore import QObject

from . import physics as physics_mod

log = logging.getLogger(__name__)

_CAPSULE_HEIGHT = 44        # 胶囊视觉高度（与 dynamic_island._CAPSULE_HEIGHT 同步）


def _rect_radial(rx: float, ry: float, nx: float, ny: float) -> float:
    """身体矩形在半轴 (rx, ry) 下沿单位法线 (nx, ny) 的径向半径。

    矩形边界到中心的距离比内切椭圆大（椭圆只相切于四条边中点）；同步硬墙
    钳制用矩形口径，保证身体框整体不进入岛碰撞区。
    """
    if abs(nx) <= 1e-9:
        return ry / max(abs(ny), 1e-9)
    if abs(ny) <= 1e-9:
        return rx / max(abs(nx), 1e-9)
    return min(rx / abs(nx), ry / abs(ny))


class IslandCollisionBody(QObject):
    """灵动岛的同步硬墙：身体框任何移动都进不了岛碰撞区（屏幕边界语义）。

    没有 30Hz 检测/结算定时器：岛碰撞体只在统一位置出口
    move_window_towwards 里按需钳制位置（host 上挂 _island_clamp_body hook），
    以及岛自己移动时（on_geometry_changed → submit）事件驱动推出被压住的桌宠。
    """

    def __init__(self, island, config, pets_provider=None, parent=None):
        super().__init__(parent if isinstance(parent, QObject) else None)
        self._island = island
        self._config = config
        # 返回本进程全部桌宠窗口的回调（AppShell 注入）
        self._pets_provider = pets_provider or (lambda: ())
        self._running = False

    # ------------------------------------------------------------ 生命周期
    def _register_clamp_hooks(self) -> None:
        """给全部桌宠窗口挂同步硬墙 hook（move_window_towwards 里按需调用）。"""
        try:
            for win in self._pets_provider():
                if win is not None:
                    win._island_clamp_body = self._clamp_body
        except RuntimeError:
            pass  # 窗口已销毁

    def _clear_clamp_hooks(self) -> None:
        try:
            for win in self._pets_provider():
                if win is not None:
                    win._island_clamp_body = None
        except RuntimeError:
            pass

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._register_clamp_hooks()
        log.info("灵动岛碰撞体已启动（同步硬墙，无 30Hz 检测）")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._clear_clamp_hooks()
        log.info("灵动岛碰撞体已停止")

    def set_own_pet_visible(self, visible: bool) -> None:
        """本进程桌宠可见性回调（AppShell 接线保留）：本地版无挂起语义，
        仅留日志便于排查。"""
        log.debug("灵动岛碰撞体：本进程桌宠可见性=%s", bool(visible))

    def submit(self) -> None:
        """岛几何变化（拖拽/展开/停靠/归位）：岛是移动的墙，把此刻被它
        压住的桌宠经统一出口推出（岛动而桌宠没动的穿越；桌宠动时由同步墙挡）。

        事件驱动、无定时器；几何动画/细条态不推挤（与 _clamp_body 同口径）。
        """
        if not self._wall_active():
            return
        try:
            stadium = self._island_stadium()
        except Exception:
            return
        for win in self._pets_provider():
            try:
                if win is None or not win.isVisible():
                    continue
                if getattr(win, "_hidden_paused", False):
                    continue
                if getattr(win, "_physics_mode", "") == "drag" \
                        or getattr(win, "_interaction_state", "") == "DRAGGING":
                    continue  # 用户正在摆放这只，不抢位置
                sbr_fn = getattr(win, "_stable_body_local_rect", None)
                vp_fn = getattr(win, "_virtual_pos", None)
                mover = getattr(win, "_move_window_towards", None)
                if not callable(sbr_fn) or not callable(vp_fn) or not callable(mover):
                    continue
                vp = vp_fn()
                (_xi, _yi), moved, _n = self._compute_clamped(
                    stadium, float(vp.x()), float(vp.y()), sbr_fn())
                if moved:
                    # 经统一出口：_clamp_body 会钳出（抛掷中的桌宠一并反射速度）
                    mover(vp.x(), vp.y())
            except RuntimeError:
                continue  # 窗口已销毁
            except Exception:  # noqa: BLE001 - 单只异常不拖垮推挤循环
                log.warning("灵动岛推挤跳过异常桌宠", exc_info=True)

    # ------------------------------------------------------------ 几何
    def _wall_active(self) -> bool:
        """墙是否生效：运行中 + 岛可见 + 非细条态 + 非几何动画。"""
        if not self._running or not self._island.isVisible():
            return False
        if getattr(self._island, "_mode", "") == "docked" \
                and not getattr(self._island, "_hover_peek", False):
            return False  # 细条态不设墙（stadium 水平轴假设不成立）
        if getattr(self._island, "_geo_to", None) is not None:
            return False  # 展开/停靠/归位动画中几何在变，不设墙
        return True

    def _island_stadium(self) -> tuple[float, float, float, float, float]:
        """岛的体育场形：(axis_x0, axis_x1, axis_y, radius, rect_height)。

        展开卡片时只覆盖胶囊本体（卡片区域不设幽灵墙）。
        """
        rect = self._island.geometry()
        height = min(rect.height(), _CAPSULE_HEIGHT)
        radius = height / 2.0
        axis_y = rect.y() + radius
        return (rect.x() + radius, rect.x() + rect.width() - radius,
                axis_y, radius, height)

    @staticmethod
    def _axis_closest(stadium, px: float, py: float) -> tuple[float, float]:
        """胶囊轴线上离 (px, py) 最近的点。"""
        ax0, ax1, ay, _radius, _h = stadium
        return (min(max(px, ax0), ax1), ay)

    def _compute_clamped(
        self, stadium, xi: float, yi: float, sbr,
    ) -> tuple[tuple[float, float], bool, tuple[float, float]]:
        """把身体框推出岛碰撞区的虚拟左上；未越界时原样返回。

        返回 (钳制后的 (xi, yi), 是否发生了钳制, 墙法线 (nx, ny))。身体框屏幕
        位置 = 虚拟左上 + 身体框局部偏移；中心沿"轴最近点→中心"方向推出到
        (身体矩形径向半径 + 岛半径 + 1)。
        """
        ax0, ax1, ay, rr, _h = stadium
        body_left = xi + sbr.x()
        body_top = yi + sbr.y()
        cx = body_left + sbr.width() / 2.0
        cy = body_top + sbr.height() / 2.0
        rx = sbr.width() / 2.0
        ry = sbr.height() / 2.0
        closest_x = min(max(cx, ax0), ax1)
        dx, dy = cx - closest_x, cy - ay
        dist = math.hypot(dx, dy)
        if dist <= 1e-9:
            # 中心恰在轴上：沿 -y 推出（向上）
            nx, ny, radial = 0.0, -1.0, ry
        else:
            nx, ny = dx / dist, dy / dist
            radial = _rect_radial(rx, ry, nx, ny)
        if dist >= radial + rr:
            return (xi, yi), False, (0.0, 0.0)
        gap = radial + rr + 1.0
        target_cx = closest_x + nx * gap
        target_cy = ay + ny * gap
        return ((target_cx - sbr.width() / 2.0 - sbr.x(),
                 target_cy - sbr.height() / 2.0 - sbr.y()), True, (nx, ny))

    def _clamp_body(self, host, xi: float, yi: float, sbr) -> tuple[float, float]:
        """同步硬墙（move_window_towwards 调用的 hook）：把身体框钳出岛区。

        与屏幕边界同语义：身体框永远进不了岛区，只有这一个位置出口、没有
        30Hz 采样间隙，从根上杜绝"钻进→被弹→再钻回"的抽搐。

        抛掷中撞岛顺手把速度沿墙法线反射（口径同屏幕边缘 throw_step 的
        RESTITUTION）并钉住物理位置：纯钳制只挡位置会让物理空间穿过岛、视觉
        被钉在墙上直到落体结束——反射后才是真正的"像屏幕边缘一样"弹开。
        """
        if not self._wall_active():
            return xi, yi
        try:
            stadium = self._island_stadium()
        except Exception:
            return xi, yi
        (nx_pos, ny_pos), moved, (nx, ny) = self._compute_clamped(
            stadium, xi, yi, sbr)
        if not moved:
            return xi, yi
        if getattr(host, "_physics_mode", "") == "throw":
            vel = getattr(host, "_phys_vel", None)
            if isinstance(vel, list) and len(vel) >= 2:
                # 墙法线指向桌宠一侧：接近速度 vn<0 才反射；反射后法向分量
                # 反号，同一位置不会二次反射。e 用屏幕边缘同款 RESTITUTION。
                vn = vel[0] * nx + vel[1] * ny
                if vn < 0.0:
                    k = (1.0 + physics_mod.RESTITUTION) * vn
                    vel[0] -= k * nx
                    vel[1] -= k * ny
            phys = getattr(host, "_phys_pos", None)
            if isinstance(phys, list) and len(phys) >= 2:
                phys[:] = [float(nx_pos), float(ny_pos)]
        return nx_pos, ny_pos
