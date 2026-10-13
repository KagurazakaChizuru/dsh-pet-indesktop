# -*- coding: utf-8 -*-
"""抽签的纯逻辑层：**抽哪一支 + 怎么念**（零 Qt、零 IO、零网络）。

两条取签路径：

* :func:`draw` —— **真随机**，摇签的手感（可注入 ``rng`` 复现，用例靠它断言）；
* :func:`daily_draw` —— **按日期确定性取"今日签"**（机主 2026-10-13 定的口径：
  「抽签每天只能抽一次」）。它不 import ``random``：日期 → splitmix64 → 下标，
  同一个日期在任何进程、任何解释器版本上都是同一支签；跨天分布均匀，且**不是**
  "按日洗牌取头一个"那种小池子上会退化成 A/B 交替的写法。

其余口径：

* 吉凶按 :data:`pet.divination_quotes.LEVEL_WEIGHTS` **加权**取（上上少见、
  中平最多），档内**均匀**；有 :func:`daily_draw` 的 ``recent``（跨天"一轮不重复"）
  时，被排除的签不参与，档空了就换下一支（仍同日恒定）。
* 气泡恒五行（甲形态：签头含签题 / 七言上句 / 七言下句 / 解曰 / 宜穿色），
  语音一句话念完（她 2026-10-10 的反馈：文案别拖沓）。
* 文本里**不出现感叹号**，不预测健康/疾病/寿命/怀孕（同名用例守卫）。
"""

from __future__ import annotations

import random
from datetime import date, timedelta

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


# --------------------------------------------------------------------------- #
# 今日签：按日期确定性取号（第五轮，2026-10-13）
# --------------------------------------------------------------------------- #

#: 混入日期序数的盐（splitmix64 常数；刻意自带、不 import random——见模块 docstring）。
_DAY_SALT = 0x9E3779B97F4A7C15
_SALT_FALLBACK = 0x94D049BB133111EB
_DAY_MUL = 1000003
_MIX_A = 0xBF58476D1CE4E5B9
_MIX_B = 0x94D049BB133111EB
_MASK64 = (1 << 64) - 1
_U32_LIMIT = 1 << 32

#: 「一轮不重复」的回看天数（第五轮口径：跨天尽量避开最近抽过的，同日恒定）。
RECENT_DAYS = 7


def splitmix64(value: int) -> int:
    """splitmix64 混合（自带、纯算术）：雪崩性好，连续输入不会出交替规律。"""
    state = (value * _DAY_SALT) & _MASK64
    state = ((state ^ (state >> 30)) * _MIX_A) & _MASK64
    state = ((state ^ (state >> 27)) * _MIX_B) & _MASK64
    return (state ^ (state >> 31)) & _MASK64


def _uniform(day: date, total: int, salt: int) -> int:
    """``[0, total)`` 上的确定性均匀下标（拒绝采样，避免取模偏置）。"""
    limit = _U32_LIMIT - _U32_LIMIT % total
    step = 0
    while True:
        value = splitmix64(day.toordinal() * _DAY_MUL + salt + step) & 0xFFFFFFFF
        if value < limit:
            return value % total
        step += 1


def _tier_index(day: date, salt: int) -> int:
    """按权重定的档位下标；权重和不为 100 也成立（区间归一）。"""
    total = sum(quotes.LEVEL_WEIGHTS.get(level, 1) for level in quotes.LEVELS) or 1
    draw_at = _uniform(day, total, salt)
    for index, level in enumerate(quotes.LEVELS):
        weight = quotes.LEVEL_WEIGHTS.get(level, 1)
        if draw_at < weight:
            return index
        draw_at -= weight
    return len(quotes.LEVELS) - 1


def _daily_index(day: date, recent: frozenset[int]) -> int:
    """日期 → 签下标（``recent`` 里的签号不参与）。

    同一档里若全被 ``recent`` 占满，就换下一档；整副都占满（48 支全在回看窗口里，
    正常不会发生）则退回最近一支。两条路径都用**当天固定的**确定性子序列，
    所以同一天调用多少次都是同一支。
    """
    pools = _pools()
    for offset in range(len(quotes.LEVELS)):
        level = quotes.LEVELS[(_tier_index(day, _DAY_SALT) + offset) % len(quotes.LEVELS)]
        items = pools.get(level) or ()
        candidates = [stick for stick in items if int(stick["no"]) not in recent]
        if candidates:
            return int(candidates[_uniform(day, len(candidates), _DAY_SALT)]["no"])
    return int(quotes.STICKS[_uniform(day, len(quotes.STICKS), _SALT_FALLBACK)]["no"])


