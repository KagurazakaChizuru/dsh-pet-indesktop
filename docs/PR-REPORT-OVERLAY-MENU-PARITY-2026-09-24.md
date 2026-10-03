# PR 报告：overlay 右键菜单完整 parity（模板感知 + 缺失条目补齐）

> **基线**：`4af5450`（feat(app): T5 默认化——默认 overlay 拓扑，`PET_RENDER_TOPOLOGY=legacy` 逃生门）
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-24
> **范围**：6 个代码文件（实现 3、测试 3）+ 本文档与 `INDEX.md`
> **关联**：`.scratch/single-overlay-window/HANDOFF.md`（Phase 4 全线）、
> [`CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md`](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md)、
> [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)（本改动**不加设置键**）

## 一、核心特性

**用户实机反馈**：「右键菜单就是老版的，但是设置里显示我用的是新版菜单」「该有的功能都不能少」。

根因（坐实）：`pet/sprite_menu_facade.py` 的 `build_sprite_full_menu` 硬编码 legacy 扁平布局
（`icons=False`），**完全不读** `context_menu_template`，且只覆盖了 `build_legacy_menu` 的一部分条目。
用户配置里 `context_menu_template = "modern"`（实机副本读回，见第五节），于是「设置说新版、右键出旧版」。

处置：facade 不再自带一份会漂移的布局，而是像窗口路径一样**按模板分发到既有建造器**：

```text
Config.context_menu_template
  → normalize_template_id → load_menu_template
      ├─ legacy → build_legacy_menu(menu, facade, template)   # 扁平旧布局
      └─ modern → build_modern_menu(menu, facade, template)   # 注册表 + 用户编排 + 图标分组
```

菜单结构因此只存在一份（`pet/context_menus/`），facade 的职责收窄成「把 legacy 窗侧的方法面
搬到 sprite 世界」。切换模板写配置 + **原位重开**（下一次右键与本次立即生效都覆盖）。

**红线 / 不变量**

- **不加新设置键**，不改 `pet/window.py` / `pet/app.py` / `pet/pet_sprite.py` / `pet/overlay_*.py` / `pet/library.py`。
- legacy 模板条目与 `build_legacy_menu` 同条件逐项一致（机器比对锁死）；modern 模板与
  `build_modern_menu` 同条件逐项一致；overlay 只允许三类额外项（`桌宠设置` / `隐藏桌宠` / `退出这只`）。
- 聊天门（`enable_chat`）、`win32` 门、音乐服务门、歌词开关门等**条件显示**逐点对齐；
  无实现的能力隐藏而不是留在菜单里当死项。
- overlay 的 per-tick 路径零新增（菜单/旋转/看屏都不在 tick 链上）。

### 缺失条目逐项处置表

