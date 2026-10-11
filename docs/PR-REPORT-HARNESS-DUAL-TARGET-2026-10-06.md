# PR 报告：Harness 双目标启动（dsh web / 桌面端）+ 尾项收口（2026-10-06）

> **基线**：`ed18a3e`（联动减法收口提交）
> **分支**：`feature/agent-link-subtraction`　**日期**：2026-10-06
> **范围**：20 个文件（实现 7、测试 10、文档 3），本地工作区未提交
> **关联**：`.scratch/SPEC-harness-launcher-dual-target-20261006.md`（本批规格）；
> 归属收口前作 [`PR-REPORT-HARNESS-OWNERSHIP-2026-09-29.md`](PR-REPORT-HARNESS-OWNERSHIP-2026-09-29.md)；
> 设置门禁 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)
>
> **复审更正（2026-10-06，P2-6 / P2-7）**：本报告初版有几处不实，已就地更正并逐处
> 标注「复审更正」：① 性能计量把「默认安装位命中」的耗时标成「含注册表枚举」、
> 漏算 desktop 启动路径上的进程枚举、据此写出的「单次探测总和 < 0.2ms」不成立；
> ② 「只有两处收口调用点、没有任何一处挂在开关上」被 `pet/app.py:2136-2138` 反证；
> ③ `resolve_launch_target` 被写成纯函数；④ `docs/INDEX.md` 的 numstat 写错。
> P2-6 是同一事实的另一半：设置页 hint 与 README 段落都缺自启的联动门与收口的
> 启动窗口例外，已改文案并补机器守卫。
>
> **三轮更正（2026-10-06，计数口径复核）**：复审指出 §四还有 3 处计数不实，均已
> 用**新探针**（真 `launch_harness` / 真 `_maybe_autostart_harness` + 真注册表与真
> 进程枚举，只打桩 OS 边界）按**路径分支**重测后改写：①「`_harness_autostart_wanted`
> 每次自动拉起调 1 次」错——实测已有实例 3 次、正常 spawn 4 次（`:2107`/`:2118`/
> `:2129`/`:2136` 四个调用点）；②「web 目标付 `resolve_launch_target()` ~55µs」错
> ——显式 `target=web` 的安装探测是 **0** 次（0.3µs），~55µs 是只有 `auto` 才付的
> 安装探测；③安装/注册表「一次」的口径漏了 `auto` → desktop 且未运行这条路径——
> 安装探测 **2** 次、进程探测 1 次、默认安装位不存在时注册表也 **2** 次。数字取
> 第三轮 4 轮实测（`.scratch/dual-target-tail/PROBE-CALLCOUNTS-20261006.log`），
> 三条更正与逐路径计数见 §四。

## 一、核心特性

用户以后主用 **DeepSeek Harness 桌面端**，上游默认的 `dsh web` 也不能丢，于是把
「一键启动」拆成两个目标，并让设置页的自启也能选目标：

| # | 能力 | 说明 |
|---|---|---|
| 1 | 菜单双入口 | 右键 `DeepSeek Harness` 子菜单四项：启动 dsh web 界面 / 启动桌面端界面 / 重启服务 / 停止服务；托盘菜单是两个平铺启动项（没有重启/停止） |
| 2 | 自启目标 | 新配置键 `harness_launch_target`（`auto`/`web`/`desktop`，默认 `auto`）：auto = 检测到桌面端安装则桌面端、否则 web。**只作用于「随桌宠启动」这一路**，菜单点哪项就起哪项 |
| 3 | 桌面端只登记不杀 | 桌面端是用户主力 GUI 应用：由桌宠拉起时登记 pid（kind=desktop）但退出/联动关闭**绝不终止**；收口只覆盖 web 服务进程 |
| 4 | 桌面端在线判定 | 端口候选全 miss 时以「桌面端进程在跑」兜底 online（`pet/agent_link.py`） |
| 5 | 尾项收口（本轮） | ① 开关说明去掉字面 Markdown 并改成事实；② 非 Windows 上「桌面端」项置灰 + 回落 + 绝不写回 `desktop`；③ README 现行段落对齐真实菜单 |