def daily_draw(day: date, recent: object = ()) -> dict:
    """**今日签**：同一个 ``day`` 永远同一支；换一天按权重均匀换一支。

    ``recent`` ＝最近的签号（服务层给的是"最近 ``RECENT_DAYS`` 天抽过的"），
    落在里面的签当天不取（"一轮不重复"的跨天形态）。被排除的档当天权重会让给
    下一档——``recent`` 为空时分布严格等于 :data:`pet.divination_quotes.LEVEL_WEIGHTS`。
    """
    numbers = {int(no) for no in recent} if recent else set()
    number = _daily_index(day, frozenset(numbers))
    # 按签号取（不按下标）：签库被改小/号被拆走时也不抛，退回确定性兜底号。
    for stick in quotes.STICKS:
        if int(stick["no"]) == number:
            return dict(stick)
    return dict(quotes.STICKS[_uniform(day, len(quotes.STICKS), _SALT_FALLBACK)])


def recent_days(day: date, days: int = RECENT_DAYS) -> list[date]:
    """``day`` 之前的 ``days`` 天（不含当天，旧 → 新）：服务层据此凑 ``recent``。"""
    return [day - timedelta(days=offset) for offset in range(days, 0, -1)]


def total_sticks() -> int:
    """签库总数（服务层用它判断一轮是否抽完）。"""
    return len(quotes.STICKS)


def stick_title(stick: dict) -> str:
    """签头：``第 7 签 · 上``。"""
    return f"第 {stick['no']} 签 · {stick['level']}"


def bubble_text(stick: dict, day: date | None = None, note: str = "") -> str:
    """气泡**恒五行**：签头（含签题）/ 七言上句 / 七言下句 / 解曰 / **今日宜穿色**。

    甲形态（机主 2026-10-13 拍板「抽签做甲方案」）＝四字典故签题 + 两句七言签诗 +
    一句解曰（≤14 字）。本轮去掉宜/忌后空出一行，**签题就排进签头**：
    ``第 7 签 · 上 · 渭水垂钓``——四档签头一行看全，剩下三行正好是签诗两句 + 解曰。
    这样做是为了给第五行让位：穿衣色与签无关，它只由**当天日柱天干的五行**推出
    （见 ``pet/almanac.py``），同一天抽几次都是同一句；那是机主 2026-10-10 定的口径
    「合并进抽签」——点一次拿两样，不为它单开入口（她要的是"签是另外一部分"，
    而不是"签里再塞黄历"：宜忌已经还给黄历，穿色行是既有的合入口径，保留）。

    ``note`` 是"今天已经抽过啦"这类一句提醒（每日一签加）：插在穿色行之前，
    前三行（签头/上句/下句）与解曰**一字不改**（重复点只多一行，契约用例守着）。
    """
    poem = [str(line) for line in stick.get("poem", ())]
    plain = str(stick.get("plain", ""))
    color = almanac.short_line(day or date.today())
    lines = [_head_line(stick), *poem, plain]
    if note:
        lines.append(str(note))
    lines.append(color)
    return "\n".join(lines)


def _head_line(stick: dict) -> str:
    """签头行：有签题时排成 ``第 7 签 · 上 · 渭水垂钓``（签题空则退回纯签头）。"""
    title = str(stick.get("title", "") or "")
    return f"{stick_title(stick)} · {title}" if title else stick_title(stick)


def speech_text(stick: dict, day: date | None = None) -> str:
    """语音一句念完：``第 7 签，上。渭水垂钓。…，…。解曰。今日宜穿X，避Y。``

    签题与签诗都念——甲形态的重点就是这两句七言，只听解曰不成签。
    """
    color = almanac.speech_line(day or date.today())
    title = str(stick.get("title", "") or "")
    poem = "".join(str(line) for line in stick.get("poem", ()))
    lead = f"{title}。" if title else ""
    return (f"{stick_title(stick).replace(' · ', '，')}。"
            f"{lead}"
            f"{poem}"
            f"{stick.get('plain', '')}"
            f"{color}")


def speech_title(stick: dict) -> str:
    """桌面通知/日志用的短标题。"""
    return f"第 {stick['no']} 签 · {stick['level']}"