| # | 条目 | 处置 | 路由落点 / 等价性 |
|---|---|---|---|
| 1 | AI 对话 | 补齐 | `facade.on_open_chat` → `PetInstance.open_chat`；聊天门 = `enable_chat`（无聊天打包变体整条不显示，与 `app.py:450` 同门） |
| 2 | AI 设置 | 补齐 | `PetInstance.open_chat_settings`，同门 |
| 3 | 黄金回旋 | 补齐 | `facade.trigger_golden_spin` → `OverlayShell.trigger_golden_spin`（新 sprite 版：`QTimer` + `golden_spin.GOLDEN_SPIN_*` 常量 + `window_effects.eased_progress`，共用 `PetSprite.set_throw_rotation`；探头/彩蛋会话在跑时让路，同 PetWindow「探头激活不叠加」） |
| 4 | 显示本轮消费 | 补齐 | 直写 `config.agent_cost_enabled`；消费结算在 `agent_link.py:3882` 读同一键，无需刷新钩子 |
| 5 | 音乐子菜单（暂停/下一首/上一首/退出音乐/打开网易云/打开 QQ 音乐） | 补齐 | `OverlayShell` 新增**歌词宿主四件套**（`install/sync/pause/shutdown_music_lyric`，逐行对齐 `window_optional_services`）+ `cfg` 只读别名；`音乐→暂停/切歌` 走 `now_playing`（`_run_off_main` 后台线程），`打开…给主人放歌` 走 `music_players`。**服务不可达整组隐藏**（`facade.music_service_available`，产品路径恒可达） |
| 6 | 边缘探头 | 补齐 | `facade.set_edge_probe_enabled` 只写 `config.edge_probe_enabled`；sprite 探头世界每次进入判定前热读该键（`overlay_shell._build` 注释），等价窗口版「写配置 + controller.set_enabled」 |
| 7 | 大小四档 | 补齐 | `build_size_menu` 原样复用：`facade.scale` 读 sprite、`change_scale` 写 sprite + `config.scale` |
| 8 | DeepSeek Harness | 补齐 | `add_harness(launch_harness_gui(facade))`，聊天门同 legacy（`on_open_chat` 是否存在）；模态父窗口经 `shared._dialog_parent` 解析到 overlay 窗（facade 不是 QWidget），反馈气泡走 facade 新增的宿主形 `show_bubble` |
| 9 | 打开网页版 DeepSeek | 补齐 | `QDesktopServices.openUrl`，无 pet 面依赖 |
| 10 | 主动识屏 | 补齐 | `facade.toggle_proactive_enabled` / `set_proactive_option` 写 `config.proactive_screen` + 共享 `proactive_watcher.apply_config()`（缺失时从 `AppShell._shared.proactive` 回填，等价 `_ensure_proactive_watcher`）；`win32 + 聊天门` |
| 11 | Agent 联动 | 补齐 | `facade.toggle_agent_link` → `agent_link_manager.set_enabled`（拒绝时回滚勾选，同 `window.py:3945`）；`set_agent_link_option` 写 `agent_link.report_gates` 的 0/1 两端 |
| 12 | 切换菜单模板 | 补齐 | `set_context_menu_template`（写配置，同 `window.py:3887`）+ `reopen_context_menu` 原位重开（新增 `ShellOverlayWindow.reopen_context_menu`） |
| 13 | 桌宠设置（legacy 模板） | 保留并补位 | legacy.py 的设置槽 `on_open_legacy_settings` 在 app 里**恒为 None**（`app.py:457`）；若不补，切到旧版后没有任何设置入口。按被点 sprite 的 D13 身份路由 `open_settings_for(sprite)` |
| 14 | 隐藏桌宠 | 保留 | legacy.py 没有；overlay 的隐藏语义（`set_pet_visible`）没有别的菜单入口，删掉即实机功能回退 |
| 15 | 退出这只 | 保留 | 仅多宠时注入，插在「退出」之前（4.2c D13 既有语义） |
| 16 | 其余 legacy/modern 已有一项 | 顺带补齐 | `看看屏幕`（新 `OverlayShell.look_at_screen`，`look_done` 信号 + vision worker）、`重命名当前角色…`（`facade.rename_character`）、`DeepSeek 余额`、`检查更新`、`待办提醒`、`立即报时`/`节日提醒`（AppShell 路由）、`生小肥鱼` 菜单头像（`facade.icon_pixmap`）、`播放动画` 缩略图（`facade.animation_icon_image` / `_cached_image`，缓存挂壳、128 条上限同窗口版） |

### 顺带修复的实机缺陷：`close_on_trigger` 命令不派发

