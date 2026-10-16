# 截图识屏 P0（框选 → 动作条 → 提取文字/翻译预留/截图问答/复制图像）—— 实机与打包证据

> 分支 `feat/screen-capture-p0`。范围：右键菜单「截图 → 框选识屏…」单一入口，
> 采集闭环（藏窗 → 冻结帧 → 框选 → 松手出动作条），本地 OCR（RapidOCR 随包模型，断网可用），
> 结果浮层（可复制/可拖/可缩放/可继续提问）与灵动岛状态显示，截图问答为带图对话浮窗
> （图在输入栏上方、多轮、发送权在用户手上），复制图像直进剪贴板。
> 全局热键、多屏、翻译引擎、macOS/Linux 实机不在本片（见末节遗留）。

> **2026-10-14 下午交互重做**：首版（Enter 确认 + 三条菜单叶 + 系统确认框 + 固定面板）
> 实机验收被打回（压暗过重发白雾、面板丑且不能调、要按 Enter 不顺手、问答弹系统框）。
> 按豆包悬浮球动线重做：松手出动作条选动作、问答改对话浮窗、面板可拖可缩放真圆角、
> 菜单收成单入口。聊天输入框顺带补齐粘贴/拖拽图片与文件（同一轮实机反馈）。
>
> **同日晚间收口（round 2/3 + HDR）**：框前零压暗（对齐 PixPin）；结果面板/问答浮窗跟在
> 选区正下方；问答浮窗缩略图改输入栏上方 chip；「继续提问」关掉结果卡；翻译接通
> （聊天模型文本互译 + 结果卡「译为」语言行，切换用缓存原文直接重翻）；等待态是
> DeepSeek 鲸鱼吐泡泡动画（官方 logo 路径，simple-icons CC0）；复制图像的剪贴板同时塞
> 无损 PNG（Qt 单写只落 CF_DIB，Electron 系转换软化偏色）；**HDR 屏 FP16 截图通道**
> （DXGI Desktop Duplication，见 `PR-REPORT-HDR-CAPTURE-2026-10-14.md`）治 GDI 折叠的
> 文字灰化软化；菜单再拍平成直接动作「截图」（一个选项不套子菜单）；动作条「截图问答」
> 更名「问问肥鱼」。验收：用户实机确认"没啥问题了"。

## 一、修改文件说明

### 新增（产品）

