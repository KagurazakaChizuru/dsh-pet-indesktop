# -*- coding: utf-8 -*-
"""语音报时：纯逻辑决策层（零 Qt、零 edge_tts）。

模块顶部为纯函数与纯数据，可在无 GUI 环境直接导入测试；语音合成与播放
由 pet/voice_chime_service.py 承担（后台线程 + QtMultimedia）。

职责：
- 配置默认值与逐项清洗（与 config.py 平铺键对应）；
- 报时调度判定（整点 / 每30分钟 / 每15分钟 / 每5分钟 / 每分钟 / 自定义
  时间点）与“距下一报时点秒数”计算；
- 报时文本组装：语音口播（中文数字，供 TTS 与缓存键）与气泡展示（阿拉伯数字）
  两套文本解耦生成；
- 台词/歌词轮换：库按 8 小时周期整体换批，同一周期内按序轮换取不同条目；
- 自定义台词/歌词解析（留空回退内置库）；
- edge-tts 参数格式化（rate / pitch）。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .voice_chime_quotes import CHINESE_QUOTES, ENGLISH_QUOTES

# 调度模式键（设置页 ModernSelect 的 data 与此对应）。
SCHEDULE_KEYS = (
    "hourly",  # 整点
    "every_30",  # 每 30 分钟
    "every_15",  # 每 15 分钟
    "every_5",  # 每 5 分钟
    "every_minute",  # 每分钟
    "custom",  # 自定义时间点
)
SCHEDULE_LABELS = {
    "hourly": "整点报时",
    "every_30": "每 30 分钟",
    "every_15": "每 15 分钟",
    "every_5": "每 5 分钟",
    "every_minute": "每分钟",
    "custom": "自定义时间点",
}

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = 0  # 语速偏移（%），edge-tts 范围约 -100 ~ +100
DEFAULT_PITCH = 0  # 音调偏移（Hz），edge-tts 范围约 -50 ~ +50
DEFAULT_VOLUME = 80  # 播放音量（0-100）
DEFAULT_SHOW_BUBBLE = True  # 报时气泡开关
DEFAULT_SHOW_QUOTE = True  # 台词/歌词开关

# 台词/歌词轮换：库按本地时间每 8 小时整体换一批（周期 0-8 / 8-16 / 16-24）。
# 库按序均分为 _QUOTE_BATCHES_PER_DAY（=3）批，周期序号取模决定当前批次，跨周期
# 即切到新批次；同一周期内每次报时在批次内按顺序轮换取下一条（用尽回环），因此
# 同周期内多次报时听到的是不同句子，而非“一句固定 8 小时”。周期序号跨天连续
# 递增，故跨天也保持可预期的换批顺序。
QUOTE_ROTATION_HOURS = 8
_QUOTE_SLOTS_PER_DAY = 24 // QUOTE_ROTATION_HOURS
_QUOTE_BATCHES_PER_DAY = _QUOTE_SLOTS_PER_DAY  # 台词库均分批数（一天 3 个周期 = 3 批）
_MAX_CUSTOM_QUOTE_LEN = 120  # 自定义单条台词长度上限（超长截断，防误粘长文）

# edge-tts 中英文音色下拉列表（value=音色名，label=友好中文标签）。
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

# ---------------------------------------------------------------- 合成后端
# 本模块是纯逻辑层：只存「后端名 / 参数 / 请求体构造 / 响应解析」，不 import
# 任何网络或 TTS 库——真正的 HTTP 在 pet/voice_chime_service.py 的后台线程里做。
BACKEND_EDGE = "edge"  # edge-tts（微软在线，免 Key）
BACKEND_MIMO = "mimo"  # 小米 MiMo TTS（OpenAI 兼容接口，需 API Key）
BACKENDS: tuple[str, ...] = (BACKEND_EDGE, BACKEND_MIMO)
BACKEND_LABELS = {
    BACKEND_EDGE: "edge-tts（微软 · 免 Key）",
    BACKEND_MIMO: "小米 MiMo（需 API Key）",
}
# 默认走小米（用户点名要的），失败时按 voice_chime_tts_fallback 自动回退 edge。
DEFAULT_BACKEND = BACKEND_MIMO
DEFAULT_TTS_FALLBACK = True

MIMO_BASE_URL = "https://api.xiaomimimo.com"
MIMO_CHAT_PATH = "/v1/chat/completions"
MIMO_MODEL = "mimo-v2.5-tts"  # 内置音色
MIMO_MODEL_VOICE_DESIGN = "mimo-v2.5-tts-voicedesign"  # 用文字描述生成音色
MIMO_MODELS: tuple[tuple[str, str], ...] = (
    (MIMO_MODEL, "内置音色（8 款）"),
    (MIMO_MODEL_VOICE_DESIGN, "音色设计（用文字描述音色）"),
)
DEFAULT_MIMO_MODEL = MIMO_MODEL
# 内置音色 id 就是中文/英文名本身（见官方文档的音色表）
MIMO_VOICE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("冰糖", "冰糖（女 · 中文默认）"),
    ("茉莉", "茉莉（女 · 中文）"),
    ("苏打", "苏打（男 · 中文）"),
    ("白桦", "白桦（男 · 中文）"),
    ("Mia", "Mia（女 · 英文）"),
    ("Chloe", "Chloe（女 · 英文）"),
    ("Milo", "Milo（男 · 英文）"),
    ("Dean", "Dean（男 · 英文）"),
)
DEFAULT_MIMO_VOICE = "冰糖"
# 风格指令（user 消息）：自然语言描述语气/情绪/节奏；空则不发该条消息。
DEFAULT_MIMO_STYLE = ""
MIMO_STYLE_MAX_LEN = 300
MIMO_AUDIO_FORMAT = "wav"  # 非流式请求的音色输出格式（服务据此决定缓存扩展名）
MIMO_TIMEOUT_S = 30.0

_CUSTOM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_RATE_RE = re.compile(r"^[+-]?\d+$")
_PITCH_RE = re.compile(r"^[+-]?\d+$")

# 中文时刻文本（12 小时制）。
_HOUR_CN = (
    "十二",
    "一",
    "二",
    "三",
    "四",
    "五",
    "六",
    "七",
    "八",
    "九",
    "十",
    "十一",
)


def default_chime_config() -> dict:
    """语音报时配置默认值（config.py 顶层平铺键的镜像）。"""
    return {
        "voice_chime_enabled": False,
        "voice_chime_schedule": "hourly",
        "voice_chime_custom_times": "",
        "voice_chime_voice": DEFAULT_VOICE,
        "voice_chime_rate": DEFAULT_RATE,
        "voice_chime_pitch": DEFAULT_PITCH,
        "voice_chime_volume": DEFAULT_VOLUME,
        "voice_chime_show_bubble": DEFAULT_SHOW_BUBBLE,
        "voice_chime_show_quote": DEFAULT_SHOW_QUOTE,
        "voice_chime_custom_quotes_zh": "",  # 自定义中文台词/歌词（一行一条，留空用内置库）
        "voice_chime_custom_quotes_en": "",  # 自定义英文台词/歌词（一行一条，留空用内置库）
        "voice_chime_tts_backend": DEFAULT_BACKEND,  # edge / mimo
        "voice_chime_tts_fallback": DEFAULT_TTS_FALLBACK,  # 主后端失败时自动回退 edge
        "voice_chime_mimo_model": DEFAULT_MIMO_MODEL,
        "voice_chime_mimo_voice": DEFAULT_MIMO_VOICE,
        "voice_chime_mimo_style": DEFAULT_MIMO_STYLE,
    }


def clean_flag(value, default: bool = True) -> bool:
    """清洗布尔开关：JSON bool 原样返回，字符串按常见真值解析，非法回落默认。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on", "开", "开启"):
        return True
    if text in ("0", "false", "no", "off", "关", "关闭"):
        return False
    return default


