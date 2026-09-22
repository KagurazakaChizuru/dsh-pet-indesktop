# -*- coding: utf-8 -*-
"""edge-tts provider：微软在线音色，免 Key，默认作为后备后端。

依赖 ``edge_tts``（可选依赖）：模块顶层**只做 find_spec 探测**，真正的 import 推迟到
``synth()``——首次 import 实测 ~1.4s 且常驻内存，而语音报时默认关闭，顶层 import
等于让每个用户白付这笔钱。

**两条实机踩过的坑**（2026-09-22 排查 edge 合成失败时定位）：

1. 微软会**下架音色**。老清单里 31 款有 10 款已经查不到（晓涵/晓辰/晓梦/晓墨/晓秋/
   晓睿/晓双/晓萱/晓颜/晓悠），配上它们只会得到 ``NoAudioReceived``——用户看到的是
   「声音没了」，不是「音色不存在」。对策：``preflight()`` 拿**在线音色表**校验，
   下线的自动换默认音色并给出说明；``synth()`` 里再兜一次底。
2. **连发请求会偶发** ``NoAudioReceived``（实测 en-US 那批间隔 6 秒重试全部成功，
   连发则整批失败）。对策：``synth()`` 内置重试 + 间隔，且主音色反复失败时退到默认音色。

在线音色表通过 ``refresh_voice_list()`` 拉取并缓存（TTL ``VOICE_LIST_TTL_S``）；
**它只允许在后台合成线程里调用**——``preflight()`` 跑在 GUI 线程，只看缓存/内置清单。
"""

from __future__ import annotations

import asyncio
import importlib.util
import threading
import time

from .base import TtsField, TtsProvider, TtsUnavailable, register

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = 0  # 语速偏移（%），范围约 -100 ~ +100
DEFAULT_PITCH = 0  # 音调偏移（Hz），范围约 -50 ~ +50
AVAILABILITY_CODE = "edge-tts-missing"
MISSING_MESSAGE = "语音报时需要 edge-tts 库：请运行 pip install edge-tts 后重试"

#: 合成失败时的重试次数与间隔（避开连发限流；实测间隔重试能救回偶发的 NoAudioReceived）
EDGE_RETRY_TIMES = 2
EDGE_RETRY_DELAY_S = 1.5
#: 在线音色表缓存时长
VOICE_LIST_TTL_S = 6 * 3600

# 中英文音色下拉列表（value=音色名，label=友好中文标签）。
# **2026-09-22 按微软在线音色表重建**：删掉已下线的 10 款，补上在线的新音色。
# 这份清单同时是「拿不到在线表」时的兜底校验集，所以宁可少列也不要留死音色。
VOICE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("zh-CN-XiaoxiaoNeural", "晓晓（女 · 自然）"),
    ("zh-CN-XiaoyiNeural", "晓伊（女 · 活泼）"),
    ("zh-CN-YunjianNeural", "云健（男 · 浑厚）"),
    ("zh-CN-YunxiNeural", "云希（男 · 阳光）"),
    ("zh-CN-YunxiaNeural", "云夏（男 · 少年）"),
    ("zh-CN-YunyangNeural", "云扬（男 · 新闻播报）"),
    ("zh-CN-liaoning-XiaobeiNeural", "晓北（女 · 东北腔）"),
    ("zh-CN-shaanxi-XiaoniNeural", "晓妮（女 · 陕西腔）"),
    ("zh-TW-HsiaoChenNeural", "曉臻（女 · 台灣腔）"),
    ("zh-TW-HsiaoYuNeural", "曉雨（女 · 台灣腔）"),
    ("zh-TW-YunJheNeural", "雲哲（男 · 台灣腔）"),
    ("zh-HK-HiuGaaiNeural", "曉佳（女 · 粵語）"),
    ("zh-HK-HiuMaanNeural", "曉文（女 · 粵語）"),
    ("zh-HK-WanLungNeural", "雲龍（男 · 粵語）"),
    ("en-US-AriaNeural", "Aria（英文女声 · 自然）"),
    ("en-US-JennyNeural", "Jenny（英文女声 · 甜美）"),
    ("en-US-MichelleNeural", "Michelle（英文女声 · 温暖）"),
    ("en-US-AnaNeural", "Ana（英文女声 · 童声）"),
    ("en-US-AvaNeural", "Ava（英文女声 · 新一代）"),
    ("en-US-EmmaNeural", "Emma（英文女声 · 新一代）"),
    ("en-US-GuyNeural", "Guy（英文男声 · 沉稳）"),
    ("en-US-ChristopherNeural", "Christopher（英文男声 · 沉稳）"),
    ("en-US-EricNeural", "Eric（英文男声 · 年轻）"),
    ("en-US-RogerNeural", "Roger（英文男声 · 成熟）"),
    ("en-US-AndrewNeural", "Andrew（英文男声 · 新一代）"),
    ("en-US-BrianNeural", "Brian（英文男声 · 新一代）"),
    ("en-US-SteffanNeural", "Steffan（英文男声 · 沉稳）"),
    ("en-US-AvaMultilingualNeural", "Ava（多语言女声）"),
    ("en-US-EmmaMultilingualNeural", "Emma（多语言女声）"),
    ("en-US-AndrewMultilingualNeural", "Andrew（多语言男声）"),
    ("en-US-BrianMultilingualNeural", "Brian（多语言男声）"),
    ("en-GB-SoniaNeural", "Sonia（英音女声）"),
    ("en-GB-RyanNeural", "Ryan（英音男声）"),
    ("en-GB-LibbyNeural", "Libby（英音女声）"),
    ("en-GB-MaisieNeural", "Maisie（英音女童）"),
    ("en-GB-ThomasNeural", "Thomas（英音男声）"),
)


