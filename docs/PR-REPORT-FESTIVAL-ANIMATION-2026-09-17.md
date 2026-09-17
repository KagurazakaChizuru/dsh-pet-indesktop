# 节日提醒 × 内置动画绑定 PR 报告

> **承接关系**：`#127`「节日提醒」（合并提交 `be9a6d0`）的**增量迭代**。按 `DEV-HANDOVER`
> §8.2 从 `main` 新起承接分支 **`feat/festival-reminder-v2`**，父报告
> `docs/PR-REPORT-FESTIVAL-REMINDER-2026-09-16.md` 已按 §8.3 追加「七、第二轮迭代」章节
> （不修改既往章节）。
>
> **状态（2026-09-17，含独立审核修复轮）**：分支 `feat/festival-reminder-v2` 已推 **5 个提交**（功能 → smoke 校准 → 生日文案/守卫 → 日志定稿 → 审核修复）；PR [#131](https://github.com/MerZlin/dsh-pet-indesktop/pull/131)，早先一轮 CI 在 `112a327` 上**三平台全绿**，修复轮推送后 CI 重新触发。修复轮后本地门禁：ruff 通过、守卫族 226 passed、全量 **2386 passed / 11 skipped / 0 failed**、`.\run-gates.ps1` = ALL GATES PASSED。
>
> 结论先说：给节日提醒加了**画面**——命中节日当天，桌宠在气泡（可选语音）之外再播一段
> 与节日氛围匹配的**内置动画**（中秋「中秋赏月吃月饼」、端午「吃粽子」、腊八「吃腊八粥」…）；
> 并支持**用户自定义生日**，生日当天播「端蛋糕送礼物」。当天只播第一次，手动
> 「今日节日」与设置页「立即试听」每次都播；素材对不上（换角色 / 外部 DLC）时**先退关键词级、
> 再退季节兜底**，都没有才不播（只出气泡，不报错、不刷日志）。

---

## 一、核心特性

1. **46 个节日/节气的动画绑定**：新建纯数据映射表 `pet/festival_animations.py`，
   键为 `Festival.id`（`zhongqiu` / `duanwu` / `labajie` …），值为候选动画名（按优先级）。
2. **三级降级，永不硬失败**：精确表 → 关键词表 → 节气季节兜底 → `None`（静默跳过）。
   24 节气全部能播出一段；仅有复活节/母亲节/父亲节确属素材空白（刻意保留，显式登记）。
3. **用户生日**（`festival_birthday`，`MM-DD`）：当天按节日提醒处理（气泡 / 可选语音 /
   「端蛋糕送礼物」动画）。生日是**个人日期**，不受「中国节日/节气/西方节日」三类开关约束；
   与节日撞同一天时**生日优先**（文案与动画都取 `hits[0]`）。生日文案用专属祝福主句
   「今日是你的生日，祝你生日快乐，健健康康。」（不套"今天是X。"模板 + 诗词引文；自定义中文文案仍会追加）。
4. **只播主窗、当天只播第一次**：与节日气泡同口径；一天 1–6 次提醒不会把同一段动画播 6 遍。
5. **不打断用户操作**：优先 `request_link_anim`（正在播的一次性动作/点击回应/移动不被打断，
   节日动画排队等它播完），退化到 `switch_clip(link_request=True)`。
6. **两个新开关**：`festival_reminder_animation`（默认开）、`festival_birthday`（默认空）。
7. **零架构改动**：`window.py`（4507/4507）与 `modern_settings_dialog.py`（2311/2311）
   **一行未动**；全部落在服务层 + 新模块 + 设置页自有文件。

## 二、修改文件清单

**新增（2）**

| 文件 | 行数 | 说明 |
|---|---|---|
| `pet/festival_animations.py` | 226 | 纯数据 + 纯函数，**零第三方依赖**（仅 `__future__`/`typing`）；映射表、关键词表、季节兜底表、`pick_animation()`、`all_animation_names()`、`KNOWN_GAPS` |
| `docs/PR-REPORT-FESTIVAL-ANIMATION-2026-09-17.md` | 本文件 | — |

**修改（10）**

| 文件 | 增/删 | 说明 |
|---|---|---|
| `pet/festival_service.py` | +65/-2 | `_play_festival_anim()`；三处触发点（`remind_now` / `_catch_up` / `_on_tick`）各加一行；**按 (日期, 节日id) 去重、且只在确认开播后才记账**；`remind_now(now=None)` 增加可注入时间（与 `_on_tick` 同构） |
| `pet/festival.py` | +75/-4 | `DEFAULT_ANIMATION`、`clean_birthday()`（**锚定 + 拒年份**，见 §八）、`today_festival()`、`normalize_festival_config` 加 `animation`/`birthday`、`festivals_on` 追加**动态生日节日**并让生日排最前 |
| `pet/festival_data.py` | +9 | `KIND_BIRTHDAY`、`BIRTHDAY_ID`、`BIRTHDAY_FESTIVAL`（**不进** `FESTIVALS`，见 §3.2） |
| `pet/config.py` | +10 | 两个新键的默认值 + `reload()` 白名单 |
| `pet/festival_settings.py` | +35/-3 | 「节日动画」「我的生日」两行 + `apply_to_config`/`refresh_from_config`；校正文档里「11/10 键」陈旧数字 |
| `tests/test_festival.py` | +518/-2 | `_Win` 假窗改用**真实素材池**（原取自映射表 → 假绿，见 §八）+ 动画/生日记录器；**新增 31 个用例** |
| `tests/smoke.py` | +36/-4 | 三处陈旧断言按当前素材与平台语义校准；素材数量改**下界**+核心动画+文件存在性（原写法与 library 同源、是同义反复，见 §八） |
| `tests/test_architecture.py` | +1 | `festival_animations.py` 进「纯逻辑层零 Qt」白名单 |
| `tests/test_config_schema.py` | +6/-3 | 白名单快照 +2 键；校正陈旧计数（80/75/10 键 → 123/119/13 键） |
| `docs/PR-REPORT-FESTIVAL-REMINDER-2026-09-16.md` | +24 | 按 §8.3 追加「七、第二轮迭代」章节 |

**刻意未改**：`pet/window.py`（预算零余量）；`pet/modern_settings_dialog.py` 只把 1 行陈旧注释从「10 键」改成「13 键」，**行数不变**（2311/2311）；
`pet/catalog.py::ANIM_FILES`（51 名双冻结且运行时不用）、`festival_quotes_*.py`（生日不新增文案库条目）。

## 三、实现要点

### 3.1 素材名以真实文件 stem 为准，且必须按当前角色动作池过滤

`pick_animation(festival_id, available)` 的所有返回值都取自调用方传入的 `available`
（`PetWindow.acts`）。两条硬事实决定了这个设计：

- **换角色是整窗重建**（`app.py:527-566`，新库新分类），外部 DLC 角色包不一定有内置素材名；
  直传写死的名字会打到窗口缺名守卫（`window._switch` 的 `lib.names()` 检查）上，
  **每次提醒刷一条 "动画启动被拒绝" 的 warning**。
- 名字对不上时**静默跳过**才是正确观感：提醒本身（气泡/语音）不受影响。

**不能抄 `catalog.ANIM_FILES`**：那个 dict 只列 51 个名字（真实 106 个），其中 5 个名字对不上
任何真实文件，且被 `assert len(ANIM_FILES) == 51` 与 `tests/test_runtime.py` 双重冻结。
`test_mapped_animations_use_real_asset_names` 是针对这类"名字悄悄脱节"的机器化护栏。

### 3.2 生日是「动态节日」，不碰静态表与文案库

生日日期来自用户配置，因此**不加入** `FESTIVALS` / `FESTIVALS_BY_ID`：

- `festival_data.BIRTHDAY_FESTIVAL` 是模块级常量，由 `festivals_on` 在命中当天**追加**到
  命中列表（并排到最前）。这样 `test_festival_ids_are_frozen`（静态 id 快照）、
  `test_quote_libraries_have_no_orphan_keys`（文案库键集合 == 节日 id 集合）等护栏
  无需为"一个用户可配的日期"而放宽。
- 文案：`QUOTES_CN` 没有 `shengri` 键 → 只有「今天是你的生日。」，用户的
  「自定义中文文案」仍按既有规则追加（`quote_pool` 对空内置池返回 `""`，无需改动）。
- 排序键改为 `(生日优先, 类别序, 名字)`，顺带用 `default=99` 兜住空类别元组。

### 3.3 三级降级

```text
pick_animation(festival_id, available)
  ① 精确表 FESTIVAL_ANIMATIONS[id] 按优先级取第一个 ∈ available
  ② 关键词表 FESTIVAL_ANIMATION_KEYWORDS[id]：available 里按字典序取第一个命中的
  ③ SOLAR_TERM_SEASONS[id] → SEASON_ANIMATIONS[season] 取第一个 ∈ available
  ④ 都没有 → None（服务层静默跳过，不打日志）
```

第 ② 步按**字典序**遍历，保证同样输入永远得到同样输出（可测）。第 ③ 步让 24 节气——
包括雨水/谷雨/小满/芒种/处暑/白露这 6 个没有专属素材的——都能播出一段时令相符的通用动画
（春：放风筝/开花；夏：摇扇纳凉/吃西瓜；秋：被落叶淹没/吃大闸蟹；冬：堆雪人/涮火锅/吃糖葫芦/吃饺子）。

### 3.4 服务层接线（`festival_service.py`）

| 触发点 | 调用 | 语义 |
|---|---|---|
| `remind_now()`（右键「今日节日」/设置页试听） | `_play_festival_anim(day, force=True)` | 每次都播 |
| `_catch_up()`（开机补提醒） | `_play_festival_anim(day)` | 当天首次 → 播 |
| `_on_tick()`（30s tick 到点） | `_play_festival_anim(day)` | 当天已播则跳过 |

- 三处都在既有 `if text:` 之内 —— **当天无节日时既不弹气泡也不播动画**。
- 去重靠 `self._anim_day`（只在真正发起播放时置位），跨天自然失效。
- 动画播完的收尾（进 gap、回随机链）**由窗口负责**，服务侧不做任何善后。
- `remind_now(now=None)` 新增可选时间参数：生产路径取系统当前时间，测试注入固定日期。

## 四、测试与验证

### 4.1 门禁

| 门 | 命令 | 结果 |
|---|---|---|
| 门1 静态检查 | `ruff check pet/ tests/` | `All checks passed!` |
| 门2 守卫族 | `pytest tests/test_architecture.py tests/test_config_schema.py tests/test_menu_layout.py tests/test_voice_chime.py -q` | **226 passed** |
| 门3 全量 | `pytest -q` | **2386 passed / 11 skipped / 0 failed**（185.24s）｜修复轮后复跑 |
| CI | GitHub Actions `test (windows / ubuntu / macos-latest)` | **三平台全部 success**（head `112a327`） |
| 附加 | `python -m compileall -q pet packaging scripts` | exit 0 |

`.\run-gates.ps1` 汇总输出：`ALL GATES PASSED`（exit 0）。对照上一轮（节日提醒 PR，2026-09-16）：
2279 passed / 10 skipped / 0 failed；差额来自期间合入的其它 PR 与本轮新增的 17 个用例。
既有用例**语义未改**，只给 `_Win` 假窗补了动画记录器（否则新副作用测不到）。

### 4.2 端到端冒烟（真实窗口 + 真实素材）

用**真** `PetWindow`（真 `MovieLibrary`、真 webm、真 `_switch` 链路）驱动真实服务，
素材指向**已安装版 107 段包**（含「端蛋糕送礼物」；仓库素材缺这一段）。18 个场景全部符合预期：

| 场景 | 日期 | 命中 | 选中动画 | 窗口实际 anim |
|---|---|---|---|---|
| 春节 | 2026-02-17 | 春节 | 收红包 | 收红包 |
| 除夕 | 2026-02-16 | 除夕 | 吃饺子 | 吃饺子 |
| 元宵节 | 2026-03-03 | 元宵节 | 吃汤圆 | 吃汤圆 |
| 端午节 | 2026-06-19 | 端午节 | 吃粽子 | 吃粽子 |
| 七夕节 | 2026-08-19 | 七夕节 | 穿针乞巧 | 穿针乞巧 |
| 中元节 | 2026-08-27 | 中元节 | 放河灯 | 放河灯 |
| **中秋节** | 2026-09-25 | 中秋节 | **中秋赏月吃月饼** | 中秋赏月吃月饼 |
| 重阳节 | 2026-10-18 | 重阳节 | 插茱萸赏菊 | 插茱萸赏菊 |
| 腊八节 | 2027-01-15 | 腊八节 | 吃腊八粥 | 吃腊八粥 |
| 清明节 | 2026-04-05 | 清明节 | 吃青团 | 吃青团 |
| 夏至 | 2026-06-21 | 夏至 | 摇扇纳凉 | 摇扇纳凉 |
| 冬至 | 2026-12-22 | 冬至 | 吃饺子 | 吃饺子 |
| 雨水（无专属素材→季节兜底） | 2026-02-18 | 雨水 | 放风筝 | 放风筝 |
| 万圣节 | 2026-10-31 | 万圣节 | 讨糖南瓜灯 | 讨糖南瓜灯 |
| 圣诞节 | 2026-12-25 | 圣诞节 | 装点圣诞树 | 装点圣诞树 |
| **我的生日** | 2026-10-24 | 你的生日 | **端蛋糕送礼物** | 端蛋糕送礼物 |
| 生日撞春节（生日优先） | 2026-02-17 | 你的生日 | 端蛋糕送礼物 | 端蛋糕送礼物 |
| 复活节（刻意缺口） | 2027-03-28 | 复活节 | —（无素材） | 待机呼吸休闲（不播） |

冒烟进程退出码 0，结论 `=== 冒烟结果: 全部符合预期 ===`；另生成 17 格首帧对照图
（曾生成 17 格首帧对照图供肉眼确认；该临时产物已清理，脚本可重建。）

**红-绿对照**（证明新用例确实承重）：临时把 `_play_festival_anim` 替换为 no-op 后，
中秋当天的 `anim_requests` 从 `["中秋赏月吃月饼"]` 变成 `[]`，而气泡数保持 1 不变——
既证明断言由新代码路径决定，也证明"动画"与"提醒本身"解耦。

### 4.3 顺带发现的既有问题（**不在本轮改动范围**）

`tests/smoke.py`（仓库自带冒烟）第 44 行断言 `len(names) == 51`，而真实素材已是 **106 段** →
该脚本当前必红（`AssertionError: 106`）。这是素材扩充后未同步的历史遗留，与本轮改动无关，
本轮已在 `8f5d3d8` 校准（见 §4.5 与 §八）。

### 4.4 实机演示（真窗口 + 真语音）

用**真** `PetWindow` + 真 `VoiceChimeService`（edge-tts 合成 + QMediaPlayer 播放）+ 真
`FestivalReminderService` 跑了两轮桌面实机演示（配置写在临时目录，不碰用户真实配置）：

| 演示 | 做法 | 结果 |
|---|---|---|
| 圣诞节全链路 | 日期冻结 `2026-12-25`、时钟走真实时间 | 启动补提醒 + 两次到点 tick + 手动入口：气泡 4 次、动画请求 2 次（当天只播一次 + 手动重播）、真 edge-tts mp3 3 个；圣诞动画播完自动回随机链 |
| 生日提醒 | `festival_birthday=03-15`，日期冻结 `2027-03-15` | 命中对照：前一天/后一天/清空生日**均不提醒**，仅当天命中「你的生日」；到点播「端蛋糕送礼物」，第二次到点不重播、手动入口重播；同句语音走缓存只合成 1 个 mp3 |

### 4.5 本轮提交（分支 `feat/festival-reminder-v2`）

| 提交 | 内容 |
|---|---|
| `1ca34af` | feat: 节日提醒绑定内置动画 + 用户生日（承接 #127 第二轮迭代） |
| `8f5d3d8` | fix: `tests/smoke.py` 断言按当前素材与平台语义校准（51 段写死 / Windows `mask()` 语义 / 脱节的 `catalog.CLICKS`） |
| `112a327` | feat: 生日文案改为专属祝福 + 补设置页新行的域收集/写回守卫 |

## 五、已知限制与后续

1. **3 个西方节日无素材**：复活节、母亲节、父亲节在标准素材包里没有氛围相符的动画，
   当天只出气泡不出动画（`KNOWN_GAPS` 显式登记 + 用例锁死；补素材后用例会变红提醒）。
2. **`端蛋糕送礼物` 只随已安装版发布**：仓库 `assets/` 暂缺这一段，映射表里为生日与情人节
   登记的它只对已安装版生效；对仓库素材运行时该动画静默跳过（冒烟已分别验证两种素材集）。
3. **生日需要总开关**：`festival_birthday` 之外还要开启「启用节日提醒」（与其它节日一致，
   设置页提示文案已写明）。
4. **只播主窗**：多开的小肥鱼（子窗）不会跟着播；要"所有桌宠一起赏月"需经
   `MultiWindowProxy`（`multi_window_shared.py:160`）扇出，属需先定架构的改动，本轮未做。
5. **没有用户自定义绑定 UI**：当前是内置映射表 + 关键词兜底。若后续要"用户给每个节日自选动画"，
   可仿 `click_talk_bindings`（`character_profiles` 下的 `{动画id: [台词]}` + `click_talk_dialog.py`）。
6. **未验证**：GIF 变体与节日动画的共存（仓库无 `assets/characters_gif`，同步测试自动 skip）；
   时区/夏令时下的日期边界（与既有 `reminder_slot` 同风险）。

## 六、风险与回滚

| 风险 | 缓解 |
|---|---|
| 动画打断用户操作 | 走 `request_link_anim`（不打断一次性动作），必要时排队；退化路径才用 `switch_clip` |
| 换角色/外部素材缺名 → 报错 | `pick_animation` 只在当前 `acts` 里挑，缺失即 `None`；`test_missing_material_is_silent_noop` |
| 生日填错导致"每年错日子跳出来" | `clean_birthday` 拒绝 02-30 / 13-01 等不存在的日期，静默落空 |
| 一天多次打扰 | 当天只播第一次；手动入口由用户显式触发 |
| 新增配置键漏登记 | 三处登记齐全（默认 dict + reload 白名单 + `test_config_schema.py` 快照），已跑绿 |
| 动了用户自己的节日模块 | 生日走**动态节日**路径：静态 id 快照、文案库键集合护栏均未放宽 |
| 行数预算 | `window.py` / `modern_settings_dialog.py` **一行未动** |
| 素材名脱节（`ANIM_FILES` 式隐患） | `test_mapped_animations_use_real_asset_names` 机器化护栏 |

**回滚**：删除 `pet/festival_animations.py` + 回退 10 个修改文件的 diff 即可完全回滚；
或用户侧把设置页「节日动画」关掉（`festival_reminder_animation=False`）+ 清空「我的生日」，
服务层即完全不进入动画分支。

---

---

## 七、独立审核与修复轮（2026-09-17）

功能提交完成后，另开**三个全新会话**做独立审核（不给它们作者的结论，只读仓库，允许在
`%TEMP%` 的 `git archive` 副本里做缺陷注入）：

| 审核员 | 角度 | 方法 | 结论 | 发现 |
|---|---|---|---|---|
| A | 逻辑正确性与边界 | 反例构造 + 真窗口端到端 | 有需修问题，核心链路成立 | 1 MAJOR + 3 MINOR |
| B | 架构与工程纪律 | 对照仓库自身规则逐条核对 | **架构可交付**（红线零绕过） | 3 MAJOR（全在报告/记录）+ 5 MINOR |
| C | 测试有效性与回归 | **25 组缺陷注入** | **不足以支撑交付** | **1 BLOCKER + 8 MAJOR** + 8 MINOR |
| （作者自审） | 安全 / 静态缺陷 | ruff `S/B/PLW` + 危险构造扫描 + ReDoS 计时 | 未引入新安全问题 | 3 MINOR |

### 7.1 发现（合并去重）

| 级别 | 问题 | 位置 |
|---|---|---|
| BLOCKER | **假绿**：假窗动作池取自被测实现自己的映射表（`all_animation_names()`），生日动画用例永远不会红；换真实素材池后 `pick_animation("shengri")` 实为「拆礼物」 | `tests/test_festival.py`（`_Win`） |
| MAJOR | **代码 bug**：`clean_birthday` 用不锚定的 `search` 取"第一组数字"，把 `2005-03-15` 解析成 `05-03` → 每年在**错误的日子**提醒（972 个 YYYY-MM-DD 输入：144 错日 / 828 落空 / 0 正确） | `pet/festival.py` |
| MAJOR | 「当天只播第一次」是**空断言**：第二枪打 15:00，而提醒点是 09:00/21:00，`_on_tick` 在槽位判定处就返回 | `tests/test_festival.py` |
| MAJOR | 排序用例不承重：春节的「春」(U+6625) > 「你」(U+4F60)，删掉"生日优先"排序键仍绿 | `tests/test_festival.py` |
| MAJOR | `festival_reminder_animation` 的设置页写回/刷新**零覆盖** | `pet/festival_settings.py` |
| MAJOR | `win is None` / `isVisible()=False` / `today_festival` / `_anim_day` 跨天 / `_catch_up` 播动画：五处**零覆盖** | `pet/festival_service.py`、`pet/festival.py` |
| MAJOR | 「缺素材静默跳过」只覆盖空池，未覆盖"池非空但无任何匹配名" | `tests/test_festival.py` |
| MAJOR | `tests/smoke.py` 的素材数量断言与 `library` **同源**（同义反复）→ 删掉 40/106 段素材仍 PASS | `tests/smoke.py` |
| MAJOR | 报告漏记 `smoke.py`、§4.3 与 §4.5 自相矛盾、`festival_animations.py` 186→实测 226、"17 个新用例"→实测 20、提交数与 CI head 不符 | 本报告 |
| MINOR | `pytest.skip` 可静默关掉唯一名字护栏；`DEFAULT_ANIMATION` 值无测试；`clean_birthday("1990-10-24")==""` 未文档化；注释宣称"缺素材静默跳过"与实测（关键词兜底到「拆礼物」）不符；`valentine` 有错误的 `KNOWN_GAPS` 交叉引用；退化支 `switch_clip` 实为不可达且其语义是**立即切**（会打断）；`_catch_up` 无时间注入点 | 多处 |

### 7.2 修复内容

| 项 | 修法 |
|---|---|
| 生日解析 | `clean_birthday`：长度上限 32 + **拒 3 位以上连续数字**（带年份不猜）+ 整串 `fullmatch` |
| 当天去重 | 记账键改 `(日期, 节日id)`、跨天自动复位；**只在确认开播后记账**（`switch_clip` 返回值 / 公有 `win.anim == name`）；请求只排队（未确认）时不记账 → 留给下一个提醒点**补播**（宁可补播也不丢，见 §7.5） |
| 假绿 | 假窗动作池改取**真实素材 stem**；生日用例拆成三条：映射优先级单测（池显式含蛋糕素材）/ 真实素材池断言（缺素材则 `skipif`）/ 缺素材兜底到「拆礼物」 |
| 空断言 | 第二枪改打 **21:00**（真实第二提醒点），并先断言该点确实会触发提醒、且确实出了气泡 |
| 排序不承重 | 基准日改撞**中秋节**（「中」U+4E2D < 「你」U+4F60），文案断言改精确相等 |
| 覆盖缺口 | 新增：设置页 animation 往返、`win is None`、不可见、多命中口径（文案与动画同源）、跨天复位、`_catch_up` 播动画、未确认请求补播、带年份回归（全量 YYYY-MM-DD）、`DEFAULT_ANIMATION` 默认值、两表同键/季节表恰覆盖 24 节气 |
| smoke 同义反复 | 换成**非同源**断言：素材数量下界（`MIN_EXPECTED_CLIPS = 100`，实测 106）+ 核心动画（idle/turn/drag/moves）必须在库 + 每个名字必须解析到真实存在文件 + 所选 click 素材文件必须存在 |
| 注释/文档 | 「零 import」→「零第三方依赖」；缺素材行为与注释对齐；删掉 `valentine` 的 `KNOWN_GAPS` 错误引用；「12 键」→13、「10 键」→13；报告与 `DEV-ENV`/`DEV-HANDOVER` 的数字、提交数、CI head 全部对齐；**明确标注 `tests/smoke.py` 不在 pytest/run-gates/CI 覆盖内** |

### 7.3 修复后验证（缺陷注入，与审核员 C 同法）

在 `%TEMP%` 只读副本里逐条注入缺陷后跑对应用例，**11/11 全部如预期变红**：

| 注入 | 目标用例 | 结果 |
|---|---|---|
| 去掉当天去重守卫 | `test_tick_plays_matching_animation_once_per_day` | 红 ✓ |
| 记账键去掉日期 | `test_animation_is_played_again_on_the_next_festival_day` | 红 ✓ |
| 去掉可见性检查 | `test_invisible_window_does_not_burn_the_days_chance` | 红 ✓ |
| 去掉 `win is None` 守卫 | `test_no_window_does_not_burn_the_days_chance` | 红 ✓ |
| `_catch_up` 提前返回 | `test_startup_catch_up_plays_the_animation` | 红 ✓ |
| 去掉生日优先排序键 | `test_birthday_sorts_before_a_festival_on_the_same_day` | 红 ✓ |
| `today_festival` 改取 `hits[-1]` | `test_text_and_animation_follow_the_same_festival_on_a_multi_hit_day` | 红 ✓ |
| 去掉年份闸门 | `test_clean_birthday_rejects_year_prefixed_and_multi_segment_inputs` | 红 ✓ |
| `pick_animation` 不做池过滤 | `test_missing_material_is_silent_noop` | 红 ✓ |
| 设置页不写回 animation | `test_animation_setting_round_trips_through_the_page` | 红 ✓ |
| 映射表删掉 `shengri` | `test_birthday_prefers_the_cake_animation_over_keyword_fallback` | 红 ✓ |

`tests/smoke.py` 的非同源验证：正常仓库 PASS；副本里删掉 40/106 段 → `AssertionError: 素材疑似丢失：66 < 100`；只删 `idle/` → `AssertionError: 核心动画缺失：待机呼吸休闲`。

### 7.4 修复后门禁

`ruff` All checks passed ｜ 守卫族 **226 passed** ｜ 全量 **2386 passed / 11 skipped / 0 failed**（185.24s）｜ `.\run-gates.ps1` = **ALL GATES PASSED**。
11 个 skip 里有 1 条是本迭代新增：`端蛋糕送礼物` 只随已安装版发布、仓库素材缺该段 → 用例显式 `skipif` **暴露缺口**，而不是让假窗把素材"变出来"。

### 7.5 未修 / 已决策

- **F2 语义**已按「宁可补播也不丢」落地：未确认开播就不记账（极端情况下同一天可能补播一次）。若要严格"一天只播一次"，把未确认请求也记账即可，代价是重新引入"偶尔一次都不播"。
- **`02-29` 生日**：行为保持"仅闰年提醒"，已在设置页说明与占位符写明。
- **`switch_clip` 退化支**：真实窗口都提供 `request_link_anim`，该支实为不可达；保留作兜底，但文档不再宣称"不打断"（它的语义是立即切）。
- **多窗口**：仍只播主窗（与气泡同口径），多开小肥鱼不跟着播。

---

*（内容由 AI 生成，仅供参考；测试数字以 §4.1 门禁结果为准。）*
