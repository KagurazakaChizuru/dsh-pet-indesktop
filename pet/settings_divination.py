# -*- coding: utf-8 -*-
"""设置页「趣味」域：每日一签（控件创建 / 行装配 / 保存）。

与「文件识别」域同形——本域的控件与行全部在本模块构建，`modern_settings_dialog.py`
只做三处接线（建控件、域导航挂页、保存委托），避免主对话框继续膨胀。

**2026-10-16 起本域只有签，没有黄历**：她原话「不需要看黄历写宜忌了，我不是说了
忘掉之前的吗」。原先的「今日穿色」一节（当日日柱天干五行 → 宜穿/次吉/避）连同
`pet/almanac.py` 一起删掉了，别再往这里捡回来。
"""
from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from .settings_widgets import SettingRow, SettingsSection, ToggleSwitch


def create_divination_controls(dialog) -> None:
    """在对话框上创建本域控件（幂等；行由 build_divination_rows 装配）。"""
    if getattr(dialog, "divination_enabled_check", None) is not None:
        return
    cfg = dialog.config
    dialog.divination_enabled_check = ToggleSwitch(dialog)
    dialog.divination_enabled_check.setChecked(bool(cfg.get("divination_enabled", True)))

    dialog.divination_speak_check = ToggleSwitch(dialog)
    dialog.divination_speak_check.setChecked(bool(cfg.get("divination_speak", False)))

    dialog.divination_hint_check = ToggleSwitch(dialog)
    dialog.divination_hint_check.setChecked(bool(cfg.get("divination_hint", True)))


def _preview_today(dialog) -> None:
    """「试听今天的签」：走与右键同一条路径出声+出气泡。

    接法与语音报时的试听一致——设置页只碰**父级的公开钩子**（`on_divination_draw`
    由 `app.py` 接到 `AppShell.trigger_divination_draw`），不碰窗口私有成员；
    独立设置进程没有父级 AppShell 时退到本地合成播放。
    """
    parent = dialog.parent() if hasattr(dialog, "parent") else None
    cb = getattr(parent, "on_divination_draw", None)
    if callable(cb):
        cb()
        return
    if getattr(dialog, "standalone", False):
        import datetime as _d

        from . import divination
        from .settings_standalone import preview_voice_chime

        preview_voice_chime(dialog, divination.speech_text(
            divination.draw_for_day(_d.date.today())))


def build_divination_rows(dialog) -> list[SettingRow]:
    """本域的设置行（objectName 前缀 `settingRow_divination_`，可被设置搜索索引）。"""
    preview_btn = QPushButton("试听今天的签", dialog)
    preview_btn.setToolTip("按当前配置立刻抽一次并出声（不动签号：还是今天那一支）")
    preview_btn.clicked.connect(lambda: _preview_today(dialog))
    return [
        SettingRow(
            "divination_enabled",
            "每日一签",
            "右键「抽支签」出当天的签：一天一支，当天再点显示同一支，次日 0 点换新；"
            "跨天一轮不重复（48 支走完再轮回）。签只跟日期有关，不涉及任何个人信息。",
            dialog.divination_enabled_check,
        ),
        SettingRow(
            "divination_speak",
            "抽签时念出来",
            "念一遍「抽签中...」起手，再接签题、四句签诗与解签"
            "（复用语音报时的音色与音频通道）。默认关闭。",
            dialog.divination_speak_check,
        ),
        SettingRow(
            "divination_preview",
            "试听今天的签",
            "按当前配置立刻走一遍抽签（含「抽签中...」与念签文）。**不改签号**："
            "还是今天那一支，只是让你先听听声音。",
            preview_btn,
        ),
        SettingRow(
            "divination_hint",
            "每天提醒一次",
            "当天还没抽签时，第一次点桌宠冒一行「今日的签还没看」。一天只提示一次，"
            "不会主动弹窗打扰。",
            dialog.divination_hint_check,
        ),
    ]


def build_divination_page(dialog) -> QWidget:
    """「趣味」域整页内容（_rebuild_domain_navigation 直接挂到域导航）。"""
    content = QWidget(dialog)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(18)
    layout.addWidget(SettingsSection("抽签", build_divination_rows(dialog), content))
    layout.addStretch(1)
    return content


def save_divination_settings(dialog) -> None:
    """保存委托：三个开关写回 config（顶层扁平键，与 config.py 登记一致）。"""
    if getattr(dialog, "divination_enabled_check", None) is None:
        return
    dialog.config.set("divination_enabled", bool(dialog.divination_enabled_check.isChecked()))
    dialog.config.set("divination_speak", bool(dialog.divination_speak_check.isChecked()))
    dialog.config.set("divination_hint", bool(dialog.divination_hint_check.isChecked()))