#: 2026-09-22 实测已从微软在线音色表下线的音色（我们老清单里的）——只用于把
#: 「你配的那个音色已经没了」这件事说成人话（中文名），并可在设置页标出来。
DEPRECATED_VOICE_LABELS = {
    "zh-CN-XiaochenNeural": "晓辰",
    "zh-CN-XiaohanNeural": "晓涵",
    "zh-CN-XiaomengNeural": "晓梦",
    "zh-CN-XiaomoNeural": "晓墨",
    "zh-CN-XiaoqiuNeural": "晓秋",
    "zh-CN-XiaoruiNeural": "晓睿",
    "zh-CN-XiaoshuangNeural": "晓双",
    "zh-CN-XiaoxuanNeural": "晓萱",
    "zh-CN-XiaoyanNeural": "晓颜",
    "zh-CN-XiaoyouNeural": "晓悠",
}


def voice_label(value) -> str:
    """音色的中文名：内置清单 → 已下线映射 → 原样返回 id。用于给用户看的提示。"""
    voice = str(value or "").strip()
    for name, label in VOICE_OPTIONS:
        if name == voice:
            return label.split("（")[0]
    return DEPRECATED_VOICE_LABELS.get(voice, voice)


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


# ---------------------------------------------------------------- 在线音色表
_bundled_voices: frozenset[str] = frozenset(value for value, _label in VOICE_OPTIONS)
_live_voices: frozenset[str] | None = None
_live_fetched_at = 0.0
_voice_lock = threading.Lock()


def bundled_voices() -> frozenset[str]:
    """内置（随包发布）音色集合——拿不到在线表时的校验集。"""
    return _bundled_voices


def known_voices() -> frozenset[str]:
    """当前可用于校验的音色集合：有在线缓存就用在线表，否则退回内置表。

    **不联网**，可以放心在 GUI 线程（preflight）里调。
    """
    with _voice_lock:
        return _live_voices if _live_voices else _bundled_voices


def refresh_voice_list(*, force: bool = False, timeout: float = 10.0) -> frozenset[str] | None:
    """拉一次微软在线音色表并缓存（**会联网**，只该在后台合成线程里调）。

    失败/超时返回 ``None`` 并保留旧缓存（联网失败不该让报时跟着失败）。
    """
    global _live_voices, _live_fetched_at
    now = time.time()
    with _voice_lock:
        if not force and _live_voices and now - _live_fetched_at < VOICE_LIST_TTL_S:
            return _live_voices
    try:
        import edge_tts

        raw = asyncio.run(asyncio.wait_for(edge_tts.list_voices(), timeout=timeout))
        voices = frozenset(str(item.get("ShortName") or "") for item in raw)
        voices = frozenset(name for name in voices if name)
    except Exception as exc:  # noqa: BLE001 —— 拉不到不是错误，用旧的就够
        import logging

        logging.getLogger(__name__).debug("拉取在线音色表失败（沿用内置/旧表）：%s", exc)
        return None
    if not voices:
        return None
    with _voice_lock:
        _live_voices = voices
        _live_fetched_at = now
    return voices