def clean_schedule(value) -> str:
    """清洗调度模式；非法回落整点。"""
    text = str(value or "").strip()
    return text if text in SCHEDULE_KEYS else "hourly"


def clean_custom_times(value) -> frozenset[str]:
    """清洗自定义时间点：逗号/空格/分号分隔的 HH:MM，非法项丢弃。"""
    text = str(value or "").strip()
    parts = re.split(r"[,，;；\s]+", text)
    times: set[str] = set()
    for part in parts:
        part = part.strip()
        match = _CUSTOM_RE.match(part)
        if match:
            times.add(f"{int(match.group(1)):02d}:{match.group(2)}")
    return frozenset(times)


def clean_voice(value) -> str:
    """清洗音色名：仅保留可见字符，超长截断。"""
    text = str(value or "").strip()
    return text[:64] if text else DEFAULT_VOICE


def clean_backend(value) -> str:
    """清洗合成后端名；非法回落默认后端。"""
    text = str(value or "").strip().lower()
    return text if text in BACKENDS else DEFAULT_BACKEND


def clean_mimo_model(value) -> str:
    """清洗 MiMo 模型 id；非法回落内置音色模型。"""
    text = str(value or "").strip()
    return text if text in {model for model, _ in MIMO_MODELS} else DEFAULT_MIMO_MODEL


