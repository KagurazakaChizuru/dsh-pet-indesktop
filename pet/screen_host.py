# -*- coding: utf-8 -*-
"""多屏承载：一屏一个宿主（一张 overlay + 一份屏局部仿真控制器）。

契约（2026-10-15 用户口径）：每只宠各自独立地放在任意显示器上；进程、tick
时钟与共享服务仍只有一份，被占用的显示器各有一张 overlay。

sprite 坐标是 **overlay 局部坐标**（= 全局 - 该屏原点，见
``OverlayShell._local_bounds``）。两块屏上局部坐标相同的两只宠在桌面上相距上千
像素，因此：

- 行为控制器的活动边界（漫游/落位钳制）必须逐屏一份，否则副屏的宠会被主屏的
  可用区钳制；
- 碰撞世界必须逐屏一份——共用一个 ``SpriteCollisionWorld`` 会把两块屏上同局部
  坐标的宠判成接触（假碰撞），去抖/扫掠/成员状态也会跨屏串味；
- 抛掷物理边界、边缘探头、抛掷彩蛋同 bounds，逐屏一份。

本类只回答"这块屏上画什么、这块屏上怎么算"。窗口能力、气泡、菜单、托盘、音效、
联动、监视器、素材库等进程级面仍归 ``OverlayShell``（共享面绝不复刻）。
"""

from __future__ import annotations

from PySide6.QtCore import QRect

from .sprite_behavior import BehaviorController
from .sprite_collision import SpriteCollisionWorld
from .sprite_physics import ThrowPhysicsController


class ScreenHost:
    """一块屏的绘制 + 仿真宿主：overlay、屏局部可用区与一份控制器组。"""

    def __init__(self, screen, overlay, bounds: QRect) -> None:
        self.screen = screen
        self.overlay = overlay
        self.bounds = QRect(bounds)
        # 屏局部仿真：行为（漫游/落位边界）→ 碰撞（本屏成员）→ 抛掷物理（本屏边界）
        self.behavior = BehaviorController(self.bounds)
        self.collision = SpriteCollisionWorld()
        self.physics = ThrowPhysicsController(self.bounds)
        # 附加仿真控制器（tick 尾段，顺序即列表序：边缘探头先、抛掷彩蛋后）；
        # 都是几何绑定的，逐屏一份
        self.extras: list = []
        self.probe = None
        self.throw_egg = None
        self.feeding = None
        # overlay 反查宿主：驱动器的分组仿真与鼠标路由都从这里取
        overlay.host = self
        overlay.behavior = self.behavior  # contextMenuEvent 查表点

    @property
    def sprites(self) -> list:
        """本屏当前承载的 sprite（overlay 有序表即 z-order）。"""
        return list(self.overlay.sprites)

    def tick(self, dt: float) -> None:
        """本屏一轮仿真：行为 → 碰撞 → 物理 → 附加控制器（顺序协议同 M-2）。"""
        sprites = list(self.overlay.sprites)
        self.behavior.tick(sprites, dt)
        self.collision.tick(sprites, dt)
        self.physics.tick(sprites, dt)
        for ctrl in list(self.extras):
            ctrl.tick(sprites, dt)

    def set_bounds(self, bounds: QRect) -> None:
        """换本屏可用区（同屏几何/任务栏变化）：控制器与全部成员一起换域。"""
        self.bounds = QRect(bounds)
        self.behavior.bounds = QRect(bounds)
        self.physics.set_bounds(bounds)
        for sprite in self.overlay.sprites:
            sprite.set_bounds(QRect(bounds))
        for ctrl in (self.probe, self.throw_egg):
            if ctrl is not None:
                ctrl.set_bounds(QRect(bounds))

    def __repr__(self) -> str:  # pragma: no cover - 诊断用
        try:
            name = str(self.screen.name())
        except Exception:
            name = "?"
        return (f"<ScreenHost {name} bounds={self.bounds.x()},{self.bounds.y()}"
                f",{self.bounds.width()}x{self.bounds.height()}"
                f" sprites={len(self.overlay.sprites)}>")