**红线 / 不变量**：① 没装桌面端的用户走 web，行为与本批之前**逐字一致**；
② 用户自己在终端起的实例永不误杀（收口只认自拉起登记表 + 命令行复核）；
③ 桌面端进程在任何路径上都不会被桌宠终止；④ 平台不支持时不得产生「保存了却
什么都不发生」的无声死选项。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/harness_launcher.py` | +252 / −10 | 双目标主体：`DESKTOP_SUPPORTED`（`os.name == "nt"`，非 Windows 一律按不支持处理，**不 Popen macOS 的 .app 目录**）、`desktop_install_path()`（默认安装位 → 注册表卸载项 InstallLocation/DisplayIcon，`_display_name_matches` 只放宽到「全名 + 空格 + 版本号开头」、`_strip_icon_index` 剥 `,0`）、`desktop_processes()/desktop_process_running()`、`resolve_launch_target()`、`_spawn_desktop()`；`launch_harness(target=)` 新增 desktop 分支（already/not-found/unsupported/aborted 四态）、`_SELF_LAUNCHED_KIND` 登记目标类型、收口循环对 live desktop **只跳过终止但照旧销死登记**、`restart_harness` 钉 `target="web"`、`launch_harness_gui(target=)` 与 unsupported/not-found 的如实提示框 |
| `pet/config.py` | +8 / −1 | 新键 `harness_launch_target`（默认 `auto`）+ 重载白名单 + `_normalize_pet_settings` 收敛非法值到 `auto` |
| `pet/app.py` | +19 / −11 | 自启按目标拉起；把「已有实例」判定下移给 `launch_harness`（原按 web 端口提前 return 会把 desktop/auto 目标一起挡掉）；`cancel_check` 补「开关/联动已被关」；托盘两个平铺启动项；退出收口语义注释同步 |
| `pet/context_menus/shared.py` | +10 / −4 | 右键子菜单：`_launch(action, target)`，启动拆两项（web / desktop），重启与停止不受目标影响 |
| `pet/modern_settings_dialog.py` | +63 / −2 | 「自启目标」下拉（三项）+ 平台可见性；开关说明与目标说明改写（见「实现要点」）；保存边界最后一道门。**复审更正（P2-6）**：开关说明补自启的 DSH 联动门与收口的启动窗口例外（初版写 +61 / −2，未算这次补的两行） |
| `pet/settings_widgets.py` | +17 / −0 | `ModernSelect` 新增**可选**的单项置灰能力（`setItemDisabled`/`isItemDisabled` + 弹窗 `action.setEnabled`）；未调用它的既有下拉行为不变 |
| `pet/agent_link.py` | +4 / −0 | `DshMonitor._probe_online`：三条端口候选全 miss 时以「桌面端进程在跑」兜底 online（desktop host 端口随版本变，不赌死） |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_harness_launcher.py` | +375 / −2 | 文件名级 autouse 夹具钉死桌面端边界（避免开发机上真装了桌面端把既有 web 用例全带偏）；双目标 8 条：web 命令零变化、desktop 拉起 exe、auto 回落、auto 优先、显式 desktop 未安装、桌面端已在跑、desktop 登记退出不杀、死 desktop 登记销账；**本轮新增** desktop 直接 abort 路径 |
| `tests/test_harness_ownership.py` | +97 / −1 | 自启把「已有实例」判定交给 launcher；**本轮新增** ①探测期间关开关 → desktop 不得 spawn（走产品的 `cancel_check`，真线程 + 真 `launch_harness`，只打桩 OS 边界）②对照：开关一直开着照常拉起 |
| `tests/test_requested_regressions.py` | +126 / −0 | **本轮新增** ①hint 无字面 Markdown 且不得谎称「关闭本项就停服务」②非 Windows：桌面端项存在但置灰、存量 `desktop` 回落、弹窗项点不动、程序化硬选也写不进 ③Windows 对照：可选可存、说明里不出现「暂不支持」。**复审更正（P2-6）**：① 那条 hint 用例补两条判别断言（自启要联动开、收口有启动窗口例外）②新增 `test_readme_harness_autostart_paragraph_matches_the_launch_gates` 看住 README 同口径（初版写 +93 / −0） |
| `tests/test_harness_lifecycle.py` | +66 / −14 | 重启/停止钉 web；`start` 动作必须把 `target` 原样传到 `launch_harness`（回归：worker 里重名变量把 target 吞成 UnboundLocalError，所有启动入口静默失败）；子菜单四项逐一接线 |
| `tests/test_menu_layout.py` | +4 / −2 | 现代模板子菜单四项断言 |
| `tests/test_sprite_menu_parity.py` | +8 / −5 | overlay facade 菜单与 legacy 模板同款四项 |
| `tests/test_desktop_pet_features.py` | +2 / −1 | 纯桌宠版两个启动入口都不出现 |
| `tests/test_config_schema.py` | +1 / −0 | 新键进重载白名单快照 |
| `tests/test_agent_link_subtraction.py` | +4 / −0 | DshMonitor 用例钉死「桌面端进程旁路」为假（否则本机装了+在跑桌面端时，离线分支永远进不去） |
| `tests/test_tray_icon_ready.py` | +21 / −0 | **本轮新增** 托盘里是两个平铺启动项、无 Harness 子菜单、无重启/停止（README 那句托盘口径的机器守卫；先前托盘侧没有任何守卫） |

### 文档

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `README.md` | +3 / −3 | 现行段落对齐真实菜单：mac/Linux 安装步骤的「启动 DeepSeek Harness」写明两个启动入口 + 桌面端仅 Windows；功能清单改为「右键子菜单四项 + 托盘两个平铺启动项」；顺带修正同句里与代码不符的「退出桌宠不会顺带停止 dsh 服务」（桌宠自拉起的那份会随退出收口）。**复审更正（P2-6）**：同一段落补上自启的 DSH 联动门与「拉起探测期间关掉开关会立刻收掉刚拉起实例」这一例外（改的是已在 diff 内的那一行，故增删计数不变） |
| `docs/PR-REPORT-HARNESS-DUAL-TARGET-2026-10-06.md` | 新增 | 本报告（三份交付证据） |
| `docs/INDEX.md` | +2 / −1 | 报告入场登记（新文档入场规则第 1 条）+ 在 `PR-REPORT-HARNESS-OWNERSHIP-2026-09-29.md` 条目补「后续演进」互链（**复审更正**：初版写 +1 / −0，未算上那条互链） |

