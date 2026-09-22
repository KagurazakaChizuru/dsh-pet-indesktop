# -*- coding: utf-8 -*-
"""节日提醒：纯逻辑层测试（零 Qt 依赖，可离线快跑）。

覆盖：节日表冻结快照、农历/节气/浮动节日换算、今日命中与分类开关、
配置清洗、提醒时间计算、文案池与挑选、槽位幂等、启动补提醒。

日历基准日全部是**外部已知事实**（春节/复活节/母亲节等公开历法日期），
不是从实现里回抄的——否则测试只能证明"代码没变"，不能证明"代码是对的"。
"""

from __future__ import annotations

import datetime as dt
import logging

import pytest

from pet import festival as F
from pet import festival_calendar as C
from pet import festival_data as D
from pet.festival_quotes_cn import QUOTES_CN
from pet.festival_quotes_west import QUOTES_WEST
from pet.festival_quotes_west_game import QUOTES_WEST_GAME
from pet.festival_quotes_west_movie import QUOTES_WEST_MOVIE
from pet.festival_quotes_west_song import QUOTES_WEST_SONG

# 西方节日的四段内置库（公有领域 -> 电影 -> 游戏 -> 歌曲），顺序即拼装顺序。
WEST_LIBRARIES = (QUOTES_WEST, QUOTES_WEST_MOVIE, QUOTES_WEST_GAME, QUOTES_WEST_SONG)

# 一个**已核实**当天无任何节日/节气的公历日（2026-01-02 小寒尚未到、
# 农历仍在腊月且非腊八/除夕）。原先误用 2026-03-03，那天其实是元宵节。
PLAIN_DAY = dt.date(2026, 1, 2)


def cfg(**overrides) -> dict:
    """构造一份启用的配置，便于逐项覆盖。"""
    base = {
        "enabled": True,
        "cn": True,
        "solar_terms": True,
        "west": True,
        "mode": F.MODE_TIMES,
        "count": 2,
        "times": frozenset({"09:00"}),
        "show_quote": True,
        "animation": True,
        "birthday": "",
        "custom_quotes_cn": (),
        "custom_quotes_west": (),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------- 节日表
def test_festival_ids_are_frozen():
    """节日 id 集合冻结：新增/删除节日必须显式改本快照，属于需要评审的决策。

    本表是「敏感议题规避白名单」的落地形态——不靠列举违禁词，而是要求
    任何收录变更都必须走一次显式改动，无法悄悄混入。
    """
    assert {f.id for f in D.FESTIVALS} == {
        # 中国节日
        "yuandan", "chunjie", "yuanxiao", "longtaitou", "laodongjie", "duanwu",
        "ertongjie", "qixi", "zhongyuan", "zhongqiu", "chongyang", "guoqingjie",
        "labajie", "chuxi",
        # 24 节气（term_06 由清明节占用）
        "term_00", "term_01", "term_02", "term_03", "term_04", "term_05",
        "qingming",
        "term_07", "term_08", "term_09", "term_10", "term_11", "term_12",
        "term_13", "term_14", "term_15", "term_16", "term_17", "term_18",
        "term_19", "term_20", "term_21", "term_22", "term_23",
        # 西方节日
        "valentine", "april_fools", "easter", "mothers_day", "fathers_day",
        "halloween", "christmas_eve", "christmas",
    }
    assert len(D.FESTIVALS) == 46


def test_solar_terms_cover_all_24():
    assert len(C.SOLAR_TERMS) == 24
    assert set(C.SOLAR_TERMS) == {
        "小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明", "谷雨",
        "立夏", "小满", "芒种", "夏至", "小暑", "大暑", "立秋", "处暑",
        "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
    }


def test_qingming_belongs_to_both_category_switches():
    """清明节既是节气又是传统节日：任一开关开启都应命中。"""
    qingming = D.FESTIVALS_BY_ID["qingming"]
    assert set(qingming.categories) == {D.CATEGORY_CN, D.CATEGORY_SOLAR_TERM}
    assert F.is_festival_enabled(qingming, cfg(cn=True, solar_terms=False))
    assert F.is_festival_enabled(qingming, cfg(cn=False, solar_terms=True))
    assert not F.is_festival_enabled(qingming, cfg(cn=False, solar_terms=False))


# ---------------------------------------------------------------- 历法换算
@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2024, "2024-02-10"),
        (2025, "2025-01-29"),
        (2026, "2026-02-17"),
        (2027, "2027-02-06"),
        (2028, "2028-01-26"),
    ],
)
def test_spring_festival_dates(year, expected):
    assert C.spring_festival(year).isoformat() == expected


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2026, "2026-02-16"), (2027, "2027-02-05")],
)
def test_new_year_eve_is_day_before_spring_festival(year, expected):
    """除夕必须是春节前一天；用「腊月三十」直构会在小月年份抛错。"""
    assert C.new_year_eve(year).isoformat() == expected


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2024, "2024-03-31"),
        (2025, "2025-04-20"),
        (2026, "2026-04-05"),
        (2027, "2027-03-28"),
    ],
)
def test_easter_dates(year, expected):
    assert C.easter(year).isoformat() == expected


def test_nth_weekday_dates_2026():
    assert C.nth_weekday(2026, 5, 6, 2).isoformat() == "2026-05-10"   # 母亲节
    assert C.nth_weekday(2026, 6, 6, 3).isoformat() == "2026-06-21"   # 父亲节
    assert C.nth_weekday(2026, 11, 3, 4).isoformat() == "2026-11-26"  # 通用工具：11 月第 4 个周四


def test_leap_month_is_flagged_and_excluded_from_festivals():
    """闰月必须被识别，且闰月里的同号日不得被当成农历节日。

    2025 年有闰六月；闰六月初一（2025-07-25）绝不能被判成"六月初一"类
    节日。六月初一本身不在表内，故这里用一个一定存在的对照：闰月标记本身。
    """
    leap = C.solar_to_lunar(dt.date(2025, 7, 25))
    assert leap.is_leap and leap.month == 6 and leap.day == 1
    # 闰月里的日期不产生任何农历节日命中
    assert F.festivals_on(dt.date(2025, 7, 25), cfg()) == ()


# ---------------------------------------------------------------- 今日命中
def test_festivals_on_known_days():
    assert [f.name for f in F.festivals_on(dt.date(2026, 2, 17), cfg())] == ["春节"]
    assert [f.name for f in F.festivals_on(dt.date(2026, 2, 16), cfg())] == ["除夕"]
    assert [f.name for f in F.festivals_on(dt.date(2026, 2, 4), cfg())] == ["立春"]
    assert [f.name for f in F.festivals_on(dt.date(2026, 10, 1), cfg())] == ["国庆节"]
    assert [f.name for f in F.festivals_on(dt.date(2026, 5, 10), cfg())] == ["母亲节"]
    assert [f.name for f in F.festivals_on(dt.date(2026, 12, 25), cfg())] == ["圣诞节"]


def test_festivals_on_orders_cn_before_west():
    """2026-04-05 同时是清明节与复活节：中国节日/节气排在西方节日之前。"""
    names = [f.name for f in F.festivals_on(dt.date(2026, 4, 5), cfg())]
    assert names == ["清明节", "复活节"]