def clean_mimo_voice(value) -> str:
    """清洗 MiMo 音色 id（内置音色名就是 id 本身）；空值回落默认音色。"""
    text = str(value or "").strip()
    return text[:64] if text else DEFAULT_MIMO_VOICE


def clean_mimo_style(value) -> str:
    """清洗风格指令（user 消息）：去控制字符、压掉换行、超长截断。"""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"\s*\r?\n\s*", " ", text).strip()
    return text[:MIMO_STYLE_MAX_LEN]


def synth_ext(backend) -> str:
    """该后端的合成产物扩展名（缓存文件名用）：edge→mp3，mimo→wav。"""
    return "wav" if clean_backend(backend) == BACKEND_MIMO else "mp3"


def synth_attempts(cfg: dict) -> tuple[dict, ...]:
    """按配置给出合成尝试序列（主后端优先，可回退 edge）。

    每项是一个自足的「怎么合成」描述，服务层照着执行：
      {"backend": "mimo", "model":..., "voice":..., "style":..., "ext": "wav"}
      {"backend": "edge", "voice":..., "rate": "+0%", "pitch": "+0Hz", "ext": "mp3"}
    纯函数：不探测环境、不读凭据——「这个后端现在能不能用」由服务层判定，
    这样单测不需要网络/钥匙串。
    """
    backend = clean_backend(cfg.get("backend", DEFAULT_BACKEND))
    order = [backend]
    fallback = clean_flag(cfg.get("fallback", DEFAULT_TTS_FALLBACK), DEFAULT_TTS_FALLBACK)
    if fallback and backend != BACKEND_EDGE:
        order.append(BACKEND_EDGE)
    attempts: list[dict] = []
    for name in order:
        if name == BACKEND_MIMO:
            attempts.append({
                "backend": BACKEND_MIMO,
                "model": clean_mimo_model(cfg.get("mimo_model", DEFAULT_MIMO_MODEL)),
                "voice": clean_mimo_voice(cfg.get("mimo_voice", DEFAULT_MIMO_VOICE)),
                "style": clean_mimo_style(cfg.get("mimo_style", DEFAULT_MIMO_STYLE)),
                "ext": synth_ext(BACKEND_MIMO),
            })
        else:
            attempts.append({
                "backend": BACKEND_EDGE,
                "voice": clean_voice(cfg.get("voice", DEFAULT_VOICE)),
                "rate": edge_rate_arg(cfg.get("rate", DEFAULT_RATE)),
                "pitch": edge_pitch_arg(cfg.get("pitch", DEFAULT_PITCH)),
                "ext": synth_ext(BACKEND_EDGE),
            })
    return tuple(attempts)


