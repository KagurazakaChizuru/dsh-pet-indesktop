# -*- coding: utf-8 -*-
"""抽签（右键「抽支签」）的聚焦回归。

钉住六件事：

1. **签库形状**：48 支、编号唯一、四档数量对、签题四字、签诗**两句七言**（各 7 字）、
   解曰 ≤14 字且不重复、**没有宜/忌字段**（2026-10-13 甲方案：签不承担"今天该干什么"）；
2. **加权 + 真随机**：上上少见、中平最多；注入 ``random.Random(seed)`` 时结果可复现；
3. **今日签**（第五轮）：按日期确定性取号——**同日恒定、跨天均匀、无 A/B 交替**，
   且"最近 N 天抽过的"不再出现（一轮不重复的跨天形态）；
4. **文案口径**：气泡五行（签头含签题 / 上句 / 下句 / 解曰 / 宜穿色）、语音一句念完、
   无感叹号、无医疗/疾病词、不出现你/我、解曰不下指令；
5. **配置清洗**：两个开关非法值回落默认，绝不抛异常；
6. **红线**：纯逻辑模块零 Qt（服务层只在真正用到窗口时才惰性 import），
   每日一签的取号**不 import random**（跨版本会漂）；签卡**不印宜忌**。
"""

from __future__ import annotations

import random
import re
from datetime import date, timedelta

import pytest

from pet import divination, divination_quotes as quotes


# --------------------------------------------------------------------------- #
# 签库形状
# --------------------------------------------------------------------------- #

def test_stick_library_shape() -> None:
    """48 支签、编号 1..48 唯一、每支字段齐全且签诗两句、**没有宜/忌**。"""
    assert len(quotes.STICKS) == 48
    numbers = [stick["no"] for stick in quotes.STICKS]
    assert numbers == list(range(1, 49)), "编号必须是连续的 1..48"
    assert divination.total_sticks() == 48
    for stick in quotes.STICKS:
        assert stick["level"] in quotes.LEVELS, stick
        assert len(stick["poem"]) == 2, f"第 {stick['no']} 签要有两句签诗"
        assert all(str(line).strip() for line in stick["poem"])
        assert str(stick["plain"]).strip()
        assert str(stick["title"]).strip()
        # 甲方案：宜/忌字段整体退场（那是黄历的活儿），字段表也就此钉住。
        assert set(stick) == {"no", "level", "title", "poem", "plain"}, stick


def test_stick_title_is_a_four_character_allusion() -> None:
    """签题＝四字典故/成语（照机主认可的「渭水垂钓」样张），且 48 个互不相同。"""
    titles = [str(stick.get("title", "")) for stick in quotes.STICKS]
    wrong = [(stick["no"], title) for stick, title in zip(quotes.STICKS, titles) if len(title) != 4]
    assert not wrong, f"签题必须四字：{wrong}"
    assert len(set(titles)) == 48, "签题不许重复"


def test_poem_lines_are_seven_characters_each() -> None:
    """甲形态：**两句七言**（每句 7 字、全签 14 字）——四句五言那版被她说"差点味道"。"""
    bad = [
        (stick["no"], line)
        for stick in quotes.STICKS
        for line in stick["poem"]
        if len(str(line).rstrip("，。！？、")) != 7
    ]
    assert not bad, f"这些句子不是七言：{bad}"
    lines = [str(line) for stick in quotes.STICKS for line in stick["poem"]]
    assert len(lines) == 96
    assert len(set(lines)) == 96, "签诗句子出现重复（48 支各自都该是自撰的）"


def test_level_distribution_matches_reference() -> None:
    """四档数量：上上 4 / 上 10 / 中平 24 / 下 10（重写只换文案，档位分布不变）。"""
    counts: dict[str, int] = {level: 0 for level in quotes.LEVELS}
    for stick in quotes.STICKS:
        counts[stick["level"]] += 1
    assert counts == {"上上": 4, "上": 10, "中平": 24, "下": 10}
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


def test_plain_text_is_short_and_unique() -> None:
    """她 2026-10-10 的反馈：别拖沓。解曰单条 ≤14 字，且 48 句不许有重复句。"""
    plains = [str(stick["plain"]) for stick in quotes.STICKS]
    too_long = [plain for plain in plains if len(plain) > 14]
    assert not too_long, "这些解曰还嫌长：" + " / ".join(too_long)
    assert len(set(plains)) == 48, "解曰出现重复句"


