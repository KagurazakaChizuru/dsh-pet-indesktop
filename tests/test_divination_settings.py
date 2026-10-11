# -*- coding: utf-8 -*-
"""「趣味」设置域（抽签 + 今日穿色）的聚焦回归。

机主 2026-10-10 的原话：「**抽签这个功能应该是放到设置里面的。归类为趣味**」——
所以抽签（含黄历穿色）从「互动」域的页内标签**搬成侧栏一级域「趣味」**：

1. 侧栏多一个「趣味」域，位置在「文件识别」之后、「更新」之前（更新恒末位）；
2. 域内两节：**抽签**（两个开关）/ **今日穿色**（只读预览，无开关）；
3. 三行都包在 ``SettingRow`` 内、objectName 是 ``settingRow_<键>``（保存链与搜索靠它）；
4. 开关落盘走既有 ``_write_config``（两个键仍在 config 里）；预览不落盘、随打开当天刷新。
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("PySide6")

from pet import almanac  # noqa: E402

EXPECTED_SIDEBAR = [
    "常规", "桌宠", "互动", "菜单", "桌面组件", "AI 与对话", "自动化与联动", "语音", "文件识别", "趣味", "更新",
]
DOMAIN_TITLE = "趣味"
ROWS = ("divination_speak", "divination_animation", "divination_last_draw", "divination_daily_color")


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(tmp_path, monkeypatch):
    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = _qapp()
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dlg = settings_mod.ModernSettingsDialog(Config(tmp_path), include_ai=True)
    yield dlg
    dlg.close()
    app.processEvents()


def _row(dialog, key: str):
    from pet.modern_settings_dialog import SettingRow

    found = dialog.findChild(SettingRow, f"settingRow_{key}")
    assert found is not None, f"缺少设置行 {key}"
    return found


def test_fun_domain_sits_between_file_and_update(dialog):
    labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]
    assert labels == EXPECTED_SIDEBAR
    assert labels[-1] == "更新", "「更新」必须留在末位（多处既有断言）"
    assert labels.index("趣味") == labels.index("文件识别") + 1


def test_fun_domain_has_two_sections_and_three_rows(dialog):
    from pet.modern_settings_dialog import QLabel

    labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]
    index = labels.index(DOMAIN_TITLE)
    page = dialog.pages.widget(index)
    titles = [label.text() for label in page.findChildren(QLabel, "sectionTitle")]
    assert titles == ["抽签", "今日穿色"], titles
    for key in ROWS:
        row = _row(dialog, key)
        assert page.isAncestorOf(row), f"{key} 必须落在「趣味」域页里"
        assert row.isVisibleTo(page) is True, f"{key} 在「趣味」域里不可见"


def test_last_draw_preview_reads_the_local_record(dialog):
    """「最近抽到」是只读预览：没抽过时给一句说明，有记录时显示签号与时间。"""
    from pet.modern_settings_dialog import QLabel

    preview = dialog.findChild(QLabel, "divinationLastDraw")
    assert preview is not None, "缺少「最近抽到」预览标签"
    assert "还没抽过" in preview.text(), preview.text()

    # 造一条记录再重建页面 → 预览应显示它（记录文件就在这个 tmp 配置目录里）
    history = dialog.config.dir / "divination-history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text('{"ts": "2026-10-10T22:00:00", "no": 25, "level": "上上"}\n', encoding="utf-8")
    dialog._rebuild_domain_navigation()
    labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]
    page = dialog.pages.widget(labels.index(DOMAIN_TITLE))
    refreshed = page.findChild(QLabel, "divinationLastDraw")
    assert refreshed is not None and "第 25 签 · 上上" in refreshed.text()


def test_daily_color_preview_shows_today(dialog):
    """预览是只读文本，内容＝当天黄历行（干支/五行/宜穿/避/冲煞）。"""
    from pet.modern_settings_dialog import QLabel

    preview = dialog.findChild(QLabel, "divinationColorPreview")
    assert preview is not None, "缺少今日穿色预览标签"
    text = preview.text()
    assert text == almanac.detail_line(date.today())
    assert "宜穿" in text and "避" in text and "冲" in text
    # 只读：不是可编辑控件，且没有落到 config 的开关
    assert not hasattr(preview, "isChecked")


def test_switches_persist_through_write_config(dialog):
    """两个开关仍走既有保存链（``_write_config``），键名与默认值不变。"""
    dialog.divination_speak_check.setChecked(False)
    dialog.divination_animation_check.setChecked(False)
    assert dialog._write_config() is True
    assert dialog.config.get("divination_speak") is False
    assert dialog.config.get("divination_animation") is False
    # 预览不落盘：config 里不该出现任何 divination_color* 键
    assert not [key for key in dialog.config.data if "divination_color" in key]
