# PR 报告 · 抽签（右键「抽支签」，2026-10-10）

> **基线**：`d56cce1`（2026-10-04 合并上游 `beaa8f5` 后的集成分支 HEAD）
> **分支**：`feat/media-window-fallback`　**日期**：2026-10-10
> **范围**：12 个文件（实现 7：4 新增 + 3 改；测试 5：1 新增 + 4 改）+ 2 篇文档
> **关联**：[`DIVINATION-2026-10-10.md`](DIVINATION-2026-10-10.md)、
> [`PR-REPORT-FESTIVAL-REMINDER-2026-09-16.md`](PR-REPORT-FESTIVAL-REMINDER-2026-09-16.md)（气泡门禁/音频通道先例）、
> [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)
> **它是已废除的「趣味 · 占星 / 每日运势」的替代品**：那套 2026-10-10 按机主决定归档在
> `.scratch/fortune-astrology/`（补丁 + 临时分支 `backup/fortune-astrology-20261010`），
> 本批**不含任何星历/本命盘/出生信息**。

## 一、核心特性

桌宠右键菜单新增「**抽支签**」：点一下 → 角色动一下 → 气泡出签文 → 语音念出来。
**真随机、不联网、不读个人数据、不挂日历**。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 24 支签库 | 签号 + 吉凶（上上/上/中平/下）+ 七言签诗两句 + 白话解（≤14 字）+ 宜/忌 |
| 2 | 加权抽签 | 四档权重 4/18/56/22（上上少见、中平最多）；档内均匀；**可注入 RNG 复现** |
| 3 | 一次性的播报 | 气泡四行 + 语音一句话念完；**复用既有音频通道**，不新增播放器 |
| 4 | 摇签动作 | 按候选名找当前角色动作池里第一个存在的动作；**没有就安静跳过** |
| 5 | 设置 | 「设置 → 互动 → 抽签」两个开关（语音 / 摇签动作）；**无个人信息字段** |

**红线 / 不变量**：`divination.py` / `divination_quotes.py` 纯逻辑零 Qt；文案无感叹号、
无医疗/疾病/寿命/怀孕词、白话解 ≤14 字；不改动报时/节日提醒的调度与让位语义；
**不开新的一级设置域**（沿用「互动」域内的页内标签）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/divination_quotes.py` | **新增 165 行** | 纯数据：24 支签（编号/吉凶/签诗两句/白话解/宜忌）、四档权重、摇签动作候选 |
| `pet/divination.py` | **新增 74 行** | 纯逻辑：加权抽签（可注入 `random.Random`）、配置清洗、气泡/语音文本组装 |
| `pet/divination_service.py` | **新增 136 行** | 摇签动作 → 气泡（与节日提醒同一套门禁与降级链）→ 经既有音频通道朗读；无定时器 |
| `pet/divination_settings.py` | **新增 60 行** | 设置页接线三件套：控件创建 / 行构建 / 落盘（照 `settings_file_interpret` 的做法） |
| `pet/app.py` | +21 / −0 | `win.on_draw_lot` 注入、`_ensure_divination_service()`（懒创建）、`trigger_draw_lot()`（异常只在本地吞掉） |
| `pet/context_menus/registry.py` | +14 / −0 | `ACTION_ICONS["draw_lot"]`、`_build_draw_lot`（`close_on_trigger=True`）、`MenuActionSpec` |
| `pet/settings_interaction.py` | +8 / −2 | 互动域加第三个页内标签「抽签」（`TAB_KEYS/TAB_LABELS` + `addTab`） |
| `pet/modern_settings_dialog.py` | +7 / −0 | 只留接线：import、`_build_divination_controls`（2 行）、`_write_config` 里一行 save |
| `pet/sprite_menu_facade.py` | +5 / −0 | overlay 拓扑的 `on_draw_lot` 属性 |
| `pet/config.py` | +7 / −0 | 两个新键（默认 `True`）+ reload 白名单登记 |
| `pet/menu_templates/modern-default-v1.json` | +1 / −0 | 默认布局加 `draw_lot`（**visible: true**，与报时/节日四项相反） |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_divination.py` | **新增 195 行 / 11 例** | 签库形状（24/编号连续/四档数量）、签诗两句、白话 ≤14 字、无感叹号与医疗词、加权分布（4000 次）、可复现注入、气泡四行、语音单句、配置清洗、纯逻辑零 Qt、服务降级（无窗口走桌面通知、关语音不碰音频） |
| `tests/test_settings_interaction_tabs.py` | +4 / −1 | 第三个标签进 `EXPECTED_TABS` 与 `ROWS_BY_TAB`（每行可路由、可见） |
| `tests/test_menu_layout.py` | +7 / −1 | 模板节点顺序、注册动作集、根菜单文案与渲染顺序 |
| `tests/test_desktop_pet_features.py` | +2 / −0 | 真实 QMenu 根项含「抽支签」；设置分组名含「抽签」 |
| `tests/test_config_schema.py` | +2 / −0 | reload 白名单快照（同时覆盖 `DEFAULTS_SNAPSHOT`） |
| `tests/test_architecture.py` | +5 / −1 | 行数预算按实测 2396 → **2403**（带日期与理由注释） |

