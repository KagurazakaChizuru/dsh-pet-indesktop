# -*- coding: utf-8 -*-
"""豆包（火山引擎语音合成 2.0）provider —— SSE 单向流式 + 本地变调。

接口（2026-10-13 实测打通，见 docs/PR-REPORT 与记忆）：
```
POST https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse
X-Api-Key:         <「API Key 管理」页的 API Key，存钥匙串>
X-Api-Resource-Id: seed-tts-2.0      ← 2.0 的固定资源号；别的值一律 not granted
X-Api-Request-Id:  <uuid>
body: {"user":{"uid":…},"req_params":{"text":…,"speaker":"<2.0 音色>",
       "audio_params":{"format":"mp3","sample_rate":24000}}}
```
响应是 SSE：成功码 `code=0` / `20000000`，音频是**逐片 base64**（要全部拼接）；
`55000000`＝音色与 resource 不匹配（2.0 音色名字里带 `uranus`）。

**音调**：2.0 接口不吃音调参数（`pitch_rate`/`pitch`/`pitch_ratio` 实测均被忽略），
所以音调在本地用 ffmpeg 变调（`asetrate` + `aresample` + `atempo`，**时长不变**）。
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .base import TtsField, TtsProvider, TtsUnavailable, register

PROVIDER_ID = "doubao"
LABEL = "豆包语音 2.0（火山引擎）"
ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse"
RESOURCE_ID = "seed-tts-2.0"
SAMPLE_RATE = 24000
SECRET_REF = "tts/doubao_api_key"
AVAILABILITY_CODE = "doubao_key_missing"
MISSING_MESSAGE = (
    "豆包的 API Key 没配：在火山控制台「豆包语音 → API Key 管理」里那串 UUID，"
    "填进设置页即可（只存系统钥匙串，不写进配置文件）。"
)
TIMEOUT_S = 60
#: 常用 2.0 音色（名字带 uranus 的才是 2.0；完整表见 ark-skills 的 voices.md）
VOICE_OPTIONS = (
    ("zh_female_peiqi_uranus_bigtts", "佩奇猪（儿童，机主选定）"),
    ("zh_female_xiaoxue_uranus_bigtts", "儿童绘本"),
    ("zh_male_tiancaitongsheng_uranus_bigtts", "天才童声"),
    ("zh_female_yingtaowanzi_uranus_bigtts", "樱桃丸子"),
    ("zh_female_vv_uranus_bigtts", "Vivi（通用女声）"),
    ("zh_female_sophie_uranus_bigtts", "魅力苏菲"),
)


class DoubaoTtsProvider(TtsProvider):
    id = PROVIDER_ID
    label = LABEL
    is_fallback = False
    availability_code = AVAILABILITY_CODE
    unavailable_message = MISSING_MESSAGE
    fields = (
        TtsField(
            "voice", "voice_chime_doubao_speaker", "音色",
            "2.0 音色（名字里带 uranus）；配错会得到 55000000「音色与资源不匹配」。"
            "完整音色表见 ark-skills 的 voices.md。",
            kind="select", default="zh_female_peiqi_uranus_bigtts", options=VOICE_OPTIONS,
            allow_custom=True,
        ),
        TtsField(
            "pitch", "voice_chime_doubao_pitch", "音调（本地变调）",
            "0–30（%）。2.0 接口不支持音调，这里在本地用 ffmpeg 变调、**时长不变**"
            "——机主实测 15% 合适；调太高会有金属感。",
            kind="number", default=15, minimum=0, maximum=30, suffix="%",
        ),
        TtsField(
            "api_key", "voice_chime_doubao_api_key", "API Key",
            "火山控制台「豆包语音 → API Key 管理」里那串 UUID。只存系统钥匙串；"
            "留空表示不改动已保存的值。",
            kind="secret", default="", secret_ref=SECRET_REF,
        ),
    )

    # ------------------------------------------------------------ 合同
    def plan(self, values: dict) -> dict:
        return {
            "provider": self.id,
            "api_key": str(values.get("api_key") or "").strip(),
            "speaker": str(values.get("voice") or "").strip() or "zh_female_peiqi_uranus_bigtts",
            "pitch": max(0, min(30, _as_int(values.get("pitch"), 15))),
            "ext": "mp3",
        }

    def flavor(self, values: dict) -> str:
        # 只放影响音频内容的参数（凭据不进缓存键）
        speaker = str(values.get("voice") or "").strip() or "zh_female_peiqi_uranus_bigtts"
        return f"doubao|{speaker}|{max(0, min(30, _as_int(values.get('pitch'), 15)))}"

    def availability(self, values: dict) -> str:
        return "" if str(values.get("api_key") or "").strip() else AVAILABILITY_CODE

    def synth(self, text: str, plan: dict, out_path) -> None:
        key = str(plan.get("api_key") or "").strip()
        if not key:
            raise TtsUnavailable(AVAILABILITY_CODE)
        try:
            audio = _fetch(key, str(text or ""), str(plan.get("speaker") or ""))
        except TtsUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 —— 统一转成可读错误
            raise TtsUnavailable(AVAILABILITY_CODE, f"豆包合成失败：{exc}") from exc
        if not audio:
            raise TtsUnavailable(AVAILABILITY_CODE, "豆包返回空音频")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        pitch = max(0, min(30, _as_int(plan.get("pitch"), 15)))
        if pitch <= 0:
            out_path.write_bytes(audio)
        else:
            _write_with_pitch(audio, pitch, out_path)
        try:
            if not out_path.exists() or out_path.stat().st_size == 0:
                raise TtsUnavailable(AVAILABILITY_CODE, "豆包产物为空")
        except OSError as exc:
            raise TtsUnavailable(AVAILABILITY_CODE, f"豆包产物不可读：{exc}") from exc


def _fetch(api_key: str, text: str, speaker: str) -> bytes:
    body = {
        "user": {"uid": "dsh-pet"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {"format": "mp3", "sample_rate": SAMPLE_RATE},
        },
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-Request-Id": str(uuid.uuid4()),
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=TIMEOUT_S) as response:
        payload = response.read()
    chunks: list[bytes] = []
    for line in payload.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line.startswith("event:"):
            continue
        raw = line[5:].strip() if line.startswith("data:") else line
        try:
            frame = json.loads(raw)
        except Exception:
            continue
        candidate = frame.get("data") if isinstance(frame.get("data"), str) else None
        if candidate:
            try:
                chunks.append(base64.b64decode(candidate))
            except Exception:
                continue
            continue
        code = frame.get("code")
        if code not in (None, 0, 20000000):
            raise TtsUnavailable(
                AVAILABILITY_CODE,
                f"豆包返回 {code}：{str(frame.get('message') or '')}".strip(),
            )
    return b"".join(chunks)


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _write_with_pitch(audio: bytes, pitch_pct: int, out_path: Path) -> None:
    """本地变调（保时长）：asetrate 抬基频 → aresample 还原采样率 → atempo 拉回时长。

    ``pitch_pct <= 0`` 直接写原音、**不起子进程**（少一次无意义的窗口与开销）。
    """
    if pitch_pct <= 0:
        out_path.write_bytes(audio)
        return
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        out_path.write_bytes(audio)          # 没有 ffmpeg 就退回原音，不静默失败
        return
    factor = 1.0 + pitch_pct / 100.0
    source = Path(tempfile.mkdtemp(prefix="dsh-pet-doubao-")) / "raw.mp3"
    source.write_bytes(audio)
    filter_chain = (
        f"asetrate={SAMPLE_RATE}*{factor:.4f},aresample={SAMPLE_RATE},atempo={1 / factor:.6f}"
    )
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "quiet", "-i", str(source),
             "-af", filter_chain, "-b:a", "128k", str(out_path)],
            check=True, timeout=TIMEOUT_S,
            # 绝不弹控制台黑窗：机主对"又弹一个窗口"有明文红线（同 agent_link / harness_launcher 的写法）
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
    except Exception:
        out_path.write_bytes(audio)          # 变调失败不阻断播报
    finally:
        shutil.rmtree(source.parent, ignore_errors=True)


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


PROVIDER = register(DoubaoTtsProvider())