def test_plain_text_gives_a_state_of_affairs_not_a_to_do_list() -> None:
    """甲方案里解曰**只给这一签的气象/结论，不下指令**。

    机械能挡的是典型行动句式（"今天…去做/别做"这类）；"有没有指望人家照做"是人读的，
    所以这里只钉住词面，口径写在 ``pet/divination_quotes.py`` 的模块 docstring 里。
    """
    action_tails = ("去做", "别做", "要做", "该做", "记得", "务必", "应该", "先把", "别再", "不要")
    hits = [
        (stick["no"], stick["plain"], tail)
        for stick in quotes.STICKS
        for tail in action_tails
        if tail in str(stick["plain"])
    ]
    assert not hits, f"解曰写成了行动清单：{hits}"


def test_card_does_not_print_yiji_and_still_renders(tmp_path) -> None:
    """签卡跟着甲形态走：① 版式里**不再有宜/忌**；② 仍然画得出来、尺寸没变。"""
    from pathlib import Path

    from pet import divination_card

    source = (Path(__file__).resolve().parents[1] / "pet" / "divination_card.py").read_text(
        encoding="utf-8")
    for field in ('"good"', '"bad"'):
        assert field not in source, f"签卡还在读已经退场的字段：{field}"

    yiji_free = next(item for item in quotes.STICKS if item["level"] == "上上")
    for text in divination_card.card_texts(yiji_free, date(2026, 10, 10)):
        assert not text.startswith(("宜 ", "忌 ")), text
        assert not ("宜" in text and "忌" in text), text

    pytest.importorskip("PIL")
    from PIL import Image

    path = divination_card.render_card(yiji_free, tmp_path / "card.png")
    assert path.exists()
    with Image.open(path) as image:
        assert image.size == (760, 420)


def test_all_text_has_no_exclamation_or_health_claims() -> None:
    """腔调与安全底线：不许感叹号，不许医疗/疾病/寿命/怀孕类词，不出现你/我。"""
    forbidden = ("！", "!", "治疗", "疾病", "痊愈", "寿命", "怀孕", "药", "投资")
    pronouns = ("你", "我")
    texts: list[str] = []
    for stick in quotes.STICKS:
        texts.extend([*stick["poem"], stick["plain"], stick["title"]])
        texts.append(divination.bubble_text(stick))
        texts.append(divination.speech_text(stick))
    hits = [text for text in texts if any(word in text for word in forbidden)]
    assert not hits, "文案越界：" + " / ".join(hits)
    # 签诗是古人语气，不点名"你/我"；解曰与签题同样保持无人称。
    personal = [
        f"{stick['no']}:{field}"
        for stick in quotes.STICKS
        for field in ("plain", "title")
        if any(word in str(stick[field]) for word in pronouns)
    ]
    assert not personal, "解曰/签题里出现了你或我：" + " / ".join(personal)


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
    """气泡固定五行：签头（含签题）/ 七言上句 / 七言下句 / 解曰 / 今日宜穿色（黄历按日柱算）。"""
    stick = divination.draw(random.Random(1))
    day = date(2026, 10, 10)  # 丁巳日：宜穿绿、避蓝（两个公开来源交叉验证过）
    lines = divination.bubble_text(stick, day).splitlines()
    assert len(lines) == 5, lines
    assert lines[0] == f"第 {stick['no']} 签 · {stick['level']} · {stick['title']}"
    assert lines[1] == stick["poem"][0]
    assert lines[2] == stick["poem"][1]
    assert lines[3] == stick["plain"]
    assert lines[4] == "今日宜穿 绿 · 避 蓝"


def test_every_stick_keeps_the_five_line_bubble() -> None:
    """48 支逐支走一遍：去掉宜忌后腾出的那一行给签题，五行契约对全表成立。"""
    day = date(2026, 10, 10)
    for stick in quotes.STICKS:
        lines = divination.bubble_text(stick, day).splitlines()
        assert len(lines) == 5, (stick["no"], lines)
        assert lines[0].startswith(f"第 {stick['no']} 签 · {stick['level']} · ")
        assert len(lines[1].rstrip("，。！？、")) == 7
        assert len(lines[2].rstrip("，。！？、")) == 7
        assert lines[3] == stick["plain"]


