# -*- coding: utf-8 -*-
"""捕获模式在 overlay 拓扑下的文案/消费口径回归（DS 审查 M15 / T4）。

overlay 拓扑不建 PetWindow，捕获依赖的窗旗标（``set_stream_capture_mode``）
在全仓没有 overlay 侧消费者，**重启也不生效**（审计 D：PHASE4_DESIGN 早期的
「重启级切换」设想从未落地）。故设置页文案改为如实说明不支持并置灰控件。
legacy 拓扑（PetWindow 唯一存在理由）文案与运行期切换路径保持不变。

纪律：offscreen；同步直调，不 sleep。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tests.test_overlay_dead_switches import _make_shell

app = QApplication.instance() or QApplication([])

LEGACY_HINT = "让 OBS 等工具能够枚举并捕获桌宠窗口。"


def _stream_capture_hint(tmp_path, monkeypatch, topology: str) -> str:
    """按拓扑构建设置页，取「直播捕获兼容」行的说明文本。"""
    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    monkeypatch.setattr(settings_mod.sys, "platform", "win32")
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", topology)
    dialog = settings_mod.ModernSettingsDialog(Config(tmp_path), include_ai=False)
    try:
        row = dialog.findChild(settings_mod.SettingRow,
                               "settingRow_stream_capture")
        assert row is not None, "Windows 设置页必须有直播捕获兼容行"
        return row.hint_label.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_stream_capture_copy_says_unsupported_under_overlay_topology(tmp_path, monkeypatch):
    """overlay 拓扑：文案如实说明单窗模式不支持（不再声称「重启后生效」）。"""
    hint = _stream_capture_hint(tmp_path, monkeypatch, "overlay")
    assert "暂不支持" in hint
    assert "重启" not in hint
    assert "让 OBS 等工具能够枚举并捕获桌宠窗口" in hint


def test_stream_capture_copy_unchanged_under_legacy_topology(tmp_path, monkeypatch):
    """legacy 拓扑：文案逐字不变（运行期切换仍有效，不该提示重启）。"""
    hint = _stream_capture_hint(tmp_path, monkeypatch, "legacy")
    assert hint == LEGACY_HINT
    assert "重启" not in hint


def test_overlay_topology_has_no_runtime_capture_switch(tmp_path, monkeypatch):
    """overlay 拓扑下不得触发 legacy 运行期切换路径（window.py:3826-3828）。

    该键在 overlay 侧只落 config，重启后由拓扑分流消费——壳上没有
    ``set_stream_capture_mode`` 这类运行期入口，refresh_settings 也不读它。
    """
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "overlay")
    shell, _lib = _make_shell(tmp_path, {"stream_capture_mode": False})
    try:
        assert not hasattr(shell, "set_stream_capture_mode")
        assert not hasattr(shell, "_stream_capture_mode")
        flags_before = shell.overlay.windowFlags()
        shell._config.set("stream_capture_mode", True)
        shell.refresh_settings()          # 不得抛错、不得改窗旗标
        assert shell.overlay.windowFlags() == flags_before
        assert shell._config.get("stream_capture_mode") is True
    finally:
        shell._delete_runtime_marker()
