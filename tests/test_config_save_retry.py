# -*- coding: utf-8 -*-
"""Config.save() 的抗瞬时占用回归（2026-09-23 实机「保存失败」排查后补）。

机制（已实机复现）：Windows 上 `os.replace` 需要目标可替换；当另一个进程——杀软/
索引服务/同步软件、或**设置进程隔离时那个独立设置进程**——正把 config.json 打开着，
它会以 `[WinError 5] 拒绝访问` 或 `[WinError 32] 另一个程序正在使用此文件` 失败。
占用一释放就成功，所以属**可自愈的瞬时错误**，不该把「保存失败」丢给用户。

2026-10-04 合并上游后改口径：替换走 `pet/config.py::atomic_replace_with_retry`
（上游同名实现，判定集合从「只认 PermissionError」放宽到
`_REPLACE_CONFLICT_WINERRORS = (5, 32)` 与 `EACCES/EPERM`，退避 20ms 起、200ms
封顶），并且**失败也把临时文件清掉**（上游口径：残留会污染配置目录）；失败真因
仍留在 `last_save_error`，设置页据此把话说清楚。本文件随之改用上游的
`_REPLACE_RETRY_BASE_DELAY` 置零，测试里的临时文件前缀也改成 config.py 的
`config.json.<pid>.tmp` 口径。
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pet.config as config_mod  # noqa: E402
from pet.config import Config  # noqa: E402


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    """退避基数在测试里置零：断言的是「重试了」，不是「睡够了」。"""
    monkeypatch.setattr(config_mod, "_REPLACE_RETRY_BASE_DELAY", 0.0)
    monkeypatch.setattr(config_mod, "_REPLACE_RETRY_MAX_DELAY", 0.0)


def _flaky_replace(monkeypatch, failures: int, exc: Exception | None = None):
    """让前 ``failures`` 次 os.replace 失败，之后走真实实现。"""
    real = os.replace
    calls = {"n": 0}

    def fake(src, dst):
        if calls["n"] < failures:
            calls["n"] += 1
            raise exc or PermissionError(
                errno.EACCES, "拒绝访问。", f"{src} -> {dst}"
            )
        return real(src, dst)

    monkeypatch.setattr(config_mod.os, "replace", fake)
    return calls


def test_transient_lock_is_retried_and_save_succeeds(tmp_path, monkeypatch):
    """瞬时占用（前两次失败）：重试后成功落盘，且不留 tmp。"""
    cfg = Config(base=tmp_path)
    cfg.set("scale", 1.25)
    calls = _flaky_replace(monkeypatch, failures=2)

    assert cfg.save() is True
    assert calls["n"] == 2, "前两次确实被拒了"
    assert cfg.last_save_error == ""
    assert not list(cfg.path.parent.glob(f"{cfg.path.name}.*.tmp")), "成功后不该留下临时文件"

    reloaded = Config(base=tmp_path)
    assert reloaded.get("scale") == 1.25, "重试后必须真的写进去了"


def test_winerror32_is_treated_as_transient_conflict(tmp_path, monkeypatch):
    """共享冲突不只有 WinError 5：正在被别处读句柄占用的文件回 WinError 32。"""
    cfg = Config(base=tmp_path)
    cfg.set("scale", 1.5)
    exc = PermissionError(errno.EACCES, "另一个程序正在使用此文件，进程无法访问。")
    exc.winerror = 32  # CPython 在 Windows 上给 OSError 挂的字段
    calls = _flaky_replace(monkeypatch, failures=1, exc=exc)

    assert cfg.save() is True
    assert calls["n"] == 1
    assert Config(base=tmp_path).get("scale") == 1.5


def test_persistent_lock_reports_reason_and_cleans_temp(tmp_path, monkeypatch):
    """真的一直占用：返回 False、给出原因，并清掉自己的 tmp（不留垃圾）。"""
    cfg = Config(base=tmp_path)
    cfg.set("scale", 1.0)
    assert cfg.save() is True  # 先有一份基线
    cfg.set("scale", 1.75)
    calls = _flaky_replace(monkeypatch, failures=99)

    assert cfg.save() is False
    assert calls["n"] == 5, "重试到 attempts 上限（默认 5）才认输"
    assert cfg.last_save_error, "失败要说清原因（上层要显示给用户）"
    assert "拒绝访问" in cfg.last_save_error or "EACCES" in cfg.last_save_error
    assert not list(cfg.path.parent.glob(f"{cfg.path.name}.*.tmp")), \
        "失败出口也必须清掉自己的 tmp（上游口径：残留会污染配置目录）"
    assert Config(base=tmp_path).get("scale") == 1.0, "磁盘上仍是旧值（没被写坏）"


def test_non_conflict_oserror_is_not_retried(tmp_path, monkeypatch):
    """非共享冲突类错误（如磁盘满）不该重试：直接失败并记录。"""
    cfg = Config(base=tmp_path)
    calls = _flaky_replace(monkeypatch, failures=99,
                           exc=OSError(errno.ENOSPC, "磁盘空间不足"))

    assert cfg.save() is False
    assert "磁盘空间不足" in cfg.last_save_error
    assert calls["n"] == 1, "只试一次就够，别对真实错误反复重试"


def test_successful_save_clears_previous_error(tmp_path, monkeypatch):
    """上一次失败的残影不能留在 last_save_error 里（否则下次成功还报旧原因）。"""
    cfg = Config(base=tmp_path)
    _flaky_replace(monkeypatch, failures=99)
    assert cfg.save() is False
    assert cfg.last_save_error

    monkeypatch.undo()
    assert cfg.save() is True
    assert cfg.last_save_error == ""


def test_successful_save_sweeps_stale_temps_from_other_processes(tmp_path):
    """成功落盘后清掉别的进程留下的陈旧 tmp。"""
    cfg = Config(base=tmp_path)
    cfg.path.parent.mkdir(parents=True, exist_ok=True)  # save() 才建目录，这里先备好
    stale = cfg.path.with_name(f"{cfg.path.name}.99999.tmp")
    stale.write_text("{}", encoding="utf-8")

    assert cfg.save() is True
    assert not stale.exists(), "成功保存后，更旧的 tmp 应当被清掉"
    assert not list(cfg.path.parent.glob(f"{cfg.path.name}.*.tmp"))