def test_bubble_note_sits_before_the_color_line() -> None:
    """当天再点时那句提醒插在穿色行之前：签头/上句/下句/解曰四行一字不动。"""
    stick = divination.draw(random.Random(3))
    day = date(2026, 10, 10)
    lines = divination.bubble_text(stick, day, note="今天已经抽过啦").splitlines()
    assert len(lines) == 6, lines
    assert lines[:4] == divination.bubble_text(stick, day).splitlines()[:4]
    assert lines[4] == "今天已经抽过啦"
    assert lines[5] == "今日宜穿 绿 · 避 蓝"


def test_speech_text_is_one_breath() -> None:
    """语音一句话念完：签头 + 签题 + 两句签诗 + 解曰 + 今日穿衣色，句号收尾。"""
    stick = divination.draw(random.Random(2))
    text = divination.speech_text(stick, date(2026, 10, 10))
    assert text.startswith(f"第 {stick['no']} 签，{stick['level']}。")
    assert f"{stick['title']}。" in text
    assert "".join(stick["poem"]) in text
    assert stick["plain"] in text
    assert text.endswith("今日宜穿绿，避蓝。")
    assert "\n" not in text


# --------------------------------------------------------------------------- #
# 今日签：按日期确定性取号
# --------------------------------------------------------------------------- #

def test_daily_draw_is_constant_within_a_day() -> None:
    """同一天无论打多少次、什么时候打，都是同一支（跨进程重算也一致）。"""
    day = date(2026, 10, 13)
    numbers = {divination.daily_draw(day)["no"] for _ in range(5)}
    assert len(numbers) == 1, f"同一天取到了不同签：{numbers}"
    # 注入 recent（前几天的历史）不影响"同日恒定"
    again = {divination.daily_draw(day, recent={1, 2, 3})["no"] for _ in range(3)}
    assert len(again) == 1, f"带 recent 时同一天取到了不同签：{again}"


def test_daily_draw_next_day_is_not_todays_stick() -> None:
    """跨天换签：相邻两天不会是同一支，也不是 A/B 那样的机械交替。

    注：相邻不同是"最近 N 天不重复"带出来的**正常**结果（recent 里有昨天那支），
    所以这里不拿它当规律证据——真会退化的写法（按日洗牌取头一个 / 乘 k 模 k 抵消）
    表现的是"只有两三个值来回换"，下面按周期长度和窗口多样性钉住。
    """
    start = date(2026, 10, 13)
    played: list[int] = []
    for offset in range(60):
        day = start + timedelta(days=offset)
        stick = divination.daily_draw(day, recent=set(played[-divination.RECENT_DAYS:]))
        played.append(int(stick["no"]))
    assert played[0] != played[1], "次日不该还是同一支"
    assert len(set(played)) >= 30, f"60 天只出了 {len(set(played))} 支签，像是有规律"
    for period in (2, 3, 4, 5):
        assert any(
            played[index] != played[index - period]
            for index in range(period, len(played))
        ), f"取号序列出现了周期 {period} 的机械交替"


def test_daily_draw_avoids_the_recent_window() -> None:
    """跨天"一轮不重复"：最近 RECENT_DAYS 天抽过的签号不会出现在今天。"""
    start = date(2026, 4, 1)
    played: list[int] = []
    for offset in range(120):
        day = start + timedelta(days=offset)
        recent = set(played[-divination.RECENT_DAYS:])
        number = int(divination.daily_draw(day, recent=recent)["no"])
        assert number not in recent, f"{day} 抽到了最近 7 天里的第 {number} 签"
        played.append(number)


def test_daily_draw_spread_is_close_to_the_level_weights() -> None:
    """跨天分布尊重权重（上上最少、中平最多），且四档都出现过。

    取 3 年（1095 天）：每档观测占比与配置权重之差 ≤2 个百分点。
    """
    start = date(2026, 1, 1)
    tally: dict[str, int] = {level: 0 for level in quotes.LEVELS}
    for offset in range(1095):
        tally[divination.daily_draw(start + timedelta(days=offset))["level"]] += 1
    total = sum(tally.values())
    assert all(count > 0 for count in tally.values()), f"有档位取不到：{tally}"
    for level, weight in quotes.LEVEL_WEIGHTS.items():
        ratio = tally[level] * 100.0 / total
        assert abs(ratio - weight) <= 2.0, f"{level} 占比 {ratio:.2f}% ≠ 权重 {weight}%"
    assert tally["中平"] == max(tally.values()), f"中平该最多：{tally}"
    assert tally["上上"] == min(tally.values()), f"上上该最少：{tally}"