### 未改动（有意）

- `pet/dsh_state.py`：8 态收敛逻辑属联动减法分支的领土，本批只加端口候选与进程旁路，收敛器一行未动。
- macOS 桌面端实现：本轮明确不做（见「已知限制」），只保证**如实汇报不支持**，不新增 `.app` 占位路径。
- `tools/greenscreen_to_frameseq.py`：工作区里的未跟踪文件，属另一条工作流，与本批无关，未纳入。

## 三、实现要点

1. **目标解析是单向判定，但不是纯函数**（`resolve_launch_target`，`pet/harness_launcher.py:210`）：`auto` 只在「检测到桌面端安装」时拐向 desktop，其余一律 web。**复审更正（P2-7）**：原报告写「纯函数」不成立——它内部调 `desktop_install_path()`，因此会做**文件系统探测**（默认安装位命中即返回，不命中再走注册表），auto 的判定依赖本机 IO 状态，不可当无副作用函数看待。非 Windows 上 `desktop_install_path()` 恒为 `None`（能力位提前返回），因此 auto 在该平台**结构上**不可能拐到 desktop —— 这是「不静默改开网页」之外的另一半保证：显式 desktop 报 `unsupported`，auto 老老实实走 web。
2. **归属用 kind 区分**（`_SELF_LAUNCHED_KIND`）：desktop 与 web 共用登记表与子进程句柄表，收口循环里 desktop 分支放在「按句柄判死销登记」**之后**——活着的 desktop 跳过终止，但用户已经关掉的那条登记必须销掉，否则每次退出都留一条永不消费的死 pid。
3. **`cancel_check` 是探测窗口期唯一的中止闸**：真机上 `desktop_install_path()` 要做文件系统（必要时注册表）探测，窗口极短但存在；判定条件补上「开关或联动已被关」后，desktop 路径不会弹出一个用户刚说不想要的 GUI 窗口。**复审更正（P2-7）**：本机默认安装位存在，该函数在 `pet/harness_launcher.py:174` 提前返回，**一次注册表都没读**（探针计数 `REGISTRY_CALLED = 0`）；原报告把 76.5µs 标成「含注册表枚举」失实，注册表兜底须单独计量（见 §四）。
4. **平台能力只在设置页表达一次**：`harness_launcher.DESKTOP_SUPPORTED` 是唯一口径，设置页不另写平台判定；不支持时该下拉项**保留但置灰**（`SETTINGS-CHANGE-GATES.md` §4「暂不可用的能力保留并解释原因」），说明文案同时改成平台相关版本；并且显示与保存两处都回落 `auto`（该平台上 auto 解析就是 web）——「存量 desktop 配置」不会变成无声死选项，跨平台回迁时也不丢语义。
5. **hint 是纯文本**：设置页 `SettingRow` 的 hint 用 `QLabel` 直接渲染，不解析 Markdown。旧文案里的 `**…**` 会原样显示成星号，且声称「关闭本项即停止已拉起的 web 服务」，与代码不符。**复审更正（P2-6）**：初版此处把收口写成「只有两条路（退出 `pet/app.py:2331` / 关闭 DSH 联动 `pet/app.py:2186`）」，漏了 `pet/app.py:2136-2138` 的**启动窗口补偿**（拉起探测期间关掉本项 → 立刻收掉这一次刚拉起的实例），也漏了自启的第三个必要条件「DSH 联动开着」（`_harness_autostart_wanted`，`pet/app.py:2161-2165`）。文案现按「稳态两条路 + 一次性补偿单列 + 自启要联动开」重写。

## 四、性能分析

**方法（可复现，共三轮，数字取第三轮）**：
① 初轮 `QT_QPA_PLATFORM=offscreen python .scratch/dual-target-tail/probe_dual_target_tail.py`（原始输出：`.scratch/dual-target-tail/PROBE-20261006.log`）；
② **复审补测** `QT_QPA_PLATFORM=offscreen python .scratch/dual-target-tail/probe_registry_and_callsites.py`（原始输出：`.scratch/dual-target-tail/PROBE-REGISTRY-20261006.log`）——把「默认安装位命中 / 注册表兜底 / 完整 desktop 启动探测」分开计量，并对注册表函数做调用计数；
③ **三轮计数复核（2026-10-06）** `QT_QPA_PLATFORM=offscreen python .scratch/dual-target-tail/probe_call_counts_by_path.py`（原始输出：`.scratch/dual-target-tail/PROBE-CALLCOUNTS-20261006.log`）——把「一次拉起」按**路径分支**拆开：用**真** `launch_harness` 与**真** `_maybe_autostart_harness`（只打桩端口探测、dsh 命令解析、Popen 与进程存活探测这些 OS 边界）数调用次数，并用两组独立实现交叉核对（打桩 `launch_harness` 的返回状态 vs 真 `launch_harness` 配合打桩 `is_running`），两者结论一致。首版探针的原始输出也保留在同一目录（`PROBE-CALLCOUNTS-20261006-run1-superseded-probe-race.log`）——它因没等 worker 线程结束而少读一次门调用，是本探针自己的竞态，见 §五 第 4 条。

