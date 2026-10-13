# -*- coding: utf-8 -*-
"""科大讯飞在线语音合成（v2 WSS 流式）provider。

接口：`wss://tts-api.xfyun.cn/v2/tts`
- 鉴权＝**HMAC-SHA256 签名**（不是 Bearer）：签名原文
  ``host: tts-api.xfyun.cn\ndate: <RFC1123 GMT>\nGET /v2/tts HTTP/1.1``，
  用 ``api_secret`` 做 HMAC-SHA256 → base64 → 拼成 ``api_key="…", algorithm="hmac-sha256",
  headers="host date request-line", signature="…"`` 再整体 base64，放进 query 的 ``authorization``；
  ``date`` 与 ``host`` 也一并在 query 里回传。
- 请求帧：``common.app_id`` + ``business{aue,sfl,tte,vcn,...}`` + ``data{status:2, text: base64}``
- 响应帧：``data.audio`` 是 **base64 音频分片**，``data.status == 2`` 表示最后一帧；
  ``code != 0`` 是错误（带上 ``message``）。
- 客户端用 ``aiohttp``（edge-tts 已带进包，**不引入新依赖**）；``synth`` 是同步接口，
  内部 ``asyncio.run`` 一把（与 edge provider 同一约定：只在合成线程里付这笔成本）。

凭据：``app_id`` 是明文配置键；``api_key`` / ``api_secret`` 走 ``kind="secret"`` +
``secret_ref``，**只存系统钥匙串**，不进 config.json、不进日志、不进 flavor（缓存键）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from email.utils import formatdate
from urllib.parse import quote

from .base import TtsField, TtsProvider, TtsUnavailable, register

PROVIDER_ID = "xfyun"
LABEL = "科大讯飞（在线，签名鉴权）"
HOST = "tts-api.xfyun.cn"
PATH = "/v2/tts"
AVAILABILITY_CODE = "xfyun_credentials_missing"
MISSING_MESSAGE = (
    "讯飞的凭据没配全：需要 APPID / APIKey / APISecret 三件（在 xfyun.cn 控制台创建应用并开通"
    "「在线语音合成」后可见）。APIKey 与 APISecret 只存系统钥匙串。"
)
SECRET_REF_KEY = "tts/xfyun_api_key"
SECRET_REF_SECRET = "tts/xfyun_api_secret"
SYNTH_TIMEOUT_S = 30.0

#: 常用音色（完整清单在控制台；留 ``allow_custom`` 允许手填新音色，如超拟人那档）
VOICE_OPTIONS = (
    ("xiaoyan", "小燕（女声，经典）"),
    ("aisjiuxu", "许久（男声）"),
    ("aisjinger", "小婧（女声）"),
    ("aisbabyxu", "许小宝（童声）"),
    ("x4_yezi", "叶子（女声，较新）"),
)


def build_auth_url(api_key: str, api_secret: str, *, date: str | None = None,
                   host: str = HOST, path: str = PATH) -> tuple[str, str]:
    """返回 ``(wss url, 用到的 date)``。``date`` 可注入以便单测/复现。"""
    stamp = date or formatdate(usegmt=True)
    origin = f"host: {host}\ndate: {stamp}\nGET {path} HTTP/1.1"
    digest = hmac.new(str(api_secret).encode("utf-8"), origin.encode("utf-8"), hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode("ascii")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("ascii")
    url = (
        f"wss://{host}{path}?authorization={quote(authorization)}"
        f"&date={quote(stamp)}&host={quote(host)}"
    )
    return url, stamp


def build_payload(app_id: str, text: str, voice: str, speed: int) -> dict:
    """请求帧：文本按 UTF8 走 base64，``aue=lame`` 即 mp3。"""
    return {
        "common": {"app_id": app_id},
        "business": {
            "aue": "lame",
            "sfl": 1,                 # 流式返回
            "tte": "UTF8",
            "vcn": voice,
            "speed": max(0, min(100, int(speed))),
            "volume": 50,
            "pitch": 50,
        },
        "data": {"status": 2, "text": base64.b64encode(text.encode("utf-8")).decode("ascii")},
    }


class XfyunTtsProvider(TtsProvider):
    id = PROVIDER_ID
    label = LABEL
    is_fallback = False
    availability_code = AVAILABILITY_CODE
    unavailable_message = MISSING_MESSAGE
    fields = (
        TtsField(
            "app_id", "voice_chime_xfyun_appid", "讯飞 APPID",
            "xfyun.cn 控制台 → 创建应用 → 在线语音合成，页面上那串 APPID。",
            kind="text", default="",
        ),
        TtsField(
            "api_key", "voice_chime_xfyun_api_key", "APIKey",
            "与 APPID 同页；只存系统钥匙串，不进配置文件。留空表示不改动已保存的值。",
            kind="secret", default="", secret_ref=SECRET_REF_KEY,
        ),
        TtsField(
            "api_secret", "voice_chime_xfyun_api_secret", "APISecret",
            "签名用；同样只存钥匙串。留空表示不改动已保存的值。",
            kind="secret", default="", secret_ref=SECRET_REF_SECRET,
        ),
        TtsField(
            "voice", "voice_chime_xfyun_voice", "音色",
            "控制台「在线语音合成」可用的发音人（vcn）。想要更自然的那档，需在控制台开通"
            "「超拟人合成」并按它的参数手填。",
            kind="select", default="xiaoyan", options=VOICE_OPTIONS, allow_custom=True,
        ),
        TtsField(
            "speed", "voice_chime_xfyun_speed", "语速",
            "0–100，50 为默认（与设置页的「语速」是两套：这里传给讯飞）。",
            kind="number", default=50, minimum=0, maximum=100,
        ),
    )

    # ------------------------------------------------------------ 合同
    def plan(self, values: dict) -> dict:
        return {
            "provider": self.id,
            "app_id": str(values.get("app_id") or "").strip(),
            "api_key": str(values.get("api_key") or "").strip(),
            "api_secret": str(values.get("api_secret") or "").strip(),
            "voice": str(values.get("voice") or "").strip() or "xiaoyan",
            "speed": _as_int(values.get("speed"), 50),
            "ext": "mp3",
        }

    def flavor(self, values: dict) -> str:
        # 只放影响音频内容的参数；凭据绝不进 flavor（它进缓存键，会被落盘）
        return f"xfyun|{str(values.get('voice') or '').strip() or 'xiaoyan'}|{_as_int(values.get('speed'), 50)}"

    def availability(self, values: dict) -> str:
        for name in ("app_id", "api_key", "api_secret"):
            if not str(values.get(name) or "").strip():
                return AVAILABILITY_CODE
        return ""

    def synth(self, text: str, plan: dict, out_path) -> None:
        import asyncio

        url, _stamp = build_auth_url(str(plan.get("api_key") or ""), str(plan.get("api_secret") or ""))
        payload = build_payload(
            str(plan.get("app_id") or ""),
            str(text or ""),
            str(plan.get("voice") or "xiaoyan"),
            _as_int(plan.get("speed"), 50),
        )
        try:
            audio = asyncio.run(asyncio.wait_for(_collect(url, payload), timeout=SYNTH_TIMEOUT_S))
        except TtsUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 —— 统一转成可读错误
            raise TtsUnavailable(AVAILABILITY_CODE, f"讯飞合成失败：{exc}") from exc
        if not audio:
            raise TtsUnavailable(AVAILABILITY_CODE, "讯飞返回空音频")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio)


async def _collect(url: str, payload: dict) -> bytes:
    """连 ws、发一帧、把 base64 分片攒成完整音频（status==2 收尾）。"""
    import aiohttp

    chunks: list[bytes] = []
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, heartbeat=20) as ws:
            await ws.send_str(json.dumps(payload, ensure_ascii=False))
            async for message in ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    frame = json.loads(message.data)
                    code = _as_int(frame.get("code"), 0)
                    if code != 0:
                        raise TtsUnavailable(
                            AVAILABILITY_CODE,
                            f"讯飞返回 {code}：{frame.get('message') or ''}".strip(),
                        )
                    data = frame.get("data") or {}
                    audio = data.get("audio")
                    if audio:
                        chunks.append(base64.b64decode(audio))
                    if _as_int(data.get("status"), 0) == 2:
                        break
                elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
    return b"".join(chunks)


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


PROVIDER = register(XfyunTtsProvider())
