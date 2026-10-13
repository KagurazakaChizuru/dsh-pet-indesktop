# -*- coding: utf-8 -*-
"""上上签卡：把一支签画成一张 PNG（纯 PIL，不用 Qt）。

第四轮加的。只在抽到「上上」时落一张到桌面——4% 的概率，稀有才有意思；
渲染失败只记日志，绝不影响抽签本身。

甲形态（2026-10-13）起版式跟着签文走：签头带四字典故签题、签诗两句七言，
**不再印黄历那两行**（签不再承担"今天该干什么"的分工，见 ``pet/divination_quotes.py``
的口径）。要画出来的文本统一由 :func:`card_texts` 给出，用例断言它而不是去读源码。
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

#: 字体候选（Windows 自带；本机实测 msyh 一定在）。
_FONTS = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
)

_CARD_BG = (22, 20, 18)
_CARD_BORDER = (120, 96, 60)
_TITLE = (240, 226, 196)
_TITLE_ALT = (214, 190, 148)
_POEM = (226, 214, 190)
_PLAIN = (238, 232, 218)
_FOOT = (132, 120, 100)


def _font(size: int):
    from PIL import ImageFont

    for candidate in _FONTS:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
    return ImageFont.load_default()


def card_texts(stick: dict, day: date | None = None) -> list[str]:
    """签卡上会画出来的全部文本：签头 / 签题 / 签诗两句 / 解曰 / 页脚。

    版式改动就改这里——``render_card`` 只负责把这些字符串摆到坐标上，
    所以用例可以断言"卡上到底印了什么"，不必去 grep 源码。
    """
    return [
        f"第 {stick['no']} 签 · {stick['level']}",
        f"〔{stick.get('title', '')}〕",
        *[str(line) for line in stick.get("poem", ())],
        str(stick.get("plain", "")),
        f"{(day or date.today()).isoformat()}　签是抽的，怎么做还是你定。",
    ]


def render_card(stick: dict, path: Path) -> Path:
    """画一张签卡并保存；返回落盘路径。"""
    from PIL import Image, ImageDraw

    title_font, name_font, body_font, small_font = _font(32), _font(26), _font(23), _font(18)
    head, name, *poem, plain, foot = card_texts(stick)
    image = Image.new("RGB", (760, 420), _CARD_BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((14, 14, 746, 406), radius=16, outline=_CARD_BORDER, width=2)
    draw.text((46, 44), head, font=title_font, fill=_TITLE)
    draw.text((46, 102), name, font=name_font, fill=_TITLE_ALT)
    y = 156
    for line in poem:
        draw.text((46, y), line, font=body_font, fill=_POEM)
        y += 40
    draw.line((46, y + 14, 714, y + 14), fill=(96, 78, 52), width=1)
    draw.text((46, y + 38), plain, font=body_font, fill=_PLAIN)
    draw.text((46, 344), foot, font=small_font, fill=_FOOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
