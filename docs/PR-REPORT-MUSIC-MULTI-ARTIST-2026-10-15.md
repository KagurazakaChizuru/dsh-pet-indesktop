# PR 报告：多歌手分隔符归一（酷狗/汽水歌词）+ 设置页文案指引

> **基线**：`99bdc7f`（main，含 #277）
> **分支**：`feat/music-multi-artist`　**日期**：2026-10-15
> **范围**：6 个文件（实现 3、测试 1、文档 2）
> **关联**：用户需求「酷狗音乐/汽水音乐看不到歌词」；调研记录见本报告 §三

## 一、核心特性

用户反馈酷狗音乐/汽水音乐放歌时桌宠没有歌词。调研结论（2026-10-15 会话的本机实测
+ 公开资料）：
**两个播放器都已注册 Windows SMTC**（汽水时间轴完整；酷狗需在其设置里开
「支持系统播放控件」且无时间轴），"正在播放"层零改动即可识别——填 exe 路径
没用是因为那只影响右键「打开播放器」菜单，与歌词链无关。

真正丢词的原因（实机复现）：酷狗 SMTC 报的歌手是 `FLOW、GRANRODEO`（CJK 顿号），
歌词源返回 `FLOW/GRANRODEO`（斜杠），`_name_matches` 只做整串子串比对 →
「搜索到 10 个候选但无人匹配歌手」→ 丢词。**这是取词链的通用缺陷**，
对网易云/QQ 的多歌手曲目同样有效。（SMTC 那条字符串来自 2026-10-15 的实机观察，
本轮未复验——原因见 §五；本轮能复验的是候选侧：网易云活数据 10 条候选在基线
实现下 10/10 判 False。）

| # | 能力 | 说明 |
|---|---|---|
| 1 | 多歌手分隔符归一 | `、` `/` `／` `&` `×` `,` `； feat. ft.` 两侧都是多歌手形态时逐段比对 |
| 2 | 设置页指引 | 「显示歌词」行写明酷狗的开关位置；酷狗/汽水无需填路径 |

**红线 / 不变量**：整串子串命中优先于逐段比对——**本 PR 只增加命中，不改既有命中**
（基线命中过的对子在两版都命中）；只有两侧都切成 ≥2 段时才走新增的逐段比对，
单侧无分隔符不新增任何命中；逐段比对是去空白后**相等**（不用子串，防碎片假命中）。
两处**兼容取舍**（子串快路与 1 字符段都保持现状语义）见 §三末尾，附实测与复验命令。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/music_lyric.py` | +23 / −2 | `_name_matches`：整串子串命中后，新增「两侧都含分隔符 → 归一逐段**相等**比对」分支；`_ARTIST_SEP_RE` 模块级编译一次，feat/ft 带**双侧**词边界且在去空白前切分（两轮盲审返修：左侧无边界会拆碎 swift/craft，右侧无边界会拆碎 Featherstone/FTIsland）；逐段比对为去空白后相等；另同步 `:338` 的陈旧注释为「仅两侧均呈多歌手形态时增加逐段匹配」（纯注释，无行为改动，见 §三） |
| `pet/modern_settings_dialog.py` | +1 / −1 | 「显示歌词」行 hint：补酷狗开关的具体位置（设置 → 常规设置 → 播放 → 支持系统播放控件）+「酷狗/汽水无需填路径」（防止再有人往音乐关联槽里填 exe） |
| `pet/music_title.py` | +4 / −2 | 陈旧注释同步（纯注释/docstring，无行为改动）：两处把 `_name_matches` 描述成「子串校验」的文案，补上「两侧都写成多歌手形态时，分隔符归一后再逐段**相等**比一次」——原描述停留在本 PR 之前的行为 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_music_lyric.py` | +53 / −0 | 四条：分隔符变体互认（含实机样本 `FLOW/GRANRODEO` × `FLOW、GRANRODEO`、中文、feat.、英文逗号）；防误伤（单侧无分隔符/多歌手互不相干）；词边界反例（盲审两轮：swift/craft/daft punk 不被拆碎、碎片不假命中、Featherstone/FTIsland 词首不误拆）；**左词边界反例**（`Daft Punk`×`Da、Punk`、`Swift Lefty`×`Swi、X`、`Soft Cell`×`So、胖胖`：去掉 feat/ft 前的 `\b` 时这三条转红，见 §六消融） |

红→绿（真跑，不是推断）：把 `pet.music_lyric._name_matches` 在内存里换回基线
`99bdc7f` 实现（pytest 插件 `-p baseline_impl`，**不改文件**）后跑本次新增的四条
测试 → **3 failed, 4 passed**，其中 `test_name_matches_multi_artist_separator_variants`
红在 `tests/test_music_lyric.py:2154` 的
`assert music_lyric._name_matches("FLOW/GRANRODEO", "FLOW、GRANRODEO")`（False）；
换回本分支实现后 `test_music_lyric.py` 107 条全绿（见 §六）。

### 文档

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `docs/INDEX.md` | +1 / −0 | 本报告按「新文档入场规则」登记（一句话摘要 + 何时必读），第 144 行 |
| `docs/PR-REPORT-MUSIC-MULTI-ARTIST-2026-10-15.md` | +639 / −0 | 三份交付证据：修改文件说明 / 性能分析 / 实机运行记录；终版行数以 `git diff --numstat 99bdc7f -- docs/` 为准（本文件 +639/−0、INDEX +1/−0） |

### 未改动（有意）

- **窗口标题通道**：不新增。汽水标题恒为「汽水音乐」（读不到内容）；酷狗暂停时
  标题残留上一首会串台。SMTC 已通，标题通道是下位替代。
