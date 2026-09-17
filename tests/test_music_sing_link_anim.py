# -*- coding: utf-8 -*-
"""唱歌动画循环不得饿死待播联动动作（节日提醒动画）。

背景：``悠闲哼歌`` 位于 ``videos/random/`` ⇒ 唱歌动画属 ``acts``（一次性动作）。
节日提醒经 ``request_link_anim`` 请求动画时，正在播一次性动作会把请求存成
``_pending_link_anim``（不打断）；而唱歌循环在圈末**提前 return 续播**，
待播动画永远等不到 ``_on_anim_ended`` 里的消费点 —— 只要音乐不停，
节日动画一次都播不出来（文案/语音/气泡正常）。

现要求（用户裁定：提醒优先，圈末交付）：
圈末先把待播动作交付出去，并把唱歌状态交回每秒轮询重启。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from pet import window_alerts
from pet.config import Config
from pet.window import SING_ANIM, PetWindow
from tests.test_music_sing_timer import SingingLibrary

LINK_ANIM = "写代码"  # FakeLibrary 里的一次性动作名


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_real_music_detection(monkeypatch):
    """测试环境不读真实音频峰值（各用例按需覆盖）。"""
    import pet.music_detect as music_detect

    monkeypatch.setattr(music_detect, "is_music_playing", lambda: False)
    music_detect.clear_self_speaking()


def _singing_win(app, tmp_path) -> PetWindow:
    cfg = Config(base=tmp_path)
    cfg.set("music_sing_enabled", True)
    win = PetWindow(SingingLibrary(), cfg)
    win.show()
    app.processEvents()
    win._music_sing_timer.stop()  # 用例自己驱动轮询，避免与窗口定时器竞态
    win._music_sing_enabled = True
    win._music_sing_active = True
    win._switch(SING_ANIM)
    return win


def test_sing_loop_hands_over_to_pending_link_anim(app, tmp_path):
    """唱歌中到达圈末：待播的节日动画优先交付，而不是继续续播唱歌。"""
    win = _singing_win(app, tmp_path)
    try:
        assert win.anim == SING_ANIM
        win.request_link_anim(LINK_ANIM)
        assert win._pending_link_anim == LINK_ANIM, "一次性动作播放中不该被打断"

        win._on_anim_ended(SING_ANIM)

        assert win.anim == LINK_ANIM, "圈末必须把待播的节日动画交付出去"
        assert win._pending_link_anim is None
        assert win._music_sing_active is False, "唱歌状态要交回轮询，别锁死本首歌"
    finally:
        win.close()
        win.deleteLater()


def test_sing_loop_still_loops_without_pending_link_anim(app, tmp_path):
    """无待播动作时保持原行为：圈末无缝续播唱歌。"""
    win = _singing_win(app, tmp_path)
    try:
        win._on_anim_ended(SING_ANIM)
        assert win.anim == SING_ANIM
        assert win._music_sing_active is True
    finally:
        win.close()
        win.deleteLater()


def test_festival_anim_not_interrupted_and_singing_resumes(app, tmp_path, monkeypatch):
    """提醒动画播放期间不被唱歌抢走；播完回待机后唱歌由轮询自动重启。"""
    import pet.music_detect as music_detect

    win = _singing_win(app, tmp_path)
    try:
        win.request_link_anim(LINK_ANIM)
        win._on_anim_ended(SING_ANIM)
        assert win.anim == LINK_ANIM

        monkeypatch.setattr(music_detect, "is_music_playing", lambda: True)
        window_alerts.check_music_sing(win)
        assert win.anim == LINK_ANIM, "提醒动画还在播，唱歌不得抢动画"
        assert win._music_sing_active is False

        win._switch(win.idles[0])  # 提醒动画播完 → 回待机
        window_alerts.check_music_sing(win)
        assert win._music_sing_active is True, "音乐还在放，唱歌应恢复"
        assert win.anim == SING_ANIM
    finally:
        win.close()
        win.deleteLater()
