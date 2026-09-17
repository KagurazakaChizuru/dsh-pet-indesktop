# -*- coding: utf-8 -*-
"""桌宠设置页「歌词」开关的门控测试。

歌词走 Windows SMTC（`now_playing.available()`）：非 Windows 或没装 winrt 时
读不到媒体会话，开关必须置灰并说明原因——否则用户能打开一个静默无效的功能。
（审计发现：`now_playing.available()` 在设置页里从来没被调用过。）

host 用最小替身：`build_pet_controls` 只往 host 上挂控件、并调用若干 `_on_*` 槽，
没写的槽由 ``__getattr__`` 兜底成空操作。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from pet import now_playing
from pet.config import Config
from pet.settings_pet_controls import build_pet_controls


class _Host(QWidget):
    """设置对话框的最小替身（只需满足 build_pet_controls 的挂载需求）。"""

    include_ai = False

    def __init__(self, cfg):
        super().__init__()
        self.config = cfg

    def __getattr__(self, name):
        # 设置页里那些 _on_xxx / _update_xxx 槽：测试不关心，兜底成空操作
        if name.startswith("_"):
            return lambda *a, **k: None
        raise AttributeError(name)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def host(app, tmp_path):
    return _Host(Config(base=tmp_path))


def test_lyric_toggle_disabled_when_now_playing_unavailable(host, monkeypatch):
    monkeypatch.setattr(now_playing, "available", lambda: False)
    build_pet_controls(host)
    assert host.music_lyric_check.isEnabled() is False
    assert host.music_lyric_check.toolTip(), "置灰必须说明原因"
    assert "winrt" in host.music_lyric_check.toolTip()


def test_lyric_toggle_enabled_when_now_playing_available(host, monkeypatch):
    monkeypatch.setattr(now_playing, "available", lambda: True)
    build_pet_controls(host)
    assert host.music_lyric_check.isEnabled() is True
    assert host.music_lyric_check.toolTip() == ""