- `pet/music_players.py` 的 PLAYERS 表：不加酷狗/汽水条目——该表服务右键
  「打开播放器」菜单，与歌词无关；等真有"打开酷狗"需求再说。
- QQ 音乐歌词源 500（本机当日整体故障，curl 直测同样 500）：源侧问题，非本仓可修。

## 三、实现要点与调研记录

调研方式（2026-10-15 会话）：本机枚举 SMTC 会话（酷狗 20.1.51.27967 / 汽水 3.7.0
均在运行），直接调 `get_now_playing()` 验证汽水在播曲目可读；酷狗/汽水的 SMTC
支持情况对照 Lyricify 官方支持表（酷狗"无时间轴信息"、汽水"完美"）。

分隔符集合的取法：CJK 顿号（酷狗实测）、ASCII/全角斜杠（网易云/QQ 歌词源）、
`&`/`×`/逗号/分号（常见曲库）、`feat.`/`ft.`（英文曲库，带词边界——否则 swift/
craft/daft punk 会被拆碎，盲审 P1）。逐段比对是**去空白后相等**（不用子串——
2-3 字符碎片几乎什么都命中，盲审 P2）。`&`/`/` 会拆开 Simon & Garfunkel / AC/DC
这类组合名，由「两侧都是多歌手形态」闸门限幅（盲审 P3）。逐段比对要求
**两侧**都是多歌手形态（`len(raw) >= 2`），单侧无分隔符不新增命中。

**两处兼容取舍**（2026-10-16 复验时改正了本报告上一版的两条**错误**描述；
两条都有实测，命令与原始输出见下）：

- **闸门只收窄新增的逐段路径，不构成「防单名误命中」的守卫**。函数先跑**既有的
  整串子串快路**（`a in b or b in a`），命中即返回；`len(raw) >= 2` 只在子串未中
  之后才起作用。所以 `_name_matches("A", "Aimer、B")` = **True**、`_name_matches("赵雷",
  "赵雷、马頔")` = **True**，且与基线 `99bdc7f` 同值——这是**有意保留的既有语义**：
  本 PR 只增加命中，不制造「以前命中、现在不命中」的回归。上一版报告写成
  「防止 "A" 误中 "Aimer、B"」是错的，A 走的根本不是新增分支。（测试里也没有把
  这条写成断言：`test_name_matches_multi_artist_does_not_overreach` 断言的是
  `not _name_matches("A", "B、C")` 这种本来就互不相干的组合。）
- **1 字符段参与逐段比对**。实现里没有按段长度过滤的分支（只滤空段），单字母歌手
  照样参与相等比对：`_name_matches("A、B", "X、B")` = **True**，命中来自 1 字符段
  `'b' == 'b'`（基线同一对 = False，即这是本 PR 新增的命中）。上一版报告写成
  「1 字符段（罕见单字母歌手）不参与逐段比对」与实现不符；如实记录为**保留现状
  语义的取舍**：碎片假命中的影响由「去空白后**相等**」（而非子串）压到「整段一样
  才算命中」，短段不做额外限制。
- **源码注释已同步（本轮做的）**：`pet/music_lyric.py:338` 原注释写着
  `# 只在两侧都是多歌手形态时才逐段比：单侧无分隔符保持原语义（防单名误命中）`，
  括号里那半句与本报告更正后的描述不一致——闸门只收窄**新增的**逐段路径，
  `_name_matches` 仍会在整串子串快路上命中 "A" × "Aimer、B"。本轮把该行改成
  `# 仅两侧均呈多歌手形态时增加逐段匹配`：**纯注释同步，函数体一行不动**
  （`pet/music_lyric.py` 的 diff 仍是 +23/−2，行为与上一轮完全相同）。

复验命令与原样输出（只读脚本，不改产品代码；`.scratch/` 被 gitignore，故附全文）：

    cd D:/dsh-pet-wt-music
    python .scratch/music-multi-artist/verify_name_matches_claims.py

```
python 3.13.7  regex='\\s*(?:[、/／&×,，;；]|\\bfeat\\b\\.?|\\bft\\b\\.?)\\s*'
----------------------------------------------------------------------------------------------------------------------
用例                                candidate           wanted              子串快路     闸门    逐段对       本分支    基线
----------------------------------------------------------------------------------------------------------------------
断言1 单名 vs 多歌手（子串能被包含）             A                   Aimer、B             True     False None      True   True
断言1 反向                            Aimer、B             A                   True     False None      True   True
断言1 中文单名 vs 多歌手                   赵雷                  赵雷、马頔               True     False None      True   True
断言2 1 字符段参与逐段相等                   A、B                 X、B                 False    True  ('b', 'b')True   False
断言2 1 字符段参与逐段相等（反向）               B、X                 A、B                 False    True  ('b', 'b')True   False
断言2 1 字符段不因长度被过滤                  Z                   Zed、Y               True     False None      True   True
本 PR 目标：实机样本                      FLOW/GRANRODEO      FLOW、GRANRODEO      False    True  ('flow', 'flow')True   False
本 PR 目标：中文多变体                     周杰伦、林俊杰             林俊杰/Jay Chou        False    True  ('林俊杰', '林俊杰')True   False
拒绝：碎片不假命中                         Craft               Soft、Raft           False    False None      False  False
拒绝：两串歌手互不相干                       其他歌手                周杰伦                 False    False None      False  False
----------------------------------------------------------------------------------------------------------------------
切分结果（只列切口不同的用例）：
  断言1 单名 vs 多歌手（子串能被包含）: candidate→['a']  wanted→['aimer', 'b']
  断言1 反向: candidate→['aimer', 'b']  wanted→['a']
  断言1 中文单名 vs 多歌手: candidate→['赵雷']  wanted→['赵雷', '马頔']
  断言2 1 字符段参与逐段相等: candidate→['a', 'b']  wanted→['x', 'b']
  断言2 1 字符段参与逐段相等（反向）: candidate→['b', 'x']  wanted→['a', 'b']
  断言2 1 字符段不因长度被过滤: candidate→['z']  wanted→['zed', 'y']
  本 PR 目标：实机样本: candidate→['flow', 'granrodeo']  wanted→['flow', 'granrodeo']
  本 PR 目标：中文多变体: candidate→['周杰伦', '林俊杰']  wanted→['林俊杰', 'jaychou']
  拒绝：碎片不假命中: candidate→['craft']  wanted→['soft', 'raft']
  拒绝：两串歌手互不相干: candidate→['其他歌手']  wanted→['周杰伦']
----------------------------------------------------------------------------------------------------------------------
断言1 结论：_name_matches('A', 'Aimer、B') = True （基线同值： True ）
断言2 结论：_name_matches('A、B', 'X、B') = True → 命中来自 1 字符段 'b' == 'b'；代码里没有任何按段长度过滤的分支
```

