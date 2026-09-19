# -*- coding: utf-8 -*-
"""移动驱动的纯逻辑（无 Qt）：纵向漫游目标与朝向判定。

规则单一事实来源：朝向由「移动目标 + 屏幕位置」决定，与随机数无关——
随机只用来挑方向（两侧都够得着时）和步长。RNG 一律可注入，便于钉死分支。
"""

from __future__ import annotations

import random

__all__ = ["body_reach", "choose_move_direction", "inward_facing", "wander_target_y"]


def wander_target_y(
    start_y: float,
    top: float,
    bottom: float,
    height: float,
    margin: float,
    rnd=random,
) -> int:
    """Pick a bounded vertical wander target; injectable RNG keeps it testable."""
    y_lo = top + margin
    y_hi = bottom - height - margin
    if y_hi <= y_lo:
        return int(start_y)
    max_dy = max(40, int((y_hi - y_lo) * 0.25))
    return int(max(y_lo, min(y_hi, start_y + rnd.randint(-max_dy, max_dy))))


def body_reach(
    avail_left: float,
    avail_right: float,
    body_left: float,
    body_width: float,
    margin: float,
) -> tuple[float, float, float]:
    """身体框中心的可达界：返回 (cx, left_bound, right_bound)。

    漫游空间按角色身体框算（虚拟窗口坐标）——身体不越出工作区，不用
    "窗口中心 + _w/2"这类画布经验值。可达界含 margin 安全边距与身体半宽，
    即身体框中心允许落到的端点；两侧剩余空间 = |cx - 对应 bound|。
    """
    half_w = body_width / 2
    return (body_left + half_w,
            avail_left + margin + half_w,
            avail_right - margin - half_w)


def choose_move_direction(
    cx: float,
    left_bound: float,
    right_bound: float,
    min_distance: float,
    rnd=random,
) -> int | None:
    """按边缘可达性挑移动方向：-1 左 / +1 右 / None 两侧都走不了。

    先算两侧剩余空间，够 min_distance 才算「可达」（含等号）。单侧可达 →
    该侧（不掷骰）；两侧可达 → rnd.choice 二选一；都不可达 → None，调用方
    据此拒绝建立移动计划（边缘可达性闸门，替代此前的「先取朝向再算出界」）。
    """
    if cx - left_bound >= min_distance and right_bound - cx >= min_distance:
        return rnd.choice([-1, 1])
    if cx - left_bound >= min_distance:
        return -1
    if right_bound - cx >= min_distance:
        return 1
    return None


def inward_facing(
    cx: float,
    avail_left: float,
    avail_right: float,
    ratio: float = 0.07,
) -> str | None:
    """偏离中线超过滞回带时返回应朝的内侧方向，带内返回 None。

    滞回带 = 可用区间宽 × ratio，用于避免角色在中线附近反复翻转朝向。
    """
    center = (avail_left + avail_right) / 2
    band = (avail_right - avail_left) * ratio
    if cx < center - band:
        return "right"
    if cx > center + band:
        return "left"
    return None
