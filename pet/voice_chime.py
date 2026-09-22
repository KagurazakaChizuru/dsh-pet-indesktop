# -*- coding: utf-8 -*-
"""语音报时：纯逻辑决策层（零 Qt、零 edge_tts）。

模块顶部为纯函数与纯数据，可在无 GUI 环境直接导入测试；语音合成与播放
由 pet/voice_chime_service.py 承担（后台线程 + QtMultimedia）。

**合成后端已接口化**（``pet/tts/`` 注册表）：本模块只负责「调度 + 文本 + 选哪条
后端链 + 缓存键」，具体后端（音色/参数/请求体/响应解析）由 provider 自己声明。
接入新 TTS 见 ``pet/tts/base.py`` 的模块文档；本模块按历史名再导出 edge 的音色与
参数工具，外部 import 点零改动。

职责：
- 配置默认值与逐项清洗（与 config.py 平铺键对应）；
- 报时调度判定（整点 / 每30分钟 / 每15分钟 / 每5分钟 / 每分钟 / 自定义
  时间点）与“距下一报时点秒数”计算；
- 报时文本组装：语音口播（中文数字，供 TTS 与缓存键）与气泡展示（阿拉伯数字）
  两套文本解耦生成；
- 台词/歌词轮换：库按 8 小时周期整体换批，同一周期内按序轮换取不同条目；
- 自定义台词/歌词解析（留空回退内置库）；
- 合成尝试链（主后端 → 后备后端）与缓存键（含后端，按 provider 的 flavor）。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import tts
from .tts import edge as _edge_provider
from .tts import mimo as _mimo_provider
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

# edge-tts 的音色/参数常量与清洗函数现在住在 pet/tts/edge.py：
# 这里按历史名再导出，既有 import 点（设置页、测试、文档）零改动。
DEFAULT_VOICE = _edge_provider.DEFAULT_VOICE
DEFAULT_RATE = _edge_provider.DEFAULT_RATE
DEFAULT_PITCH = _edge_provider.DEFAULT_PITCH
VOICE_OPTIONS = _edge_provider.VOICE_OPTIONS
clean_voice = _edge_provider.clean_voice
clean_rate = _edge_provider.clean_rate
clean_pitch = _edge_provider.clean_pitch
edge_rate_arg = _edge_provider.edge_rate_arg
edge_pitch_arg = _edge_provider.edge_pitch_arg

# 小米 MiMo 的常量/纯函数同样在 pet/tts/mimo.py，按历史名再导出。
MIMO_BASE_URL = _mimo_provider.MIMO_BASE_URL
MIMO_CHAT_PATH = _mimo_provider.MIMO_CHAT_PATH
MIMO_MODEL = _mimo_provider.MIMO_MODEL
MIMO_MODEL_VOICE_DESIGN = _mimo_provider.MIMO_MODEL_VOICE_DESIGN
MIMO_MODELS = _mimo_provider.MIMO_MODELS
DEFAULT_MIMO_MODEL = _mimo_provider.DEFAULT_MIMO_MODEL
MIMO_VOICE_OPTIONS = _mimo_provider.MIMO_VOICE_OPTIONS
DEFAULT_MIMO_VOICE = _mimo_provider.DEFAULT_MIMO_VOICE
DEFAULT_MIMO_STYLE = _mimo_provider.DEFAULT_MIMO_STYLE
MIMO_STYLE_MAX_LEN = _mimo_provider.MIMO_STYLE_MAX_LEN
MIMO_AUDIO_FORMAT = _mimo_provider.MIMO_AUDIO_FORMAT
MIMO_TIMEOUT_S = _mimo_provider.MIMO_TIMEOUT_S
clean_mimo_model = _mimo_provider.clean_mimo_model
clean_mimo_voice = _mimo_provider.clean_mimo_voice
clean_mimo_style = _mimo_provider.clean_mimo_style
mimo_messages = _mimo_provider.mimo_messages
mimo_payload = _mimo_provider.mimo_payload
parse_mimo_audio = _mimo_provider.parse_mimo_audio

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

# ---------------------------------------------------------------- 合成后端
# 后端清单/标签来自注册表（pet/tts）：新增 provider 后这里自动跟着变，不需要改本文件。
# 本模块仍是纯逻辑层：只看「后端名 + 参数 + 合成计划」，不 import 任何网络或 TTS 库——
# 真正的合成在 provider.synth() 里，由 pet/voice_chime_service.py 的后台线程调用。
BACKEND_EDGE = _edge_provider.PROVIDER.id
BACKEND_MIMO = _mimo_provider.PROVIDER.id
BACKENDS: tuple[str, ...] = tts.provider_ids()
BACKEND_LABELS = tts.labels()
# 默认走小米（用户点名要的），失败时按 voice_chime_tts_fallback 回退带 is_fallback 的后端。
DEFAULT_BACKEND = BACKEND_MIMO
DEFAULT_TTS_FALLBACK = True

_CUSTOM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

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
    """语音报时配置默认值（config.py 顶层平铺键的镜像）。

    合成后端那几项由 provider 自己声明（``pet/tts`` 的 ``fields``），这里遍历生成——
    接入新 TTS 不需要改本函数，也不会漏登记。
    """
    config = {
        "voice_chime_enabled": False,
        "voice_chime_schedule": "hourly",
        "voice_chime_custom_times": "",
        "voice_chime_volume": DEFAULT_VOLUME,
        "voice_chime_show_bubble": DEFAULT_SHOW_BUBBLE,
        "voice_chime_show_quote": DEFAULT_SHOW_QUOTE,
        "voice_chime_custom_quotes_zh": "",  # 自定义中文台词/歌词（一行一条，留空用内置库）
        "voice_chime_custom_quotes_en": "",  # 自定义英文台词/歌词（一行一条，留空用内置库）
        "voice_chime_tts_backend": DEFAULT_BACKEND,  # 主后端（注册表里的 provider id）
        "voice_chime_tts_fallback": DEFAULT_TTS_FALLBACK,  # 主后端失败自动回退后备后端
    }
    for provider in tts.providers():
        for spec in provider.fields:
            if spec.kind == "secret":
                continue  # 凭据存系统钥匙串，不进 config
            config[spec.key] = spec.default
    return config



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


def clean_backend(value) -> str:
    """清洗合成后端 id：必须是已注册的 provider，非法值回落默认后端。"""
    text = str(value or "").strip().lower()
    return text if text in tts.provider_ids() else DEFAULT_BACKEND


def synth_ext(backend) -> str:
    """该后端产物的扩展名（缓存文件名用）：由 provider 的合成计划给出。"""
    provider = tts.get(clean_backend(backend))
    if provider is None:
        return "mp3"
    return str(provider.plan(provider.values({})).get("ext") or "mp3")


def synth_attempts(cfg: dict, secrets: dict | None = None) -> tuple[tts.TtsAttempt, ...]:
    """按配置给出合成尝试序列（主后端优先，再回退带 ``is_fallback`` 的后端）。

    每项是 :class:`pet.tts.TtsAttempt`（``provider`` / ``values`` / ``plan``）。
    纯函数：不探测环境、不读凭据——「现在能不能用」由 ``provider.availability`` 判定，
    密钥由调用方经 ``secrets[provider_id][字段名]`` 注入，因此单测不需要网络与钥匙串。
    """
    backend = clean_backend(cfg.get("backend", DEFAULT_BACKEND))
    order = [backend]
    if clean_flag(cfg.get("fallback", DEFAULT_TTS_FALLBACK), DEFAULT_TTS_FALLBACK):
        order.extend(tts.fallback_ids(exclude=backend))
    values_map = cfg.get("providers") or {}
    secret_map = secrets or {}
    attempts: list[tts.TtsAttempt] = []
    for provider_id in order:
        provider = tts.get(provider_id)
        if provider is None:
            continue
        values = dict(values_map.get(provider_id) or provider.values({}))
        injected = secret_map.get(provider_id) or {}
        for spec in tts.secret_fields(provider):
            values[spec.name] = str(injected.get(spec.name) or "")
        attempts.append(
            tts.TtsAttempt(provider=provider_id, values=values, plan=provider.plan(values))
        )
    return tuple(attempts)



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


def clean_volume(value) -> int:
    """清洗音量（0-100）。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_VOLUME
    return max(0, min(100, number))