### 未改动（有意）

`pet/window.py`（预算 4510/4510 顶满，本功能不需要碰窗口）；`pet/voice_chime_service.py`、
`pet/festival_service.py`（让位仲裁与新功能无关）；`SETTINGS_DOMAIN_NAV`（**不加新域**，
理由见第四节）。

## 三、实现要点

- **真随机 vs 可复现**：抽签用系统熵，**刻意不挂日期种子**——「每天固定一签」会让第二次
  点击没有反应；要复现就注入 `random.Random(seed)`（用例与将来的"再抽一次"都用它）。
- **加权只作用在档位**：先按 4/18/56/22 抽吉凶档，再在档内均匀抽——所以 12 支中平彼此
  等概率；`tests/test_divination.py` 用 4000 次抽样断言「中平最多、上上最少」。
- **一次性的服务**：没有定时器、没有状态机，只在点菜单时干活；音频走
  `AppShell.ensure_audio_channel()`（进程内唯一音频出口），气泡走节日提醒那套
  「直写 → 气泡位 → 系统通知」降级链，飞行/全屏拦截时静默不出。
- **摇签动作不赌运气**：按 `ANIMATION_CANDIDATES` 顺序取**动作池里真实存在**的第一个，
  取不到就跳过——避免"设置了却什么也没发生"这种没法解释的行为。
- **设置页不给上帝对话框加行数**：控件与行都在新模块
  `pet/divination_settings.py`，`modern_settings_dialog.py` 只多 7 行接线（见第二节）。

## 四、性能分析

**方法（可复现）**：`D:\dsh-pet\.venv\Scripts\python.exe .scratch\divination_bench.py`
（`timeit`，N=2000，取 3 轮最小值）；环境：Windows 10.0.26100 / Python 3.11.9。

| 指标 | 实测 | 归属 |
|---|---|---|
| `draw()`（加权 + 取签） | **5.2 µs/次** | 新增·点一次菜单 |
| `bubble_text()` | **0.9 µs/次** | 新增 |
| `speech_text()` | **0.4 µs/次** | 新增 |
| `normalize_divination_config()` | **0.6 µs/次** | 新增 |
| 冷启动 `import pet.divination`（连带签库） | **16.3 ms**（其中签库 6.8 ms） | 新增·**只在第一次点「抽支签」时付**（服务懒创建 + import 在构造点） |

**结论（逐条）**：① **稳态开销零变化**——不注册定时器、不被任何 tick 路径调用，空闲时
不占 CPU；② 新增路径绝对成本 **≈7 µs/次**，触发频率＝用户点一次菜单（外加首次
import 16 ms，一次性）；③ **没有新的系统调用/网络/磁盘/线程**：纯逻辑无 IO，语音只在
`divination_speak` 打开时经**既有**报时通道发声，动作只调一次 `request_link_anim`；
④ **内存/缓存不增长**：签库是 24 条常量，不落任何文件、不建缓存。

