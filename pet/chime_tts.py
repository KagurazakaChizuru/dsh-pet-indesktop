"""整点报时语音播报：edge-tts 合成 + QtMultimedia 播放。

设计：
- 中文音色清单 EDGE_VOICES 供设置页下拉选择；
- 合成在后台线程执行（edge-tts 为 asyncio 网络 IO），完成后经信号
  桥回 GUI 线程调用 click_sound.play_sound 播放（复用点击音效播放器池）；
- 合成结果按 (voice, text) 哈希缓存到 config.dir/chime_tts_cache，避免重复合成。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import click_sound

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "zh-CN-XiaoyiNeural"

# 中文音色清单：(显示名, voice id)。取自 edge-tts 官方 voices 列表的中文子集。
# 可爱/自然的女性音色置顶，便于直接选用。
EDGE_VOICES: list[tuple[str, str]] = [
    ("晓伊（女·活泼可爱）", "zh-CN-XiaoyiNeural"),
    ("晓梦（女·甜美）", "zh-CN-XiaomengNeural"),
    ("晓双（女·童声）", "zh-CN-XiaoshuangNeural"),
    ("晓辰（女·少女）", "zh-CN-XiaochenNeural"),
    ("晓晓（女·温暖）", "zh-CN-XiaoxiaoNeural"),
    ("晓萱（女·自然）", "zh-CN-XiaoxuanNeural"),
    ("晓墨（女·温柔）", "zh-CN-XiaomoNeural"),
    ("晓涵（女·清亮）", "zh-CN-XiaohanNeural"),
    ("晓梦（女·甜美）", "zh-CN-XiaomengNeural"),
    ("晓秋（女·柔和）", "zh-CN-XiaoqiuNeural"),
    ("晓睿（女·成熟）", "zh-CN-XiaoruiNeural"),
    ("晓双（女·童声）", "zh-CN-XiaoshuangNeural"),
    ("晓颜（女·自然）", "zh-CN-XiaoyanNeural"),
    ("晓悠（女·柔和）", "zh-CN-XiaoyouNeural"),
    ("晓辰（女·少儿）", "zh-CN-XiaochenNeural"),
    ("晓甄（女·知性）", "zh-CN-XiaozhenNeural"),
    ("云希（男·阳光）", "zh-CN-YunxiNeural"),
    ("云健（男·沉稳）", "zh-CN-YunjianNeural"),
    ("云扬（男·新闻）", "zh-CN-YunyangNeural"),
    ("云枫（男·大气）", "zh-CN-YunfengNeural"),
    ("云皓（男·深沉）", "zh-CN-YunhaoNeural"),
    ("云杰（男·活力）", "zh-CN-YunjieNeural"),
    ("云夏（男·少年）", "zh-CN-YunxiaNeural"),
]

_VOICE_IDS = frozenset(voice for _, voice in EDGE_VOICES)


def voice_display_name(voice_id: str) -> str:
    """音色 id → 显示名；未知 id 原样返回。"""
    for label, vid in EDGE_VOICES:
        if vid == voice_id:
            return label
    return voice_id


def normalize_voice(voice: str) -> str:
    """音色归一：已知清单或合法自定义（zh-CN-xxxNeural）放行，否则回退默认。"""
    text = str(voice or "").strip()
    if text in _VOICE_IDS:
        return text
    if text.startswith("zh-CN-") and text.endswith("Neural"):
        return text
    return DEFAULT_VOICE


def synthesize_to_file(text: str, voice: str, out_path: Path,
                       rate: int = 0, pitch: int = 0) -> bool:
    """同步合成 mp3 到 out_path（后台线程调用）。失败返回 False。

    rate/pitch：edge-tts 语速（%）与音调（Hz）偏移，0 表示默认。
    """
    try:
        import edge_tts
    except ImportError:
        logger.error("未安装 edge-tts，无法语音播报。请执行: pip install edge-tts")
        return False
    try:
        kwargs = {}
        if rate:
            kwargs["rate"] = f"{rate:+d}%"
        if pitch:
            kwargs["pitch"] = f"{pitch:+d}Hz"
        asyncio.run(edge_tts.Communicate(text, voice, **kwargs).save(str(out_path)))
        return True
    except Exception:
        logger.exception("edge-tts 合成失败: voice=%s rate=%s pitch=%s", voice, rate, pitch)
        return False


class _TtsBridge(QObject):
    """合成完成信号桥：子线程合成 → 主线程播放。"""

    ready = Signal(str, bool, float)  # (mp3_path, ok, volume)

    _instance: "_TtsBridge | None" = None

    @classmethod
    def instance(cls) -> "_TtsBridge":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class ChimeTts:
    """语音播报入口：缓存命中直接播放；未命中后台合成后播放。"""

    def __init__(self, cache_dir: Path | str) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._bridge = _TtsBridge.instance()
        # 信号只在 GUI 线程首次使用时连接（模块级单例信号桥不重复连接）
        if not getattr(self._bridge, "_chime_connected", False):
            self._bridge.ready.connect(self._on_ready)
            self._bridge._chime_connected = True

    def _cached_path(self, text: str, voice: str, rate: int = 0, pitch: int = 0) -> Path:
        key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode("utf-8")).hexdigest()[:20]
        return self._cache_dir / f"{key}.mp3"

    def speak(self, text: str, voice: str = DEFAULT_VOICE, volume: float = 1.0,
              rate: int = 0, pitch: int = 0) -> bool:
        """合成并播放；返回 True 表示已发起（含缓存命中直接播放）。"""
        voice = normalize_voice(voice)
        path = self._cached_path(text, voice, rate, pitch)
        if path.is_file() and path.stat().st_size > 0:
            return click_sound.play_sound(path, volume=volume)
        threading.Thread(
            target=self._synth_and_play,
            args=(text, voice, volume, path, rate, pitch),
            daemon=True,
        ).start()
        return True

    def _synth_and_play(self, text: str, voice: str, volume: float,
                        path: Path, rate: int, pitch: int) -> None:
        ok = synthesize_to_file(text, voice, path, rate=rate, pitch=pitch)
        # 通过信号桥回主线程播放（QtMultimedia 必须在 GUI 线程）
        self._bridge.ready.emit(str(path), ok, volume)

    def _on_ready(self, path: str, ok: bool, volume: float) -> None:
        if not ok:
            return
        try:
            click_sound.play_sound(Path(path), volume=volume)
        except Exception:
            logger.exception("语音播放失败（路径=%s）", path)
