# 抽签（右键「抽支签」，2026-10-10）

> **基线**：集成分支 `feat/media-window-fallback`，`d56cce1`（2026-10-04 合并上游 `beaa8f5`）
> **日期**：2026-10-10　**实测用例数**：`tests/test_divination.py` 11 例
> **关联**：[`PR-REPORT-DIVINATION-2026-10-10.md`](PR-REPORT-DIVINATION-2026-10-10.md)（交付证据）、
> [`PR-REPORT-FESTIVAL-REMINDER-2026-09-16.md`](PR-REPORT-FESTIVAL-REMINDER-2026-09-16.md)（气泡门禁与音频通道先例）、
> [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)（设置行准入/准出）
> **它是「趣味 · 占星 / 每日运势」的替代品**：那套（星历 + 本命盘 + 出生信息）已于
> 2026-10-10 按机主决定废除并归档在 `.scratch/fortune-astrology/`（含补丁与临时分支
> `backup/fortune-astrology-20261010`），**不要**把它的复杂度带回来。

## 一、这是什么

桌宠右键菜单的一个**娱乐向**入口：点「**抽支签**」→ 抽一支签（真随机）→ 桌宠动一下、
气泡出签文、语音念出来。**不联网、不读任何个人信息、不挂日历**——签是抽的，抽完就完。

**点一次拿两样**（机主 2026-10-10 定的口径「合并进抽签不就好了」）：签文之后**顺带给出
今日宜穿的颜色**（黄历，按当日日柱天干五行推，见第五节）。所以气泡是五行、语音末尾多一句：

```
第 7 签 · 上
轻舟已过万重山，回首方知行路难。
难的已经过去了。
宜 歇一口气 · 忌 回头硬磕
今日宜穿 青绿 · 避 藏青
```

一签的其余形状（机主 2026-10-10 拍板"按默认来"）：

* **签号 + 吉凶**四档：上上 / 上 / 中平 / 下，权重 4 / 18 / 56 / 22（**上上少见、中平最多**）；
* **签诗**两句（庙签味），**白话解 ≤14 字**（她嫌占星那版文案"太长太拖沓"，这次签文天生短）；
* **宜/忌**各一条，都是能立刻做的动作；
* 语音只念「签号 + 吉凶 + 白话解 + 宜忌 + 今日穿色」，**一句话念完**。

## 二、模块与分层

dsh-pet 设置里的位置：**侧栏一级域「趣味」**（在「文件识别」后、「更新」前），域内两节——
**抽签**（两个开关）/ **今日穿色**（只读预览，每天自动变）。

| 文件 | 层 | 职责 |
|---|---|---|
| `pet/divination_quotes.py` | 纯数据（零 Qt） | **24 支签**：签号/吉凶/签诗两句/白话解/宜忌 + 四档权重 + 摇签动作候选 |
| `pet/divination.py` | 纯逻辑（零 Qt） | 加权抽签（可注入 `random.Random`）、配置清洗、气泡/语音文本组装（含黄历穿色行） |
| `pet/almanac.py` | 纯逻辑（零 Qt） | **黄历穿色**：日柱干支（六十甲子锚点）→ 日干五行 → 宜穿/次吉/避 + 冲煞 |
| `pet/divination_service.py` | IO/UI 边缘 | 摇签动作 → 气泡（与节日提醒同一套门禁与降级链）→ 经既有音频通道朗读；**无定时器** |
| `pet/divination_settings.py` | 设置页 | 「趣味」域整页（两节）：两个开关的控件与落盘 + 今日穿色只读预览 |
| `pet/app.py` | 组合根 | `win.on_draw_lot` 注入、`trigger_draw_lot()`、`_ensure_divination_service()`（懒创建） |
| `tests/test_divination.py` / `tests/test_almanac.py` / `tests/test_divination_settings.py` | 测试 | 签库形状/加权/文本口径/服务降级；干支锚点/冲煞/五色映射；趣味域与两节可达、开关落盘 |
| `tests/test_divination.py` / `tests/test_almanac.py` | 测试 | 签库形状/加权/文本口径/服务降级；干支锚点/冲煞/五色映射/红线 |

依赖方向：`divination.py` → `divination_quotes.py`（数据）+ `almanac.py`（黄历）；
`divination_service.py` → `divination.py` + `window_alerts`；`app.py` → `divination_service.py`。
**纯逻辑三个模块都不得 import Qt**（`tests/test_architecture.py` 与各自用例双守）。

## 三、随机性与确定性

* 抽签是**真随机**（`random.Random()`，系统熵），**刻意不挂日期种子**：
  「每天固定一签」会让第二次点击没有反应，抽签要的是"抽"的手感；