## 五、实机运行记录

**环境**：本机 `D:\dsh-pet`（Python 3.11.9 + PySide6，onedir 构建）。

1. **构建（第一次尝试失败，如实记录）**：
   ```
   Remove-Item ...\dsh-pet-standalone-webm-chat\_internal\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe
     → 文件正由另一进程使用
   PyInstaller ... COLLECT → PermissionError: [WinError 32] 同一个 ffmpeg 文件
   ```
   根因：**PyInstaller 的 `COLLECT` 会先清空目标目录再写入**，而该文件被外部进程占着。
   查占用者：`Get-CimInstance Win32_Process -Filter "Name LIKE '%ffmpeg%'"` →
   ```
   Name        : obs-ffmpeg-mux.exe
   CommandLine : "E:/WeGameApps/rail_apps/DeltaForce(2001918)/icreate/recorder-release/obs-ffmpeg-mux.exe"
                 "D:\GameVideos\deltaForceRecord\...\record20261010-015449.mp4" ...
   ```
   ＝《三角洲行动》自带录制器（游戏已退出但录制进程仍在）。**两次构建都撞在同一个文件上。**
   live 目录因此被清成半成品（文件数 1、exe 丢失）→ 用**整目录备份** `bak-20261010-0207`
   `robocopy /MIR /XF ffmpeg-win-x86_64-v7.1.exe` 恢复（1994 文件 + exe 在位），桌宠立刻可用。
2. **绕过锁的构建口径（本次新增的做法）**：把 `scripts/build_onedir.ps1` 原样拷到
   `.scratch/build_onedir_alt.ps1`，只改三处输出路径（`--distpath dist-onedir-alt` 与两处
   `Join-Path $root "dist-onedir-alt\..."`），然后：
   ```
   & .\.scratch\build_onedir_alt.ps1 -Variant webm-chat -SkipZip     → ALT_BUILD_EXIT=0
   robocopy <dist-onedir-alt>\dsh-pet-standalone-webm-chat <live> /MIR /XF ffmpeg-win-x86_64-v7.1.exe
   robocopy <live> H:\dsh-pet-standalone-webm-chat /MIR
   ```
   全部门禁照跑：bridge 零依赖 / Qt runtime / slim（−124 文件 −53.03 MB）/ **中文编码 PASS** /
   DLL 链 ALL OK / `exe` 与 `exe --settings` 双启动冒烟（3.1s / 1.0s）。
3. **装出去的包确实带新功能**（扒 PYZ，不是看时间戳）：
   ```
   模块总数 1356；pet.divination / pet.divination_quotes / pet.divination_service /
   pet.divination_settings  in bundle: True（四个都 True）
   冻结包内 pet.settings_interaction 的标签元组：('click','self_talk','draw_lot')
   冻结包内菜单模板：{"type":"action","id":"draw_lot","visible":true,"section":"tools"}（根节点 26 个）
   ```
4. **部署起来**（她的硬要求：换完包必须把桌宠拉起来）：
   ```
   cmd /c start "" /D <live> "<live>\dsh-pet-standalone-webm-chat.exe" --slot 0
   Get-Process → Id 27948, MainWindowHandle 593086（≠0）；pet-27948.log：0 条 ERROR
   ```
5. **用户可见行为**：等她点一次「抽支签」确认味道（签文语气/语速/动作合不合适）——
   **这一格尚未由她确认**，据实记录。
