# -*- coding: utf-8 -*-
"""节日提醒：节日/节气 → 内置动画的绑定表（纯数据 + 纯函数，零 Qt / 零 GUI）。

设计要点
--------
- **键是 ``Festival.id``**（英文小写 slug，见 ``festival_data.py``）；值是候选动画名
  元组，**按优先级排列**。动画名 = 素材文件名去掉 ``.webm``（``library.py`` 的
  ``name = path.stem``），**不含目录前缀**——``events/balance/余额-钱袋满溢.webm``
  的请求名是裸名 ``余额-钱袋满溢``。
- **三级降级**：精确表 → 关键词表 → 节气季节兜底。三级都没有可用素材时返回
  ``None``，由服务层静默跳过（换角色、外部 DLC 角色包缺素材都属正常情况）。
- **只在「当前角色实际拥有的动作池」里挑**：``pick_animation`` 的所有返回值都来自
  调用方传入的 ``available``，绝不返回角色没有的动画名——否则请求会打到窗口的
  缺名守卫（``window._switch`` 的 ``lib.names()`` 检查）上，每次提醒刷一条 warning。
- **素材缺口是刻意保留的**：雨水/谷雨/小满/芒种/处暑/白露六个节气、以及复活节/
  母亲节/父亲节没有专属素材，靠季节兜底或直接不播（见 ``KNOWN_GAPS`` 与测试）。
  不为了"每个节日都有动画"去硬塞氛围不符的素材。
- 本模块**零第三方依赖**（只有 ``from __future__`` 与 ``typing``），因此天然满足
  「纯逻辑层零 Qt」的机器化守卫（``tests/test_architecture.py``）。
- 素材库的名字用**真实文件 stem**，**不要抄 ``catalog.ANIM_FILES``**：那个 dict 已
  严重脱节（只列 51 个、其中 5 个名字对不上任何文件），且被 ``assert len == 51``
  与 ``tests/test_runtime.py`` 双重冻结。
"""

from __future__ import annotations

from typing import Iterable

# ---------------------------------------------------------------- 季节
SEASON_SPRING = "spring"
SEASON_SUMMER = "summer"
SEASON_AUTUMN = "autumn"
SEASON_WINTER = "winter"

#: 节气/季节兜底池：无专属素材的日子至少能播一段"时令相符"的通用动画。
#: 选择原则与文案库一致——氛围必须对得上，宁缺毋滥。
SEASON_ANIMATIONS: dict[str, tuple[str, ...]] = {
    SEASON_SPRING: ("放风筝", "蝴蝶蜜蜂环绕头顶开花", "凭空生花", "荡秋千"),
    SEASON_SUMMER: ("摇扇纳凉", "吃西瓜", "吃冰淇淋融化"),
    SEASON_AUTUMN: ("被落叶淹没", "吃大闸蟹", "插茱萸赏菊", "吃重阳糕"),
    SEASON_WINTER: ("堆雪人", "涮火锅", "吃糖葫芦", "吃饺子"),
}

#: 节气 id → 季节。注意 24 节气里**没有 ``term_06``**：清明在 festival_data 里
#: 复用节日 id ``qingming``（同时带 cn + solar_term 两个类别）。
SOLAR_TERM_SEASONS: dict[str, str] = {
    "term_00": SEASON_WINTER,  # 小寒
    "term_01": SEASON_WINTER,  # 大寒
    "term_02": SEASON_SPRING,  # 立春
    "term_03": SEASON_SPRING,  # 雨水
    "term_04": SEASON_SPRING,  # 惊蛰
    "term_05": SEASON_SPRING,  # 春分
    "qingming": SEASON_SPRING,  # 清明（节气口径的特例 id）
    "term_07": SEASON_SPRING,  # 谷雨
    "term_08": SEASON_SUMMER,  # 立夏
    "term_09": SEASON_SUMMER,  # 小满
    "term_10": SEASON_SUMMER,  # 芒种
    "term_11": SEASON_SUMMER,  # 夏至
    "term_12": SEASON_SUMMER,  # 小暑
    "term_13": SEASON_SUMMER,  # 大暑
    "term_14": SEASON_AUTUMN,  # 立秋
    "term_15": SEASON_AUTUMN,  # 处暑
    "term_16": SEASON_AUTUMN,  # 白露
    "term_17": SEASON_AUTUMN,  # 秋分
    "term_18": SEASON_AUTUMN,  # 寒露
    "term_19": SEASON_AUTUMN,  # 霜降
    "term_20": SEASON_WINTER,  # 立冬
    "term_21": SEASON_WINTER,  # 小雪
    "term_22": SEASON_WINTER,  # 大雪
    "term_23": SEASON_WINTER,  # 冬至
}

