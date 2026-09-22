# -*- coding: utf-8 -*-
"""语音报时设置页（现代设置对话框侧栏页）。

配置键（config.py 顶层平铺键）：
    voice_chime_enabled / voice_chime_schedule / voice_chime_custom_times /
    voice_chime_volume / voice_chime_show_bubble / voice_chime_show_quote /
    voice_chime_custom_quotes_zh / voice_chime_custom_quotes_en /
    voice_chime_tts_backend / voice_chime_tts_fallback
    + 各合成后端的字段键（见 ``pet/tts/*.py`` 的 ``fields[].key``）

**合成后端是 provider 驱动的**：本页不写死任何后端——「语音引擎」下拉与每个后端的
参数行都由 ``pet/tts`` 注册表里的 ``TtsProvider.fields`` 生成（控件类型、标题、提示、
依赖隐藏全在 provider 里声明）。接入新 TTS 只需新增 provider 模块，本文件不用改。

密码类字段（``kind="secret"``）的值只写系统钥匙串（``pet/tts_secrets``），**不落
config.json**；行提示会显示「已保存 / 未设置」与「钥匙串可用 / 仅本次运行」。

风格对齐 pet/exploration_watchdog_settings.py：自含 QWidget 页，
提供 apply_to_config，
由 modern_settings_dialog.py 注册为侧边栏「语音」总域下的「语音报时」分组并参与
_write_config 保存。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import tts, tts_secrets
from .modern_settings_dialog import (
    BrowserSpinBox,
    SettingRow,
    SettingsSection,
    ToggleSwitch,
)
from .settings_widgets import ModernSelect
from .voice_chime import (
    DEFAULT_BACKEND,
    DEFAULT_SHOW_BUBBLE,
    DEFAULT_SHOW_QUOTE,
    DEFAULT_TTS_FALLBACK,
    DEFAULT_VOLUME,
    SCHEDULE_KEYS,
    SCHEDULE_LABELS,
    clean_backend,
    clean_flag,
    clean_schedule,
    clean_volume,
)


class VoiceChimeSettingsPage(QWidget):
    """自含语音报时设置页（后端参数行由 provider 声明生成）。"""

    # 用户点击「试听」时发出（payload: 当前试听文案，空串表示按当前时间组装）
    preview_requested = Signal(str)

    def __init__(self, config, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config

        # 字段控件/行：按 (provider_id, 字段名) 与配置键索引，供显隐与读写使用
        self._field_widgets: dict[str, QWidget] = {}
        self._secret_edits: dict[str, QLineEdit] = {}
        self._field_rows: dict[tuple[str, str], SettingRow] = {}
        self._secret_cleared: set[str] = set()

        # ---- 基础设置 ----
        self.enabled_check = ToggleSwitch(self)
        self.enabled_check.setChecked(bool(self.config.get("voice_chime_enabled", False)))

        # ---- 调度 ----
        self.schedule_select = ModernSelect(self, width=170)
        for key in SCHEDULE_KEYS:
            self.schedule_select.addItem(SCHEDULE_LABELS[key], key)
        self.schedule_select.setCurrentData(clean_schedule(self.config.get("voice_chime_schedule", "hourly")))

        self.custom_edit = QLineEdit(self)
        self.custom_edit.setText(str(self.config.get("voice_chime_custom_times", "") or ""))
        self.custom_edit.setPlaceholderText("如 08:30, 12:00, 23:59（逗号分隔）")
        self.schedule_select.currentIndexChanged.connect(self._refresh_custom_enabled)

        # ---- 合成后端（provider 驱动）----
        self.backend_select = ModernSelect(self, width=230)
        for provider in tts.providers():
            self.backend_select.addItem(provider.label, provider.id)
        self.backend_select.setCurrentData(
            clean_backend(self.config.get("voice_chime_tts_backend", DEFAULT_BACKEND))
        )
        self.backend_select.currentIndexChanged.connect(self._refresh_backend_controls)

        self.fallback_check = ToggleSwitch(self)
        self.fallback_check.setChecked(
            clean_flag(
                self.config.get("voice_chime_tts_fallback", DEFAULT_TTS_FALLBACK),
                DEFAULT_TTS_FALLBACK,
            )
        )

        provider_rows: list[SettingRow] = []
        for provider in tts.providers():
            for spec in provider.fields:
                row = self._build_field_row(provider, spec)
                self._field_rows[(provider.id, spec.name)] = row
                provider_rows.append(row)
        self._bind_provider_aliases()

        # ---- 语音（与后端无关的部分）----
        # 音量/数字一律走纯逻辑层清洗：config.json 被手改成非法值时回落默认值，
        # 绝不让设置页在构造期抛异常把用户挡在设置界面之外。
        self.volume_spin = BrowserSpinBox(self)
        self.volume_spin.setRange(0, 100)
        self.volume_spin.setSuffix(" %")
        self.volume_spin.setValue(clean_volume(self.config.get("voice_chime_volume", DEFAULT_VOLUME)))

        self.bubble_check = ToggleSwitch(self)
        self.bubble_check.setChecked(bool(self.config.get("voice_chime_show_bubble", DEFAULT_SHOW_BUBBLE)))

        self.quote_check = ToggleSwitch(self)
        self.quote_check.setChecked(bool(self.config.get("voice_chime_show_quote", DEFAULT_SHOW_QUOTE)))

        # ---- 自定义台词/歌词（一行一条；留空回退内置库）----
        self.custom_zh_edit = QPlainTextEdit(self)
        self.custom_zh_edit.setMinimumSize(280, 84)
        self.custom_zh_edit.setMaximumHeight(180)
        self.custom_zh_edit.setPlaceholderText(
            "每行一条，例如：\n又是元气满满的一天～\n该起来喝口水、动一动啦。"
        )
        self.custom_zh_edit.setPlainText(str(self.config.get("voice_chime_custom_quotes_zh", "") or ""))

        self.custom_en_edit = QPlainTextEdit(self)
        self.custom_en_edit.setMinimumSize(280, 84)
        self.custom_en_edit.setMaximumHeight(180)
        self.custom_en_edit.setPlaceholderText(
            "One quote per line, e.g.\nTake a short break and stretch.\nYou've got this!"
        )
        self.custom_en_edit.setPlainText(str(self.config.get("voice_chime_custom_quotes_en", "") or ""))

        self.preview_btn = QPushButton("立即试听", self)
        self.preview_btn.setToolTip("按当前配置立即播报一句报时+台词（无需等待报时点）")
        self.preview_btn.clicked.connect(self._on_preview_clicked)

        # ---- Layout ----
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        root.addWidget(
            SettingsSection(
                "基础设置",
                [
                    SettingRow("voice_chime_enabled", "启用语音报时", "开启后按下方调度规则定时语音报时，并附台词/歌词（每 8 小时整体换一批，同周期内按序轮换）。", self.enabled_check),
                    SettingRow("voice_chime_schedule", "报时频率", "整点 / 每30分钟 / 每15分钟 / 每5分钟 / 每分钟 / 自定义时间点。", self.schedule_select),
                    SettingRow("voice_chime_custom_times", "自定义时间点", "仅「自定义时间点」模式生效；HH:MM 逗号分隔，如 08:30, 12:00。", self.custom_edit),
                ],
                self,
            )
        )

        root.addWidget(
            SettingsSection(
                "合成后端",
                [
                    SettingRow(
                        "voice_chime_tts_backend",
                        "语音引擎",
                        "用哪家在线语音合成；该引擎自己的参数行在下方（切换引擎时跟着换）。",
                        self.backend_select,
                    ),
                    SettingRow(
                        "voice_chime_tts_fallback",
                        "失败自动回退",
                        "主引擎合成失败（没配 Key / 网络不通 / 接口报错）时自动改用后备引擎，"
                        "都不可用才只显示气泡不出声。",
                        self.fallback_check,
                    ),
                    *provider_rows,
                ],
                self,
            )
        )

        root.addWidget(
            SettingsSection(
                "语音",
                [
                    SettingRow("voice_chime_volume", "音量", "报时播放音量（0-100）。", self.volume_spin),
                    SettingRow("voice_chime_show_bubble", "报时气泡", "报时时在桌宠头顶显示气泡文字（含台词/歌词）。", self.bubble_check),
                    SettingRow("voice_chime_show_quote", "台词/歌词", "报时时附带台词/歌词（每 8 小时整体换一批，同周期内每次报时按序取不同条目）；关闭后仅播报时间文本。", self.quote_check),
                    SettingRow("voice_chime_preview", "立即试听", "按当前配置立即播报一句“报时文本 + 台词/歌词”，无需等待报时点。", self.preview_btn),
                ],
                self,
            )
        )

        root.addWidget(
            SettingsSection(
                "台词/歌词",
                [
                    SettingRow(
                        "voice_chime_custom_quotes_zh",
                        "自定义台词/歌词（中文）",
                        "每行一条，与内置中文库的关系：填了就整体替换内置库参与分批轮换"
                        "（每 8 小时整体换一批，同一周期内每次报时按序取不同条目）；"
                        "留空则自动回退内置中文台词库。中文音色报时时使用这里的内容。",
                        self.custom_zh_edit,
                        stacked=True,
                    ),
                    SettingRow(
                        "voice_chime_custom_quotes_en",
                        "自定义台词/歌词（英文）",
                        "每行一条，规则同上（每 8 小时整体换一批，同一周期内按序取不同条目）；"
                        "留空则自动回退内置英文台词库，与中文库各自独立分批轮换。"
                        "非中文音色报时时使用这里的内容。",
                        self.custom_en_edit,
                        stacked=True,
                    ),
                ],
                self,
            )
        )

        self._refresh_custom_enabled()
        self._refresh_backend_controls()

    # ------------------------------------------------------------ provider 字段 → 控件
    def _build_field_row(self, provider, spec: tts.TtsField) -> SettingRow:
        widget = self._build_field_widget(provider, spec)
        self._field_widgets[spec.key] = widget
        # 多行框整行铺开（stacked）：写在右侧一栏里放不下一句话
        return SettingRow(
            spec.key, spec.label, spec.hint, widget, stacked=spec.kind == "multiline"
        )

    def _build_field_widget(self, provider, spec: tts.TtsField) -> QWidget:
        """按字段声明造控件（select / multiline / number / flag / secret / text）。"""
        current = provider.clean(spec, self.config.get(spec.key, spec.default))
        if spec.kind == "select":
            select = ModernSelect(self, width=230)
            for value, label in spec.options:
                select.addItem(label, value)
            if select.findData(current) < 0 and spec.allow_custom:
                # 配置值不在清单里（手改配置、或清单里那项已被厂家下架）：
                # 明确标出来，别让用户以为它还是有效选项（provider 的提示会说清后果）。
                select.addItem(f"不在清单里：{current}", current)
            select.setCurrentData(current)
            select.currentIndexChanged.connect(self._refresh_backend_controls)
            return select
        if spec.kind == "number":
            spin = BrowserSpinBox(self)
            spin.setRange(spec.minimum, spec.maximum)
            if spec.suffix:
                spin.setSuffix(spec.suffix)
            spin.setValue(int(current))
            if spec.hint:
                spin.setToolTip(spec.hint)
            return spin
        if spec.kind == "flag":
            toggle = ToggleSwitch(self)
            toggle.setChecked(bool(current))
            return toggle
        if spec.kind == "secret":
            # 凭据：只写钥匙串；留空 = 不改动已保存的值。
            edit = QLineEdit(self)
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setPlaceholderText("粘贴 API Key（留空不变）")
            clear = QPushButton("清除", self)
            clear.setToolTip("清除已保存的凭据")
            clear.clicked.connect(lambda _=False, s=spec: self._on_secret_clear(s))
            box = QWidget(self)
            layout = QHBoxLayout(box)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            layout.addWidget(edit)
            layout.addWidget(clear)
            self._secret_edits[spec.key] = edit
            return box
        if spec.kind == "multiline":
            # 整句描述（风格指令、音色描述）用多行框：单行框在设置页里根本看不全
            area = QPlainTextEdit(self)
            area.setMinimumHeight(max(48, int(spec.min_height)))
            area.setMaximumHeight(180)
            if spec.placeholder:
                area.setPlaceholderText(spec.placeholder)
            area.setPlainText(str(current or ""))
            return area
        edit = QLineEdit(self)
        if spec.max_length:
            edit.setMaxLength(spec.max_length)
        if spec.placeholder:
            edit.setPlaceholderText(spec.placeholder)
        edit.setText(str(current or ""))
        return edit

    def _bind_provider_aliases(self) -> None:
        """历史属性名别名（测试与既有调用点按名字取控件）；新代码请用 _field_widgets。"""
        aliases = {
            "voice_select": "voice_chime_voice",
            "rate_spin": "voice_chime_rate",
            "pitch_spin": "voice_chime_pitch",
            "mimo_model_select": "voice_chime_mimo_model",
            "mimo_voice_select": "voice_chime_mimo_voice",
            "mimo_style_edit": "voice_chime_mimo_style",
            "mimo_key_edit": "voice_chime_mimo_api_key",
        }
        for name, key in aliases.items():
            # 密钥类字段的容器是「输入框 + 清除按钮」，别名要指向输入框本身
            widget = self._secret_edits.get(key) or self._field_widgets.get(key)
            if widget is not None:
                setattr(self, name, widget)
        # 行别名：切后端显隐的既有断言按名字取
        for name, (provider_id, field_name) in {
            "edge_voice_row": ("edge", "voice"),
            "edge_rate_row": ("edge", "rate"),
            "edge_pitch_row": ("edge", "pitch"),
            "mimo_model_row": ("mimo", "model"),
            "mimo_voice_row": ("mimo", "voice"),
            "mimo_style_row": ("mimo", "style"),
            "mimo_key_row": ("mimo", "api_key"),
        }.items():
            row = self._field_rows.get((provider_id, field_name))
            if row is not None:
                setattr(self, name, row)

    # ------------------------------------------------------------ 交互
    def _on_preview_clicked(self) -> None:
        # 先落盘当前控件值，再发试听信号（服务端按最新配置合成播放）
        self.apply_to_config()
        self.preview_requested.emit("")

    def _refresh_custom_enabled(self) -> None:
        is_custom = self.schedule_select.currentData() == "custom"
        self.custom_edit.setEnabled(is_custom)

    def _refresh_backend_controls(self) -> None:
        """按当前后端显隐参数行：只留选中后端的字段，并处理字段间依赖。"""
        backend = clean_backend(self.backend_select.currentData() or DEFAULT_BACKEND)
        for provider in tts.providers():
            active = provider.id == backend
            values = self._current_field_values(provider)
            for spec in provider.fields:
                row = self._field_rows.get((provider.id, spec.name))
                if row is None:
                    continue
                visible = active
                if visible and spec.hidden_when is not None:
                    dep_name, dep_value = spec.hidden_when
                    visible = values.get(dep_name) != dep_value
                row.setVisible(visible)
        self._refresh_secret_hints()

    def _current_field_values(self, provider) -> dict:
        """读当前控件值（已按 provider 规则清洗），供依赖显隐判断。"""
        values: dict = {}
        for spec in provider.fields:
            widget = self._field_widgets.get(spec.key)
            if widget is None:
                continue
            values[spec.name] = provider.clean(spec, self._read_widget(spec, widget))
        return values

    def _read_widget(self, spec: tts.TtsField, widget: QWidget):
        if spec.kind == "flag":
            return widget.isChecked()
        if spec.kind == "number":
            return widget.value()
        if spec.kind == "select":
            return widget.currentData()
        if spec.kind == "secret":
            return self._secret_edits.get(spec.key).text().strip() if spec.key in self._secret_edits else ""
        if spec.kind == "multiline":
            return widget.toPlainText()
        return widget.text()

    def _on_secret_clear(self, spec: tts.TtsField) -> None:
        """清除已保存的凭据：立即生效（服务下一次合成即读不到）。"""
        tts_secrets.clear(spec.secret_ref)
        edit = self._secret_edits.get(spec.key)
        if edit is not None:
            edit.clear()
        self._secret_cleared.add(spec.key)
        self._refresh_secret_hints()

    def _refresh_secret_hints(self) -> None:
        for provider in tts.providers():
            for spec in tts.secret_fields(provider):
                row = self._field_rows.get((provider.id, spec.name))
                if row is None:
                    continue
                saved = bool(tts_secrets.get(spec.secret_ref))
                state = "已保存" if saved else "未设置"
                where = "系统钥匙串" if tts_secrets.available() else "本次运行（钥匙串不可用）"
                row.hint_label.setText(f"{spec.hint}\n凭据：{state}（{where}）")

    # ------------------------------------------------------------ 配置读写
    def apply_to_config(self) -> None:
        """把控件值合并写回 config（含各后端的字段键；凭据只进钥匙串）。"""
        if self.config is None:
            return
        self.config.set("voice_chime_enabled", self.enabled_check.isChecked())
        self.config.set("voice_chime_schedule", self.schedule_select.currentData() or "hourly")
        self.config.set("voice_chime_custom_times", self.custom_edit.text().strip())
        self.config.set("voice_chime_volume", self.volume_spin.value())
        self.config.set("voice_chime_show_bubble", self.bubble_check.isChecked())
        self.config.set("voice_chime_show_quote", self.quote_check.isChecked())
        self.config.set("voice_chime_custom_quotes_zh", self.custom_zh_edit.toPlainText().strip())
        self.config.set("voice_chime_custom_quotes_en", self.custom_en_edit.toPlainText().strip())
        self.config.set("voice_chime_tts_backend", clean_backend(self.backend_select.currentData()))
        self.config.set("voice_chime_tts_fallback", self.fallback_check.isChecked())
        for provider in tts.providers():
            for spec in provider.fields:
                if spec.kind == "secret":
                    self._apply_secret(spec)
                    continue
                widget = self._field_widgets.get(spec.key)
                if widget is None:
                    continue
                self.config.set(spec.key, provider.clean(spec, self._read_widget(spec, widget)))

    def _apply_secret(self, spec: tts.TtsField) -> None:
        """凭据写入口：非空即保存（钥匙串优先），输入框随即清空。

        空输入且没按过「清除」= 不改动已保存的凭据（避免每次保存设置都把凭据抹掉）。
        """
        edit = self._secret_edits.get(spec.key)
        if edit is None:
            return
        text = edit.text().strip()
        if text:
            tts_secrets.set(spec.secret_ref, text)
            edit.clear()
            self._secret_cleared.discard(spec.key)
        self._refresh_secret_hints()