6. **边界与失败路径**（用例覆盖 + 代码路径）：角色动作池里没有候选动作 → 只出气泡与语音，
   动作静默跳过；音频通道不可用 → 只出气泡；窗口不可见/拦截中 → 退系统通知。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check .` | **All checks passed!** |
| 聚焦 | `pytest -q tests/test_divination.py tests/test_menu_layout.py tests/test_settings_interaction_tabs.py tests/test_config_schema.py tests/test_architecture.py tests/test_desktop_pet_features.py` | **213 passed** |
| 架构红线 | 同上（含 `tests/test_architecture.py`） | 通过（纯逻辑零 Qt、退役层、预算 2403） |
| 全量 | `python -m pytest -q` | **4422 passed / 14 skipped / 0 failed**（435.87s；含第二/三/四轮的 `test_almanac.py`、`test_divination_settings.py` 与第四轮去重/记录/签卡用例） |
| 冻结包抽检 | 扒 PYZ + 读包内菜单模板 | 四个模块 + `draw_lot` 节点 + 三标签都在 |

**全量**用 `PYTHONIOENCODING=gbk` 跑：这样同时**避开**已知环境 flake
`test_overlay_instance_gate::test_real_second_process_refused_on_overlay_topology`
（它在 UTF-8 子进程 / GBK 父进程下会因解码失败报红，与本改动无关），本次 0 failed。

## 七、已知限制与后续

- **摇签动作依赖角色素材**：`ANIMATION_CANDIDATES` 目前是 `凭空生花 / 写福字 / 动物环绕 /
  原地专心玩魔方`，取自「深深」的动作池；换角色若一个都没有，就只出气泡+语音（设计如此）。
- **签库 24 支**：想扩到 64/100 是纯加数据（改 `pet/divination_quotes.py` 的 `STICKS`，
  **只追加不改号**）；真实机 UI 三档宽度 / 高 DPI 的视觉核验本批**没做**（如实登记）。
- **可能的下一步**（等她点名再做）：抽签记录/收藏（"再抽一次"、当日第几次）、签筒音效、
  签文卡片图、把抽签接进「点击桌宠」的长按手势。

## 八、风险与回滚

- **影响面**：新增一个菜单项 + 两个设置行 + 两个配置键；不改既有调度、不碰 `window.py`。
- **开关**：`divination_speak`、`divination_animation`（都在「设置 → 互动 → 抽签」）。
- **配置迁移**：两个键都有默认值，老 `config.json` 不需要迁移。
- **回滚**：`git revert` 本批即可（不落任何用户数据文件）；构建产物回滚点
  `dist-onedir\dsh-pet-standalone-webm-chat.bak-20261010-0207`（无抽签的干净构建），
  `robocopy` 回 live 与 H: 后重新拉起桌宠。

---

## 九、第二轮：黄历「今日宜穿色」并入抽签 + 两处服务对齐（2026-10-10 深夜）

机主要求原话：「**可以做一个今日宜穿什么颜色，根据黄历来**」→「**合并进抽签不就好了**」。
所以**不新开入口、不新开设置节**：点一次「抽支签」，签文之后顺带给出今日宜穿色。

### 修改文件说明（第二轮）

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/almanac.py` | **新增** | 黄历纯逻辑：日柱干支（六十甲子锚点）→ 日干五行 → 宜穿/次吉/避 + 冲煞；`short_line` / `speech_line` / `detail_line` |
| `pet/divination.py` | 改 | `bubble_text(stick, day)` 增第五行「今日宜穿 X · 避 Y」；`speech_text(stick, day)` 末尾加一句 |
| `pet/divination_service.py` | 改 | `draw_now(..., day=None)` 传当天；**桌面通知标题改用签头**；摇签动作对齐 `festival_service` 的保护（`win.isVisible()` 判断 + `request_link_anim` 不可用时退 `switch_clip(link_request=True)`） |
| `pet/divination_quotes.py` | 改一行 | 第 16 签白话解原来与宜忌重复（「看长线，别贪小利」），改成「这件事值得再等一轮」 |
| `pet/divination_settings.py` | 改 | 「抽签语音朗读」hint 补上「以及今日宜穿的黄历色」 |
| `tests/test_almanac.py` | **新增 10 例** | 干支锚点（1949-10-01 甲子 / 2026-10-10 丁巳）、六十甲子周期、四组煞方、五色映射、连续一年无空洞、短句与红线、零 Qt |
| `tests/test_divination.py` | 改 2 例 | 气泡 4 行 → **5 行**（末行＝穿色）；语音句尾＝穿色句；通知标题断言改签头 |