环境：Windows 10 x64 / Python 3.13 / 本机已安装 **DeepSeek Harness 桌面端**（默认安装位存在；探针启动时枚举到 5 个桌面端进程）。n 见各行，均为 **4 轮**。

**两条诚实边界**：① 耗时数字随机器负载漂移——同一个 `desktop_processes()` 在三轮测量里的中位区间是 **12.6–21.1ms**，所以下表给逐轮中位而不是单值快照；**调用次数与负载无关**，也正是本轮要更正的口径。② 初轮探针 ⑦ 的括号里写「每次自动拉起只调 1 次」，该口径已被第三轮推翻（见下表 A）。

### A. 逐路径调用次数（本轮更正的核心）

| 拉起路径 | 结果 | `desktop_install_path()` | `_desktop_exe_from_registry()` | 进程探测 | 端口探测 |
|---|---|---|---|---|---|
| 显式 `target=web` | started | **0** | 0 | 0 | 2 |
| 显式 `target=desktop`（已在跑） | already | 0 | 0 | 1 | 0 |
| 显式 `target=desktop`（未运行，默认位命中） | started | 1 | 0 | 1 | 0 |
| `auto` → web（未安装：默认位无 + 注册表无） | started | 1 | 1 | 0 | 2 |
| `auto` → desktop（已在跑） | already | 1 | 0 | 1 | 0 |
| `auto` → desktop（未运行，默认位命中） | started | **2** | 0 | 1 | 0 |
| `auto` → desktop（未运行，默认位不存在→注册表） | started | **2** | **2** | 1 | 0 |

（命令：`.scratch/dual-target-tail/probe_call_counts_by_path.py` ②；端口探测 2 次 = `_candidate_ports()` 的「配置端口 + 官方默认 3080」各一次。）

**三条被更正的口径**：

1. **显式 `target=web` 不做任何目标解析**：`resolve_launch_target("web")` 内部 `desktop_install_path()` 调用 **0 次**（实测 0.3µs），显式 `desktop` 同样 0 次，只有 `auto` 才是 1 次（82.7µs 级）。初版把它写成「web 目标只付 `resolve_launch_target()`（~55µs）」，等于把只有 `auto` 才付的安装探测算给了显式 web。
2. **`auto` → desktop 且桌面端未运行时，安装探测走两次**：`resolve_launch_target("auto")` 一次（判目标）+ 进程探测未命中后 `pet/harness_launcher.py:585` 再一次（取 exe）。初版把这条路径写成「安装/注册表各一次」。
3. **默认安装位不存在时注册表也走两次**：两次 `desktop_install_path()` 各兜底一次。初版写「只在默认安装位不存在时，拉起时**一次**」，漏了同一条路径上的第二次。

### B. 各子探针真实耗时（4 轮，逐轮中位 / 该轮最坏）

| 指标 | 逐轮中位 | 中位的中位数 | 最坏 | 归属 |
|---|---|---|---|---|
| `desktop_install_path()`——默认位命中，`pet/harness_launcher.py:174` 提前返回，**不读注册表** | 56.2 / 61.1 / 61.5 / 56.0µs（n=20 每轮）；同轮计数 `REGISTRY_CALLED = 0` | **58.7µs** | 152.6µs | 新增（按路径 0 / 1 / 2 次，见 A） |
| `_desktop_exe_from_registry()`——注册表兜底本身 | 336.3 / 355.0 / 375.7 / 442.6µs（n=20） | **365.4µs** | 943.3µs | 新增，**只在默认安装位不存在时**发生 |
| `desktop_install_path()`——默认位不存在，真走注册表兜底（含兜底调用） | 368.7 / 444.1 / 424.9 / 412.7µs（n=20） | **418.8µs** | 766.0µs | 新增（自定义安装位的用户） |
| `desktop_processes()` / `desktop_process_running()` | 17605.6 / 17336.5 / 19833.9 / 19030.3µs（n=10，即 **17.3–19.8ms**） | **18.3ms** | 24.6ms | 新增（`EnumProcesses` 全表 + 逐 pid 取镜像名） |
| **完整 desktop 启动探测**（`desktop_process_running()`，未命中再 `desktop_install_path()`；`pet/harness_launcher.py:583-585`） | 17331.3 / 18311.4 / 17958.1 / 17786.0µs（n=10） | **17.9ms** | 20.1ms | 新增（每次 desktop 目标拉起 / 菜单点「启动桌面端」各一次）；本机进程探测命中即返回，所以等于上一行 |
| `resolve_launch_target("auto")` | 93.1 / 60.8 / 72.3 / 96.5µs（n=20） | **82.7µs** | 225.6µs | 新增（每次拉起一次；内部含一次 `desktop_install_path`） |
| `resolve_launch_target("web")` / `("desktop")` | 0.3µs（n=20，4 轮均 0.2–0.3µs） | **0.3µs** | 8.4 / 1.5µs | 新增；**只做字符串归一**，不做任何文件系统/注册表探测（错误②的实测依据） |
| `is_running()`——端口探测一次（**本机口径，见注**） | 509514 / 507865 / 508705 / 510040µs（n=5，即 **约 509ms**） | **509.1ms** | 512.7ms | **既有**（`pet/harness_launcher.py:53` / `_candidate_ports`，本批一行未改） |
| `_harness_autostart_wanted()` 单次调用 | 中位 **0.4µs** / 最坏 2.8µs（n=50，初轮 ⑦） | 0.4µs | 2.8µs | 新增，**按路径调 3 次 / 4 次**（见结论 4，初版写「1 次」） |
| `import pet.harness_launcher` | 单独导入 tracemalloc 峰值 **4606.2 KB**；已加载后重复 import **55.8µs** | — | — | 既有：`pet/app.py:50` 早已顶层导入 ⇒ 本轮在 `modern_settings_dialog` 加同款导入的**边际成本为 0**（子进程实测 `harness_launcher` 在 `import pet.app` 后即在 `sys.modules`；`import pet.app` 峰值 25.01MB） |
| `pet/modern_settings_dialog.py` 行数 | 实测 **2380**（复审补文案后 +2） | — | — | 既有红线 2393 未越线（故未改预算注释） |

