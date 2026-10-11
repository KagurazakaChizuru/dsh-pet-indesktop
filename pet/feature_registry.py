# -*- coding: utf-8 -*-
"""自有功能（进程内功能型 DLC）的**登记处**。

出处：上游 phase-01 §5.1/§6 —— 进程内功能只经公开 API 接入，按配置启停，
关闭时**不加载**（懒创建 + 释放），失败不许阻塞 Core。

约定（新加自有功能照抄）：

* 一个功能 = 一条 :class:`FeatureSpec`（`feature_id` / `gate_key` / `factory` / 设置页模块）；
* `gate_key=None` 表示**手动触发型**（点菜单才创建，没有常驻开关，如抽签）；
* 有 `gate_key` 的表示**可常驻型**（如节日提醒、语音报时）——`sync()` 按开关启动或释放；
* 服务对象若提供 `start()` / `stop()` / `apply_config()`，注册表会按同一套语义调用；
* 工厂只接收 :class:`~pet.feature_context.FeatureContext`，**不许**再拿 AppShell/PetWindow。

本模块零 Qt、零应用导入，可直接单测。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from .feature_context import FeatureContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureSpec:
    """一条自有功能的登记项。"""

    feature_id: str
    description: str = ""
    #: 常驻总开关的配置键；``None`` = 手动触发型（无常驻）
    gate_key: str | None = None
    #: 懒创建工厂：``(context) -> service``
    factory: Callable[[FeatureContext], Any] | None = None
    #: 设置页所在模块（便于交接与文档核对；不参与运行）
    settings_module: str = ""
    #: 菜单动作 id（若有）
    menu_action: str = ""
    #: 备注：迁移状态等
    note: str = ""


class FeatureRegistry:
    """按配置启停自有功能，并保证"关闭＝不加载"。"""

    def __init__(self, context_factory: Callable[[str], FeatureContext]) -> None:
        self._context_factory = context_factory
        self._specs: dict[str, FeatureSpec] = {}
        self._instances: dict[str, Any] = {}

    # ------------------------------------------------------------ 登记
    def register(self, spec: FeatureSpec) -> FeatureSpec:
        if spec.feature_id in self._specs:
            raise ValueError(f"功能 id 重复登记: {spec.feature_id}")
        self._specs[spec.feature_id] = spec
        return spec

    def specs(self) -> tuple[FeatureSpec, ...]:
        return tuple(self._specs.values())

    def spec(self, feature_id: str) -> FeatureSpec | None:
        return self._specs.get(feature_id)

    def context(self, feature_id: str) -> FeatureContext:
        return self._context_factory(feature_id)

    # ------------------------------------------------------------ 门控
    def is_enabled(self, feature_id: str) -> bool:
        spec = self._specs.get(feature_id)
        if spec is None or spec.gate_key is None:
            return False
        return bool(self.context(feature_id).config(spec.gate_key, False))

    def running_ids(self) -> tuple[str, ...]:
        return tuple(self._instances)

    # ------------------------------------------------------------ 取用
    def get(self, feature_id: str, *, create: bool = True) -> Any:
        """拿功能实例（懒创建并缓存）；``create=False`` 时只查已创建的。"""
        if feature_id in self._instances:
            return self._instances[feature_id]
        spec = self._specs.get(feature_id)
        if spec is None or not create:
            return None
        if spec.factory is None:
            return None
        try:
            service = spec.factory(self.context(feature_id))
        except Exception:
            # 单个功能起不来不许阻塞 Core（上游 §6 原文）
            logger.exception("功能 %s 创建失败", feature_id)
            return None
        self._instances[feature_id] = service
        return service

    def stop(self, feature_id: str) -> None:
        service = self._instances.pop(feature_id, None)
        if service is None:
            return
        stop = getattr(service, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                logger.exception("功能 %s 停止失败", feature_id)

    def sync(self) -> None:
        """按各功能的 `gate_key` 启停（常驻型）；手动触发型不参与。"""
        for spec in self._specs.values():
            if spec.gate_key is None:
                continue
            if self.is_enabled(spec.feature_id):
                service = self.get(spec.feature_id)
                if service is None:
                    continue
                if getattr(service, "is_running", None) and service.is_running():
                    apply_config = getattr(service, "apply_config", None)
                    if callable(apply_config):
                        apply_config()
                else:
                    start = getattr(service, "start", None)
                    if callable(start):
                        try:
                            start()
                        except Exception:
                            logger.exception("功能 %s 启动失败", spec.feature_id)
            else:
                self.stop(spec.feature_id)

    def sync_one(self, feature_id: str) -> None:
        """只同步一个功能（设置页保存后按开关即时生效用）。"""
        spec = self._specs.get(feature_id)
        if spec is None or spec.gate_key is None:
            return
        if self.is_enabled(feature_id):
            self.get(feature_id)
        else:
            self.stop(feature_id)
