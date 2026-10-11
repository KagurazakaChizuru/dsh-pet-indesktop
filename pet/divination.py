# -*- coding: utf-8 -*-
"""抽签的纯逻辑层：**抽哪一支 + 怎么念**（零 Qt、零 IO、零网络）。

与 ``pet/fortune.py``（已按机主决定归档）的分工口径一致：

* 抽签是**用户主动触发**的一次性动作，**真随机**——不挂日期种子。
  「今天固定一签」那种设计会让第二次点击没有反应，抽签要的就是"抽"的手感；
  想复现某一支签，用 :func:`draw` 的 ``rng`` 注入（用例就这么测）。
* 吉凶按 :data:`pet.divination_quotes.LEVEL_WEIGHTS` **加权**抽（上上少见、
  中平最多），档内**均匀**抽一支。
* 气泡恒四行以内、语音一句话念完（她 2026-10-10 的反馈：文案别拖沓）。
* 文本里**不出现感叹号**，不预测健康/疾病/寿命/怀孕（同名用例守卫）。
"""

from __future__ import annotations

import random
from datetime import date

from . import almanac
from . import divination_quotes as quotes

#: 抽签配置（只有两个开关，**不含任何个人信息**——这是它与已归档的占星功能最大的区别）。
DEFAULT_DIVINATION_CONFIG: dict[str, bool] = {
    "speak": True,       # 抽到签时用语音报时的音色念出来
    "animation": True,   # 抽签时播一个摇签动作（角色动作池里有才播）
}


def normalize_divination_config(config) -> dict:
    """把 config（或扁平 dict）清洗成 :data:`DEFAULT_DIVINATION_CONFIG` 的形状。

    非法值一律回落默认，**绝不抛异常**（服务层在点击路径上用它）。
    """
    getter = getattr(config, "get", None)

    def value(key: str) -> bool:
        if callable(getter):
            raw = getter(f"divination_{key}", DEFAULT_DIVINATION_CONFIG[key])
            return DEFAULT_DIVINATION_CONFIG[key] if raw is None else bool(raw)
        return DEFAULT_DIVINATION_CONFIG[key]

    return {key: value(key) for key in DEFAULT_DIVINATION_CONFIG}


def _pools() -> dict[str, tuple[dict, ...]]:
    """按吉凶分桶（签库是常量，这里只读不缓存，避免多一份状态）。"""
    pools: dict[str, list[dict]] = {level: [] for level in quotes.LEVELS}
    for stick in quotes.STICKS:
        pools.setdefault(str(stick["level"]), []).append(stick)
    return {level: tuple(items) for level, items in pools.items()}


def draw(rng: random.Random | None = None, exclude: object = ()) -> dict:
    """抽一支签：先按权重定吉凶，再在该档里均匀取一支。

    ``rng`` 可注入（用例用 ``random.Random(seed)`` 断言确定结果）；不传就走系统熵。

    ``exclude`` ＝**这一轮已经抽到过的签号**（第四轮加：她反馈"完善"缺的一环——连着抽几把
    撞到同一支体验差）。排除后某一档空了，该档就不参与加权；整副签都抽完了，
    ``exclude`` 自动作废（开新一轮），调用方不用自己判。
    """
    picker = rng if rng is not None else random.Random()
    drawn = {int(no) for no in exclude} if exclude else set()
    pools = _pools()
    if drawn:
        filtered = {level: tuple(s for s in items if int(s["no"]) not in drawn)
                    for level, items in pools.items()}
        if any(filtered.values()):
            pools = filtered
    levels = [level for level in quotes.LEVELS if pools.get(level)]
    weights = [quotes.LEVEL_WEIGHTS.get(level, 1) for level in levels]
    level = picker.choices(levels, weights=weights, k=1)[0]
    return dict(picker.choice(pools[level]))


def total_sticks() -> int:
    """签库总数（服务层用它判断一轮是否抽完）。"""
    return len(quotes.STICKS)


def stick_title(stick: dict) -> str:
    """签头：``第 7 签 · 上``。"""
    return f"第 {stick['no']} 签 · {stick['level']}"


def bubble_text(stick: dict, day: date | None = None) -> str:
    """气泡五行：签头 / 签诗 / 白话解 / 宜忌 / **今日宜穿色**（黄历）。

    穿衣色与签无关——它只由**当天日柱天干的五行**推出（见 ``pet/almanac.py``），
    所以同一天抽几次都是同一句；这是机主 2026-10-10 定的口径「合并进抽签」：
    点一次拿两样，不为它单开入口。
    """
    poem = "".join(str(line) for line in stick.get("poem", ()))
    plain = str(stick.get("plain", ""))
    tail = f"宜 {stick['good']} · 忌 {stick['bad']}"
    color = almanac.short_line(day or date.today())
    return "\n".join([stick_title(stick), poem, plain, tail, color])


def speech_text(stick: dict, day: date | None = None) -> str:
    """语音一句念完：``第 7 签，上。…。宜 …，忌 …。今日宜穿X，避Y。``"""
    color = almanac.speech_line(day or date.today())
    return (f"{stick_title(stick).replace(' · ', '，')}。"
            f"{stick.get('plain', '')}"
            f"宜 {stick['good']}，忌 {stick['bad']}。"
            f"{color}")


def speech_title(stick: dict) -> str:
    """桌面通知/日志用的短标题。"""
    return f"第 {stick['no']} 签 · {stick['level']}"
