"""整点报时核心逻辑（纯 Python，模块顶层无 Qt）。

分层与 todo_reminder.py 相同：
- 纯函数负责时刻计算 / 配置清洗 / 文案拼装；
- 台词库存独立 JSON（chime_quotes.json），ChimeStore 读写；
- GUI 线程调度见 chime_service.py。
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ------------------------------------------------------------ 默认台词库

# 内置电影台词（30 条，经典公知短句；用户可在设置页覆盖）
MOVIE_QUOTES: list[str] = [
    "生活就像一盒巧克力，你永远不知道下一颗是什么味道。——《阿甘正传》",
    "做人如果没梦想，跟咸鱼有什么分别。——《少林足球》",
    "曾经有一份真诚的爱情放在我面前，我没有珍惜。——《大话西游》",
    "希望是美好的，也许是人间至善，而美好的事物永不消逝。——《肖申克的救赎》",
    "如果你有梦想的话，就要去捍卫它。——《当幸福来敲门》",
    "昨天已是历史，明天还是个谜，今天则是上天赐予的礼物。——《功夫熊猫》",
    "让子弹飞一会儿。——《让子弹飞》",
    "我命由我不由天。——《哪吒之魔童降世》",
    "能力越大，责任越大。——《蜘蛛侠》",
    "道路千万条，安全第一条。——《流浪地球》",
    "你跳，我也跳。——《泰坦尼克号》",
    "不疯魔，不成活。——《霸王别姬》",
    "每个人都会经过这个阶段，见到一座山，就想知道山后面是什么。——《东邪西毒》",
    "不管前方的路有多苦，只要走的方向正确，都比站在原地更接近幸福。——《千与千寻》",
    "生活坏到一定程度就会好起来，因为它无法更坏。——《龙猫》",
    "世界这么大，人生这么长，总会有这么一个人，让你想要温柔地对待。——《哈尔的移动城堡》",
    "爱是唯一可以超越时间与空间的事物。——《星际穿越》",
    "一个人只有一个命运。——《教父》",
    "我等了三年，就是要等一个机会。——《英雄本色》",
    "对不起，我是警察。——《无间道》",
    "秋刀鱼会过期，肉罐头会过期，连保鲜纸都会过期，我开始怀疑，这个世界上还有什么东西是不会过期的。——《重庆森林》",
    "及时采撷你的花蕾，旧时光一去不回。——《死亡诗社》",
    "这枚面具之下不只是血肉，而是一个理念。——《V字仇杀队》",
    "于是我们奋力前行，逆水行舟，被不断地向后推，直至回到往昔岁月。——《了不起的盖茨比》",
    "我们笑着说再见，却深知再见遥遥无期。——《海上钢琴师》",
    "永远不要说永远，总有东西要去尝试。——《放牛班的春天》",
    "开拓视野，冲破艰险，看见世界，身临其境，贴近彼此，感受生活。——《白日梦想家》",
    "人心其实很脆弱，所以我们要经常哄哄它。——《三傻大闹宝莱坞》",
    "奖牌不会长在树上，得努力争取。——《摔跤吧！爸爸》",
    "真正的死亡是世界上再没有一个人记得你。——《寻梦环游记》",
]

# 内置歌词（30 条，经典单句；用户可在设置页覆盖）
SONG_LYRICS: list[str] = [
    "原谅我这一生不羁放纵爱自由。——《海阔天空》",
    "风雨中抱紧自由。——《光辉岁月》",
    "是你多么温馨的目光，教我坚毅望着前路。——《真的爱你》",
    "故事的小黄花，从出生那年就飘着。——《晴天》",
    "雨下整夜，我的爱溢出就像雨水。——《七里香》",
    "还记得你说家是唯一的城堡，随着稻香河流继续奔跑。——《稻香》",
    "天青色等烟雨，而我在等你。——《青花瓷》",
    "繁华如三千东流水，我只取一瓢爱了解。——《发如雪》",
    "该配合你演出的我演视而不见。——《演员》",
    "和我在成都的街头走一走，直到所有的灯都熄灭了也不停留。——《成都》",
    "我曾经跨过山和大海，也穿过人山人海。——《平凡之路》",
    "我曾将青春翻涌成她，也曾指尖弹出盛夏。——《起风了》",
    "时间是让人猝不及防的东西。——《岁月神偷》",
    "原来你是我最想留住的幸运。——《小幸运》",
    "后来，我总算学会了如何去爱。——《后来》",
    "可惜不是你，陪我到最后。——《可惜不是你》",
    "爱真的需要勇气，来面对流言蜚语。——《勇气》",
    "知了也睡了，安心地睡了。——《宁夏》",
    "我知道我一直有双隐形的翅膀，带我飞，飞过绝望。——《隐形的翅膀》",
    "爱是一道光，如此美妙。——《欧若拉》",
    "谁都只得那双手，靠拥抱亦难任你拥有。——《富士山下》",
    "十年之前，我不认识你，你不属于我。——《十年》",
    "你当我是浮夸吧，夸张只因我很怕。——《浮夸》",
    "有时候，有时候，我会相信一切有尽头。——《红豆》",
    "如果再见不能红着眼，是否还能红着脸。——《匆匆那年》",
    "没有了联络，后来的生活，我都是听人说。——《说好不哭》",
    "像我这样优秀的人，本该灿烂过一生。——《像我这样的人》",
    "一杯敬朝阳，一杯敬月光。——《消愁》",
    "还要多远才能进入你的心，还要多久才能和你接近。——《水星记》",
    "我只想唱这一首老掉牙的歌。——《老男孩》",
]

QUOTES_VERSION = 1


def default_quotes_data() -> dict:
    """台词库默认数据：空 = 使用内置库。"""
    return {
        "version": QUOTES_VERSION,
        "movies": list(MOVIE_QUOTES),
        "lyrics": list(SONG_LYRICS),
    }


# ------------------------------------------------------------ 配置清洗

def default_chime_data() -> dict:
    """整点报时配置默认值。"""
    return {
        "enabled": True,
        "hourly_enabled": True,
        "interval_minutes": 0,          # 0=仅整点；15/30/60=按分钟间隔报时
        "hour_start": "08:00",
        "hour_end": "22:00",
        "custom_times": [],
        "speech_enabled": True,
        "voice": "zh-CN-XiaoyiNeural",
        "voice_custom": "",             # 自定义音色 ID，非空时优先于 voice
        "rate": 0,                      # 语速偏移（%），-50 ~ +50
        "pitch": 0,                     # 音调偏移（Hz），-50 ~ +50
        "volume": 1.0,
        "quote_enabled": True,
    }


def _parse_hhmm(value, default: str) -> str:
    """解析 HH:MM，非法回退 default。"""
    try:
        text = str(value).strip()
        hour, minute = text.split(":")
        hh, mm = int(hour), int(minute)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
    except (TypeError, ValueError):
        pass
    return default


def _parse_hms(value) -> str | None:
    """解析 HH:MM:SS，非法返回 None。"""
    try:
        text = str(value).strip()
        parts = text.split(":")
        if len(parts) != 3:
            return None
        hh, mm, ss = int(parts[0]), int(parts[1]), int(parts[2])
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
    except (TypeError, ValueError):
        pass
    return None


_VOICE_PATTERN_PREFIX = "zh-CN-"


def _voice_valid(value) -> bool:
    """音色宽松校验：格式为 zh-CN-xxxNeural；具体存在性由 edge-tts 层兜底。"""
    text = str(value or "").strip()
    return text.startswith(_VOICE_PATTERN_PREFIX) and text.endswith("Neural")


def clean_chime_data(value) -> dict:
    """清洗整点报时配置（同 dynamic_island 规约：白名单字段 + 类型归一）。"""
    defaults = default_chime_data()
    if not isinstance(value, dict):
        return dict(defaults)
    result = dict(defaults)
    result.update({k: v for k, v in value.items() if k in defaults})
    result["enabled"] = bool(result["enabled"])
    result["hourly_enabled"] = bool(result["hourly_enabled"])
    result["speech_enabled"] = bool(result["speech_enabled"])
    result["quote_enabled"] = bool(result["quote_enabled"])
    try:
        interval = int(result.get("interval_minutes", 0))
        result["interval_minutes"] = interval if interval in (15, 30, 60) else 0
    except (TypeError, ValueError):
        result["interval_minutes"] = 0
    result["hour_start"] = _parse_hhmm(result.get("hour_start"), defaults["hour_start"])
    result["hour_end"] = _parse_hhmm(result.get("hour_end"), defaults["hour_end"])
    raw_times = result.get("custom_times")
    times: list[str] = []
    if isinstance(raw_times, (list, tuple, set)):
        for item in raw_times:
            parsed = _parse_hms(item)
            if parsed is not None and parsed not in times:
                times.append(parsed)
    times.sort()
    result["custom_times"] = times[:50]
    voice = str(result.get("voice") or "").strip()
    result["voice"] = voice if _voice_valid(voice) else defaults["voice"]
    custom_voice = str(result.get("voice_custom") or "").strip()
    result["voice_custom"] = custom_voice if _voice_valid(custom_voice) else ""
    try:
        result["rate"] = max(-50, min(50, int(result.get("rate", 0))))
    except (TypeError, ValueError):
        result["rate"] = 0
    try:
        result["pitch"] = max(-50, min(50, int(result.get("pitch", 0))))
    except (TypeError, ValueError):
        result["pitch"] = 0
    try:
        result["volume"] = max(0.0, min(1.0, float(result.get("volume", 1.0))))
    except (TypeError, ValueError):
        result["volume"] = defaults["volume"]
    return result


# ------------------------------------------------------------ 时刻计算

def current_chime_keys(now: datetime, cfg: dict) -> set[str]:
    """当前时刻命中的报时键集合（空 = 无报时点）。

    - hour:*：整点（minute==0 且 second==0），且在 [hour_start, hour_end] 区间；
    - interval:*：按 interval_minutes（15/30/60）命中分钟，second==0 且落在区间；
    - custom:*：精确命中自定义时刻（HH:MM:SS）。
    键含日期，天然跨天不串扰；同一秒只触发一次。
    """
    keys: set[str] = set()
    interval = int(cfg.get("interval_minutes") or 0)
    if interval in (15, 30, 60):
        if now.second == 0 and now.minute % interval == 0:
            hhmm = now.strftime("%H:%M")
            start = str(cfg.get("hour_start") or "08:00")
            end = str(cfg.get("hour_end") or "22:00")
            if start <= hhmm <= end:
                keys.add(f"interval:{now.strftime('%Y-%m-%d %H:%M')}")
    elif bool(cfg.get("hourly_enabled", True)):
        if now.minute == 0 and now.second == 0:
            hhmm = now.strftime("%H:%M")
            start = str(cfg.get("hour_start") or "08:00")
            end = str(cfg.get("hour_end") or "22:00")
            if start <= hhmm <= end:
                keys.add(f"hour:{now.strftime('%Y-%m-%d %H')}")
    custom = cfg.get("custom_times") or []
    if custom:
        hms = now.strftime("%H:%M:%S")
        if hms in custom:
            keys.add(f"custom:{now.strftime('%Y-%m-%d')} {hms}")
    return keys


def period_hour_text(now: datetime) -> str:
    """把时间转成中文时段描述，如「下午 3 点整」。"""
    hour = now.hour
    if hour == 0:
        period, hour12 = "凌晨", 12
    elif hour < 6:
        period, hour12 = "凌晨", hour
    elif hour < 12:
        period, hour12 = "上午", hour
    elif hour == 12:
        period, hour12 = "中午", 12
    elif hour < 18:
        period, hour12 = "下午", hour - 12
    else:
        period, hour12 = "晚上", hour - 12
    return f"{period}{hour12} 点整"


def chime_text(now: datetime, cfg: dict, quote: str = "", kind: str = "hour") -> str:
    """报时文案：时间主体 + 可选随机台词/歌词。"""
    if kind == "custom":
        text = f"现在是 {now.strftime('%H:%M:%S')}"
    elif kind == "interval":
        text = f"现在是{now.strftime('%H:%M')}"
    else:
        text = f"现在是{period_hour_text(now)}"
    quote = (quote or "").strip()
    if quote and bool(cfg.get("quote_enabled", True)):
        text = f"{text}\n{quote}"
    return text


# ------------------------------------------------------------ 台词库存储

def quotes_path(config_dir, instance_id: str = "") -> Path:
    """台词库文件路径：多开实例跟随 config 文件命名惯例。"""
    name = f"chime_quotes-{instance_id}.json" if instance_id else "chime_quotes.json"
    return Path(config_dir) / name


def _clean_quote_lines(value, fallback: list[str]) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return list(fallback)
    lines: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in lines:
            lines.append(text[:120])
    return lines or list(fallback)


class ChimeStore:
    """chime_quotes.json 的读写：读侧清洗容错，写侧原子替换（同 TodoStore）。"""

    def __init__(self, path) -> None:
        self.path = Path(path)

    def load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        return {
            "movies": _clean_quote_lines(raw.get("movies"), MOVIE_QUOTES),
            "lyrics": _clean_quote_lines(raw.get("lyrics"), SONG_LYRICS),
        }

    def save(self, data: dict) -> bool:
        payload = {
            "version": QUOTES_VERSION,
            "movies": _clean_quote_lines(data.get("movies"), MOVIE_QUOTES),
            "lyrics": _clean_quote_lines(data.get("lyrics"), SONG_LYRICS),
        }
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return True
        except OSError:
            logger.exception("台词库写入失败：%s", self.path)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def pick_quote(self, enabled: bool = True) -> str:
        """随机挑一句台词或歌词；关闭或库为空时返回空串。"""
        if not enabled:
            return ""
        data = self.load()
        pool = [item for item in data.get("movies", []) + data.get("lyrics", []) if item.strip()]
        if not pool:
            return ""
        return random.choice(pool)