* 要复现就用 :func:`pet.divination.draw` 的 ``rng`` 注入（用例、调试、将来的"再抽一次"都用它）；
* 加权只作用在**吉凶档位**，档内**均匀**抽——所以同档 12 支中平的命中率彼此相同。

## 四、菜单与设置接线

新增这个入口一共改了这些地方（照抄这份清单，避免漏接）：

1. `pet/context_menus/registry.py`：`ACTION_ICONS`（`"draw_lot": "todo"`）、`_build_draw_lot`
   （`close_on_trigger=True`）、`MenuActionSpec(_build_draw_lot, _callback_available("on_draw_lot"))`；
2. `pet/menu_templates/modern-default-v1.json`：`{"type":"action","id":"draw_lot","visible":true,"section":"tools"}`
   （**默认可见**——报时/节日那四项才是 `visible: false`）；
3. `pet/app.py`：`win.on_draw_lot = self._slot_wrap(self.shell.trigger_draw_lot)` +
   `_ensure_divination_service()` + `trigger_draw_lot()`（**异常只在本地吞掉**，不抛回 Qt 回调）；
4. `pet/sprite_menu_facade.py`：`on_draw_lot` 属性（overlay 拓扑走 `trigger_draw_lot`）；
5. 设置页：**侧栏一级域「趣味」**（第三轮改定，见第五节）+ `pet/divination_settings.py`
   的整页构建（控件在新模块，`modern_settings_dialog.py` 只多几行接线：import /
   `_build_divination_controls` / `domain_content["趣味"]` / `_write_config` 里一行 save）；
6. 配置：`divination_speak`、`divination_animation`（默认都 `True`）＋ reload 白名单 ＋
   `tests/test_config_schema.py` 快照。

**关于「为什么第一轮先放在互动域的标签里、第三轮又搬出来」**：第一轮我按「不新开域」的口径
把两个开关塞进「互动」域的页内标签；机主随后明确「**抽签这个功能应该是放到设置里面的。
归类为趣味**」，于是搬成一级域（域内两节＝抽签 / 今日穿色，满足设置门禁对一级域的
「≥2 个稳定设置组」要求）。**结论：趣味类功能归「趣味」域；别把它藏进不相关的域里。**

## 五、设置位置（2026-10-10 第三轮：搬成一级域「趣味」）

机主原话：「**抽签这个功能应该是放到设置里面的。归类为趣味**」——所以抽签 + 今日穿色从
「互动」域的页内标签**搬成侧栏一级域「趣味」**：

* `pet/settings_widgets.py::SETTINGS_DOMAIN_NAV` 里 `("趣味", "fun")`，位置在「文件识别」
  之后、「更新」之前（**「更新」恒末位**，多处既有断言 `labels[-1]`）；图标 `fun` 是
  `pet/context_menus/icons.py` 里的**矢量四角星**（不新增二进制素材）。
* 域内两节（整页在 `pet/divination_settings.py::build_divination_page` 构建，
  `modern_settings_dialog.py` 只多一行接线）：
  - **抽签**：`divination_speak`（语音朗读）／`divination_animation`（摇签动作）两个开关；
  - **今日穿色**：一行**只读预览**（`divination_daily_color`，objectName
    `settingRow_divination_daily_color`，控件是 `divinationColorPreview` 标签），
    显示当天 `丁巳日（火）· 宜穿 青绿（…）· 次吉 朱红 · 避 藏青（…）· 冲猪煞东`，
    **不落盘、没有开关**（开关只有上面那两个）。

| 键 | 默认 | 作用 |
|---|---|---|
| `divination_speak` | `True` | 抽到签是否用**报时的音色**念出来（与报时/节日共用同一条音频通道，结构上不叠音） |
| `divination_animation` | `True` | 抽签时请角色动一下（在当前角色动作池里按 `ANIMATION_CANDIDATES` 顺序挑第一个存在的；**没有就安静跳过**，绝不为它报错） |

**不含任何个人信息**——这是它与已归档的占星功能最大的区别（那套要出生日期/时刻/地点）。
准入/准出按 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)（新一级域要有「长期目标 +
≥2 个稳定设置组」，趣味域正好是抽签 + 今日穿色两组）。

## 六、黄历「今日宜穿色」（`pet/almanac.py`，2026-10-10 并入）

**颜色只有一个硬依据：当日日柱天干的五行**（其余黄历条目——宜嫁娶/忌动土之类——各版本
互相矛盾，**一律不编**）。规则用五行生克：

