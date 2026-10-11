# -*- coding: utf-8 -*-
"""抽签（右键「抽支签」）的聚焦回归。

钉住五件事：

1. **签库形状**：24 支、编号唯一、四档数量对、签诗两句、白话解短（≤14 字）；
2. **加权 + 真随机**：上上少见、中平最多；注入 ``random.Random(seed)`` 时结果可复现；
3. **文案口径**：气泡 ≤4 行、语音一句念完、无感叹号、无医疗/疾病词；
4. **配置清洗**：两个开关非法值回落默认，绝不抛异常；
5. **红线**：纯逻辑模块零 Qt（服务层只在真正用到窗口时才惰性 import）。
"""

from __future__ import annotations

import random
import re

import pytest

from pet import divination, divination_quotes as quotes


# --------------------------------------------------------------------------- #
# 签库形状
# --------------------------------------------------------------------------- #

def test_stick_library_shape() -> None:
    """48 支签、编号 1..48 唯一、每支字段齐全且签诗两句。"""
    assert len(quotes.STICKS) == 48
    numbers = [stick["no"] for stick in quotes.STICKS]
    assert numbers == list(range(1, 49)), "编号必须是连续的 1..48"
    assert divination.total_sticks() == 48
    for stick in quotes.STICKS:
        assert stick["level"] in quotes.LEVELS, stick
        assert len(stick["poem"]) == 2, f"第 {stick['no']} 签要有两句签诗"
        assert all(str(line).strip() for line in stick["poem"])
        assert str(stick["plain"]).strip()
        assert str(stick["good"]).strip() and str(stick["bad"]).strip()


def test_level_distribution_matches_reference() -> None:
    """四档数量：上上 4 / 上 8 / 中平 26 / 下 10（24 支时代是 2/5/12/5，第四轮扩签后重算）。"""
    counts: dict[str, int] = {level: 0 for level in quotes.LEVELS}
    for stick in quotes.STICKS:
        counts[stick["level"]] += 1
    assert counts == {"上上": 4, "上": 8, "中平": 26, "下": 10}
    assert set(quotes.LEVEL_WEIGHTS) == set(quotes.LEVELS)
    assert quotes.LEVEL_WEIGHTS["上上"] < quotes.LEVEL_WEIGHTS["上"]
    assert quotes.LEVEL_WEIGHTS["中平"] == max(quotes.LEVEL_WEIGHTS.values())


def test_draw_skips_excluded_sticks() -> None:
    """``exclude`` 里的签号不会再被抽到；整副抽完时 exclude 自动作废（开新一轮）。"""
    rng = random.Random(11)
    drawn: set[int] = set()
    for _ in range(48):
        stick = divination.draw(rng, exclude=drawn)
        number = int(stick["no"])
        assert number not in drawn, f"第 {number} 签被重复抽到"
        drawn.add(number)
    assert drawn == set(range(1, 49)), "一轮应该刚好把 48 支抽完"
    again = divination.draw(rng, exclude=drawn)      # 整副抽完 → 新一轮
    assert int(again["no"]) in range(1, 49)


def test_draw_with_partial_exclude_keeps_the_pool_usable() -> None:
    """只排除一小部分时仍然能抽（且不会抽到被排除的）。"""
    excluded = {1, 2, 3}
    for seed in range(20):
        stick = divination.draw(random.Random(seed), exclude=excluded)
        assert int(stick["no"]) not in excluded


def test_plain_text_is_short() -> None:
    """她 2026-10-10 的反馈：别拖沓。白话解单条 ≤14 字。"""
    too_long = [stick["plain"] for stick in quotes.STICKS if len(str(stick["plain"])) > 14]
    assert not too_long, "这些白话解还嫌长：" + " / ".join(too_long)


def test_all_text_has_no_exclamation_or_health_claims() -> None:
    """腔调与安全底线：不许感叹号，不许医疗/疾病/寿命/怀孕类词。"""
    forbidden = ("！", "!", "治疗", "疾病", "痊愈", "寿命", "怀孕", "药")
    texts: list[str] = []
    for stick in quotes.STICKS:
        texts.extend([*stick["poem"], stick["plain"], stick["good"], stick["bad"]])
        texts.append(divination.bubble_text(stick))
        texts.append(divination.speech_text(stick))
    hits = [text for text in texts if any(word in text for word in forbidden)]
    assert not hits, "文案越界：" + " / ".join(hits)


# --------------------------------------------------------------------------- #
# 抽签行为
# --------------------------------------------------------------------------- #

def test_draw_is_deterministic_with_injected_rng() -> None:
    """抽签本身是真随机，但注入 rng 时必须可复现（用例与调试都靠这条）。"""
    first = divination.draw(random.Random(20261010))
    second = divination.draw(random.Random(20261010))
    assert first == second
    assert first in quotes.STICKS or first["no"] in [s["no"] for s in quotes.STICKS]


def test_draw_covers_every_level_and_is_weighted() -> None:
    """抽 4000 次：四档都能出现，且中平最多、上上最少（加权生效）。"""
    rng = random.Random(7)
    tally: dict[str, int] = {level: 0 for level in quotes.LEVELS}
    for _ in range(4000):
        tally[divination.draw(rng)["level"]] += 1
    assert all(count > 0 for count in tally.values()), f"有档位抽不到：{tally}"
    assert tally["中平"] == max(tally.values()), f"中平该最多：{tally}"
    assert tally["上上"] == min(tally.values()), f"上上该最少：{tally}"


