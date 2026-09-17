# -*- coding: utf-8 -*-
"""回归：SMTC 采样不得阻塞调用方线程（事故 2026-09-17）。

背景：歌词控制器每 1000ms 在 GUI 线程 tick 一次 ``now_playing.get_now_playing()``。
旧实现直接 ``asyncio.run(_read_async())``；而 PyWinRT 的 awaitable 在某些系统/
播放器状态下**永不完成**，且该 await 连 ``asyncio.wait_for`` 都取消不掉（事件循环
钉在 proactor ``_poll``，定时器得不到执行）→ GUI 线程永久阻塞 → 窗口冻死，被
Windows 判定 ``Application Hang`` 关掉。

设计约束（本文件锁死的契约）：采样在工作线程里做，取值/操作在调用线程只做**有界
等待**。功能可以降级（歌词停止更新），进程必须活着。
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time

import pytest

from pet import now_playing

# 预算给得很宽（CI 慢 runner 是本地数倍慢），只要求「有界」而非「快」。
BUDGET = 3.0


@pytest.fixture(autouse=True)
def _isolate_sampler():
    """每个用例前后都摘掉采样线程，避免模块级状态串场。"""
    now_playing._stop_sampler()
    yield
    now_playing._stop_sampler()


@pytest.fixture(autouse=True)
def _no_real_window_probe(monkeypatch):
    """窗口标题兜底默认按「没在放歌」处理；要用它的用例自行覆盖。"""
    monkeypatch.setattr(now_playing, "_read_window_media", lambda: None)


def _playback(title: str = "曲名", artist: str = "歌手") -> now_playing.Playback:
    return now_playing.Playback(
        track=now_playing.Track(title=title, artist=artist, playing=True),
        position=1.0,
        updated_at=time.monotonic(),
    )


def _wait_for_sample(want, *, timeout: float = 5.0):
    """轮询取值直到拿到目标样本（宽预算 + 事件驱动，不用固定 sleep 赌时序）。"""
    deadline = time.monotonic() + timeout
    value = None
    while time.monotonic() < deadline:
        value = now_playing.get_now_playing()
        if value is want:
            return value
        time.sleep(0.02)
    return value


# ------------------------------------------------------- 采样绝不阻塞调用方


def test_get_now_playing_never_blocks_when_sample_stalls(monkeypatch):
    """底层请求永不返回时，取值必须立刻返回——这是本次事故的回归点。"""
    entered = threading.Event()
    gate = threading.Event()

    def _stuck():
        entered.set()
        gate.wait(5.0)  # 模拟「请求永不完成」
        return None

    monkeypatch.setattr(now_playing, "_read_blocking", _stuck)
    try:
        t0 = time.monotonic()
        assert now_playing.get_now_playing() is None
        first = time.monotonic() - t0
        assert entered.wait(BUDGET), "采样线程未启动"
        # 卡住的采样在飞：后续取值同样不得等待
        t1 = time.monotonic()
        assert now_playing.get_now_playing() is None
        second = time.monotonic() - t1
    finally:
        gate.set()
    assert first < BUDGET, f"首次取值被阻塞 {first:.2f}s（GUI 线程会冻死）"
    assert second < BUDGET, f"采样卡住后取值被阻塞 {second:.2f}s"


def test_get_now_playing_publishes_background_sample(monkeypatch):
    """正常路径不变：后台采到的样本必须能被取值读到。"""
    sample = _playback()
    monkeypatch.setattr(now_playing, "_read_blocking", lambda: sample)
    assert _wait_for_sample(sample) is sample


def test_stalled_sampler_is_abandoned_and_recovers(monkeypatch):
    """采样线程卡死后必须被弃用重开，且陈旧结果不得发布。"""
    monkeypatch.setattr(now_playing, "_SAMPLE_STALL_LIMIT", 0.2)
    monkeypatch.setattr(now_playing, "_RESTART_COOLDOWN", 0.0)
    # 本用例只考「摘牌重开」，不考 SMTC 退避：关掉退避让新线程立刻重试 SMTC。
    monkeypatch.setattr(now_playing, "_SMTC_BACKOFF_S", 0.0)
    state = {"stuck": True}
    entered = threading.Event()
    sample = _playback()

    def _read():
        if state["stuck"]:
            entered.set()
            threading.Event().wait(5.0)
            return None
        return sample

    monkeypatch.setattr(now_playing, "_read_blocking", _read)
    assert now_playing.get_now_playing() is None
    assert entered.wait(BUDGET), "采样线程未启动"

    # 第一个采样线程永久卡住 → 监管方弃用它并起新线程，新线程给出样本
    state["stuck"] = False
    assert _wait_for_sample(sample) is sample, "卡死的采样线程未被弃用重启"


def test_sampler_idles_out_without_requests(monkeypatch):
    """调用方不再取值（歌词关/窗口隐藏）时，采样线程必须自行退出。"""
    monkeypatch.setattr(now_playing, "_IDLE_STOP", 0.2)
    monkeypatch.setattr(now_playing, "_SAMPLE_INTERVAL", 0.02)
    monkeypatch.setattr(now_playing, "_read_blocking", lambda: _playback())
    now_playing.get_now_playing()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        thread = now_playing._sample_thread
        if thread is None or not thread.is_alive():
            return
        time.sleep(0.02)
    pytest.fail("采样线程在无人取值后仍在轮询")


# --------------------------------------------------- 用户操作同样必须有界


def test_run_bounded_returns_default_when_work_never_finishes(monkeypatch):
    """有界执行器：工作永不结束时按预算返回默认值（跨平台覆盖机制本身）。"""
    monkeypatch.setattr(now_playing, "_ACTION_TIMEOUT", 0.2)
    gate = threading.Event()
    try:
        t0 = time.monotonic()
        assert now_playing._run_bounded(lambda: gate.wait(5.0), "default") == "default"
        elapsed = time.monotonic() - t0
    finally:
        gate.set()
    assert elapsed < BUDGET, f"有界执行器超预算 {elapsed:.2f}s"


def test_run_bounded_returns_value_when_work_finishes():
    """正常路径不变：工作正常结束时必须拿到真实返回值。"""
    assert now_playing._run_bounded(lambda: "ok", "default") == "ok"


@pytest.mark.skipif(sys.platform != "win32", reason="SMTC 只在 Windows 存在")
@pytest.mark.parametrize(
    "invoke",
    [
        pytest.param(lambda: now_playing.toggle_play_pause(), id="toggle_play_pause"),
        pytest.param(lambda: now_playing.skip_track("next"), id="skip_track"),
        pytest.param(lambda: now_playing.resume_playback(), id="resume_playback"),
        pytest.param(
            lambda: now_playing.play_session_for("cloudmusic.exe"),
            id="play_session_for",
        ),
    ],
)
def test_player_actions_are_bounded_when_winrt_stalls(monkeypatch, invoke):
    """右键菜单里的播放器操作也不能被卡死的 SMTC 拖住 GUI。"""
    monkeypatch.setattr(now_playing, "_ACTION_TIMEOUT", 0.2)

    async def _never(*_args, **_kwargs):
        await asyncio.Event().wait()

    for name in (
        "_resume_async",
        "_play_session_async",
        "_skip_async",
        "_play_pause_async",
    ):
        monkeypatch.setattr(now_playing, name, _never)

    t0 = time.monotonic()
    assert invoke() is False
    elapsed = time.monotonic() - t0
    assert elapsed < BUDGET, f"播放器操作被阻塞 {elapsed:.2f}s"


# ------------------------------------------- 窗口标题兜底（SMTC 卡死时仍能知道在放什么）


def _fallback_playback(title: str = "夜曲", artist: str = "周杰伦"):
    return now_playing.Playback(
        track=now_playing.Track(title=title, artist=artist, playing=True),
        position=None,  # 窗口兜底拿不到进度
        updated_at=time.monotonic(),
    )


def test_smtc_sample_wins_when_healthy(monkeypatch):
    """SMTC 健康时优先它（有播放进度），兜底不得顶掉。"""
    smtc = _playback("SMTC曲", "SMTC歌手")
    monkeypatch.setattr(now_playing, "_read_blocking", lambda: smtc)
    monkeypatch.setattr(
        now_playing, "_read_window_media", lambda: _fallback_playback("窗口曲", "窗口歌手")
    )
    assert _wait_for_sample(smtc) is smtc
    assert now_playing.get_now_playing() is smtc


def test_window_fallback_used_when_smtc_returns_nothing(monkeypatch):
    """SMTC 正常但查不到会话（未接入/无会话）→ 用窗口标题兜底。"""
    monkeypatch.setattr(now_playing, "_read_blocking", lambda: None)
    fallback = _fallback_playback()
    monkeypatch.setattr(now_playing, "_read_window_media", lambda: fallback)
    assert _wait_for_sample(fallback) is fallback


def test_window_fallback_takes_over_after_smtc_wedges(monkeypatch):
    """SMTC 卡死被摘牌后进入退避：改为只用窗口兜底，且退避期内不再触 SMTC。"""
    monkeypatch.setattr(now_playing, "_SAMPLE_STALL_LIMIT", 0.2)
    monkeypatch.setattr(now_playing, "_RESTART_COOLDOWN", 0.0)
    monkeypatch.setattr(now_playing, "_SAMPLE_INTERVAL", 0.05)
    entered = threading.Event()
    calls = {"smtc": 0}

    def _stuck():
        calls["smtc"] += 1
        entered.set()
        threading.Event().wait(5.0)  # 模拟 request_async 永不返回
        return None

    monkeypatch.setattr(now_playing, "_read_blocking", _stuck)
    fallback = _fallback_playback()
    monkeypatch.setattr(now_playing, "_read_window_media", lambda: fallback)

    assert now_playing.get_now_playing() is None
    assert entered.wait(BUDGET), "采样线程未启动"

    # 卡死被监管方摘牌 → 之后只走兜底
    assert _wait_for_sample(fallback) is fallback
    smtc_calls = calls["smtc"]
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        assert now_playing.get_now_playing() is fallback
        time.sleep(0.05)
    assert calls["smtc"] == smtc_calls, "退避窗口内不得再次调用 SMTC（会被再次卡死）"


def test_smtc_retried_after_backoff_expires(monkeypatch):
    """退避到期后应重新尝试 SMTC，以便它恢复时自动切回（有进度的来源）。"""
    monkeypatch.setattr(now_playing, "_SAMPLE_STALL_LIMIT", 0.2)
    monkeypatch.setattr(now_playing, "_RESTART_COOLDOWN", 0.0)
    monkeypatch.setattr(now_playing, "_SAMPLE_INTERVAL", 0.05)
    monkeypatch.setattr(now_playing, "_SMTC_BACKOFF_S", 0.3)
    gate = threading.Event()

    def _stuck_then_ok():
        if not gate.is_set():
            gate.set()
            threading.Event().wait(5.0)
            return None
        return _playback("SMTC曲", "SMTC歌手")

    monkeypatch.setattr(now_playing, "_read_blocking", _stuck_then_ok)
    monkeypatch.setattr(
        now_playing, "_read_window_media", lambda: _fallback_playback("窗口曲", "窗口歌手")
    )

    assert now_playing.get_now_playing() is None
    # 先落到兜底
    assert _wait_for_sample(_fallback_playback("窗口曲", "窗口歌手"), timeout=5.0) is not None
    # 退避到期后重试 SMTC：拿到带进度的样本
    want = now_playing.Playback(
        track=now_playing.Track(title="SMTC曲", artist="SMTC歌手", playing=True),
        position=1.0,
        updated_at=time.monotonic(),
    )
    deadline = time.monotonic() + 6.0
    got = None
    while time.monotonic() < deadline:
        got = now_playing.get_now_playing()
        if got is not None and got.track.title == "SMTC曲":
            break
        time.sleep(0.05)
    assert got is not None and got.track.title == "SMTC曲", "退避到期后未重试 SMTC"
    del want