| 文件 | 行数 | 改了什么 + 为什么 |
|---|---|---|
| `pet/screen_capture/session.py` | 204 | 采集会话状态机（idle→hiding→frozen→selecting→captured/cancelled→restoring），纯 Python 零 Qt，非法迁移拒绝 |
| `pet/screen_capture/host.py` | ~110 | `WindowHider`：隐藏/还原自家顶层窗口，账本含原激活态（恢复时还原），`restore_all` 异常也收口 |
| `pet/screen_capture/pixels.py` | 116 | 冻结帧抓取（grabWindow QPixmap→QImage 归一）、DPR floor/ceil 选区裁剪、统一 sRGB 8-bit |
| `pet/screen_capture/overlay.py` | ~380 | 框选覆盖层：**松手即钉住选区 + 动作条**（提取/翻译置灰/问答/复制/取消，带图标）、压暗 80（HDR 白雾修正）、白虚线框+尺寸标签、`MIN_SELECTION_SIDE=8` 防误触、`SelectionMemory` 按屏尺寸记上次选区（任何动作都记住） |
| `pet/screen_capture/controller.py` | ~230 | 采集闭环编排：hide → **DwmFlush 等一帧合成**（~5.5ms，审查 major 项的保险）→ grab → 框选 → `captured(图, 选区, 动作)` 三参输出；收口单点 `_teardown` |
| `pet/screen_capture/ocr.py` | ~830 | RapidOCR 引擎封装：**子进程用完即退**（切片5 B 方案）、退出码族+stage 分级人话错误；模型 sha256 单一真相源 |
| `pet/screen_capture/actions.py` | ~780 | 动作分发编排（动作由动作条带回，菜单不押注）+ `ScreenCapturePresenter`（岛短结果/面板长结果/继续提问回调）+ watcher 暂停恢复闸（现取式） |
| `pet/screen_capture/ask_dialog.py` | ~330 | **截图问答对话浮窗**：缩略图在输入栏上方、打字发问、多轮（后台线程发送+信号回 GUI）、可拖可缩放、Esc 关；浮窗即确认面（替代原系统 Yes/No 框） |
| `pet/screen_capture/result_panel.py` | ~500 | 结果浮层：真圆角（paintEvent 手画卡片——透明窗上 QSS 不落像素，A/B 实测）、accent 主按钮、可复制、双语槽位、Esc 关、贴边夹取+边缘翻转、不抢焦点、跟随宿主主题、**标题栏拖动 + QSizeGrip 缩放（用户尺寸进程内记忆）+ 底部「继续提问…」** |
| `pet/screen_capture/vision_bridge.py` | ~180 | 问答桥：选区 QImage → 内存 JPEG；`VisionConversation` 多轮会话（首轮带图+可选 OCR 文字参考，历史自持，不落盘） |
| `pet/screen_capture/reasons.py` | 小 | 置灰/待接入文案单一真相源（审查 m4） |
| `pet/qt_image_limits.py` | ~40 | 进程级图像解码上限抬到 1024MB（只抬不降；夹带项，见末节说明） |
| `scripts/verify_rapidocr_models.py` | ~150 | 构建期模型门（文件名+sha256）+ `--app-dir` 产物侧门（含引擎模块在 PYZ 图里的校验） |

### 修改（既有文件，逐处克制）

- `pet/__main__.py` / `pet/app.py`：启动点接 `apply_image_allocation_limit()`；`--ocr-worker` 子进程分流（切片5）；app.py 注入取岛回调（+3）
- `pet/vision.py`：`ask_about_screen` 增可选 `user_text`（None 时逐字原行为）；新增 `post_vision_messages`（messages_override 多轮入口，端点/Key 纪律/重试共用同一路径）
- `pet/chat/widgets.py`：输入框 `AttachmentTextEdit` 支持 **Ctrl+V 粘贴图片/文件**与**拖拽内存图**（浏览器拖图无 URL 场景）；内存图落临时 PNG 走统一附件校验，发送/移除后只清我们落盘的缓存文件
- `pet/window.py` / `pet/overlay_shell.py` / `pet/sprite_menu_facade.py` / `pet/context_menus/{registry,shared}.py`：右键「截图」子菜单收拢为单一入口「框选识屏…」（宿主回调三合一为 `on_screen_capture`；菜单不再押注动作）
- `scripts/build_onedir.ps1` / `build_linux.sh` / `build_macos.sh`：去掉 numpy/cv2 排除（留着=冻结包 OCR 全灭，实测）、加 `--add-data` 模型与 rapidocr yaml、加 `--hidden-import pet.screen_capture.ocr`（**审查 blocker：动态 seam 导致引擎模块不进包**）、接模型双门
- `scripts/slim_bundle.py`：numpy 移出违禁清单（已是合法依赖）、OpenCV 视频后端 DLL（28MB，OCR 不用）进移除清单
- `requirements.txt`：+rapidocr/onnxruntime/numpy/omegaconf（`test_runtime_dependencies.py` 门）
- `THIRD_PARTY_NOTICES.md` + `resources/rapidocr_models/{LICENSE,MODEL_LICENSES,NOTICE}`：许可登记（Apache-2.0/MIT/BSD）
- `docs/ONEDIR_PACKAGING.md`：随包 OCR 模型一节 + 体积口径更正 + 门接线说明
- `docs/INDEX.md`：本报告登记

