# -*- coding: utf-8 -*-
"""edge-tts provider：微软在线音色，免 Key，默认作为后备后端。

依赖 ``edge_tts``（可选依赖）：模块顶层**只做 find_spec 探测**，真正的 import 推迟到
``synth()``——首次 import 实测 ~1.4s 且常驻内存，而语音报时默认关闭，顶层 import
等于让每个用户白付这笔钱。
"""

from __future__ import annotations

import asyncio
import importlib.util

from .base import TtsField, TtsProvider, TtsUnavailable, register

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = 0  # 语速偏移（%），范围约 -100 ~ +100
DEFAULT_PITCH = 0  # 音调偏移（Hz），范围约 -50 ~ +50
AVAILABILITY_CODE = "edge-tts-missing"
MISSING_MESSAGE = "语音报时需要 edge-tts 库：请运行 pip install edge-tts 后重试"

# 中英文音色下拉列表（value=音色名，label=友好中文标签）。
VOICE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("zh-CN-XiaoxiaoNeural", "晓晓（女 · 自然）"),
    ("zh-CN-XiaoyiNeural", "晓伊（女 · 活泼）"),
    ("zh-CN-YunjianNeural", "云健（男 · 浑厚）"),
    ("zh-CN-YunxiNeural", "云希（男 · 阳光）"),
    ("zh-CN-YunyangNeural", "云扬（男 · 新闻播报）"),
    ("zh-CN-XiaochenNeural", "晓辰（女 · 电台）"),
    ("zh-CN-XiaohanNeural", "晓涵（女 · 温柔）"),
    ("zh-CN-XiaomengNeural", "晓梦（女 · 甜美）"),
    ("zh-CN-XiaomoNeural", "晓墨（女 · 知性）"),
    ("zh-CN-XiaoqiuNeural", "晓秋（女 · 柔和）"),
    ("zh-CN-XiaoruiNeural", "晓睿（女 · 老人音）"),
    ("zh-CN-XiaoshuangNeural", "晓双（女 · 童声）"),
    ("zh-CN-XiaoxuanNeural", "晓萱（女 · 甜妹）"),
    ("zh-CN-XiaoyanNeural", "晓颜（女 · 儿童）"),
    ("zh-CN-XiaoyouNeural", "晓悠（女 · 童声）"),
    ("zh-CN-liaoning-XiaobeiNeural", "晓北（女 · 东北腔）"),
    ("zh-CN-shaanxi-XiaoniNeural", "晓妮（女 · 陕西腔）"),
    ("zh-TW-HsiaoChenNeural", "曉臻（女 · 台灣腔）"),
    ("zh-TW-YunJheNeural", "雲哲（男 · 台灣腔）"),
    ("zh-HK-HiuGaaiNeural", "曉佳（女 · 粵語）"),
    ("zh-HK-HiuMaanNeural", "曉文（女 · 粵語）"),
    ("en-US-AriaNeural", "Aria（英文女声 · 自然）"),
    ("en-US-JennyNeural", "Jenny（英文女声 · 甜美）"),
    ("en-US-GuyNeural", "Guy（英文男声 · 沉稳）"),
    ("en-US-AnaNeural", "Ana（英文女声 · 童声）"),
    ("en-US-MichelleNeural", "Michelle（英文女声 · 温暖）"),
    ("en-US-ChristopherNeural", "Christopher（英文男声 · 沉稳）"),
    ("en-US-EricNeural", "Eric（英文男声 · 年轻）"),
    ("en-US-RogerNeural", "Roger（英文男声 · 成熟）"),
    ("en-GB-SoniaNeural", "Sonia（英音女声）"),
    ("en-GB-RyanNeural", "Ryan（英音男声）"),
)


def clean_voice(value) -> str:
    """清洗音色名：仅保留可见字符，超长截断，空值回落默认。"""
    text = str(value or "").strip()
    return text[:64] if text else DEFAULT_VOICE