**端口探测那行的注（不这么写会误读）**：本机 loopback 对**未监听端口**不返回 RST 而是丢包，`socket.create_connection(..., timeout=0.5)` 每次走满超时（实测 38080 / 3080 / 59999 三个端口一律 `TimeoutError` ≈ 509–512ms）；对照有监听的桌面端 host 19387 只要 0.2–0.6ms。这是**本机特性**，与常说的「端口没人听就立刻 ECONNREFUSED」不同，端口探测这条路本批一行未改（`git diff` 无 `is_running` / `_candidate_ports`）。

### C. 按路径汇总（成本 = B 表中位之和；不含与本批无关的 dsh 命令解析）

| 拉起路径 | 探测成本 | 组成 |
|---|---|---|
| 显式 `target=web` | **约 1018ms** | 目标解析 0.3µs（可忽略）+ 2 × 端口探测 509.1ms |
| `auto` → web（未安装） | **约 1019ms** | 安装探测 418.8µs（默认位不存在，含注册表兜底）+ 2 × 端口探测 |
| `auto` → desktop（已在跑） | **约 18.4ms** | 安装探测 58.7µs + 进程探测 18.3ms |
| `auto` → desktop（未运行，默认位命中） | **约 18.4ms** | 2 × 安装探测 117.4µs + 进程探测 18.3ms |
| `auto` → desktop（未运行，默认位不存在） | **约 19.2ms** | 2 × 安装探测 837.6µs（含 2 次注册表兜底）+ 进程探测 18.3ms |
| （对照）显式 `target=desktop`（未运行，默认位命中） | 约 18.4ms | 安装探测 58.7µs + 进程探测 18.3ms |

**结论**：
1. **稳态开销无变化**：本批没有新增线程、定时器、网络或常驻循环。唯一周期性新增点仍是上一轮引入的 `DshMonitor._probe_online` 里的进程旁路（每 3s 一次，`pet/agent_link.py:1749`），且**只在三条端口候选全 miss 时**才执行——三轮测量中位区间 12.6–21.1ms（第三轮逐轮中位 17.3–19.8ms），占该后台线程约 **0.4–0.7%**（不在 GUI 线程）。本轮未改；如要收，方向是缓存进程扫描结果或按目标门控，属另一次设计变更。
2. **一次启动成本必须按路径写（本轮更正）**：见 C 表。原报告两处口径都不成立——「单次探测总和 < 0.2ms」漏了 desktop 路径上的 `desktop_process_running()`（`pet/harness_launcher.py:583`），差两个数量级；「web 目标 ~55µs」把只有 `auto` 才付的安装探测算给了显式 web（显式 web 的安装探测是 0 次）。web 目标的真实大头是端口候选探测（本机 2 × 509ms，机器相关）；本批对这条路径的真实影响是**减少**：改动前 `pet/app.py` 自己先做一轮 `any(is_running(p) for p in _candidate_ports())`、未命中再进 `launch_harness` 又做一轮 ⇒ 端口全 miss 时 spawn 路径共 4 次；本批把 app.py 那轮收掉后 spawn 路径只剩 2 次（表 A 那一行）。端口已监听时前后都是 1 次——`any()` 与 `launch_harness` 的 `for candidate in _candidate_ports()` 循环都在首个候选命中处短路（`pet/harness_launcher.py:597-602`）。相对一次桌面端 GUI 启动（数百 ms）desktop 路径仍低一个数量级。
3. **新增系统调用/磁盘/线程**：新增注册表读取（仅 Windows，且**只在默认安装位不存在时**；按路径 0 / 1 / 2 次，见 A 表）与全表 PID 枚举（两处触发：仅端口全 miss 的探测轮；desktop 目标拉起前的一次判定）；**无新增线程**，无网络，无磁盘写。
4. **`_harness_autostart_wanted` 的调用次数（本轮更正）**：单次 0.4µs（n=50），**每次自动拉起不是 1 次**——已有实例 / 未安装路径 **3 次**，正常 spawn 路径 **4 次**（真机实测，两组独立实现一致）。四个调用点：`pet/app.py:2107`（调度时，主线程）、`:2118`（worker 入口复检）、`:2129`（`cancel_check` lambda 内，由 `launch_harness` 在慢探测后评估）、`:2136`（`launch_harness` 返回后的补偿复核）。4 次 × 0.4µs 相对同路径 18ms 的进程扫描可忽略；本批相对改动前的真实变化是 spawn 路径**多付 1 次**（0.4µs 级，换来 desktop 探测窗口的中止闸）。
5. **内存**：新增一个 3 项下拉（字符串 + 一个索引集合，KB 级）；无新增缓存、无长驻容器；`_SELF_LAUNCHED_KIND` 最多等于自拉起进程数（≤ 个位数条目，随 `_SELF_LAUNCHED_PIDS` 同进同出）。