脚本全文（`verify_name_matches_claims.py`，111 行，`.scratch/music-multi-artist/`
被 gitignore，故原文附在这里）：

```python
# -*- coding: utf-8 -*-
"""校验报告 §三 里两条关于 `_name_matches` 行为的断言（只读脚本，不改产品代码）。

断言 1：「单侧无分隔符直接退回原语义——防止 "A" 误中 "Aimer、B" 这类单名误命中」
断言 2：「1 字符段（罕见单字母歌手）不参与逐段比对」

脚本对每个用例打印它在 `_name_matches` 里实际走到的判定步骤：
子串快路（既有行为，`a in b or b in a`）→ 闸门（两侧都 >= 2 段）→ 逐段相等，
并同时给出基线 `99bdc7f` 实现的返回值，用来区分「本 PR 改变了什么」与
「既有行为本来就这样」。

用法：
    cd D:/dsh-pet-wt-music
    python .scratch/music-multi-artist/verify_name_matches_claims.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pet.music_lyric import _ARTIST_SEP_RE, _name_matches  # noqa: E402


def baseline_name_matches(candidate: str, wanted: str) -> bool:
    """基线 99bdc7f:pet/music_lyric.py 的 `_name_matches` 原样拷贝（无分隔符归一）。"""
    a = re.sub(r"\s+", "", str(candidate or "").lower())
    b = re.sub(r"\s+", "", str(wanted or "").lower())
    if not a or not b:
        return False
    return a in b or b in a


def _segments(text: str) -> list[str]:
    raw = [re.sub(r"\s+", "", p) for p in _ARTIST_SEP_RE.split(str(text or "").lower())]
    return [p for p in raw if p]


def trace(candidate: str, wanted: str) -> dict:
    a = re.sub(r"\s+", "", str(candidate or "").lower())
    b = re.sub(r"\s+", "", str(wanted or "").lower())
    fast = bool(a or b) and (a in b or b in a)
    seg_a, seg_b = _segments(candidate), _segments(wanted)
    gate = len(seg_a) >= 2 and len(seg_b) >= 2
    pair = None
    if gate:
        pairs = [(pa, pb) for pa in seg_a for pb in seg_b if pa == pb]
        pair = pairs[0] if pairs else None
    return {
        "a": a,
        "b": b,
        "substring_fast_path": fast,
        "seg_a": seg_a,
        "seg_b": seg_b,
        "gate_two_sided": gate,
        "segment_equal_pair": pair,
        "new": _name_matches(candidate, wanted),
        "baseline": baseline_name_matches(candidate, wanted),
    }


CASES = [
    # (说明, candidate, wanted)
    ("断言1 单名 vs 多歌手（子串能被包含）", "A", "Aimer、B"),
    ("断言1 反向", "Aimer、B", "A"),
    ("断言1 中文单名 vs 多歌手", "赵雷", "赵雷、马頔"),
    ("断言2 1 字符段参与逐段相等", "A、B", "X、B"),
    ("断言2 1 字符段参与逐段相等（反向）", "B、X", "A、B"),
    ("断言2 1 字符段不因长度被过滤", "Z", "Zed、Y"),
    ("本 PR 目标：实机样本", "FLOW/GRANRODEO", "FLOW、GRANRODEO"),
    ("本 PR 目标：中文多变体", "周杰伦、林俊杰", "林俊杰/Jay Chou"),
    ("拒绝：碎片不假命中", "Craft", "Soft、Raft"),
    ("拒绝：两串歌手互不相干", "其他歌手", "周杰伦"),
]


def main() -> int:
    print(f"python {sys.version.split()[0]}  regex={_ARTIST_SEP_RE.pattern!r}")
    print("-" * 118)
    header = (
        f"{'用例':<34}{'candidate':<20}{'wanted':<20}"
        f"{'子串快路':<9}{'闸门':<6}{'逐段对':<10}{'本分支':<7}{'基线'}"
    )
    print(header)
    print("-" * 118)
    for label, candidate, wanted in CASES:
        t = trace(candidate, wanted)
        print(
            f"{label:<34}{candidate:<20}{wanted:<20}"
            f"{str(t['substring_fast_path']):<9}{str(t['gate_two_sided']):<6}"
            f"{str(t['segment_equal_pair']):<10}{str(t['new']):<7}{t['baseline']}"
        )
    print("-" * 118)
    print("切分结果（只列切口不同的用例）：")
    for label, candidate, wanted in CASES:
        t = trace(candidate, wanted)
        print(f"  {label}: candidate→{t['seg_a']}  wanted→{t['seg_b']}")
    print("-" * 118)
    m = lambda c, w: _name_matches(c, w)  # noqa: E731
    print("断言1 结论：_name_matches('A', 'Aimer、B') =", m("A", "Aimer、B"),
          "（基线同值：", baseline_name_matches("A", "Aimer、B"), "）")
    print("断言2 结论：_name_matches('A、B', 'X、B') =", m("A、B", "X、B"),
          "→ 命中来自 1 字符段 'b' == 'b'；代码里没有任何按段长度过滤的分支")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```


