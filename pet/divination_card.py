# -*- coding: utf-8 -*-
"""上上签卡：把一支签画成一张 PNG（纯 PIL，不用 Qt）。

第四轮加的。只在抽到「上上」时落一张到桌面——4% 的概率，稀有才有意思；
渲染失败只记日志，绝不影响抽签本身。
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
_POEM = (226, 214, 190)
_PLAIN = (238, 232, 218)
_TAIL = (198, 186, 164)
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


def render_card(stick: dict, path: Path) -> Path:
    """画一张签卡并保存；返回落盘路径。"""
    from PIL import Image, ImageDraw

    title_font, body_font, small_font = _font(34), _font(22), _font(18)
    image = Image.new("RGB", (760, 420), _CARD_BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((14, 14, 746, 406), radius=16, outline=_CARD_BORDER, width=2)
    draw.text((46, 40), f"第 {stick['no']} 签 · {stick['level']}", font=title_font, fill=_TITLE)
    y = 110
    for line in stick.get("poem", ()):
        draw.text((46, y), str(line), font=body_font, fill=_POEM)
        y += 36
    draw.line((46, y + 10, 714, y + 10), fill=(96, 78, 52), width=1)
    draw.text((46, y + 30), str(stick.get("plain", "")), font=body_font, fill=_PLAIN)
    draw.text((46, y + 78), f"宜 {stick.get('good', '')}　·　忌 {stick.get('bad', '')}",
              font=small_font, fill=_TAIL)
    draw.text((46, y + 120), f"{date.today().isoformat()}　签是抽的，怎么做还是你定。",
              font=small_font, fill=_FOOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