`shared.connect_action` 对带 `closeOnTrigger` 的条目在菜单可见时只把回调挂进
根菜单 `_deferred_callbacks`（`defer_menu_callback`），由窗口在 `menu.exec()` 返回后统一派发。
`ShellOverlayWindow.contextMenuEvent` 此前**没有派发这一步** → overlay 下所有此类条目
（AI 对话 / 桌宠设置 / 隐藏桌宠 / 退出 / 生小肥鱼…）点下去静默无反应。本次补上同一条收口
（`_dispatch_deferred_menu_callbacks`，0ms 定时器绑长寿命窗口而不是菜单）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/sprite_menu_facade.py` | +531 / −68 | facade 重写为模板感知：`build_sprite_full_menu` 按 `context_menu_template` 分发 legacy/modern 建造器并安装同款菜单样式；补齐全套 pet 形方法面（聊天/设置/视觉/余额/更新/待办/报时/节日/识屏/联动/黄金回旋/探头/大小/重命名/音乐宿主/菜单图标/`show_bubble`/`dialog_parent`），新增 `music_service_available` 服务门与三个 overlay 专属条目（桌宠设置/隐藏桌宠/退出这只）的定位插入；`on_open_modern_settings` 闭包绑定被点 sprite（修 D13 身份丢失） |
| `pet/overlay_shell.py` | +219 / −1 | ① `ShellOverlayWindow`：`close_on_trigger` 挂起命令的派发收口 + `reopen_context_menu` / `_exec_full_menu_at`（模板切换原位重开）；② `OverlayShell`：歌词宿主四件套 + `cfg` 别名（挂进 `start()` / `refresh_settings()` / `stop()` / `aboutToQuit`）、`look_at_screen` + `look_done` 信号（vision worker，限流口径同窗口版）、`trigger_golden_spin`（QTimer 表现层旋转，常量复用 `golden_spin`/`window_effects`） |
| `pet/context_menus/shared.py` | +20 / −3 | `add_harness` 的模态父窗口改为点击时解析 `_dialog_parent(pet)`：窗口路径下 `pet` 就是 QWidget（无 `dialog_parent` 属性 → 原样返回自己，逐位不变），sprite 路径下取 facade 自报的 overlay 窗——否则 `QMessageBox(parent=facade)` 在点「重启/停止服务」时会 TypeError。这是本刀唯一一处共享建造器改动（必要的可复用性调整） |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_sprite_menu_parity.py` | 新增 +698 | 19 条：legacy/modern 两模板与**真实 PetWindow**同条件菜单树的机器比对（同父路径 + 兄弟顺序包含、额外项白名单）、用户点名缺失条目清单、模板差异（扁平 vs 分组 + `menuStyle`）、聊天门、harness 模态父必须是 QWidget、音乐服务门与宿主、点击路由逐项等价、`close_on_trigger` 挂起→派发（真实 `QMenu.popup()` + `trigger()`）、原位重开、黄金回旋、看屏限流/同步、歌词宿主降级 |
| `tests/test_sprite_menu_facade.py` | +21 / −6 | 原「窗口能力条目在根层」断言改为**递归**枚举 + 两模板各跑一遍（模板感知后条目落在分组子菜单里） |
| `tests/test_overlay_spawn.py` | +15 / −3 | `test_menu_has_spawn_entries` 同样改递归（生小肥鱼/退出子肥鱼在 modern 的「桌宠控制」组内） |

### 未改动（故意）

- `pet/context_menus/legacy.py`、`modern.py`、`registry.py`、`pet/menu_layout.py`、`pet/context_menu.py`：
  模板判定、布局模型与注册表**零改动**（facade 复用既有建造器与入口，避免两套模板语义分叉）。
  `legacy.py` 本身没有 `隐藏桌宠`、其设置槽由 app 关闭——这两处按「overlay 专属补充项」在
  facade 侧补，不动 legacy 布局。`shared.py` 只改了 `add_harness` 的模态父解析（见上）。
- `pet/window.py`、`pet/app.py`、`pet/pet_sprite.py`、`pet/overlay_window.py`、`pet/sprite_*`、`pet/tick_driver.py`、`pet/library.py`：未改（`window.py` 只作语义参照；sprite 旋转走既有 `set_throw_rotation`/`clear_throw_rotation`）。
- 设置页与配置 schema：**未改**（本刀不加/不改任何持久设置键）。