def test_festivals_on_respects_category_switches():
    """三个分类开关各自独立生效；清明节因同属两类，需两个开关都关才消失。"""
    # 纯中国节日
    assert F.festivals_on(dt.date(2026, 2, 17), cfg(cn=False)) == ()
    # 纯节气
    assert F.festivals_on(dt.date(2026, 2, 4), cfg(solar_terms=False)) == ()
    # 纯西方节日
    assert F.festivals_on(dt.date(2026, 12, 25), cfg(west=False)) == ()

    day = dt.date(2026, 4, 5)
    assert [f.name for f in F.festivals_on(day, cfg(cn=False))] == ["清明节", "复活节"]
    assert [f.name for f in F.festivals_on(day, cfg(solar_terms=False))] == ["清明节", "复活节"]
    assert [f.name for f in F.festivals_on(day, cfg(cn=False, solar_terms=False))] == ["复活节"]


def test_festivals_on_plain_day_is_empty():
    assert F.festivals_on(PLAIN_DAY, cfg()) == ()


# ---------------------------------------------------------------- 配置清洗
def test_normalize_defaults_when_master_switch_absent():
    """总开关默认关闭：配置里没有该键时不得变成开启。"""
    assert F.normalize_festival_config({})["enabled"] is False


def test_normalize_accepts_string_booleans():
    normalized = F.normalize_festival_config(
        {"festival_reminder_enabled": "开", "festival_reminder_west": "0"}
    )
    assert normalized["enabled"] is True
    assert normalized["west"] is False


def test_normalize_clamps_count_and_falls_back_on_garbage():
    assert F.normalize_festival_config({"festival_reminder_count": 99})["count"] == F.MAX_COUNT
    assert F.normalize_festival_config({"festival_reminder_count": -5})["count"] == F.MIN_COUNT
    assert F.normalize_festival_config({"festival_reminder_count": "abc"})["count"] == F.DEFAULT_COUNT


def test_normalize_mode_falls_back_on_unknown_value():
    assert F.normalize_festival_config({"festival_reminder_mode": "nope"})["mode"] == F.DEFAULT_MODE
    assert F.normalize_festival_config({"festival_reminder_mode": "custom"})["mode"] == "custom"


def test_normalize_never_raises_on_dirty_config():
    """config.json 被手改坏时不得抛异常——本方法跑在启动路径上。"""
    dirty = {
        "festival_reminder_enabled": object(),
        "festival_reminder_count": [1, 2],
        "festival_reminder_times": 12345,
        "festival_custom_quotes_cn": {"a": 1},
    }
    normalized = F.normalize_festival_config(dirty)
    assert normalized["enabled"] is False
    assert normalized["count"] == F.DEFAULT_COUNT


def test_custom_times_parsing_normalizes_and_drops_garbage():
    normalized = F.normalize_festival_config(
        {"festival_reminder_times": "9:00, 25:00，12:30; 坏值 09:00"}
    )
    assert normalized["times"] == frozenset({"09:00", "12:30"})


# ---------------------------------------------------------------- 提醒时间
def test_times_mode_spreads_count_over_window():
    assert F.reminder_times(cfg(count=1)) == ("09:00",)
    assert F.reminder_times(cfg(count=2)) == ("09:00", "21:00")
    assert F.reminder_times(cfg(count=3)) == ("09:00", "15:00", "21:00")
    assert F.reminder_times(cfg(count=4)) == ("09:00", "13:00", "17:00", "21:00")


def test_custom_mode_uses_user_times_sorted():
    got = F.reminder_times(cfg(mode="custom", times=frozenset({"20:00", "07:30"})))
    assert got == ("07:30", "20:00")


def test_custom_mode_with_empty_times_falls_back():
    """选了自定义却没填：回落默认时间，而不是静默永不提醒。"""
    assert F.reminder_times(cfg(mode="custom", times=frozenset())) == (F.DEFAULT_TIMES,)


# ---------------------------------------------------------------- 文案
def test_quote_pool_uses_cn_for_chinese_and_west_for_western():
    cn_pool = F.quote_pool(D.FESTIVALS_BY_ID["chunjie"], cfg())
    west_pool = F.quote_pool(D.FESTIVALS_BY_ID["christmas"], cfg())
    assert cn_pool == QUOTES_CN["chunjie"]
    # 西文库是「公有领域 -> 电影 -> 游戏 -> 歌曲」四段按序拼接；后三段都是
    # 有意不覆盖全部节日，故用 .get 取值（缺键即不追加）。
    expected = (
        tuple(QUOTES_WEST["christmas"])
        + tuple(QUOTES_WEST_MOVIE.get("christmas", ()))
        + tuple(QUOTES_WEST_GAME.get("christmas", ()))
        + tuple(QUOTES_WEST_SONG.get("christmas", ()))
    )
    assert west_pool == expected


def test_pop_culture_libraries_are_present_and_non_empty():
    """受版权库是「可剥离」设计：若被误删，本用例必须立刻红。

    festival.py 用 try/except 导入这三个模块（删文件即降级为空表），
    因此"静默变空"是可能的——这条断言就是防那种静默退化。
    """
    assert QUOTES_WEST_MOVIE, "电影台词库缺失或为空（被误删？）"
    assert QUOTES_WEST_GAME, "游戏台词库缺失或为空（被误删？）"
    assert QUOTES_WEST_SONG, "歌曲歌词库缺失或为空（被误删？）"
    assert sum(len(v) for v in QUOTES_WEST_MOVIE.values()) >= 30
    assert sum(len(v) for v in QUOTES_WEST_GAME.values()) >= 20
    assert sum(len(v) for v in QUOTES_WEST_SONG.values()) >= 8


def test_pop_culture_libraries_key_sets():
    """电影库覆盖全部西方节日；游戏库与歌曲库是**有意**的子集。

    游戏里"广为流传 + 氛围确实契合某节日"的交集远小于电影；歌曲里只有圣诞
    这一类与节日强绑定且名句密度够高。宁可缺项也不硬塞弱相关句子（缺的节日
    仍由公有领域库与电影库覆盖）。这条断言把该设计固定下来：子集是刻意的，
    不是遗漏。
    """
    expected = {f.id for f in D.FESTIVALS if set(f.categories) == {D.CATEGORY_WEST}}
    assert set(QUOTES_WEST_MOVIE) == expected
    assert set(QUOTES_WEST_GAME) <= expected
    assert set(QUOTES_WEST_SONG) <= expected
    # 至少要覆盖多数节日，避免哪天被误删成只剩一两个键还"测试通过"
    assert len(QUOTES_WEST_GAME) >= 6
    assert len(QUOTES_WEST_SONG) >= 2
    # 维护者明确要求：圣诞与平安夜必须有歌曲歌词
    assert {"christmas", "christmas_eve"} <= set(QUOTES_WEST_SONG)
    # 每个已覆盖的键都必须有实质内容
    for library in (QUOTES_WEST_GAME, QUOTES_WEST_SONG):
        for key, quotes in library.items():
            assert len(quotes) >= 1, f"{key} 为空"


def test_custom_quotes_are_appended_not_replacing():
    """自定义文案是追加：不应把内置库挤掉。"""
    pool = F.quote_pool(D.FESTIVALS_BY_ID["chunjie"], cfg(custom_quotes_cn=("我的句子",)))
    assert pool[: len(QUOTES_CN["chunjie"])] == QUOTES_CN["chunjie"]
    assert pool[-1] == "我的句子"


def test_custom_quotes_do_not_leak_across_languages():
    pool_cn = F.quote_pool(D.FESTIVALS_BY_ID["chunjie"], cfg(custom_quotes_west=("English only",)))
    pool_west = F.quote_pool(D.FESTIVALS_BY_ID["christmas"], cfg(custom_quotes_cn=("仅中文",)))
    assert "English only" not in pool_cn
    assert "仅中文" not in pool_west


