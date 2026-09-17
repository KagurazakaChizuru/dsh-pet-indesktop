# -*- coding: utf-8 -*-
"""pet.http_util 的离线单元测试：系统代理不通时自动改直连。

背景（2026-09-17 实机）：Windows 系统代理（IE/WinINET 设置，`ProxyEnable=1`,
`ProxyServer=127.0.0.1:33210`）被加速器/VPN 打开、进程却没在跑时，`urllib` 仍会照着
它走 ⇒ 所有请求 `ConnectionRefused`。歌词取词因此全军覆没（气泡只剩歌名），余额查询、
识屏、AI 对话、更新检查同样会废掉。本模块是这条兜底的唯一实现，其他模块共用。
"""
from __future__ import annotations

import urllib.error

import pytest

from pet import http_util


class _Resp:
    """最小 response 替身：支持 ``with`` 与 ``read()``。"""

    def __init__(self, payload: bytes = b"{}"):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._payload


@pytest.fixture(autouse=True)
def _reset_transport():
    """「固定直连」是模块级状态：每个用例前后清零，避免互相污染。"""
    http_util.reset_transport()
    yield
    http_util.reset_transport()


def _opener_factory(monkeypatch, log: list[tuple[bool, object]]):
    """把 ``_opener`` 换成记账替身：按 use_proxy 决定成功或抛连接失败。"""

    def _opener(use_proxy, context=None):
        class _Opener:
            def open(self, request, timeout=None, **kwargs):
                log.append((use_proxy, getattr(request, "full_url", request)))
                if use_proxy:
                    raise ConnectionRefusedError("connection refused")
                return _Resp(b'{"ok": 1}')

        return _Opener()

    monkeypatch.setattr(http_util, "_opener", _opener)


def test_falls_back_to_direct_when_proxy_dead(monkeypatch):
    """代理连不上 → 直连重试一次并成功；此后本进程固定直连，不再撞死代理。"""
    calls: list[tuple[bool, object]] = []
    _opener_factory(monkeypatch, calls)

    with http_util.urlopen("https://example.com/x", timeout=3.0) as resp:
        assert resp.read() == b'{"ok": 1}'
    assert [use_proxy for use_proxy, _ in calls] == [True, False], "先代理、失败后直连"
    assert http_util.force_direct() is True, "确认代理不可用后应记住结论"

    calls.clear()
    with http_util.urlopen("https://example.com/y", timeout=3.0):
        pass
    assert [use_proxy for use_proxy, _ in calls] == [False], "后续请求不该再撞一遍"


def test_http_error_is_not_retried(monkeypatch):
    """服务器明确答复（HTTPError）说明链路是通的：原样抛出、不重试、不改传输方式。"""
    calls: list[bool] = []

    def _opener(use_proxy, context=None):
        class _Opener:
            def open(self, request, timeout=None, **kwargs):
                calls.append(use_proxy)
                raise urllib.error.HTTPError("https://example.com/x", 404, "Not Found", None, None)

        return _Opener()

    monkeypatch.setattr(http_util, "_opener", _opener)

    with pytest.raises(urllib.error.HTTPError):
        http_util.urlopen("https://example.com/x", timeout=3.0)
    assert calls == [True]
    assert http_util.force_direct() is False


def test_both_transports_failing_raises_last_error(monkeypatch):
    """两种方式都失败时抛最后一次的传输异常（与原生 urlopen 失败语义一致）。"""

    def _opener(use_proxy, context=None):
        class _Opener:
            def open(self, request, timeout=None, **kwargs):
                raise ConnectionRefusedError("dead %s" % use_proxy)

        return _Opener()

    monkeypatch.setattr(http_util, "_opener", _opener)

    with pytest.raises(ConnectionRefusedError):
        http_util.urlopen("https://example.com/x", timeout=3.0)
    assert http_util.force_direct() is False, "直连也失败时不该记住'直连可用'"


def test_forced_direct_only_tries_direct(monkeypatch):
    """已确定代理不可用后：只试直连一次，不做无谓的代理尝试。"""
    http_util._force_direct = True
    calls: list[bool] = []

    def _opener(use_proxy, context=None):
        class _Opener:
            def open(self, request, timeout=None, **kwargs):
                calls.append(use_proxy)
                return _Resp()

        return _Opener()

    monkeypatch.setattr(http_util, "_opener", _opener)

    with http_util.urlopen("https://example.com/x", timeout=3.0):
        pass
    assert calls == [False]


def test_reset_transport_restores_proxy_attempt(monkeypatch):
    """网络环境变化后 reset 可恢复"先试代理"的行为（测试隔离也靠它）。"""
    http_util._force_direct = True
    http_util.reset_transport()
    assert http_util.force_direct() is False

    calls: list[bool] = []
    _opener_factory(monkeypatch, calls)
    with http_util.urlopen("https://example.com/x", timeout=3.0):
        pass
    assert [use_proxy for use_proxy, _ in calls] == [True, False]