# ---------------------------------------------------------------- 精确映射
#: 节日 id → 候选动画名（按优先级）。第一项即"首选"。
FESTIVAL_ANIMATIONS: dict[str, tuple[str, ...]] = {
    # —— 中国节日 ——
    "chunjie": ("收红包", "写福字", "舞狮头", "吃饺子", "吃年糕", "放烟花"),
    "chuxi": ("吃饺子", "放烟花", "收红包", "写福字"),
    "yuanxiao": ("吃汤圆", "放孔明灯"),
    "qingming": ("吃青团", "放风筝", "荡秋千"),
    "duanwu": ("吃粽子",),
    "qixi": ("穿针乞巧", "放孔明灯"),
    # 中元节只能"肃穆追思"（festival_quotes_cn 明令禁止鬼怪/猎奇），故不放萌化小幽灵
    "zhongyuan": ("放河灯", "放孔明灯"),
    "zhongqiu": ("中秋赏月吃月饼", "吃大闸蟹"),
    "chongyang": ("插茱萸赏菊", "吃重阳糕", "吃长寿面"),
    "labajie": ("吃腊八粥",),
    "longtaitou": ("吃长寿面",),  # 弱匹配：龙须面联想，无理发/春耕素材
    "yuandan": ("放烟花", "吹气球"),
    "ertongjie": ("骑木马", "吹气球", "抽陀螺", "踢毽子"),
    "laodongjie": ("工作状态-忙碌点按", "工作状态-清点归档", "工作状态-雀跃庆祝"),
    "guoqingjie": ("放烟花",),  # 弱匹配；刻意不涉政治表达
    # —— 西方节日 ——
    "halloween": ("讨糖南瓜灯", "萌化小幽灵"),
    "christmas": ("装点圣诞树", "拆礼物", "堆雪人"),
    "christmas_eve": ("装点圣诞树", "拆礼物"),
    "april_fools": ("扑克魔术", "变鸽子"),
    # 该素材只随已安装版发布、仓库素材里没有；缺它时按关键词兜底到「拆礼物」
    "valentine": ("端蛋糕送礼物",),
    # —— 用户生日（动态节日：日期来自配置，见 festival_data.BIRTHDAY_FESTIVAL）——
    "shengri": ("端蛋糕送礼物",),
    # —— 24 节气：只登记有专属素材的，其余走季节兜底 ——
    "term_00": ("涮火锅", "吃糖葫芦", "堆雪人"),  # 小寒
    "term_01": ("涮火锅", "吃糖葫芦", "堆雪人"),  # 大寒
    "term_02": ("放风筝", "蝴蝶蜜蜂环绕头顶开花"),  # 立春
    "term_04": ("蝴蝶蜜蜂环绕头顶开花", "动物环绕"),  # 惊蛰
    "term_05": ("放风筝", "荡秋千", "蝴蝶蜜蜂环绕头顶开花"),  # 春分
    "term_08": ("摇扇纳凉", "吃西瓜"),  # 立夏（弱）
    "term_11": ("摇扇纳凉", "吃西瓜", "吃冰淇淋融化"),  # 夏至
    "term_12": ("摇扇纳凉", "吃西瓜", "吃冰淇淋融化"),  # 小暑
    "term_13": ("摇扇纳凉", "吃西瓜", "吃冰淇淋融化"),  # 大暑
    "term_14": ("吃西瓜", "被落叶淹没"),  # 立秋（弱：啃秋）
    "term_17": ("被落叶淹没", "吃大闸蟹"),  # 秋分
    "term_18": ("被落叶淹没", "吃大闸蟹"),  # 寒露
    "term_19": ("被落叶淹没",),  # 霜降
    "term_20": ("吃饺子", "涮火锅", "吃糖葫芦"),  # 立冬
    "term_21": ("堆雪人", "涮火锅", "吃糖葫芦"),  # 小雪
    "term_22": ("堆雪人", "涮火锅", "吃糖葫芦"),  # 大雪
    "term_23": ("吃饺子", "堆雪人", "涮火锅"),  # 冬至
}

