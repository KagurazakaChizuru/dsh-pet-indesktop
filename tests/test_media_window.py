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
    monkeypatch.setattr(mw, "_audio_active_pids", lambda: audio)


def test_prefers_process_that_is_actually_playing(monkeypatch):
    _stub(
        monkeypatch,
        [
            (1, "chrome.exe", "某个网页 - Google Chrome"),          # 不在白名单
            (2, "cloudmusic.exe", "夜曲 - 周杰伦"),                  # 白名单但没出声
            (3, "cloudmusic.exe", "晴天 - 周杰伦"),                  # 白名单且出声
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


def test_paused_player_reports_not_playing(monkeypatch):
    """窗口还在、标题还在，但那个进程没在出声 → 视为暂停（歌词不推进）。"""
    _stub(
        monkeypatch,
        [(2, "cloudmusic.exe", "夜曲 - 周杰伦")],
        audio={9},          # 出声的是别的进程
    )
    assert mw.read_window_media() == ("夜曲", "周杰伦", False)


def test_no_session_info_assumes_playing(monkeypatch):
    """拿不到逐会话音频信息时假定在播放：宁可显示歌词，也别整体静默。"""
    _stub(monkeypatch, [(2, "cloudmusic.exe", "夜曲 - 周杰伦")], audio=None)
    assert mw.read_window_media() == ("夜曲", "周杰伦", True)


def test_picks_first_candidate_when_nothing_is_audible(monkeypatch):
    _stub(
        monkeypatch,
        [(2, "cloudmusic.exe", "夜曲 - 周杰伦"), (3, "qqmusic.exe", "晴天 - 周杰伦")],
        audio=set(),
    )
    assert mw.read_window_media() == ("夜曲", "周杰伦", False)


def test_never_raises_on_broken_seams(monkeypatch):
    """任何一步炸了都按「没在放歌」处理：歌词只是锦上添花。"""

    def _boom(*_a, **_k):
        raise OSError("枚举失败")

    monkeypatch.setattr(mw, "_list_windows", _boom)
    assert mw.read_window_media() is None