## 三、实现要点

1. **模板分发复用窗口路径的同一判定**：`normalize_template_id` + `load_menu_template`，
   样式安装（`apply_modern_menu_style` / `install_modern_check_indicators` /
   `install_responsive_menu_style` / `install_stay_open_interaction`）与
   `pet/context_menu.py::populate_context_menu` 逐条对齐——这是「设置说新版就必须出新版」的根因修复点。
2. **方法面而非布局**：facade 只提供 `cfg / scale / on_* / set_* / install_music_lyric` 等
   duck-typing 面（与 `PetWindow` 同名同签名），建造器无需知道自己在给窗口还是 sprite 建菜单。
3. **宿主优先级**：AppShell（余额/更新/待办/报时/节日）→ PetInstance（聊天/设置）→ 本壳
   （音乐/看屏/黄金回旋/菜单图标缓存）；共享 `agent_link_manager` / `proactive_watcher`
   缺失时从 `AppShell._shared` 回填，保证与 `PetWindow._ensure_*` 同语义。
4. **旋转通道复用**：sprite 只有 `set_throw_rotation` 一条整帧旋转通道，黄金回旋与抛掷彩蛋
   共用，故探头激活/彩蛋会话在跑时让路；角度与缓动直接 import `golden_spin` /
   `window_effects` 常量，不复制数值。
5. **挂起命令的派发**：定时器 context 绑窗口（长寿命）而非菜单——菜单在事件返回后即无
   Python 引用，绑菜单会让 0ms 定时器随对象消失、命令永不执行。
6. **缓存归属**：动画缩略图缓存挂壳（`_menu_icon_cache`，128 条上限 + 超限全清）而不是
   facade——facade 每次右键重建，缓存必须长寿命。

## 四、性能分析

**方法（可复现）**：
`python .scratch/single-overlay-window/menu_parity_probe.py`（offscreen，25 次取中位数；
配置 = 实机 `%APPDATA%\dsh-pet-standalone\config.json` 的副本）
环境：Windows / Python 3.13 / PySide6（仓库 `.venv`）/ 本机 2026-09-24。

| 指标 | 实测 | 归属 |
|---|---|---|
| overlay legacy 菜单建造 | median **6.00ms** / mean 6.10 / max 9.72（n=25） | 右键一次 |
| PetWindow legacy `populate_context_menu` | median **4.65ms** / mean 4.73 / max 7.24（n=25） | 既有路径（对照） |
| overlay modern 菜单建造 | median **24.90ms** / mean 25.42 / max 33.81（n=25） | 右键一次 |
| PetWindow modern `populate_context_menu` | median **20.29ms** / mean 20.56 / max 26.63（n=25） | 既有路径（对照） |
| `sync_music_lyric()`（`music_lyric_enabled=false`） | median **0.2µs**（n=200） | `start()` / 配置变更扇出 |
| `trigger_golden_spin()` | **0.152ms**（起 16ms QTimer，n=1） | 菜单点击 |
| `_dispatch_deferred_menu_callbacks`（无挂起命令） | median **3.8µs**（n=200） | 每次菜单关闭 |
| overlay 主动画树条目数 | legacy 69 / modern 75（真实配置） | 与对照树逐项一致 |

**结论**

1. **稳态开销**：tick 链零改动（新增能力都不在 `TickDriver` 上）；`OverlayShell.__init__` 多两个
   标量属性 + 一条信号连接（实测在噪声内）；`start()`/`refresh_settings()` 各多一次
   `sync_music_lyric()` = 0.2µs（关闭态立即返回）；`stop()`/`aboutToQuit` 只在控制器存在时才做事。
