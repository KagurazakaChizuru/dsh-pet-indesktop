# -*- coding: utf-8 -*-
"""右键菜单「音乐」子菜单的可用性 / 无效项测试。

审计发现（2026-09-18）：
1. 暂停与切歌这两个**播放器控制**项被 ``music_lyric_enabled`` 门控——用户关掉歌词
   气泡之后连暂停都用不了。
2. 「切歌」绕道歌词控制器，控制器没装配（歌词关着）时点了**静默无效**。
3. 「进入/退出音乐模式」本来就是歌词功能的临时开关，随歌词配置走是对的。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMenu

from pet import now_playing
from pet.context_menus import shared
from pet.context_menus.registry import MenuActionRegistry


class _Cfg:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        return None


class _Pet:
    """最小桌宠替身：歌词控制器**没有**装配（``_music_lyric`` 缺失）。"""

    def __init__(self, **cfg):
        self.cfg = _Cfg(**cfg)

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_skip_track_goes_straight_to_player(app, monkeypatch):
    """切歌直接找播放器：不依赖歌词控制器（否则歌词关着时点了没反应）。"""
    calls: list[str] = []
    monkeypatch.setattr(now_playing, "skip_track", lambda direction="next": calls.append(direction) or True)

    assert shared._skip_track("next") is True
    assert calls == ["next"], "必须真的把切歌指令发出去"


def test_pause_and_next_available_without_lyrics(app, monkeypatch):
    """歌词关着 + 机器能读媒体会话 → 暂停/切歌仍应出现。"""
    monkeypatch.setattr(now_playing, "available", lambda: True)
    pet = _Pet(music_lyric_enabled=False)
    registry = MenuActionRegistry()

    available = registry.available_ids(pet)
    assert "music_pause" in available
    assert "music_next" in available


def test_pause_and_next_hidden_without_media_session(app, monkeypatch):
    """读不到媒体会话（非 Windows / 没装 winrt）→ 这两项没有意义，不出现。"""
    monkeypatch.setattr(now_playing, "available", lambda: False)
    pet = _Pet(music_lyric_enabled=True)
    registry = MenuActionRegistry()

    available = registry.available_ids(pet)
    assert "music_pause" not in available
    assert "music_next" not in available


def test_music_mode_toggle_still_follows_lyric_setting(app, monkeypatch):
    """"进入/退出音乐模式"是歌词功能的临时开关：仍随 music_lyric_enabled。"""
    monkeypatch.setattr(now_playing, "available", lambda: True)
    registry = MenuActionRegistry()

    assert "music_quit" in registry.available_ids(_Pet(music_lyric_enabled=True))
    assert "music_quit" not in registry.available_ids(_Pet(music_lyric_enabled=False))


def test_music_submenu_skip_action_reaches_player(app, monkeypatch):
    """端到端：歌词关着时构建菜单，点「切歌」确实会发给播放器。"""
    calls: list[str] = []
    monkeypatch.setattr(now_playing, "skip_track", lambda direction="next": calls.append(direction) or True)
    pet = _Pet(music_lyric_enabled=False)

    menu = QMenu()
    shared.add_music_next(menu, pet)
    action = menu.actions()[0]
    assert action.isEnabled()
    action.trigger()
    assert calls == ["next"]


# ------------------------------------------- 「上一首」菜单项（承接上游 #134）

def test_prev_action_reaches_player(app, monkeypatch):
    """「上一首」同样直达播放器（不绕歌词控制器），方向必须是 previous。"""
    calls: list[str] = []
    monkeypatch.setattr(now_playing, "skip_track", lambda direction="next": calls.append(direction) or True)
    pet = _Pet(music_lyric_enabled=False)

    menu = QMenu()
    shared.add_music_prev(menu, pet)
    action = menu.actions()[0]
    assert "上一首" in action.text()
    action.trigger()
    assert calls == ["previous"]


def test_prev_available_without_lyrics(app, monkeypatch):
    """「上一首」与暂停/切歌同一门控：能读媒体会话就出现，与歌词开关无关。"""
    monkeypatch.setattr(now_playing, "available", lambda: True)
    assert "music_prev" in MenuActionRegistry().available_ids(_Pet(music_lyric_enabled=False))

    monkeypatch.setattr(now_playing, "available", lambda: False)
    assert "music_prev" not in MenuActionRegistry().available_ids(_Pet(music_lyric_enabled=True))