## 四、性能分析

**测量环境与时刻**（本报告的结论只对本行环境成立，换机器/换时段请按下述脚本重测）：

- Windows 11（`Windows-11-10.0.26300-SP0`）、CPython 3.13.7、AMD64、16 逻辑核；
- 测量时刻：**2026-10-16 05:09:53**（本机当日常规负载，非空载基准机）；
- 计时口径：**同进程 A/B 交替（ABBA）**。A（old）= 基线 `99bdc7f` 的 `_name_matches`
  原样拷贝在脚本里；B（new）= 本分支实现，脚本直接 `import` 产品函数
  `pet.music_lyric._name_matches`（不是拷贝，测的就是要发出去的那份代码）。
  9 轮 × 每轮每实现 2 个计时块（ABBA 交替 a1/b1/b2/a2，轮值取两块均值），
  **每个计时块 6000 批**，样本写死在脚本的 `PATHS` 里；下表列名「每个计时块calls」
  = 6000 × 该路径样本条数——它数的是**单个计时块**的调用数，不是每轮：每轮每实现
  两个计时块，故每轮每实现的真实调用量是该列的 2 倍（9 轮合计 = 9 × 2 × 6000 ×
  该路径样本条数）。

**完整可执行脚本**（`.scratch/music-multi-artist/ab_name_matches.py`；`.scratch/` 被
gitignore，故原文附在这里保证可复现）：