def test_daily_draw_does_not_collapse_on_a_short_window() -> None:
    """小窗口不许塌缩：40 天里出现的不同签号数要够多（洗牌+取头的退化写法只有 1-2 个）。"""
    start = date(2026, 3, 1)
    numbers = {
        int(divination.daily_draw(start + timedelta(days=offset))["no"])
        for offset in range(40)
    }
    assert len(numbers) >= 15, f"40 天只出现 {len(numbers)} 支签"


def test_splitmix64_gives_a_deterministic_sequence() -> None:
    """自带混合器：同一输入同一输出，且相邻输入的输出互不相关（不做 A/B 交替）。"""
    assert divination.splitmix64(0) == divination.splitmix64(0)
    values = [divination.splitmix64(20261013 + step) for step in range(8)]
    assert len(set(values)) == 8
    bits = {(value >> 63) for value in values}
    assert bits == {0, 1}, "高位不该恒定（否则下标会交替）"


def test_daily_modules_do_not_import_random_for_the_pick() -> None:
    """今日签取号不许借 random（跨 Python 版本会漂）：只有 draw 那条真随机路径能用它。"""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "pet" / "divination.py").read_text(encoding="utf-8")
    daily = source.split("# 今日签：按日期确定性取号", 1)[1]
    assert "random." not in daily.replace("random.Random", ""), "今日签段落里出现了 random 调用"
    assert "splitmix64" in daily


def test_recent_days_are_before_the_day_and_oldest_first() -> None:
    """``recent_days`` 给的是"当天之前的 N 天"（不含当天、旧 → 新）。"""
    day = date(2026, 10, 13)
    days = divination.recent_days(day, 3)
    assert days == [date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12)]
    assert day not in days


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


# --------------------------------------------------------------------------- #
# 服务层：每天一支（第五轮）
# --------------------------------------------------------------------------- #

class _Cfg(dict):
    """假 config：既是 dict（``.get`` 走开关）又带 ``dir``（记录文件落 tmp）。"""

    def __init__(self, directory, **values):
        super().__init__(**values)
        self.dir = directory


def _app(directory, **values):
    class App:
        win = None
        config = _Cfg(directory, **values)

        def system_notify(self, title, message):
            notified.append((title, message))

    notified: list[tuple[str, str]] = []
    return App(), notified


def _history(directory):
    return (directory / "divination-history.jsonl").read_text(encoding="utf-8").strip().splitlines()


def test_service_works_without_a_window(tmp_path) -> None:
    """没有窗口（或窗口不可见）时也要出内容：走桌面通知，不抛异常。"""
    pytest.importorskip("PySide6")
    from pet.divination_service import DivinationService

    spoken: list[str] = []

    class Channel:
        def speak(self, text, log_tag=""):
            spoken.append(text)

    app, notified = _app(tmp_path, divination_speak=True, divination_animation=True)
    app.ensure_audio_channel = lambda: Channel()

    service = DivinationService(app)
    stick = service.draw_now(random.Random(5), day=date(2026, 10, 13))
    assert stick["no"] in range(1, 49)
    # 桌面通知的标题＝签头（"第 5 签 · 中平"），正文＝气泡
    assert notified and notified[0][0] == f"第 {stick['no']} 签 · {stick['level']}"
    assert spoken and spoken[0].startswith(f"第 {stick['no']} 签")
    assert service.config() == {"speak": True, "animation": True}


def test_service_obeys_speak_switch(tmp_path) -> None:
    """关掉语音开关时只出气泡，不碰音频通道。"""
    pytest.importorskip("PySide6")
    from pet.divination_service import DivinationService

    spoken: list[str] = []

    app, notified = _app(tmp_path, divination_speak=False)
    app.ensure_audio_channel = lambda: spoken.append("不该被调用")

    service = DivinationService(app)
    service.draw_now(random.Random(6), day=date(2026, 10, 13))
    assert not spoken
    assert notified