## 五、实机运行记录

**本机**：Windows 10 x64，真实开发机（非 CI、非 mock）。

1. **前提现场复现（旧文案对不上代码）**——列出真正收口自拉起 web 的调用点。初版只跑了 `PROBE-20261006.log` ⑤ 那次按**方法名**的扫描（只匹配 `_stop_self_launched_harness` / `_stop_harness_if_still_unwanted`），**复审更正（P2-7）**：按模块函数全名 `stop_self_launched_harness` 重扫（`probe_registry_and_callsites.py` ③，真实输出）多出 `pet/app.py:2138` 这一处：

```text
CALL pet/app.py:2138: harness_mod.stop_self_launched_harness()        # ← 启动窗口补偿（就是挂在本开关上的那一处）
CALL pet/app.py:2186: self._stop_self_launched_harness()             # ← 联动关闭（_stop_harness_if_still_unwanted）
DEF  pet/app.py:2188: def _stop_self_launched_harness(self) -> list[int]:
CALL pet/app.py:2196: return harness_mod.stop_self_launched_harness() # 方法内部的转发
CALL pet/app.py:2331: self._stop_self_launched_harness()             # ← 退出收口
```

   收口共 **三处真实调用点**（`:2138` / `:2186` / `:2331`）。**复审更正（P2-7）**：初版据此写成「全文件只有这两处调用点，**没有任何一处挂在 `harness_autostart` 开关上**」——`pet/app.py:2136-2138` 正是一处挂在开关上的补偿收口（拉起探测期间关掉本项 → 立刻收掉这一次刚拉起的实例，行为由 `tests/test_harness_ownership.py::test_autostart_stops_immediately_if_gate_flips_after_launch` 钉住）。所以旧 hint 的问题不是「开关根本不参与收口」，而是它把**稳态**收口说得像全部：稳态下确实只有退出 / 关闭联动两条路，但启动窗口那一次是立刻收掉的。文案已按这个分法改写（见下条）。

2. **真实设置页对象读出的逐字文案**（同一进程内构造真 `ModernSettingsDialog`，非截图推断；**复审更正（P2-6）**：初版 152 字的旧文案在此，现为改写后的 239 字）：

```text
[harness_autostart] hint（239 字）: 桌宠启动后自动拉起下面「自启目标」：dsh web 时在后台静默起服务（不开浏览器、不弹窗口），桌面端界面时直接打开桌面端应用。本项要同时开着 DSH 联动才会自启——联动关着时 dsh web 没有消费者，拉起只是白占一个进程。关闭本项后不再自动拉起；已经跑起来的 dsh web 不因此退出，例外是刚在拉起探测期间关掉本项——那一次刚拉起的实例会被立刻收掉。稳态下要等桌宠退出或关闭 DSH 联动时才收口。桌面端是你自己的应用，桌宠退出或关闭本项都不会结束它。仅主桌宠生效。
  含字面 Markdown '**' : False
```

   文案里两处新增事实的代码依据与机器守卫：① **自启门是三条件合取**（`_harness_autostart_wanted`，`pet/app.py:2161-2165`：`enable_chat` + 本开关 + `agent_link.dsh`）← `tests/test_harness_ownership.py::test_autostart_gated_off_when_dsh_link_disabled`；② **启动窗口补偿**（`pet/app.py:2136-2138`）← 上面引的那条收口用例。两处文案（设置页 hint + `README.md` 同一段落）各有一条守卫：`tests/test_requested_regressions.py::test_harness_autostart_hint_has_no_markdown_and_names_the_real_stop_gate` 与 `::test_readme_harness_autostart_paragraph_matches_the_launch_gates`；把文案改回旧口径两条都会红（本轮实测：`2 failed`）。

3. **平台能力假的现场行为**（把 `harness_launcher.DESKTOP_SUPPORTED` 置假后重建真对话框，等价于 mac/Linux 首启）：