### 测试（新增 14 个文件，~430 例）

`tests/test_screen_capture_{session,host,pixels,overlay,controller,ocr,actions,menu,result_panel,packaging,ask_dialog}.py`、
`test_qt_image_limits.py`、`test_verify_rapidocr_models.py`、`test_chat_composer_paste.py`（粘贴/拖拽附件 8 例）——
先红后绿，含变异/消融校验（去锁变红、去掉 hidden-import 的 A/B 包对照、假退出码三端一致性等）。
交互重做当日由独立子代理按新契约适配（49 红 → 全绿），适配中发现的两个产品缺陷
（面板复用尺寸钉死、空白答复空气泡）已修复并复验。

## 二、性能分析

真机实测（2560×1440@170Hz HDR 屏，dpr=1.0；OCR 数字为 Python 3.13.7 + onnxruntime 1.20.1 + rapidocr 3.10）：

| 环节 | 实测 | 样本 |
|---|---|---|
| 触发→冻结帧到手（藏窗+抓帧+等帧） | ≈40–60ms | grab 47.1ms@1440p / 29.1ms@1080p（n=20），hide 6.3ms，settle 5.5ms |
| 选区裁剪 + sRGB 转换（1200×900） | 1.13ms / 0.69ms | max 2.2 / 6.2 |
| OCR 模型加载（懒加载首触发） | 1975ms | 含 rapidocr import ~1.7s |
| OCR 冷识别（加载后首帧 800×400） | 1020ms | 8 块全中，置信度 0.946~0.997 |
| OCR 热识别 P50/P95/max | **675 / 739 / 774ms** | n=30，中英混排 |
| 识别后闲置 CPU | **0.00%**（关自旋实测） | — |
| 内存增量（旧进程内口径，已被 aaafe91 取代） | 加载 +114.5MB、平台期 162.7MB 不涨；unload 回吐 ~30MB | native 堆不还 → 子进程化（B 方案）已落地，见末节 |
| 内存增量（子进程化后，aaafe91 实测） | **主进程 RSS Δ+0.0MB**（47.8→47.9，3 次识别前后）；子进程峰值 307~320MB，退出后全机扫描 0 残留 | 源码态探针 `.scratch/screen-capture/probe_ocr_subprocess.txt` |
| OCR 端到端（子进程化后，暖/冷模型文件） | 2556~2592ms / 2617ms | 每次识别付 spawn+重载模型，较旧进程内稳态（801ms）多约 1.8s——用户拍板的取舍 |
| 启动期新增成本 | 截图栈不进启动路径（菜单函数内 import，实测省 ~55ms）；`import ocr` 21ms 且不载重模块 | — |

打包体积：探针包实测 334MB（消融视频后端后 306MB），增量构成 cv2 99MB + 模型 31.6MB + onnxruntime 29MB + numpy 27MB；
产品变体全量体积下次出包顺手回填（文档已标注）。CI 成本提醒：`test_runtime_dependencies.py` 因新依赖 ~10s→~85s。

## 三、实机运行记录

1. **HDR/色准探针**（真显示器，HDR 开，H27T22S）：`DisplayConfig`+DXGI 双通道判定 HDR 启用；
   5 个已知色块经 `grabWindow` 逐字节命中（偏差 0），与 PIL ImageGrab 交叉一致 94.7%（残差全是动态视频区）
   → **P0 不需要 WGC 备选路径**（`.scratch/screen-capture/probe_hdr_output.txt`）。
2. **藏窗→抓帧正确性探针**：亮纯色标记窗口走产品 hide→settle→grab 路径，冻结帧里标记像素 **0/134400**
   （对照组成立）。本机不复现"藏不干净"，等帧为保险（代码注释如实标注）。