def test_bubble_is_five_short_lines() -> None:
    """气泡固定五行：签头 / 签诗 / 白话解 / 宜忌 / 今日宜穿色（黄历按日柱算）。"""
    from datetime import date

    stick = divination.draw(random.Random(1))
    day = date(2026, 10, 10)  # 丁巳日：宜穿青绿、避藏青（两个公开来源交叉验证过）
    lines = divination.bubble_text(stick, day).splitlines()
    assert len(lines) == 5, lines
    assert lines[0] == f"第 {stick['no']} 签 · {stick['level']}"
    assert lines[1] == "".join(stick["poem"])
    assert lines[2] == stick["plain"]
    assert lines[3] == f"宜 {stick['good']} · 忌 {stick['bad']}"
    assert lines[4] == "今日宜穿 青绿 · 避 藏青"


def test_speech_text_is_one_breath() -> None:
    """语音一句话念完，且以句号收尾（TTS 断句友好），末尾带今日穿衣色。"""
    from datetime import date

    stick = divination.draw(random.Random(2))
    text = divination.speech_text(stick, date(2026, 10, 10))
    assert text.startswith(f"第 {stick['no']} 签，{stick['level']}。")
    assert stick["plain"] in text
    assert text.endswith("今日宜穿青绿，避藏青。")
    assert "\n" not in text


# --------------------------------------------------------------------------- #
# 配置清洗
# --------------------------------------------------------------------------- #

def test_normalize_defaults_and_illegal_values() -> None:
    assert divination.normalize_divination_config({}) == {"speak": True, "animation": True}
    assert divination.normalize_divination_config(
        {"divination_speak": False, "divination_animation": False}
    ) == {"speak": False, "animation": False}
    # 非法值回落默认，绝不抛
    assert divination.normalize_divination_config(
        {"divination_speak": None, "divination_animation": "x"}
    ) == {"speak": True, "animation": True}

    class Cfg:
        def get(self, key, default=None):
            return {"divination_speak": 0}.get(key, default)

    assert divination.normalize_divination_config(Cfg())["speak"] is False


# --------------------------------------------------------------------------- #
# 红线
# --------------------------------------------------------------------------- #

def test_pure_logic_modules_are_qt_free() -> None:
    """纯逻辑层零 Qt 只按真实 import 语句判定（文档里提到 Qt 不算违规）。"""
    pattern = re.compile(r"^\s*(?:from|import)\s+(PySide6|Qt)", re.MULTILINE)
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "pet"
    for name in ("divination.py", "divination_quotes.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert not pattern.search(text), f"{name} 不许 import Qt"


def test_service_works_without_a_window(monkeypatch) -> None:
    """没有窗口（或窗口不可见）时也要出内容：走桌面通知，不抛异常。"""
    pytest.importorskip("PySide6")  # 服务模块本身不 import Qt，但环境需能构造假 app 之外的路径
    from pet.divination_service import DivinationService

    notified: list[tuple[str, str]] = []
    spoken: list[str] = []

    class Channel:
        def speak(self, text, log_tag=""):
            spoken.append(text)

    class App:
        win = None
        config = {"divination_speak": True, "divination_animation": True}

        def ensure_audio_channel(self):
            return Channel()

        def system_notify(self, title, message):
            notified.append((title, message))

    service = DivinationService(App())
    stick = service.draw_now(random.Random(5))
    assert stick["no"] in range(1, 49)
    # 桌面通知的标题＝签头（"第 5 签 · 中平"），正文＝气泡四行
    assert notified and notified[0][0] == f"第 {stick['no']} 签 · {stick['level']}"
    assert spoken and spoken[0].startswith(f"第 {stick['no']} 签")
    assert service.config() == {"speak": True, "animation": True}


def test_service_obeys_speak_switch() -> None:
    """关掉语音开关时只出气泡，不碰音频通道。"""
    pytest.importorskip("PySide6")
    from pet.divination_service import DivinationService

    spoken: list[str] = []
    notified: list[tuple[str, str]] = []

    class App:
        win = None
        config = {"divination_speak": False}

        def ensure_audio_channel(self):
            spoken.append("不该被调用")
            return None

        def system_notify(self, title, message):
            notified.append((title, message))

    service = DivinationService(App())
    service.draw_now(random.Random(6))
    assert not spoken
    assert notified


def test_service_round_has_no_repeats_and_records_history(tmp_path, monkeypatch) -> None:
    """一轮 48 把不重复；每把都写进本机记录；上上签卡落到（测试的）桌面目录。"""
    pytest.importorskip("PySide6")
    from pet import divination_service
    from pet.divination_service import DivinationService, last_record

    monkeypatch.setattr(divination_service, "desktop_dir", lambda: tmp_path)

    class Cfg(dict):
        dir = tmp_path

    class App:
        win = None
        config = Cfg({"divination_speak": False, "divination_animation": False})

        def system_notify(self, title, message):
            pass

    service = DivinationService(App())
    seen: set[int] = set()
    for _ in range(48):
        stick = service.draw_now(random.Random(len(seen)))
        number = int(stick["no"])
        assert number not in seen, f"服务层出现重复：第 {number} 签"
        seen.add(number)
    assert len(seen) == 48 and service.drawn_this_round() == 48

    history = tmp_path / "divination-history.jsonl"
    assert history.exists(), "抽签记录文件没写出来"
    assert len(history.read_text(encoding="utf-8").strip().splitlines()) == 48
    record = last_record(tmp_path)
    assert record and int(record["no"]) in range(1, 49) and record["level"] in ("上上", "上", "中平", "下")

    # 上上会落签卡（测试里桌面被 monkeypatch 到 tmp_path，别污染她真桌面）
    cards = list(tmp_path.glob("签卡-*.png"))
    assert cards, "抽满一轮应该至少抽到过上上并落一张签卡"