```text
下拉项: [(0, '自动（dsh web 界面）', 'auto', 'enabled'), (1, 'dsh web 界面', 'web', 'enabled'), (2, '桌面端界面', 'desktop', 'disabled')]
存量 desktop 显示为: auto
弹窗项可用性: [('自动（dsh web 界面）', True), ('dsh web 界面', True), ('桌面端界面', False)]
硬选 desktop 后落盘值: auto
```

   本机（Windows）对照：三项全 `enabled`，`desktop_install_path()` 真实返回
   `C:\Users\me\AppData\Local\Programs\DeepSeek Harness\DeepSeek Harness.exe`。

4. **拉起点门调用次数（真机、真线程，不是静态扫描）**——在真 `AppShell`（真 `Config` + 真门方法）上跑 `_maybe_autostart_harness`。它起的是**真线程**，且产品在 `launch_harness` **返回之后**还有一次门复查（`pet/app.py:2136`），探针必须等该 worker 线程结束再读计数（首版探针没等，读到 3 而不是 4——那是探针竞态，不是产品行为）。两组独立实现结论一致（真实输出：`PROBE-CALLCOUNTS-20261006.log` ③ / ③b）：

```text
③  打桩 launch_harness 的返回状态：
    已有实例（already）        门调用 3 次
    正常 spawn（started）      门调用 4 次
    探测期被中止（aborted）    门调用 4 次
    未安装（not-found）        门调用 3 次
③b 真 launch_harness，只打桩 is_running / Popen：
    钉 web 边界 + 端口空闲 → 真 spawn    门调用 4 次（Popen 打桩记录 1 次）
    钉 web 边界 + 端口已占 → already     门调用 3 次（Popen 打桩记录 0 次）
    本机真实状态（auto→desktop 已在跑）    门调用 3 次（Popen 打桩记录 0 次）
```

   四个调用点（`pet/app.py:2107` / `:2118` / `:2129` / `:2136`）与逐路径成本见 §四结论 4。这就是「每次自动拉起只调 1 次」被推翻的现场。

5. **边界/失败路径（消融判别，六刀全红）**：

| 消融 | 结果 |
|---|---|
| 删掉 `pet/app.py` cancel_check 的 `not self._harness_autostart_wanted()` | `test_autostart_desktop_not_spawned_when_toggle_flipped_during_probe` **FAILED**（`_spawn_desktop` 收到 exe 路径） |
| 删掉 `pet/modern_settings_dialog.py:2323` 的保存回落 | `test_harness_target_desktop_disabled_and_never_saved_on_unsupported_platform` **FAILED**（落盘 `desktop`） |
| 删掉 `setItemDisabled` 调用 | 同上 **FAILED**（`isItemDisabled(2)` 为 False） |
| 删掉 `settings_widgets.py:868` 的 `action.setEnabled(...)` | 同上 **FAILED**（弹窗项仍 `enabled=true`） |
| **复审新增（P2-6）** 把 `harness_autostart` hint 改回旧口径四条（去掉联动门 + 启动窗口例外） | `test_harness_autostart_hint_has_no_markdown_and_names_the_real_stop_gate` **FAILED**（`'同时开着 DSH 联动' not in text`） |
| **复审新增（P2-6）** 把 `README.md` 同一段落改回旧口径 | `test_readme_harness_autostart_paragraph_matches_the_launch_gates` **FAILED**（`'不会拉起' not in para`） |

6. **无法自动验证的能力（诚实登记，不是沉默）**：
   - **本轮没有跑任何 GUI 截图/真机目视验收**：置灰项在真实 Windows 桌面上的观感（置灰对比度、弹窗 hover 态、1100/720px 窄宽度不裁切）**未经人眼确认**，`desktop-pet-ui-style` 要求的截图证据（默认/长文本/平台条件/禁用态）**未产出**。
   - **macOS/Linux 未验证**：无 mac 真机；非 Windows 行为由 `DESKTOP_SUPPORTED` 能力假 + 上述探针覆盖，属「模型/CI 覆盖」而非「真实平台已验证」。
   - **未做全 PR 验收**：本轮只跑聚焦测试与 ruff（见下节），全量套件留给主代理统一执行。
   - 未运行真实桌面端拉起/退出收口的实机动作（会真弹 GUI 窗口），该路径由替身边界测试覆盖。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | **All checks passed!** |
| 聚焦①（本轮新测试所在四文件） | `pytest -q tests/test_requested_regressions.py tests/test_harness_launcher.py tests/test_harness_ownership.py tests/test_harness_lifecycle.py` | **149 passed, 1 skipped**（**复审后 150 passed, 1 skipped**——新增 README 文案守卫） |
| 聚焦②（菜单/配置/架构/文档纪律/联动减法） | `pytest -q tests/test_pr_report_discipline.py tests/test_architecture.py tests/test_config_schema.py tests/test_agent_link_subtraction.py tests/test_menu_layout.py tests/test_sprite_menu_parity.py` | **198 passed** |
| 聚焦③（设置页族 + 桌面宠物特性，覆盖被改的共享下拉控件） | `pytest -q tests/test_settings_and_resources.py tests/test_settings_interaction_tabs.py tests/test_settings_overlay_copy.py tests/test_settings_process_isolation.py tests/test_settings_subslot_autostart.py tests/test_settings_event_gating.py tests/test_desktop_pet_features.py` | **187 passed** |
| 聚焦④（托盘菜单口径） | `pytest -q tests/test_tray_icon_ready.py` | **8 passed** |
| 架构红线 | `pytest -q tests/test_architecture.py` | **10 passed**（`modern_settings_dialog.py` 实测 2380 < 2393） |
| 断言有效性 | 见上节六刀消融 | 六刀全红 |
| 全量 | `python -m pytest -q` | **未跑**（本轮按父任务口径只做 focused，合计 542 passed / 1 skipped；全量由主代理统一执行） |