def test_service_second_click_same_day_repeats_the_stick(tmp_path, monkeypatch) -> None:
    """当天再点「抽支签」＝显示同一支（不重新摇签、不重复记账、不重复落卡）。"""
    pytest.importorskip("PySide6")
    from pet import divination_service
    from pet.divination_service import DivinationService

    monkeypatch.setattr(divination_service, "desktop_dir", lambda: tmp_path)
    app, notified = _app(tmp_path, divination_speak=False, divination_animation=False)
    service = DivinationService(app)
    day = date(2026, 10, 13)

    first = service.draw_now(day=day)
    assert len(_history(tmp_path)) == 1, "第一次应该记一笔"

    for _ in range(3):
        again = service.draw_now(day=day)
        assert again["no"] == first["no"], "当天再点必须还是同一支"
        assert again["level"] == first["level"]
    assert len(_history(tmp_path)) == 1, "当天再点不许重复记账"
    # 重复点的那几次气泡/通知里带了"今天已经抽过啦"
    assert any("今天已经抽过啦" in message for _, message in notified[1:])
    cards = list(tmp_path.glob("签卡-*.png"))
    assert len(cards) <= 1, "签卡不该重复落"


def test_service_next_day_gets_a_new_stick_and_a_new_record(tmp_path) -> None:
    """次日（本机自然日翻页）自动换新签，记录一天一行。"""
    pytest.importorskip("PySide6")
    from pet.divination_service import DivinationService

    app, _ = _app(tmp_path, divination_speak=False, divination_animation=False)
    service = DivinationService(app)
    days = [date(2026, 10, 13) + timedelta(days=offset) for offset in range(5)]
    sticks = [service.draw_now(day=day) for day in days]
    assert len(_history(tmp_path)) == 5, "一天应该只有一行记录"
    for day, stick in zip(days, sticks):
        assert f"{day.isoformat()}T" in _history(tmp_path)[days.index(day)]
    assert len({stick["no"] for stick in sticks}) >= 4, "5 天里该换好几支"


def test_service_restart_keeps_todays_stick(tmp_path) -> None:
    """换进程/重启后当天再点仍是同一支，而且不再记账（配额以记录文件为准）。"""
    pytest.importorskip("PySide6")
    from pet.divination_service import DivinationService

    day = date(2026, 10, 13)
    app, _ = _app(tmp_path, divination_speak=False, divination_animation=False)
    first = DivinationService(app).draw_now(day=day)
    assert len(_history(tmp_path)) == 1

    restarted = DivinationService(app)            # 新实例＝新进程的等价物
    again = restarted.draw_now(day=day)
    assert again["no"] == first["no"], "重启后当天应该还是同一支"
    assert again["level"] == first["level"]
    # 记录里只有 ts/no/level，重启后要靠签库按号补回签题/签诗/解曰才念得出来
    for field in ("title", "poem", "plain"):
        assert again.get(field) == first.get(field), f"重启后缺了 {field}"
    assert len(_history(tmp_path)) == 1, "重启当天不许再记一笔"


def test_service_null_history_dir_still_works(tmp_path) -> None:
    """拿不到 config 目录（记录写不了）也不能抛——签照出、通知照发。"""
    pytest.importorskip("PySide6")
    from pet.divination_service import DivinationService

    class App:
        win = None
        config = {"divination_speak": False, "divination_animation": False}

        def system_notify(self, title, message):
            return None

    service = DivinationService(App())
    first = service.draw_now(day=date(2026, 10, 13))
    assert first["no"] in range(1, 49)
    assert service.draw_now(day=date(2026, 10, 13))["no"] == first["no"]


def test_service_history_file_stays_readable_for_settings_page(tmp_path) -> None:
    """记录格式仍是 ts/no/level 三个字段，且已有老记录不受影响（不迁移、不改写）。"""
    pytest.importorskip("PySide6")
    from pet.divination_service import DivinationService, last_record, record_day

    history = tmp_path / "divination-history.jsonl"
    history.write_text(
        '{"ts": "2026-10-12T22:00:00", "no": 20, "level": "下"}\n'
        '{"ts": "2026-10-13T08:00:00", "no": 25, "level": "中平"}\n'
        '{"ts": "2026-10-13T09:00:00", "no": 3, "level": "上"}\n',
        encoding="utf-8",
    )
    record = last_record(tmp_path)
    assert record and int(record["no"]) == 3 and record["level"] == "上"
    assert record_day(record) == date(2026, 10, 13)
    assert record_day({"ts": "坏数据"}) is None

    app, _ = _app(tmp_path, divination_speak=False, divination_animation=False)
    service = DivinationService(app)
    stick = service.draw_now(day=date(2026, 10, 13))
    assert int(stick["no"]) == 3, "当天已经抽过：应直接沿用记录里那一支"
    assert len(_history(tmp_path)) == 3, "旧记录不许被改写或追加"
