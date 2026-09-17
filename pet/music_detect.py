# -*- coding: utf-8 -*-
"""后台音乐/音频播放检测（Windows）。

通过 pycaw 读取默认音频输出设备的瞬时峰值电平：只要系统正在输出声音
（音乐、视频、游戏等），峰值就会高于静音阈值。桌宠据此自动播放唱歌动画；
阈值设置得较低，避免只有极微弱提示音时频繁触发。
"""

from __future__ import annotations

import sys
import time

# 峰值电平阈值：0.0=静音，1.0=满幅。取 0.02 过滤极低电平/数字静音。
MUSIC_PEAK_THRESHOLD = 0.02

# 「桌宠自己在出声」的登记时长上限（秒）。峰值检测分不清"系统在放音乐"与
# "桌宠自己在报时/节日播报"，所以由播放侧主动登记；终止态回调丢失时靠它兜底
# 自动失效——绝不能把唱歌检测永久屏蔽掉。
SELF_SPEAKING_TTL_S = 60.0

_self_speaking_until = 0.0


_meter = None


def _get_meter():
    """惰性创建并复用一个音频峰值检测 COM 对象。

    每次调用都重新 Activate 会持续产生 COM 接口句柄，长时间运行（如音乐自动
    唱歌每 4 秒检测一次）可能累积并导致崩溃；这里只初始化一次。
    """
    global _meter
    if _meter is not None:
        return _meter
    try:
        import comtypes
        from ctypes import POINTER, cast

        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

        device = AudioUtilities.GetSpeakers()._dev
        interface = device.Activate(
            IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL, None
        )
        _meter = cast(interface, POINTER(IAudioMeterInformation))
    except Exception:
        _meter = None
    return _meter


def is_music_playing() -> bool:
    """返回系统当前是否正在输出音频（Windows；其他平台恒 False）。"""
    if sys.platform != 'win32':
        return False
    try:
        meter = _get_meter()
        if meter is None:
            return False
        return meter.GetPeakValue() > MUSIC_PEAK_THRESHOLD
    except Exception:
        # 无 pycaw / 音频设备不可用 / COM 初始化失败时按“未播放”处理，不打扰用户
        return False


# --- 桌宠自己的播报登记（2026-09-17 跨功能审计）--------------------------------
# 报时/节日播报走的就是系统输出，峰值必然超过阈值；不登记的话，开启「音乐自动
# 唱歌」时桌宠会在自己报时的那一刻切去唱歌动画。登记只是为了把这些"自己的声音"
# 排除在音乐判定之外，语义上仍是本模块的职责（判断系统里有没有**别处**在放歌）。


def mark_self_speaking(duration_s: float | None = None) -> None:
    """登记「桌宠正在用自己的音频通道播报」；``None`` 用默认 TTL。"""
    global _self_speaking_until
    ttl = SELF_SPEAKING_TTL_S if duration_s is None else max(0.0, float(duration_s))
    _self_speaking_until = time.monotonic() + ttl


def clear_self_speaking() -> None:
    """撤销登记（媒体终止态、服务停止、退出）。"""
    global _self_speaking_until
    _self_speaking_until = 0.0


def is_self_speaking() -> bool:
    """桌宠自己是否正在播报（超过登记时长自动失效）。"""
    return time.monotonic() < _self_speaking_until
