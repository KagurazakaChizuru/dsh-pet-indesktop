# -*- coding: utf-8 -*-
"""自有功能接入面与登记表的契约（R1/R2：进程内功能型 DLC）。

守三件事：
① `FeatureContext` 只暴露注入进来的函数，**不把 AppShell / PetWindow 交出去**；
② `FeatureRegistry` 的懒创建、门控启停、失败不阻塞 Core；
③ 两个新模块**零 Qt**（上游 phase-01 对纯逻辑层的一贯要求）。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from pet.feature_context import FeatureContext
from pet.feature_registry import FeatureRegistry, FeatureSpec

PET = Path(__file__).resolve().parent.parent / "pet"


class FakeService:
    """假的常驻功能：只记调用轨迹。"""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.started = False

    def start(self) -> None:
        self.started = True
        self.calls.append("start")

    def stop(self) -> None:
        self.started = False
        self.calls.append("stop")

    def is_running(self) -> bool:
        return self.started

    def apply_config(self) -> None:
        self.calls.append("apply_config")


# ------------------------------------------------------------ 接入面


def test_context_falls_back_to_default_without_config_source() -> None:
    ctx = FeatureContext(feature_id="x")
    assert ctx.config("missing", 7) == 7
    assert ctx.flag("missing", False) is False
    assert ctx.visible() is False          # 没注入可见性 → 视为不可见
    assert ctx.available_animations() == set()
    assert ctx.blocked() is False
    assert ctx.data_path() is None


def test_context_swallows_broken_core_hooks() -> None:
    def boom(*_a, **_k):
        raise RuntimeError("Core 挂了")

    ctx = FeatureContext(
        feature_id="x",
        config_get=boom,
        is_visible=boom,
        animations=boom,
        bubble_blocked=boom,
        data_dir=boom,
    )
    assert ctx.config("k", "d") == "d"
    assert ctx.visible() is False
    assert ctx.available_animations() == set()
    assert ctx.blocked() is False
    assert ctx.data_path() is None


def test_bubble_tries_direct_then_fallback_then_gives_up() -> None:
    seen: list[tuple[str, str]] = []

    def direct(text, duration_ms):
        seen.append(("direct", text))
        if text == "坏":
            raise RuntimeError("直写失败")

    def fallback(text, duration_ms):
        seen.append(("fallback", text))

    ctx = FeatureContext(feature_id="x", show_bubble=direct, show_bubble_fallback=fallback)
    assert ctx.bubble("好", 100) is True
    assert seen == [("direct", "好")]
    assert ctx.bubble("坏", 100) is True          # 直写失败 → 兜底成功
    assert seen[-1] == ("fallback", "坏")

    empty = FeatureContext(feature_id="x")
    assert empty.bubble("没人接") is False
    assert empty.bubble("") is False


def test_context_actions_report_success_without_raising() -> None:
    played: list[str] = []
    spoken: list[str] = []
    told: list[tuple[str, str]] = []
    ctx = FeatureContext(
        feature_id="x",
        play_animation=played.append,
        speak=spoken.append,
        notify=lambda t, m: told.append((t, m)),
    )
    assert ctx.animate("写福字") is True and played == ["写福字"]
    assert ctx.say("一句话") is True and spoken == ["一句话"]
    assert ctx.tell("签头", "正文") is True and told == [("签头", "正文")]
    assert ctx.animate("") is False and ctx.say("") is False


def test_context_has_no_backdoor_to_app_or_window() -> None:
    """合同：接入面只能是一组函数——多出对象句柄就等于绕过了公开 API。"""
    names = {f.name for f in dataclasses.fields(FeatureContext)}
    assert names == {
        "feature_id", "config_get", "is_visible", "show_bubble", "show_bubble_fallback",
        "bubble_blocked", "animations", "play_animation", "speak", "notify", "data_dir", "extra",
    }, "接入面字段变了就要同步 review：新字段必须是函数/数据，不能是 AppShell/PetWindow"


# ------------------------------------------------------------ 登记表


def _registry(calls: list[str], gates: dict[str, bool]) -> FeatureRegistry:
    ctx = FeatureContext(feature_id="t", config_get=lambda key, default=None: gates.get(key, default))
    registry = FeatureRegistry(lambda feature_id: ctx)
    registry.register(FeatureSpec(feature_id="resident", gate_key="resident_on",
                                  factory=lambda _c: FakeService(calls)))
    registry.register(FeatureSpec(feature_id="manual", gate_key=None,
                                  factory=lambda _c: FakeService(calls)))
    return registry


def test_registry_refuses_duplicate_ids() -> None:
    registry = _registry([], {})
    with pytest.raises(ValueError):
        registry.register(FeatureSpec(feature_id="resident"))


def test_registry_is_lazy_and_caches_one_instance() -> None:
    calls: list[str] = []
    registry = _registry(calls, {"resident_on": True})
    assert registry.running_ids() == ()          # 没人要 → 一个都没建
    first = registry.get("resident")
    assert first is registry.get("resident")     # 只有一个实例
    assert registry.running_ids() == ("resident",)
    assert registry.get("nope") is None
    assert registry.get("resident", create=False) is first


def test_registry_sync_follows_gate_and_releases_on_off() -> None:
    calls: list[str] = []
    gates = {"resident_on": True}
    registry = _registry(calls, gates)

    registry.sync()
    assert calls == ["start"]
    registry.sync()                              # 已运行 → 只刷新配置
    assert calls == ["start", "apply_config"]

    gates["resident_on"] = False
    registry.sync()
    assert calls == ["start", "apply_config", "stop"]
    assert registry.running_ids() == ()           # 关闭＝释放对象（"关闭即不加载"）


def test_registry_manual_features_never_auto_start() -> None:
    calls: list[str] = []
    registry = _registry(calls, {})
    registry.sync()
    assert calls == []                            # 手动触发型不参与自动启停
    assert registry.get("manual") is not None      # 但点菜单仍能懒创建
    assert registry.is_enabled("manual") is False  # 它没有常驻开关


def test_registry_factory_failure_does_not_block_core() -> None:
    def boom(_ctx):
        raise RuntimeError("这个功能坏了")

    registry = FeatureRegistry(lambda feature_id: FeatureContext(feature_id=feature_id))
    registry.register(FeatureSpec(feature_id="broken", gate_key="on", factory=boom))
    assert registry.get("broken") is None          # 不抛，只记日志
    assert registry.running_ids() == ()


def test_registry_stop_swallows_service_errors() -> None:
    class Bad(FakeService):
        def stop(self) -> None:
            raise RuntimeError("停不掉")

    registry = FeatureRegistry(lambda feature_id: FeatureContext(feature_id=feature_id))
    registry.register(FeatureSpec(feature_id="bad", gate_key=None, factory=lambda _c: Bad([])))
    registry.get("bad")
    registry.stop("bad")                            # 不抛
    assert registry.running_ids() == ()


# ------------------------------------------------------------ 零 Qt


@pytest.mark.parametrize("module", ["feature_context.py", "feature_registry.py"])
def test_new_modules_are_zero_qt(module: str) -> None:
    source = (PET / module).read_text(encoding="utf-8")
    assert "PySide6" not in source and "from PySide" not in source