def test_pick_quote_is_deterministic_and_varies_by_index():
    day = dt.date(2026, 2, 17)
    festival = D.FESTIVALS_BY_ID["chunjie"]
    first = F.pick_quote(festival, day, 0, cfg())
    assert first == F.pick_quote(festival, day, 0, cfg())
    pool = F.quote_pool(festival, cfg())
    assert len({F.pick_quote(festival, day, i, cfg()) for i in range(len(pool))}) == len(pool)


def test_build_festival_text_names_the_day_and_appends_quote():
    text = F.build_festival_text(dt.date(2026, 2, 17), cfg(), 0)
    assert text.startswith("今天是春节。")
    assert text[len("今天是春节。"):] in QUOTES_CN["chunjie"]


def test_build_festival_text_without_quote_switch():
    assert F.build_festival_text(dt.date(2026, 2, 17), cfg(show_quote=False)) == "今天是春节。"


def test_build_festival_text_lists_multiple_festivals():
    text = F.build_festival_text(dt.date(2026, 4, 5), cfg(), 0)
    assert text.startswith("今天是清明节、复活节。")


def test_build_festival_text_empty_when_nothing_matches():
    assert F.build_festival_text(PLAIN_DAY, cfg()) == ""
    # 分类全关时同样不提醒
    assert F.build_festival_text(dt.date(2026, 2, 17), cfg(cn=False, solar_terms=False, west=False)) == ""


def test_no_festival_text_is_available_for_manual_entry():
    assert F.NO_FESTIVAL_TEXT


# ---------------------------------------------------------------- 槽位幂等
def test_reminder_slot_only_at_configured_time_and_on_festival_day():
    at_nine = dt.datetime(2026, 2, 17, 9, 0, 30)
    assert F.reminder_slot(at_nine, cfg(count=2)) == "2026-02-17T09:00"
    # 非提醒时间
    assert F.reminder_slot(dt.datetime(2026, 2, 17, 10, 0), cfg(count=2)) == ""
    # 提醒时间但当天无节日
    assert F.reminder_slot(dt.datetime(2026, 1, 2, 9, 0), cfg(count=2)) == ""


def test_reminder_slot_is_stable_within_the_same_minute():
    """同一分钟内的多次 tick 必须得到同一槽位，才能靠盖戳去重。"""
    a = F.reminder_slot(dt.datetime(2026, 2, 17, 9, 0, 1), cfg(count=2))
    b = F.reminder_slot(dt.datetime(2026, 2, 17, 9, 0, 59), cfg(count=2))
    assert a == b == "2026-02-17T09:00"


def test_reminder_slot_does_not_use_master_switch():
    """槽位只回答"此刻该不该提醒"，总开关由服务层把关（手动触发要无视开关）。"""
    assert F.reminder_slot(dt.datetime(2026, 2, 17, 9, 0), cfg(enabled=False)) != ""


def test_startup_slot_only_after_first_reminder_time():
    assert F.startup_slot(dt.datetime(2026, 2, 17, 8, 0), cfg(count=2)) == ""
    assert F.startup_slot(dt.datetime(2026, 2, 17, 12, 0), cfg(count=2)) == "2026-02-17#startup"
    # 当天无节日则不补
    assert F.startup_slot(dt.datetime(2026, 1, 2, 12, 0), cfg(count=2)) == ""


def test_startup_slot_differs_from_scheduled_slot():
    """补提醒不能压掉当天晚些时候的正常提醒。"""
    day = dt.date(2026, 2, 17)
    assert F.startup_slot(dt.datetime(2026, 2, 17, 12, 0), cfg(count=2)) != (
        f"{day.isoformat()}T21:00"
    )


# ---------------------------------------------------------------- 文案库完整性
def test_every_festival_has_a_quote_pool():
    """每个节日都必须有非空文案池，否则提醒会变成光秃秃一行字。

    直接断言真实取词入口的返回值（而不是逐个查内置表），这样新增/剥离
    任一文案库都会被覆盖到。
    """
    missing = [f.id for f in D.FESTIVALS if not F.quote_pool(f, cfg())]
    assert missing == []


def test_quote_libraries_have_no_orphan_keys():
    needed_cn = {
        f.id for f in D.FESTIVALS
        if set(f.categories) & {D.CATEGORY_CN, D.CATEGORY_SOLAR_TERM}
    }
    needed_west = {f.id for f in D.FESTIVALS if set(f.categories) == {D.CATEGORY_WEST}}
    assert set(QUOTES_CN) == needed_cn
    assert set(QUOTES_WEST) == needed_west


@pytest.mark.parametrize("library", [QUOTES_CN, *WEST_LIBRARIES])
def test_quote_entries_are_clean(library):
    for key, quotes in library.items():
        assert quotes, f"{key} 文案池为空"
        assert len(set(quotes)) == len(quotes), f"{key} 存在重复文案"
        for quote in quotes:
            assert isinstance(quote, str)
            assert quote.strip() == quote and quote, f"{key} 文案含首尾空白"
            assert "\n" not in quote, f"{key} 文案含换行"


def _actual_sources(path, marker: str) -> dict[str, int]:
    """从受版权库的**行内出处注释**统计「作品名 -> 条数」。

    出处写成行内注释正是为了让这份统计可被机器核对（而不是靠人誊抄到声明里）。
    """
    import collections
    import re as _re

    src = path.read_text(encoding="utf-8")
    src = src[src.index(marker):]
    names = (
        _re.sub(r"\s*\(\d{4}\)$", "", m).strip()
        for m in _re.findall(r"#\s*(.+?)\s*\(\d{4}\)", src)
    )
    return dict(collections.Counter(names))


def _declared_sources(notices: str, section: str) -> dict[str, int]:
    import re as _re

    part = notices[notices.index(section):]
    nxt = part.find("###", 10)
    if nxt != -1:
        part = part[:nxt]
    return {
        _re.sub(r"\s*\(\d{4}\)$", "", m.group(1)).strip(): int(m.group(2))
        for m in _re.finditer(r"^\|\s*(.+?)\s*\|\s*(\d+)\s*\|$", part, _re.M)
    }


