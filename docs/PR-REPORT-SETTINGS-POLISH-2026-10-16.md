# PR 报告：设置页打磨收口 + 三端修复（`feat/settings-polish`）

> **基线**：`99bdc7f`（fix(overlay): 穿透卡死——click-only grab 看门狗收尾 #277，本分支的起点）
> **分支**：`feat/settings-polish`　**日期**：2026-10-16
> **范围**：34 个文件（实现 10、测试 16、文档 5、构建脚本 3），其中 **7 个新增文件**
> （5 个测试 + `pet/application_icon.py` + 本报告）；净 `+4165 / −142`
> （`git diff --numstat 99bdc7f` + 新增文件的 `wc -l`，与 `git status --short` 逐条对得上，见 §二；
> 已计入 §九 的 CI 返修增量与本报告自身的增长）
> **关联**：[`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 2026-10-16 条目（本轮门禁登记）、
> [`SETTINGS-INFORMATION-ARCHITECTURE-2026-08-27.md`](SETTINGS-INFORMATION-ARCHITECTURE-2026-08-27.md)
> 的「后继变更（2026-10-16）」（常规域两处归属调整）、
> [`ONEDIR_PACKAGING.md`](ONEDIR_PACKAGING.md) 的「运行期应用图标」
> **状态**：**未 commit / 未 push / 未构建 / 未部署**（按用户口径留给最终整合方）

## 一、核心特性

设置页在真实使用中暴露的问题分两类：**找东西找不到**（常规域把「光标隐藏时自动穿透」
和「直播捕获兼容」塞在同一组里、"装得下"的页却一直摆着跳转条、页尾多出一大块空白）和
**看得见但不对**（切主题后图标不变色、选中态对比度不足、`save` 与 `back` 是同一个箭头、
打包版标题栏是系统通用图标）。本刀把这两类一起收口，并在收口过程中把三条**三端必红**
的测试缺陷与页内标签域的判据漏层一并修掉。

用户可见的变化：

| # | 能力 | 说明 |
|---|---|---|
| 1 | 「光标隐藏时自动穿透」回「窗口与系统」组 | 它和置顶 / 全屏隐藏同为窗口旗标类偏好，用户找它会先看这一组；原先它与「直播捕获兼容」同组，等于被埋掉 |
| 2 | 「直播捕获兼容」单独成「直播捕获（高级）」折叠组 | 行说明有四段（重启级切换 / OBS 捕获方式 / 平台限制 / 作用域），平铺在首屏就是逼用户读完；组描述只写一句"这一项做什么"，四段仍逐字留在行内，搜索照旧可达 |
| 3 | 短页不再摆跳转条、页尾不再多出空白 | 跳转条判据改量**落定几何**（同步推平后复核），并补上页内标签那一层；1100×542…568 这一段从「错停显态 + 365…393px 页尾空白」变成「隐态 + 空白 0」 |
| 4 | 切主题后图标跟着变色 | 图标是位图，换 QSS 不会自己变色；改为按记录（名字 + 尺寸）在切主题后重画导航 / 保存并退出 / 重置 / 搜索框 / 各页按钮 |
| 5 | 选中态对比度达标 | 选中 ink 与侧栏 3px 左条共用 `settings_selection_accent(dark)` 一个真值，浅 `#0a7ae8` / 深 `#0a84ff`，两档对选中底 **3.35:1 / 3.07:1**（WCAG 1.4.11 非文本对比线 3:1） |
| 6 | `save` 不再和 `back` 共用一个字形 | `pet/context_menus/icons.py` 里 `elif name in {"back", "save"}` 拆成 `name == "save"` 的独立字形 |
| 7 | 作用域声明不再占一整行 | 「影响所有桌宠」这类声明从灰说明末尾拆成标签行右侧的独立标注；800 宽常规域页高从 606px 回到 **538px**（= 拆分前口径），跳转条消失的最小窗高 700 → **640** |
| 8 | 侧栏密度与宽度 | slot 页有两个重置按钮时 10 个能力域在默认 800×560 下装不下（「更新」被截在视口外）；侧栏宽度改为按字体度量取最小值，1.5 倍字体下按钮文案不再被省略。**CI 280 上 Ubuntu 仍差 1px（本机余量只有 4px），纵向间距再收到 3px、余量抬到 15–19px，见 §九** |
| 9 | 重置按钮自带作用域 | slot 页的两个破坏性动作改为「重置本宠设置…」/「重置全局设置…」，不必点开确认框或读 tooltip 才知道点的是哪一个 |
| 10 | 打包版窗口/标题栏图标 | 三端构建脚本各补一行 `--add-data` 把 `assets/icon.ico` 送进包，设置窗 `setWindowIcon(load_application_icon())` |

**红线 / 不变量**（本刀不允许被破坏的既有语义）：

- **无新增、无删除持久设置**：配置键、默认值、归属唯一性、依赖与迁移零改动，**行键一个都没动**。
- 「鼠标穿透」与「直播捕获兼容」的 `sys.platform == "win32"` 平台闸门**一个字没动**
  （非 Windows 上常规域仍是 3 个区）。
- 右键菜单与聊天窗的图标路径**逐字节未变**（它们拿不到设置窗的 Selected 图元，仍走单态图标）。
- 作用域文字**一个都没删**：`accessibleDescription` 仍是"说明 + 标注"全文，
  搜索索引照旧读得到（搜「所有桌宠」命中口径不变）。
- 全量 `python -m pytest -q` **7642 passed / 14 skipped / 0 failed**。

## 二、修改文件说明

### 全文件 numstat（含未跟踪）

`git diff --numstat HEAD` 覆盖已跟踪文件；未跟踪的 7 个新文件（含本报告）用逐文件行数计入
（每个文件均以换行结尾，已核对 `bytes.count(b'\n')` 与 `endswith(b'\n')`，行数与 `git`
口径一致）。本表与 `git status --short` 逐条对得上：**27 个已跟踪文件被修改 + 7 个新增文件**。
生成物（`build-onedir/`、`dist-onedir/`、`.scratch/`）在 `.gitignore` 内，不进本表、不进提交。

| 文件 | + | − | 类 |
|---|---|---|---|
| `pet/context_menus/icons.py` | 144 | 9 | 实现 |
| `pet/settings_widgets.py` | 307 | 11 | 实现 |
| `pet/settings_page_guide.py` | 181 | 12 | 实现 |
| `pet/settings_theme_qss.py` | 57 | 4 | 实现 |
| `pet/settings_pet_controls.py` | 36 | 12 | 实现 |
| `pet/modern_settings_dialog.py` | 35 | 22 | 实现 |
| `pet/settings_reset_defaults.py` | 19 | 6 | 实现 |
| `pet/settings_search.py` | 9 | 2 | 实现 |
| `pet/settings_menu_layout_editor.py` | 5 | 5 | 实现 |
| `pet/application_icon.py` | 79 | 0 | 实现（**新增文件**） |
| `docs/ONEDIR_PACKAGING.md` | 56 | 1 | 文档 |
| `docs/SETTINGS-CHANGE-GATES.md` | 57 | 0 | 文档（2026-10-16 门禁登记） |
| `docs/SETTINGS-INFORMATION-ARCHITECTURE-2026-08-27.md` | 17 | 0 | 文档（后继变更） |
| `docs/INDEX.md` | 3 | 2 | 文档（本报告登记 + 两行「何时必读」同步） |
| `docs/PR-REPORT-SETTINGS-POLISH-2026-10-16.md` | 511 | 0 | 文档（**新增文件·本报告**；行数为交回时的 `wc -l`，含 §九） |
| `scripts/build_onedir.ps1` | 7 | 1 | 构建（含 §九 的 UTF-8 BOM） |
| `scripts/build_macos.sh` | 5 | 0 | 构建 |
| `scripts/build_linux.sh` | 5 | 0 | 构建 |
| `tests/test_settings_page_guide.py` | 502 | 13 | 测试 |
| `tests/test_settings_theme_polish.py` | 539 | 0 | 测试（**新增文件**） |
| `tests/test_settings_sidebar_and_chrome.py` | 434 | 0 | 测试（**新增文件**；含 §九 的余量口径登记） |
| `tests/test_settings_scope_notes.py` | 337 | 0 | 测试（**新增文件**） |
| `tests/test_application_icon.py` | 322 | 0 | 测试（**新增文件**） |
| `tests/test_settings_compat_layering.py` | 267 | 0 | 测试（**新增文件**） |
| `tests/test_settings_overlay_copy.py` | 55 | 14 | 测试 |
| `tests/test_settings_reset_defaults.py` | 54 | 2 | 测试 |
| `tests/test_menu_layout.py` | 42 | 12 | 测试 |
| `tests/test_settings_ia_first_cut.py` | 34 | 4 | 测试 |
| `tests/test_stream_capture_copy.py` | 22 | 4 | 测试 |
| `tests/test_architecture.py` | 9 | 1 | 测试 |
| `tests/test_settings_default_marks.py` | 5 | 1 | 测试 |
| `tests/test_requested_regressions.py` | 4 | 1 | 测试 |
| `tests/test_settings_slot_config_route.py` | 3 | 1 | 测试 |
| `tests/test_settings_subslot_autostart.py` | 3 | 2 | 测试 |
| | **4165** | **142** | 34 个文件 |

### 实现

| 文件 | 改动（对 HEAD 累计） | 改动意图 |
|---|---|---|
| `pet/application_icon.py` | +79（新增） | 运行期窗口/标题栏图标的唯一入口 `load_application_icon()`：`_MEIPASS` 与源码根双候选、缺件/坏件回退**空图标**（不是抛异常）、缓存跟随 QApplication 实例、无 QApplication 时不构造 QIcon（实测无应用时 `QIcon(<文件>)` 让进程以退出码 127 死掉，空 `QIcon()` 无碍） |
| `pet/context_menus/icons.py` | +144 / −9 | ① 渲染时把 `(名字, 尺寸)` 记在**消费者**控件上（`themedIconRequest`），并抽出 `_icon_consumer`：只有能把图标写回去的宿主才记；② 选中态取设置窗的选中强调色（与 QSS 同一真值）；③ `save` 与 `back` 拆开字形 |
| `pet/settings_widgets.py` | +307 / −11 | ① `SettingsSidebarPane`（宽度按字体度量取最小值，事件驱动的单发重算）；② `settings_sidebar_item` / `refresh_settings_icons`（按记录重画，含侧栏项 / 列表项 / 搜索框 action 三分支）；③ `SAVE_EXIT_TOOLTIP` + `settings_save_exit_button`；④ `SettingRow.set_scope_note`（标注挂在标签那一行，`setWordWrap(False)`）；⑤ `CONTENT_READING_MAX_WIDTH = 800`；⑥ 快捷启动项把请求记进 `THEMED_ICON_ROLE` |
| `pet/settings_page_guide.py` | +181 / −12 | ① `_apply_visibility` 改**有界两拍**：算 → 变了就施加 → `_settle_geometry()` 同步推平 → 复核（同步，不排队、不用定时器、不放大窗口）；② 新增 `_tab_chrome` / `tab_chrome_height` / `current_page_height`，`_content_overflows` 与 `_PastEndPadding._height_for` 改量**整块滚动内容**（页高 + 标签那一层），容器由调用者传入以免非标签域热路径新增子树查找 |
| `pet/settings_theme_qss.py` | +57 / −4 | 新增 `SETTINGS_SELECTION_ACCENT` / `settings_selection_accent(dark)` 与 QSS 占位记号 `@selection-accent@`：选中左条与图标 ink 共用**同一个真值**，不可能各写一个色号 |
| `pet/settings_pet_controls.py` | +36 / −12 | 新增 `ALL_PETS_SCOPE_SENTENCE` / `GLOBAL_SCOPE_ROWS` 接线表；`_apply_window_scope_rows` 改为走 `set_scope_note`，并把全局键的同类声明合成同一个 pass（主文件有行数预算，不允许再接线一次）；两个「试听」按钮的图标宿主从 `host` 改成按钮自己 |
| `pet/modern_settings_dialog.py` | +35 / −22（**净 −1 行**，2515 → 2514） | `setWindowIcon(load_application_icon())`；侧栏改 `SettingsSidebarPane` + 间距 9→6 / 行距 2→1（§九 因 Ubuntu 再收到 **3**）；`_add_page` 改用 `settings_sidebar_item`；保存钮改用工厂；搜索框图标宿主改成它自己；`_apply_selected_theme` 末尾加一行 `refresh_settings_icons`；常规域装配表拆出「直播捕获（高级）」；`_page_shell` 默认宽度改取 `CONTENT_READING_MAX_WIDTH`；`QListWidgetItem` 导入随之删除。**行数预算未上调也不吃满**（`tests/test_architecture.py` 仍 2515，文件 2514） |
| `pet/settings_reset_defaults.py` | +19 / −6 | 新增 `RESET_SLOT_BUTTON_TEXT`（「重置本宠设置…」）与改措辞的 `RESET_GLOBAL_BUTTON_TEXT`（「重置全局设置…」）：slot 页两个破坏性动作各自把作用域写在标签上；全局页沿用原文案，不自称"本宠" |
| `pet/settings_search.py` | +9 / −2 | `_row_text` 把 `scope_note` 也算进索引：那句声明原本拼在 hint 末尾、因此本来就在索引里，拆成独立标注只是换了呈现位置，不该从搜索里掉出去 |
| `pet/settings_menu_layout_editor.py` | +5 / −5 | 5 个编辑器按钮的图标宿主从"编辑器面板"改成**按钮自己**（记录挂在消费者上，重画才写得回去）；像素逐字节一致 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_settings_theme_polish.py` | +539（新增，19 例） | 四档主题下四类图标的墨色、浅→深→浅往返、选中 ink 与左条同色且 ≥3:1、hover 明显弱于 selected、每个记录了请求的消费者都画成设置窗墨色、菜单/聊天窗图标不取选中强调色 |
| `tests/test_settings_sidebar_and_chrome.py` | +430（新增，13 例） | 默认窗口 10 域全部可见不滚动、两种窗口尺寸下每域可达、侧栏子控件不被裁、放大字体不省略按钮文案、侧栏宽度按策略跳过撑满控件、阅读宽度与页头同一条契约、紧凑窗不裁切、设置窗带应用图标 / 图标不可用时仍能开窗 |
| `tests/test_settings_scope_notes.py` | +337（新增，13 例） | 声明从说明移入标注且逐字保留、重复调用不吞字、空标注收回、全局键行带标注、窗口级注入不丢、搜索仍命中、最坏组合（最长标注 + 最长标签 + 1.5 倍字体）不被压窄、标注不给行加高、标签行 `heightForWidth` 只等于标签自己 |
| `tests/test_application_icon.py` | +322（新增，21 例） | 双候选优先序、源码根解析、不依赖 CWD、入库 ICO 档数等于生成器声明、冻结件优先、坏件回退、无应用不构造 QIcon（子进程真实跑）、缓存不跨应用实例、三端脚本语法门 + 真的带了这一行且目标目录等于产品常量、安装器不多加条目、文档登记 |
| `tests/test_settings_compat_layering.py` | +267（新增，8 例） | 穿透行回主组、折叠组内文案完整、组描述只有一句、作用域标注可访问可搜、搜索找到捕获行并展开组、组标题可达、紧凑宽度无横向滚动 |
| `tests/test_settings_page_guide.py` | +502 / −13 | 新增页内标签域 2 例 + 临界带 3 例；`BAND_DOMAIN` 改用三平台都 ≥4 区的「自动化与联动」、基准窗高按实测反推（不再写死 900）；`_needed_height` 从"只量子页"改成量**整块滚动内容**（原来等于把产品那句错口径抄进测试） |
| `tests/test_settings_overlay_copy.py` | +55 / −14 | 文案断言跟随「作用域标注挂在标签那一行」的呈现变化 |
| `tests/test_settings_reset_defaults.py` | +54 / −2 | 两个重置按钮的文案与作用域一致性 |
| `tests/test_menu_layout.py` | +42 / −12 | 常规域分组顺序与折叠态随「直播捕获（高级）」拆出同步 |
| `tests/test_settings_ia_first_cut.py` | +34 / −4 | 常规域顶层顺序（4 个区，含 `stream_capture`） |
| `tests/test_stream_capture_copy.py` | +22 / −4 | 捕获行整段文案在折叠组内一条不少 |
| `tests/test_architecture.py` | +9 / −1 | `modern_settings_dialog.py` 行数预算新基线 2514 |
| `tests/test_settings_default_marks.py` / `tests/test_requested_regressions.py` / `tests/test_settings_slot_config_route.py` / `tests/test_settings_subslot_autostart.py` | 各 +3…+5 / −1…−2 | 随上面几处呈现与分组变化同步的行键/文案快照 |

### 文档与构建脚本

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `docs/ONEDIR_PACKAGING.md` | +56 / −1 | 新增「运行期应用图标：`assets/icon.ico`（三端都带）」一节（为什么 `--icon` 不算数、真机实测落点、macOS 交叉链接口径、安装器不用额外条目）与冒烟清单第 9 条 |
| `scripts/build_onedir.ps1` / `build_macos.sh` / `build_linux.sh` | 各 +5…+6 / −0 | 各补一行 `--add-data` 把 `assets/icon.ico` 送进包 + 一段说明为什么漏掉不报错 |

### 未改动（故意没动）

- `pet/app.py` 的应用级 `setWindowIcon`（本刀范围外；exe 自带的文件图标已覆盖任务栏与
  资源管理器）。
- 右键菜单 / 聊天窗的图标取色路径：逐字节未变，另有两条用例钉住它们**不取**选中强调色。
- `cursor_hidden_passthrough` / `stream_capture` 的平台闸门与行内文案：逐字未动。
- `PER_SLOT_SETTING_KEYS`、`Config._initial_data()`、任何配置键的默认值：一字未动。
- DLC 相关目录与日用进程/配置：未触碰（用户明确划界）。

## 三、实现要点

1. **跳转条判据要量在"落定几何"上**。跳转条藏掉之后，滚动视口要等下一轮事件循环才长回
   它让出的那 28px；判据却在这一拍就重判，量到的还是矮视口，而 `hidden` 分支又不补自己
   那一段 ⇒ 判据说「装不下」⇒ 把自己显示回来。结果是**双稳态且停在错的显态**：内容其实
   装得下却一直摆着跳转条（带内最坏点实测：显态 + **381px 页尾空白**）。修法是显隐变更
   **当场**从跳转条往上逐层 `layout().activate()` 到滚动区所在那一页，再复核一次——
   **同步，不排队、不用定时器、不放大窗口**。
2. **判据量的必须是"整块滚动内容"，不是它里面的子页**。`current_page_content` 在页内标签域
   返回的是**子页**，拿它跟整块滚动视口比就漏掉 `SettingsTabContainer` 的标签栏 + 12px 间距：
   `子页高 <= 视口 < 整块内容高` 这一小段答成"装得下"、跳转条收起来，而用户明明要滚才看得完。
   同一句错口径还留在页尾留白的"装得下"闸里，只改一处会出现"跳转条摆着却点不到"的半修状态。
3. **图标是位图，QSS 换不掉它**。渲染入口把 `(名字, 尺寸)` 记在**消费者**控件上（能不能
   兑现才记，`_icon_consumer`），`_apply_selected_theme` 末尾按同一个名字与尺寸重画一遍；
   侧栏项与快捷启动项不是控件，请求记在项的数据角色 `THEMED_ICON_ROLE` 上。顺手修掉同族
   缺陷：页面内容先独立构造、之后才挂进对话框（菜单 / 快捷启动两页），那些图标在渲染时
   拿不到设置窗上下文 ⇒ 墨色退化成应用调色板黑 `#000000`（深色卡片上几乎看不见）且没有记录。
4. **同一个蓝色不可能同时满足明暗两档**。`#0a84ff` 浅色 2.89:1 / 深色 3.07:1；压深到
   `#0a7ae8` 后浅色 3.35:1 / 深色 2.65:1（越让一边好、另一边越差）。所以按档取值，并让
   QSS 左条与图标 ink 共用 `settings_selection_accent(dark)` **一个真值**。
5. **同一行里不能有两个可换行标签**。Qt 的 `QLayout.heightForWidth` 会退化成按当前几何
   求和：实测标签行量出 96px（标签自己只要 13px），页内标签容器取各页最大值 ⇒ 隐藏标签页
   也能把整域页高抬 103px。标注因此 `setWordWrap(False)`，只留标签一个可换行项。
6. **"未保存指示器"没有可靠信号，就不伪造**（见 §七）。

## 四、性能分析

**方法**：本机 Windows（`QT_QPA_PLATFORM` 未设 ⇒ 原生 `windows` 插件，`app.platformName()`
实测 `windows`），Python **3.13.7**、PySide6 **6.11.2**、PyInstaller **6.22.2**，
每档 **7 次取中位**。改前 / 改后是**同一台机器、同一份工作区，只换产品文件**。

### 4.1 本轮新增/改动路径的单次耗时（原始命令与日志）

| 量 | 改前 | 改后 | 差 | 命令 / 日志 |
|---|---|---|---|---|
| `_content_overflows`（**标签域**，桌宠） | 5.10 µs/次 | 7.74 µs/次 | **+2.64 µs** | `python .scratch/settings-reviewfix/probe_chrome_cost.py`（真机插件）→ `cost_before.log` / `cost_after.log` |
| `_content_overflows`（非标签域，语音） | 15.55 µs/次 | 15.81 µs/次 | +0.26 µs（噪声内） | 同上 |
| `_height_for`（标签域 / 非标签域） | 5.02 / 13.56 µs | 7.12 / 14.44 µs | +2.10 / +0.88 µs | 同上 |
| `refresh_settings_icons` 一次 | — | ≈16.3 ms（全窗扫 3174 个控件读属性 5.0 ms + 重画 17 枚 8.5 ms + 侧栏/列表项 ≈2.8 ms） | — | `python .scratch/settings-navfix/probe_cost.py`（离屏）→ `cost.log` |
| 记录 `(名字, 尺寸)` 到消费者控件 | — | **2.1 µs/次**（期间 polish=0 / stylechange=0，不触发 Qt 重排版） | — | `python .scratch/settings-navfix/probe_mechanism.py` |
| 开窗一次（`load_application_icon` 冷加载） | — | min 1.098 / median **1.223** ms（20 次） | — | `python .scratch/appicon/real_gui_probe.py`（真机插件） |
| 同上，命中缓存 | — | **0.198 µs/次**（100 000 次共 19.8 ms） | — | 同上 |

### 4.2 整段链路与开窗墙钟（真机，7 次中位）

| 场景 | 改前 | 改后 | 命令 / 日志 |
|---|---|---|---|
| 开窗 + 关闭 | 1070.7 ms | 1071.7 ms（+1.0 ms） | `python .scratch/settings-anchor-p2/probe_open_cost.py [--legacy]` → `open_cost_{before,after}.log` |
| 开窗 + 走完 10 个域 + 点 chip 跳转 + 换两个页内标签 + 三档 resize | 1916.0 ms | **1836.9 ms（−79 ms / −4%）** | `python .scratch/settings-anchor-p2/probe_cost.py [--legacy]` → `cost_{before,after}.log` |
| 同上：判据被调 / 显隐真的变了 | 413 次 / 70 次 | 406 次 / **56 次** | 同上 |
| 同上：同步推平 | 无 | 56 次，共 81.77 ms（**每次 1.46 ms**） | 同上 |

**同一台机器上重测的对照（本报告新增，非抄上文）**：在**最终代码**上重跑，
`probe_open_cost.py` → 中位 **1250.6 ms**（7 次 1186.1…1305.7）、`probe_cost.py` →
中位 **1947.2 ms**（7 次 1878.9…2110.6），判据 **406** 次、显隐真的变了 **56** 次、
同步推平 **56** 次共 84.91 ms（每次 1.52 ms）。**结构计数与 4.2 表逐位一致**
（406 / 56 / 56），墙钟比 04:57 那次会话高 **+16.7%**（开窗 1071.7 → 1250.6 ms）/
**+6.0%**（链路 1836.9 → 1947.2 ms）——本机单次样本散布
±60 ms 以上，且两次会话之间本机跑过全量套件与其它任务（同树有两个代理在改），**两次会话
的绝对值不可直接相比**；能站得住的结论是"结构计数一致、开销方向不变"，A/B 必须同会话测
（4.2 表就是）。

### 4.3 逐条回答四问

- **稳态开销有没有变化**：显隐不变时**一次都不推平**（`_settle_geometry` 只在状态真的改了
  才调）；判据本身的调用次数没有变化（它一直在那个 0ms 单发定时器里），每拍多算一次
  「标签那一层」（标签域 +2.6 µs；非标签域 0——容器由调用者传入，不再每拍在内容子树上
  再 `findChild` 一遍）。链路里判据 406 次 ⇒ 标签域上整段多花约 1.1 ms（占 1947 ms 的 0.06%）。
  侧栏宽度重算是幂等的：宽度没变时什么都不做。
- **新增路径的绝对成本与触发频率**：
  - 跳转条显隐**真的变化**时才触发一次同步推平（3 层布局 `activate()`，1.5–1.9 ms）：
    上面两个场景里分别是 56 次 / 开窗 7 次（开窗合计约 13 ms，占开窗 1%）。
  - `refresh_settings_icons` 约 16.3 ms，触发频率 = **开窗一次 + 用户每次切主题**
    （实测开窗 595.3 → 619.4 ms，+24.1 ms / +4.0%；切一次主题 349.2 → 370.3 ms，+21.1 ms / +6.0%）。
  - 应用图标冷加载 1.223 ms，**每进程每个 QApplication 实例最多一次**；之后 0.198 µs/次。
  - 记录图标请求 2.1 µs/次，只在渲染时写一个动态属性；菜单宿主不满足 `_icon_consumer`，
    一次都不写。
- **有没有引入新的系统调用 / 网络 / 磁盘 / 线程 / 周期任务**：
  - 跳转条那条线：**都没有**。没有新增 `QTimer`（`settings_page_guide.py` 里仍只有那个
    `_sync_timer`，单发 0ms）、没有线程、没有 syscall、没有 I/O；`_settle_geometry` 只用
    局部变量，循环上界写死 2 拍。
  - 标签层判据：**都没有**。只读了标签容器与标签栏的既有几何。
  - 应用图标：**都没有**。不新增线程 / 定时器 / 网络 / 周期任务；加载只在窗口构造时走一次。
  - **唯一新增的定时器**是 `SettingsSidebarPane._sync_timer`（`pet/settings_widgets.py`）：
    单发、`interval=0`、挂在容器自己身上（child timer，容器销毁一并销毁）。它**不是周期任务**，
    只在 `LayoutRequest` / `StyleChange` / `FontChange` / `Show` 事件到达时启动一次，同一批
    事件里 `_schedule_sync` 用 `isActive()` 去重，回调里宽度没变就什么都不做。推到下一拍是
    必须的：`QDialog.setStyleSheet` 会在样式重算过程中把 `StyleChange` 派发给每个子控件，
    在那一刻改自己的固定宽度会重入 Qt 的样式/布局失效流程——**本机实测直接 access violation**
    （`_apply_selected_theme → setStyleSheet`），`tests/test_settings_reset_defaults.py` 与
    `tests/test_settings_sidebar_and_chrome.py` 都能复现。
- **内存与缓存有没有增长**：
  - 图标请求记录：多 17 个 `(str, int)` 元组（侧栏项 + 快捷启动项记在数据角色上）+ 重画
    产生的 QIcon（随控件释放）。
  - 跳转条：没有持久状态；`_settle_geometry` 只用局部变量。
  - 标签层：数值上只多缓存一个 `self._tabs` 引用（对象已存在），无新容器。
  - 应用图标：进程内常驻**一个** QIcon（419 110 字节 ICO 对应的 Qt 图像数据），
    缓存跟随 QApplication 实例，**不随窗口数增长**；换应用实例即失效重建。

## 五、实机运行记录

**本机真实环境**：Windows + 原生 `windows` 平台插件（本次实测 `app.platformName()` = `windows`，
环境里 `QT_QPA_PLATFORM` 为空）。**不是 CI、不是 mock**。下面把
「真实 Windows 截图」与「offscreen 产物」**分开列**，两者不混用为同一条证据。

### 5.1 真实 Windows 平台插件的截图与探针

| 产物 | 数量 | 生成方式 | 看什么 |
|---|---|---|---|
| `.scratch/settings-polish2/{light,dark}-{800x560,1100x760,720x500-f150,1600x900}/` | 80 PNG（8 档 × 10 域） | `python scripts/capture_settings_pages.py <目录> --width W --height H`（脚本**不设** `QT_QPA_PLATFORM` ⇒ 用宿主原生插件） | 标注挂在标签那一行；图标墨色与档位一致；无裁字；宽窗阅读宽度 |
| `.scratch/settings-navfix/shots/` | 12 PNG | `python .scratch/settings-navfix/capture_shots.py <目录>`（无 QPA 覆盖） | 浅/深两档下侧栏、菜单编辑器（改前是**黑**图标）、660 高时跳转条不再出现 |
| `.scratch/settings-anchor-p2/shots/before-1100x596.png` / `after-1100x596.png` | 2 PNG | `QT_QPA_PLATFORM=windows python .scratch/settings-anchor-p2/capture_band.py shots 1100 596` | 改前：内容装得下却仍摆着 chip 行、页尾多出 412px 空白；改后：chip 行收起、页尾那一颗「启动项（高级）」连说明一起装进一屏 |
| `.scratch/appicon/titlebar.png` | 1 PNG | `python .scratch/appicon/real_gui_probe.py` | 标题栏是蓝色桌宠头像，不是系统通用图标 |
| `.scratch/settings-polish/realwin/` | 5 PNG | `.scratch/settings-polish/realwin_probe.py` + `titlebar_shot.py` | 三档窗口的真机页面 + 标题栏条 |

**根因/前提的现场复现**（原始输出片段）：

- 跳转条双稳态：`python .scratch/settings-anchor-p2/probe_band.py [--legacy] 1100 584 624 4`
  （真机）→ 改前 592…616 全部「**显态（错）**，留白 408…432」；改后同一档全部「隐态，留白 0」。
  日志 `band_1100_before_realwindows.log` / `band_1100_after_realwindows.log`。
- 页内标签域：`python .scratch/settings-reviewfix/probe_tab_overflow.py 1100 1222 1282 10` →
  改前 `合计 18 条 FAIL`、改后 `合计 0 条 FAIL`；改前滚动范围 26…66 就是"用户确实要滚"的
  **独立证据**（不是拿产品口径自证）。日志 `tab_overflow_before.log` / `tab_overflow_after.log`。
- 切主题后图标墨色：`python .scratch/settings-navfix/probe_theme_switch_ink.py` → 四档场景
  （浅→强制深、浅→强制浅、深 + 强制浅、深→跟随系统）全部 "OK"，五类图标墨色与档位一致；
  每档**先在相反档落一次再切到目标档**，所以墨色只能来自"切主题后重画"。
- 应用图标：`python .scratch/appicon/real_gui_probe.py` → 不调 `setWindowIcon` 时
  `WM_GETICON(ICON_BIG)` / `(ICON_SMALL)` 都是 **0**（= 系统通用图标）；调
  `setWindowIcon(load_application_icon())` 后是 **222039939 / 1418858791**（真实 HICON 句柄）。
- 常规域归属（**本报告新增的独立核对，不靠源码推断**；本机原生 `windows` 平台插件，`app.platformName() = windows`）：构造真实 `ModernSettingsDialog`
  后遍历 `pages.widget(0)` 的分区与 `stream_capture` 行的父链，实测输出
  `应用启动=[autostart]` / `窗口与系统=[on_top, auto_hide_fullscreen, cursor_hidden_passthrough]` /
  `直播捕获（高级）=[stream_capture]` / `启动项（高级）=[harness_autostart, harness_launch_target]`，
  父链 `SettingRow < SettingsCard < SettingsSection[直播捕获（高级）]`。
  （`dock_icon` 是 macOS 专属，Windows 上不构造，故不在 `窗口与系统` 里。）
  同一探针另证 `balance_refresh` 的父链是 `SettingsSection[余额与服务状态]`（归「AI 与对话」），
  即快照里常规域的「后台服务」一行确已迁走（见 `SETTINGS-INFORMATION-ARCHITECTURE-2026-08-27.md`
  的「后继变更（2026-10-16）」）。

**用户可见行为的确认**：上述改动都由用户在此之前逐项点名（切主题图标不刷新、1100×556
页尾一大块空白、880 宽上下都摆跳转条等），本刀按点名的档位复现后再修；实机截图与墨色
读数逐张人工复核过（无裁字、标注不独占一行、图标色与档位一致）。

**边界与失败路径的实机观察**：

- 非 Windows 腿：用「pytest 初始化之后替换 `sys.platform`」模拟（`nonwin_plugin.py`），
  改前 **4 failed / 26 passed / 8 skipped** → 改后 **31 passed / 9 skipped**。
  **已知边界**（写在插件文档串里）：只换 `sys.platform`；连 `os.name` 一起改会让 `pathlib`
  当场选错实现（`INTERNALERROR: cannot instantiate 'PosixPath'`）。本轮涉改的两条闸门都是
  函数体内**运行时**读 `sys.platform`，故不受这条边界影响。
- 夹窗闸：带用例所需的窗口高被屏幕夹住时（真机插件、屏不够高）**如实 `skip` 并带上数字**，
  不伪装成产品缺陷；离屏平台（套件与 CI 的配置）不夹、照跑不跳。
- 应用图标缺件 / 坏件：只回退成空图标、不抛异常，设置窗仍能打开
  （`tests/test_settings_sidebar_and_chrome.py::test_settings_window_still_opens_when_the_icon_is_unavailable`）。

### 5.2 offscreen 产物（**与上面分开，不当实机证据**）

| 产物 | 生成方式 | 用途 |
|---|---|---|
| `.scratch/settings-anchor-p2/shots/before-1100x556.png` / `after-1100x556.png` | `capture_band.py` 默认 `QT_QPA_PLATFORM=offscreen` | 复现 ops 报的 1100×556 / 381px 空白那一帧；离屏字体渲染成方框，**只看结构** |
| `.scratch/settings-navfix/cost.log` | `probe_cost.py`（离屏） | 开窗 / 切主题的增量耗时百分比 |
| 各 `probe_*.py` 的离屏读数 | 多数探针默认 offscreen | 几何与判据的结构性对照 |

**离屏与真机的差量必须记住**：offscreen 下整页比真机矮 **46px**（1100 宽、常规域，
真机内容高 508 / 离屏 464），临界带的位置跟着移动——**拿离屏读数去判「跳转条该不该出现」
会得出相反结论**。本刀全部判据断言都按实测几何推尺寸（不写死像素），所以字体或平台一变，
它们跟着移动、不会假绿。

### 5.3 没做真机验证的部分（如实登记，不推断）

- macOS / Linux 的**真实构建与运行未跑**（本机只有 Windows）：非 Windows 只有"替换
  `sys.platform`"的模拟腿与文本级/源码级证据。
- **打包版未构建、未部署**（用户口径：今晚只修不发布，4.3.1 正式 tag 构建明早再定）。
  `--add-data` 那三行只有**最小 onedir 探针包**的实测（PyInstaller 6.22.2：产物
  `_internal/assets/icon.ico` 419 110 字节、冻结进程里 `is_file()` 为真）与契约测试，
  **不等于**本分支的完整包已经跑过。
- **Ubuntu 的那 1px 没有在本机复现**（§九）：这是一台 Windows 主机，WSL 里的容器运行时
  拉不到镜像（registry-1.docker.io 直连超时），所以拿不到 Ubuntu runner 的实测
  chrome 高度，只能从 CI 的 `scrollBar.maximum() == 1` **反推** chrome ≥ 144。本机可构造的
  最松字体组合（DejaVu Sans + CJK 兜底）停在 chrome = 143、余量 0 —— 正好是边界，再 +1px
  才复现同款判据。返修给的是 15–19px 余量，等于已观测差距（≥1px）的 15 倍以上。
- DLC / 日用进程与配置未触碰（用户明确划界）。

## 六、测试与验证

| 门 | 命令 | 结果 | 日志 |
|---|---|---|---|
| 相关测试族（20 个文件，最终代码） | `python -m pytest tests/test_settings_theme_polish.py tests/test_settings_scope_notes.py tests/test_settings_sidebar_and_chrome.py tests/test_settings_page_guide.py tests/test_settings_overlay_copy.py tests/test_settings_compat_layering.py tests/test_settings_ia_first_cut.py tests/test_settings_default_marks.py tests/test_settings_reset_defaults.py tests/test_menu_layout.py tests/test_requested_regressions.py tests/test_settings_subslot_autostart.py tests/test_settings_slot_config_route.py tests/test_stream_capture_copy.py tests/test_architecture.py tests/test_settings_interaction_tabs.py tests/test_settings_pet_tabs.py tests/test_settings_search_aliases.py tests/test_weather_settings.py tests/test_application_icon.py -q` | **452 passed / 1 skipped**（215.44s） | `.scratch/settings-reviewfix/focused_final.log` |
| 本刀两条焦点文件 | `python -m pytest tests/test_settings_page_guide.py tests/test_settings_compat_layering.py -q` | **40 passed** | `tests_green_after.log` |
| 非 Windows 腿（模拟） | 同上 + `-p nonwin_plugin` | **31 passed / 9 skipped**（改前同一命令 4 failed / 26 passed / 8 skipped） | `nonwin_after.log` / `tests_red_nonwin.log` |
| **全量** | `QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:randomly` | **7642 passed, 14 skipped, 3119 warnings in 1239.03s (0:20:39)**；`grep -c FAILED` = **0** | `.scratch/settings-reviewfix/full_suite_final.log` |
| ruff | `python -m ruff check pet/ tests/` | `All checks passed!` | `.scratch/settings-navfix/ruff.log` |
| CI 返修·焦点两条（语法门 + 侧栏） | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_application_icon.py tests/test_settings_sidebar_and_chrome.py -q` | **39 passed**（16.15s） | `.scratch/ci280-probe/focused_final.log` |
| CI 返修·读了 `build_onedir.ps1` 的族（8 文件 + `test_desktop_pet_features`） | `python -m pytest tests/test_bundle_slim.py … tests/test_desktop_pet_features.py -q` | **404 passed**（26.39s） | `.scratch/ci280-probe/ps1_family.log` |
| CI 返修·设置/壳层批次 | `python -m pytest tests/ -k "settings or chrome or menu_layout or architecture or modern_settings or desktop_pet_features or requested_regressions" -q` | **1007 passed / 1 skipped**（383.22s） | `.scratch/ci280-probe/focused_settings_batch.log` |
| CI 返修·脚本编码门（模拟 CI windows runner ACP=1252） | `python .scratch/ci280-probe/ps1_encoding.py` | 加 BOM **前 rc=1**（报错与 CI 日志逐字一致）→ **后 rc=0** | `.scratch/ci280-probe/ps1_encoding_before.txt` / `ps1_encoding_after.txt` |
| CI 返修·侧栏字体度量矩阵与合成 +1px 对照 | `.scratch/ci280-probe/font_matrix.py 6|3` / `cjk_fallback_scan.py` / `ubuntu_plus1px.py` | 余量 **0–4px → 15–19px**；chrome 144 时修复前 `max=1`、修复后 0 | `.scratch/ci280-probe/sidebar_metrics.txt` |
| ruff（返修后） | `python -m ruff check pet/ tests/` | `All checks passed!` | 见 §九 |
| **全量（返修后）** | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **7644 passed, 14 skipped, 3120 warnings in 1205.34s (0:20:05)**；`grep -c FAILED` = **0**；收集 **7658**（`--collect-only`：返修前的同一棵树也是 7658，返修不改用例集） | `.scratch/ci280-probe/full_after.log` |
| 空白 / 冲突标记 | `git diff --check` | 空（0 字节） | `.scratch/settings-navfix/diffcheck.log` |
| 换个目录跑（自检） | `cd C:/Users/me/Desktop && python -m pytest D:/…/tests/test_settings_page_guide.py D:/…/tests/test_settings_compat_layering.py -c D:/…/pytest.ini --rootdir=D:/… -q` | **40 passed** | — |
| 架构红线 | `python -m pytest tests/test_architecture.py -q` | **15 passed**（`modern_settings_dialog.py` 行数预算新基线 2514 ≤ 2515） | 见相关测试族 |

**全量日志的尾部逐字确认**（本次 `Read` 了文件尾部，不是转述）：
`7642 passed, 14 skipped, 3119 warnings in 1239.03s (0:20:39)`，`grep -c FAILED` = 0。
`7642 = 上一轮的 7640 + 本轮新增 2 条用例`，一条不多一条不少（同一台机器、同一份工作区）；
跑之前已核对产品文件与本轮改动逐字节相同，**本报告不改任何产品文件**。

**先红后绿的四组证据**（不靠"绿了就算"）：

1. 三端必红：非 Windows 腿 4 failed → 31 passed / 9 skipped。
2. 页内标签域两条新用例：把本轮产品改动全部撤掉 → **2 failed / 30 passed**
   （报错原文 `前提：带内跳转条摆着` / `前提：大窗里整块内容装得下`）；改回 → 40 passed。
3. 带用例不是空跑：去掉上一轮那条"当场推平再复核" → **3 failed**
   （报错原文 `「自动化与联动」开窗：内容高 1264px / 可用 1236px，跳转条显隐判反了`）。
4. 应用图标：撤 QGuiApplication 闸门 2 例红（含子进程**真实崩溃** exit 3221226505）、
   撤可读性判定 2 例红、撤应用实例键 1 例红；三次消融后逐字节还原，21 passed 复现。

**顺手修掉的两条既有测试缺陷**（本刀实测发现，非本刀引入）：

- `test_sidebar_width_ignores_widgets_that_fill_the_column` 在全量跑到时红、单独跑绿：
  前提写成绝对值（`QLineEdit.sizeHint().width() > 200`），而 `tests/test_screen_capture_ocr.py`
  的 `QFontDatabase.addApplicationFont` 会改变 Qt 对默认家族的解析——实测同一段代码里 'x'
  的 advance 从 **12 → 6**、`QLineEdit.sizeHint` 从 **210 → 108**。改为自己造一个"确定很宽"
  的撑满控件立前提。
- `tests/test_settings_page_guide.py::_needed_height` 对「内容自己就是标签容器」的域页取不到
  当前标签页，量成容器的高（实测 **1750 vs 产品口径 1255**）；本轮的判据断言要靠它，一并对齐。

## 七、已知限制与后续

1. **「未保存」指示器没做——没有可靠信号，所以不伪造**（用户已批准，属功能范围内）。
   可复现的排查结论：表单控件自己持有草稿，`Config` 在编辑期间**收不到任何写入**
   （`_write_config` 只在关闭/保存时把控件值写进 Config）；`Config.has_local_changes`
   （`data != _save_baseline`）比的是 Config 内存与"最后一次成功保存/读取"的基线，而即时
   生效的两个音效开关**自己会 `save()`**（基线跟着走）⇒ 它对"表单里有没保存的改动"
   既不必要也不充分。现成的「· 已修改」标记比的是**出厂默认值**（`_row_default_value` 读
   `Config._initial_data()`），不是相对盘上现值。要做得先在表单层补一个**草稿脏位信号**，
   本刀按"不新造轮询 / 不可靠全量 dirty"的要求不加，也没有伪造一个。
   作为替代，把**真实发生的**保存时机写进「保存并退出」的 tooltip（`SAVE_EXIT_TOOLTIP`）：
   直接关窗（X / Esc）同样保存、两个音效开关改一下立刻写盘、写入失败时问"继续编辑 /
   放弃未保存的改动并关闭"。
2. **跳转条的"不动点"仍有滞后**（既有设计，非本刀引入）：跳转条显着时视口矮 34px，而内容页
   `heightForWidth` 与当前几何有关。本刀把「量在了没落定的那一拍」这一半修掉；若将来某页
   真的出现"两态内容高不一致"，会重新出现带（更宽的一条），届时要改的是**判据口径**而不是
   时序——本刀不动那条线。
3. **700px 宽以下 + 1.5 倍字体时最坏组合余量约 15px**（最长标注 + 最长标签）。若日后加上
   更长的标注文案，需要重新评估是否让标注在极窄宽度下退化成独立一行。
4. **非 Windows 上常规域仍只有 3 个区**（「直播捕获（高级）」整组是 Windows 专属）。若哪天
   要把那一组改成三平台都建，属产品决策，另开。
5. **macOS / Linux 真实 GUI 未跑**，打包版未构建未部署（见 §5.3）。
6. 本分支 `git status --short` 里除本报告 §二 列出的 34 个文件外没有其他改动；`build-onedir/`、
   `dist-onedir/` 是本地构建产物（`.gitignore` 内），提交时不要带进去。

## 八、风险与回滚

- **影响面**：全部落在设置页（及其图标与打包资源）。右键菜单、聊天窗、桌宠渲染、碰撞、
  联动一律未触碰；两条平台闸门逐字未动。
- **开关**：**没有新增任何配置键**，因此没有新开关、没有迁移、没有回滚残留状态。
- **回滚**：`git revert` 本分支的提交即可，**不涉及落盘数据**（无新键、无默认值变更、
  无 `config.json` 结构变化）。唯一需要留意的是 `tests/test_architecture.py` 的
  `modern_settings_dialog.py` 行数预算新基线 2514——回滚时随测试一起回滚。
- **可再恢复的既有决定**：「光标隐藏时自动穿透」与「直播捕获兼容」的**行键、文案与平台
  闸门**都没有变，只是分组归属变了；若要把归属改回去，是纯装配表改动（`modern_settings_dialog.py`
  常规域的 `page_content` 列表），不涉及数据。

## 九、CI 返修（run 280：Windows 语法门 + Ubuntu 侧栏）

首轮三端（run 280 = `38820508434`：**ubuntu-latest 红** + **windows-latest 红** +
macos-latest 绿）暴露两条"本机绿、CI 红"的缺陷。两条都不能靠放宽门禁解决：一条是门禁
抓到了**真缺陷**，另一条是余量薄到 1px 就翻脸。返修共 3 个文件、**+11 / −7 行**（对 HEAD）：

| 文件 | + | − | 改动 |
|---|---:|---:|---|
| `scripts/build_onedir.ps1` | 1 | 1 | 第 1 行加 UTF-8 BOM（3 字节） |
| `pet/modern_settings_dialog.py` | 3 | 3 | 侧栏纵向间距 `6 → 3`（注释同步） |
| `tests/test_settings_sidebar_and_chrome.py` | 7 | 3 | 默认尺寸用例的 docstring 登记返修事实与余量口径（**断言一条没改**） |

**运行时开销**：零。BOM 只在 PowerShell 解析脚本时读一次（构建期，且 `shell: pwsh` 的
workflow 不受影响）；间距是构造期的一个整数。不新增系统调用/线程/网络/磁盘，不新增内存。

### 9.1 Windows：构建脚本在非 UTF-8 系统代码页下语法错误（**真缺陷**）

**症状**：`tests/test_application_icon.py::test_windows_build_script_stays_syntactically_valid`
在 `windows-latest` 红（`tests\test_application_icon.py:271: AssertionError`），PowerShell
解析器报 `Unexpected token 'ç¨‹åº'...` 与 `Missing closing '}' in statement block or type
definition.`，退出码 1；同一条测试在本机绿。

**根因**：Windows PowerShell 5.1 读**无 BOM** 文件用的是 `Encoding.Default`（= 系统 ACP）。
CI 的 runner ACP 不是 UTF-8（日志没直接记 ACP，由乱码形态 + 逐字复现反推为 **1252**）：
脚本里 10 638 字节的 UTF-8 中文注释被按 cp1252 解码，
解析器把乱码字节当成了引号/花括号 → 整份脚本**不可解析**。（本机 ACP = 65001，所以本机
这道门是**空门**。）

**为什么不能改成"显式 UTF-8 读文本再 ParseInput"**：仓库里**唯一**的 `.ps1` 就是它；
`docs/ONEDIR_PACKAGING.md` 写给用户的手工构建命令正是
`powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1`（= 5.1）；脚本自己
也已经踩过同一条坑并写明（读 `package.json` 必须 `[System.IO.File]::ReadAllText(..., UTF8)`，
否则「PowerShell 5.1 按系统 ANSI 代码页读 → 中文 description 变成非法 JSON」）。也就是说，
在 ACP≠UTF-8 的 Windows 上按文档构建会当场失败——门禁抓到的是**真缺陷**；把读取方式换成
显式 UTF-8 的 `ParseInput` 等于在门禁里把这条信号摘掉（它在本机复现不了）。

**修法**：给脚本加 UTF-8 BOM。带 BOM 的文件 PowerShell 一律按 UTF-8 读，与 ACP 无关，
脚本的**可解析性**因此在任何代码页下都成立；执行语义零变化（BOM 不影响 PS 7 / `pwsh`）。

**复现与验证**：`.scratch/ci280-probe/ps1_encoding.py` 把 PowerShell 的读取规则原样搬过来
（有 BOM → UTF-8；无 BOM → 指定 ACP），再交给**产品路径同一个** `Parser::ParseInput`，
所以被模拟的只有"解码选择"这一步：

| 场景 | 加 BOM 前 | 加 BOM 后 |
|---|---|---|
| `Parser::ParseFile`（本机 ACP=65001） | rc=0 | rc=0 |
| 模拟 ACP=1252（CI windows runner） | **rc=1**：`Unexpected token 'ç¨‹åº'. Build with a PATH " + … Missing closing '}' in statement block or type definition.`（与 CI 日志逐字一致） | rc=0（`via=BOM->UTF8`） |
| 模拟 ACP=936（GBK） | rc=0（乱码恰好仍是合法语法 → 只有部分代码页会红） | rc=0（`via=BOM->UTF8`） |

`tests/test_application_icon.py` 21 passed（含这条语法门）。

### 9.2 Ubuntu：默认 800×560 下侧栏第 10 个能力域差 1px 装不下（**余量薄**）

**症状**：`tests/test_settings_sidebar_and_chrome.py::test_default_window_shows_every_domain_without_scrolling`
在 `ubuntu-latest` 红（`:190`）：`assert 1 == 0`，`1 = QListWidget(settingsSidebar).verticalScrollBar().maximum()`。

**判据的粒度**：`scrollBar.maximum()` 是**按行**量（`singleStep=1`、`pageStep=11`），
内容只要比视口高 1px 就跳到 1（本机实测：视口 359 → 0，358 → 1）。所以这条红说明
**内容比视口高了至少 1px**，不是差一整行。

**本机实测的预算**（`.scratch/ci280-probe/sidebar_slack.py` / `sidebar_budget.py`，800×560）：

| 项 | 间距 6px（修复前） | 间距 3px（修复后） |
|---|---:|---:|
| 侧栏列表视口 | 363 | 378 |
| 10 行导航需要（显式 `setSizeHint(34)` + 行距） | 359 | 359 |
| **余量** | **4px** | **19px** |
| `scrollBar.maximum()` | 0 | 0 |

余量只来自侧栏纵向间距：导航行高是显式 token（与字体无关），另外 5 个子控件（保存并退出
32 / 搜索框 32 / 两个重置 30 / 版本号 15–19）高度由字号与 QSS `min-height` 决定。
换句话说，**任何平台的字体度量差异都直接从这个余量里扣**。

**字体度量敏感性**（`.scratch/ci280-probe/font_matrix.py` + `cjk_fallback_scan.py`：把设置窗
基础字体换成真实字体文件，逐个量 chrome 高度）：

| 设置窗基础字体 | 5 个子控件高度和 | 余量 @6px | 余量 @3px |
|---|---:|---:|---:|
| 本机 offscreen 默认（字体库为空） | 139 | 4 | 19 |
| SimSun | 140 | 3 | 18 |
| DejaVu Sans（Debian/Ubuntu 解析出的 "Sans Serif"） | 141 | 2 | 17 |
| Segoe UI / Arial / Noto Sans / Microsoft YaHei | 143 | **0** | 15 |
| DejaVu Sans + CJK 兜底（雅黑，模拟 `fonts-noto-cjk` 兜底那条路） | 143 | **0** | 15 |
| 上面任一 + 合成 1px（= CI 的 Ubuntu 情形：chrome 144） | 144 | **−1 → `max=1`＝CI 同款判据** | 14 → 0 |

结论：修复前本机余量只有 **0–4px**，任何平台多画 1px 就翻红——CI 上的 Ubuntu 正是这样
（`.scratch/ci280-probe/ubuntu_plus1px.py` 把 chrome 补到 144，`max` 就从 0 变 1）。
间距收到 3px 后新增 **15px** 布局预算；字体矩阵余量为 **15–19px**，合成 +1px 对照的余量为 **14px**，该对照通过。真实 Ubuntu 结果仍以返修后的 CI 为准。

**为什么只动间距**：`references/visual-system.md` 的 Layout 表把「侧栏外边距 12,16,12,12」与
「侧栏宽度 200」列为**设计令牌**（不动），导航行高 34 是显式 token（规范还要求"行高从
sizeHint 往上给、不为塞文案缩行"，不缩）；可动的只有间距——它是这里唯一的余量来源，
本轮把它从 9→6 再收到 3（5 处 × 3px = 15px）。

**没有改断言**：`scrollBar.maximum() == 0` 与逐项 `visualItemRect().bottom() <= viewport`
两条判据逐字保留；用例 docstring 只是把"余量只剩个位数像素"更新成实测的 0–4px、3px 后的
15–19px，并写明"再被吃掉就是默认尺寸真装不下，修法是继续收间距或按字体度量重算预算"。

**边界（如实登记）**：Ubuntu 的实测 chrome 高度拿不到——本机是 Windows，WSL 里的容器运行时
拉不到镜像（registry-1.docker.io 直连 `i/o timeout`），所以 Ubuntu 侧只能**反推**
（`max=1` ⇒ chrome ≥ 144）＋本机字体矩阵＋合成 +1px 的对照，不能声称"本机复现了 Ubuntu"。
若下一轮 Ubuntu 仍红，说明 15px 也不够，届时的修法是**按字体度量重算预算**（把 chrome 高度
算进来再定间距），不是继续手调像素，也不是放宽断言。