```python
# -*- coding: utf-8 -*-
"""`_name_matches` 同进程 A/B 计时（报告 §四 表格的复现脚本）。

- **A（old）**：基线 `99bdc7f:pet/music_lyric.py` 的 `_name_matches`，原样拷在本文件里。
- **B（new）**：本分支实现，直接 `import` 产品函数 `pet.music_lyric._name_matches`
  （不是拷贝，测的就是要发出去的那份代码）。

同一进程里 A/B 交替（ABBA 顺序）计时，消掉换机器/换时段带来的漂移；每条路径的
样本、批次数、轮数都写在文件里，可原样复现。

用法（在仓库根目录）：
    python .scratch/music-multi-artist/ab_name_matches.py
    python .scratch/music-multi-artist/ab_name_matches.py --rounds 9 --batch 6000

输出：每条路径的 µs/次调用（轮中位数 + 轮最小/最大）、A/B 差值、以及两版在
同一批样本上的**返回值**（用来看清各自实际走到哪条分支）。
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pet.music_lyric import _name_matches as new_matches  # noqa: E402


def old_matches(candidate: str, wanted: str) -> bool:
    """基线 99bdc7f 实现（原样拷贝，无分隔符归一）。"""
    a = re.sub(r"\s+", "", str(candidate or "").lower())
    b = re.sub(r"\s+", "", str(wanted or "").lower())
    if not a or not b:
        return False
    return a in b or b in a


# 每条路径 = (说明, [(candidate, wanted), ...])
PATHS: list[tuple[str, list[tuple[str, str]]]] = [
    ("P1 整串子串命中（未改路径）", [
        ("周杰伦", "周杰伦/Jay Chou"),
        ("FLOW", "FLOW"),
        ("Aimer", "Aimer"),
    ]),
    ("P2 多歌手归一逐段命中（新增分支）", [
        ("FLOW/GRANRODEO", "FLOW、GRANRODEO"),
        ("周杰伦、林俊杰", "林俊杰/Jay Chou"),
        ("A、B", "X、B"),
    ]),
    ("P3 无关候选拒绝（仍要切分）", [
        ("其他歌手", "周杰伦"),
        ("五月天", "陈奕迅"),
    ]),
    ("P4 单侧无分隔符（新增闸门路径）", [
        ("周杰伦、林俊杰", "五月天"),
        ("Aimer、B", "Aimer B"),
    ]),
    ("P5 混合样本整体（canonical 3 对）", [
        ("FLOW/GRANRODEO", "FLOW、GRANRODEO"),
        ("周杰伦", "周杰伦/Jay Chou"),
        ("其他歌手", "周杰伦"),
    ]),
]


def time_batch(fn, pairs, batch: int) -> float:
    """返回 batch * len(pairs) 次调用的墙钟耗时（秒）。"""
    t0 = time.perf_counter()
    for _ in range(batch):
        for candidate, wanted in pairs:
            fn(candidate, wanted)
    return time.perf_counter() - t0


def measure(pairs, batch: int, rounds: int) -> tuple[list[float], list[float], int]:
    calls = batch * len(pairs)
    old_rounds: list[float] = []
    new_rounds: list[float] = []
    for _ in range(rounds):
        a1 = time_batch(old_matches, pairs, batch)
        b1 = time_batch(new_matches, pairs, batch)
        b2 = time_batch(new_matches, pairs, batch)
        a2 = time_batch(old_matches, pairs, batch)
        old_rounds.append((a1 + a2) / 2 / calls * 1e6)
        new_rounds.append((b1 + b2) / 2 / calls * 1e6)
    return old_rounds, new_rounds, calls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=9, help="ABBA 轮数（默认 9）")
    parser.add_argument("--batch", type=int, default=6000, help="每个计时块批次数（默认 6000）")
    args = parser.parse_args()

    print(f"平台: {platform.platform()}  CPython {platform.python_version()}  "
          f"{platform.machine()}  CPU 逻辑核 {os.cpu_count()}")
    print(f"时刻: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"参数: rounds={args.rounds} batch={args.batch}  调用顺序=ABBA 交替")
    print("=" * 122)
    header = (f"{'路径':<38}{'每个计时块calls':>10}{'基线 old µs':>22}{'本分支 new µs':>24}"
              f"{'差值 µs':>11}{'倍数':>8}")
    print(header)
    print("-" * 122)
    for label, pairs in PATHS:
        old_rounds, new_rounds, calls = measure(pairs, args.batch, args.rounds)
        o_med, n_med = statistics.median(old_rounds), statistics.median(new_rounds)
        print(f"{label:<38}{calls:>10}"
              f"{f'{o_med:.2f} [{min(old_rounds):.2f}–{max(old_rounds):.2f}]':>22}"
              f"{f'{n_med:.2f} [{min(new_rounds):.2f}–{max(new_rounds):.2f}]':>24}"
              f"{n_med - o_med:>+11.2f}{n_med / o_med:>8.2f}x")
    print("-" * 122)
    print("返回值对照（看清各路径实际走到哪个分支；True/False 是 (基线, 本分支)）：")
    for label, pairs in PATHS:
        marks = "  ".join(
            f"{c!r}×{w!r}→({old_matches(c, w)}, {new_matches(c, w)})" for c, w in pairs
        )
        print(f"  {label}: {marks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

运行命令与**原样输出**（本机 2026-10-16 05:09:53）。
**列名说明**：下表第一列在 2026-10-16 按口径澄清改名为「每个计时块calls」（原始运行
打印的是「每轮调用数」）——**只改列名，数字一字未动、未重跑**；两个存档文件
`.scratch/music-multi-artist/ab_name_matches_output.txt` 与 `ab_rerun_2rounds.txt`
里的列名同步替换，其余逐字未动（新旧列名的字段宽度都是 10 字符，整行列宽因此完全
一致）。

    cd D:/dsh-pet-wt-music
    python .scratch/music-multi-artist/ab_name_matches.py --rounds 9 --batch 6000

```
平台: Windows-11-10.0.26300-SP0  CPython 3.13.7  AMD64  CPU 逻辑核 16
时刻: 2026-10-16 05:09:53
参数: rounds=9 batch=6000  调用顺序=ABBA 交替
==========================================================================================================================
路径                                    每个计时块calls             基线 old µs              本分支 new µs      差值 µs      倍数
--------------------------------------------------------------------------------------------------------------------------
P1 整串子串命中（未改路径）                            18000      1.75 [1.73–1.81]        1.82 [1.79–1.86]      +0.07    1.04x
P2 多歌手归一逐段命中（新增分支）                         18000      2.04 [2.00–2.14]        8.53 [8.21–8.76]      +6.48    4.17x
P3 无关候选拒绝（仍要切分）                            12000      1.70 [1.69–1.74]        4.87 [4.82–5.18]      +3.17    2.86x
P4 单侧无分隔符（新增闸门路径）                          12000      1.87 [1.86–1.96]        6.47 [6.32–6.58]      +4.60    3.46x
P5 混合样本整体（canonical 3 对）                   18000      1.98 [1.96–2.20]        5.41 [5.34–5.52]      +3.43    2.73x
--------------------------------------------------------------------------------------------------------------------------
返回值对照（看清各路径实际走到哪个分支；True/False 是 (基线, 本分支)）：
  P1 整串子串命中（未改路径）: '周杰伦'×'周杰伦/Jay Chou'→(True, True)  'FLOW'×'FLOW'→(True, True)  'Aimer'×'Aimer'→(True, True)
  P2 多歌手归一逐段命中（新增分支）: 'FLOW/GRANRODEO'×'FLOW、GRANRODEO'→(False, True)  '周杰伦、林俊杰'×'林俊杰/Jay Chou'→(False, True)  'A、B'×'X、B'→(False, True)
  P3 无关候选拒绝（仍要切分）: '其他歌手'×'周杰伦'→(False, False)  '五月天'×'陈奕迅'→(False, False)
  P4 单侧无分隔符（新增闸门路径）: '周杰伦、林俊杰'×'五月天'→(False, False)  'Aimer、B'×'Aimer B'→(False, False)
  P5 混合样本整体（canonical 3 对）: 'FLOW/GRANRODEO'×'FLOW、GRANRODEO'→(False, True)  '周杰伦'×'周杰伦/Jay Chou'→(True, True)  '其他歌手'×'周杰伦'→(False, False)