2. **新增路径成本与频率**：主要新增发生在**右键那一刻**——facade 与真实 PetWindow 走同一批建造器
   （真机数字见上表）。overlay 相对窗口路径的中位差为 legacy +1.35ms、modern +4.6ms（+29% / +22%）：
   来源是 facade 逐次重建 + 属性间接层 + 服务探测（3 个宿主 getattr）+ 2~3 个 overlay 专属条目
   （legacy 含 隐藏桌宠/桌宠设置）。相比「右键菜单本身要弹窗 + registry 解析 + 图标解码」的既有
   ~20ms 量级，这个增量在交互预算内；modern 的绝对成本几乎全部来自既有注册表路径（对照 20.29ms）。
3. **新增系统调用 / 网络 / 磁盘 / 线程**：
   - 磁盘：**0**（无新增文件读写；菜单图标缓存只在内存）；
   - 网络：**0 新增**（`打开…给主人放歌` / `看看屏幕` / 歌词取词都沿用既有实现，只在用户点击时触发）；
   - 线程：`看看屏幕` 每次点击 1 条 daemon 线程（与窗口版同款、同频率）；歌词采样线程**仅当
     `music_lyric_enabled=True`** 时存在（默认关，与 legacy 同纪律）；黄金回旋主线程 16ms QTimer，700ms 后停表。
4. **内存/缓存**：新增 `_menu_icon_cache`（≤128 张缩略图 QImage，超限全清，挂壳长寿命——
   与窗口版 `_animation_icon_image_cache` 同口径）；金旋/看屏只有几个标量；歌词控制器懒建。

## 五、实机运行记录

**本机真实环境**（Windows，源码树 + `.venv`，offscreen Qt；**不启动第二个产品实例**，避免与用户
正在运行的桌宠/单实例门（D4）相互干扰）。

1. **根因现场复现（真实配置）**：

   ```powershell
   $env:QT_QPA_PLATFORM="offscreen"
   .\.venv\Scripts\python.exe .scratch\single-overlay-window\menu_parity_probe.py
   ```

   ```text
   [probe] real config = C:\Users\me\AppData\Roaming\dsh-pet-standalone\config.json exists=True
   [real-config] context_menu_template = "modern"      ← 设置里就是新版
   [real-config] character = "shenshen"
   [real-config] music_lyric_enabled = false
   [real-config] quick_launch_apps = [{"name": "默认浏览器", "path": "", "kind": "default_browser"}]
   ```
   修前 overlay 无论该键为何值都出 legacy 扁平布局（用户截图：待机/转向/移动…逐项平铺）；
   修后同一份真实配置导出 **modern 75 项 / legacy 69 项**两套树（完整树见探针输出），
   modern 为「厉害了我的鲸 / AI 对话 / 看看屏幕 / 播放动画 / 切换角色 / 播放速率 / 大小 / 音乐 /
   桌宠控制 / 快捷启动 / 工具与帮助 / Agent 联动 / 主动识屏 / 待办提醒 / 桌宠设置 / 退出」。

2. **用户可见行为确认（可自动的部分）**：真实 `QMenu.popup()` + 真实 `QAction.trigger()`，
   `隐藏桌宠`（`closeOnTrigger=True`）在菜单可见时命令被挂起、菜单关闭后由新派发收口执行
   （`tests/test_sprite_menu_parity.py::test_close_on_trigger_action_defers_then_dispatches`）；
   菜单截图以真实配置渲染落盘（`.scratch/single-overlay-window/menu-shots/overlay-menu-{legacy,modern}.png`，
   255×610 / 238×458；像素非空校验：legacy 19 色 17340 个不透明采样点，modern 136 色 12224 点）。
   **诚实标注**：本机模型不支持读图，截图未经我肉眼核对；「弹窗观感/鼠标悬停」这类最终确认
   仍需用户实机右键一眼。

3. **边界与失败路径**：无聊天变体（`enable_chat=False`）下 AI 对话/AI 设置/看看屏幕/DeepSeek 余额/
   主动识屏/DeepSeek Harness 六项在 overlay 与真实 PetWindow 基准里**一起消失**（对照断言
   `test_chat_gated_entries_follow_chat_availability`）；音乐服务不可达时整组「音乐」子菜单被摘除
   （`test_music_group_hidden_when_service_unavailable`）；`Agent 联动` 的 `set_enabled` 返回 False
   时勾选态回滚（`test_menu_agent_link_rolls_back_when_manager_refuses`）。