def clean_rate(value) -> int:
    """清洗语速偏移（%）：钳制到 [-100, 100]。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RATE
    return max(-100, min(100, number))


def clean_pitch(value) -> int:
    """清洗音调偏移（Hz）：钳制到 [-50, 50]。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PITCH
    return max(-50, min(50, number))


def edge_rate_arg(rate) -> str:
    """edge-tts rate 参数：如 +10% / -20% / +0%。"""
    value = clean_rate(rate)
    sign = "+" if value >= 0 else ""
    return f"{sign}{value}%"


def edge_pitch_arg(pitch) -> str:
    """edge-tts pitch 参数：如 +5Hz / -10Hz / +0Hz。"""
    value = clean_pitch(pitch)
    sign = "+" if value >= 0 else ""
    return f"{sign}{value}Hz"


def _probe() -> bool:
    """**不 import 本体**地探测 edge-tts 是否可用。"""
    try:
        return importlib.util.find_spec("edge_tts") is not None
    except (ImportError, ValueError):
        # 父包缺失 / sys.modules 里被置 None 等异常形态：一律按不可用处理。
        return False


# 惰性探测结果（模块顶层，但不 import 本体）。测试可 monkeypatch 本标志。
_EDGE_TTS_AVAILABLE = _probe()


def edge_tts_available() -> bool:
    return bool(_EDGE_TTS_AVAILABLE)


class EdgeTtsProvider(TtsProvider):
    id = "edge"
    label = "edge-tts（微软 · 免 Key）"
    is_fallback = True
    availability_code = AVAILABILITY_CODE
    unavailable_message = MISSING_MESSAGE
    fields = (
        TtsField(
            "voice", "voice_chime_voice", "音色",
            "内置 20+ 款中英文音色（在线合成，无需 API Key）；配置值不在列表时自动追加“自定义”项。",
            kind="select", default=DEFAULT_VOICE, options=VOICE_OPTIONS,
        ),
        TtsField(
            "rate", "voice_chime_rate", "语速",
            "语速偏移百分比：0 为正常，正数更快，负数更慢。",
            kind="number", default=DEFAULT_RATE, minimum=-100, maximum=100, suffix=" %",
        ),
        TtsField(
            "pitch", "voice_chime_pitch", "音调",
            "音调偏移（Hz）：0 为正常，正数更尖锐，负数更低沉。",
            kind="number", default=DEFAULT_PITCH, minimum=-50, maximum=50, suffix=" Hz",
        ),
    )

    def plan(self, values: dict) -> dict:
        return {
            "provider": self.id,
            "voice": clean_voice(values.get("voice")),
            "rate": edge_rate_arg(values.get("rate")),
            "pitch": edge_pitch_arg(values.get("pitch")),
            "ext": "mp3",
        }

    def flavor(self, values: dict) -> str:
        # 历史格式逐字节保持：老缓存升级后仍能命中。
        return (
            f"{clean_voice(values.get('voice'))}"
            f"|{edge_rate_arg(values.get('rate'))}|{edge_pitch_arg(values.get('pitch'))}"
        )

    def availability(self, values: dict) -> str:
        return "" if edge_tts_available() else AVAILABILITY_CODE

    def synth(self, text: str, plan: dict, out_path) -> None:
        # 惰性导入：只在真的要合成的后台线程里付这笔 import 成本。
        try:
            import edge_tts
        except Exception as exc:  # noqa: BLE001 —— 统一转成「不可用」信号
            raise TtsUnavailable(AVAILABILITY_CODE, f"edge-tts 不可导入：{exc}") from exc
        communicate = edge_tts.Communicate(
            text,
            plan.get("voice") or DEFAULT_VOICE,
            rate=plan.get("rate") or edge_rate_arg(DEFAULT_RATE),
            pitch=plan.get("pitch") or edge_pitch_arg(DEFAULT_PITCH),
        )
        asyncio.run(communicate.save(str(out_path)))


PROVIDER = register(EdgeTtsProvider())
