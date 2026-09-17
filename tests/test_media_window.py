# -*- coding: utf-8 -*-
"""窗口标题兜底监听：SMTC 卡死时仍能知道「在放什么歌」。

背景（2026-09-17）：本机 SMTC 的 ``request_async`` 间歇性永不返回，且与外壳、
播放器会话、桌宠采样压力都无关（三组对照试验均为阴性）。歌词/自动唱歌因此完全
失效。本模块从播放器窗口标题拿「歌名 - 歌手」，作为不依赖 SMTC 的兜底来源。

本文件只测纯逻辑与候选挑选，不依赖真实窗口/真实音频设备。
"""
from __future__ import annotations

import pytest

from pet import media_window as mw


@pytest.fixture(autouse=True)
def _clear_active_memory():
    """「最近 Active 过」是模块级状态：每个用例前后清干净。"""
    mw._last_active_at.clear()
    yield
    mw._last_active_at.clear()


# --------------------------------------------------------------- 标题解析


@pytest.mark.parametrize(
    "title, expected",
    [
        # 网易云（Electron 版实测标题格式）
        ("Older - Sasha Alex Sloan", ("Older", "Sasha Alex Sloan")),
        ("夜曲 - 周杰伦", ("夜曲", "周杰伦")),
        # 带应用名后缀
        ("晴天 - 周杰伦 - 网易云音乐", ("晴天", "周杰伦")),
        ("Hotel California - Eagles - QQ音乐", ("Hotel California", "Eagles")),
        # Spotify 风格分隔符
        ("告白气球 • 周杰伦", ("告白气球", "周杰伦")),
        ("Blinding Lights • The Weeknd", ("Blinding Lights", "The Weeknd")),
        # 多余空白
        ("  夜曲   -   周杰伦  ", ("夜曲", "周杰伦")),
        # 噪声/非歌曲
        ("", None),
        ("   ", None),
        ("网易云音乐", None),
        ("QQ音乐", None),
        ("Spotify", None),
        ("Spotify Free", None),
        ("只有歌名没有分隔符", None),
        (" - ", None),
        ("- 周杰伦", None),
        ("夜曲 - ", None),
    ],
)
def test_parse_track_title(title, expected):
    assert mw.parse_track_title(title) == expected


def test_music_player_allowlist_is_lowercase_exe_names():
    assert "cloudmusic.exe" in mw.MUSIC_PLAYER_EXES
    assert "qqmusic.exe" in mw.MUSIC_PLAYER_EXES
    assert all(name == name.lower() for name in mw.MUSIC_PLAYER_EXES)
    # 非播放器不得混进来
    assert "chrome.exe" not in mw.MUSIC_PLAYER_EXES


# --------------------------------------------------------------- 候选挑选


def _stub(monkeypatch, windows, audio):
    monkeypatch.setattr(mw, "_list_windows", lambda: list(windows))
    monkeypatch.setattr(mw, "_active_session_pids", lambda: audio)


def test_prefers_process_that_is_actually_playing(monkeypatch):
    _stub(
        monkeypatch,
        [
            (1, "chrome.exe", "某个网页 - Google Chrome"),          # 不在白名单
            (2, "cloudmusic.exe", "夜曲 - 周杰伦"),                  # 白名单但会话不 Active
            (3, "cloudmusic.exe", "晴天 - 周杰伦"),                  # 白名单且会话 Active
        ],
        audio={3},
    )
    assert mw.read_window_media() == ("晴天", "周杰伦", True)


def test_returns_none_without_any_player_window(monkeypatch):
    _stub(
        monkeypatch,
        [(1, "notepad.exe", "无标题 - 记事本"), (2, "chrome.exe", "bilibili")],
        audio={1},
    )
    assert mw.read_window_media() is None


def test_unparseable_player_title_is_ignored(monkeypatch):
    _stub(monkeypatch, [(2, "cloudmusic.exe", "网易云音乐")], audio={2})
    assert mw.read_window_media() is None


def test_active_player_keeps_playing_through_gaps(monkeypatch):
    """迟滞判定：见过它 Active 之后，换歌瞬间的会话切换**不算暂停**。

    实机回归（2026-09-17）：换歌瞬间峰值为 0 被判成暂停 → 连续两首歌整首不出词。
    """
    clock = {"t": 1000.0}
    monkeypatch.setattr(mw, "_now", lambda: clock["t"])
    _stub(monkeypatch, [(2, "cloudmusic.exe", "夜曲 - 周杰伦")], audio={2})
    assert mw.read_window_media() == ("夜曲", "周杰伦", True)   # 听到过 → 记住

    clock["t"] += 3.0
    _stub(monkeypatch, [(2, "cloudmusic.exe", "晴天 - 周杰伦")], audio=set())
    assert mw.read_window_media() == ("晴天", "周杰伦", True), "宽限期内不得判暂停"


def test_pause_after_lasting_silence_reports_not_playing(monkeypatch):
    """确实见过它 Active、且离开 Active 超过宽限期 → 视为暂停（歌词冻结）。"""
    clock = {"t": 2000.0}
    monkeypatch.setattr(mw, "_now", lambda: clock["t"])
    _stub(monkeypatch, [(2, "cloudmusic.exe", "夜曲 - 周杰伦")], audio={2})
    assert mw.read_window_media() == ("夜曲", "周杰伦", True)

    clock["t"] += mw._ACTIVE_GRACE_S + 5.0
    _stub(monkeypatch, [(2, "cloudmusic.exe", "夜曲 - 周杰伦")], audio=set())
    assert mw.read_window_media() == ("夜曲", "周杰伦", False)


def test_no_session_info_assumes_playing(monkeypatch):
    """拿不到逐会话音频信息时假定在播放：宁可显示歌词，也别整体静默。"""
    _stub(monkeypatch, [(2, "cloudmusic.exe", "夜曲 - 周杰伦")], audio=None)
    assert mw.read_window_media() == ("夜曲", "周杰伦", True)


def test_player_never_active_is_treated_as_playing(monkeypatch):
    """从没见过它 Active（例：音频会话落在别的输出设备上）→ 没有暂停的正证据，按在放。

    实机回归：网易云的音频会话不在默认设备上时，逐会话集合里没有它；
    若因此判暂停，歌词会整首不出。
    """
    _stub(monkeypatch, [(2, "cloudmusic.exe", "夜曲 - 周杰伦")], audio={9})
    assert mw.read_window_media() == ("夜曲", "周杰伦", True)


def test_prefers_recently_active_candidate(monkeypatch):
    """多个候选：优先会话 Active 的，其次最近 Active 过的，最后才取第一个。"""
    clock = {"t": 3000.0}
    monkeypatch.setattr(mw, "_now", lambda: clock["t"])
    _stub(monkeypatch, [(2, "cloudmusic.exe", "夜曲 - 周杰伦")], audio={2})
    assert mw.read_window_media() == ("夜曲", "周杰伦", True)   # pid=2 进入"最近听到过"

    clock["t"] += 2.0
    _stub(
        monkeypatch,
        [(2, "cloudmusic.exe", "夜曲 - 周杰伦"), (3, "qqmusic.exe", "晴天 - 周杰伦")],
        audio=set(),          # 都在间隙里
    )
    assert mw.read_window_media() == ("夜曲", "周杰伦", True), "应优先最近听到过的那个"


def test_never_raises_on_broken_seams(monkeypatch):
    """任何一步炸了都按「没在放歌」处理：歌词只是锦上添花。"""

    def _boom(*_a, **_k):
        raise OSError("枚举失败")

    monkeypatch.setattr(mw, "_list_windows", _boom)
    assert mw.read_window_media() is None