def reset_voice_cache() -> None:
    """清掉在线音色表缓存（测试用）。"""
    global _live_voices, _live_fetched_at
    with _voice_lock:
        _live_voices = None
        _live_fetched_at = 0.0


class EdgeTtsProvider(TtsProvider):
    id = "edge"
    label = "edge-tts（微软 · 免 Key）"
    is_fallback = True
    availability_code = AVAILABILITY_CODE
    unavailable_message = MISSING_MESSAGE
    fields = (
        TtsField(
            "voice", "voice_chime_voice", "音色",
            "微软在线音色（无需 API Key）。清单随微软增删维护；"
            "选到已下线的音色会自动改用默认音色「晓晓」并记入日志。",
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

    def preflight(self, values: dict) -> tuple[dict, str]:
        """配置音色不在（缓存/内置）音色表里时换成默认音色，并给出面向用户的说明。

        跑在 GUI 线程：只看缓存/内置清单，**不联网**。真正的兜底在 ``synth()``。
        """
        voice = clean_voice(values.get("voice"))
        if edge_tts_available() and voice not in known_voices():
            note = (
                f"音色「{voice_label(voice)}」已不在微软在线音色表里（多半被下架了），"
                f"本次改用默认音色「{voice_label(DEFAULT_VOICE)}」；"
                "可在 设置 → 语音 → 语音报时 → 音色 里换一个可用的。"
            )
            return {**values, "voice": DEFAULT_VOICE}, note
        return values, ""

    def synth(self, text: str, plan: dict, out_path) -> None:
        # 惰性导入：只在真的要合成的后台线程里付这笔 import 成本。
        try:
            import edge_tts
        except Exception as exc:  # noqa: BLE001 —— 统一转成「不可用」信号
            raise TtsUnavailable(AVAILABILITY_CODE, f"edge-tts 不可导入：{exc}") from exc

        # 后台线程：有网就顺手刷新在线音色表（失败无所谓，用旧的）
        refresh_voice_list()

        voice = clean_voice(plan.get("voice"))
        checked, _note = self.preflight({"voice": voice})
        voice = clean_voice(checked.get("voice"))

        candidates = [voice]
        if voice != DEFAULT_VOICE:
            # 主音色反复失败（下架、限流、参数被拒）时退到默认音色再试一轮
            candidates.append(DEFAULT_VOICE)
        errors: list[str] = []
        for candidate in candidates:
            for attempt in range(1, EDGE_RETRY_TIMES + 1):
                try:
                    asyncio.run(self._save(edge_tts, text, candidate, plan, out_path))
                    if out_path.exists() and out_path.stat().st_size > 0:
                        if candidate != voice:
                            import logging

                            logging.getLogger(__name__).warning(
                                "音色 %s 合成失败，已改用默认音色 %s", voice, candidate
                            )
                        return
                    raise RuntimeError("服务端未返回音频（空文件）")
                except Exception as exc:  # noqa: BLE001 —— 记下来，重试/换音色
                    errors.append(f"{candidate} 第{attempt}次: {type(exc).__name__}: {exc}")
                    try:
                        out_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    if attempt < EDGE_RETRY_TIMES:
                        time.sleep(EDGE_RETRY_DELAY_S)  # 间隔重试：连发会被偶发拒绝
        raise RuntimeError("edge-tts 合成失败 → " + "；".join(errors[-4:]))

    @staticmethod
    async def _save(edge_tts, text: str, voice: str, plan: dict, out_path) -> None:
        communicate = edge_tts.Communicate(
            text,
            voice,
            rate=plan.get("rate") or edge_rate_arg(DEFAULT_RATE),
            pitch=plan.get("pitch") or edge_pitch_arg(DEFAULT_PITCH),
        )
        await communicate.save(str(out_path))


PROVIDER = register(EdgeTtsProvider())