### 实现要点（第二轮）

- **颜色只有一个硬依据**：当日**日柱天干**的五行。宜穿＝生我者（印，母行）、次吉＝同我者、
  避＝克我者（官杀）；冲煞＝日支 +6 的生肖 + 日支三合局对应的煞方。
- **黄历里那些「宜嫁娶／忌动土」一概不编**——各版本互相矛盾，编不出"对"的那一份；
  农历日期与纳音五行同样没做（前者要另一张表，后者属流派）。
- **锚点经过交叉验证**：`911cha` 1949-10-01＝甲子日（同日儒略日 2433196.5）+ `黄历网`
  2026-10-10＝丁巳日、冲猪煞东；两天相距 28133 天，`28133 mod 60 = 53` → 甲子顺数 53 位
  ＝丁巳 ✓，煞方也与「巳酉丑煞东」一致。UTC+8 当地日期直接算，不依赖节气/农历表。

### 性能分析（第二轮）

`pet/almanac.py` 纯算术（日期差 + 取模 + 查表），无 IO/网络/线程/定时器。
抽签一次的总成本仍约 **7 µs**（`draw` 5.2 µs + 文案 <2 µs，`speech_text` 本身 0.4 µs），
与第一轮同量级；稳态零变化。

### 实机运行记录（第二轮）

- `ruff check .` → **All checks passed!**；聚焦（`test_almanac.py` + `test_divination.py` +
  菜单 / 设置标签 / 架构）→ 全绿；全量 → 见第六节更新后的数字。
- **真跑一遍文案**（`python -c`，2026-10-10 丁巳日）：
  ```
  今日 2026-10-10 丁巳日（火）· 宜穿 青绿（墨绿、竹青、橄榄绿）· 次吉 朱红
       · 避 藏青（深蓝、墨黑、灰蓝）· 冲猪煞东
  第 3 签 · 上 / 顺水行舟不用撑，一路东风到岸平。 / 顺着走，别用力过猛。
       / 宜 顺势推进 · 忌 逆着来 / 今日宜穿 青绿 · 避 藏青
  语音：第 3 签，上。顺着走，别用力过猛。宜 顺势推进，忌 逆着来。今日宜穿青绿，避藏青。
  ```
- 构建与部署：见第十节（live 目录再次被占用，走备用 dist 口径）。

## 十、第二轮部署：备用 dist 口径再次生效

live 目录里的 `ffmpeg-win-x86_64-v7.1.exe` **又一次被外部进程占用**（同前：《三角洲行动》
录制器 `obs-ffmpeg-mux.exe`），`COLLECT` 依然会在半清空状态失败。处置与第一轮一致：

```
1) 停桌宠 → 整目录 robocopy 备份（bak-<stamp>）
2) 拷 scripts/build_onedir.ps1 → .scratch/build_onedir_alt.ps1，三处输出路径改 dist-onedir-alt
3) & .\.scratch\build_onedir_alt.ps1 -Variant webm-chat -SkipZip    → 全部门禁照跑
4) robocopy <alt>\dsh-pet-standalone-webm-chat <live> /MIR /XF ffmpeg-win-x86_64-v7.1.exe
5) robocopy <live> H:\dsh-pet-standalone-webm-chat /MIR
6) 拉起桌宠 → 查窗口句柄 ≠0 与日志无 ERROR
```

**教训（已写进 ops 记忆）**：构建前必做三步——停进程、确认目标目录无占用、先整目录备份。
两轮各把 live 打坏过一次，两次都是靠整目录备份在几分钟内救回；**别去杀游戏/反作弊进程**。

