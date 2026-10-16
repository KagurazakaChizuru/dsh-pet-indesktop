# PR 报告 · 每日一签（右键盘抽签 / 四句七言签诗 + 白话解签）

> **基线**：`1dc37ed2`（PR #290 的作者提交，`KagurazakaChizuru`，主题
> `feat(divination): 新增「每日一签」`）
> **分支**：`pr290-daily-divination`（worktree `D:/dsh-pet-wt-pr290`，**本地提交，未 push、未 merge**）
> **日期**：2026-10-17
> **范围**：本轮 18 个受版本控制的文件（实现 8、测试 7、文档 3——含本报告与两份登记）
> **关联**：PR [#290](https://github.com/MerZlin/dsh-pet-indesktop/pull/290)；
> [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)（设置准入与准出）、
> [`PR-REPORT-ISSUE-209-WEATHER-2026-10-07.md`](PR-REPORT-ISSUE-209-WEATHER-2026-10-07.md)（「互动」页内标签先例）

## 〇、本报告覆盖两件事

1. **PR 本体**（作者提交，`1dc37ed2`）：每日一签功能的完整实现——48 支签库、按日期确定性
   取签、同日锁定、一轮不重复、气泡与播报同一段文字、语音预合成、右键菜单入口。
   **本轮不改它的功能口径**（48 签 / 确定性 / 状态 / 语音一条不删），作者历史保留。
2. **本轮（2026-10-17）的两处收口 + 三份交付证据**：
   - **设置分组偏离修回**：作者把一个只有一组的「趣味」一级域加进侧栏（能力域
     10 → 11），为此把侧栏布局间距 3→0、导航行距 1→0。按
     [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 的准入（新增一级能力域须
     "代表长期独立用户目标、预计包含**至少两个**稳定设置组"）判**不合格**：域撤回，
     四行归位到「互动」域的第四个页内标签「抽签」（与「天气」同口径），侧栏间距与行高
     一个都不动。
   - **旁路预合成与报时预合成互相覆盖**：`VoiceChimeService.precache()`（每日一签用）
     原先复用 `role="precache"`，与**报时预合成**共用 `_precache_slot/_text/_bubble/_path`
     那一组占位字段。旁路合成**失败**会把报时**已经合好**的那一段一起清掉；旁路合成
     **成功**又会把 `_precache_path` 覆盖成旁路的 mp3。改为最小独立角色
     `AUX_PRECACHE_ROLE`，两条路径的占位互不相干。

**红线 / 不变量**（本轮不许破坏的语义）：

| # | 不变量 | 由谁钉住 |
|---|---|---|
| 1 | 同一天必得同一支签；签号 = `RAW_QUOTES` 下标 + 1，**只许追加** | `tests/test_divination.py::test_same_day_same_quote`（含跨进程一致性 `test_draw_is_reproducible_across_processes`）、`tests/test_divination_service.py::test_same_day_is_locked_to_one_quote` |
| 2 | 一轮 48 天不重不漏，走满后开新一轮（`drawn` 清空） | `tests/test_divination.py::test_a_round_covers_all_48_without_repeat` + 本报告 §五 实测 |
| 3 | 气泡与语音同一段文字；「抽签中...」是独立的第一句、只出现一次 | `tests/test_divination_service.py::test_waiting_line_is_spoken_exactly_once` |
| 4 | **侧栏 10 个能力域与顺序不变**（多处用例/截图脚本按名称与索引依赖） | `tests/test_settings_interaction_tabs.py::test_interaction_domain_uses_in_page_tabs_without_changing_sidebar` |
| 5 | 侧栏布局间距 3 / 导航行距 1 / 行高 34 不许再被压缩 | 本轮新增 `test_sidebar_spacing_and_row_height_are_not_squeezed` |
| 6 | 报时预合成的占位状态只由报时自己改 | 本轮新增 3 条（`tests/test_voice_chime_service.py`，消融后 3/3 变红） |
| 7 | 「抽支签」在 overlay 菜单里必须出现（门面显式代理 `on_divination_draw`） | `tests/test_sprite_menu_parity.py::test_divination_entry_appears_when_app_shell_provides_the_callback` |

## 一、核心特性

右键桌宠 → **「抽支签」**：一天一支签，当天再点显示同一支，次日 0 点换新；一轮 48 天
不重复（走满再轮回）。签是**四字典故签题 + 四句七言签诗 + 白话解签**，档位
上上 4 / 上 10 / 中平 24 / 下 10。可选语音播报复用语音报时的音色与音频通道。

**取签完全由日期决定**（splitmix64 定种子，不 `import random`）：无需存"今天抽了什么"
就能跨进程、跨重装得到同一支；用例给一个日期就能断言一支签，不存在"今天验过明天又变"。
**零个人信息**：只看日期，不碰生日/坐标等任何字段，因此不需要隐私守卫。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 签库 48 支 | `pet/divination_quotes.py`：四字典故签题 + 四句七言 + 白话解签两三句 |
| 2 | 同日锁定 | `pet/divination.py::draw_for_day`，按 `date.toordinal()` 派生种子；不存状态也稳定 |
| 3 | 一轮不重复 | 取签只在"本轮剩下"的签里定档再等概率取；走满 48 支由服务层清空 `drawn` 开新一轮 |
| 4 | 气泡 | 先「抽签中...」，等这一段**念完**（`channel_idle`）再静 2.8s 才揭签；气泡停留按字数算（4s + 90ms/字，上限 30s） |
| 5 | 播报 | 「抽签中...」独立起手 → 「今日X签，签题。签文：上句，下句。下句，下句。解签：…」 |
| 6 | 每日一签提示 | 当天还没抽时，第一次点桌宠冒一行「今日的签还没看」（一天只提示一次、可关） |
| 7 | 语音预合成 | 启动/配置变更/跨天检查时把两段文本提前合成**但不出声**；失败每 3s 重试（上限 20 次） |
| 8 | 右键入口 | `menu_templates/modern-default-v1.json` 的 tools 段，默认可见；`SpriteMenuFacade.on_divination_draw` 显式代理 |
| 9 | 设置页 | **「互动 · 抽签」标签**（本轮归位；原为独立「趣味」一级域，见 §〇） |

## 二、修改文件说明

### 本轮改动（`git diff --numstat HEAD`，HEAD = `1dc37ed2`）

#### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/settings_divination.py` | +23 / −9 | **归位**：`build_divination_page`（一级域整页）→ `build_divination_tab`（互动域页内标签，与 `build_weather_tab` 同形）；`build_divination_rows` 内部先调 `create_divination_controls`（自足，不依赖对话框别处接线）；模块 docstring 记下"为什么不再是独立域"与"三个开关是进程级键、`divination_state` 没有设置行"；修掉「试听今天的签」行说明里的 Markdown 星号（`**不改签号**` 在 Qt 里就是两个字形星号，改「不改签号」） |
| `pet/settings_interaction.py` | +18 / −11 | 「互动」域从三个页内标签扩到四个：`TAB_KEYS/TAB_LABELS` 追加 `("divination", "抽签")`，`build_interaction_domain` 挂第四页；docstring 把"两个标签"改成"四个同级任务"并写明抽签与天气同族（用户主动拉一次、桌宠给一个结果） |
| `pet/modern_settings_dialog.py` | +3 / −10 | **撤回**侧栏布局间距 0→3、导航行距 0→1（连带注释回到原口径）；删掉两条为「趣味」域做的接线（`settings_divination.build_divination_page(self)` 与 `create_divination_controls(self)`），保存委托 `save_divination_settings(self)` 与 import 保留 |
| `pet/settings_widgets.py` | +0 / −4 | `SETTINGS_DOMAIN_NAV` 删掉 `("趣味", "play")`（回到 10 个域）；`SIDEBAR_ROW_HEIGHT` 上方那段"能力域 10→11 要从间距里挤"的注释随之删除（它描述的机制已不存在） |
| `pet/app.py` | +2 / −2 | 总开关关掉时气泡里那句去处提示 `设置 → 趣味 里打开` → `设置 → 互动 · 抽签 里打开`（用户照着去找，指向已不存在的域就是误导）；同处段落注释 `每日一签（趣味域）` 同步 |
| `pet/config.py` | +2 / −2 | `divination_enabled` 上方注释里的归属改为「互动 · 抽签」标签 |
| `pet/settings_page_guide.py` | +1 / −1 | `SECTION_GUIDE` 的 `"抽签"` 分组注释 `# 趣味` → `# 互动 · 抽签` |
| `pet/voice_chime_service.py` | +46 / −11 | **旁路预合成与报时预合成分家**：新增 `PRECACHE_ROLE` / `AUX_PRECACHE_ROLE` / `PRECACHE_ROLES` 三个常量（附最长的一段注释说明为什么必须分开）；`precache()` 改用 `AUX_PRECACHE_ROLE`；`_fire` 的缓存命中分支按 `PRECACHE_ROLES` 判断（两条预合成路径都"不播放"）；`_handle_synthesized` 的缺依赖/失败/成功三处按角色分流——旁路**不碰**报时那一组 `_precache_*` 占位字段，也不进播放出口；`_maybe_precache` 与 `_synthesis_role` 的初始化改引用常量 |

#### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_settings_interaction_tabs.py` | +93 / −4 | 侧栏期望回到 10 域；`EXPECTED_TABS` 与 `ROWS_BY_TAB` 增加抽签标签（四行）；新增 4 条：① 抽签行确实挂在「互动」域、且没有「趣味」一级域；② 侧栏间距 3 / 导航行距 1 / 行高 ≥34 未被压缩；③ 搜「抽签」「每日一签」「试听今天的签」都命中并**自动切到抽签标签**；④ 三个开关进"已修改"标记覆盖面、按钮行不进，且改动真的出标记 |
| `tests/test_voice_chime_service.py` | +99 / −0 | 新增 3 条旁路预合成隔离用例（参数化：合成失败 / 缺依赖）+ 1 条返回值契约：报时预合成完成后，旁路的**失败**不许清掉报时的占位与路径、旁路的**成功**不许改写 `_precache_path`、两态都不出声；通道忙时旁路返回 `False` 供调用方重试 |
| `tests/test_desktop_pet_features.py` | +43 / −2 | 新增：总开关关掉时点「抽支签」给去处提示，且落点就是「互动 · 抽签」（不许再出现「趣味」、不许写状态）；菜单标签注释随归属更新；设置页域列表回到 10 个 |
| `tests/test_settings_slot_config_route.py` | +7 / −1 | **作用域**：抽签三个键列入"运行期只读主配置"清单（不参与 slot 分流）；子宠页保存抽签开关必须落**主** `config.json`、一个字节都不许进 slot 文件 |
| `tests/test_menu_layout.py` | +2 / −3 | 三处侧栏域列表与 `SETTINGS_DOMAIN_NAV` 图标表回到 10 域（不含「趣味」） |
| `tests/test_settings_pet_tabs.py` | +1 / −1 | 侧栏域列表回到 10 域 |
| `tests/test_architecture.py` | +4 / −3 | `MODERN_SETTINGS_DIALOG_PY_LINE_BUDGET` 按实测由 2537 校准到 **2530**（该文件本轮净 −7 行：删掉两条为「趣味」域做的接线，另加侧栏间距与保存委托两处注释的措辞）；注释里写明"抽签的页装配不在本文件"（它在 `settings_interaction` 里挂页） |

#### 文档

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `docs/PR-REPORT-DIVINATION-2026-10-17.md` | **新增 375 行** | 本报告：逐文件说明 / 离线性能实测数字 / 实机运行记录（隔离配置目录 + 真实 `windows` 插件截图）/ 已知限制与回滚 |
| `docs/INDEX.md` | +1 / −0 | 「PR 报告存档」登记本报告（新文档入场规则第 1 条；`tests/test_pr_report_discipline.py` 强制） |
| `docs/SETTINGS-CHANGE-GATES.md` | +46 / −0 | 文末追加 2026-10-17 变更记录：4 个新键登记 + 域归位理由与准入复核 + 本轮五行准出对应 |

合计（`git diff --cached --shortstat`）：**18 files changed, 766 insertions(+), 64 deletions(−)**（本报告自身占 375 行）。

### 未改动（看起来相关但故意没动）

| 文件 | 为什么不动 |
|---|---|
| `pet/divination.py` / `pet/divination_quotes.py` | 取签算法、48 支签库、档位权重一条不改（用户明确要求保留） |
| `pet/divination_service.py` | 状态与节奏口径不改；本轮只改它**依赖的**通道角色语义（`pet/voice_chime_service.py`） |
| `pet/voice_chime_settings.py` | 作者同日把「立即试听」挪进「用什么声音」组、把两个自定义台词框压到 56/90px——那是**用户直接要求**的语音页改动，与本轮归位无关，保留 |
| `pet/context_menus/registry.py`、`pet/menu_templates/modern-default-v1.json`、`pet/sprite_menu_facade.py`、`pet/overlay_shell.py`、`pet/window.py`、`tests/test_menu_layout.py` 的菜单断言 | 右键入口与 overlay 接线已由作者写完并有正反两向用例；本轮不动 |
| `docs/SETTINGS-CHANGE-GATES.md` 的历史条目 | 只在文末**追加** 2026-10-17 一条（新增键 + 域归位 + 本轮证据），不重写旧记录 |

## 三、实现要点

### 1. 取签为什么不用随机数

`_seed_for(day) = splitmix64(day.toordinal() * 0x2545F4914F6CDD1D)`。用 `toordinal` 的
好处是与本地时区/夏令时无关（同一天在任何时区都是同一个序数）。**不 `import random`**
是刻意的：`random` 需要外部状态才能复现，而"今天抽了什么"本身不该被存下来——不存也能
得到稳定结果，重启/重装/换机都一致，且用例可以给任意日期断言任意一支签。

**同一处踩过的坑**（作者注释里也记了）：在档位内取签时**不能用 `hash(tier)`**——Python
的字符串 hash 每进程随机（`PYTHONHASHSEED`），"同一天同一支"会跨进程失效；改用档位在
`TIERS` 里的固定序号。

### 2. 为什么"只在同档里排除"不成立

中平有 24 支却占 56% 权重，48 天里必然先抽空。若取签只做同档排除，就会出现"同一支重复
出现、而别的档还有没见过的签"，与"走完 48 支再轮回"直接矛盾。现在的口径是把
`drawn_ids` 当作**全局**排除集：先在还有剩余的档里按权重定档（该档抽空就回落到还有剩余的
档），再在该档剩余里等概率取一支。48 天恰好走完 48 支。

### 3. 揭签的"间隔"按声音判、不按点击时刻算

`_schedule_reveal` 轮询 `channel_idle`（150ms 一步，上限 6s），空闲后再静
`READING_GAP_MS = 2800`。若从点击起算固定毫秒，音色/语速一变间隔就被吃掉——用户的原话
是「抽签中和解签要分一个比较长的间隔」，这个间隔指的是**两段声音之间**。

### 4. 预合成的两条路径为什么必须分家（本轮修复）

`VoiceChimeService` 里 `_precache_slot/_precache_text/_precache_bubble/_precache_path`
这一组字段原本只有**报时预合成**一个写者：`_maybe_precache` 占位 → 到点
`_consume_precache` 取用。作者为了让每日一签"点下去马上出声"加了公开入口
`precache(text)`，但它复用了 `role="precache"`，于是：

- `_handle_synthesized` 的**失败/缺依赖**分支按角色清占位——旁路的一次失败会把报时
  **已经合成好**的缓存路径一起抹掉，到点只能回退即时合成（晚 3–8 秒才响）；
- **成功**分支按角色写 `_precache_path`——旁路完成会把这一格改成旁路那个 mp3；
  随后 `_consume_precache(报时槽位)` 判"槽位对得上 + 文件存在"就返回，日志里报的是
  别人的文件名（这次只是运气好：调用方拿了返回文本重算 cache key 才没出声播错）。

修法是**最小独立角色**，不新增通用框架：加一个 `AUX_PRECACHE_ROLE = "precache_aux"`，
旁路路径只落在自己按文本算出的 cache key 上，报时那一组字段一个都不碰；两个角色在
`_fire` 的缓存命中分支与 `_handle_synthesized` 的播放出口都归入"不出声"。

### 5. 设置页归属（本轮撤回一级域）

「趣味」一级域不满足设置门准入第 1 条（同一能力域内的**同级任务**适合页内标签，
先例：菜单域的 菜单编排/快捷启动/外观、互动域的 点击与音效/自言自语/天气），也不满足
"新一级域须预计包含至少两个稳定设置组"——它只有一个组、四行。用户的代价是实打实的：
为了在 800×560 里塞下第 11 个域，作者把侧栏布局间距压到 0、导航行距压到 0，**所有域**的
点击目标与呼吸空间一起缩水。归位后侧栏回到 10 域、间距回到 3/1（本机实测余量 17px，
见 §四）。

## 四、性能分析

**方法（可复现）**：`python .scratch/divination-pr290/probe_perf.py`
（脚本在 worktree 内，`n` 逐条标注）　环境：Windows 11 / Python 3.13.7 / PySide6 6.11.2 /
本机 CPU（未固定频率，取中位数与最小值并给轮间噪声带）。**全程不联网、不开事件循环、
不落真实配置**。

| 指标 | 实测（中位数，n 见括号） | 归属 |
|---|---|---|
| `draw_for_day`（本轮已抽 30 支） | **8.5 µs/次**（min 8.2；n=5×2000） | 热路径（点一次菜单一次） |
| `draw_for_day`（新一轮，`drawn` 空） | **10.5 µs/次**（min 10.3；n=5×2000） | 热路径 |
| `speech_text`（播报文本拼装） | 0.56 µs/次（n=5×2000） | 点一次一次 |
| `card_lines`（详版三行） | 0.35 µs/次（n=5×2000） | 点一次一次 |
| `quote_by_id`（当天锁定读回） | 0.11 µs/次（n=5×2000） | 当天重复点 |
| `normalize_divination_config(dict)` | 0.79 µs/次（n=5×2000） | 启动 / 每次配置变更 |
| `clean_divination_state(48 支 + 50 条脏 history)` | 3.4 µs/次（n=5×2000） | 每次读状态 |
| `hint_on_interaction`（当天已看过：读完 state 早退） | **10.9 µs/次**（min 10.1；n=5×2000） | **每次点桌宠**（新增热路径） |
| `hint_on_interaction`（当天没看：冒提示 + 写 state） | 14.9 µs/次（n=5×2000） | 一天一次 |
| `_precache_today`（语音关着：直接早退） | 0.27 µs/次（n=5×2000） | 跨天定时器每 10 分钟一拍 |
| `_precache_today`（今天已预热：字符串比对后早退） | 3.1 µs/次（n=5×2000） | 同上 |
| 设置窗整窗构建（含抽签 4 行） | **1107.6 ms**（min 1044.8；n=7） | 一次性 |
| `build_divination_tab`（4 行 + 1 分区） | **6.05 ms**（n=20） | 一次性 |
| `build_interaction_domain`（四标签整装） | 91.5 ms（min 70.6 / max 124.3；n=20） | 一次性 |

（逐字日志：`.scratch/divination-pr290/perf.log`）

**结论**（逐条回答）：

1. **稳态开销**：新增的稳态成本只有两处，都极小——① 每 10 分钟一次的跨天检查
   （0.27–3.1 µs，纯字符串比对）；② **每次点桌宠**的提示门（10.9 µs，其中 3.4 µs 是
   状态清洗）。相比一次点击本身的动画面/音效路径（毫秒级）可忽略。
2. **新增路径的绝对成本与触发频率**：取签 8.5–10.5 µs（一天一次，或当天重复点）；
   状态清洗 3.4 µs（读状态时）；揭签延时由 `QTimer.singleShot` 承载，不占线程。
   落盘次数：新的一天第一次抽签写 1 次 `config.json`，同一天再点 **0 次**；
   当天提示写 1 次（一天只提示一次）。实测（`probe_perf.py`）：当天两次抽签
   `saves=1`；新的一天点桌宠 50 次 → 提示 1 次、`saves` 共 2。
3. **有没有新的系统调用/网络/磁盘/线程**：**没有新增任何一条**。网络只走既有的
   `VoiceChimeService.precache` → edge-tts 合成线程（每日一签每天最多提交 **2 段**文本；
   通道忙就返回 `False` 由服务层 3s 后重试，不排队、不并发第二路）。线程是既有的合成
   worker；磁盘只有上面那两处 `Config.save()`（既有入口）；定时器是 1 个 `QTimer`
   （10 分钟一格，停在服务停用时由 `shutdown()` 显式停）。
   **本轮的角色分家改动新增 0 条网络/线程/系统调用**：diff 只改了传进去的角色字符串与
   分支归属，不新增调用点。
4. **内存与缓存有没有增长**：状态只有一份扁平 dict（`date` / `quote_id` / `drawn` /
   `hint_date`，`drawn` 最多 48 个 int）。**不写签册**（作者按用户选择删掉了"历史只写
   不读"的字段）。缓存侧每日一签没有自己的目录：它写进**既有**的
   `voice_chime_cache/<key>.mp3`，每天最多新增 2 个 key，且受既有的"200 文件上限 +
   5 分钟节流清扫"约束。本机实测（`probe_perf.py` 的 48 天连跑，隔离目录）：
   `divination_state` 在整轮里始终是
   `{"date": ..., "quote_id": int, "drawn": [≤48 个 int]}` 三个字段。

**测不出的一处（如实登记）**：`build_interaction_domain` 的轮间噪声带 53.7 ms，
而抽签那一刀是 6.05 ms——**落在带内，等于测不出**。所以本报告不给"互动域整装净增
多少"这个数，只给可归因的那一项（`build_divination_tab` 6.05 ms，设置窗打开时一次）。

**未测得的一处（如实登记）**：真正会联网的 edge-tts 合成本机**没有实测**（本轮不捏造
TTS 联网数字）。可确证的只有调用次数与失败语义：每天最多 2 段、失败返回 `False`
由调用方重试（`tests/test_voice_chime_service.py::test_precache_reports_busy_so_the_caller_can_retry`）。

## 五、实机运行记录

**本机真实环境**（Windows 11，Python 3.13.7，PySide6 6.11.2，**真实 `windows` 平台插件**
`windows11` 样式，不是 offscreen），全部跑在**隔离的一次性配置目录**里
（`Config(base=tempfile.mkdtemp())`，`PYTHON_KEYRING_BACKEND=null`），**不读用户真实配置**。

### 5.1 取签与落盘（`python .scratch/divination-pr290/probe_runtime.py`，日志 `runtime.log`）

```text
--- ① 当天第一次点「抽支签」 ---
  气泡第一段：'抽签中...'
  气泡第二段：'〔中平〕按兵不动\n按兵不动非怯战\n等风来时再扬帆\n此时收手不算输\n阵脚稳住就是赢\n解签：今天不动，是留力，不是认输。看着就好，别急着表态。'
  签号=16 档位=中平 签题=按兵不动 newly=True
  config.json → divination_state = {'date': '2026-10-17', 'quote_id': 16, 'drawn': [16]}

--- ② 同一天再点一次 ---
  同一支签：True  newly=False
  状态未变：True

--- ③ 一轮 48 天：不重不漏（真实 Config + 真实服务） ---
  48 天签号：[16, 23, 34, 19, 7, 33, 20, 47] ... [4, 1, 2, 3]  去重后 48 支
  第 49 天状态（新一轮起点）：date=2026-12-03 drawn=[]

--- ④ 开关关掉时右键那次点击（不静默无反应） ---
  气泡：['每日一签已关闭 · 设置 → 互动 · 抽签 里打开']

--- ⑤ 语音打开时：先念「抽签中...」，再念整段签文（通道替身记账） ---
  启动预合成：['[precache]抽签中...', '[precache]今日中平签，按兵不动。签文：…']
  点下去之后的播报序列：['抽签中...', '今日中平签，按兵不动。签文：按兵不动非怯战，等风来时再扬帆。此时收手不算输，阵脚稳住就是赢。解签：今天不动，是留力，不是认输。看着就好，别急着表态。']
  气泡尾行 = '解签：今天不动，是留力，不是认输。看着就好，别急着表态。'

全部实机检查通过（隔离目录；未触网、未出声）
```

- **根因/前提现场复现**：③ 是本轮最关键的现场证据——48 天走完 48 支、第 49 天状态里
  `drawn=[]`（一轮走满即开新一轮），用的是**真实 `Config` + 真实 `DivinationService`**，
  状态每一轮都重新从磁盘读回。
- **用户可见行为的确认**：①②⑤ 给出气泡文本、播报序列与磁盘状态的真实值。
  **注意 ⑤ 的播报是通道替身记账，不是真机出声**（本机没有可用音频设备，也不该在
  用户机器上出声）；"真机听到声音"这一条**未验**，见 5.4。
- **边界与失败路径**：④ 是"开关关掉"这条本该如此的分支——点击**不静默无反应**，
  气泡指名设置页落点，且**不写任何状态**。

### 5.2 设置页几何（`python .scratch/divination-pr290/probe_settings_layout.py`，真实 windows 插件）

六档全过（`结论：全部几何断言通过`）：

```text
=== 800x560 · light ===   pane=200x560 layout.spacing=3 sidebar.spacing=1 rowHint=34
  domains=10 viewport=375 scrollMax=0 lastBottom=358 slack=17
  interaction tabs = ['click', 'self_talk', 'weather', 'divination']
    divination_enabled     w= 532 h= 68 hintW= 444 hintH= 30 need= 30
    divination_speak       w= 532 h= 68 hintW= 444 hintH= 30 need= 30
    divination_preview     w= 532 h= 68 hintW= 378 hintH= 30 need= 30
    divination_hint        w= 532 h= 68 hintW= 444 hintH= 30 need= 30
  scrolled to bottom: last row bottom y=166 viewport=476
（720×560 light/dark、800×560 dark、800×560 @150% 同形；1.5× 与 720 下长 hint 行
  自动增高到 45/83px，need 全部 ≤ 实际高）
```

- **侧栏 10 个域全部落在视口内**、逐个都能选中并切页；800×560 下余量 **17px**
  （这正是"不必压间距"的量：把间距压掉只能多买 16px，代价是所有域的点击目标）。
- **抽签四行**不横向裁切、说明文字按 `heightForWidth` 不纵向裁切、滚到底最后一行可见。
- 1.5 倍字体下窗口最小高度被自身撑到 **746px**（800×560 的窗口约束在该档不适用），
  此档布局同样无裁切。

### 5.3 截图自查（项目自带脚本 `scripts/capture_settings_pages.py`）

命令（隔离目录由脚本自己建；`--interaction-details` 会遍历互动域每个页内标签）：

```bash
python scripts/capture_settings_pages.py .scratch/divination-pr290/capture---light-800x560 --width 800 --height 560 --light --interaction-details
python scripts/capture_settings_pages.py .scratch/divination-pr290/capture---dark-800x560  --width 800 --height 560 --dark  --interaction-details
python scripts/capture_settings_pages.py .scratch/divination-pr290/capture-light-800x560-f150 --width 800 --height 560 --light --font-scale 1.5 --interaction-details
python scripts/capture_settings_pages.py .scratch/divination-pr290/capture-light-720x560 --width 720 --height 560 --light --interaction-details
```

产出 `03-互动-抽签.png` 等 14 张/档（worktree 内 `.scratch/`，**不进提交**，`.gitignore` 已有 `.scratch/`）。
**逐张人工看过**（本会话直接读图复核）：

| 档 | 看到什么 |
|---|---|
| light 800×560 | 侧栏 10 域名称完整、`更新` 完整可见；「互动」页四个标签 `点击与音效 / 自言自语 / 天气 / 抽签`（抽签选中）；「抽签」分区四行齐全：每日一签（开）、抽签时念出来（关）、试听今天的签（按钮）、每天提醒一次（开）；长 hint 正常换行，无截断 |
| dark 800×560 | 同上；文字/边界/开关的关态与开态可辨认（关态灰底无填充、开态蓝填充） |
| light 800×560 @1.5 | 窗口被最小高度撑到 800×746；字号放大后行高随之增高，文案不裁切、按钮不压字 |
| light 720×560 | 窄窗下侧栏仍完整（10 域 + 两个重置按钮 + 版本号都在），页面横向不溢出 |

### 5.4 无法自动验证的能力（给排查证据，不用沉默代替结论）

| 能力 | 为什么不能在本轮自动验证 | 已做的探针/替代判据 |
|---|---|---|
| 真机听到抽签语音 | 本机**有**音频输出设备（探针：`QMediaDevices.audioOutputs()` 返回 6 个设备，默认 `扬声器 (Creative Pebble Pro)`）——不是"没设备"，而是**不该由代理在用户机器上出声**（全量测试 conftest 也是全局静音 `play()`） | 播报序列与文本用通道替身逐句断言（5.1 ⑤ + `tests/test_divination_service.py`）；真机音色/音量/是否被免打扰吃掉由**用户点击验收**（PR 页面写清）。**未验就是未验**，不用探针结果冒充已验 |
| edge-tts 真实联网合成耗时 | 本轮明确不捏造联网实测 | 只登记调用次数（每天 ≤2 段）与失败语义（返回 `False` 交调用方重试）；合成线程与预合成口径是既有代码，未改 |
| 右键菜单在真机桌面上的视觉效果 | 需要真机 CU 交互（本轮范围外） | `tests/test_sprite_menu_parity.py` 用真 overlay 壳 + 真注册表构建菜单，正反两向断言「抽支签」出现/消失；菜单段位与顺序由 `tests/test_menu_layout.py` 的渲染断言钉住 |
| 「每日提示」在真机上第一次点桌宠时的观感 | 同上 | `divination_hint_on_interaction` 的服务语义有 4 条用例（只提示一次/可关/开关联动/已抽过不提示），本轮另加界外成本实测（10.9 µs/次点击） |

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | **All checks passed!** |
| 聚焦（本轮改动面，17 个文件） | `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_divination.py tests/test_divination_service.py tests/test_settings_interaction_tabs.py tests/test_settings_slot_config_route.py tests/test_voice_chime.py tests/test_voice_chime_service.py tests/test_settings_page_guide.py tests/test_settings_default_marks.py tests/test_settings_search_aliases.py tests/test_settings_copy_lint.py tests/test_menu_layout.py tests/test_desktop_pet_features.py tests/test_settings_pet_tabs.py tests/test_architecture.py tests/test_config_schema.py tests/test_sprite_menu_parity.py tests/test_pr_report_discipline.py` | **891 passed**（202.65 s） |
| 受影响时序族高负载复跑 ×3 | 同一命令连跑 3 遍：`pytest -q tests/test_voice_chime.py tests/test_voice_chime_service.py` | 3 遍各 **271 passed**（5.73 / 8.71 / 9.09 s），无 flake |
| 断言有效性（消融·预合成） | 把 `pet/voice_chime_service.py` 换回 `HEAD` 版本，重跑 `-k aux_precache` | **3 failed**（两条参数化 + 一条完成路径）；恢复后全绿 |
| 断言有效性（消融·归位） | 把 4 个设置页产品文件换回 `HEAD` 版本，重跑 `-k "divination or sidebar_spacing"` | **3 failed / 1 passed**（归属、侧栏间距、搜索三条红；默认标记那条两版都成立——它锁的是覆盖面，不是归属） |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **7967 passed / 15 skipped / 0 failed**（1454.19 s；日志 `.scratch/divination-pr290/full-suite.log`） |
| 架构红线 | `tests/test_architecture.py`（含行数预算） | 通过（`MODERN_SETTINGS_DIALOG_PY_LINE_BUDGET = 2530`，实测 2530 行） |
| 工作区卫生 | `git diff --check` | 通过（无空白错误；`docs/*.md` 行尾统一 CRLF） |

### 补充一：证据文件位置（都在 worktree 内、`.scratch/` 已被 `.gitignore` 排除，不进提交）

| 文件 | 内容 |
|---|---|
| `.scratch/divination-pr290/probe_perf.py` / `perf.log` | §四 的全部性能数字（可复跑） |
| `.scratch/divination-pr290/probe_runtime.py` / `runtime.log` | §五 5.1 的真实 Config 落盘与播报序列 |
| `.scratch/divination-pr290/probe_settings_layout.py` / `layout.log` | §五 5.2 的六档几何断言（真实 `windows` 插件） |
| `.scratch/divination-pr290/capture---light-800x560/`、`capture---dark-800x560/`、`capture-light-800x560-f150/`、`capture-light-720x560/` | §五 5.3 的四档截图（各 14 张，含 `03-互动-抽签.png`） |
| `.scratch/divination-pr290/full-suite.log` | 全量 pytest 逐字输出 |

## 七、已知限制与后续

1. **TTS 合成仍然"慢"的本质没变**：预合成能覆盖"启动后当天"，但**跨天的第一次点击**
   仍可能冷合成（0 点后到第一次点之间没有预热窗口，除非机器通宵开着让 10 分钟定时器
   补上）。267 那条线正在重构 TTS provider 接口——**合并时接缝就是本 PR 用到的两个
   公开面**：`VoiceChimeService.precache(text, log_tag=...) -> bool`（返回值语义 =
   "已可用或已在合成中"）与只读属性 `channel_idle`。旁路预合成角色
   `AUX_PRECACHE_ROLE` 是**通道内部**的事，provider 重构不该把它当作外部契约。
2. **「每天提醒一次」只在"点桌宠"这一条路径上提示**：overlay 拓扑下提示走壳自己的
   `SpriteInteraction` 入口（`overlay_shell`），气泡落在主窗口上——点**子宠**也提示，
   但气泡跟随主宠。与节日提醒同口径，本轮不动。
3. **`build_interaction_domain` 的净增量测不出**（噪声带 53.7 ms > 抽签的 6.05 ms），
   已如实登记；要量准得把互动域整装拆细测，属另一件事。
4. **真机验收项**（交给用户）：右键「抽支签」的观感、语音实际出声与间隔、
   每日提示的打扰程度。

## 八、风险与回滚

**影响面**

| 面 | 说明 |
|---|---|
| 用户可见功能 | 新增一个右键菜单项（tools 段默认可见）+ 设置页「互动」域多一个页内标签 |
| 新增持久键 | `divination_enabled`（默认 **开**）、`divination_speak`（默认关）、`divination_hint`（默认开）、`divination_state`（运行时状态，默认 `{}`）。**都是全新键**：老配置没有它们 → 取默认；出厂默认与重置共用 `Config._initial_data()`，没有第二份真值 |
| 恢复默认 | `divination_enabled`/`divination_hint` 出厂为开，全量重置后回到开；`divination_state` 被重置清空 → 当天会重新取签（**这是取的同一支**，因为取签只跟日期有关，不会"换签"） |
| 跨平台 | 无新平台分支；三个开关与签库都是标准库 |
| 性能 | 见 §四；新增稳态成本为 10.9 µs/次点击 + 3.1 µs/10 分钟 |

**开关与回滚**：设置页「互动 · 抽签 → 每日一签」关掉即停（服务被释放、定时器停、
菜单项保留但点了给去处提示）。代码回滚 = `git revert` 本分支提交；**残留状态**：
`config.json` 里的四个 `divination_*` 键会留着（读入即弃不存在——`divination_state`
只是历史状态，不会影响其它功能；想彻底清干净可手工删这四个键，或走「恢复全局默认…」）。
作者原始提交 `1dc37ed2` 完整保留在分支历史上，可单独取用。

## 九、第三轮（2026-10-17）：累计合并 PR267 候选后的兼容收口

> **起点**：本轮收口后的 `1c69fb3`（本分支）
> **合入**：`integration/pr267` = `210ea04`——PR [#267](https://github.com/MerZlin/dsh-pet-indesktop/pull/267)
> （作者 `KagurazakaChizuru`，tip `29a87be`，TTS 合成后端 provider 化）合上游 `main` `056dc2a`
> （#291 汽水歌词 / #288 跨屏 / #287 edge-tts 门禁）的候选。合并前先读过
> `D:/dsh-pet-pr267-artifacts/PRECACHE-COMPAT-NOTE-FOR-290.md`（该候选给 `precache` 相关
> 接口写了兼容说明）。
> **状态**：本分支**仍是本地提交**——未 push 作者 fork、未 merge 上游。理由见 9.5。

### 9.1 六处冲突的取法

| 冲突文件 | 取法 | 为什么 |
|---|---|---|
| `pet/voice_chime_service.py`（`_fire` 缓存命中分支） | **两侧都要**：逐后端循环（本支）＋循环内对 `role in PRECACHE_ROLES` 早退（267） | 缓存路径从"一个"变成"逐后端一个"，早退必须落在循环里；只取循环就丢"提前合好不许出声"，只取早退就只查第一个后端 |
| `pet/modern_settings_dialog.py` | 取 267 侧（`voice_chime_rows` / `festival_rows` 认领） | 语音报时与节日提醒的行已由 provider 声明重建为平卡，旧的 `voice_sections` / `festival_sections` 分组表在合并树里**没有消费方**（留下就是死代码） |
| `pet/settings_page_guide.py` | 取 267 侧新卡名 + 保留本支「抽签」条目 | 卡片标题从「语音报时 · X / 节日提醒 · X」变成卡片名；「抽签」是本支新增的页内标签落点，两边都要在 |
| `tests/test_settings_page_guide.py` | 取 267 侧 | 旧的三条「语音报时 · X」卡名在合并树里不存在（`_section(dialog, "语音", …)` 必失败） |
| `tests/test_architecture.py` | 行数预算按合并后**实测 2535** 重设 | `2526`（main）/ `2530`（本支）/ `2533`（267）三个数字都被合并树取代：TTS provider 化净 +7 与抽签接线净 +4 落在同一份文件上 |
| `docs/INDEX.md` | 两侧行并集 | 本支的 DIVINATION 行 + 主线的 SODA-LYRICS-ROUTE 行（#291） |

### 9.2 语义迁移（没有文本冲突、但不改就是坏的）

- **`precache()` 改用 provider 接口**：可用后端改用 `_usable_attempts()`（它已跑过 provider
  的 `preflight()`，"音色下架换默认"的说明由它弹一次），缓存路径改用
  `_cache_path(text, attempt)`（扩展名 `.mp3`/`.wav` 与缓存键里的 provider flavor 都由
  provider 给）。原来那三段——自己 `resolve_voice()`、自己拼平铺 dict 喂 `cache_key()`、
  自己认 `.mp3`——在合并后**服务层已无这些符号**（合成整段进了 `pet/tts/`），不改就是
  `NameError`。
- **"后端不可用"的判据换源**：原来是 `_EDGE_TTS_AVAILABLE`（模块级标志，已随合成链路搬进
  provider），现在就是"`_usable_attempts()` 返回空元组"——回退链上的 doubao / mimo 同样
  按各自的 `availability()` 参与判定，不再只看 edge 一家。
- **AUX 预合成与报时预合成仍然分家**（本支的核心隔离，一个字节未改）：
  `AUX_PRECACHE_ROLE` 只写自己的 cache key，不碰报时那一组
  `_precache_slot/_text/_bubble/_path`；`_handle_synthesized` 的失败/完成分支按角色分流。
  合并只动了 `_fire` 的命中分支结构，占位隔离不在其中。
- **上游能力照留**：`edge-tts>=7.3.1,<8` 的依赖下限（#287 门禁）、`pet/tts_diagnostics.py`
  的脱敏失败诊断、`pet/music_lyric.py` 的 #291 直连＋有界单次回退（与本支改动面无关，
  合并后逐字节等于上游 `056dc2a` 版本）。

### 9.3 本轮验证（本机 Windows 11 / Py3.13.7 / PySide6 6.11.2）

环境口径：`D:\dsh-pet-src\.venv` + 隔离依赖目录 `D:/dsh-pet-pr267-deps`（edge-tts 7.3.1，
= `requirements.txt` 的下限）+ `D:/dsh-pet-pr267-deps-ocr`（omegaconf）、
`PYTHONPATH="…;…"` `QT_QPA_PLATFORM=offscreen`。

> **环境坑（会让结果看起来像产品 bug）**：Windows 上 `PYTHONPATH` 的分隔符是 **`;`**，
> 用 Git Bash 惯用的 `:` 拼两条路径会**整条作废**（被当成一个带冒号的路径名）。后果是
> `edge_tts` 根本没被导入 → `_usable_attempts()` 返回空 → `test_voice_chime_service.py`
> 里 46 条用例集体变红（"worker 没被构造"），看起来像 provider 化改坏了合成链。共享 venv
> 本身**没装 edge-tts**，同样表现为那 46 条红；而上游 `main` 的同一批用例在 267 候选树上
> 是依赖 `edge-tts>=7.3.1` 的（构建门禁也认这个下限）。复跑请用
> `PYTHONPATH="D:/dsh-pet-pr267-deps;D:/dsh-pet-pr267-deps-ocr"`。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check .` | **All checks passed!** |
| 聚焦（两侧改动面的并集，25 个文件） | `pytest -q tests/test_tts_*.py tests/test_voice_chime*.py tests/test_divination*.py tests/test_settings_{interaction_tabs,page_guide,default_marks,search_aliases,copy_lint,pet_tabs,slot_config_route}.py tests/test_menu_layout.py tests/test_desktop_pet_features.py tests/test_config_schema.py tests/test_sprite_menu_parity.py tests/test_festival*.py tests/test_architecture.py tests/test_pr_report_discipline.py` | **1053 passed**（201.64 s，提交后在已提交的树上复跑；9.3 之外那次 1052 是新增用例之前跑的） |
| 受影响时序族高负载复跑 ×3 | `pytest -q tests/test_voice_chime.py tests/test_voice_chime_service.py` 连跑 3 遍 | 3 遍各 **272 passed**（5.88 / 6.07 / 6.23 s），无 flake |
| 全量（按文件切 18 片、各起独立进程） | `python run_chunks_pr290.py 500`（脚本与逐片日志：`D:/dsh-pet-pr290-artifacts/`） | **8092 用例跑到：passed 8070 / failed 1 / skipped 21**；唯一那条红是 9.4 的环境用例，与本次改动无关 |
| 断言有效性（消融·早退守卫，本轮新增用例） | 删掉 `_fire` 里那 4 行 `if role in PRECACHE_ROLES: … return` 后重跑 `-k aux_precache` | **1 failed / 3 passed**（红的那条正是新增用例，`plays == 1`："预合成偷偷播了一次"）；恢复后 4/4 绿，文件 sha256 与消融前一致 |

### 9.4 全量那一条红的归因（不假称通过）

`tests/test_proactive.py::TestVisionAndWatcherPhase2::test_foreground_window_info_real_call_no_shadow_bug`

那条用例断言"真实调用 `pet.vision.foreground_window_info()` 必须拿得到前台窗口"。探针
（`D:/dsh-pet-pr290-artifacts/probe-foreground.py`，输出同名 `.log`）在本机此刻拿到的是
**不可见**窗口：

```
GetForegroundWindow() = 27987436
IsWindowVisible = False
IsIconic        = False
```

而 `foreground_window_info()` 的契约就是"窗口不可见 / 最小化 / cloaked / 取不到 → 返回 None"
（`pet/vision.py:95`），所以那句 `assert info is not None` 的前提不成立。**与本次改动无关的
证据有三条**：① 两侧都没碰过 `pet/vision.py` 与 `tests/test_proactive.py`（对 merge-base
的 diff 为空，合并树里逐字节等于两侧）；② 同一条用例在 `D:/dsh-pet-wt-pr267`（PR267 候选、
三端 CI 全绿的那棵树）**同样失败**；③ 它在隔离环境下失败，与分片位置、并发都无关。

### 9.5 未做与边界

- **未 push 作者 fork 的 `feat/divination`**（PR #290 的 head）：267 候选还在等合并，
  现在就把累计结果推上去，会把 267 的内容一起卷进 #290 的 diff，两条管线互相混账。
  本轮只本地提交。**（第四轮口径已变：上游三条已落 main，本轮随分支更新 #290，见 §十。）**
- **未改 289 / input / v5 相关树**，未涉及 DLC。
- **未做真实配置与人工点击**（本轮不重复广泛审查、不操作真实用户配置）：真机验收项仍以
  §五 的隔离配置探针为准，右键观感与真实出声留给用户点验收。
- **doubao / mimo 仍无 Key**：与 267 候选同一状态（合成链路的可用性判定有用例，真实合成未测）。

## 十、第四轮（2026-10-17 晨）：发布前累计整合（合 main 上的 #267 / #293 / #289）

> **起点**：`e426727`（上一轮的累计树）→ **三段合并后的 tip**：`d193e72`（本报告登记此次整合）
> **上游状态**：`#267` `fdb3908`、`#293` `139aca3`、`#289` `e08c7fb` 已按 squash 依次落进
> `origin/main`（在 `53d0587` 之后）。本支此前分别合过它们落地**之前**的候选树，
> 所以这一轮只处理真正重叠的部分，不是把三条 PR 又合一遍。

### 10.1 三段合并与冲突取法

| 段 | 合入 | 冲突文件 | 取法 |
|---|---|---|---|
| ① | `origin/main` `53d0587`（#292 frameseq alpha 档） | `docs/INDEX.md` | 两侧行并集（DIVINATION 行 + FRAMESEQ-ALPHA-FLOOR 行） |
| ② | 输入链路候选 `498ecd1`（#293 落地前的已验证树） | `docs/INDEX.md` | 两侧行并集（再加 INPUT-GRAB-RELEASE 行） |
| ③ | `origin/main` `e08c7fb`（#267 / #293 / #289 都在里面） | `pet/voice_chime_service.py`、`pet/settings_page_guide.py`、`tests/test_architecture.py`、`docs/INDEX.md` | 见下 |

③ 的三处代码冲突（前两段只有 `docs/INDEX.md` 一个文档冲突）：

- **`pet/voice_chime_service.py`**：main 侧（随 267）把缓存命中分支重构成「逐后端一条路径」，
  本支在同一位置加了 `if role in PRECACHE_ROLES: return`（预合成撞上已有缓存不许出声）。
  取**两侧都要**——早退落在重构后的循环里；只取循环会丢「提前合好不许出声」，只取早退就只查第一个后端。
- **`pet/settings_page_guide.py`**：main 侧（随 267）把语音那几张卡的描述改成卡片名口径，
  本支新增「抽签」条目——两个都要，「抽签」落在互动域页内标签那一组。
- **`tests/test_architecture.py`**：行数预算 main 侧 `2533`（= 2526 + TTS provider 化净 +7）、
  本支 `2535`。按**合并树实测 2535** 取，注释改写为「main 2533 + 本支接线净 +2」。
- **`docs/INDEX.md`**：两侧行并集（含 289 新登记的 ZERO-PET-NOTICE 行）。

### 10.2 合并后的隔离核对（这是本轮最关键的一条证据）

`git diff --numstat e08c7fb`（合并树 vs 上游 main）**只剩本支的每日一签改动面，零删除行**：

- 与 main **逐字节相同**（因此不出现在 diff 里）：`pet/tts/**`、`tests/test_proactive.py`、
  `pet/overlay_window.py`、`pet/sprite_slingshot.py`、`pet/pet_profiles.py`、
  `tests/test_no_pet_startup_notice.py`、`tests/test_pet_profiles.py`——即 #267 / #293 / #289 的全部产品面。
- 本支在上游文件上的净增量只有两处：`pet/voice_chime_service.py` **+96/−5**（旁路预合成隔离 +
  `precache()` 走 provider 接口）、`pet/overlay_shell.py` **+11**（每日一签提示接线）。

「零删除行」正是「上游内容一条没丢、本支也没把上游改回去」的机器判据；文档侧还有
`docs/INDEX.md` / `docs/SETTINGS-CHANGE-GATES.md` / 本报告三处本支新增。

### 10.3 §9.4 那条环境红现在怎么算

§9.4 把 `tests/test_proactive.py::TestVisionAndWatcherPhase2::test_foreground_window_info_real_call_no_shadow_bug`
归因为**本机前台窗口不可见**（与产品改动无关）。上游 #293 的 `faf8d35` 已把该用例改成
「先独立读一遍 Win32 前置条件（句柄非零 / 可见 / 未最小化 / 未被 cloak / 尺寸为正），
成立才断言，不成立则跳过并写明原因」，**断言语义一个字没放宽**。本轮**不再自己改这条用例**
（改法以上游为准），只把它合进来。**如实口径**：本轮它在**本机是 skip 不是 pass**
（本会话期间桌面没有可见前台窗口，跳过理由是那句前置条件），所以「全量 0 failed」里
这一条算跳过，不算已验通过。

### 10.4 本轮门禁（环境同 §9.3）

本机 Windows 11 / Python 3.13.7 / PySide6 6.11.2；`D:\dsh-pet-src\.venv` +
隔离依赖目录 `D:/dsh-pet-pr267-deps`（edge-tts 7.3.1）+ `D:/dsh-pet-pr267-deps-ocr`（omegaconf 2.4.0），
`PYTHONPATH` 用 **`;`** 分隔（§9.3 的坑），`QT_QPA_PLATFORM=offscreen`。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check .` | **All checks passed!** |
| 聚焦（本支 + 上游接缝的改动面，41 个文件） | `pytest -q`（`tests/test_tts_*` / `test_voice_chime*` / `test_divination*` / `test_settings_{interaction_tabs,page_guide,default_marks,search_aliases,copy_lint,pet_tabs,slot_config_route}` / `test_menu_layout` / `test_desktop_pet_features` / `test_config_schema` / `test_sprite_menu_parity` / `test_festival*` / `test_architecture` / `test_pr_report_discipline` / `test_overlay_{screen_migration,window_capabilities,hosts_multiscreen}` / `test_sprite_slingshot` / `test_proactive` / `test_frameseq*` / `test_no_pet_startup_notice` / `test_pet_profiles`） | **1576 passed / 3 skipped / 0 failed**（235.86 s） |
| 累计全量（按文件切 18 片、各起独立进程） | `python run_chunks_pr290.py 500`（逐片日志 `D:/dsh-pet-pr290-artifacts/chunk290-*.log`，汇总 `chunks290-final.log`） | **18 片 rc 全 0：passed 8105 / failed 0 / skipped 22 / error 0（收集 8127）** |

聚焦那 3 条 skip 与全量那 22 条 skip 都不是本支新增：本支改过的用例文件里**只有**
既有的 `QtMultimedia 不可用` 守卫（7 处，早于本支）。新增用例**一条 skip 都没有**。

### 10.5 未做与边界

- **Android**：本 PR **不含任何 `android/*` 改动**——`git diff --stat origin/main HEAD -- android/`
  为空（逐字节相同）。Android 能力继承自 `main`，**不是本 PR 新增**。
- **doubao / mimo 无 API Key**：与上游同状态。可用性判定（`*-key-missing`）与失败语义有单测，
  **真实合成未测**，单列在此，不并入「已验证」。
- **真机听到抽签语音 / 右键菜单观感 / 每日提示的打扰程度**：仍需用户点验收，口径同 §5.4。
- **未改 289 / 输入 / v5 相关树的任何产品代码**：本轮对它们的文件只做合并（逐字节等于上游），未再改动。
- **本轮不重复广泛审查、不操作真实用户配置**（沿用 §9.5 的边界）。

## 十一、第五轮（2026-10-17 发布前收尾）：两条产品阻断的修复

> **起点**：`6ce64db`（第四轮累计树的 tip，**三端 CI 绿**：`PR Test Gate` run
> [38976101980](https://github.com/MerZlin/dsh-pet-indesktop/actions/runs/38976101980)，
> `head_sha=6ce64dbb…`，macOS / ubuntu / windows 三个 job 全 success）
> **本轮范围**：只修**两条产品阻断**（外部审查与独立票各出一份，本轮在本机各自独立复现），
> 不加功能、不改任何功能口径、不做广泛复审。**先红后绿**（§11.4）：新用例 5 条，改产品代码前
> 5/5 红、改后 5/5 绿。
> **上游**：`origin/main` 仍是 `e08c7fb`（本轮 `git fetch` 复核）→ 不需要额外 merge。

### 11.1 两条阻断（现场 / 根因 / 修法）

| # | 阻断 | 现场与根因 | 本轮修法（最小改动） |
|---|---|---|---|
| ① | **只开「抽签时念出来」时，通道不按用户配置合成** | `AppShell._chime_wanted()` 只认报时 / 节日语音 / 点击朗读三者：报时一关、只剩抽签语音时，`_sync_chime_service()` 把通道释放掉。抽签取通道走 `ensure_audio_channel()` → `_ensure_chime_service()` **懒创建** `VoiceChimeService`，而它构造里的 `_cfg` 是 `normalize_chime_config(None)`（模块默认：`backend="edge"`、`fallback=True`、`volume=80`），**没有任何人 `apply_config()`**（运行中的通道由 `start()` / 保存路径刷新，懒创建这条没有）。后果：选了本机 SAPI / 关掉回退 / 音量 0 的主人点抽签时**照旧联网 edge 合成、按默认音量出声**——三个设置项一个都不生效 | ① 把**真实抽签需求**纳入通道生命周期：新增 `_divination_speak_wanted()`（读 `normalize_divination_config`，与抽签服务同一处清洗，不另立第二份真值）并接进 `_chime_wanted()` 的**四个**消费者；② 在**唯一的取通道接缝** `ensure_audio_channel()` 上补"未运行就先 `apply_config()`"（沿用 `speak_self_talk` 的既有做法）。收在一处，两个抽签调用点与节日那条自动跟上，不必逐个改调用方 |
| ② | **停用抽签后，在途的揭签 / 预热重试闭包照旧执行** | `DivinationService.shutdown()` 只 `timer.stop()` 那个 10 分钟跨天定时器；而**揭签**（`_schedule_reveal` → `QTimer.singleShot(READING_GAP_MS=2800)`）、**通道轮询**（`WAITING_POLL_MS`）、**预热重试**（`PRECACHE_RETRY_MS`，上限 20 次）全是**投递出去的闭包**，停定时器管不着它们。于是关掉抽签之后：签文气泡照冒、经**共用的音频通道**出声、还把当天那段文本重新提交一次合成（真事故：在设置里关掉抽签，几秒后仍听得到签文） | 投递口 + 入口两层最小 guard：① `_after()` 的投递 wrapper 带**动身时的代次**，回调回来时代次对不上（`shutdown()` 把代次 +1）即整条丢弃——揭签 / 轮询 / 重试三条闭包一次覆盖；② `_disabled` 挡入口（`draw_now` / `hint_on_interaction` / `_precache_today`），`apply_config()` 是"重新可用"的判定点；③ `shutdown()` 顺手把 `_precache_pending` 复位——那条链已被代次作废，标记留着会让复活后的 `_precache_today` 一直以为"已有一条链在跑"，当天那段签文再也没人补合成。**不碰共用音频通道**：`shutdown()` 里没有任何 channel 调用（停用抽签 ≠ 替报时 / 节日 / 点击朗读关声音） |

### 11.2 修改文件说明（`git diff --numstat 6ce64db..` 本轮 6 个文件；含 §11.9 的 docs-only 补登提交）

| 文件 | 增删 | 改了什么 + 为什么 |
|---|---|---|
| `pet/app.py` | **+30 / −4** | 阻断①的两半：① `_divination_speak_wanted()`（3 行实现 + 注释）与 `_chime_wanted()` 的第四个分支——否则只剩抽签语音时通道会被释放；② `ensure_audio_channel()` 补"未运行就先 `apply_config()`"——否则懒创建的通道沿用模块默认（edge / 回退开 / 音量 80），用户设置全失效。原 docstring 里的"节日提醒语音复用"改写为"节日提醒语音 / 每日一签复用" |
| `pet/divination_service.py` | **+52 / −6** | 阻断②：`__init__` 加 `_disabled` / `_generation`；`apply_config()` 置 `_disabled = False`（读一次配置即"可用"）；`draw_now()` / `hint_on_interaction()` / `_precache_today()` 三处入口早退；`_after()` 的投递 wrapper 加代次比较（唯一覆盖全部延后回调的地方）；`shutdown()` 置停用 + 代次 +1 + 复位 `_precache_pending`（定时器停法不变），docstring 写清"只作废自己、不碰共用通道" |
| `tests/test_voice_chime_service.py` | **+85 / −0** | 阻断①的两条回归：① "只剩抽签语音时通道必须存在且在跑"（与节日语音 / 点击朗读同款用例，此前抽签缺这条）；② **真 `VoiceChimeService`**（不是 `_Channel` 桩）跑真抽签点击：断言合成链路只出现 `sapi`（`edge` 一出现即红）、音量 0 真落到播放器 —— 只替掉合成线程与播放器两个边界 |
| `tests/test_divination_service_timers.py` | **新增 148 行** | 阻断②的三条**时序**用例（真 `QTimer.singleShot` + 真事件循环）：揭签闭包 / 预热重试闭包在停用后不许执行、停用再启用是新代次（旧闭包全死、新实例照常揭签）；共用通道不许被停；另钉住 `shutdown()` 复位 `_precache_pending`。每条"什么都没发生"的断言都配一个**更晚到点**的控制定时器当凭据（避免"等得不够久"的假绿），不用固定 sleep 赌时序 |
| `docs/PR-REPORT-DIVINATION-2026-10-17.md` | **+179 / −0**（含 §11.9 数字补登的 docs-only 提交） | 本节（第五轮的现场 / 修法 / 先红后绿 / 消融 / 实测 / 门禁 / 边界） |
| `docs/INDEX.md` | **+1 / −1**（同一行的条目内追加一句） | 「PR 报告存档」里本报告那一行追加"第五轮"这一段（新文档入场规则不涉及新文件，但索引条目要跟内容同步） |

### 11.3 这两条为什么在"上一轮全绿"里没被抓住（口径修正，必须登记）

**"上一轮门禁绿"推不出"没有这两个缺陷"**——本轮两条都是真缺陷，且两条都在第四轮那套
（聚焦 1576 passed / 累计全量 8105 passed）里**逐条绿**。缺的是**用例**，不是门禁失效：

1. **阻断①的用例缺口**：`_chime_wanted()` 的前三个消费者**各自**都有"只剩它一个时通道必须存在"
   的用例（节日语音 `test_audio_channel_survives_on_festival_speak_alone`、点击朗读
   `test_audio_channel_survives_on_self_talk_speak_alone`），**抽签是第四个消费者却没有同款用例**；
   而"通道的配置有没有被读"此前只在**运行中的**通道上被覆盖（`start()` 会 `apply_config()`），
   唯一覆盖"懒创建 + 不 start"的是 `speak_self_talk`，那条路径还有"命中本地缓存先返回"的分支。
2. **阻断②的用例缺口**：`tests/test_divination_service.py` 的模块 docstring 明确写着"不开 Qt"，
   并把 `_after` 打桩成**立即执行**——于是"投递出去、稍后回来"这条契约在测试里**根本不存在**：
   该文件里所有"延后"用例都在验证"投递时打了什么参数"，**没有一条**验证"回来时还该不该执行"。
   这正是本轮新增 `tests/test_divination_service_timers.py` 的原因（真事件循环 + 真 `QTimer`）。
3. **结论口径**：绿是"**当时列出的不变量全绿**"，不是"无缺陷"；本轮把这两条**变成清单内的机器判据**
   （5 条新用例 + 3 组消融，见 §11.4），此后同类回归会红。

### 11.4 断言有效性（先红后绿 + 消融）

命令：`PYTHONPATH="D:/dsh-pet-pr267-deps;D:/dsh-pet-pr267-deps-ocr" QT_QPA_PLATFORM=offscreen
"D:/dsh-pet-src/.venv/Scripts/python.exe" -m pytest -q tests/test_divination_service_timers.py
tests/test_voice_chime_service.py::test_audio_channel_survives_on_divination_speak_alone
tests/test_voice_chime_service.py::test_divination_speak_uses_the_user_backend_on_a_lazily_created_channel`

| 阶段 | 命令/手法 | 结果 |
|---|---|---|
| **改产品代码前** | `git stash push -- pet/app.py pet/divination_service.py` 后重跑 5 条 | **5 failed**（日志 `D:/dsh-pet-pr290-artifacts/round5-red-before-fix.log`）；红的方式正是现场：`AssertionError: 合成链路只许出现用户选的后端，实际 ['edge']`、`抽签语音需要这条通道`（None）、旧闭包冒出了签文气泡 |
| **改后** | `git stash pop` 后重跑 | **5 passed**（1.61 s） |

消融（把修复的某一半单独放回去，证明**没有一行是摆设**）：

| 消融 | 重跑 | 结果 |
|---|---|---|
| 删 `ensure_audio_channel()` 的补读（只留生命周期那半） | 阻断①的 2 条 | 生命周期那条 **passed** / "按用户配置合成"那条 **failed**（仍是 edge） |
| 删 `_chime_wanted()` 的抽签门（只留补读那半） | 阻断①的 2 条 | "通道必须存在且在跑" **failed** / 后端那条 **passed** |
| 删 `_after()` 的投递 guard（只留 `_disabled` 入口门） | 时序 3 条 | 揭签与"停用再启代次" **failed** / 预热重试 **passed**（重试那条是入口门挡住的） |

### 11.5 性能分析（本轮实测）

**方法（可复现）**：`python .scratch/divination-pr290/probe_round5_perf.py`（真机 Windows 11 /
Python 3.13.7 / PySide6 6.11.2，真 `Config`；逐字日志 `.scratch/divination-pr290/round5-perf.log`）。
量的都是本轮**新增的那几行**在稳态热路径上的成本：

| 新增点 | 实测（中位数） | 归属 / 触发频率 |
|---|---|---|
| `_divination_speak_wanted()` | **0.58 µs/次**（n=5×20000） | `_chime_wanted()` 每次多问一次（启动 + 每次配置保存 / 服务同步） |
| `AppShell._chime_wanted()` 整体 | **5.6 µs/次**（n=5×20000，其中约 0.6 µs 是本轮新增的抽签门） | 同上 |
| `_after()` 投递 wrapper 的代次 guard | **+0.45 µs/次**（对照组 = 改动前 `_after` 的逐行等价实现，同法把 `QTimer.singleShot` 打成"就地调用"以剔除 Qt 注册成本；n=5×200000） | 每日一签每天投递**个位数次**（1 次揭签 + 少量轮询 + 预热重试） |
| 入口停用门（读 `_disabled`） | **0.054 µs/次** | 每次 `draw_now` / 每日提示 / 预合成 |
| `ensure_audio_channel()` 补读，**通道在运行**时 | **+0.26 µs/次**（一次 `is_running()`） | 每次取通道（节日语音 / 抽签点击） |
| 同上，**通道未运行**时 | **+18.2 µs**（`apply_config()`，节流命中不扫目录）；每 300 s 首次含一次缓存目录扫描 **230 µs**（本机缓存目录为空） | 只在"通道还没跑起来"的分支；本修复后正常路径通道都在跑，这条基本不触发 |

逐条回答（对齐交付证据纪律）：

1. **稳态开销**：启动 / 设置保存路径多 0.58 µs；每日一签热路径（点击、揭签、重试）各多
   0.45 µs。相对一次点击本身的动画面 / 音效（毫秒级）可忽略。
2. **新增路径成本与触发频率**：`ensure_audio_channel()` 的补读只在**未运行**分支发生
   （0.26 µs → 18.2 µs，取决于通道是否已跑），运行中恒定 0.26 µs；缓存目录扫描受既有
   `_PRUNE_MIN_INTERVAL_S = 300` 节流。
3. **有无新增系统调用 / 网络 / 磁盘 / 线程**：**一条都没有**。改动只在既有函数体内加判据与闭包：
   不发网络（反而**消掉**了"该走本机 SAPI 却走 edge"的那条网络路径，见 §11.6）、不开线程、
   不新增文件读写、不新增定时器（`shutdown()` 的停表口径不变）。
4. **内存有无增长**：服务多两个标量字段（`_generation` int / `_disabled` bool）；`_after()` 每次
   投递多一个闭包，而 `QTimer.singleShot` 本就持有该回调引用，到期即释放。
5. **净收益是"不出声 / 不联网"，不是"更快"**：只开抽签语音且音量 0 的用户，点击时不再按默认
   音量 80 出声；选 SAPI 的用户不再每次点抽签都发一次 edge 网络请求（本机实测链路由
   `['edge']` 变为 `['sapi']`，§11.6）。

### 11.6 实机运行记录（本轮）

**本机真实环境**：Windows 11 / Python 3.13.7 / PySide6 6.11.2 / **真实 `windows` 平台插件**
（探针首行打印 `platform = windows`），**隔离一次性配置目录**（`tempfile.mkdtemp()` +
`PYTHON_KEYRING_BACKEND=null`），**不读用户真实配置、不联网、全程不出声**（播放器替身只记账）。

命令：`python .scratch/divination-pr290/probe_round5.py` → 日志 `.scratch/divination-pr290/round5-runtime.log`

```text
platform = windows  python = 3.13.7

--- Part A：只开抽签语音（真 SAPI 合成 / 音量 0 / 不许 edge） ---
  _chime_wanted() = True
  voice_chime_service = VoiceChimeService  is_running=True
  _cfg: backend='sapi' fallback=False volume=0
  可用合成后端链 = ['sapi']
  起播 = True  用时 0.13s
  气泡 = ['抽签中...']
  播放器音量记录 = [0.0]  起播文件 = ['db30f7db2b02c6de.wav']
  缓存目录产物 = [('db30f7db2b02c6de.wav', 70566)]
  edge 合成调用次数 = 0（[]）

--- Part B：停用抽签（真 QTimer，真 2.8 秒揭签间隔） ---
  点下去那一刻气泡 = ['抽签中...', '抽签中...']
  3.4 秒后（> 2.8 秒揭签间隔）气泡总数 = 3
  停用那一支（2026-10-17）揭签了 = 否
  没停用那一支（2026-10-18）揭签了 = 是（对照正常）
  停用那一支的播报出现在通道里 = 否
  通道记账的播报 = ['抽签中...', '抽签中...', '今日中平签，老马识途。签']
```

- **阻断①的真机证据**：服务里的 `_cfg` 就是用户设置（`sapi / False / 0`）；可用后端链只有
  `['sapi']`；真的用**本机 SAPI（COM，零网络）**合出了一段 **70 566 字节 `.wav`**（`.wav` 只有
  SAPI 产出、edge 出 `.mp3`），从点击到起播 0.13 s；交给播放器的音量是 **0.0**；`edge` 的 `synth`
  被替换成"一调用就抛异常"，**调用次数 0**——"没走 edge"不是从日志推断，而是**真调用就会当场炸**。
- **阻断②的真机证据**：两份实例同一时刻各点一次抽签（不同日期，便于区分是哪一支），其中一份
  `shutdown()`；**真 3.4 秒**（> 真实 `READING_GAP_MS = 2800`）后，被停用的那一支**既没冒签文气泡、
  也没进通道**；没停用的那一支照常揭签 —— 对照组证明"这 3.4 秒里闭包本该回来"。
- **用户可见行为的确认**：Part A 打印了气泡文本、播放器收到的音量与文件名、缓存目录产物、
  edge 调用次数；Part B 打印了两支签的揭签与否与通道记账。
- **未验的（如实登记）**：**真机听到声音仍未验**——本轮探针只做"播放器记账"，不在用户机器上出声
  （conftest 与探针同口径）；音色 / 音量 / 间隔的听感仍留给用户点验收（同 §5.4）。
  edge-tts 的**联网耗时不测**（本轮不捏造网络数字，且修复后的正常路径根本不发这次请求）。

### 11.7 本轮门禁

环境同 §10.4（`D:\dsh-pet-src\.venv` + 隔离依赖目录 `D:/dsh-pet-pr267-deps`（edge-tts 7.3.1）+
`D:/dsh-pet-pr267-deps-ocr`（omegaconf 2.4.0），`PYTHONPATH` 分隔符是 **`;`**，`QT_QPA_PLATFORM=offscreen`）。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | **All checks passed!** |
| 先红后绿 / 消融 | 见 §11.4 | 5 failed → 5 passed；三组消融各自命中 |
| 聚焦（本支 + 上游接缝） | `bash D:/dsh-pet-pr290-artifacts/round5-focused.sh`（脚本内是 §10.4 的 41 文件清单 + `tests/test_app_lazy_imports.py`） | **1488 passed / 2 skipped / 0 failed**（243.40 s；日志 `D:/dsh-pet-pr290-artifacts/round5-focused.log`） |
| 受影响时序族高负载复跑 ×3 | `pytest -q tests/test_voice_chime.py tests/test_voice_chime_service.py tests/test_divination_service_timers.py` 连跑 3 遍 | 3 遍各 **277 passed**（10.44 / 6.38 / 6.19 s），无 flake |
| 累计全量（按文件切 18 片、各起独立进程） | `PR290_REPO=D:/dsh-pet-wt-pr290 python run_chunks_pr290.py 500`（逐片日志 `D:/dsh-pet-pr290-artifacts/chunk290-*.log`，汇总 `chunks290-final.log`） | **18 片 rc 全 0：passed 8110 / failed 0 / skipped 22 / error 0**（收集 8132；较第四轮 +5 = 本轮新增的 5 条用例） |

（聚焦那 2 条 skip 与全量的 skip 都不是本轮新增：本支改过的用例文件里只有既有的依赖 / 环境守卫；
新增的 5 条用例**一条 skip 都没有**。）

### 11.8 未做与边界（本轮）

- **只修这两条阻断**：不加功能、不改签库 / 取签 / 状态 / 播报口径，不做广泛复审（用户口径），
  未改 289 / 输入 / v5 相关树，未涉及 Android 与 DLC。
- **`speak_self_talk()` 里那处同款"未运行就 `apply_config()`"刻意保留**：两处各自成立且幂等
  （非运行分支多花 18 µs，本修复后基本不触发）；删它等于把语义挪到别处，超出本轮范围。
- **`_disabled` 入口门的产品可达面**：产品路径关闭抽签是"`shutdown()` + 引用置 None"（再启用时
  重建实例），因此入口门主要挡的是①已排进事件队列的跨天定时器 timeout、②对已停用实例的直接调用；
  本轮把它与投递 guard 一起钉成契约（§11.4 消融证明它自己也在挡重试链）。
- **真机听感 / doubao / mimo 真实合成**：仍未验（同 §10.5、§11.6 末条）。
- **未 tag、未 merge、未改 `main`**：`origin/main` 复核仍是 `e08c7fb`，本 PR 只需更新自身 head。

### 11.9 push 与 CI（同 head 快照，不等循环）

| 项 | 值 |
|---|---|
| 目标 | 作者 fork `KagurazakaChizuru/dsh-pet-indesktop` 的 `feat/divination`（PR #290 的 head 分支） |
| push 前 head | `6ce64db`（其 CI：run 38976101980 success，三端 job 全绿） |
| 本轮修复提交（= 推上去的 head） | `451b4bc`（`gh pr view` 与 `git ls-remote` 双证：PR #290 的 `headRefOid` 已指向它） |
| 同 head CI | run **38982694017**（`pull_request`，创建于 2026-10-16T23:40:47Z；快照时刻三个 job 均已建、状态 `queued`——本轮**不等循环**，只取这一次快照） |
| 本节数字的补登 | 一个 docs-only 提交（`pet/` / `tests/` 零改动）；它自己那次 CI 不在本报告内登记（避免"报告里记自己的 run"的循环） |
| 不做 | 不 merge、不 tag、不 release |