```

**读数（轮中位数，方括号是轮最小–最大）与逐条结论**：

| 路径（单次调用） | 基线 `99bdc7f` | 本分支 | 差值 | 倍数 | 触发频率 |
|---|---|---|---|---|---|
| P1 整串子串命中（未改路径） | 1.75 µs [1.73–1.81] | 1.82 µs [1.79–1.86] | +0.07 µs（噪声级） | 1.04× | 每候选一次，命中即返回 |
| P2 多歌手归一逐段命中（新增分支） | 2.04 µs [2.00–2.14] | **8.53 µs** [8.21–8.76] | +6.48 µs | 4.17× | 仅两侧都是多歌手且整串子串未中时 |
| P3 无关候选拒绝（仍要切分） | 1.70 µs [1.69–1.74] | **4.87 µs** [4.82–5.18] | +3.17 µs | 2.86× | 每次查歌词十来个候选里的大多数（走到底） |
| P4 单侧无分隔符（闸门不通过） | 1.87 µs [1.86–1.96] | 6.47 µs [6.32–6.58] | +4.60 µs | 3.46× | 同拒绝路径 |
| P5 混合样本整体（同一批样本） | 1.98 µs [1.96–2.20] | 5.41 µs [5.34–5.52] | +3.43 µs | 2.73× | 用户触发级：每次查歌词十来个候选 |

1. **稳态开销**：不取词就不调用，空闲开销为 0；取词时只在这十来个候选串上多花
   3.2–6.5 µs/次，十来个候选合计约 **+35–65 µs/次取词**，相对一次秒级网络往返不可见。
2. **新增路径成本与触发频率**：未命中/逐段命中路径由基线 **1.70–2.05 µs** 抬到
   **4.87–8.53 µs（2.7–4.2×）**，每次查歌词对每个候选各触发一次（用户触发级）。
   **基线不是「次微秒级」**——上一版报告用「次微秒」描述基线是错的，正确量级是
   ~1.7–2.1 µs（本次实测最小值 1.70 µs 也在亚微秒之上）。
3. **有无新的系统调用/网络/磁盘/线程**：无。改动是纯字符串处理；`_ARTIST_SEP_RE`
   模块级编译一次（摊薄为零），`re.sub(r"\s+", ...)` 命中标准库的正则缓存，
   不作新的编译或 IO。
4. **内存有无增长**：无。每次调用多两个临时 list（段表）与一个生成器，随调用返回
   释放；无缓存、无累积结构（`_name_matches` 是纯函数）。

**另一口径（与本报告上一版同一条 canonical 命令，n=30000 次/轮，7 轮）**：
`python -c "import time;from pet.music_lyric import _name_matches;pairs=[('FLOW/GRANRODEO','FLOW、GRANRODEO'),('周杰伦','周杰伦/Jay Chou'),('其他歌手','周杰伦')];t0=time.perf_counter();[[_name_matches(c,w) for c,w in pairs] for _ in range(10000)];print((time.perf_counter()-t0)/30000*1e6)"`
本机实测 7 轮（原始输出保留两位小数）：5.48 / 6.81 / 5.53 / 5.49 / 6.65 / 5.51 / 5.50 µs →
**中位 5.51 µs，区间 5.48–6.81**（原始逐行见 `.scratch/music-multi-artist/canonical_cmd_output.txt`；
其中两次落在 6.6–6.8，本机其它任务抢 CPU，故给中位数 + 区间，不拿单次最小值当结论）。
它与上表 P5 本分支的 5.41 µs 只差约 2%：两个口径这次是一致的，
上一版报告写「两口径差 ~20%」是那组旧数字的产物，本次复测不成立。

**与上一版表格的关系**：上一版给出的 A/B 表（old 2.16/2.14/1.77/2.02/2.52 → new
2.25/8.98/4.98/6.93/6.51）**没有附脚本、无法逐行复现**；本次带脚本复跑后各项差值
≤0.6 µs，唯一明显移动的是 P5 本分支（6.51 → 5.41 µs）。本报告一律以**带脚本的
本次数字**为准。

**复跑核对（不是跑一次就下结论）**：换工作目录（`cd C:/Users/me/Desktop`）以短参数
再跑一次 —— `python D:/dsh-pet-wt-music/.scratch/music-multi-artist/ab_name_matches.py
--rounds 2 --batch 500`（输出存 `ab_rerun_2rounds.txt`）：P1 1.80/1.88、P2 2.06/8.45、
P3 1.74/5.15、P4 1.93/6.73、P5 1.99/5.50 µs（old/new）—— 与上表同量级，逐项差
≤0.28 µs，且 P1 的「差值≈噪声」结论在两次运行里都成立。

## 五、实机运行记录

本节把证据分三段：**本轮已验证**（能自己跑出来的）/ **本轮明确未验证**（不许
拿纯函数或单源结果冒充端到端）/ **上一轮观察**（保留记录，但本轮未复验）。

### 5.1 本轮已验证：真实网络取词（公开接口，走产品原函数）

探针脚本 `.scratch/music-multi-artist/probe_fetch_lyrics.py`（同时把
`_write_cache` 换成 no-op，**不写用户歌词缓存**，避免污染早间实机检查；
网络请求、解析、匹配全部是产品原逻辑）：

    cd D:/dsh-pet-wt-music
    python .scratch/music-multi-artist/probe_fetch_lyrics.py

原样输出（2026-10-16 05:10:36，本机真实网络）：

```
[log] INFO pet.music_lyric: 歌词请求直连：已绕过系统代理 http://127.0.0.1:7890
[log] WARNING pet.music_lyric: 歌词请求失败 lrclib.net（1.15s）: HTTPError: HTTP Error 404: Not Found
[log] WARNING pet.music_lyric: 歌词请求失败 lrclib.net（0.79s）: HTTPError: HTTP Error 404: Not Found
====================================================================================================
环境：是否存在系统代理配置 = True （歌词请求按设计绕过代理，见 pet/music_lyric.py::_build_opener）
时刻: 2026-10-16 05:10:36   python 3.13.7
====================================================================================================

[1] fetch_lyrics(use_cache=False) —— SMTC 形态的歌手串（酷狗实机样本）
  fetch_lyrics('Howling', 'FLOW、GRANRODEO'): Lyrics(lines=61, 前 3 行='作词 : Keigo Hayashi/Kohshi Asakawa/Kishow Taniyama / 作曲 : 飯塚\u3000昌明/浅川岳史 / Are you satisfied？')  耗时 1.22s