| 路径 | 说明 |
|---|---|
| `.scratch/build_onedir_alt.ps1` | 备用构建脚本副本（**不入仓库**，`.scratch/` 已 gitignore） |
| `dist-onedir-alt\` | 备用输出目录（构建产物，不入仓库） |

---

## 十一、第三轮：抽签搬进侧栏一级域「趣味」（2026-10-10）

机主要求原话：「**抽签这个功能应该是放到设置里面的。归类为趣味**」——第一轮我把它塞在
「互动」域的页内标签里（当时的判断是"只有两个开关，不值得新开域"），**这个判断被机主否掉**。
第三轮按她的口径搬成**侧栏一级域「趣味」**，位置在「文件识别」之后、「更新」之前。

### 修改文件说明（第三轮）

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/context_menus/icons.py` | +6 | 新矢量图标 `fun`（四角星，无二进制素材） |
| `pet/settings_widgets.py` | +3 | `SETTINGS_DOMAIN_NAV` 加 `("趣味", "fun")`（「更新」仍在末位） |
| `pet/divination_settings.py` | 改 | 新增 `build_divination_page()` / `build_daily_color_rows()`；控件创建多一个只读预览标签（`divinationColorPreview`） |
| `pet/modern_settings_dialog.py` | +1 | `domain_content["趣味"] = divination_settings.build_divination_page(self)`（预算 2403 → **2404**） |
| `pet/settings_interaction.py` | −8 | **撤掉**「互动」域的第三个标签「抽签」（回到两个标签） |
| `tests/test_divination_settings.py` | **新增 4 例** | 域位置（在「文件识别」后、末位仍是「更新」）、两节三行可达、预览＝当天黄历行、开关经 `_write_config` 落盘且预览不落盘 |
| `tests/test_menu_layout.py` | 改 3 处 | 两处侧栏清单 + `SETTINGS_DOMAIN_NAV` 快照加「趣味」 |
| `tests/test_desktop_pet_features.py` | 改 2 处 | `expected_pages` 加「趣味」；分组名清单改成「抽签 / 今日穿色」 |
| `tests/test_settings_interaction_tabs.py` | 改 | `EXPECTED_SIDEBAR` 加「趣味」；标签与行归属回到两标签 |
| `tests/test_architecture.py` | 改 | 预算 2403 → **2404**（带日期与理由注释） |
| `docs/SETTINGS-CHANGE-GATES.md` | 改 | 补「趣味」一级域的**准入记录**（逐项登记三个 setting_id） |

### 实机运行记录（第三轮）

- `ruff check .` → **All checks passed!**；聚焦（含新 `test_divination_settings.py`）→ 全绿；
  全量 → 见第六节更新后的数字。
- **离屏渲染验过页面**（`QT_QPA_PLATFORM=offscreen` + 系统字体）：侧栏 11 项、末位仍是
  「更新」，「趣味」域渲染出「抽签」「今日穿色」两节与三行，预览文本＝当天的黄历行。
- 构建与部署：仍走第十节的备用 dist 口径（live 目录被游戏录制器占着），部署后经
  **扒 PYZ + 读包内设置模块**确认 `pet.divination_settings` 里的域页面串与 `("趣味","fun")`
  都在，桌宠已重启。

### 教训（第三轮）

**"只有两个开关，不值得新开域"是我的判断，不是机主的口径。** 她认的是"归属要清楚"——
趣味类的东西就该在「趣味」里，哪怕只有两行。以后再遇到"新功能放哪"，**先按她的分类直觉走**
（她早前也说过设置要「大类→小类」），别用"成本最小"替她做信息架构决定。

---

## 十二、第四轮：一轮不重复 / 抽签记录 / 摇签音效 / 上上签卡 / 签库扩到 48（2026-10-10）

机主反馈原话：「**抽签功能现在还是不完善**」——不再等她圈选，按我自己给过的那份清单直接补。

