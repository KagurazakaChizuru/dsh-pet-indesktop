# PR 报告：抽签「今日签」（每天一支）+ 48 支签文重写（2026-10-13）

- **分支**：`feat/media-window-fallback`　**日期**：2026-10-13
- **触发**：机主原话「**抽签每天只能抽一次，然后抽签文案感觉还是不太好。**」
  追问后她定了方向：文案「**能不能用那种庙里的签文类似物**」＋「**用短的吧**」。
- **范围**：5 个文件（实现 3、测试 1、文档 2——文档含本报告与设置准入记录）。
  **无新增配置键、无新增模块、无新增线程/定时器/网络。**
- **关联**：[`PR-REPORT-DIVINATION-2026-10-10.md`](PR-REPORT-DIVINATION-2026-10-10.md)（起草那轮）、
  [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 的 2026-10-13 准入记录。

> **后记（同日，甲方案轮）**：下面第 4 条「48 支签文整体重写」的**形制**随后被机主拍板的
> **甲方案**取代——**两句七言（各 7 字）+ 解曰 ≤14 字、去掉宜/忌**；气泡五行与上上签卡版式
> 随之调整（签卡不再印宜忌、加上四字典故签题）。本报告其余部分（每天一支、按日期取号、
> 记录文件口径）**不受影响**。逐条口径与 48 支新表见
> [`PR-REPORT-DIVINATION-JIA-2026-10-13.md`](PR-REPORT-DIVINATION-JIA-2026-10-13.md)。

## 一、核心特性

| # | 能力 | 说明 |
|---|---|---|
| 1 | **今日签（每天一支）** | 当天第一次点「抽支签」＝正式那一支（写记录、上上才落签卡）；当天再点＝**同一支** + 一句「今天已经抽过啦，还是这一支」，不重新摇签、不重复记账、不重复落卡；次日 0 点按本机自然日自动换新签。 |
| 2 | **签号按日期确定性取** | `splitmix64(日期 × 1000003 + 盐)` → 权重定档 → 档内均匀取；同一天永远同一支（跨进程一致），跨天分布贴合 上上4/上18/中平56/下22，且**不出现 A/B 交替**（自带混合器，不 import `random`——跨版本会漂）。 |
| 3 | **跨天「一轮不重复」** | 取号时避开**最近 7 天**抽过的签号（落在里面就确定性地顺延到下一支，仍保证同日恒定）；被排除的档当天把权重让给下一档。 |
| 4 | **48 支签文整体重写** | 形制照她认可的「渭水垂钓」样张：**四字典故签题 + 四句五言签诗 + 一句白话解（≤14 字）+ 宜/忌各 2-3 项**；签号、数量、四档分布、`LEVEL_WEIGHTS` **一律不变**。 |

**红线 / 不变量**：① 已有 3 条本机记录（10-12 下、10-13 中平、10-13 上）**不迁移、不改写**，
记录字段仍是 `ts/no/level`（老格式照读）；② `divination_speak` / `divination_animation`
两个配置键的默认值、保存链、设置页布局不动，**不新增任何配置键**；
③ 「今日宜穿色」不受影响（同日永远同一句，与签无关）；
④ `pet/divination.py` / `pet/divination_quotes.py` 仍零 Qt、零 IO；
⑤ `modern_settings_dialog.py` 2409 行（预算 2409）、`window.py` 4489 行（预算 4510）——**本轮没碰这两个文件**。

## 二、修改文件说明

`git diff --numstat`（本轮无新增/删除文件；两份文档中的 `SETTINGS-CHANGE-GATES.md` 是准入记录，
本报告是新增文档，未进 `git diff`）：

```
24	0	docs/SETTINGS-CHANGE-GATES.md
111	12	pet/divination.py
212	203	pet/divination_quotes.py
136	31	pet/divination_service.py
293	69	tests/test_divination.py
```

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/divination_quotes.py` | +212 / −203 | 48 支签**全量换文案**：新增 `title`（四字典故签题）字段，`poem` 由「七言两句」改为**四句五言**，`plain` 重写为「只给结论」的白话句（≤14 字，48 句互不重复），宜/忌补到各 2-3 项。签号 1..48、档位（4/10/24/10）、`LEVEL_WEIGHTS`、`ANIMATION_CANDIDATES` 一律不动。模块 docstring 记下她这轮的三句原话与新形制口径。 |
| `pet/divination.py` | +111 / −12 | 新增「今日签」纯逻辑：`splitmix64`（自带混合器）、`_uniform`（拒绝采样取均匀下标，避免取模偏置）、`_tier_index`（按权重定档）、`_daily_index`（档内避开 `recent`，档空则换档）、`daily_draw(day, recent)`、`recent_days(day, days)`、常量 `RECENT_DAYS=7` 与三个盐。`bubble_text` 新增可选 `note`（插在穿色行之前，既有四行一字不改），供"今天已经抽过啦"用。模块 docstring 从"不挂日期种子"改写为"两条路径：真随机 `draw` / 按日期 `daily_draw`"。 |
| `pet/divination_service.py` | +136 / −31 | ① `last_record` 的读文件逻辑抽成 `records()`（一次读全，`last_record` 改为取最后一条，坏行跳过）；新增 `record_day()`（`ts` → 本机自然日，认不出返回 `None`）、`recent_numbers()`（最近 N 天抽过的签号）、`_merge_record()`（记录只有 `ts/no/level`，按号回查签库补全签题/签诗/宜忌——重启后当天再点才念得出来）。② `draw_now` 改为走 `_daily()`：内存缓存 → 记录文件最后一条日期 → 都没有才按日期取新签；**只有新抽那次**才写记录/落签卡。③ `_record(stick, day)` 把 `day` 写进 `ts`（否则用例注入的"今天"与服务层判定用的日期会打架），`_save_card(stick, day)` 同理。④ 删掉第四轮的 `_drawn` 一轮集合（`drawn_this_round()` 保留为 0 的兼容壳，新增 `drawn_today()`）。 |
| `tests/test_divination.py` | +293 / −69 | 见第⑤条测试清单；原「一轮 48 把不重复 + 一笔一记录」用例与新口径冲突，改成"每天一支"的语义用例。 |
| `docs/SETTINGS-CHANGE-GATES.md` | +24 / −0 | 准入记录：**不新增设置项、不新增配置键**，说明为什么"每天一支"是产品语义不是偏好、以及记录文件从"每抽一行"变"每天一行"的影响与回滚。 |
| `docs/PR-REPORT-DIVINATION-DAILY-2026-10-13.md`（新增） | 本文件 | 三份交付证据 + 48 支文案的位置与样张。 |
| `docs/INDEX.md` | +1 行 | 「PR 报告存档」登记本报告（`tests/test_pr_report_discipline.py` 机器校验）。 |

**未改动（看起来相关但故意没动）**：`pet/almanac.py`（黄历穿色，机主明确说本次不动）、
`pet/divination_card.py`（签卡版式：它按 `poem` 逐行画，两句改四句只是行数变化，
760×420 画布实测仍居中不缺行——见 `.scratch/divination-card-sample.png`）、
`pet/divination_settings.py` 与 `pet/modern_settings_dialog.py`（设置页一行未动）、
`pet/app.py`（右键入口调的还是 `draw_now()`，语义变化全在服务层内）、
`pet/config.py`（无新键，所以不需要三处登记）。

## 三、48 支新文案

- **全量表格**（48 行：签号/档/签题/签诗/解曰/宜/忌）：`.scratch/divination-48-new.md`（gitignore，不进仓库）。
- **机主扫一眼用的前 8 支**：

| 签号 | 档 | 签题 | 签诗（四句五言） | 解曰 | 宜 | 忌 |
|---|---|---|---|---|---|---|
| 1 | 上上 | 渭水垂钓 | 钓竿垂处龙，不问别山风。三载空垂手，一朝入云中。 | 等得起的，都会到手。 | 投递、告白、签约 | 催、加注、争执 |
| 2 | 上上 | 高山流水 | 空谷一声琴，自有知音听。不必满城传，只须一个人。 | 说给对的人听，就有人应。 | 发出去、当面聊、约见 | 藏着、改到完美、自说自话 |
| 3 | 上上 | 水到渠成 | 水到渠自成，用力反添乱。该落的自落，伸手只推倒。 | 该成的今天自己会成。 | 收尾、确认、交付 | 反复改、临门加码、再等等 |
| 4 | 上上 | 双喜临门 | 好事不单来，门开接一双。今日皆可应，明日亦不迟。 | 今天有两样好事，别推。 | 答应、赴约、收下好意 | 推辞、挑一个、犹豫 |
| 5 | 上 | 顺水推舟 | 水顺舟自轻，一篙到岸平。顺风莫改道，省力多三成。 | 顺着现成的势头做。 | 接着推进、用现成条件 | 另起一摊、硬拐方向 |
| 6 | 上 | 东风解冻 | 一夜东风吹，冰河先自开。旧事松了口，从头说一句。 | 卡着的那件事今天会松。 | 重新开口、再试一次 | 翻旧账、算谁对谁错 |
| 7 | 上 | 灯下看字 | 灯下字须明，细处见真章。再读一遍去，省下十日忙。 | 细节再看一遍再交。 | 复核数字、读第二遍 | 凭手感、赶时间交 |
| 8 | 上 | 轻舟过山 | 轻舟过万山，回首路已平。歇口气再走，莫回头硬磕。 | 最难的已经过去了。 | 歇一口气、记下过程 | 回头硬磕、自找麻烦 |

字数体检（脚本 `.scratch/verify_divination_copy.py` 输出，48 支全量）：
签题 48 个不重复；签诗 192 句**全部五言**（4×5＝20 字）；解曰 48 句不重复、最长 14 字；
宜/忌各 2-3 项；无感叹号、无「你/我」、无医疗/投资词。四档语气按机主口径分开写：
上上＝顺、可放手做（渭水垂钓/高山流水/水到渠成/双喜临门）；上＝方向对、稳步推进（顺水推舟/东风解冻/…）；
中平＝按老办法、别加码、多看一眼（看天晾谷/量体裁衣/守株待兔/…）；下＝收、停、躲、别硬扛
（歧路亡羊/刻舟求剑/拔苗助长/螳臂当车/…，**都是"今天别做这件事"，不是凶兆**）。

## 四、实现要点

### 4.1 取号算法（`pet/divination.py`）

```text
splitmix64(value) = 三次 xorshift-multiply（常数 0x9E3779B97F4A7C15 / 0xBF58476D1CE4E5B9 / 0x94D049BB133111EB，64 位掩码）
_uniform(day, total, salt):  value = splitmix64(day.toordinal() * 1000003 + salt + step) & 0xFFFFFFFF
                            拒绝采样（value >= 2**32 - 2**32 % total 就 step+1 重取）；返回 value % total
_tier_index(day, salt):      draw_at = _uniform(day, 权重和=100, salt)；按 LEVELS 顺序减权重落在哪档
_daily_index(day, recent):   从 _tier_index 那一档起（档内全被 recent 占满就 +1 档，最多绕 4 档）
                            在候选里取 _uniform(day, len(candidates), salt) 那支的签号
daily_draw(day, recent):     按签号回查签库返回完整签（不按下标取——签库改小也不抛）
```

为什么这么写（踩过的坑，见 lesson「确定性取项」）：
① **不 import `random`**：`random.Random(seed)` 的结果在不同 Python 版本/平台上没有跨版本承诺，
   缓存键与"今天这句"都会漂；混合器自带、纯整数算术，任何进程任何版本同结果。
② **不用"按日洗牌取头一个"**：小池子上会退化成 A/B/A/B 的机械交替（一眼看得出规律）。
③ **取模不做在原始 32 位值上**：拒绝采样消掉了 `2**32 % 48 ≠ 0` 的偏置（偏置量级 1e-7，
   但既然要跨年累计，就顺手做干净）。
④ **同日恒定靠"同一天用的是确定子序列"**，不靠缓存：`_daily_index` 里每一次试算都由
   `day + salt + step` 唯一决定，所以同一天调 1 次还是 100 次都是同一支（用例钉住）。

### 4.2 与既有「一轮不重复」的关系

- 第四轮的「一轮不重复」是**一次会话内连抽 48 把不撞**（`draw(rng, exclude=...)`），
  那套**原样保留**（真随机路径仍在，设置页预览 `preview_text` 还走它）。
- 每日一签下"同一天重抽"不算新的一轮：`draw_now` 在同一天根本不会走到取号分支。
- 「不重复」跨天形态＝`recent`：`RECENT_DAYS = 7`，服务层从记录文件里取"最近 7 天（不含今天）
  抽过的签号"，交给 `daily_draw` 避开。实测 120 天链式推进**零重复**（见第⑤节用例）。
- 代价写在明处：被 `recent` 排除的档**当天不参与**，权重让给下一档——所以"带 recent"时
  单日分布不再严格等于 4/18/56/22；**`recent` 为空时严格等于**（1095 天实测每档偏差 ≤2 个百分点）。
  这是"同日恒定"与"跨天不重复"必然的取舍（同一个 `day` 不能因为历史变了而换签），
  用例把两个口径分别钉住（`..._spread_is_close_to_the_level_weights` vs `..._avoids_the_recent_window`）。

### 4.3 跨日边界

- "今天"＝**本机自然日**（`date.today()`），判定顺序：内存缓存 → 记录文件最后一条的 `ts` 日期 →
  都没有才取新签。因此**换进程/重启当天也算"已经抽过"**（记录文件是账本）。
- 同一天记录的**号**就是当天要显示的那一支：即使签库以后改了内容，重启后显示的仍是"她那天抽到的那支"
  （`_merge_record` 按号回查补文案；号不在签库里就只显示号与档，**不抛**）。
- 用例覆盖：`day=` 注入 10-13 连点 4 次（同一支、只一行记录）、10-13 起连续 5 天（5 行记录、
  至少换 4 支）、新实例重放同一天（同一支、不加行）、记录里已存在当天两条时**沿用最后一条**
  且不追加（旧记录零改写）。

### 4.4 取舍与备选

| 备选 | 为什么没选 |
|---|---|
| 每次点击重新 `draw()`，只在当天缓存内存里 | 重启即失效（同一天能抽第二次、还能再落一张签卡），与她"每天只能抽一次"不符 |
| 用 `random.Random(day.toordinal())` 固定种子 | 依赖 CPython 的 Mersenne Twister 实现细节，跨版本会漂；且 `random.seed(date)` 的相邻种子输出相关性没保证 |
| 按日 Fisher–Yates 洗牌再取第 0 位 | 小池子上塌缩成 1-2 条（lesson 实锤过）；48 支虽大，但没理由留这个坑 |
| 新增配置键控制"每天一支" | 她定的是功能本身的形状，不是偏好 ⇒ 按 `SETTINGS-CHANGE-GATES.md` 准入第 1 条不进设置页，也就不需要新键 |

## 五、性能分析

**方法（可复现）**：`D:\dsh-pet\.venv\Scripts\python.exe .scratch\bench_daily.py`
（脚本内 `timeit.repeat(..., repeat=5)` 取最快值；输出 `.scratch/daily-bench.txt`）。
环境：本机 Windows 11（Ryzen 7 5800X / 32 GB），Python 3.11.9，venv `D:\dsh-pet\.venv`。

| 指标 | 实测 | 归属 |
|---|---|---|
| `daily_draw(day)` 取号 | **13.08 µs/次**（n=100000） | 新增（每天只跑一次） |
| `daily_draw(day, recent=7 天)` | **13.05 µs/次**（n=100000） | 新增（真正走的那条） |
| `draw()`（既有真随机，对照） | **6.72 µs/次**（n=100000） | 既有 |
| `records()` 读 60 行记录 | **517.37 µs/次**（n=20000） | 既有逻辑重排（原来 `last_record` 逐行读、只解析最后一条） |
| `recent_numbers()`（读 60 行 + 算最近 7 天） | **560.27 µs/次**（n=5000） | 新增 |
| `_merge_record()` 按号回查签库 | **1.69 µs/次**（n=100000） | 新增（只在"当天再点/重启"时用） |
| `import pet.divination_service` 冷启动 | **95.8 ms**（`sys.dont_write_bytecode=True`） | 新增了一个 import（`divination_quotes`）与我加的纯函数 |

**结论**（逐条）：① **稳态开销**：抽签没有定时器、没有常驻循环，稳态开销＝0；
新增代码只在"点一下"的路径上跑。② **新增路径的绝对成本与触发频率**：一次点击＝
`records()`（517µs，读本机 jsonl，一天最多几十行）＋ `daily_draw()`（13µs）＋
（重复点时）`_merge_record()`（1.7µs），合计 **≈0.53 ms**，而后面紧接的摇签音效与 TTS
朗读是 10²–10³ ms 量级；频率＝每天 1 次（重复点击时同样量级）。③ **新的系统调用/网络/磁盘/线程**：
无网络、无线程、无定时器；磁盘只多了一次"追加一行"（本来就有）与一组**读**（≤2 次小文件读）。
④ **内存与缓存**：新增常驻只有 3 个 int 常量、1 个 list 与 2 个字段（`_last_day`/`_last_stick`，
  原来那个 48 元素的 `_drawn` set 被删掉，常驻内存是**净减**）；无新缓存。
⑤ **签卡**：`divination_card.render_card` 版式未改，四句五言在 760×420 上仍居中不溢出
  （样本图 `.scratch/divination-card-sample.png`）。

## 六、实机运行记录

命令与输出均为本机真跑（`D:\dsh-pet`，venv 3.11.9）：

- **静态检查**：`python -m ruff check .` → `All checks passed!`（改动后整仓一遍，exit 0）。
- **聚焦**：`python -m pytest -q tests/test_divination.py tests/test_divination_settings.py` → **36 passed**（7.87s）。
- **相关族**：`tests/test_config_schema.py test_desktop_pet_features.py test_menu_layout.py
  test_feature_registry.py test_no_credentials_in_source.py test_settings_and_resources.py` →
  **223 passed**（58.07s）。`test_divination.py test_divination_settings.py test_almanac.py
  test_architecture.py test_pr_report_discipline.py` → **134 passed**（7.61s）。
- **全量 `pytest -q`：单进程跑不完，如实记录。** 本机撞原生 `0xC0000005`（exit `-1073741819`），
  落点 `tests/test_proactive.py::TestUXFixesRound3::test_self_talk_yields_to_important_bubble`，
  **崩前 2943 passed + 9 skipped、0 failed**（进度点计数），faulthandler 现场栈里活跃线程是
  `imageio_ffmpeg._parsing.run` / `pet.webm_clip._reader` / `pet.mem_debug._tick_loop` /
  `overlay_shell._self_talk_loader_loop` —— 与 2026-10-13 语音页整理那轮的落点**同一条同族**
  （详见 lesson「全量 pytest 撞原生崩溃怎么办」），本轮改动不碰 webm/ffmpeg/proactive。
  ⇒ 判定为**本机既存的原生崩溃**，不宣称"全量通过"。日志 `.scratch/full-single-divination.log`。
- **为取得真实覆盖按文件切 10 片、各自独立进程顺序跑**（`.scratch/run_chunks.py`，每片 ≤500 例，崩溃自动二分）：
  `460 / 470+4skip / 406+3skip / 486 / 495+2skip / 461 / 485+3skip / 497 / 493+1skip / 256+1skip`，
  **10 片 exit 全 0**；**合计 4523 collected ＝ 4509 passed + 14 skipped，0 failed**
  （切片的 collect 总数，与 `--collect-only` 一致）。日志 `.scratch/chunks/`。
- **受影响的时序族满载复跑**：15 个烧机进程打满 CPU，跑「抽签 + 趣味设置域 + 黄历 + 菜单布局/开关
  + 桌面宠功能面 + 架构预算 + 配置快照 + 设置与资源 + 设置进程隔离 + 功能注册表 + 凭据守卫 +
  交付纪律」共 **395 例 × 3 遍，每遍 `395 passed`**（102.6s / 75.9s / 75.2s，exit 全 0）。
  脚本 `.scratch/family_load_divination.py`，日志 `.scratch/family-load-divination.log`。
  webm/ffmpeg 族本轮未碰，故未满载。
- **签文自检（真跑）**：`.scratch/verify_divination_copy.py` → 48 支、档位 `{上上4, 上10, 中平24, 下10}`、
  192 句全五言、解曰 48 句不重复且最长 14 字、无红线词；输出 `.scratch/verify-out.txt`。
- **分布探针（真跑）**：`.scratch/probe_daily.py` 取 1095 天（2026-01-01 ~ 2028-12-30）——
  无 recent 时档位占比 `中平 57.44% / 下 21.19% / 上 17.81% / 上上 3.56%`（配置权重 56/22/18/4，
  每档偏差 ≤1.5 个百分点）；带 recent 链式推进 7 天窗口内重复 **0 次**；40 天窗口出现 28-32 个
  不同签号（不塌缩）。输出 `.scratch/daily-probe.txt`。
- **真机观感**：把第 1 签（上上·渭水垂钓）用真实 `render_card` 画了一张签卡
  （`.scratch/divination-card-sample.png`）人工看过：四句五言逐行居中、分隔线与宜忌/日期都在框内。
  **未验**：桌宠真机点击一次的实际观感（气泡 5→6 行在真实窗口里的换行/截断）、
  TTS 念「四句五言 + 解曰 + 宜忌」的听感与时长、次日 0 点真跨天的那一次切换——
  这三项都需要在有 Qt 窗口的桌宠进程里过一天，本代理没有可交互桌面会话，
  只能给出上面的逻辑层与渲染层证据。

## 七、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `.venv\Scripts\python.exe -m ruff check .` | `All checks passed!`（exit 0） |
| 聚焦 | `pytest -q tests/test_divination.py tests/test_divination_settings.py` | 36 passed |
| 相关族 | `pytest -q test_config_schema / test_desktop_pet_features / test_menu_layout / test_feature_registry / test_no_credentials_in_source / test_settings_and_resources` | 223 passed |
| 受影响时序族满载 3 遍 | `.scratch/family_load_divination.py`（15 烧机进程） | 395 passed × 3，exit 全 0 |
| 全量（切片） | `.scratch/run_chunks.py` | 4509 passed + 14 skipped ＝ 4523 collected，0 failed，10 片 exit 全 0 |
| 全量（单进程） | `python -m pytest -q` | **跑不完**：原生 `0xC0000005`，崩前 2943 passed + 9 skipped（见第六节） |

**新增/修改的用例清单**（`tests/test_divination.py`，从 15 条增到 24 条）：

新增：`test_stick_title_is_a_four_character_allusion`、`test_poem_lines_are_five_characters_each`、
`test_plain_text_is_short_and_unique`（原 `test_plain_text_is_short` 扩展成含去重）、
`test_good_bad_items_are_two_or_three_each`、`test_bubble_note_sits_before_the_color_line`、
`test_daily_draw_is_constant_within_a_day`、`test_daily_draw_next_day_is_not_todays_stick`
（含"非 A/B/ABC/ABCD/ABCDE 周期"的机械规律反例）、`test_daily_draw_avoids_the_recent_window`、
`test_daily_draw_spread_is_close_to_the_level_weights`（1095 天，每档 ±2 个百分点）、
`test_daily_draw_does_not_collapse_on_a_short_window`（40 天 ≥15 支）、
`test_splitmix64_gives_a_deterministic_sequence`、
`test_daily_modules_do_not_import_random_for_the_pick`（源码级守卫）、
`test_recent_days_are_before_the_day_and_oldest_first`、
`test_service_second_click_same_day_repeats_the_stick`、
`test_service_next_day_gets_a_new_stick_and_a_new_record`、
`test_service_restart_keeps_todays_stick`（含"按号补回签题/签诗/宜忌"）、
`test_service_null_history_dir_still_works`、
`test_service_history_file_stays_readable_for_settings_page`（旧记录零改写）。

改写：`test_stick_library_shape`（签诗两句 → 四句）、`test_level_distribution_matches_reference`
（档位 4/10/24/10）、`test_all_text_has_no_exclamation_or_health_claims`（加投资词与人称守卫）、
`test_service_works_without_a_window` / `test_service_obeys_speak_switch`（补 `day=` 注入与临时 config 目录，
否则第二次调用会撞上每日配额）。

删除：原 `test_service_round_has_no_repeats_and_records_history`（"一次会话连抽 48 把不重复、
48 行记录"与新口径直接冲突）——它的两个意图分别由 `test_daily_draw_avoids_the_recent_window`
（跨天不重复）与 `test_service_second_click_same_day_repeats_the_stick`（记录行为）承接。

## 八、已知限制与后续

1. **单进程全量 pytest 的原生崩溃本轮不处理**（既存、非本次引入、有同族先例），已如实登记。
2. **"每天一支"按本机自然日**：改系统日期即可换签（这是本机单机玩具的合理边界，
   不引入服务器时间/防作弊）。
3. **`recent` 窗口是 7 天**：48 支签下 7 天内不会重复；抽满 7 天后旧号解禁。
   若机主觉得"回来抽到上个月那支"没劲，把 `RECENT_DAYS` 调大即可（纯常量，用例按常量取值）。
4. **上上签卡仍然是每天最多一张**：当天已经抽过的上上，重启后再点不会重复落卡
   （用例 `..._second_click...` 的 `cards <= 1` 断言）。
5. 未验项见第六节末（真机观感/TTS 听感/真跨天），需要一天的桌面会话才能补。

## 九、风险与回滚

- **影响面**：只有右键「抽支签」这一条路（`app.py` 一行调用没动）+ 三支本机记录文件格式未变。
- **配置迁移**：**无新增键、无默认值变更**，所以没有迁移路径；设置页两个开关行为不变。
- **数据兼容**：`divination-history.jsonl` 老记录（10-12 下 / 10-13 中平 / 10-13 上）照读；
  新记录字段不变。回滚后的表现：旧代码只按 `ts/no/level` 读最后一条，能正常显示。
- **回滚步骤**：`git revert` 本轮 5 个文件的改动即可；**注意回滚会让"每天一支"消失**
  （回到每次点击真随机），本机记录文件里已经存在的"每天一行"数据仍可读，无需清理；
  `.scratch/` 下的脚本与产物全在 gitignore 内，不影响仓库。