[2] fetch_lyrics(use_cache=False) —— 歌词源形态的歌手串（负对照）
  fetch_lyrics('Howling', 'FLOW/GRANRODEO'): Lyrics(lines=62, 前 3 行='Are you satisfied？ / Just open your eyes / You can see the light')  耗时 1.31s

[3] 三个源的单源调用（同一 title，SMTC 形态歌手串）
  _fetch_from_qq('Howling', 'FLOW、GRANRODEO'): Lyrics(lines=66, 前 3 行='Howling - FLOW (フロウ)/GRANRODEO / 词：Kohshi Asakawa/eigo Hayashi/Kisho Taniyama / 曲：Takeshi Asakawa/Masaaki Iizuka')  耗时 1.97s
  _fetch_from_lrclib('Howling', 'FLOW、GRANRODEO'): None（无结果）  耗时 0.79s
  _fetch_from_netease('Howling', 'FLOW、GRANRODEO'): Lyrics(lines=61, 前 3 行='作词 : Keigo Hayashi/Kohshi Asakawa/Kishow Taniyama / 作曲 : 飯塚\u3000昌明/浅川岳史 / Are you satisfied？')  耗时 0.45s

[4] 网易云真实候选逐条判定（同一请求形态，走产品的 _http_get_json）
  候选数 = 10（查询串 = Howling%20FLOW%E3%80%81GRANRODEO）
     1. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling'
     2. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling'
     3. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling -TV Size-'
     4. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='GLOW'
     5. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling (Instrumental)'
     6. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling'
     7. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling -TV Size-'
     8. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling'
     9. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling -TV Size-'
    10. 歌手串='FLOW/GRANRODEO'  基线=False  本分支=True  歌名='Howling -Instrumental-'