| | 取哪个五行 | 例（丁巳日，日干丁属火） |
|---|---|---|
| **宜穿**（生我者，印） | 日干五行的母行 | 木 → **青绿**（墨绿、竹青、橄榄绿） |
| 次吉（同我者，比） | 日干五行本身 | 火 → 朱红（酒红、紫、橙） |
| **避**（克我者，官杀） | 克日干五行的行 | 水 → **藏青**（深蓝、墨黑、灰蓝） |

**冲煞**：冲的生肖＝日支 +6（子↔午…）；煞方按日支的三合局（申子辰煞南 / 巳酉丑煞东 /
寅午戌煞北 / 亥卯未煞西）。

**锚点（别凭记忆改）**：日干支是连续六十甲子，只需一个锚。取 **1949-10-01＝甲子日**
（[911cha](https://mipnongli.911cha.com/1949-10-1.html)，同日儒略日 2433196.5），
用 [黄历网 2026-10-10＝丁巳日、冲猪煞东](https://hli.cc/hdjr/2026/10/10) 交叉验证：
两天相距 28133 天，`28133 mod 60 = 53`，甲子顺数 53 位正是丁巳；煞方也与「巳酉丑煞东」一致。
`tests/test_almanac.py` 把这两个日期与六十甲子周期、四个煞方分组全部钉住。

**农历日期、纳音五行、宜忌条目**都没做——农历要另一张表，纳音/宜忌属流派与版本差异，
做了就是装饰。要加再单独提。

## 七、怎么扩签库

改 `pet/divination_quotes.py` 的 `STICKS`：

* **只追加，不改号**：号一旦发出去就是"她抽到过的那支"，改内容等于改历史（2026-10-10 第四轮
  从 24 扩到 **48** 就是这么加的：新增 25–48，旧 1–24 一字未动）；
* 每支必须有：`no`（连续编号）/ `level`（四档之一）/ `poem`（**两句**）/ `plain`（**≤14 字**）/
  `good` / `bad`；
* 加档位或改权重：改 `LEVELS` / `LEVEL_WEIGHTS`（`tests/test_divination.py` 按档位数量与
  分布断言，改完同步那个用例；当前 48 支＝上上 4 / 上 8 / 中平 26 / 下 10）；
* **白话解别与宜忌重复**（第 16 签曾写成「看长线，别贪小利」而宜忌正是「看长线/抢小利」，
  已改成「这件事值得再等一轮」——同一句说两遍就是拖沓）。

## 七之二、第四轮：一轮不重复 / 记录 / 摇签音效 / 上上签卡（2026-10-10）

她一句「抽签功能现在还是不完善」之后，按清单补了四件（外加签库扩到 48）：

1. **一轮之内不重复**：`draw(rng, exclude=…)` 排除已抽过的签号（某档排空则该档不参与加权；
   整副抽完自动开新一轮）。服务层 `DivinationService._drawn` 记本轮集合，`drawn_this_round()`
   可查——这是"连抽几把撞到同一支"的直接解法。
2. **本机抽签记录**：每签追加一行到 `<config.dir>/divination-history.jsonl`
   （`{ts, no, level}`，best-effort，失败只记日志）；设置页新增只读行 **「最近抽到」**
   （`settingRow_divination_last_draw` / 控件 `divinationLastDraw`）——设置跑在独立进程，
   所以读**文件最后一条**（`divination_service.last_record`）。
3. **摇签音效**：复用点击音效的播放器与音量（`click_sound.play_click_sound` + 内置
   `assets/sounds/start.wav`），受「摇签动作」开关与点击音效总开关/音量约束，
   **不新增通道、不新增配置键**。
4. **上上签卡**：抽到「上上」（4%）时用 PIL 落一张签卡 PNG 到她的**真桌面**——
   `divination_service.desktop_dir()` 读注册表 `User Shell Folders\Desktop`
   （`~\Desktop` 在她机器上是个空壳），渲染失败只记日志、绝不影响抽签。
   `pet/divination_card.py` 是纯 PIL 渲染器（零 Qt）。

## 八、测试与验证入口

```powershell
D:\dsh-pet\.venv\Scripts\python.exe -m pytest -q tests/test_divination.py tests/test_almanac.py tests/test_divination_settings.py tests/test_menu_layout.py
D:\dsh-pet\.venv\Scripts\python.exe -m ruff check .
```

红线（用例守着）：签诗/白话/宜忌里**不许出现感叹号**与医疗/疾病/寿命/怀孕类词；
白话解单条 ≤14 字；气泡恒五行；穿色短句 ≤16 字、语音句 ≤18 字；纯逻辑模块零 Qt；
**一轮 48 把不许重复**；记录文件写在 config 目录（测试里用 tmp、桌面被 monkeypatch）。