3. **冻结包 A/B 对照**（审查 blocker 复验）：同源码同机两包——不带 hidden-import 的包引擎缺席、菜单置灰、
   产物门 exit 1；带上的包认出 `'frozen bundle ocr 12345\nquick brown fox'` 逐字正确、零网络请求（requests 打桩抛异常仍成功）、
   unload 后 −37.8MB 可重载再认。构建日志 0 WARNING。
4. **OCR 链路探针**：真引擎走编排层全链（解析→识别→浮层状态），无聊天配置时问答如实报「AI 对话通道不可用」。
5. **真机 UI 烟测**（2026-10-14，真 GUI 非 offscreen，探针 `.scratch/screen-capture/smoke_overlay_ui.py`）：控制器真实闭环——
   `start()` 到覆盖层上屏 184~505ms（含藏窗+等帧+抓帧）；合成鼠标拖拽出 1400×750 亮框（压暗 80+亮洞渲染正确，
   截图 `smoke_1/2`）；**松手即出动作条**（`smoke_2` 可见五键白 pill 带图标，选区左上尺寸标签）；
   Enter=默认提取文字走完整捕获路径；OCR 子进程识别 3.5~3.8s（机器高负载下 5.6s），认出 485~743 字；
   结果面板真机上屏（`smoke_3_result_*.png` + 面板自截 `smoke_3_panel_self.png`）：真圆角卡片、accent 复制按钮、
   细滚动条、标题栏可拖、右下角 grip 可缩放；
   探针进程 RSS 识别前后 Δ≈+1MB（子进程化兑现）。**覆盖层观感一项由此销账。**
   另：面板"透明窗 QSS 不落像素"缺陷由本探针真机抓出（A/B 最小复现：`background`/`background-color` 在
   `WA_TranslucentBackground` 下都不画，只能 `paintEvent` 手画）。
6. **HDR 重绘保真探针**（`probe_hdr_roundtrip.py`）：抓帧→覆盖层画出→再抓，逐像素比对——输出与"帧像素×压暗系数"
   逐位吻合（182→103 = ×0.569 = 1−110/255），重绘路径零失真；用户报告的"白雾"根因是压暗层在 HDR 屏的
   SDR 感知提亮下变亮（110→80 修正），不是抓帧/重绘失真。
7. **本机未验（如实登记）**：多屏/分数 DPR、HDR 源内容（PQ 视频）逐像素还原、
   Linux/macOS 构建与产物门（脚本接线有测试，未真跑）、完整产品变体构建体积。
   问答浮窗的**真实联网发送**（配置真 Key 走一轮多轮对话）未验——有打桩层的端点/Key 纪律测试，
   真链路等你配置后实机过一遍。

## 遗留与后续

- **OCR 子进程化（用户拍板 B 方案）——已落地（aaafe91）**：识别改为 `--ocr-worker` 子进程用完即退，源码态主进程 RSS Δ+0.0MB、
  冻结探针包端到端 2837ms / 主进程 Δ+0.7MB / 残留 0（证据 `.scratch/screen-capture/probe_frozen_package.txt`）。
  代价明账：每次识别较进程内稳态多约 1.8s（spawn + 重载模型）。冻结复验用的是最小探针包，完整变体的 `--app-dir` 门待下次出包回填。
- 翻译引擎（`translate.py` seam 就位，面板双语槽就位，动作条置灰带说明）；全局热键；多屏采集；选区记忆跨重启（涉配置键门禁）。
- 面板「钉住」按钮不做：本面板不自动消失、始终置顶，豆包 pin 的语义在我们这里没有对应物（如实说明，不是漏做）。
- `_last_image` 口径例外：为「继续提问」留的最近一次选区图会驻留内存到下次截图（纯内存、不落盘），与"用完就丢"的其余口径不同，刻意为之。
- 夹带项说明：进程级图像解码上限 256MB→1024MB（聊天附件/头像等同受益，坏图头最多多申请 1GB；取舍与实测在
  `.scratch/screen-capture/note-pr-report-2026-10-13.md`）。
