# 桌面 4.3.1：气泡风格、在线语音与关于页

基线：`15e0b7b`，分支 `feat/android-overlay-pet`；日期 2026-10-16（Asia/Shanghai）。
本轮保留已存在的 Android 未提交改动，以下统计只说明桌面增量。
关联：[设置门禁](SETTINGS-CHANGE-GATES.md)、[打包流程](ONEDIR_PACKAGING.md)、
[代理历史](NETWORK-PROXY-AND-VPN-2026-09-22.md)、[领域契约](../CONTEXT.md)。
原始证据位于 `.scratch/desktop-431/`，下文日志/图片/脚本路径均相对于该目录。

## 一、核心特性

- 气泡风格/字号从所属宠物档案读取，通用刷新不再用全局默认覆盖当前呈现者。
  已显示的文字/图片切换颜色、形状和朝向时重排；原有按钮、回调和隐藏期限保留。
- 本机旧 edge-tts 7.2.8 的中文、英文请求都在约 2 秒返回 403；同网络升级 7.3.1
  后分别得到 17856 / 18720 字节 MP3，FFmpeg 完整解码为 2.97 / 3.12 秒音频。
  上游 [7.3.0](https://github.com/rany2/edge-tts/releases/tag/7.3.0) 增加 Sec-MS-GEC v2，
  [7.3.1](https://github.com/rany2/edge-tts/releases/tag/7.3.1) 修正日期解析。
  这是本机已证实的协议兼容原因；不将任意 403 都归因于代理或旧版本。
- 作者账号并进「更新」页底部，**不新增侧栏能力域**：四个账号的复制保留 `@` 与大小写，
  GitHub 主页固定为 `https://github.com/MerZlin`，没有为另三个账号猜测主页链接。
  分区只读、不写入 Config、不参与重置，图标按设置窗自己的主题重画。

## 二、修改文件说明

本表以 **`origin/main` 为基线**（合并 main 后用 `git diff --numstat origin/main` 重算），只列本 PR
在 main 之上的**桌面侧**净增删。Android 侧文件（`android/**`、`docs/ANDROID.md`、两份 Android
报告、`scripts/android_*`、`tests/test_android_*`、README 的 Android 说明、`THIRD_PARTY_NOTICES.md`
的点击音效许可、`.gitignore` 的 Android 构建忽略）由 Android 报告逐文件说明，不在此重复；
原有 `.venv/` 不属于任何一轮代码变更。

| 文件 | 增删 | 改了什么、为什么 |
|---|---:|---|
| `requirements.txt` | +1/-1 | edge-tts 下限 7.3.1、上限 8（main 仍是 `>=6.1.10`），旧环境不再满足依赖。 |
| `pet/overlay_shell.py` | +5/-14 | 绑定及全局刷新按气泡所属宠物档案应用风格/字号，消除全局值覆盖。 |
| `pet/speech_bubble.py` | +63/-28 | 提取已有文字/图片布局用于实时重排，失效几何缓存，保留按钮、分页状态和消失计时。 |
| `pet/tts_diagnostics.py`（新增） | +43/-0 | 分类语音错误、惰性读取版本；错误消息不回显 URL/令牌/代理凭据；统一缺组件提示。 |
| `pet/voice_chime_service.py` | +15/-7 | 合成/音色列表使用脱敏诊断，记录实际出口类型，打包缺组件指向更新应用。 |
| `pet/settings_standalone.py` | +3/-1 | 独立设置窗口禁用试听时使用同一缺组件提示。 |
| `pet/settings_about.py`（新增） | +72/-0 | 账号表与复制/主页按钮的静态源；渲染请求记在按钮上，由设置窗按自己的主题重画。 |
| `pet/update_settings.py` | +2/-0 | 「更新」页底部挂上作者账号分区（import + 一行 `addWidget`）。 |
| `pet/settings_widgets.py` | +2/-2 | 已有区/卡片允许放只读 QWidget 行（返回类型仍是 `SettingRow` 的调用点不变）。 |
| `pet/settings_page_guide.py` | +1/-0 | 作者账号组的描述，遵循统一描述表。 |
| `pet/context_menus/icons.py` | +10/-0 | 共享矢量提供方增加 info/external_link。 |
| `scripts/verify_bundle_tts.py` | +63/-4 | 环境约束、包内版本/元数据一致性与原导入闭包检查；新增独立环境检查入口。 |
| `scripts/build_onedir.ps1` | +5/-0 | PyInstaller 前、产物完成后均执行 TTS 门禁。 |
| `scripts/build_linux.sh` | +2/-0 | 同样接入两个门禁，失败即停。 |
| `scripts/build_macos.sh` | +2/-0 | 签名前执行产物门禁，环境门禁在构建前。 |
| `scripts/capture_settings_pages.py` | +19/-1 | 显式 `--light`，避免深色 Windows 下把默认截图误称浅色。 |
| `tests/test_bubble_style_refresh.py`（新增） | +110/-0 | 五种风格、字号、多次刷新、slot0 缺席、几何/计时/按钮/隐藏状态回归。 |
| `tests/test_settings_about.py`（新增） | +81/-0 | 两种构建下账号分区都在「更新」页、复制内容、主页目标、配置不变，以及主题重画路径。 |
| `tests/test_tts_diagnostics.py`（新增） | +40/-0 | 403/超时/代理/空音频分类，敏感串不进入错误与日志，失败清理临时文件。 |
| `tests/test_verify_bundle_tts.py` | +25/-0 | 旧库、包内旧库、缺元数据、版本不匹配及不支持的大版本均失败。 |
| `tests/test_voice_chime_service.py` | +9/-2 | 源码与冻结场景的不同缺依赖提示。 |
| `tests/test_voice_chime_edge_voice.py` | +5/-2 | 网络替身使用真实异常类型语义；原临时文件清理断言保留。 |
| `tests/test_settings_process_isolation.py` | +18/-0 | 独立设置进程的缺库按钮状态及冻结提示。 |
| `CONTEXT.md` | +10/-0 | 作者账号的只读职责、版本及账号单源（术语由 About Page 改名为 Author Accounts）。 |
| `docs/ONEDIR_PACKAGING.md` | +14/-0 | 说明版本门禁和实际打包解释器要求，链接本报告。 |
| `docs/INDEX.md` | +5/-1 | 登记本报告与 TTS 门禁必读时机、`ANDROID.md` 行与 `ONEDIR_PACKAGING.md` 行的门禁触发词。 |
| 本报告（新增） | 见最终 numstat | 原因、逐文件说明、实测与边界。 |

**净变更为零的文件**（合并 main 后与 `origin/main` 逐字节相同，故不列表）：`pet/__init__.py`
（main 的 `dab867f` 已是 4.3.1）、`pet/modern_settings_dialog.py`，以及
`tests/test_architecture.py`、`test_desktop_pet_features.py`、`test_menu_layout.py`、
`test_settings_interaction_tabs.py`、`test_settings_pet_tabs.py`、`test_settings_page_guide.py`、
`test_update_feature.py`、`test_settings_sidebar_and_chrome.py`——后八个原先是「关于」独立成域
带来的侧栏顺序/行数预算/跳转条断言改动，作者账号并进「更新」页后全部退回 main 的样子
（第九节记了这次设计变更的来龙去脉）。

## 三、实现要点

气泡属性是 per-slot，`_speech_bubble` 则是当前可见呈现者，不能拿进程配置设置它。
通用刷新遍历实际宠物，使用已有档案入口；布局重排不重播 `show_text`、不重建交互按钮，
不重启隐藏计时。移动时的 `(anchor,size)` 快路径仍保留。没有新增配置键或配置迁移。

TTS 的版本约束只从 requirements 解析；元数据和构建环境版本必须一致，同时保留原模块
完整性检查。退出码 6 表示构建版本不支持，7 表示包内元数据缺失/不一致；Windows `_internal`
与 macOS Resources/Frameworks 都查发行元数据。错误路径惰性读取版本，启动设置页不导入 edge-tts。

“关于”页为 QWidget 只读行，复用 SettingsSection/Card；不注册成偏好，也不参与重置写回。
四个账号来自同一个表；复制按钮用系统剪贴板并给出提示，主页通过 QDesktopServices 打开。

## 四、性能分析

环境：Windows 11，Ryzen 7 H 255 / 16 逻辑核，Python 3.12，Qt windows 插件，DPR=1.5。
命令：`.venv/Scripts/python.exe .scratch/desktop-431/gui_evidence.py`，基线模块为开工快照。
原始 JSON：`gui-performance.json`。不是 CI/mocks；窗口由真实 Qt 创建和绘制。

| 路径 | 样本量 | 修改前中位 | 修改后中位 | 解释 |
|---|---:|---:|---:|---|
| 五种风格依次切换 | 100 轮 | 0.452 ms/轮 | 4.673 ms/轮 | 新版包括即时重排/定位，旧版只改属性，工作量不同。 |
| 原地跟随同一锚点 | 10000 次 | 0.0017 ms/次 | 0.0017 ms/次 | 高频缓存命中路径未增加重排。 |
| AboutPage 构造 + sizeHint | 50 次 | 不存在 | 3.397 ms/次 | 不包含整个设置窗口的既有构造成本。 |
| 中文实际合成 | 各 1 次 | 2.125s 后 403 | 2.110s / 17856 bytes | 新旧版本同网络、同文本、同音色直连。 |
| 英文实际合成 | 各 1 次 | 1.906s 后 403 | 1.625s / 18720 bytes | 网络单样本不是吞吐基准。 |

稳态：没有新增常驻定时器或线程，位置不变的绘制快路径实测相同。新增布局成本仅在配置/
样式/字号改变时发生。关于页增加四行控件，随设置窗口销毁；复制只在点击时访问系统剪贴板，
打开主页只在显式点击时交给系统浏览器。语音仍在原工作线程请求网络，原缓存写入/原子发布机制
不变；版本元数据只在错误路径首次读取，缓存上限一项。
另在 windows 插件预热 20 次后连续创建并释放 AboutPage 200 次：RSS 69640192 → 69672960 bytes
（增加 32KiB），句柄 341 → 341，Qt 顶层控件残留 0；见 `logs/about-memory.log`。
这是短测，不是长期 RSS 曲线，不作长期无增长承诺。

## 五、实机运行记录

旧代码探针：slot0 档案为 `glass_right`，通用刷新前气泡 `glass_right`，刷新后 `classic_top`，
档案仍是 `glass_right`。新增回归最初 `18 failed, 8 passed`（`logs/red.log`），
诊断分类/脱敏首次 `5 failed`（`logs/red-tts-diagnostics.log`），独立冻结提示另有红记录。

语音：`probe_tts.py` 在旧库运行后升级到 7.3.1 再运行；`tts-old/results.json` 与
`tts-new/results.json` 保留真实版本/状态/耗时，不写请求令牌或代理凭据。本机没有配置系统代理。
新版中文/英文 MP3 均用 FFmpeg 解码到 PCM，实际完整时长 2.97/3.12 秒。HTTP 101 是升级成功
状态，本报告以收到可解码音频作为合成成功，不以音色表可达或握手成功代替。

视觉：用 `scripts/capture_settings_pages.py` 在 windows 插件拍摄明暗主题、720/1100 逻辑宽度，
照片物理尺寸乘以 DPR 1.5；`screenshots/` 下四组全部保留。最初默认截图实际随系统为深色，
补显式 `--light` 后重拍；关于页复制图标显式继承深色语义色。已检查四账号、窄窗滚动及图标，
没有裁切或遮挡。`bubble-screenshots/` 五种气泡图由同一真实控件热切换产生，已检查深色玻璃及
吐气水泡；`logs/about-native.log` 真实 windows 插件下复制/只读/主页接线测试 3 项通过。

首轮冻结包已验证环境与包内均为 7.3.1、1995 个冻结模块、25 个所需模块齐全；
实际 EXE 主窗口 1.8 秒出现，独立设置窗口 1.3 秒出现。构建使用隔离 APPDATA，
没有替换/退出用户正在运行的 `E:/dsh-pet-standalone-webm-chat` 实例。
最终包与直接试听记录在交付补记中登记。

## 六、测试与验证

- 聚焦：气泡/关于/语音/档案/打包共 482 项通过；侧栏旧断言和独立缺组件提示修正后相关族 348 项通过。
- 满载：16 个 CPU 繁忙进程，气泡样式、语音服务、音色、设置进程隔离四族各轮 182 项，
  连续三遍通过，耗时 21.87 / 20.02 / 20.19 秒，见 `logs/stress*.log`。
- 首轮全量的失败全部是 7 个旧侧栏固定列表/尾页断言，均按用户要求新增关于页更新；
  不是放宽断言，仍精确检查完整顺序和图标。四个隔离生命周期族 68 项通过。
- ruff 已通过；两个 bash 构建脚本 `bash -n` 通过。最终全量、差异检查、包校验见交付补记。

## 七、边界与回滚

Windows 是真实已验证平台；macOS/Linux 已接入构建门禁与共享 UI，未在对应系统实际出包。
本机旧库失败和新库成功不能证明所有用户的 403 都只有一个原因，系统代理支持保留。
关于页没有自动获取账号信息、外部头像或后台网络访问。已有个人偏好无需迁移；
回滚应用源码不会删除账号档案或语音缓存，但重新打包旧 edge-tts 会重新引入协议不兼容。

## 八、最终交付补记

- Windows 全量最终通过：四分片 **1707 + 1889 + 1906 + 1975**，另有独立生命周期族
  **68**，合计 **7545 passed / 17 skipped**。原始输出：`logs/pytest-full-final.log`、
  `logs/pytest-isolated-final.log`。前一轮失败记录保留，未掩盖或删断言。
- 满载三遍均 **182 passed**；最终文档/关于页/版本门禁聚焦 **167 passed**；ruff、
  `git diff --check`、bash 语法检查通过。
- 最终构建 `logs/build-final.log`：包内 edge-tts **7.3.1**，所需 **25** 模块全部在
  **1995** 个冻结模块中；原生 DLL 链通过。EXE 1.8 秒、独立设置页 1.0 秒出现。
- 真正操作冻结包的“立即试听”（Windows UI Automation，仅连接本次启动的 PID）：
  生成 **32256 bytes** MP3；该进程 Windows Core Audio 会话由 Active 到 Inactive，
  检测到非零输出峰值 **0.5651**；从点击到完整播放结束 **11.844s**。
  原始结果 `frozen-preview-result.json`，脚本 `frozen_preview.py`，不是 mock/播放计数。
- 冻结包另以 `--settings --settings-page 关于` 打开，UI Automation 读回四个准确账号及
  **4.3.1**；`frozen-about-result.json` 指向原生截图，已复核无截断或遮挡。

便携包：`dist-onedir/dsh-pet-4.3.1-webm-chat-portable.zip`，**649390722 bytes**（619.3 MiB）。
SHA-256：`590026c953cca22df5c753d57061b48c44dc7d7f06896702779a2090fca18ad4`。
校验文件：`dist-onedir/dsh-pet-4.3.1-SHA256SUMS.txt`。
ZIP 的 **26675** 个条目完成 CRC 校验，压缩包内元数据亦确认 edge-tts 7.3.1。

构建命令（使用已安装 requirements 的解释器；本次使用 `.venv/Scripts` 在 PATH 首位）：

```powershell
./scripts/build_onedir.ps1 -Variant webm-chat
```

截图、临时用户目录、工具环境、打包产物均留在忽略目录。

## 九、合并 origin/main 后的集成收口（2026-10-16）

提交前分支原先落后 `origin/main` 15 个提交，把 `origin/main`（`0b7152d`）合入后才推 PR。
四处冲突的解法见合并提交 `091ed63`：README 取 main 的新安装章节结构（去掉 details 包裹、
改名「安装、升级与卸载」）并重新放回那三行 Android 说明；`docs/INDEX.md` 以 main 为准
（保住 #280 的 `ASSET-PIPELINE.md` 登记与六条报告）再重新加上本分支三处登记；
`tests/test_architecture.py` 的行数预算按合并后实测校准；`tests/test_settings_page_guide.py`
整份取 main——main 已把「四个区以上才显示跳转条」那条**硬编码域集合**的用例改成按落定几何
测量，本分支当初只是往那个集合里补「关于」，该断言已不存在，属被上游取代而非被删。

### 9.1 设计变更：「关于」独立成域 → 作者账号并进「更新」页

原设计把关于页做成侧栏第 11 个能力域。合并 main 后它撞上两件事：

1. main 的
   `tests/test_settings_sidebar_and_chrome.py::test_default_window_shows_every_domain_without_scrolling`
   要求默认 800×560 下每个能力域都落在侧栏视口里，11 个域实测**视口 378px / 内容 394px，
   溢出 16px**（10 个域时余量 19px）。
2. 想靠缩行高把预算收回来，**被全量套件判红**：`tests/test_desktop_pet_features.py` 断言每个
   导航行的 `sizeHint` **不低于 34px**（可访问性下限），缩行不是选项。

中途试过只收间距与内边距（布局间距 3→1、导航行距 1→0、内边距 (12,16,12,12)→(12,12,12,10)，
余量回到 20px，候选组合对照见 `.scratch/pr-submission/measure_sidebar_variants.py`）。它能过门，
但**评审后改为把作者账号并进「更新」页**：侧栏回到 10 个域，于是侧栏预算改动与随之而来的
顺序断言、行数预算、跳转条口径**全部不需要**，这一版整段退回 main 的样子（见第二节的
「净变更为零」清单）。

最终形态：作者账号是「更新」页底部的一个只读分区——静态账号表在 `pet/settings_about.py`，
`pet/update_settings.py` 把分区挂上页尾。它不注册成偏好、不参与重置；每行有复制按钮，
GitHub 行另有主页按钮（固定 `https://github.com/MerZlin`，不为另三个平台猜链接）。

分区**不在自己身上钉深浅**：`vector_widget_icon` 会把渲染请求记在按钮上，设置窗开窗与切主题时
用**它自己的**主题（`settingsDark`）重画（`refresh_settings_icons`）。若在分区上钉
`modernDark`，跟随系统主题就会盖掉设置窗自己选的那一档——这是本轮踩到的坑，测试改按
「登记请求 + 按宿主主题重画」这条真实路径验证，不再依赖深色调色板这种巧合。

### 9.2 验证状态（如实登记）

- 合并冲突四处全部解决；`origin/main` 侧的能力域顺序、页面引导几何、行数预算断言都保持原样。
- 受影响聚焦族（关于/更新/侧栏/页内引导/桌面特性/菜单布局/架构预算/设置进程隔离/文案 lint）
  本机 **285 passed**，`ruff check .` 通过。
- **本机全量三轮都没跑完整**：第一轮暴露上面那条侧栏预算（已随设计变更消解）；第二轮我在它
  跑动中改了常量，结果新旧混合、**作废**；第三轮 shard 1 撞上 Windows 已知的
  `access violation`（`scripts/ci_shards.py` 就是为躲它而存在；那段时间本机还有别的项目的
  CPU 密集进程在跑）。跑完的分片里没有与本次改动相关的红。**最终全量以 CI 三端为准。**

本报告的提交编号：桌面修复 `37a6b99`、Android `b1e80b0`、合并 `091ed63`、作者账号并进更新页见
紧随的那个提交。
