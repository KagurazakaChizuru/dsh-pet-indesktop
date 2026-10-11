# -*- coding: utf-8 -*-
"""设置页「互动 · 抽签」域的控件与行（本模块构建，``modern_settings_dialog`` 只留接线）。

与 ``settings_file_interpret`` 同口径：

* 控件在 :func:`create_divination_controls` 里建好并挂到对话框属性上
  （``dialog.divination_speak_check`` / ``dialog.divination_animation_check``），
  初值从 config 读；
* 行在 :func:`build_divination_rows` 里构建，由 ``settings_interaction`` 挂进
  「互动」域的「抽签」标签；
* 落盘在 :func:`save_divination_settings` 里做，被 ``_write_config`` 调用一行。

**只有两个开关、没有任何个人信息**——这是它与已归档的占星功能最大的区别
（那套要出生日期/时刻/地点，见 ``.scratch/fortune-astrology``）。
"""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from . import almanac
from .settings_widgets import SettingRow, SettingsSection, ToggleSwitch


def create_divination_controls(dialog) -> None:
    """建两个开关与「今日穿色」预览标签并挂到对话框上（幂等：重复调用不重建）。"""
    if getattr(dialog, "divination_speak_check", None) is None:
        dialog.divination_speak_check = ToggleSwitch(dialog)
    if getattr(dialog, "divination_animation_check", None) is None:
        dialog.divination_animation_check = ToggleSwitch(dialog)
    if getattr(dialog, "divination_color_label", None) is None:
        label = QLabel(dialog)
        label.setObjectName("divinationColorPreview")
        label.setWordWrap(True)
        dialog.divination_color_label = label
    config = getattr(dialog, "config", None)
    getter = getattr(config, "get", None)
    speak = True if not callable(getter) else bool(getter("divination_speak", True))
    animation = True if not callable(getter) else bool(getter("divination_animation", True))
    dialog.divination_speak_check.setChecked(speak)
    dialog.divination_animation_check.setChecked(animation)
    # 预览随打开设置的那一天刷新（同日多次打开内容一致）。
    dialog.divination_color_label.setText(almanac.detail_line(date.today()))


def build_divination_rows(dialog) -> list[SettingRow]:
    """「抽签」组的行（顺序即渲染顺序）。"""
    return [
        SettingRow(
            "divination_speak",
            "抽签语音朗读",
            "抽到签时用语音报时的音色念出来（签号、吉凶、白话解、宜忌，"
            "以及今日宜穿的黄历色）；与报时共用同一条音频通道，不会叠音。",
            dialog.divination_speak_check,
        ),
        SettingRow(
            "divination_animation",
            "摇签动作",
            "抽签时请角色动一下（在当前角色的动作池里挑一个合适的；"
            "动作池里没有合适的动作就安静跳过，不会出错）。",
            dialog.divination_animation_check,
        ),
    ]


def build_daily_color_rows(dialog) -> list[SettingRow]:
    """「今日穿色」组的行：只读预览（不落盘、没有开关）。"""
    return [
        SettingRow(
            "divination_daily_color",
            "今日宜穿色",
            "按当日日柱天干的五行推（黄历）：宜穿＝生我者，避＝克我者。"
            "右键「抽支签」时气泡第五行与语音末尾会带上这一句；每天自动更新。",
            dialog.divination_color_label,
            stacked=True,  # 长文本占满一行宽度（否则被挤在右侧窄栏里折成四行）
        ),
    ]


def build_divination_page(dialog) -> QWidget:
    """「趣味」域整页：两节——抽签 / 今日穿色（挂到域导航，见 ``_rebuild_domain_navigation``）。"""
    content = QWidget(dialog)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(18)
    layout.addWidget(SettingsSection("抽签", build_divination_rows(dialog), content))
    layout.addWidget(SettingsSection("今日穿色", build_daily_color_rows(dialog), content))
    layout.addStretch(1)
    return content


def save_divination_settings(dialog) -> None:
    """把两个开关写回 config（``_write_config`` 调用）。"""
    speak = getattr(dialog, "divination_speak_check", None)
    animation = getattr(dialog, "divination_animation_check", None)
    if speak is not None:
        dialog.config.set("divination_speak", bool(speak.isChecked()))
    if animation is not None:
        dialog.config.set("divination_animation", bool(animation.isChecked()))