4. **无法自动验证的能力与理由**：真正的「右键点在桌面上的宠物身上、菜单弹出、逐项点选」需要
   真实窗口系统与用户实时桌面；本机已有用户正在使用的桌宠实例 + D4 单实例进程门，起第二个实例会
   被静默退出（`0.88s` 静默退出是既有设计），因此本刀用「真实配置树导出 + 真实 QMenu 弹出/触发 +
   真实配置副本截图」三件套替代，并**明确留下用户实机确认这一项**（交付后请用户右键一眼）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/sprite_menu_facade.py pet/overlay_shell.py pet/context_menus/shared.py tests/test_sprite_menu_parity.py tests/test_sprite_menu_facade.py tests/test_overlay_spawn.py` | `All checks passed!` |
| 空白检查 | `git diff --check` | 无输出 |
| 聚焦 | `pytest -q tests/test_sprite_menu_parity.py` | **19 passed** |
| 验收选择集 | `QT_QPA_PLATFORM=offscreen pytest tests/ -q -k "menu or facade or overlay"` | **392 passed, 2881 deselected** |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **3262 passed, 11 skipped**（271.09s，收口前最终态复跑；含本报告的纪律校验 2 条） |
| 真实配置探针 | `python .scratch/single-overlay-window/menu_parity_probe.py` | 见第四/五节数字与树 |

## 七、已知限制与后续

1. **modern 模板下「音乐」子菜单按歌词开关裁剪**：`music_pause/next/prev/quit/lyric_align` 仍是注册表
   的 `_music_lyric_configured` 门（`music_lyric_enabled`）。实机配置该项为 `false`，所以 modern 下
   只显示两条「打开播放器」；**legacy 模板不受此门影响**（仍无条件六项）。这是与真实 PetWindow
   modern 菜单**逐点一致**的行为，未在本刀改动；若希望 modern 也恒显六项，需单独评审注册表门。
2. **「看看屏幕」用户触发识别的观感**未在真机弹窗验证（worker 走 vision + 聊天提供方，需网络/额度）；
   代码路径与窗口版同构，测试只覆盖限流、信号回流与同步进会话。
3. **黄金回旋是 sprite 等价实现而非移植**：`GoldenSpinController` 的「点击连击累计圈数/逐圈加速」
   属于点击链路（`window_optional_services._effects_route_click_golden_spin`），sprite 世界的点击路由
   不在本刀范围；菜单入口只做「转一圈」。
4. 全量门在**最终态**复跑（3262 passed / 11 skipped，含本刀的 19 条新用例）；
   `tests/test_pr_report_discipline.py` 在本报告入库后仍全绿（25 passed → 含本报告 2 条）。

## 八、风险与回滚

- **影响面**：仅 overlay 拓扑（`PET_RENDER_TOPOLOGY=overlay`，T5 后为默认）的右键菜单与三个
  菜单入口背后的能力；`PetWindow`（capture 模式 / `PET_RENDER_TOPOLOGY=legacy`）走的
  `populate_context_menu` 一行未改。
- **开关**：没有新增开关；老用户可用「切换到旧版菜单」回到扁平布局，或用
  `PET_RENDER_TOPOLOGY=legacy` 回到窗口路径。
- **配置迁移**：无（未加/改设置键；`context_menu_template` / `context_menu_layout` 读写口径不变）。
- **回滚**：`git revert` 本提交即可；无落盘状态、无 schema 变更。回滚后 overlay 菜单退回
  旧硬编码扁平布局（即用户反馈的那个状态），但不会有残留数据或缓存不兼容
  （`_menu_icon_cache` 只活在进程内，歌词控制器随壳销毁）。
