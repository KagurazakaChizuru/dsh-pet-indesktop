"""整点报时设置页（host-based，对齐 settings_pet_controls）。

build_chime_page(host) 返回可加入侧栏的内容页；控件挂载在 host.* 上，
由 dialog 的 _write_config 在保存时统一调用 apply_chime_config(host) 落盘。
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .chime_clock import (
    ChimeStore,
    default_chime_data,
    period_hour_text,
    quotes_path,
)
from .chime_tts import DEFAULT_VOICE, EDGE_VOICES, ChimeTts
from .settings_widgets import (
    BrowserSpinBox,
    ModernSelect,
    SettingRow,
    SettingsSection,
    ToggleSwitch,
)

logger = logging.getLogger(__name__)


def _config_dir(host) -> Path:
    config = host.config
    return Path(getattr(config, "dir", Path(".")))


def _quotes_store(host) -> ChimeStore:
    config = host.config
    path = quotes_path(
        getattr(config, "dir", Path(".")),
        str(getattr(config, "instance_id", "") or ""),
    )
    return ChimeStore(path)


def _load_quotes(host) -> dict:
    try:
        return _quotes_store(host).load()
    except Exception:
        logger.exception("台词库读取失败，使用内置库")
        from .chime_clock import default_quotes_data
        return default_quotes_data()


# ------------------------------------------------------------ 页面构建

def build_chime_page(host) -> QWidget:
    cfg_raw = host.config.get("chime")
    cfg = cfg_raw if isinstance(cfg_raw, dict) else default_chime_data()

    content = QWidget()
    content.setProperty("contentMaxWidth", 760)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    # ---- 总开关
    host.chime_enabled_check = ToggleSwitch(host)
    host.chime_enabled_check.setChecked(bool(cfg.get("enabled", False)))
    layout.addWidget(SettingsSection("总开关", [
        SettingRow(
            "chime_enabled", "启用整点报时",
            "开启后到整点或自定义时刻，桌宠会弹出气泡，并可选用语音朗读。",
            host.chime_enabled_check,
        ),
    ], content))

    # ---- 报时频率
    host.chime_interval_select = ModernSelect(host, width=160)
    host.chime_interval_select.addItem("仅整点（每 60 分钟）", 0)
    host.chime_interval_select.addItem("每 30 分钟", 30)
    host.chime_interval_select.addItem("每 15 分钟", 15)
    try:
        host.chime_interval_select.setCurrentData(int(cfg.get("interval_minutes", 0) or 0))
    except (TypeError, ValueError):
        host.chime_interval_select.setCurrentData(0)
    host.chime_hour_start = QTimeEdit(host)
    host.chime_hour_start.setDisplayFormat("HH:mm")
    host.chime_hour_start.setTime(QTime.fromString(str(cfg.get("hour_start", "08:00")), "HH:mm"))
    host.chime_hour_end = QTimeEdit(host)
    host.chime_hour_end.setDisplayFormat("HH:mm")
    host.chime_hour_end.setTime(QTime.fromString(str(cfg.get("hour_end", "22:00")), "HH:mm"))
    layout.addWidget(SettingsSection("报时频率", [
        SettingRow(
            "chime_interval", "频率",
            "按固定间隔报时；「仅整点」为原整点模式。",
            host.chime_interval_select,
        ),
        SettingRow(
            "chime_hour_start", "开始时段",
            "仅在该时段内报时。",
            host.chime_hour_start,
        ),
        SettingRow(
            "chime_hour_end", "结束时段",
            "超过该时刻后停止报时。",
            host.chime_hour_end,
        ),
    ], content))

    # ---- 自定义时刻（精确到秒，带快捷预设）
    host.chime_custom_list = QListWidget(host)
    host.chime_custom_list.setFixedHeight(96)
    for item in cfg.get("custom_times") or []:
        host.chime_custom_list.addItem(str(item))
    host.chime_custom_edit = QTimeEdit(host)
    host.chime_custom_edit.setDisplayFormat("HH:mm:ss")
    host.chime_custom_edit.setTime(QTime(8, 30, 0))
    host.chime_custom_add_btn = QPushButton("添加", host)
    host.chime_custom_del_btn = QPushButton("删除选中", host)
    host.chime_custom_add_btn.clicked.connect(lambda: _add_custom_time(host))
    host.chime_custom_del_btn.clicked.connect(lambda: _del_custom_time(host))
    custom_control = QWidget(host)
    custom_control_layout = QVBoxLayout(custom_control)
    custom_control_layout.setContentsMargins(0, 0, 0, 0)
    custom_control_layout.setSpacing(6)
    custom_control_layout.addWidget(host.chime_custom_list)
    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    btn_row.addWidget(host.chime_custom_edit)
    btn_row.addWidget(host.chime_custom_add_btn)
    btn_row.addWidget(host.chime_custom_del_btn)
    btn_row.addStretch(1)
    custom_control_layout.addLayout(btn_row)
    presets = QHBoxLayout()
    presets.setSpacing(6)
    for preset in ("09:00:00", "12:00:00", "14:30:00", "18:00:00", "21:30:00"):
        btn = QPushButton(preset[:5], host)
        btn.setFixedWidth(64)
        btn.clicked.connect(lambda _=False, p=preset: _add_preset_time(host, p))
        presets.addWidget(btn)
    presets.addStretch(1)
    custom_control_layout.addLayout(presets)
    layout.addWidget(SettingsSection("自定义时刻", [
        SettingRow(
            "chime_custom_times", "秒级时刻",
            "可手填或点下方预设一键添加；到点播报一次。",
            custom_control,
            stacked=True,
        ),
    ], content))

    # ---- 语音播报
    host.chime_speech_check = ToggleSwitch(host)
    host.chime_speech_check.setChecked(bool(cfg.get("speech_enabled", True)))
    host.chime_voice_select = ModernSelect(host, width=240)
    for label, vid in EDGE_VOICES:
        host.chime_voice_select.addItem(label, vid)
    host.chime_voice_select.setCurrentData(str(cfg.get("voice") or DEFAULT_VOICE))
    host.chime_voice_custom = QLineEdit(host)
    host.chime_voice_custom.setPlaceholderText("留空使用上方音色")
    host.chime_voice_custom.setText(str(cfg.get("voice_custom") or ""))
    host.chime_rate_spin = BrowserSpinBox(host)
    host.chime_rate_spin.setRange(-50, 50)
    host.chime_rate_spin.setSuffix("%")
    host.chime_rate_spin.setToolTip("语速偏移，0 为默认")
    try:
        host.chime_rate_spin.setValue(int(cfg.get("rate", 0) or 0))
    except (TypeError, ValueError):
        host.chime_rate_spin.setValue(0)
    host.chime_pitch_spin = BrowserSpinBox(host)
    host.chime_pitch_spin.setRange(-50, 50)
    host.chime_pitch_spin.setSuffix("Hz")
    host.chime_pitch_spin.setToolTip("音调偏移，0 为默认")
    try:
        host.chime_pitch_spin.setValue(int(cfg.get("pitch", 0) or 0))
    except (TypeError, ValueError):
        host.chime_pitch_spin.setValue(0)
    tune_control = QWidget(host)
    tune_layout = QHBoxLayout(tune_control)
    tune_layout.setContentsMargins(0, 0, 0, 0)
    tune_layout.setSpacing(8)
    tune_layout.addWidget(host.chime_rate_spin)
    tune_layout.addWidget(host.chime_pitch_spin)
    tune_layout.addStretch(1)
    host.chime_volume_spin = BrowserSpinBox(host)
    host.chime_volume_spin.setRange(0, 100)
    host.chime_volume_spin.setSuffix("%")
    try:
        host.chime_volume_spin.setValue(round(float(cfg.get("volume", 1.0)) * 100))
    except (TypeError, ValueError):
        host.chime_volume_spin.setValue(100)
    host.chime_preview_btn = QPushButton("试听", host)
    host.chime_preview_btn.clicked.connect(lambda: _preview(host))
    volume_control = QWidget(host)
    volume_layout = QHBoxLayout(volume_control)
    volume_layout.setContentsMargins(0, 0, 0, 0)
    volume_layout.setSpacing(8)
    volume_layout.addWidget(host.chime_volume_spin)
    volume_layout.addWidget(host.chime_preview_btn)
    volume_layout.addStretch(1)
    layout.addWidget(SettingsSection("语音播报", [
        SettingRow(
            "chime_speech", "语音播报",
            "用选定音色朗读报时内容。基于 edge-tts 在线合成，需联网。",
            host.chime_speech_check,
        ),
        SettingRow(
            "chime_voice", "音色",
            "选择内置音色，点右侧「试听」立即播放当前效果。",
            host.chime_voice_select,
        ),
        SettingRow(
            "chime_voice_custom", "自定义音色 ID",
            "edge-tts 音色 ID，如 zh-CN-liaoning-XiaobeiNeural；留空使用上方音色。",
            host.chime_voice_custom,
        ),
        SettingRow(
            "chime_tune", "语速 / 音调",
            "语速按百分比、音调按 Hz 微调，0 为默认。",
            tune_control,
        ),
        SettingRow(
            "chime_volume", "音量",
            "语音播报音量，不影响点击音效。",
            volume_control,
        ),
    ], content))

    # ---- 台词与歌词
    host.chime_quote_check = ToggleSwitch(host)
    host.chime_quote_check.setChecked(bool(cfg.get("quote_enabled", True)))
    quotes = _load_quotes(host)
    host.chime_movies_edit = QPlainTextEdit(host)
    host.chime_movies_edit.setFixedHeight(120)
    host.chime_movies_edit.setPlainText("\n".join(quotes.get("movies", [])))
    host.chime_lyrics_edit = QPlainTextEdit(host)
    host.chime_lyrics_edit.setFixedHeight(120)
    host.chime_lyrics_edit.setPlainText("\n".join(quotes.get("lyrics", [])))
    layout.addWidget(SettingsSection("随机台词与歌词", [
        SettingRow(
            "chime_quote", "附带随机台词",
            "报时时从台词/歌词库随机选一句展示；关闭则只报时间。",
            host.chime_quote_check,
        ),
        SettingRow(
            "chime_movies", "电影台词",
            "每行一条；清空后恢复内置 30 条经典台词。",
            host.chime_movies_edit,
            stacked=True,
        ),
        SettingRow(
            "chime_lyrics", "歌词",
            "每行一条；清空后恢复内置 30 条经典歌词。",
            host.chime_lyrics_edit,
            stacked=True,
        ),
    ], content))

    return content


# ------------------------------------------------------------ 控件行为

def _add_custom_time(host) -> None:
    text = host.chime_custom_edit.time().toString("HH:mm:ss")
    existing = {
        host.chime_custom_list.item(i).text()
        for i in range(host.chime_custom_list.count())
    }
    if text not in existing:
        host.chime_custom_list.addItem(text)
    host.chime_custom_list.setCurrentRow(host.chime_custom_list.count() - 1)


def _add_preset_time(host, preset: str) -> None:
    existing = {
        host.chime_custom_list.item(i).text()
        for i in range(host.chime_custom_list.count())
    }
    if preset not in existing:
        host.chime_custom_list.addItem(preset)
    host.chime_custom_list.setCurrentRow(host.chime_custom_list.count() - 1)


def _del_custom_time(host) -> None:
    row = host.chime_custom_list.currentRow()
    if row >= 0:
        host.chime_custom_list.takeItem(row)


def _effective_voice(host) -> str:
    """当前生效音色：自定义 ID 优先，其次内置下拉。"""
    custom = str(host.chime_voice_custom.text() or "").strip()
    return custom or str(host.chime_voice_select.currentData() or DEFAULT_VOICE)


def _preview(host) -> None:
    """试听：用当前生效音色、语速、音调与音量合成示例文案并播放。"""
    text = f"现在是{period_hour_text(datetime.now())}，语音播报试听，一切正常。"
    voice = _effective_voice(host)
    volume = float(host.chime_volume_spin.value()) / 100.0
    rate = int(host.chime_rate_spin.value())
    pitch = int(host.chime_pitch_spin.value())
    try:
        tts = ChimeTts(_config_dir(host) / "chime_tts_cache")
        tts.speak(text, voice=voice, volume=volume, rate=rate, pitch=pitch)
    except Exception:
        # 试听失败只记日志，绝不让异常冒泡到 GUI 事件循环导致闪退
        logger.exception("试听失败（音色=%s rate=%s pitch=%s）", voice, rate, pitch)


# ------------------------------------------------------------ 保存

def apply_chime_config(host) -> None:
    """从控件收集整点报时配置并写回 config + 台词库落盘。"""
    cfg = dict(host.config.get("chime") or default_chime_data())
    cfg["enabled"] = bool(host.chime_enabled_check.isChecked())
    cfg["hourly_enabled"] = True
    cfg["interval_minutes"] = int(host.chime_interval_select.currentData() or 0)
    cfg["hour_start"] = host.chime_hour_start.time().toString("HH:mm")
    cfg["hour_end"] = host.chime_hour_end.time().toString("HH:mm")
    times: list[str] = []
    for i in range(host.chime_custom_list.count()):
        text = host.chime_custom_list.item(i).text().strip()
        if text and text not in times:
            times.append(text)
    cfg["custom_times"] = times
    cfg["speech_enabled"] = bool(host.chime_speech_check.isChecked())
    cfg["voice"] = str(host.chime_voice_select.currentData() or DEFAULT_VOICE)
    cfg["voice_custom"] = str(host.chime_voice_custom.text() or "").strip()
    cfg["rate"] = int(host.chime_rate_spin.value())
    cfg["pitch"] = int(host.chime_pitch_spin.value())
    cfg["volume"] = float(host.chime_volume_spin.value()) / 100.0
    cfg["quote_enabled"] = bool(host.chime_quote_check.isChecked())
    host.config.set("chime", cfg)

    movies = [
        line.strip()
        for line in host.chime_movies_edit.toPlainText().splitlines()
        if line.strip()
    ]
    lyrics = [
        line.strip()
        for line in host.chime_lyrics_edit.toPlainText().splitlines()
        if line.strip()
    ]
    _quotes_store(host).save({"movies": movies, "lyrics": lyrics})