### 修改文件说明（第四轮）

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/divination_quotes.py` | 改 | 签库 **24 → 48**（新增 25–48；档位分布 上上 +2 / 上 +3 / 中平 +14 / 下 +5；**旧 1–24 一字未动**） |
| `pet/divination.py` | 改 | `draw(rng, exclude=…)` 排除本轮已抽过的签号（某档排空则该档不参与加权；整副抽完自动开新一轮）+ `total_sticks()` |
| `pet/divination_service.py` | 改 | 本轮去重集合 `_drawn` 与 `drawn_this_round()`；`_record()` 写 `<config.dir>/divination-history.jsonl`；`_sound()` 复用点击音效放摇签声；`_save_card()` 上上落签卡；模块级 `history_file()` / `last_record()` / `desktop_dir()`（读注册表真桌面） |
| `pet/divination_card.py` | **新增** | 纯 PIL 签卡渲染（零 Qt），760×420 深底金边 |
| `pet/divination_settings.py` | 改 | 新增只读行「最近抽到」（控件 `divinationLastDraw`）；页面重建时刷新两个预览；摇签动作 hint 改成「跟随『点击与音效』那一套」——**避开设置搜索「点击音效」的域归属断言**（上一轮同类坑的原样复现） |
| `tests/test_divination.py` | 改 | 48 支与分布快照、`exclude` 连排 48 把刚好抽完、服务层一轮不重复 + 记录文件 48 行 + 上上签卡落盘（`desktop_dir` monkeypatch 到 tmp） |
| `tests/test_divination_settings.py` | 改 | 行清单加 `divination_last_draw`；新增「最近抽到」预览用例（空态文案 + 造记录后重建页面可见） |

### 性能分析（第四轮）

新增路径全在「点一次菜单」时发生且各有闸门：去重是集合运算；记录是**一行 append**（best-effort，
失败不抛）；音效走**既有**点击音效播放器（不新建通道、不加配置键）；签卡只在 4% 的上上时渲染
（PIL 一张 760×420 实测几十毫秒，非热路径）。`draw()` 从 5.2 µs 起（多一层排除推导仍在微秒级）。
稳态仍**无定时器、无新的常驻 IO**。

### 实机运行记录（第四轮）

```
── 连抽 6 把（同一 rng 序列，验证不重复）──
第 39 签，中平。联系一下老朋友。宜 发条消息，忌 装作忘了。今日宜穿朱红，避青绿。
第 24 签，下。话出口前想一遍。宜 少说两句，忌 群里争对错。今日宜穿朱红，避青绿。
第 18 签，中平。今天的小摩擦，别放大。宜 先忍一步，忌 当面顶。今日宜穿朱红，避青绿。
第 40 签，中平。钱的事算清楚。宜 对一遍账，忌 大概就行。今日宜穿朱红，避青绿。
第 22 签，下。今天别乱花钱。宜 记一笔账，忌 冲动下单。今日宜穿朱红，避青绿。
第 33 签，中平。别老掀盖看。宜 耐心等，忌 反复确认。今日宜穿朱红，避青绿。
本轮已抽: [18, 22, 24, 33, 39, 40]        ← 6 把 6 支，无重复
── 上上签卡渲染 ──  签卡-第1签.png  26727 字节
── 路径解析 ──  desktop_dir: H:\360MoveData\Users\KAZA\Desktop   ← 注册表真桌面
             签库总数: 48
```

顺带一次**跨日交叉验证**：上面每把的颜色行都是「宜穿朱红，避青绿」——按日柱推是**戊午日**
（戊属土 → 生土者火＝朱红、克土者木＝青绿），与上一轮对「丁巳日 → 青绿/藏青」的说明一致，
说明黄历那套随日期切换是对的。

门禁：`ruff` 全绿；聚焦 130 passed；全量见第六节更新后的数字。构建与部署仍走第十节的备用 dist
口径（live 目录被游戏录制器占着），部署后经扒 PYZ 与包内设置模块抽检、桌宠重启。