完成。
```

读数（全部是本轮真实网络往返）：

- `fetch_lyrics("Howling", "FLOW、GRANRODEO", use_cache=False)` = **61 行 LRC，1.22s**
  （`use_cache=False` 强制走网络，不是缓存命中）；负对照 `"FLOW/GRANRODEO"` = 62 行，1.31s。
- 单源：网易云 61 行 / 0.45s 命中，QQ 66 行 / 1.97s 命中，lrclib 404（None）。
- **候选侧机制在活数据上复现**：网易云返回 10 条候选，歌手串全部是 `FLOW/GRANRODEO`；
  基线实现 **10/10 判 False**（这正是「搜索到 10 个候选但无人匹配歌手」warning 的
  来源，也是修复前丢词的原因），本分支 **10/10 判 True**。
- 环境：本机存在系统代理（`127.0.0.1:7890`，本地回环）；歌词请求按设计直连
  （日志 `歌词请求直连：已绕过系统代理`），与 `docs/NETWORK-PROXY-AND-VPN-2026-09-22.md`
  一致。本次三源耗时均在 2s 内，没有出现该文档里 20–41s 的代理绕行故障。

### 5.2 本轮**未**验证（不得当作已闭环）

- **GUI 端到端未验证**：本轮没有启动桌宠、没有截图、没有操控任何播放器（红线：
  不操控音乐播放器 / 不调 CU）。因此「桌宠窗口上真的显示了这几行歌词」这一条
  **没有证据**，本报告不给结论——截图由用户明早实机检。
- **SMTC 侧未复验**：本轮 `get_now_playing()` 返回 `None`（`.scratch/music-multi-artist/
  probe_get_now_playing_output.txt`：`elapsed 0.20s` / `None（没有在播会话）`），
  `tasklist` 里也没有酷狗/汽水/网易云进程在跑。所以「酷狗 SMTC 报出的是
  `FLOW、GRANRODEO`」这条**本轮无法复验**，它是上一轮的实机观察（见 5.3），
  本轮只把它当作探针输入使用。
- **旧日志检索结论**：在 `D:/dsh-pet-src-wt-release/.scratch` 只读检索过
  `music|lyric|歌词|酷狗|汽水|Granrodeo|Howling`，命中的全是**源码副本**与发布清单
  里的待办项（例：`product-close-approved-candidate-20261011/REPORT.md:157` 把
  「歌词真实播放器」列为待跑项；`product-final-fix-events-20261010/04-related-b.txt`
  记录的是一次三源全超时的失败现场）。**没有任何本次多歌手场景的实机闭环日志**，
  故不引用为证据。

### 5.3 上一轮观察（2026-10-15 会话，本轮未复验，仅作记录）

- 汽水音乐在播《爱要怎么说出口(R&B女生版)》/ 七分可可：`get_now_playing()`
  直接返回结构化曲目（`app_id='汽水音乐'`，时间轴完整）；网易云源命中完整 LRC。
- 酷狗在播 Howling / `FLOW、GRANRODEO`：修复前取词失败（候选 10 条无人匹配），
  修复后 `_name_matches('FLOW/GRANRODEO', 'FLOW、GRANRODEO') = True`（回归测试锁住）。
- 设置页文案改动已跑 copy lint（`test_settings_copy_lint.py` 绿）。
- 酷狗的 SMTC 开关（它自己设置里的「支持系统播放控件」）当时已开；未开时的行为 =
  读不到会话（既有行为，文案已指引）。

## 六、验证

本轮返修**产品逻辑一行未改**（`git diff --stat 99bdc7f` 仍是 6 个文件——实现 3
（`pet/music_lyric.py`、`pet/modern_settings_dialog.py`、`pet/music_title.py`）、
测试 1、文档 2）。本轮改动只有三类：①`tests/test_music_lyric.py` 累计补 3 条左词
边界反例（+7 行，配本节消融可证）；②`pet/music_title.py`（+4/−2）、
`pet/music_lyric.py:338`（1 行注释）与本测试文件 `:2177` 的陈旧/草稿注释同步；
③`docs/INDEX.md`（+1/−0）按新文档入场规则登记 + 本报告的取证返修。产品文件里只有
注释与 docstring 变动，函数体、正则、断言值一字未动；终版 `git diff --numstat
99bdc7f` 的逐行数字见 §二 三张表。故按「注释/文档改动」的门跑：doc 门 + 音乐族相关
测试 + ruff。全量套件留给合并门。

- **doc 门**：`QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:randomly
  tests/test_pr_report_discipline.py` → **153 passed**（2026-10-16 本轮重跑两次：06:23
  一次 2.14s、报告内容改定后同一命令再跑一次，均全绿；校验本报告有四个必备章节、且已在 `docs/INDEX.md:144` 登记）。
- **音乐族 + 设置文案 lint**：`QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:randomly`
  tests/test_music_lyric.py tests/test_lyric_sources.py tests/test_music_title.py
  tests/test_music_detect.py tests/test_music_player_cache.py tests/test_music_player_settings.py
  tests/test_music_sing_grace.py tests/test_music_sing_timer.py tests/test_overlay_music_sing.py
  tests/test_settings_copy_lint.py → **209 passed, 0 failed in 17.58s**
  （2026-10-16 06:23 本轮返修后重跑，与 05:11 那次的 209 passed / 17.21s 同值）。
  按文件凑数（`--collect-only`）：`test_music_lyric.py` 107、`test_music_title.py` 24、
  `test_music_player_settings.py` 19、`test_music_player_cache.py` 17、`test_lyric_sources.py` 17、
  `test_overlay_music_sing.py` 8、`test_music_sing_timer.py` 6、`test_music_sing_grace.py` 6、
  `test_settings_copy_lint.py` 4、`test_music_detect.py` 1。
- **红→绿（真跑）**：`set PYTHONPATH=.scratch/music-multi-artist` 后
  `python -m pytest -q -p no:randomly -p baseline_impl tests/test_music_lyric.py -k name_matches`
  → **3 failed, 4 passed, 100 deselected**（2026-10-16 06:23 本轮返修后重跑复核，同值），`test_name_matches_multi_artist_separator_variants` 的首条
  失败断言是 `tests/test_music_lyric.py:2154` 的
  `assert music_lyric._name_matches("FLOW/GRANRODEO", "FLOW、GRANRODEO")`（基线实现
  返回 False）；去掉插件（本分支实现）后同一批**全绿**。插件只做内存替换
  （`ml._name_matches = _baseline`），不改任何文件。
- **§三 两条断言的复验**：`python .scratch/music-multi-artist/verify_name_matches_claims.py`
  → 输出见 §三（`_name_matches("A","Aimer、B")` = True 且与基线同值；1 字符段命中
  `'b' == 'b'`）。上一版报告的两条描述由此判定为**不实并已改正**。
- **词边界反例的消融验证（真跑 pytest，不是"应该会红"）**：在内存里替换
  `music_lyric._ARTIST_SEP_RE`（**不改文件**），用 pytest 插件方式重跑同一测试文件：

      set PYTHONPATH=.scratch/music-multi-artist && set QT_QPA_PLATFORM=offscreen
      python -m pytest -q -p no:randomly                              tests/test_music_lyric.py
      python -m pytest -q -p no:randomly -p ablate_left  tests/test_music_lyric.py
      python -m pytest -q -p no:randomly -p ablate_right tests/test_music_lyric.py
      python -m pytest -q -p no:randomly -p ablate_both  tests/test_music_lyric.py

  实测结果：基线 **107 passed**；去**左** `\b`（`feat\b\.?|ft\b\.?`）→
  `1 failed, 106 passed`，红在 `assert not music_lyric._name_matches("Daft Punk", "Da、Punk")`
  （新增三条反例里的第一条）；去**右** `\b` → 红在 `assert not
  music_lyric._name_matches("Featherstone/Alpha", "Herstone、Beta")`；两侧都去 → 红。
  同一批用例在四种正则下的真值表（六条负例：Featherstone / FTIsland / Daft Punk /
  Swift Lefty / Soft Cell + 一条正例 `FLOW feat. GRANRODEO` × `FLOW、GRANRODEO`）：

  | 正则 | Featherstone | FTIsland | Daft Punk | Swift Lefty | Soft Cell | feat 正例 |
  |---|---|---|---|---|---|---|
  | 基线（两侧都有 `\b`） | False | False | False | False | False | True |
  | 去左 `\b` | False | False | **True** | **True** | **True** | True |
  | 去右 `\b` | **True** | **True** | False | False | False | True |
  | 两侧都去 | **True** | **True** | **True** | **True** | **True** | True |

  即左/右边界分别都有实测咬合的断言，不是"写了但测不出"。上面四条命令在
  2026-10-16 06:23（本轮返修后）重跑复核：基线 `107 passed`，三种去边界正则各
  `1 failed, 106 passed`，红点与上表逐条同值。
- **ruff**：`ruff check pet/music_lyric.py pet/music_title.py tests/test_music_lyric.py
  .scratch/music-multi-artist/` → **All checks passed!**（2026-10-16 06:23 本轮返修后
  重跑，含本报告里两个被改过列名的 `.scratch` 脚本/存档）。
- 全量套件结果见 PR 描述（本报告的改动不影响产品行为，见本节首段）。