def mimo_messages(text: str, attempt: dict) -> list[dict]:
    """构造 MiMo TTS 的 messages。

    官方约定：**待合成文本必须放在 assistant 消息**；user 消息是可选的风格指令
    （音色设计模型下 user 消息就是音色描述，必填）。风格为空时不发 user 消息。
    """
    messages: list[dict] = []
    style = clean_mimo_style(attempt.get("style", ""))
    if style:
        messages.append({"role": "user", "content": style})
    messages.append({"role": "assistant", "content": str(text or "")})
    return messages


def mimo_payload(text: str, attempt: dict) -> dict:
    """MiMo TTS 非流式请求体。内置音色模型才发 voice；音色设计模型不发。"""
    audio: dict = {"format": MIMO_AUDIO_FORMAT}
    if clean_mimo_model(attempt.get("model")) != MIMO_MODEL_VOICE_DESIGN:
        audio["voice"] = clean_mimo_voice(attempt.get("voice"))
    return {
        "model": clean_mimo_model(attempt.get("model")),
        "messages": mimo_messages(text, attempt),
        "audio": audio,
        "stream": False,
    }


def parse_mimo_audio(payload) -> bytes:
    """从 MiMo 响应里解出音频字节（base64）。

    只接受官方文档记录的结构 ``choices[0].message.audio.data``；解不出就抛
    ``ValueError`` 并带上可读原因（服务层把异常文本回给气泡，用户至少知道
    发生了什么，而不是「合成失败」四个字）。
    """
    import base64

    if not isinstance(payload, dict):
        raise ValueError("响应不是 JSON 对象")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        message = payload.get("error") or payload.get("message") or "响应里没有 choices"
        raise ValueError(str(message)[:120])
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    audio = message.get("audio") if isinstance(message, dict) else None
    data = audio.get("data") if isinstance(audio, dict) else None
    if not data:
        raise ValueError("响应里没有音频数据")
    try:
        return base64.b64decode(str(data))
    except Exception as exc:  # noqa: BLE001 —— 统一转成可读错误
        raise ValueError(f"音频数据解码失败：{exc}") from exc


def clean_custom_quotes(value) -> tuple[str, ...]:
    """清洗自定义台词/歌词：按行拆分（一行一条），去空行/去重/保序。

    兼容设置页传来的多行字符串（``\\n`` / ``\\r\\n`` / ``\\r``）与已是
    序列的配置值；去除控制字符并按 ``_MAX_CUSTOM_QUOTE_LEN`` 截断单条，
    保证进入 TTS 的文本干净。返回空元组表示“未自定义”，调用方回退内置库。
    """
    if value is None:
        return ()
    if isinstance(value, (tuple, list, set)):
        raw_lines = [str(item) for item in value]
    else:
        raw_lines = re.split(r"\r\n|\r|\n", str(value))
    quotes: list[str] = []
    for line in raw_lines:
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", line).strip()
        if not text:
            continue
        text = text[:_MAX_CUSTOM_QUOTE_LEN].strip()
        if text and text not in quotes:
            quotes.append(text)
    return tuple(quotes)


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


