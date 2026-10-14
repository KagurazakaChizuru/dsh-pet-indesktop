# -*- coding: utf-8 -*-
"""语音合成凭据存取（pet/tts_secrets.py）回归测试。

两条路径都要锁：钥匙串可用（持久化）与不可用（退化为进程内存，本次运行有效）。
不碰真实凭据管理器——keyring 一律 monkeypatch。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pet import tts_secrets  # noqa: E402


class _FakeKeyring:
    """最小 keyring 替身：记调用、可注入异常。"""

    def __init__(self, *, fail_set: bool = False) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self.fail_set = fail_set

    def get_password(self, service, ref):
        return self.store.get((service, ref))

    def set_password(self, service, ref, value):
        if self.fail_set:
            raise RuntimeError("no backend")
        self.store[(service, ref)] = value

    def delete_password(self, service, ref):
        self.store.pop((service, ref), None)


def _patch(monkeypatch, module):
    monkeypatch.setattr(tts_secrets, "_keyring_module", lambda: module)


def test_round_trip_through_keyring(monkeypatch):
    """钥匙串可用：写入返回 True，读到同一个值，服务名与 ref 与 chat 侧一致。"""
    fake = _FakeKeyring()
    _patch(monkeypatch, fake)
    tts_secrets.reset_memory()

    assert tts_secrets.available() is True
    assert tts_secrets.set("tts/mimo", "k-1") is True
    assert tts_secrets.get("tts/mimo") == "k-1"
    assert fake.store == {("dsh-pet-standalone", "tts/mimo"): "k-1"}

    tts_secrets.clear("tts/mimo")
    assert tts_secrets.get("tts/mimo") == ""
    assert fake.store == {}


def test_without_keyring_falls_back_to_process_memory(monkeypatch):
    """钥匙串不可用：写入返回 False（调用方据此提示「仅本次运行有效」），仍能读回。"""
    _patch(monkeypatch, None)
    tts_secrets.reset_memory()

    assert tts_secrets.available() is False
    assert tts_secrets.set("tts/mimo", "k-2") is False
    assert tts_secrets.get("tts/mimo") == "k-2", "进程内存兜底必须能读回来"
    tts_secrets.clear("tts/mimo")
    assert tts_secrets.get("tts/mimo") == ""


def test_keyring_write_failure_keeps_memory_copy(monkeypatch):
    """钥匙串写入抛异常（系统拒绝）：不得丢值，退化为内存并返回 False。"""
    _patch(monkeypatch, _FakeKeyring(fail_set=True))
    tts_secrets.reset_memory()

    assert tts_secrets.set("tts/mimo", "k-3") is False
    assert tts_secrets.get("tts/mimo") == "k-3"


def test_empty_value_clears_both_stores(monkeypatch):
    """空值 = 清除：钥匙串与内存都不能留着旧 Key（用户清空输入框的语义）。"""
    fake = _FakeKeyring()
    _patch(monkeypatch, fake)
    tts_secrets.reset_memory()
    assert tts_secrets.set("tts/mimo", "k-4") is True

    assert tts_secrets.set("tts/mimo", "") is False
    assert tts_secrets.get("tts/mimo") == ""
    assert fake.store == {}


def test_keyring_read_error_degrades_to_memory(monkeypatch):
    """读取抛异常（凭据管理器被锁）：不向上抛，回落到内存值。"""
    class _Broken(_FakeKeyring):
        def get_password(self, service, ref):
            raise RuntimeError("locked")

    _patch(monkeypatch, _Broken())
    tts_secrets.reset_memory()
    tts_secrets.set("tts/mimo", "k-5")

    assert tts_secrets.get("tts/mimo") == "k-5"


def test_mimo_ref_is_namespaced():
    """ref 取名规则：tts/<backend>，与 chat 的 provider/<id> 同构、天然不冲突。"""
    assert tts_secrets.MIMO_API_KEY_REF == "tts/mimo"
    assert tts_secrets.SERVICE_NAME == "dsh-pet-standalone"
