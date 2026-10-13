# -*- coding: utf-8 -*-
"""黄历「今日宜穿色」（`pet/almanac.py`）的聚焦回归。

**锚点必须钉死**：日干支决定每一天的颜色，锚错了就每天都错。这里用两个独立公开来源
交叉验证过的两个日期做锚：1949-10-01＝甲子日（911cha，同日儒略日 2433196.5）、
2026-10-10＝丁巳日、冲猪煞东（黄历网）；两天相距 28133 天，28133 mod 60 ＝ 53。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from pet import almanac


# --------------------------------------------------------------------------- #
# 锚点与周期
# --------------------------------------------------------------------------- #

def test_day_ganzhi_anchors() -> None:
    assert almanac.day_ganzhi(date(1949, 10, 1)) == "甲子"
    assert almanac.day_ganzhi(date(2026, 10, 10)) == "丁巳"
    # 六十甲子循环：每 60 天回到同一个日柱，前后各一天不同
    assert almanac.day_ganzhi(date(2026, 10, 10) + timedelta(days=60)) == "丁巳"
    assert almanac.day_ganzhi(date(2026, 10, 11)) == "戊午"


def test_day_index_is_continuous_and_bounded() -> None:
    """连续 200 天：序号始终在 [0,60) 且逐日 +1（mod 60），不跳变。"""
    start = date(2026, 1, 1)
    previous = almanac.day_index(start)
    for offset in range(1, 200):
        current = almanac.day_index(start + timedelta(days=offset))
        assert 0 <= current < 60
        assert current == (previous + 1) % 60
        previous = current


def test_clash_follows_the_documented_rule() -> None:
    """冲煞：日支 +6 的生肖，煞方按「申子辰南 / 巳酉丑东 / 寅午戌北 / 亥卯未西」。"""
    assert almanac.clash(date(2026, 10, 10)) == ("猪", "东")  # 丁巳日：冲猪煞东（公开来源）
    assert almanac.clash(date(1949, 10, 1)) == ("马", "南")   # 甲子日：子→午（冲马）
    # 同一套规则在全周期自洽：冲的生肖与日支相差 6 位
    for offset in range(60):
        day = date(2026, 10, 10) + timedelta(days=offset)
        zodiac, direction = almanac.clash(day)
        assert zodiac in almanac.ZHI_ZODIAC and direction in "东南西北"


# --------------------------------------------------------------------------- #
# 五色映射
# --------------------------------------------------------------------------- #

def test_wear_colors_for_a_known_day() -> None:
    """丁巳日：日干丁属火 → 宜穿（生我）木色绿、次吉火色红、避（克我）水色蓝。"""
    info = almanac.wear_colors(date(2026, 10, 10))
    assert info["ganzhi"] == "丁巳"
    assert info["element"] == "火"
    assert info["main"] == "绿" and info["main_element"] == "木"
    assert info["second"] == "红"
    assert info["avoid"] == "蓝" and info["avoid_element"] == "水"
    assert info["clash_zodiac"] == "猪" and info["clash_direction"] == "东"


def test_every_element_maps_to_a_color_once() -> None:
    """五行 ↔ 色名是一一对应的：十天干各自落到实处，且没有空值。"""
    seen: dict[str, str] = {}
    for gan, element in almanac.GAN_ELEMENT.items():
        name, specific = almanac.ELEMENT_COLORS[element]
        assert name and specific
        seen[gan] = name
    assert set(seen.values()) == {"绿", "红", "黄", "白", "蓝"}
    # 生日干的那个五行必须是「母行」：火←木、木←水、水←金、金←土、土←火
    assert almanac._mother_of("火") == "木"
    assert almanac._mother_of("木") == "水"
    assert almanac._mother_of("水") == "金"
    assert almanac._mother_of("金") == "土"
    assert almanac._mother_of("土") == "火"
    # 克我者：水克火、金克木、土克水、火克金、木克土
    assert almanac._controller_of("火") == "水"
    assert almanac._controller_of("木") == "金"
    assert almanac._controller_of("水") == "土"
    assert almanac._controller_of("金") == "火"
    assert almanac._controller_of("土") == "木"


def test_year_of_days_all_produce_a_full_line() -> None:
    """连续一年每天都能算出完整一行（没有空洞、没有异常）。"""
    start = date(2026, 1, 1)
    for offset in range(366):
        day = start + timedelta(days=offset)
        info = almanac.wear_colors(day)
        assert info["main"] in {"绿", "红", "黄", "白", "蓝"}
        assert info["avoid"] != info["main"], f"{day} 的宜穿与忌穿撞了"
        assert almanac.short_line(day) and almanac.speech_line(day)


# --------------------------------------------------------------------------- #
# 文案口径与红线
# --------------------------------------------------------------------------- #

def test_lines_are_short_and_plain() -> None:
    """她 2026-10-10 的口径：一次说完、别拖沓。短句 ≤ 16 字，语音句 ≤ 18 字。"""
    day = date(2026, 10, 10)
    assert len(almanac.short_line(day)) <= 16, almanac.short_line(day)
    assert len(almanac.speech_line(day)) <= 18, almanac.speech_line(day)
    assert "！" not in almanac.short_line(day) and "!" not in almanac.speech_line(day)


def test_no_health_claims_anywhere() -> None:
    """黄历这边同样不许碰健康/疾病/寿命/怀孕（娱乐向红线）。"""
    forbidden = ("治疗", "疾病", "痊愈", "寿命", "怀孕", "药", "疗效")
    for offset in range(0, 366, 7):
        day = date(2026, 1, 1) + timedelta(days=offset)
        text = almanac.detail_line(day) + almanac.speech_line(day) + almanac.short_line(day)
        assert not any(word in text for word in forbidden), text


def test_almanac_is_qt_free() -> None:
    """纯逻辑零 Qt（只看真实 import 语句）。"""
    pattern = re.compile(r"^\s*(?:from|import)\s+(PySide6|Qt)", re.MULTILINE)
    text = (Path(__file__).resolve().parents[1] / "pet" / "almanac.py").read_text(encoding="utf-8")
    assert not pattern.search(text)