def clean_volume(value) -> int:
    """清洗音量（0-100）。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_VOLUME
    return max(0, min(100, number))


def normalize_chime_config(config) -> dict:
    """从 config 对象读取并清洗语音报时全部键（config 缺失字段用默认值）。"""
    if config is None:
        config = {}
    return {
        "enabled": bool(config.get("voice_chime_enabled", False)),
        "schedule": clean_schedule(config.get("voice_chime_schedule", "hourly")),
        "custom_times": clean_custom_times(config.get("voice_chime_custom_times", "")),
        "voice": clean_voice(config.get("voice_chime_voice", DEFAULT_VOICE)),
        "rate": clean_rate(config.get("voice_chime_rate", DEFAULT_RATE)),
        "pitch": clean_pitch(config.get("voice_chime_pitch", DEFAULT_PITCH)),
        "volume": clean_volume(config.get("voice_chime_volume", DEFAULT_VOLUME)),
        "show_bubble": clean_flag(config.get("voice_chime_show_bubble", DEFAULT_SHOW_BUBBLE), DEFAULT_SHOW_BUBBLE),
        "show_quote": clean_flag(config.get("voice_chime_show_quote", DEFAULT_SHOW_QUOTE), DEFAULT_SHOW_QUOTE),
        "custom_quotes_zh": clean_custom_quotes(config.get("voice_chime_custom_quotes_zh", "")),
        "custom_quotes_en": clean_custom_quotes(config.get("voice_chime_custom_quotes_en", "")),
        "backend": clean_backend(config.get("voice_chime_tts_backend", DEFAULT_BACKEND)),
        "fallback": clean_flag(
            config.get("voice_chime_tts_fallback", DEFAULT_TTS_FALLBACK), DEFAULT_TTS_FALLBACK
        ),
        "mimo_model": clean_mimo_model(config.get("voice_chime_mimo_model", DEFAULT_MIMO_MODEL)),
        "mimo_voice": clean_mimo_voice(config.get("voice_chime_mimo_voice", DEFAULT_MIMO_VOICE)),
        "mimo_style": clean_mimo_style(config.get("voice_chime_mimo_style", DEFAULT_MIMO_STYLE)),
    }


def is_chime_minute(now: datetime, cfg: dict) -> bool:
    """当前分钟是否命中报时点（cfg 为 normalize_chime_config 的输出）。"""
    schedule = cfg.get("schedule", "hourly")
    minute = now.minute
    if schedule == "hourly":
        return minute == 0
    if schedule == "every_30":
        return minute % 30 == 0
    if schedule == "every_15":
        return minute % 15 == 0
    if schedule == "every_5":
        return minute % 5 == 0
    if schedule == "every_minute":
        return True
    if schedule == "custom":
        hhmm = f"{now.hour:02d}:{now.minute:02d}"
        return hhmm in cfg.get("custom_times", frozenset())
    return False


def next_chime_in_seconds(now: datetime, cfg: dict) -> int:
    """距下一报时点的秒数（不含当前分钟已过部分，1..3600 或自定义 1..86400）。"""
    if cfg.get("schedule") == "custom":
        times = sorted(cfg.get("custom_times", frozenset()))
        if not times:
            return 3600 * 24
        for hhmm in times:
            hour, minute = (int(part) for part in hhmm.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > now:
                return max(1, int((candidate - now).total_seconds()))
        first = times[0]
        hour, minute = (int(part) for part in first.split(":"))
        tomorrow = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return max(1, int((tomorrow - now).total_seconds()))
    minute = now.minute
    if cfg.get("schedule") == "every_minute":
        return 60 - now.second if now.second else 60
    if cfg.get("schedule") == "hourly":
        step = 60
    elif cfg.get("schedule") == "every_30":
        step = 30
    elif cfg.get("schedule") == "every_15":
        step = 15
    else:  # every_5
        step = 5
    next_minute = minute - (minute % step) + step
    if next_minute >= 60:
        base = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        base = now.replace(minute=next_minute, second=0, microsecond=0)
    return max(1, int((base - now).total_seconds()))


def chime_slot(now: datetime, cfg: dict) -> str:
    """当前分钟命中报时点时返回去重槽位（YYYY-MM-DDTHH:MM#模式），否则空串。

    服务用该槽位做幂等盖戳：同一分钟只报一次（防 tick 重复触发）。
    """
    if not is_chime_minute(now, cfg):
        return ""
    return f"{now.strftime('%Y-%m-%dT%H:%M')}#{cfg.get('schedule', 'hourly')}"


def _period_cn(hour: int) -> str:
    """时段前缀；入参是 24 小时制的 hour（0-23），不是 12 小时制。"""
    return "凌晨" if hour < 5 else "早上" if hour < 9 else "上午" if hour < 12 else ("中午" if hour == 12 else "下午" if hour < 18 else "晚上")


def build_chime_text(now: datetime, cfg: dict) -> str:
    """组装报时文本：中文口播“现在是上午九点整 / 现在上午九点05分”。

    分钟用两位数字（TTS 读作「零五分」）；小时走 12 小时制中文
    （0 点与 12 点都是「十二点」）。rate/pitch 为 TTS 参数、音量在播放侧，
    都不进入正文。
    """
    hour_12 = now.hour % 12 or 12
    hour_cn = _HOUR_CN[hour_12 % 12]
    period = _period_cn(now.hour)
    if now.minute == 0:
        return f"现在是{period}{hour_cn}点整"
    return f"现在{period}{hour_cn}点{now.minute:02d}分"


def quote_slot_serial(now: datetime) -> int:
    """台词/歌词轮换的全局 8 小时周期序号（本地时间，跨天连续递增）。

    每个自然日固定 ``_QUOTE_SLOTS_PER_DAY``（=3）个 8 小时周期，序号由
    “日期序数 × 周期数 + 当日第几个周期”得到，因此相邻周期序号恰好差 1
    （含跨天 16-24 → 次日 0-8），取模即可实现顺序换批、跨天不跳乱。
    """
    return now.date().toordinal() * _QUOTE_SLOTS_PER_DAY + now.hour // QUOTE_ROTATION_HOURS


def chime_index_in_period(now: datetime, cfg: dict) -> int:
    """当前 8 小时周期内的报时次序（0 起，含当前这一次报时）。

    从周期起点（0 点 / 8 点 / 16 点）逐分钟回溯统计命中的报时点个数；
    同一周期内每报一次该值 +1，批次内据此顺序轮换取不同条目。周期内尚无
    更早报时（或自定义时间点集中在其它周期）时返回 0，取批次首条。
    """
    start = now.replace(
        hour=now.hour // QUOTE_ROTATION_HOURS * QUOTE_ROTATION_HOURS,
        minute=0,
        second=0,
        microsecond=0,
    )
    index = -1
    cursor = start
    while cursor <= now:
        if is_chime_minute(cursor, cfg):
            index += 1
        cursor += timedelta(minutes=1)
    return max(index, 0)


def split_quote_batches(pool, batches: int = _QUOTE_BATCHES_PER_DAY) -> tuple[tuple[str, ...], ...]:
    """把台词库按序均分为若干批（前几批各多 1 条），空批自动过滤。

    用于“每 8 小时整体换一批”：周期序号取模决定当前批次。条目数少于批数
    时会出现空批，过滤后保证取批永远不会命中空批（自定义仅 1 条时只有 1 批）。
    """
    items = tuple(pool)
    if not items:
        return ()
    count = max(1, int(batches))
    size, extra = divmod(len(items), count)
    result: list[tuple[str, ...]] = []
    pos = 0
    for i in range(count):
        take = size + (1 if i < extra else 0)
        if take:
            result.append(items[pos : pos + take])
        pos += take
    return tuple(result)


def pick_quote(now: datetime, cfg: dict) -> str:
    """按“每 8 小时整体换一批 + 周期内按序轮换”选取一句台词/歌词。

    选取规则：
    1. 音色以 zh 开头用中文库，否则用英文库；对应语言自定义条目非空时整体
       替换内置库（留空回退内置库）；
    2. 库按序均分为 ``_QUOTE_BATCHES_PER_DAY`` 批，周期序号
       :func:`quote_slot_serial` 取模决定当前批次 —— 跨周期即换新批次；
    3. 周期内第 :func:`chime_index_in_period` 次报时取批次内第 N 条（顺序
       轮换、用尽回环），因此同一周期内多次报时能听到不同句子。
    """
    chinese = str(cfg.get("voice", DEFAULT_VOICE)).lower().startswith("zh")
    custom = clean_custom_quotes(cfg.get("custom_quotes_zh" if chinese else "custom_quotes_en"))
    pool = custom or (CHINESE_QUOTES if chinese else ENGLISH_QUOTES)
    if not pool:
        return ""
    batch_list = split_quote_batches(pool)
    if not batch_list:
        return ""
    batch = batch_list[quote_slot_serial(now) % len(batch_list)]
    return batch[chime_index_in_period(now, cfg) % len(batch)]


def build_chime_sentence(now: datetime, cfg: dict) -> str:
    """完整报时语句：报时文本 + 轮换台词/歌词（句号分隔，便于 TTS 停顿）。

    配置 ``show_quote`` 为 False 时仅返回报时文本（用户关闭台词/歌词）。
    """
    text = build_chime_text(now, cfg)
    if not clean_flag(cfg.get("show_quote", DEFAULT_SHOW_QUOTE), DEFAULT_SHOW_QUOTE):
        return text
    quote = pick_quote(now, cfg)
    return f"{text}。{quote}" if quote else text


def build_chime_bubble_text(now: datetime) -> str:
    """气泡展示用的报时文本：以阿拉伯数字为主（如“现在下午 15:45”）。

    与 :func:`build_chime_text`（中文数字口播，供 TTS 与缓存键）解耦：气泡
    只做视觉展示，用 24 小时制阿拉伯数字 + 中文时段词，避免“下午一点05分”
    这类阿拉伯数字与中文数字混排。
    """
    return f"现在{_period_cn(now.hour)} {now.hour:02d}:{now.minute:02d}"


def build_bubble_sentence(now: datetime, cfg: dict) -> str:
    """气泡完整文本：阿拉伯数字报时 + 台词/歌词（与语音口播文本解耦）。

    语音仍用 :func:`build_chime_sentence`（中文数字口播，作为合成输入与缓存键）；
    两者在同一时刻取到同一条台词，仅时间部分表示不同。``show_quote`` 关闭时
    只返回气泡报时文本。
    """
    text = build_chime_bubble_text(now)
    if not clean_flag(cfg.get("show_quote", DEFAULT_SHOW_QUOTE), DEFAULT_SHOW_QUOTE):
        return text
    quote = pick_quote(now, cfg)
    return f"{text}。{quote}" if quote else text


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


def cache_key(text: str, cfg: dict) -> str:
    """音频缓存文件名键：内容 + 后端 + 该后端的音色/参数 的短哈希。

    后端必须进键：同一句报时在 edge 与 MiMo 下是两段不同的音频，缓存不能互串
    （换后端后仍播上一个后端的声音，用户会以为设置没生效）。
    """
    import hashlib

    backend = clean_backend(cfg.get("backend", BACKEND_EDGE))
    if backend == BACKEND_MIMO:
        raw = (
            f"{text}|mimo|{clean_mimo_model(cfg.get('mimo_model', DEFAULT_MIMO_MODEL))}"
            f"|{clean_mimo_voice(cfg.get('mimo_voice', DEFAULT_MIMO_VOICE))}"
            f"|{clean_mimo_style(cfg.get('mimo_style', DEFAULT_MIMO_STYLE))}"
        )
    else:
        # edge 分支保持历史格式逐字节不变：老缓存在升级后仍能命中。
        raw = (
            f"{text}|{clean_voice(cfg.get('voice', DEFAULT_VOICE))}"
            f"|{edge_rate_arg(cfg.get('rate'))}|{edge_pitch_arg(cfg.get('pitch'))}"
        )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