**复审补跑（P2-6 / P2-7，2026-10-06）**：

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | **All checks passed!** |
| 报告纪律 | `pytest -q tests/test_pr_report_discipline.py` | **67 passed** |
| 本轮改动面 | `pytest -q tests/test_requested_regressions.py` | **47 passed, 1 skipped** |
| 受影响的设置页族 + 归属门控 | `pytest -q tests/test_harness_ownership.py tests/test_settings_overlay_copy.py tests/test_settings_interaction_tabs.py tests/test_settings_and_resources.py` | **94 passed** |
| 架构红线 | `pytest -q tests/test_architecture.py` | **10 passed**（`modern_settings_dialog.py` 实测 2380 < 2393） |
| 消融判别（文案回退旧口径） | 见上节后两行 | **2 failed**（两条文案守卫各红一次），随后还原、复跑 **2 passed** |
| 计量证据 | `.scratch/dual-target-tail/PROBE-REGISTRY-20261006.log`（4 轮） | `REGISTRY_CALLED = 0`；默认位 / 注册表兜底 / 完整 desktop 启动探测三路径分别计量见 §四 |

**三轮补跑（计数口径复核，2026-10-06；只改报告，产品代码与测试零改动）**：

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | **All checks passed!** |
| 报告纪律 | `pytest -q tests/test_pr_report_discipline.py` | **67 passed** |
| 计量证据（新探针） | `QT_QPA_PLATFORM=offscreen python .scratch/dual-target-tail/probe_call_counts_by_path.py` | 逐路径调用次数 + 4 轮耗时，原始输出 `.scratch/dual-target-tail/PROBE-CALLCOUNTS-20261006.log`；三处更正全部由它复现（显式 `web` 安装探测 0 次、`auto`→desktop 未运行 2 次、门调用 3 / 4 次，两组独立实现一致） |
| 产品/测试改动面未变 | `git diff --name-only -- pet tests \| wc -l` | **17**（= §二 的 7 个实现 + 10 个测试文件）；第三轮只改本报告与 `.scratch/` 下被 `.gitignore` 忽略的探针，`pet/`、`tests/` 零改动 |
| 纪律测试可判别（消融） | 把 `## 四、性能分析` 改成 `## 四、性能` 后跑 `pytest -q tests/test_pr_report_discipline.py` | **1 failed**（`test_report_has_three_evidence_sections[...]`：`缺少必备章节：性能分析`），还原后复跑 **67 passed**（还原文件 md5 与消融前一致） |

## 七、已知限制与后续

1. **桌面端自动拉起本轮仅 Windows**（≠ 永久不支持）：非 Windows 上 auto 走 web、显式 desktop 报 `unsupported`，菜单项保留并如实弹「本版本仅 Windows 支持」提示框；设置页该项保留并置灰 + 写明原因。**没有**新增 macOS `.app` 探测占位路径（`.app` 是目录，Popen 会炸）。
2. `desktop_processes()` 全表枚举 **12.6–21.1ms/次**（三轮测量区间；第三轮 4 轮中位 17.3–19.8ms，随机器负载漂移）（**复审更正**：初版只写「18ms/次，仅端口全 miss 的探测轮」，漏了 desktop 目标拉起前的那次判定）：两处触发——仅端口全 miss 的 3s 探测轮（`pet/agent_link.py:1749`），以及 desktop 目标拉起前的 `pet/harness_launcher.py:583`。本轮不动，作为后续可选项登记。
3. **尚未做**：GUI 截图/窄宽度验收、mac/Linux 真机验证、全量套件、真实桌面端拉起→退出收口的实机动作。设置搜索面已覆盖（`_search_settings` 按 label + hint + objectName 匹配，`pet/modern_settings_dialog.py:1981`，新行的「自启目标 / harness_launch_target」都可搜到，不需另加别名）。
4. 桌面端 host 端口（本机实测 19387）是**版本相关**的：端口候选 + 进程旁路两条腿，任一条命中即 online，因此换版本换端口不会掉线。

## 八、风险与回滚

- **影响面**：菜单四项文案/接线、设置页两行、自启拉起路径、harness 拉起入口。web 路径行为零变化（有 `test_target_web_keeps_existing_web_command` 钉住逐字命令）。
- **配置迁移**：新增键 `harness_launch_target` 默认 `auto`，老配置读不到即 `auto`（等价于旧行为：有桌面端才拐）。非 Windows 上空写 `desktop` 会在下一次设置保存时回落 `auto`。
- **回滚**：`git checkout -- <文件>` / `git revert` 即可；无数据库、无外部注册项写入（`autostart` 登录项与本批无关）。残留状态只有配置里多出的一个键，删不删都不影响运行（`auto` = 旧行为）。
