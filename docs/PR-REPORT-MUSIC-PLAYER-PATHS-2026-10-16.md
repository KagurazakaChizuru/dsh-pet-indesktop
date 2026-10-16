# 四播放器启动入口与播放器路径 — 交付证据（`feat/music-player-paths`）

> **基线**：`0b7152d654b1263b1dda7b490eb9483c71652abf`（`fix(screen-capture): 固定品牌图标规则并隔离跨截图异步结果 (#278)`）+ 本分支提交——本报告描述的改动已提交在 `feat/music-player-paths` 并开出 PR（提交号与 PR 链接见 GitHub），**没有构建、没有发布**。
> **分支**：`feat/music-player-paths`　**日期**：2026-10-16
> **范围**：16 个受版本控制的文件（实现 7、测试 8、文档 1）+ 1 个新增测试文件 = `+2338 / −91`（`git diff --numstat`，未含本报告与两份登记文档）。另有同批文档登记：`docs/INDEX.md`、`docs/SETTINGS-CHANGE-GATES.md`、本报告（新增）。
> **关联**：[`PR-REPORT-MUSIC-MULTI-ARTIST-2026-10-15.md`](PR-REPORT-MUSIC-MULTI-ARTIST-2026-10-15.md)（**取词侧**；本报告是**启动入口与路径侧**）、[`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 2026-10-16 条目、[`PR-REPORT-SETTINGS-POLISH-2026-10-16.md`](PR-REPORT-SETTINGS-POLISH-2026-10-16.md)（同日设置页呈现层批次）。
>
> **本报告与改动的关系**：产品与 `tests/` 的改动由本批前序执行方落在工作树。本报告由**取证方**撰写，取证过程中**未改产品、未改测试**，唯一例外是按明确许可在 `pet/app.py:443` 的 docstring 补了一段注释（写明启动预热仍只覆盖原两键，**预热循环一行未动**）。

## 〇、版本记账与验证状态（先看这里）

审查期间同机还有其他执行方在改文件，故本报告按修订版记账。**本批的实现与测试文件自 `pet/settings_music.py = 4ee92b8872f009b8`、`pet/music_players.py = 2e57ee9aac7c8294` 起未再变动**；`README.md` 在 14:17 又改过一次措辞（增删行数不变），下表已换成现值；`full-final-ready.log` 那次全量跑在全部文件最后一次改动（14:18:31）**之后**，因此它测的就是下表这一棵树：

| 文件 | 增删 | sha256[:16] | 文件 | 增删 | sha256[:16] |
|---|---|---|---|---|---|
| `pet/music_players.py` | +185 / −5 | `2e57ee9aac7c8294` | `tests/test_music_player_settings.py` | +398 / −35 | `aa9e043bd062493b` |
| `pet/settings_music.py` | +218 / −34 | `4ee92b8872f009b8` | `tests/test_music_player_cache.py` | +359 / −4 | `b2be2e019a9b4676` |
| `pet/config.py` | +9 / −7 | `fb05821ea073fb58` | `tests/test_music_player_detect_refresh.py`（**新文件** 631 行） | +631 / −0 | `dfdd5ec6d810ea6d` |
| `pet/context_menus/registry.py` | +11 / −1 | `961b30bbefeeabf7` | `tests/test_menu_layout.py` | +380 / −0 | `9fc4179fbe4d4123` |
| `pet/context_menus/shared.py` | +13 / −1 | `26836e3595e6e740` | `tests/test_config_schema.py` | +81 / −0 | `7449eb4f1305cf82` |
| `pet/menu_templates/modern-default-v1.json` | +3 / −1 | `1c671c5c21b50779` | `tests/test_sprite_menu_parity.py` | +26 / −0 | `f2a2e13f04080d83` |
| `pet/app.py`（**仅注释**） | +8 / −1 | `4c05b12f67ad944d` | `tests/test_settings_pet_tabs.py` | +4 / −1 | `c7829e76ad930dad` |
| `README.md` | +10 / −1 | `6ed3bc556e6f9ffe` | `tests/test_settings_ia_first_cut.py` | +2 / −0 | `39ac74158780bc56` |

**验证状态（如实）**：

- 本批改动**自身**的门：ruff 全绿、聚焦 **327 passed**（含新增测试文件）、架构红线在全量与受影响族里通过。
- **全量已出结论（最终）**：`7792 passed / 15 skipped / 0 failed`，`exit 0`，用时 1444.40s（`full-final-ready.log`，命令见 §六）——测的就是上表这一棵树。
- 历史（**已被上一条替代，仅留档**）：修订 A 的全量 `1 failed / 7767 passed / 15 skipped`，唯一红是**另一条线**的计时 flake；修订 B 的全量在 74% 处随会话退出被杀（`full-final2.log`），无 summary，当时不能当证据。两者都**不是**当前结论。
- 与本批无关但在同期变化的：`tests/test_flight_frame_pacing.py`（+134 / −33，`16f50c5232b4c014`）由另一条线改成**同事件循环配对判据**（产品 clip vs 旧写入语义对照 clip，外加写入倒计时见证）。**仅测试改动，产品代码未动**；该线的独立 review 通过，且 mutation（把写入语义改回旧两行）能抓回旧缺陷。

## 一、核心特性

用户点名的缺口是「按播放器名字找不到能放歌的入口、填了路径也不生效」，根因是**「有哪些播放器」有三份各自写死的两键名单**（`music_players.PLAYERS`、`settings_music.PLAYER_KEYS`、`config._clean_music_player_paths`），酷狗 / 汽水**不在任何一份里**。本批把「有哪些播放器」收成一处真源，并把入口、设置页、配置清洗都挂上去；第二轮又收口了检测链路上的三处真实缺陷。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 注册表扩到四个播放器 | `PLAYERS` 新增酷狗（`KuGou.exe`）、汽水（`SodaMusic.exe`），`player_keys()` 成为消费方取键的唯一入口 |
| 2 | 右键菜单四条启动入口 | 音乐子菜单从两条扩到四条（网易云 / QQ音乐 / 酷狗 / 汽水），四键**共用**同一 builder 与同一启动 worker，只有 `player_key` 不同 |
| 3 | 设置页四个路径行 + 自动检测 | 行键 / 控件属性名由注册表派生（注册表加播放器不会再漏建行）；检测预算按播放器数放大（20s → 80s） |
| 4 | 配置清洗跟随注册表 | `music_player_paths` 键集 = 注册表键集（**同一个字典键、不新增配置格式**），酷狗 / 汽水手填的路径不再被 `Config()` / `reload()` 静默丢弃 |
| 5 | 版本化安装目录挑「当前」那一份 | 汽水装在 `…\Programs\Soda Music\<版本>\SodaMusic.exe`。原实现取 `iterdir` 首个命中——升级后旧版本目录不会删，**可能启动旧版**；现按三级次序：安装目录下的 exe → 安装器描述 `launcher_config.json` 的 `cur_path`（本机实测 `{"app_name":"SodaMusic","cur_path":"3.7.0"}`）→ **数字版本降序**（`3.10` > `3.7`，字符串比会反过来） |
| 6 | 点「自动检测」是真的重扫 | `warm_cache_async` 幂等：缓存里已有值（含上次的 `None` 负结果）时**根本不扫盘**，于是「装好播放器 → 点检测 → 还是未找到」，唯一出路是重启；现在先 `clear_cache()` 作废旧结果再预热 |
| 7 | 检测期不盖手填、超时不说「没有」 | 只回填「检测开始到现在文本未变过」的行；仍冷 / 超时的格子报**未完成**而不是**未找到**；补扫每键每轮有上界（2 次），耗尽后不承诺后台还有线程；**GUI 线程零扫盘** |
| 8 | 文案写明「路径 ≠ 歌词」 | 设置页每行、检测行与 README 用户入口都写明：这些路径只影响右键菜单的启动入口，歌词走**系统媒体会话**、与本路径无关 |

**红线 / 不变量**：启动预热仍只覆盖 `netease`/`qqmusic` 两键（`pet/app.py` 循环一行未动，有断言钉住）；手填路径是权威、**绝不静默回退自动搜索**；检测是纯本地有界查找（不联网 / 不读注册表 / 不起进程，`_MAX_DEPTH=3`、候选根 ≤ 8、版本目录枚举 ≤ 64 条、安装描述 ≤ 64 KB）；`cur_path` 按**不可信输入**校验（拒绝绝对路径、盘符、UNC、`..`、`:`、控制字符、尾随空格点）；歌词链路一行未动。

## 二、修改文件说明

增删行数取自 `git diff --numstat HEAD`；sha256 见 §〇。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/music_players.py` | +185 / −5 | ① `PLAYERS` 两键 → 四键（含中文目录名、带空格的 `Soda Music`），新增 `player_keys()`；② `_VERSIONED_INSTALL_DIRS` + `_search_versioned_install()` 表达「程序在版本号子目录里」，并**按确定性次序挑当前那一份**：`_launcher_current_install()`（读安装描述取 `cur_path`）→ `_newest_versioned_child()`（`_numeric_version()` 降序）；③ `_relative_dir_within()` 把 `cur_path` 收成安装目录内的相对目录；④ 上界常量（条目 64 / 描述 64 KB / `cur_path` 256 字符 / 版本名 32 字符）。为什么：原实现取 `iterdir` 首个命中，升级后可能启动旧版；写死版本号会随升级失效，放宽递归深度会把浅扫变全盘扫。 |
| `pet/settings_music.py` | +218 / −34 | ① `PLAYER_KEYS` 由写死两键改为 `player_keys()`，`_PICKER_ATTR`/`_ROW_KEY` 由键派生；② 行文案抽成 `_player_row_hint()`、检测文案 `_DETECT_ROW_HINT`（写明「每次点击重新搜、会覆盖原有内容、检测期间你改过的行会保留」与「路径 ≠ 歌词」）；③ 检测预算 = `DETECT_TIMEOUT_PER_PLAYER_SECONDS (20s) × len(PLAYER_KEYS)`；④ `start_detect` 先 `clear_cache()` 再预热，并记下每行起始文本；⑤ `poll_detect` 区分 `CACHED_COLD`（未完成）与 `CACHED_MISSING`（没找到），对仍冷格子 `_rescan_cold_player()` 补扫（每键每轮上界 2）；⑥ `_apply_detected_paths()` 只回填文本未变过的行；⑦ `_report_results()` 三种结局分别措辞（找到 / 未找到 / 未完成，并说明替换或保留了谁）。 |
| `pet/config.py` | +9 / −7 | `_clean_music_player_paths` 键集从写死两键改为遍历 `PLAYERS`（另同步三处注释）。为什么：清洗白名单是「手改 `config.json` 会不会被静默丢弃」的唯一开关，只认两键时酷狗 / 汽水手填路径被丢掉——**填了等于没填**。**不新增配置格式**。 |
| `pet/context_menus/shared.py` | +13 / −1 | 新增 `add_music_open_kugou` / `add_music_open_soda` 两个转发，复用既有 `_music_player_builder(key)`；docstring 改为四播放器并写明五条语义（路径解析 / 冷缓存乐观启用 / 后台预热 / 负缓存置灰 / 手填失效提示）都由这里一次性给出。为什么：语义必须同源，新键各写一遍会各自漂移。 |
| `pet/context_menus/registry.py` | +11 / −1 | 注册 `music_open_kugou` / `music_open_soda`（标签「打开酷狗音乐并播放」「打开汽水音乐并播放」、图标 `play`、可用性恒 `True`）。为什么恒 `True`：符合 `CONTEXT.md` 的 **Runtime Disabled**——保留入口位置、运行期置灰并解释原因。 |
| `pet/menu_templates/modern-default-v1.json` | +3 / −1 | 默认布局树音乐子菜单补两个 action 节点。为什么：菜单是「注册表 + 用户编排」，动作注册了但默认树没节点，新装用户看不到入口；存量用户旧布局走既有补入机制。 |
| `pet/app.py` | +8 / −1 | **仅注释、行为零变化**：`_warm_music_player_paths` docstring 写明「启动只预热两键」，后补的酷狗 / 汽水由首次菜单构建（或设置页检测）的幂等预热补齐，并给出理由（四条串行浅扫 20s+，不该压启动路径）。**预热循环一行未动**。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_music_player_settings.py` | +398 / −35 | 键集与注册表一致、每个注册播放器都有自己的 picker / 行 / 标签、行序 = 注册表序且检测行在最后、四行 + 检测行同属高级组、按用户会输入的名字都能搜到、四行文案都写明「路径只驱动右键菜单启动」、四键保存与重开回填、部分配置只填对应 picker、坏值不炸且四框留空、非法路径原样保留并提示找不到、纯空白等同留空、无 Chat 变体同样能建能存、路径行不做平台门、检测结果弹窗逐个列出（含全没找到）、预算覆盖每个串行扫描且由 `PLAYER_KEYS` 派生 |
| `tests/test_music_player_cache.py` | +359 / −4 | 注册表四键与 exe 名 / 目录名登记齐全；真实安装布局命中（含 `…/Programs/Soda Music/3.7.0/`）；exe 名不符不算命中；版本探测只对登记布局生效；**版本挑选**：`cur_path` 压过更"新"的兄弟目录（含 `./3.7.0`、`3.7.0/`、`3.7.0//`）、无描述时数字降序（`3.10` > `3.7`）、越界 / 破损 / 超大描述回退排序、枚举有上界、`_numeric_version` 边界、登记表不许超出播放器注册表；检测纯本地有界；四键同规（手填命中即用、失效返回 None 且不扫盘不回退） |
| `tests/test_music_player_detect_refresh.py`（**新文件** 631 行） | +631 / −0 | 检测第二轮契约：显式重扫作废旧负缓存；检测期不覆盖用户手填且结果里说明；在飞扫描相容、结果被清掉后补扫且不伪造值、失败补扫有上界、耗尽后报「未完成」不承诺有线程；超时区分未完成与没找到；检测期间 GUI 线程零扫盘；键集漂移护栏 |
| `tests/test_menu_layout.py` | +380 / −0 | 默认布局注册并摆好每个已知播放器、新条目点击路由到**自己的 key** 且走共享 worker、文案跟随注册表、冷缓存四条都乐观启用各预热一次、预热在途仍启用且幂等、负缓存置灰并给设置页指引、手填路径权威、已保存布局会补入新条目；默认布局期望补两键 |
| `tests/test_config_schema.py` | +81 / −0 | 四键路径可存（构造 + `reload()`）、清洗键集 = 注册表键集、表外键照旧丢弃而旧两键不丢、四键写盘重启后仍是四键且空串 / 未知键不落盘 |
| `tests/test_sprite_menu_parity.py` | +26 / −0 | overlay 侧音乐子菜单四条启动入口，文案逐键按注册表核对、无重复 |
| `tests/test_settings_pet_tabs.py` / `tests/test_settings_ia_first_cut.py` | +4 / −1、+2 / −0 | 高级行期望清单补两行 |

### 文档

`README.md`（+10 / −1）：发布状态登记本轮候选改动；「功能概览」新增「音乐播放器入口与路径（Windows）」一节（四个入口、置灰并写明原因、路径只在启动入口生效、检测每次重搜且不盖手改、**歌词不显示时改路径没有用**），全篇不声称已发布。`docs/INDEX.md`（+3 / −2）：登记本报告并按新文档入场规则互链、更新两行「何时必读」。`docs/SETTINGS-CHANGE-GATES.md`：新增 2026-10-16 变更记录（键集 / 行键 / 披露层级 / 默认值 / 平台可见性 / 保存语义 / 文案 / 检测交互语义 / 检测预算 + 准出对应）。

### 未改动（看起来相关但故意没动）

`pet/now_playing.py`、`pet/music_lyric*.py`、`pet/music_title.py`（歌词链路，本批一行未动）；`pet/menu_layout.py`（新动作走既有补入 / 置灰机制）；`pet/settings_pet_controls.py`、`pet/modern_settings_dialog.py`（picker 与行本就在 `settings_music` 里建，`modern_settings_dialog.py:358` 一行调用）；`pet/settings_slot_config.py` 与 `PER_SLOT_SETTING_KEYS`（四个键都是进程级，路由语义未变）。

## 三、实现要点

- **一处真源**：`PLAYERS` + `player_keys()`，菜单动作、设置页行、配置清洗全部由它派生；漂移由三条用例盯着（键集相等、行序 = 注册表序、菜单四条入口文案逐键核对）。
- **版本目录的三级确定性挑选**：`安装目录下的 exe` → `launcher_config.json 的 cur_path` → `数字版本降序`。前两级都要求目标真有 exe；第三级用 `_numeric_version()` 分段比整数。**为什么不能只靠枚举**：升级后旧版本目录不会删，`iterdir` 先给谁不是承诺。
- **`cur_path` 按不可信输入处理**：只接受安装目录内的相对目录；挑版本目录不能变成「照配置文件读任意路径」。
- **检测状态机**：记起始文本 → `clear_cache()` → 四键幂等预热 → 300ms 轮询（找到 / 没找到 / 未完成 + 有界补扫）→ 全部落定或到 80s 预算收尾 → 只回填文本未变过的行 → 按三种结局措辞。GUI 线程只读缓存。
- **手填路径是权威**：命中即用，不存在则 `None` + 负缓存 → 菜单置灰并提示去设置页，不回退自动搜索。

## 四、性能分析

**方法**（本机真实文件系统，只读，不启动播放器、不改配置）：`python .scratch/music-player-paths/probe_cost_and_threads.py`（`cost-and-threads-b.log`）、`probe_detect_cost.py`（`detect-cost-b.log`）、`probe_detect_e2e.py`（`e2e-detect-b.log`）。环境：Windows / Python 3.13.7 / PySide6 6.11.2 / 16 逻辑核。**测量时同机有其他执行方的测试轮次在跑**，绝对值偏保守。

| 指标 | 实测 | 归属 |
|---|---|---|
| `_clean_music_player_paths` 两键 → 四键 | 0.88 → **1.04 µs**/次（**+0.16**，n=20000×5）；四键 + 2 个表外键 1.00 µs | 既有热路径（`Config()` 构造与每次 `reload()` 各一次）＋新增两个键的遍历 |
| `_search_versioned_install` 六条候选根合计（真实盘找汽水） | 中位 **2147.7 µs**/次（n=200×5）；命中那把（`%LOCALAPPDATA%`）**367 µs** | 新增路径；每 key 每次冷扫最多一次 |
| 其中：读安装描述取 `cur_path` / 数字版本排序 | **449.8 µs** / **1023.6 µs**（n=500×5） | 新增；命中 `cur_path` 时不会走到排序那级 |
| 未登记版本布局的 key（酷狗） | **0.163 µs**/次（n=20000） | 新增（一次 dict 未命中即返回） |
| `clear_cache()`（点检测先作废旧结果） | **0.08 µs**/次（n=5000×5） | 新增调用点 |
| 逐键冷扫（真实盘、串行） | 网易云 **0.36s** / QQ音乐 **19.65s** / 酷狗 **13.95s** / 汽水 **16.19s** | 既有机制，多了两个 key |
| 「自动检测」端到端（四键串行） | 首结果 **0.36s**，四键齐 **24.50s**；预算 **80s**；真实设置窗点一次实测 **23.90s** | 预算由写死 20s 改为按播放器数派生 |
| 登记四键后台预热 | **100.0 ms**（同机争用时）/ 轻载 **1.575 ms** | 新增（两个线程登记） |
| 新增线程 | `music-player-warm-{netease,qqmusic,kugou,soda}`，全 **daemon**；四键离开冷缓存后**残留 0** | 沿用既有预热线程工厂 |
| 内存 | `_cache` dict 184 B + 4 条（172/127/151/48 B）≈ **0.7 KB**；`PLAYERS` 184 B、`_VERSIONED_INSTALL_DIRS` 184 B | 新增（两个键位 + 两张常量表） |

**逐条回答**：① **稳态开销**：菜单侧零变化（仍只读缓存，条目 2→4 只是多两次字典查找）；配置面每次构造 / `reload()` 多 **0.16 µs**；检测面只在冷扫里多一次版本目录探测（六根 2.15 ms，未登记 key 0.163 µs）。② **新增路径成本与频率**：版本目录探测 2.15 ms/次，只在该 key 冷扫且命中已知安装目录时发生，缓存暖后为 0；设置页检测一次点击端到端 24.5s（真实窗口 23.90s），是用户主动点一次的动作，出齐即收尾。③ **新系统调用 / 网络 / 磁盘 / 线程**：网络、注册表、子进程没有（由导入面用例机器化禁止）；磁盘只多**登记安装目录的 `is_dir` / `iterdir` 与一次安装描述读取**（64 条 / 64 KB 上界）；线程多两个 daemon，跑完即退。④ **内存**：缓存 2 → 4 条（≈ +0.35 KB）、常量两表 368 B，无单调增长（有界字典 + 有界补扫）。

## 五、实机运行记录

本机真实环境：Windows / Python 3.13.7 / 真实 `windows` 平台插件（**不是 offscreen、不是 mock**）。

**1）真实设置窗 + 真实「自动检测」按钮 + 真实文件系统**（`probe_detect_e2e.py`，唯一替换是弹窗记录器与临时配置目录）：

```
elapsed=23.90s (预算 80s)   button=自动检测 enabled=True   timer_active=False
picker[netease]='D:\\下载文件\\CloudMusic\\cloudmusic.exe'   picker[qqmusic]=''
picker[kugou]='C:\\Program Files\\KuGou\\KGMusic\\KuGou.exe'
picker[soda]='C:\\Users\\me\\AppData\\Local\\Programs\\Soda Music\\3.7.0\\SodaMusic.exe'
--- 弹窗原文 ---
网易云音乐：D:\下载文件\CloudMusic\cloudmusic.exe / QQ音乐：未找到
酷狗音乐：C:\Program Files\KuGou\KGMusic\KuGou.exe
汽水音乐：C:\Users\me\AppData\Local\Programs\Soda Music\3.7.0\SodaMusic.exe
没找到的可以点右侧「选择…」手动指定程序位置。
```

**三路径命中、QQ 缺失且已独立复核**：`cloudmusic.exe` / `KuGou.exe` / `SodaMusic.exe` 本机 `stat` 均存在（2634744 / 475616 / 2441592 字节）；QQ音乐候选位置确实不存在（`C:\Program Files\Tencent` 下只有 `QQNT` / `Weixin` / `Yuanbao`，`Program Files` 深度 4 与 `D:\` 深度 3 搜 `QQMusic.exe` 零命中）。四键里只有它置灰——**真实的失败路径观察，不是缺陷**。

**2）版本目录挑选的真实前提**：`C:\Users\me\AppData\Local\Programs\Soda Music` 真实存在，其中 `launcher_config.json` 含 `"cur_path": "3.7.0"`，按该描述挑出的正是本机在用的 `3.7.0\SodaMusic.exe`。越界输入现场实测全部被拒（`'../..'`、`'C:/Windows'`、`'.. '`、含控制字符 → None；`'3.7.0'` → 接受）。

**3）逐键冷扫**：`netease 0.36s / qqmusic 19.65s / kugou 13.95s / soda 16.19s`；四键齐 24.50s（预算 80s）。

**4）设置页几何与截图**（`capture_player_rows.py`，三档场景）：四行 + 检测行全部 `hint_clipped=False`、`inside=True`、`h_scroll_visible=False`（900×760 明 / 暗：行高 45 px；720×500 + 1.5 倍字体：60 px）。截图 3 张在 `.scratch/music-player-paths/shots/`，几何原文 `geometry.txt`。**这批几何/截图取自较早修订**（行数与行高未变，检测行说明文案改过），**截图由父级复核**，本报告只登记路径与数字。

**5）未实测（如实登记）**：
- 用户 GUI 点击「打开酷狗/汽水给主人放歌」→ 播放器真的起来：**没做**。真机点验会启动用户自己的播放器并放歌（不可逆、打断用户正在听的歌），本轮不操作用户播放器。链路证据止于「条目在真实菜单树里存在且启用 + worker 解析出真实存在的 exe 路径」。
- 真实桌面会话里手点「自动检测」也没做：探针点过（§五.1），但那不是人在真实会话里操作。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | **All checks passed!** |
| 聚焦（8 个改动/新增测试文件） | `QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:randomly tests/test_music_player_settings.py tests/test_music_player_detect_refresh.py tests/test_music_player_cache.py tests/test_menu_layout.py tests/test_config_schema.py tests/test_settings_ia_first_cut.py tests/test_settings_pet_tabs.py tests/test_sprite_menu_parity.py` | **327 passed in 123.34s**（`focused-final-b.log`；更早一版为 269 passed，`focused-final.log`） |
| 受 `pet/app.py` 注释影响的族 | `… tests/test_music_player_cache.py tests/test_architecture.py` | 45 passed（`affected-after-app-comment.log`；`test_music_player_cache` 会 `inspect.getsource(pet/app.py)`） |
| 文档门 | `… tests/test_pr_report_discipline.py tests/test_desktop_pet_features.py::test_product_copy_has_no_external_brand_reference` | 160 passed（`docs-gate.log`）；**全部文档编辑完成后的最后一次**加上 `tests/test_requested_regressions.py` 一起跑 = **215 passed / 1 skipped** |
| **全量（当前修订，最终）** | `QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:randomly` | **7792 passed / 15 skipped / 0 failed**（日志末行逐字：`7792 passed, 15 skipped, 3120 warnings in 1444.40s (0:24:04)`，无 failed/error ⇒ 退出码 0；`full-final-ready.log`）。该次跑在全部文件最后一次改动（14:18:31）之后、14:22 起 —— 与本报告上表那棵树一致。此后只做过**纯文档**编辑（本报告与 `docs/INDEX.md`、`docs/SETTINGS-CHANGE-GATES.md` 的定稿文字），产品与测试文件一字未动；文档门随后重跑 = **324 passed / 1 skipped** |
| 全量（修订 A，**已被替代**） | 同上 | **1 failed / 7767 passed / 15 skipped**（1792.44s，`full-final.log`）；唯一红是另一条线的计时 flake，见下 |
| 全量（修订 B，**已被替代 / 无效**） | 同上 | 在 **74% 处随会话退出被杀**（`full-final2.log`），无 summary；且它是在另一条线**重写 `tests/test_flight_frame_pacing.py`（13:30:38）期间**跑的，**不作为证据** |
| 架构红线 | `tests/test_architecture.py` | 通过 |

**关于修订 A 那唯一一条红（历史，**已被上表的最终全量取代**，此处保留现场）**：`tests/test_flight_frame_pacing.py::test_flight_speed_writes_do_not_starve_frame_delivery` 失败信息是 `41 帧（无截断应 44`——门槛 41.297，**差 0.3 帧**。当时在工作树单跑 16 次 8 红，在 **HEAD 纯净副本**（`git archive HEAD pet tests pytest.ini` → `.scratch/baseline-tree/`，不含本批任何改动）单跑 16 次 9 红、失败信息逐字相同 ⇒ 与本批无因果。该文件随后由 **agent1133** 改成**同事件循环配对判据**（现 `test_flight_frame_pacing.py` = `16f50c5232b4c014`，+134 / −33：产品 clip 与嵌入旧写入语义的对照 clip 在同一循环、同一素材、同一速度剖面上配对，判据取两臂差值，外加写入处的确定性倒计时见证），**仅测试改动、产品代码未动**；该线的独立 review 通过，且 mutation（把写入语义改回旧两行）能抓回旧缺陷。改后本机连跑 4 遍均 `5 passed`；本报告定稿后又与 `tests/test_music_player_detect_refresh.py` 合跑一次 = **16 passed**；**本批不代改他人测试**。

## 七、已知限制与后续

1. **全量已收口**（§〇/§六）：`7792 passed / 15 skipped / 0 failed`（`full-final-ready.log`）；本报告更早版本里「当前修订的完整全量未出结论 / 待验」的说法已被本条取代，不要再引用那个口径。
2. **用户 GUI 点验没做**（点「打开…给主人放歌」→ 播放器真的启动并放歌）、**真实会话里手点「自动检测」也没做**：原因见 §五.5。
3. **QQ音乐在本机没装**：四键里只有它置灰；用户机器上装在别处时，用设置页手填（本次已可用）。
4. **版本目录挑选的登记面只覆盖汽水**：将来别的播放器也用「版本号子目录 + 安装器描述」布局时照同样方式登记；**刻意不写死版本号、不放宽全局递归深度**。
5. **启动预热只覆盖原两键（沿用既有契约）**：酷狗 / 汽水首次要等一次菜单构建后的后台扫描（本机 6~14s）才从冷缓存转 found 态，期间菜单乐观启用。要不要扩到四键需另立决定（会拖慢首屏）。
6. **置灰 tooltip 的导航层级差一层**：提示写「设置 → 桌宠 → 音乐关联」，而四行在「显示与音乐」标签页下的高级折叠组「播放器路径与标题格式（高级）」里——组名真实存在，不是错路，但要再展开一层。本批未改这行产品文案。
7. **条目文案有两个来源**（`registry.ACTION_LABELS` 与 builder 的运行期条款），没有单一常量；用例只覆盖 builder 一侧。
8. **`docs/ACCEPTANCE_TESTS.md` 的验收基线数字是旧树口径**，本批未同步；引用验收数字时不要拿它当现值。
9. 本轮**已**提交本分支 `feat/music-player-paths` 并开出 PR（提交号与 PR 链接见 GitHub）；**未**做：构建/打包、部署、合并、改正式 Release 或 tag。issue #283 / PR #284 属另一条线，本批未碰。

## 八、风险与回滚

- **影响面**：新增 2 个菜单动作、2 个默认布局节点、同一 `music_player_paths` 字典新增 2 个成员（**不新增配置格式、无迁移、无落盘结构变化**）；设置页新增 2 行；检测多一次 `clear_cache()`、一次有界版本目录探测与两个 daemon 预热线程。
- **行为面两处新增判断（最值得复核）**：① **选哪一份安装**——`cur_path` 优先、否则数字版本降序，会改变「点右键菜单启动哪个 exe」（从"枚举首个"改成"安装器声明的当前版本"）；② **检测回填条件**——只写文本未变过的行，超时的格子写「未完成」。两者都有专门用例，但都改变了用户可见行为。
- **回滚**：`git checkout -- pet/context_menus pet/menu_templates pet/music_players.py pet/settings_music.py pet/config.py pet/app.py`（或等价 revert）后旧布局与旧配置照常工作；已写入 `config.json` 的 `kugou` / `soda` 成员在新（旧）版本里是**表外键**，被 `_clean_music_player_paths` 丢弃（下次 `Config()` 构造时静默清理，不报错、不残留；`test_music_player_paths_drops_unknown_keys_but_keeps_old_two` 钉住）。
- **主要风险点**：① 默认布局树 +2 节点对「已保存布局」的影响（由补入机制与用例兜住）；② 检测总耗时变长（四键 24.5s，只影响主动点检测那一次，出齐即收尾）；③ 菜单多两条启动项（恒 `True`，未安装由运行期置灰解释；注册表再加播放器需同步默认树与设置页）；④ 多读一个安装描述文件（有 64 KB 上界与越界校验，不会变成「照配置读任意路径」）。
