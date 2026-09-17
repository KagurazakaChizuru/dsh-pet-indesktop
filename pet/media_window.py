# -*- coding: utf-8 -*-
"""从播放器窗口标题读「当前在放什么歌」——不依赖 SMTC 的兜底来源。

为什么需要：Windows SMTC 的 ``request_async`` 会**间歇性永不返回**（2026-09-17 实机
复现；对照试验排除了外壳、播放器会话、采样压力三个变量），此时歌词显示与音乐自动
唱歌会整体失效。播放器窗口标题里通常就是「歌名 - 歌手」，足够支撑歌词取词。

设计要点：

- 只用 ctypes + pycaw，零 Qt；
- 只认 :data:`MUSIC_PLAYER_EXES` 白名单里的进程，避免把任意窗口标题当歌曲；
- 多窗口时**优先选真正在出声的那个进程**（pycaw 逐会话峰值）；
- 任何一步失败都返回 ``None``——歌词只是锦上添花，绝不惊动桌宠本体。

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

# 逐会话峰值阈值：低于它视为该进程没在出声。
_AUDIO_PEAK_THRESHOLD = 0.02


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


def _audio_active_pids() -> set[int] | None:
    """当前正在出声的进程 pid 集合；拿不到逐会话信息时返回 ``None``（≠ 空集）。"""
    if sys.platform != "win32":
        return None
    try:
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    except Exception:
        return None
    try:
        pids: set[int] = set()
        for session in AudioUtilities.GetAllSessions():
            proc = session.Process
            if proc is None:
                continue
            try:
                meter = session._ctl.QueryInterface(IAudioMeterInformation)
                if meter.GetPeakValue() > _AUDIO_PEAK_THRESHOLD:
                    pids.add(int(proc.pid))
            except Exception:
                continue
        return pids
    except Exception:
        return None


def read_window_media() -> tuple[str, str, bool] | None:
    """返回 ``(歌名, 歌手, 是否在播放)``；没有可识别的播放器时返回 ``None``。

    候选 = 白名单进程 × 可解析标题；多个候选时优先「该进程正在出声」的那个。
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
        audio = _audio_active_pids()
        if audio:
            for pid, song, artist in candidates:
                if pid in audio:
                    return (song, artist, True)
        pid, song, artist = candidates[0]
        # 有逐会话信息就信它（暂停/静音 = 该进程不在出声集合里，见上面的优先分支）；
        # 拿不到逐会话信息时**假定在播放**——宁可显示歌词，也不要因为探测不到音量
        # 就让整个兜底静默（冻结环境里峰值探测失败过一次）。
        playing = True if audio is None else (pid in audio)
        return (song, artist, bool(playing))
    except Exception:
        return None
