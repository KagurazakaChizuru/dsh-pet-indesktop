# -*- coding: utf-8 -*-
"""从播放器窗口标题读「当前在放什么歌」——不依赖 SMTC 的兜底来源。

为什么需要：Windows SMTC 的 ``request_async`` 会**间歇性永不返回**（2026-09-17 实机
复现；对照试验排除了外壳、播放器会话、采样压力三个变量），此时歌词显示与音乐自动
唱歌会整体失效。播放器窗口标题里通常就是「歌名 - 歌手」，足够支撑歌词取词。

设计要点：

- 只用 ctypes + pycaw，零 Qt；
- 只认 :data:`MUSIC_PLAYER_EXES` 白名单里的进程，避免把任意窗口标题当歌曲；
- 多窗口时**优先选音频会话处于 Active（正在播放）的那个进程**（pycaw 会话状态；
-   刻意不用峰值：峰值在间奏/轻声段会掉到 0，会把"安静地放着"误判成暂停）；\n- 任何一步失败都返回 ``None``——歌词只是锦上添花，绝不惊动桌宠本体。

已知边界：播放器缩小到托盘且窗口隐藏时取不到标题；标题里没有播放进度。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

# 视为「音乐播放器」的进程名（小写）。只认这些，避免误判。
MUSIC_PLAYER_EXES = frozenset({
    "cloudmusic.exe",   # 网易云音乐
    "qqmusic.exe",      # QQ 音乐
    "kugou.exe",        # 酷狗音乐
    "kwmusic.exe",      # 酷我音乐
    "spotify.exe",
    "foobar2000.exe",
    "musicbee.exe",
    "aimp.exe",
})

# 标题尾部的应用名后缀：解析前先剥掉（「晴天 - 周杰伦 - 网易云音乐」）。
_APP_SUFFIXES = (
    " - 网易云音乐", " - QQ音乐", " - 酷狗音乐", " - 酷我音乐",
    " - Spotify", " - foobar2000", " - MusicBee",
)

# 播放器空闲时的整标题（不是歌曲）。
_GENERIC_TITLES = frozenset({
    "网易云音乐", "qq音乐", "酷狗音乐", "酷我音乐",
    "spotify", "spotify free", "spotify premium", "foobar2000", "musicbee", "aimp",
})

# 歌名与歌手之间的分隔符（按优先级）。
_SEPARATORS = (" - ", " • ", " – ", " — ")

# 「最近 Active 过」宽限（秒）：换歌那一瞬会话会短暂离开 Active（旧流结束、新流开始），
# 立刻判成暂停会让歌词整首不开始（实机 2026-09-17：换歌瞬间判 False → 连续两首没出词）。
_ACTIVE_GRACE_S = 10.0

# pid -> 最近一次「它的音频会话处于 Active」的时刻（monotonic）。只在进程内累积，不落盘。
_last_active_at: dict[int, float] = {}


def _now() -> float:
    """当前单调时刻（独立函数便于测试注入）。"""
    import time

    return time.monotonic()


def parse_track_title(title: str) -> tuple[str, str] | None:
    """把播放器窗口标题解析成 ``(歌名, 歌手)``；解析不出返回 ``None``。

    宁可返回 ``None`` 也不猜：错误歌名会让歌词整首错位。
    """
    text = str(title or "").strip()
    if not text:
        return None
    lowered = text.lower()
    for suffix in _APP_SUFFIXES:
        if lowered.endswith(suffix.lower()):
            text = text[: len(text) - len(suffix)].strip()
            lowered = text.lower()
            break
    if not text or lowered in _GENERIC_TITLES:
        return None
    for sep in _SEPARATORS:
        if sep in text:
            song, artist = (part.strip() for part in text.split(sep, 1))
            if not song or not artist or song.lower() in _GENERIC_TITLES:
                return None
            return (song, artist)
    return None


def _list_windows() -> list[tuple[int, str, str]]:
    """枚举顶层窗口 → ``[(pid, 进程名小写, 标题)]``；非 Windows 或失败返回 ``[]``。

    只要求窗口存在且有标题（最小化窗口仍有标题）；托盘隐藏的窗口枚举不到。
    """
    if sys.platform != "win32":
        return []
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        # 显式声明签名：默认 restype=c_int 会在 64 位下截断 HWND/HANDLE。
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(ctypes.c_ulong),
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, ctypes.c_ulong, ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        found: list[tuple[int, str, str]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _on_window(hwnd, _lparam):  # pragma: no cover - 需要真实窗口
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return True
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return True
            exe = ""
            handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED
            if handle:
                try:
                    pbuf = ctypes.create_unicode_buffer(260)
                    size = ctypes.c_ulong(260)
                    if kernel32.QueryFullProcessImageNameW(
                        handle, 0, pbuf, ctypes.byref(size)
                    ):
                        exe = Path(pbuf.value).name
                finally:
                    kernel32.CloseHandle(handle)
            if exe:
                found.append((int(pid.value), exe.lower(), title))
            return True

        user32.EnumWindows(_on_window, 0)
        return found
    except Exception:
        return []


def _active_session_pids() -> set[int] | None:
    """音频会话处于 **Active**（= 正在播放，流在跑）的进程 pid 集合；拿不到信息返回 ``None``。

    刻意**不用峰值**判活跃：峰值在间奏/轻声段会掉到 0，把"安静地放着"误判成暂停；
    而控制器一旦认为暂停就会**冻结歌词基准**，恢复后位置整体落后（实机 2026-09-17
    用户反馈"歌词对不上"）。WASAPI 的会话状态恰好区分这两件事：
    真暂停/播完 → ``Inactive``，只是声音小 → 仍是 ``Active``。
    """
    if sys.platform != "win32":
        return None
    try:
        from pycaw.constants import AudioSessionState
        from pycaw.pycaw import AudioUtilities
    except Exception:
        return None
    try:
        pids: set[int] = set()
        for session in AudioUtilities.GetAllSessions():
            proc = session.Process
            if proc is None:
                continue
            try:
                if session.State == AudioSessionState.Active:
                    pids.add(int(proc.pid))
            except Exception:
                continue
        return pids
    except Exception:
        return None


def read_window_media() -> tuple[str, str, bool] | None:
    """返回 ``(歌名, 歌手, 是否在播放)``；没有可识别的播放器时返回 ``None``。

    候选 = 白名单进程 × 可解析标题；多个候选时优先「会话处于 Active」的那个。
    ``playing`` 采用**迟滞**判定（见 :data:`_ACTIVE_GRACE_S`）：只有「确实见过它
    Active，且已经离开 Active 超过宽限期」才算暂停——否则换歌瞬间的会话切换会被误判
    成暂停（歌词整首不出、基准冻结导致漂移）；从未见过它 Active 的（例如音频会话
    落在别的输出设备上）按在播放处理。
    """
    try:
        windows = _list_windows()
        if not windows:
            return None
        candidates: list[tuple[int, str, str]] = []
        for pid, exe, title in windows:
            if exe not in MUSIC_PLAYER_EXES:
                continue
            parsed = parse_track_title(title)
            if parsed is None:
                continue
            candidates.append((int(pid), parsed[0], parsed[1]))
        if not candidates:
            return None
        now = _now()
        active = _active_session_pids()
        for pid in active or ():
            _last_active_at[pid] = now
        if active:
            # 正在播放的优先；其次「最近 Active 过」的（换歌瞬间仍是同一台播放器）。
            for pid, song, artist in candidates:
                if pid in active:
                    return (song, artist, True)
            for pid, song, artist in candidates:
                seen = _last_active_at.get(pid)
                if seen is not None and (now - seen) <= _ACTIVE_GRACE_S:
                    return (song, artist, True)
        pid, song, artist = candidates[0]
        if active is None:
            return (song, artist, True)  # 拿不到会话信息：假定在放，别整体静默
        seen = _last_active_at.get(pid)
        if seen is None:
            # 从未见它 Active（会话可能在别的输出设备上）：没有"暂停"的正证据，按在放处理。
            return (song, artist, True)
        return (song, artist, (now - seen) <= _ACTIVE_GRACE_S)
    except Exception:
        return None