def normalize_chime_config(config) -> dict:
    """从 config 对象读取并清洗语音报时全部键（config 缺失字段用默认值）。

    ``providers`` 是各后端的字段值表（密钥留空，服务层按需注入）；``voice`` /
    ``rate`` / ``pitch`` / ``mimo_*`` 是历史平铺键，供既有调用点与设置页读取，
    值取自同一张表，两套名字不会分叉。
    """
    if config is None:
        config = {}
    providers: dict[str, dict] = {}
    for provider in tts.providers():
        values = provider.values(config)
        for spec in tts.secret_fields(provider):
            values[spec.name] = ""  # 凭据不由纯逻辑层读
        providers[provider.id] = values
    edge_values = providers.get(BACKEND_EDGE, {})
    mimo_values = providers.get(BACKEND_MIMO, {})
    return {
        "enabled": bool(config.get("voice_chime_enabled", False)),
        "schedule": clean_schedule(config.get("voice_chime_schedule", "hourly")),
        "custom_times": clean_custom_times(config.get("voice_chime_custom_times", "")),
        "volume": clean_volume(config.get("voice_chime_volume", DEFAULT_VOLUME)),
        "show_bubble": clean_flag(
            config.get("voice_chime_show_bubble", DEFAULT_SHOW_BUBBLE), DEFAULT_SHOW_BUBBLE
        ),
        "show_quote": clean_flag(
            config.get("voice_chime_show_quote", DEFAULT_SHOW_QUOTE), DEFAULT_SHOW_QUOTE
        ),
        "custom_quotes_zh": clean_custom_quotes(config.get("voice_chime_custom_quotes_zh", "")),
        "custom_quotes_en": clean_custom_quotes(config.get("voice_chime_custom_quotes_en", "")),
        "backend": clean_backend(config.get("voice_chime_tts_backend", DEFAULT_BACKEND)),
        "fallback": clean_flag(
            config.get("voice_chime_tts_fallback", DEFAULT_TTS_FALLBACK), DEFAULT_TTS_FALLBACK
        ),
        "providers": providers,
        # —— 历史平铺键（兼容既有调用点）——
        "voice": edge_values.get("voice", DEFAULT_VOICE),
        "rate": edge_values.get("rate", DEFAULT_RATE),
        "pitch": edge_values.get("pitch", DEFAULT_PITCH),
        "mimo_model": mimo_values.get("model", DEFAULT_MIMO_MODEL),
        "mimo_voice": mimo_values.get("voice", DEFAULT_MIMO_VOICE),
        "mimo_style": mimo_values.get("style", DEFAULT_MIMO_STYLE),
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


def cache_key(text: str, cfg: dict, provider_id: str | None = None) -> str:
    """音频缓存文件名键：内容 + 该后端 flavor 的短哈希。

    flavor 由 provider 给（只含影响音频内容的参数），因此换后端 / 换音色 / 换风格都会
    换键，不同后端的缓存不会互串；edge 的 flavor 保持历史格式，老缓存升级后仍命中。
    """
    import hashlib

    backend = clean_backend(provider_id or cfg.get("backend", BACKEND_EDGE))
    provider = tts.get(backend)
    if provider is None:
        raw = f"{text}|{backend}"
    else:
        values = (cfg.get("providers") or {}).get(backend)
        if values is None:
            # 紧凑调用（传的是原始 config 映射）：让 provider 自己按字段 key 取值
            values = provider.values(cfg)
        raw = f"{text}|{provider.flavor(values)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