# ---------------------------------------------------------------- 关键词兜底
#: 节日 id → 关键词。用于**换角色 / 外部 DLC 角色包**里动画名与内置不完全一致时，
#: 仍能从当前动作池里挑到语义相符的一段。刻意避开过于宽泛的词（如单独一个"月"）。
FESTIVAL_ANIMATION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "chunjie": ("红包", "福字", "舞狮", "饺", "年糕", "烟花"),
    "chuxi": ("饺", "烟花", "红包", "福字"),
    "yuanxiao": ("汤圆", "孔明灯"),
    "longtaitou": ("长寿面", "龙"),
    "qingming": ("青团", "风筝", "秋千"),
    "duanwu": ("粽",),
    "qixi": ("乞巧", "针", "河灯"),
    "zhongyuan": ("河灯", "孔明灯"),
    "zhongqiu": ("月饼", "中秋"),
    "chongyang": ("重阳", "茱萸", "菊"),
    "labajie": ("腊八",),
    "yuandan": ("烟花", "气球"),
    "ertongjie": ("木马", "气球", "陀螺", "毽子"),
    "laodongjie": ("工作状态",),
    "guoqingjie": ("烟花",),
    "valentine": ("蛋糕", "礼物"),
    "shengri": ("蛋糕", "礼物"),
    "april_fools": ("魔术", "鸽子"),
    "halloween": ("南瓜", "讨糖", "幽灵"),
    "christmas": ("圣诞", "礼物"),
    "christmas_eve": ("圣诞", "礼物"),
    "term_00": ("火锅", "糖葫芦", "雪人"),
    "term_01": ("火锅", "糖葫芦", "雪人"),
    "term_02": ("风筝", "花"),
    "term_04": ("花", "动物"),
    "term_05": ("风筝", "秋千", "花"),
    "term_08": ("纳凉", "西瓜"),
    "term_11": ("纳凉", "西瓜", "冰淇淋"),
    "term_12": ("纳凉", "西瓜", "冰淇淋"),
    "term_13": ("纳凉", "西瓜", "冰淇淋"),
    "term_14": ("西瓜", "落叶"),
    "term_17": ("落叶", "闸蟹"),
    "term_18": ("落叶", "闸蟹"),
    "term_19": ("落叶",),
    "term_20": ("饺", "火锅", "糖葫芦"),
    "term_21": ("雪人", "火锅", "糖葫芦"),
    "term_22": ("雪人", "火锅", "糖葫芦"),
    "term_23": ("饺", "雪人", "火锅"),
}

#: 已知的素材缺口（**刻意保留**，不是待修的 bug）：这些 id 在标准素材包里没有
#: 氛围相符的动画，且不适用季节兜底，因此当天不会播动画（提醒气泡照常）。
#: 补素材后把对应 id 从本表移除，并同步映射表与测试。
KNOWN_GAPS: frozenset[str] = frozenset(
    {
        "easter",  # 复活节：无彩蛋/兔子素材
        "mothers_day",  # 母亲节：无康乃馨/送花素材
        "fathers_day",  # 父亲节：无领带/贺卡素材
    }
)


def season_for(festival_id: str) -> str | None:
    """返回该 id 对应的季节（仅节气有；非节气返回 ``None``）。"""
    return SOLAR_TERM_SEASONS.get(str(festival_id or ""))


def pick_animation(festival_id: str, available: Iterable[str]) -> str | None:
    """从 ``available`` 里挑一段与该节日匹配的动画；没有可用的返回 ``None``。

    三级降级（每一级都只在 ``available`` 内挑选）：
      1. 精确表 ``FESTIVAL_ANIMATIONS``（按优先级取第一个可用的）；
      2. 关键词表 ``FESTIVAL_ANIMATION_KEYWORDS``（按动画名字典序取第一个命中的，
         保证同样的输入永远得到同样的输出，便于测试）；
      3. 节气的季节兜底 ``SEASON_ANIMATIONS``。

    ``available`` 传当前角色的动作池（``PetWindow.acts``）；传空表示"没有可用素材"，
    直接返回 ``None``——调用方据此静默跳过，不打日志、不影响提醒本身。
    """
    pool = {str(name) for name in (available or ()) if name}
    if not pool:
        return None
    key = str(festival_id or "")
    for name in FESTIVAL_ANIMATIONS.get(key, ()):
        if name in pool:
            return name
    keywords = FESTIVAL_ANIMATION_KEYWORDS.get(key, ())
    if keywords:
        for name in sorted(pool):
            if any(keyword in name for keyword in keywords):
                return name
    season = season_for(key)
    if season:
        for name in SEASON_ANIMATIONS.get(season, ()):
            if name in pool:
                return name
    return None


def all_animation_names() -> tuple[str, ...]:
    """映射表引用到的全部动画名（去重升序）。

    供测试核对"表里写的名字在真实素材里都存在"——这正是 ``catalog.ANIM_FILES``
    当初脱节却无人发现的原因，加一道机器化护栏。
    """
    names: set[str] = set()
    for pool in FESTIVAL_ANIMATIONS.values():
        names.update(pool)
    for pool in SEASON_ANIMATIONS.values():
        names.update(pool)
    return tuple(sorted(names))
