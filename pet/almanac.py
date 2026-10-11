# -*- coding: utf-8 -*-
"""黄历「今日宜穿什么颜色」的纯逻辑层（零 Qt、零 IO、零网络）。

依据与口径
----------
**颜色只来自一个硬依据：当日日柱天干的五行**（其余黄历条目——宜嫁娶/忌动土之类——各版本
互相矛盾，本模块一律不编）。规则用五行生克：

* **宜穿＝生我者**（印，母行）的颜色：例日干属火 → 木色（青绿、墨绿、竹青）
* **次吉＝同我者**（比）的颜色：火色（朱红、酒红、紫）
* **避＝克我者**（官杀）的颜色：水色（藏青、深蓝、墨黑）
* 附带**冲煞**：日支相冲的生肖与煞方（申子辰煞南 / 寅午戌煞北 / 巳酉丑煞东 / 亥卯未煞西）

锚点（2026-10-10 用两个独立公开来源交叉验证，**不要凭记忆改**）
------------------------------------------------------------
* `911cha` 1949-10-01 ＝ **己丑年 癸酉月 甲子日**，同日儒略日 2433196.5；
* `黄历网` 2026-10-10 ＝ **丙午年 戊戌月 丁巳日**、冲猪煞东。
* 两天相距 28133 天，28133 mod 60 ＝ 53；甲子(idx 0) 顺数 53 位 = 丁巳 ✓ 与第二个来源一致，
  冲煞方向也与「巳酉丑煞东」的规则一致。
日干支是**连续六十甲子**，与节气/农历无关，所以只需这一个锚点，1800–2200 年内都成立。
"""

from __future__ import annotations

from datetime import date

#: 天干、地支。
GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"

#: 地支 → 生肖 / 方位。
ZHI_ZODIAC = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")
ZHI_DIRECTION = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")

#: 天干 → 五行。
GAN_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}

#: 五行相生：A 生 B。
GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
#: 五行相克：A 克 B。
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

#: 五行 → (主色名, 具体衣着色, 该行的颜色一句话)。
ELEMENT_COLORS: dict[str, tuple[str, str]] = {
    "木": ("青绿", "墨绿、竹青、橄榄绿"),
    "火": ("朱红", "酒红、紫、橙"),
    "土": ("姜黄", "驼色、卡其、棕"),
    "金": ("象牙白", "银灰、香槟金"),
    "水": ("藏青", "深蓝、墨黑、灰蓝"),
}

#: 六十甲子锚点：1949-10-01 是甲子日（见模块头注释的两个来源）。
_ANCHOR = date(1949, 10, 1)
_ANCHOR_INDEX = 0


def day_index(day: date) -> int:
    """该日的六十甲子序号（0 = 甲子）。日干支是连续六十甲子，纯算术。"""
    return (_ANCHOR_INDEX + (day - _ANCHOR).days) % 60


def day_ganzhi(day: date) -> str:
    """日柱干支，如 ``丁巳``。"""
    index = day_index(day)
    return GAN[index % 10] + ZHI[index % 12]


def day_element(day: date) -> str:
    """日干五行（本模块唯一的颜色依据）。"""
    return GAN_ELEMENT[GAN[day_index(day) % 10]]


def _mother_of(element: str) -> str:
    """生 element 的那个五行（印/母行）。"""
    return next(source for source, target in GENERATES.items() if target == element)


def _child_of(element: str) -> str:
    """element 所生的五行（泄/子行）。"""
    return GENERATES[element]


def _controller_of(element: str) -> str:
    """克 element 的那个五行（官杀）。"""
    return next(source for source, target in CONTROLS.items() if target == element)


def clash(day: date) -> tuple[str, str]:
    """当日冲煞：``(生肖, 煞方)``。

    * **冲的生肖**由「日支 +6」定（子↔午、丑↔未…）；
    * **煞方按日支自己的三合局**：申子辰煞南 / 巳酉丑煞东 / 寅午戌煞北 / 亥卯未煞西
      （地支序号 mod 4 正好分成这四组：0=南、1=东、2=北、3=西）。
      两个已核对的例：2026-10-10 丁巳日 → 冲猪煞东；1949-10-01 甲子日 → 冲马煞南。
    """
    zhi_index = day_index(day) % 12
    opposed = (zhi_index + 6) % 12
    direction = {0: "南", 1: "东", 2: "北", 3: "西"}[zhi_index % 4]
    return ZHI_ZODIAC[opposed], direction


def wear_colors(day: date) -> dict:
    """当日穿衣色：主推 / 次吉 / 避 / 冲煞（全部由日柱推出）。"""
    element = day_element(day)
    main_element = _mother_of(element)
    avoid_element = _controller_of(element)
    main_name, main_specific = ELEMENT_COLORS[main_element]
    second_name, second_specific = ELEMENT_COLORS[element]
    avoid_name, avoid_specific = ELEMENT_COLORS[avoid_element]
    zodiac, direction = clash(day)
    return {
        "ganzhi": day_ganzhi(day),
        "element": element,
        "main_element": main_element,
        "main": main_name,
        "main_specific": main_specific,
        "second": second_name,
        "second_specific": second_specific,
        "avoid_element": avoid_element,
        "avoid": avoid_name,
        "avoid_specific": avoid_specific,
        "clash_zodiac": zodiac,
        "clash_direction": direction,
        "flat_element": _child_of(element),
    }


def short_line(day: date) -> str:
    """气泡用的一行（**必须短**，她 2026-10-10 的口径：一次说完、别拖沓）。"""
    info = wear_colors(day)
    return f"今日宜穿 {info['main']} · 避 {info['avoid']}"


def speech_line(day: date) -> str:
    """语音用的一句（一句话念完）。"""
    info = wear_colors(day)
    return f"今日宜穿{info['main']}，避{info['avoid']}。"


def detail_line(day: date) -> str:
    """完整一行（设置页/调试用；气泡里不放这么长）。"""
    info = wear_colors(day)
    return (f"{info['ganzhi']}日（{info['element']}）· 宜穿 {info['main']}"
            f"（{info['main_specific']}）· 次吉 {info['second']}"
            f"· 避 {info['avoid']}（{info['avoid_specific']}）"
            f"· 冲{info['clash_zodiac']}煞{info['clash_direction']}")