@pytest.mark.parametrize(
    ("path", "marker", "section"),
    [
        ("festival_quotes_west_movie.py", "QUOTES_WEST_MOVIE", "### 5.1"),
        ("festival_quotes_west_game.py", "QUOTES_WEST_GAME", "### 5.2"),
    ],
)
def test_third_party_notices_match_quote_libraries(path, marker, section):
    """THIRD_PARTY_NOTICES.md 的逐作品条数必须与受版权库内容逐项一致。

    声明文件里的数字错一处就是法律文件失实，而手工誊抄必然漂移——本功能开发
    过程中就真的写错过两处（Forrest Gump 2/3、Home Alone 3/2），且因一增一减
    总数恰好不变，只看总数根本发现不了。故用机器核对逐项对齐。
    """
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[1]
    notices = (repo_root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    actual = _actual_sources(repo_root / "pet" / path, marker)
    declared = _declared_sources(notices, section)
    assert declared == actual, (
        "第三方声明与文案库不一致："
        f"\n  声明 vs 实际（不一致项）: "
        f"{ {k: (declared.get(k), actual.get(k)) for k in set(declared) | set(actual) if declared.get(k) != actual.get(k)} }"
    )


def test_third_party_notices_list_every_song():
    """歌曲库每一首都必须在第三方声明里被列出。

    歌曲声明的表结构（歌名/词曲作者/年份/条数）比电影/游戏多两列，不适用上面
    的逐项条数比对，故单独校验"每首都登记了"——漏登记一首就是版权声明缺项。
    """
    from pathlib import Path as _Path
    import re as _re

    notices = (_Path(__file__).resolve().parents[1] / "THIRD_PARTY_NOTICES.md").read_text(
        encoding="utf-8"
    )
    db = _Path(__file__).resolve().parents[1] / "pet" / "festival_quotes_west_song.py"
    # 只取「引号字符串后面紧跟的注释」——否则文件头 # -*- coding -*- 与
    # "# 平安夜（12/24）：…" 这类分组注释也会被当成歌曲名。
    titles = {
        _re.sub(r"\s*\(\d{4}\).*$", "", m).strip()
        for m in _re.findall(r'^\s*"[^"]*",\s*#\s*(.+?)$', db.read_text(encoding="utf-8"), _re.M)
    }
    titles = {t for t in titles if t}
    assert titles, "歌曲库出处注释解析失败"
    missing = [t for t in sorted(titles) if t not in notices]
    assert missing == [], f"第三方声明漏登记以下歌曲：{missing}"


# ---------------------------------------------------------------- 语音播报与让位
def _real_asset_stems() -> tuple[str, ...]:
    """当前角色**素材目录里真实存在**的动画名（本仓库 106 段）。

    **不要**拿 `festival_animations.all_animation_names()` 当假窗动作池：那是被测
    实现自己的映射表，会让「生日播端蛋糕送礼物」这类用例变成自我实现的假绿
    （表里写什么，假窗就"拥有"什么，用例永远不会红）。
    """
    from pet import catalog

    video_dir = catalog.character_video_dir(catalog.DEFAULT_CHARACTER)
    if not video_dir.is_dir():
        return ()
    return tuple(
        sorted(
            {p.stem for p in video_dir.rglob("*.webm")}
            | {p.stem for p in video_dir.rglob("*.gif")}
        )
    )


#: 仓库素材里真实存在的动画名；空表示素材目录缺失（相关用例会显式 skip）
REAL_STEMS = _real_asset_stems()
#: 「端蛋糕送礼物」只随已安装版发布，仓库素材里没有 —— 用它做 skip 条件而不是白名单
HAS_CAKE_CLIP = "端蛋糕送礼物" in REAL_STEMS


class _Win:
    """假桌宠窗口：记录气泡与动画请求，并模拟"请求即上屏"。"""

    def __init__(self, acts=None) -> None:
        self.bubbles: list[str] = []
        # 动作池默认取**真实素材**（见 _real_asset_stems）；用例可显式传入构造特定池
        self.acts: list[str] = list(REAL_STEMS if acts is None else acts)
        self.anim_requests: list[str] = []
        self.switch_requests: list[str] = []
        # 真实窗口的公有属性，服务层用它确认"动画是否真的上了屏"
        self.anim = "待机呼吸休闲"

    def show_bubble(self, text: str, duration_ms: int | None = None) -> None:
        self.bubbles.append(text)

    def isVisible(self) -> bool:  # noqa: N802 - 对齐 Qt API
        return True

    def request_link_anim(self, name: str) -> None:
        self.anim_requests.append(name)
        self.anim = name  # 模拟"当前没有一次性动作在播 → 立即上屏"

    def switch_clip(self, name: str, link_request: bool = False) -> bool:
        self.switch_requests.append(name)
        self.anim = name
        return True


class _WinWithoutRequestLink(_Win):
    """只提供 switch_clip 的假窗：覆盖 request_link_anim 缺失时的退化路径。"""

    request_link_anim = None


class _WinQueuedOnly(_Win):
    """请求只排队、不上屏：模拟窗口正播一次性动作时 request_link_anim 的语义。"""

    def request_link_anim(self, name: str) -> None:
        self.anim_requests.append(name)  # 记录但不改 anim → 服务层不应记账


class _WinInvisible(_Win):
    """不可见窗口：模拟桌宠被隐藏/设置窗打开时的抑制场景。"""

    def isVisible(self) -> bool:  # noqa: N802 - 对齐 Qt API
        return False


class _Channel:
    """假音频通道（即语音报时服务）：只记录被要求播报的文本。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.spoken: list[str] = []
        self.fail = fail

    def speak(self, text: str, log_tag: str = "") -> bool:
        if self.fail:
            raise RuntimeError("通道故障")
        self.spoken.append(text)
        return True


class _App:
    def __init__(self, config, channel) -> None:
        self.config = config
        self.win = _Win()
        self._channel = channel

    def ensure_audio_channel(self):
        return self._channel


def _service(config, channel=None):
    from PySide6.QtWidgets import QApplication

    from pet.festival_service import FestivalReminderService

    QApplication.instance() or QApplication([])
    app = _App(config, channel if channel is not None else _Channel())
    return FestivalReminderService(app), app


def _cfg_with(tmp_path, **overrides):
    from pet.config import Config

    cfg = Config(base=tmp_path)
    cfg.set("festival_reminder_enabled", True)
    for key, value in overrides.items():
        cfg.set(key, value)
    return cfg


def test_should_speak_at_true_only_when_speak_on_and_festival_due(tmp_path):
    service, _app = _service(_cfg_with(tmp_path, festival_reminder_speak=True))
    service.apply_config()

    # 报时槽位带调度后缀，判定须只看前 16 位
    assert service.should_speak_at("2026-02-17T09:00#hourly") is True
    # 非提醒时间
    assert service.should_speak_at("2026-02-17T10:00#hourly") is False
    # 提醒时间但当天无节日
    assert service.should_speak_at("2026-01-02T09:00#hourly") is False
    # 脏输入不得抛异常
    assert service.should_speak_at("垃圾数据") is False


def test_should_speak_at_false_when_speak_disabled(tmp_path):
    """节日语音没开时不能让报时让位——否则报时会被静默吞掉。"""
    service, _app = _service(_cfg_with(tmp_path, festival_reminder_speak=False))
    service.apply_config()

    assert service.should_speak_at("2026-02-17T09:00#hourly") is False


def test_service_speaks_festival_text_when_enabled(tmp_path):
    channel = _Channel()
    service, app = _service(_cfg_with(tmp_path, festival_reminder_speak=True), channel)
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))

    assert len(channel.spoken) == 1
    assert channel.spoken[0].startswith("今天是春节。")
    # 气泡与语音内容一致（都走同一次组装的文案）
    assert app.win.bubbles == channel.spoken


def test_service_stays_silent_when_speak_disabled(tmp_path):
    channel = _Channel()
    service, app = _service(_cfg_with(tmp_path, festival_reminder_speak=False), channel)
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))

    assert channel.spoken == []
    assert len(app.win.bubbles) == 1, "不出声也必须有气泡"


def test_startup_catch_up_suppresses_same_minute_scheduled_slot(tmp_path):
    """P1：节日当天恰在提醒分钟内启动时，同一分钟不得播报两次。

    回归背景：``_catch_up`` 只用独立槽位 ``{day}#startup`` 盖戳，而 ``_on_tick``
    认的是 ``{day}T{HH:MM}``，两者互不压制；09:00:05 启动会先补报一次，
    紧接着同一分钟的 tick 再播一次（两次气泡 + 两段 TTS），与 ``reminder_slot``
    承诺的"同一天同一提醒时间只播报一次"矛盾。
    """
    channel = _Channel()
    service, app = _service(_cfg_with(tmp_path, festival_reminder_speak=True), channel)
    service.apply_config()

    service._catch_up(dt.datetime(2026, 2, 17, 9, 0, 5))
    assert len(app.win.bubbles) == 1, "启动补提醒应播报一次"
    assert len(channel.spoken) == 1

    # 同一分钟内的 tick（30s 间隔的那一拍）不得再播
    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 35))
    assert len(app.win.bubbles) == 1, "同一分钟不得重复播报"
    assert len(channel.spoken) == 1, "同一分钟不得重复出声"

    # 当天晚些时候的正式提醒点照常播报：补提醒只压当前这一分钟
    service._on_tick(dt.datetime(2026, 2, 17, 21, 0, 30))
    assert len(app.win.bubbles) == 2
    assert len(channel.spoken) == 2


def test_roll_day_resets_fired_slots_across_days(tmp_path):
    """跨天复位：新一天的同一提醒分钟必须能再播，且次数索引从 0 重新起算。

    回归背景：``_roll_day`` 是"提醒次数 → 文案索引"与"当天去重"的共同前提，
    此前零覆盖；它一旦失效，第二天的提醒会被前一天的槽位永久压掉。
    """
    config = _cfg_with(tmp_path, festival_reminder_speak=True)
    channel = _Channel()
    service, app = _service(config, channel)
    service.apply_config()

    # 2026-02-16 除夕 09:00
    service._on_tick(dt.datetime(2026, 2, 16, 9, 0, 5))
    assert len(app.win.bubbles) == 1
    assert app.win.bubbles[0].startswith("今天是除夕。")
    # 同一天同一槽位再 tick 不重复
    service._on_tick(dt.datetime(2026, 2, 16, 9, 0, 40))
    assert len(app.win.bubbles) == 1

    # 跨天（2026-02-17 春节）：同是 09:00 的槽位，必须重新可播
    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))
    assert len(app.win.bubbles) == 2
    assert app.win.bubbles[1].startswith("今天是春节。")
    # 跨天后"当天第几次提醒"从 0 重算（文案与当天的第一次提醒一致）
    expected = F.build_festival_text(
        dt.date(2026, 2, 17), F.normalize_festival_config(config), 0
    )
    assert app.win.bubbles[1] == expected


def test_remind_now_speaks_and_bubbles(tmp_path):
    channel = _Channel()
    service, app = _service(_cfg_with(tmp_path, festival_reminder_speak=True), channel)
    service.apply_config()

    service.remind_now()

    assert app.win.bubbles and channel.spoken == app.win.bubbles


def test_speak_failure_degrades_to_bubble_only(tmp_path):
    """音频通道故障不得影响提醒本身——有气泡就算成功。"""
    service, app = _service(_cfg_with(tmp_path, festival_reminder_speak=True), _Channel(fail=True))
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))

    assert len(app.win.bubbles) == 1


def test_missing_audio_channel_degrades_to_bubble_only(tmp_path):
    service, app = _service(_cfg_with(tmp_path, festival_reminder_speak=True), None)
    app._channel = None
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))

    assert len(app.win.bubbles) == 1


# ---------------------------------------------------------------- 设置页「立即试听」
def _page(tmp_path):
    from PySide6.QtWidgets import QApplication

    from pet.config import Config
    from pet.festival_settings import FestivalSettingsPage

    QApplication.instance() or QApplication([])
    return FestivalSettingsPage(Config(base=tmp_path))


def test_settings_page_has_preview_row_with_button(tmp_path):
    from pet.modern_settings_dialog import SettingRow

    page = _page(tmp_path)
    rows = {r.objectName() for r in page.findChildren(SettingRow)}
    assert "settingRow_festival_preview" in rows
    assert page.preview_btn.text() == "立即试听"


def test_preview_click_emits_signal_and_writes_config(tmp_path):
    page = _page(tmp_path)
    seen: list[int] = []
    page.preview_requested.connect(lambda: seen.append(1))
    page.speak_check.setChecked(True)

    page.preview_btn.click()

    assert seen == [1], "试听应发出信号（供宿主/测试观察）"
    assert page.config.get("festival_reminder_speak") is True, "试听前必须先落盘当前控件值"


def test_preview_click_is_safe_without_any_host(tmp_path):
    """没有宿主回调（独立构造/宿主未接线）时点击不得抛异常。"""
    page = _page(tmp_path)
    assert page._resolve_preview_callback() is None
    page.preview_btn.click()  # 不得抛


def test_preview_click_reaches_host_callback_end_to_end(tmp_path):
    """按钮 -> 向上解析宿主回调 -> 真实服务 remind_now -> 气泡，整条链路打通。"""
    from PySide6.QtWidgets import QWidget

    page = _page(tmp_path)
    channel = _Channel()
    # 必须改**控件**而不是 config：点击会先 apply_to_config()，用控件值覆盖 config
    # （这正是"先落盘再触发"的语义，直接改 config 会被冲掉）。
    page.enabled_check.setChecked(True)
    page.speak_check.setChecked(True)
    service, app = _service(page.config, channel)
    service.apply_config()

    host = QWidget()
    host.on_festival_now = service.remind_now  # 模拟 AppShell 给窗口赋的入口
    page.setParent(host)

    page.preview_btn.click()

    assert app.win.bubbles, "试听必须产生气泡"
    assert channel.spoken == app.win.bubbles, "开启语音播报时试听应同时出声"


def test_preview_resolution_survives_an_extra_parent_layer(tmp_path):
    """向上解析必须容忍多一层包装（页面被 reparent 到中间容器时不失效）。"""
    from PySide6.QtWidgets import QWidget

    page = _page(tmp_path)
    called: list[int] = []
    host = QWidget()
    host.on_festival_now = lambda: called.append(1)
    middle = QWidget(host)      # 中间多一层
    page.setParent(middle)

    page.preview_btn.click()

    assert called == [1]


def test_appshell_trigger_festival_now_reaches_service(tmp_path):
    """试听链路的末端：窗口属性 on_festival_now 指向 AppShell.trigger_festival_now。

    该入口必须**无视总开关**（试听语义）并懒创建服务，与语音报时的
    trigger_voice_chime_now 同约定。
    """
    from PySide6.QtWidgets import QApplication

    from pet.app import AppShell
    from pet.config import Config

    QApplication.instance() or QApplication([])
    cfg = Config(base=tmp_path)
    cfg.set("festival_reminder_enabled", False)   # 总开关关闭
    cfg.set("festival_reminder_speak", False)
    shell = AppShell(QApplication.instance(), cfg, enable_chat=False)
    assert shell.festival_service is None

    shell.trigger_festival_now()                  # 不得抛

    assert shell.festival_service is not None, "试听应懒创建服务（无视总开关）"
    shell._on_about_to_quit()


def test_preview_rows_are_collected_into_domain_sections(tmp_path):
    """试听行必须被域收集机制收进某个 SettingsSection（否则打包版里按钮会不见）。

    历史事故：设置页里**没包在 SettingRow 内**的控件（含页面根布局里的按钮）不会
    被 `_rebuild_domain_navigation` 收集，页面被移出 pages 后按钮直接消失——当时
    的表现是"打包版看不到立即试听"。这里用**真实对话框**断言试听行确实落进了域卡片，
    同时覆盖语音报时与节日提醒两个按钮（后者是本次新增）。
    """
    from PySide6.QtWidgets import QApplication

    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog
    from pet.settings_widgets import SettingsSection

    QApplication.instance() or QApplication([])
    dialog = ModernSettingsDialog(Config(base=tmp_path), include_ai=False)
    try:
        sections = dialog.findChildren(SettingsSection)
        for target in ("settingRow_festival_preview", "settingRow_voice_chime_preview"):
            holders = [
                s for s in sections if any(r.objectName() == target for r in s.rows)
            ]
            assert holders, f"{target} 未被任何域卡片收集（历史事故：打包版不可见）"
    finally:
        dialog.close()


# ---------------------------------------------------------------- 节日 × 动画绑定
def test_animation_table_keys_are_real_festival_ids():
    """映射表的键必须是真实节日 id——写中文名或打错字立即红。"""
    from pet import festival_animations as A

    # 生日（shengri）是**动态节日**：不在静态表 FESTIVALS 里，单独放行
    ids = set(D.FESTIVALS_BY_ID) | {D.BIRTHDAY_ID}
    assert set(A.FESTIVAL_ANIMATIONS) <= ids
    assert set(A.FESTIVAL_ANIMATION_KEYWORDS) <= ids
    assert set(A.SOLAR_TERM_SEASONS) <= ids
    # 两张并行表必须**同键**：只往一张表加节日，会让该节日"精确级命中但关键词级失效"
    assert set(A.FESTIVAL_ANIMATIONS) == set(A.FESTIVAL_ANIMATION_KEYWORDS)
    # 季节表必须恰好覆盖 24 个节气 id（多写 term_06 这类不存在的键也要红）
    assert set(A.SOLAR_TERM_SEASONS) == {
        f.id for f in D.FESTIVALS if "solar_term" in f.categories
    }


def test_mapped_animations_use_real_asset_names():
    """表里写的动画名必须真的存在于素材目录里——`catalog.ANIM_FILES` 当初就是这样
    悄悄脱节的（5 个名字对不上任何真实文件）。这里加一道机器化护栏。

    已知缺口随素材是否随仓库发布而变：`端蛋糕送礼物` 缺失时允许它作为唯一例外，
    素材补齐后这条断言自动收紧到"一个都不许缺"。
    """
    from pet import catalog
    from pet import festival_animations as A

    video_dir = catalog.character_video_dir(catalog.DEFAULT_CHARACTER)
    if not video_dir.is_dir():
        pytest.skip("内置素材目录缺失，跳过素材名核对")
    stems = {p.stem for p in video_dir.rglob("*.webm")}
    if not stems:
        pytest.skip("内置素材为空，跳过素材名核对")

    expected_gap = set() if HAS_CAKE_CLIP else {"端蛋糕送礼物"}
    assert set(A.all_animation_names()) - stems == expected_gap


def test_zhongqiu_prefers_mooncake_animation():
    """本次需求的原型例子：中秋 → 中秋赏月吃月饼。"""
    from pet import festival_animations as A

    assert A.FESTIVAL_ANIMATIONS["zhongqiu"][0] == "中秋赏月吃月饼"
    assert A.pick_animation("zhongqiu", A.all_animation_names()) == "中秋赏月吃月饼"


def test_pick_animation_degrades_keyword_then_season():
    from pet import festival_animations as A

    # ① 精确名不在当前角色动作池 → ② 关键词兜底
    assert A.pick_animation("zhongqiu", ("随便一段", "吃月饼啦")) == "吃月饼啦"
    # ③ 节气无专属素材（雨水属春）→ 季节兜底；多个候选时按季节表优先级取
    assert A.pick_animation("term_03", ("摇扇纳凉", "放风筝")) == "放风筝"
    # 三级都没有 → None，绝不抛异常
    assert A.pick_animation("term_03", ("鲸鱼吐泡泡特效",)) is None
    assert A.pick_animation("不存在的节日", ("放烟花",)) is None
    assert A.pick_animation("zhongqiu", ()) is None


def test_every_solar_term_has_something_to_play():
    """24 节气都必须能播出一段（专属素材或季节兜底）——按**真实素材池**断言。

    用真实素材而不是映射表自身的并集：后者只能证明"表内部自洽"，证明不了
    "仓库素材真的能覆盖 24 个节气"。
    """
    from pet import festival_animations as A

    if not REAL_STEMS:
        pytest.skip("素材目录缺失，无法断言真实素材覆盖")
    terms = [f.id for f in D.FESTIVALS if "solar_term" in f.categories]
    assert len(terms) == 24
    for term_id in terms:
        assert A.pick_animation(term_id, REAL_STEMS), term_id


def test_known_gaps_are_deliberate_and_still_empty():
    """素材缺口是**刻意保留**的：补素材后必须从 KNOWN_GAPS 移除，本用例会随之变红。"""
    from pet import festival_animations as A

    assert A.KNOWN_GAPS == frozenset({"easter", "mothers_day", "fathers_day"})
    pool = A.all_animation_names()
    for festival_id in sorted(A.KNOWN_GAPS):
        assert A.pick_animation(festival_id, pool) is None, festival_id


def test_tick_plays_matching_animation_once_per_day(tmp_path):
    """到点提醒播对应动画；当天第二次提醒不再播（避免一天把同一段播 6 遍）。"""
    from pet.festival_calendar import lunar_to_solar

    mid_autumn = lunar_to_solar(2026, 8, 15)
    service, app = _service(_cfg_with(tmp_path))
    service.apply_config()
    assert [f.id for f in F.festivals_on(mid_autumn, service._cfg)] == ["zhongqiu"], (
        "基准日撞上了其它节日/节气，需换基准日"
    )

    service._on_tick(dt.datetime(mid_autumn.year, mid_autumn.month, mid_autumn.day, 9, 0, 5))
    assert app.win.anim_requests == ["中秋赏月吃月饼"]

    # 第二枪必须打在**真实提醒点**上：默认槽位是 09:00 / 21:00，原先用 15:00 时
    # `_on_tick` 在槽位判定处就返回，断言变成同义反复（删掉守卫照样绿）。
    second = dt.datetime(mid_autumn.year, mid_autumn.month, mid_autumn.day, 21, 0, 5)
    assert F.reminder_slot(second, service._cfg), "第二枪必须是真实提醒点，否则断言是空的"
    bubbles_before = len(app.win.bubbles)
    service._on_tick(second)
    assert len(app.win.bubbles) == bubbles_before + 1, "第二个提醒点应照常出气泡"
    assert app.win.anim_requests == ["中秋赏月吃月饼"], "动画当天只播第一次"


def test_remind_now_always_plays_animation(tmp_path):
    """手动入口每次都播（试听语义），不受"当天已播过"限制。"""
    service, app = _service(_cfg_with(tmp_path))
    service.apply_config()
    when = dt.datetime(2026, 2, 17, 9, 0, 5)  # 春节（既有用例已核实的基准日）

    service._on_tick(when)
    assert len(app.win.anim_requests) == 1

    service.remind_now(when)
    assert len(app.win.anim_requests) == 2


def test_animation_toggle_off_plays_nothing(tmp_path):
    service, app = _service(_cfg_with(tmp_path, festival_reminder_animation=False))
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))

    assert app.win.anim_requests == []
    assert app.win.bubbles, "关掉动画不得影响提醒本身"


def test_missing_material_is_silent_noop(tmp_path, caplog):
    """换角色/外部角色包没有这段动画时静默跳过（不打 warning、气泡照常）。

    两种池都要覆盖：空池（`pick_animation` 提前返回）与**非空但无任何匹配名**
    （真正走完三级降级后返回 None）。"不打 warning"由 caplog 实证，不只是 docstring。
    """
    for acts in ([], ["鲸鱼吐泡泡特效"]):
        service, app = _service(_cfg_with(tmp_path))
        app.win.acts = list(acts)
        service.apply_config()

        with caplog.at_level(logging.WARNING):
            service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))

        assert app.win.anim_requests == [], f"acts={acts}"
        assert app.win.bubbles, f"动画跳过不得影响提醒本身（acts={acts}）"
        warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert not warnings, f"缺素材不该刷 warning（acts={acts}）：{warnings}"
        caplog.clear()


def test_no_festival_day_plays_nothing(tmp_path):
    """当天无节日时既不提醒也不播动画（自动路径静默）。"""
    service, app = _service(_cfg_with(tmp_path))
    service.apply_config()

    service._on_tick(dt.datetime(PLAIN_DAY.year, PLAIN_DAY.month, PLAIN_DAY.day, 9, 0, 5))

    assert app.win.bubbles == []
    assert app.win.anim_requests == []


def test_falls_back_to_switch_clip_without_request_link_anim(tmp_path):
    """没有 request_link_anim 时退化到 switch_clip(name, link_request=True)。"""
    service, app = _service(_cfg_with(tmp_path))
    app.win = _WinWithoutRequestLink()
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))

    assert app.win.switch_requests == ["收红包"]
    assert app.win.anim_requests == []


# ---------------------------------------------------------------- 用户生日（动态节日）
def test_clean_birthday_normalizes_and_rejects_impossible_dates():
    assert F.clean_birthday("") == ""
    assert F.clean_birthday(None) == ""
    assert F.clean_birthday("10-24") == "10-24"
    assert F.clean_birthday("10/24") == "10-24"
    assert F.clean_birthday("10月24日") == "10-24"
    assert F.clean_birthday("1.5") == "01-05"
    # 不存在的日期一律落空：宁可不说，也不要每年在错的日子跳出来
    assert F.clean_birthday("02-30") == ""
    assert F.clean_birthday("13-01") == ""
    assert F.clean_birthday("随便写") == ""
    # 02-29 合法（闰年生日，平年自动不命中）
    assert F.clean_birthday("02-29") == "02-29"


def test_birthday_fires_only_on_the_configured_day():
    only_birthday = cfg(cn=False, solar_terms=False, west=False, birthday="10-24")
    day = dt.date(2026, 10, 24)
    assert [f.name for f in F.festivals_on(day, only_birthday)] == ["你的生日"]
    assert F.festivals_on(dt.date(2026, 10, 23), only_birthday) == ()
    # 没设置生日时不得凭空命中（PLAIN_DAY 是已核实的无节日基准日）
    assert F.festivals_on(PLAIN_DAY, cfg()) == ()


def test_birthday_ignores_category_switches():
    """生日是个人日期：三个类别开关全关也要提醒（普通节日被关就静默）。"""
    off = cfg(cn=False, solar_terms=False, west=False, birthday="10-24")
    assert [f.name for f in F.festivals_on(dt.date(2026, 10, 24), off)] == ["你的生日"]
    assert F.festivals_on(dt.date(2026, 2, 17), off) == (), "春节应被 cn 开关关掉"


def test_birthday_sorts_before_a_festival_on_the_same_day():
    """生日与节日撞同一天时先讲生日（文案取 hits[0]，动画也跟它走）。

    基准日特意选**中秋节**：只按名字排序时「中」(U+4E2D) < 「你」(U+4F60)，中秋节会
    排在前面 —— 所以这条用例真正检验"生日优先"这个排序键。（原先用春节的「春」
    U+6625 > 「你」，删掉排序键照样通过，属不承重。）
    """
    from pet.festival_calendar import lunar_to_solar

    mid_autumn = lunar_to_solar(2026, 8, 15)
    same_day = cfg(birthday=f"{mid_autumn.month:02d}-{mid_autumn.day:02d}")
    assert [f.name for f in F.festivals_on(mid_autumn, same_day)] == ["你的生日", "中秋节"]
    assert F.build_festival_text(mid_autumn, same_day) == (
        "今日是你的生日，祝你生日快乐，健健康康。今天也是中秋节。"
    )


def test_birthday_text_is_the_dedicated_blessing():
    """生日文案用专属祝福主句，而不是"今天是X。"模板 + 诗词引文。"""
    birthday = dt.date(2027, 3, 15)
    assert F.build_festival_text(birthday, cfg(birthday="03-15")) == (
        "今日是你的生日，祝你生日快乐，健健康康。"
    )
    # 用户自定义中文文案仍按既有规则追加其后
    with_custom = F.build_festival_text(
        birthday, cfg(birthday="03-15", custom_quotes_cn=("愿你年年有今日。",))
    )
    assert with_custom == "今日是你的生日，祝你生日快乐，健健康康。愿你年年有今日。"
    # 关掉「附带文案」时只剩祝福主句
    assert F.build_festival_text(
        birthday,
        cfg(birthday="03-15", show_quote=False, custom_quotes_cn=("愿你年年有今日。",)),
    ) == "今日是你的生日，祝你生日快乐，健健康康。"


def test_birthday_prefers_the_cake_animation_over_keyword_fallback(tmp_path):
    """映射优先级：池里同时有「端蛋糕送礼物」与「拆礼物」时选前者。

    这是**映射优先级**的单元测试（池由用例显式构造）；"素材是否真的随包发布"由
    下面两条按真实素材池断言、并用 skip 标出缺口的用例负责。
    """
    service, app = _service(_cfg_with(tmp_path, festival_birthday="10-24"))
    app.win = _Win(acts=["拆礼物", "端蛋糕送礼物"])
    service.apply_config()

    service._on_tick(dt.datetime(2026, 10, 24, 9, 0, 5))

    assert app.win.anim_requests == ["端蛋糕送礼物"]


@pytest.mark.skipif(not HAS_CAKE_CLIP, reason="「端蛋糕送礼物」只随已安装版发布，仓库素材里没有")
def test_birthday_plays_the_cake_animation_with_the_shipped_pack(tmp_path):
    """素材齐全时，生日当天在**真实素材池**里确实选中「端蛋糕送礼物」。"""
    service, app = _service(_cfg_with(tmp_path, festival_birthday="10-24"))
    service.apply_config()

    service._on_tick(dt.datetime(2026, 10, 24, 9, 0, 5))

    assert app.win.anim_requests == ["端蛋糕送礼物"]


@pytest.mark.skipif(HAS_CAKE_CLIP, reason="素材已随仓库发布，该兜底分支只在缺素材时出现")
def test_birthday_falls_back_to_keyword_match_without_the_cake_clip(tmp_path):
    """仓库素材缺「端蛋糕送礼物」时的**真实行为**：关键词级兜底到「拆礼物」。

    （不是"静默跳过"——相关注释与 PR 报告已按实测口径改写。）
    """
    if not REAL_STEMS:
        pytest.skip("素材目录缺失，无法断言真实兜底行为")
    service, app = _service(_cfg_with(tmp_path, festival_birthday="10-24"))
    service.apply_config()

    service._on_tick(dt.datetime(2026, 10, 24, 9, 0, 5))

    assert app.win.anim_requests == ["拆礼物"]


def test_clean_birthday_rejects_year_prefixed_and_multi_segment_inputs():
    """带年份/多段数字的输入一律落空，**绝不**解析成另一个日子。

    回归：曾经用不锚定的 `search` 把 `2005-03-15` 解析成 `05-03`，于是在**错误的
    日子**每年提醒（972 个 YYYY-MM-DD 输入里 144 个错日 / 828 个落空 / 0 个正确）。
    """
    for raw in ("2005-03-15", "2012-10-24", "2001-10-24", "1201-05-06", "1-2-3", "2026-10-24"):
        assert F.clean_birthday(raw) == "", raw
    # 全量：任何 YYYY-MM-DD 都不得被解析成"另一个合法日子"（落空可以，猜错不行）
    for year in range(1950, 2031):
        for month in range(1, 13):
            got = F.clean_birthday(f"{year:04d}-{month:02d}-15")
            assert got in ("", f"{month:02d}-15"), (year, month, got)


def test_animation_defaults_to_on():
    """默认开启（老用户升级后不该静默失去画面），且未配置时清洗结果也是 True。"""
    assert F.DEFAULT_ANIMATION is True
    assert F.normalize_festival_config({})["animation"] is True
    assert F.normalize_festival_config({"festival_reminder_animation": "0"})["animation"] is False


def test_animation_setting_round_trips_through_the_page(tmp_path):
    """「节日动画」开关的写回与刷新（与生日行对称，原先两处都零覆盖）。"""
    page = _page(tmp_path)
    page.animation_check.setChecked(False)
    page.apply_to_config()
    assert page.config.get("festival_reminder_animation") is False

    page.animation_check.setChecked(True)  # 界面被改脏
    page.refresh_from_config()
    assert page.animation_check.isChecked() is False, "刷新应按配置回滚"


def test_no_window_does_not_burn_the_days_chance(tmp_path):
    """拿不到窗口时不播、不抛异常，且**不烧掉当天机会**（下个提醒点补播）。"""
    service, app = _service(_cfg_with(tmp_path))
    app.win = None
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))  # 不得抛

    restored = _Win()
    app.win = restored
    service._on_tick(dt.datetime(2026, 2, 17, 21, 0, 5))
    assert restored.anim_requests == ["收红包"]


def test_invisible_window_does_not_burn_the_days_chance(tmp_path):
    """桌宠不可见（被隐藏/设置窗打开）时不播，且不烧掉当天机会。"""
    service, app = _service(_cfg_with(tmp_path))
    app.win = _WinInvisible()
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))
    assert app.win.anim_requests == []

    visible = _Win()
    app.win = visible
    service._on_tick(dt.datetime(2026, 2, 17, 21, 0, 5))
    assert visible.anim_requests == ["收红包"]


def test_text_and_animation_follow_the_same_festival_on_a_multi_hit_day(tmp_path):
    """一天命中多个节日时，文案与动画必须指向**同一个**节日（hits[0] 口径）。"""
    from pet.festival_calendar import lunar_to_solar

    mid_autumn = lunar_to_solar(2026, 8, 15)
    service, app = _service(
        _cfg_with(tmp_path, festival_birthday=f"{mid_autumn.month:02d}-{mid_autumn.day:02d}")
    )
    service.apply_config()

    service._on_tick(dt.datetime(mid_autumn.year, mid_autumn.month, mid_autumn.day, 9, 0, 5))

    assert app.win.bubbles[-1].startswith("今日是你的生日"), app.win.bubbles[-1]
    # 生日在真实素材池里解析到的动画：素材齐全时是「端蛋糕送礼物」，缺该素材时退到
    # 关键词级「拆礼物」。若哪天改成取 hits[-1]，文案仍说生日、动画却会变成
    # 「中秋赏月吃月饼」→ 这条立刻红
    expected = "端蛋糕送礼物" if HAS_CAKE_CLIP else "拆礼物"
    assert app.win.anim_requests == [expected]


def test_animation_is_played_again_on_the_next_festival_day(tmp_path):
    """跨天复位：第二天的节日要重新播（记账集合只保留当天）。"""
    service, app = _service(_cfg_with(tmp_path))
    service.apply_config()

    service._on_tick(dt.datetime(2026, 2, 17, 9, 0, 5))  # 春节
    service._on_tick(dt.datetime(2026, 2, 18, 9, 0, 5))  # 次日雨水（季节兜底）

    assert app.win.anim_requests == ["收红包", "放风筝"], "第二天必须重新播一次"


def test_startup_catch_up_plays_the_animation(tmp_path, monkeypatch):
    """启动补提醒也要播动画（中午才开机时，当天的画面不能丢）。"""
    import pet.festival_service as festival_service

    class _FrozenDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 2, 17, 12, 0, 0)  # 春节，已过首个提醒点

    service, app = _service(_cfg_with(tmp_path))
    monkeypatch.setattr(festival_service, "datetime", _FrozenDatetime)
    service.start()
    try:
        assert app.win.bubbles, "启动补提醒应出气泡"
        assert app.win.anim_requests == ["收红包"]
    finally:
        service.stop()


def test_unconfirmed_request_is_not_recorded_and_is_retried(tmp_path):
    """请求只排队（没确认上屏）时**不记账**，下一个提醒点补播。

    语义取舍：宁可同一天补播一次，也不要因为被 `request_link_idle` / 新的联动动作
    覆盖掉而当天一次都不播。
    """
    service, app = _service(_cfg_with(tmp_path))
    app.win = _WinQueuedOnly()
    service.apply_config()

    service._on_tick(dt.datetime(2026, 9, 25, 9, 0, 5))  # 中秋，09:00
    assert app.win.anim_requests == ["中秋赏月吃月饼"]

    service._on_tick(dt.datetime(2026, 9, 25, 21, 0, 5))  # 21:00 补播
    assert app.win.anim_requests == ["中秋赏月吃月饼", "中秋赏月吃月饼"]


def test_new_rows_are_collected_into_domain_sections(tmp_path):
    """新增的「节日动画」「我的生日」两行必须被域收集机制收进 SettingsSection。

    没包在 SettingRow 内（或没被收集）的控件在**打包版里不可见**——这是本项目的
    历史事故点，故对新增行同样加护栏。
    """
    from PySide6.QtWidgets import QApplication

    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog
    from pet.settings_widgets import SettingsSection

    QApplication.instance() or QApplication([])
    dialog = ModernSettingsDialog(Config(base=tmp_path), include_ai=False)
    try:
        sections = dialog.findChildren(SettingsSection)
        for target in ("settingRow_festival_reminder_animation", "settingRow_festival_birthday"):
            holders = [s for s in sections if any(r.objectName() == target for r in s.rows)]
            assert holders, f"{target} 未被任何域卡片收集（打包版会不可见）"
    finally:
        dialog.close()


def test_birthday_setting_round_trips_through_the_page(tmp_path):
    """「我的生日」行的写回与刷新：用户填什么就存什么，刷新按配置回滚。"""
    page = _page(tmp_path)
    page.birthday_edit.setText("10-24")
    page.apply_to_config()
    assert page.config.get("festival_birthday") == "10-24"

    # 界面被改脏后，refresh 必须回到配置里的值（取消保存场景）
    page.birthday_edit.setText("99-99")
    page.refresh_from_config()
    assert page.birthday_edit.text() == "10-24"

    # 清空 = 关闭生日提醒
    page.birthday_edit.setText("")
    page.apply_to_config()
    assert page.config.get("festival_birthday") == ""

    # 非法日期原样落盘、由 normalize 清洗成"不提醒"（清洗只有一处实现）
    page.birthday_edit.setText("02-30")
    page.apply_to_config()
    assert F.normalize_festival_config(page.config)["birthday"] == ""
