# Android 原生悬浮桌宠首版交付报告

基线：`main` / `b55f203` 加本次未提交变更；日期：2026-10-15。
用途：本地直接安装的 0.1.0 测试 APK，非商店正式发布。
安装、构建和接口说明见 [Android 文档](ANDROID.md)；交付格式遵循
[PR 报告模板](PR-REPORT-TEMPLATE.md)。

## 一、核心特性

新增 Kotlin Android 客户端，API 26 起支持单只 shenshen 的透明悬浮、待机、
游走、转向、点击、拖拽抛掷、台词和手机设置。原生前台服务管理运行状态，
通知和应用都能停止；锁屏释放窗口/解码器；撤销权限清理服务。

共用桌面版 11 段核心动画、2651 帧、身体定位框、移动曲线和默认台词。
Python、Qt、ffmpeg 仅用于构建机资源导出，不在 APK 中运行。
资源署名和 Apache-2.0 文本随 APK 分发。

## 二、修改文件说明

统计命令：已跟踪文件使用 `git diff --numstat`；新增文件使用
`git diff --no-index --numstat -- NUL <文件>`。下表均为新增内容，没有删除文件。
现有用户 `.venv/` 保留；SDK、签名、编译产物、JVM 崩溃日志与 APK 不入库。

| 文件 | 增删 | 改了什么与原因 |
|---|---|---|
| `.gitignore` | +10/-0 | 排除 Android 缓存、构建输出、签名和 JVM 崩溃日志，避免提交环境产物。 |
| `README.md` | +4/-0 | 增加手机测试版入口，并区分本地 APK 与正式发布附件。 |
| `THIRD_PARTY_NOTICES.md` | +15/-0 | 登记 Kotlin、AndroidX、Gradle 和派生角色素材的许可归属。 |
| `docs/INDEX.md` | +2/-0 | 登记 Android 指南和本报告，使新文档可发现。 |
| `docs/ONEDIR_PACKAGING.md` | +3/-0 | 链接独立 Android 流程，防止混用 PyInstaller。 |
| `android/settings.gradle.kts` | +16/-0 | 声明 Android 模块和官方依赖仓库。 |
| `android/build.gradle.kts` | +5/-0 | 固定 AGP、Kotlin、Compose 编译插件版本。 |
| `android/gradle.properties` | +6/-0 | 限制并发与 JVM 堆，构建结束退出，Kotlin 共用编译进程。 |
| `android/gradlew` | +252/-0 | 官方 Unix Gradle Wrapper 启动入口。 |
| `android/gradlew.bat` | +94/-0 | 官方 Windows Gradle Wrapper 启动入口。 |
| `android/gradle/wrapper/gradle-wrapper.jar` | 二进制新增 | 官方 Wrapper，经公开 SHA-256 校验后固定。 |
| `android/gradle/wrapper/gradle-wrapper.properties` | +8/-0 | 锁定 Gradle 8.11.1、分发摘要与下载超时。 |
| `android/LICENSE-APACHE-2.0.txt` | +202/-0 | 携带上游 Apache-2.0 许可全文。 |
| `android/NOTICE.txt` | +21/-0 | 声明手机版组件来源与角色署名，随 APK 分发。 |
| `android/app/build.gradle.kts` | +62/-0 | 定义 SDK、应用 ID、版本、Compose、测试与构建前资源导出。 |
| `android/app/src/main/AndroidManifest.xml` | +25/-0 | 注册入口与前台服务，声明悬浮/通知权限，不申请联网权限。 |
| `android/app/src/main/java/io/github/dshpet/mobile/AssetCatalog.kt` | +62/-0 | 读取版本化资源清单，提供几何和动画数据，拒绝非法资源描述。 |
| `android/app/src/main/java/io/github/dshpet/mobile/FrameLoader.kt` | +78/-0 | 单线程有界预取、最新请求合并和关闭后的迟到结果丢弃。 |
| `android/app/src/main/java/io/github/dshpet/mobile/MainActivity.kt` | +168/-0 | 原生设置、授权入口、服务控制、恢复默认及中英/明暗/大字体适配。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetEngine.kt` | +155/-0 | 独立行为与抛掷模型，复用源像素规则和移动曲线。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetOverlayService.kt` | +434/-0 | 唯一悬浮宿主、通知、锁屏/权限/配置生命周期与诊断计数。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetPreferences.kt` | +37/-0 | 应用私有偏好、归一化位置、范围约束和重置。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetRuntime.kt` | +13/-0 | 进程内运行状态和可观测绘制/窗口计数。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetView.kt` | +171/-0 | 原生透明绘制、屏幕坐标触控、移动时采速度和多指取消收口。 |
| `android/app/src/main/res/values/strings.xml` | +26/-0 | 中文产品文案和权限/资源错误反馈。 |
| `android/app/src/main/res/values-en/strings.xml` | +26/-0 | 对应英文界面，供语言与长文本验收。 |
| `android/app/src/main/res/values/styles.xml` | +9/-0 | 应用原生窗口主题与强调色。 |
| `android/app/src/test/java/io/github/dshpet/mobile/PetEngineTest.kt` | +91/-0 | 七项模型回归：动作、边界、速度、暂停、旋转及桌面算法对照。 |
| `android/app/src/androidTest/java/io/github/dshpet/mobile/DeviceAcceptanceTest.kt` | +127/-0 | 真实设备验证素材、偏好、重复启停/通知停止和多指取消。 |
| `android/app/src/androidTest/java/io/github/dshpet/mobile/ReleaseVelocityTest.kt` | +46/-0 | 验证移动窗口的屏幕速度、70ms 松手间隙仍抛掷、静止后松手不抛掷。 |
| `scripts/setup_android.ps1` | +72/-0 | 安装用户目录工具链，验证下载摘要，准备 SDK 与 Wrapper 缓存。 |
| `scripts/build_android.ps1` | +36/-0 | 配置当前构建进程环境，跑门禁、导出 APK 并保存摘要文件。 |
| `scripts/export_android_assets.py` | +137/-0 | 从既有帧序列生成移动清单、资源、图标和许可文件。 |
| `scripts/android_acceptance.py` | +251/-0 | 可复跑的 adb 实际交互、系统窗口检查、截图与性能采样。 |
| `tests/test_android_assets.py` | +68/-0 | 四项导出契约测试：透明度/几何、动作完整性、缺帧与源目录保护。 |
| `docs/ANDROID.md` | +120/-0 | 安装、构建、资源接口、设置契约与设备验收命令。 |
| `docs/PR-REPORT-ANDROID-PET-2026-10-15.md` | +240/-0 | 汇总逐文件、性能和真实执行证据，明确验证边界。 |
| `docs/screenshots/android-pet/settings.png` | 二进制新增 | 中文竖屏设置截图。 |
| `docs/screenshots/android-pet/settings-dark.png` | 二进制新增 | 深色设置截图，检查文字和控件对比。 |
| `docs/screenshots/android-pet/settings-large-font.png` | 二进制新增 | 320dp、200% 字体截图，验证按钮不拆词。 |
| `docs/screenshots/android-pet/settings-landscape.png` | 二进制新增 | 2340×1080 横屏尺寸截图，验证滚动和布局。 |
| `docs/screenshots/android-pet/overlay-clock.png` | 二进制新增 | 在真实系统时钟应用上方显示透明宠物的模拟器截图。 |

## 三、实现要点

- Android 的窗口、触控、权限与前台服务是独立原生实现。行为模型不依赖
  Android API；重力、反弹和摩擦与桌面公共算法保持一致并用样例验证。
- 悬浮窗口只覆盖当前动作的有效范围；身体框保持稳定位置锚点。
  拖拽速度追踪使用屏幕坐标，避免窗口跟着手指移动后局部速度归零。
  按 [Android 速度追踪约定](https://developer.android.com/develop/ui/views/touch-and-input/gestures/movement)
  在 MOVE 时缓存速度；UP 时只消费缓存，超过 150ms 的静止间隙丢弃旧速度。
- 解码采用单线程、最新请求合并、三帧缓存；显示帧/解码中帧另计且有界。
  暂停不推进，锁屏清理窗口与预取，恢复不会补算锁屏期间的时间。
- 长按菜单临时获得焦点以支持可访问性和返回键，关闭后恢复原窗口交互。
  大字体下启动/停止操作纵向排列，避免英文单词被拆进窄按钮。
- Android 系统设置页会以 `mForceHideNonSystemOverlayWindow=true` 隐藏
  第三方悬浮窗；这是系统行为，保留诊断和截图，不绕过。

## 四、性能分析

环境：Windows 11，Ryzen 7 H 255，约 16 GB RAM；Microsoft JDK 17.0.20.1，
Gradle 8.11.1，AGP 8.10.1，Kotlin 2.1.21；Android Emulator 使用 WHPX 和
SwiftShader。所有模拟器数字均不得外推为真实手机的 CPU、耗电或温度。

资源导出真实输出（11 个既有帧序列，1 次）：

```text
.venv/Scripts/python.exe scripts/export_android_assets.py --output android/app/build/generated/petAssets --res-output android/app/build/generated/petRes
{"clips": 11, "frames": 2651, "bytes": 37726440, "seconds": 13.772}
```

`bytes` 含随输出的 `NOTICE.txt` 与 Apache-2.0 全文（合计 12,319 字节），素材
本体为 37,714,121 字节（脚本先拷许可文本、后统计，故引用值改为可复现的
37,726,440；本机复跑同一命令为 16.084 秒，`seconds` 随构建机负载浮动）。
最终 APK 为 55,103,154 字节（约 52.55 MiB）；手机端没有视频转码或外部
解码进程。

稳态路径新增 Android 主线程绘制/窗口更新、一条有界帧解码线程，以及 APK
内帧读取；没有网络、定时唤醒锁或手机侧子进程。偏好只在用户修改、拖拽结束、
旋转及停止时写入。

### Android 8.0 模拟器采样

命令（已实际执行，目标 30 分钟）：

```powershell
.venv/Scripts/python.exe scripts/android_acceptance.py --adb "$env:LOCALAPPDATA/dsh-pet-android/sdk/platform-tools/adb.exe" --serial emulator-5556 --output .scratch/android-pet/api26-verified --minutes 30
```

环境为 API 26 / x86_64、1080×1920 / 420dpi、2 个虚拟 CPU、1536 MB 客体内存。
采样与本机桌面分片测试共享主机。会话中断后采样和模拟器进程已退出，文件只保留
**12 个样本，首末相距 355.407 秒**；因此本报告不记作 30 分钟验收通过。

| 观测项 | 实测值 | 口径 |
|---|---|---|
| 进程/窗口 | 12/12 样本为同一 PID、运行中、1 个宠物窗口 | 服务诊断；另有停止/锁屏时的系统窗口核验 |
| PSS 内存 | 首样本 56,066 KiB，末样本 61,361 KiB | `dumpsys meminfo`，包括共享页摊销 |
| PSS 范围/中位数 | 56,066–62,128 KiB / 60,746 KiB | 12 个样本 |
| PSS 增长 | +5,295 KiB，约 +5.17 MiB | 本窗口内确有增长；短采样不能排除长期泄漏 |
| `top` 进程 CPU | 19.2%–36.0%，中位数 27.45% | 单虚拟核口径；该模拟器总量为 200%，不是手机 CPU 结论 |
| 绘制交付 | 62 → 7,333，平均 20.458 次/秒 | 宠物 View 的实际 `onDraw` 计数，不是游戏 FPS |
| 帧解码 | 平均 23.849 帧/秒 | 解码器实际计数的首末差值 |
| 暂停/锁屏 | 两次独立 2 秒观察窗，绘制/解码增量均为 0 | 交互验收记录；锁屏同时核对系统悬浮窗为空 |

成本与触发频率：冷启动每次打开应用发生一次，API 26 三次 `am start -W`
为 2263 / 2042 / 2114 ms；服务首次出帧延迟未单独打点。动画稳态按上表频率
读 APK 帧资源和绘制；位置/尺寸变化时更新窗口，台词按 20–60 秒间隔出现，
偏好写入由用户设置或位置保存触发。没有联网权限或应用唤醒锁。

新增线程的实现为一条解码 worker，Android 运行时及 UI 框架线程另计。
本轮旧版 `ps -T -p` 输出只列出主进程，**不能作为实际线程数或线程增长证据**。
同样未采集系统调用总数；上述磁盘/线程触发点来自源码检查，而 CPU、PSS、
绘制和解码数据来自运行采样。模拟器电池字段不用于耗电/温度结论。

## 五、实机运行记录

### 构建和设备边界

本机真实执行构建、安装与 adb 测试；设备为 Android 模拟器，不是真实手机。
`adb devices -l` 起初为空，之后分别只出现 `emulator-5554`（API 35）或
`emulator-5556`（API 26）。
因此没有可用手机来测量真实耗电、温度、厂商后台策略或完成真机 30 分钟验收。

已执行的行为证据（API 35 / Android 15）：

```text
Kotlin unit tests: 7 passed
Android instrumentation: 5 passed
permission_denied: permission action visible; service absent
fling: mode=THROWN
paused_observation_2s: windows=1 draws=680 decoded=924
screen_off_observation_2s: windows=0 draws=680 decoded=924
explicit_stop: service and application overlay windows absent
permission_revoked: service removed
result: PASS
```

最终触控修正后的该轮冷启动 `am start -W` 的 TotalTime 为
6284 / 6267 / 5862 ms（n=3），属于当时共享主机负载下的调试包模拟器结果。
长按菜单、暂停、锁屏/解锁、授权撤销与恢复均通过真实 Android 输入/系统调用
验证。截图已检查：[中文竖屏](screenshots/android-pet/settings.png)、
[深色](screenshots/android-pet/settings-dark.png)、
[大字体](screenshots/android-pet/settings-large-font.png)、
[横屏尺寸](screenshots/android-pet/settings-landscape.png)、
[跨应用悬浮](screenshots/android-pet/overlay-clock.png)。

### 最低版本与最终安装包

API 26 / Android 8.0 的原生设备测试为 **5 passed**。最终包安装后完整交互脚本
也通过：授权拒绝/恢复、跨应用、抛掷、长按菜单、暂停、锁屏/解锁、停止后系统
窗口归零、权限撤销。此轮暂停和锁屏观察的计数均保持 `draws=579 decoded=686`。

| 验证平台 | 包摘要前缀 | 结果 |
|---|---|---|
| Android 15 / API 35 模拟器 | `BD028B7E8AAC`（干净构建前候选） | 7 项模型、5 项设备测试及完整交互脚本通过 |
| Android 8.0 / API 26 模拟器 | `B7979D164D55`（最终干净构建） | 7 项模型、5 项设备测试及完整交互脚本通过 |

最终构建命令：`./scripts/build_android.ps1 -Tasks @('clean','testDebugUnitTest','lintDebug','assembleDebug')`。
实际输出：`BUILD SUCCESSFUL in 2m 56s`，`53 actionable tasks: 53 executed`。
Android lint 为 0 errors；保留固定依赖版本及旧 API/风格建议等 warnings。

```text
APK: dist-android/dsh-pet-android-0.1.0-debug.apk
SHA-256: b7979d164d557b68b1478716fdf06abc7e018e6f4adef1d13498d20b8319fd83
Package: io.github.dshpet.mobile
Version: 0.1.0 (1)
minSdk: 26; targetSdk: 36
ABIs: arm64-v8a, armeabi-v7a, x86, x86_64
apksigner verify --verbose --print-certs: Verifies; v2=true
zipalign -c -P 16 4: exit 0
```

APK 内核对 11 段 / 2651 帧齐全、许可文本存在、Python 文件数为 0；其原生库
只有各 ABI 的 `libandroidx.graphics.path.so`。`aapt dump permissions` 核对没有
INTERNET 权限。固定测试证书 SHA-256：
`6bff57ec335564392e4acce881b0fdb6cdd198ed2022148a3e0d268dac3db379`。

两条触控回归有明确红绿证据：多指取消后错误点击（expected 0 / actual 1）与
70ms 松手间隙失去抛掷（expected THROWN / actual IDLE）；修正后两代设备测试通过。

过程中主机曾报告分页文件不可用、提交内存不足：模拟器所需 1536 MB 高于
剩余 1022 MB，JVM 报 Windows error 1455。之后可提交内存恢复，干净构建与
API 26 验收才得以完成。这些失败属于开发环境记录，不计入成功测试。

### 桌面回归

首轮全量命令：`QT_QPA_PLATFORM=offscreen python -m pytest -q`。
实际结果：7500 passed、17 skipped、1 failed，1316.53 秒。
唯一失败为未改动的 `test_decode_fanout_integration.py::test_two_clips_share_single_decode`：
日志显示订阅者等待 1900 ms 后触发看门狗，回退本地解码，违反该测试的
“订阅者不拉起 ffmpeg”断言。当时 Android 编译和模拟器也在运行。
停止重负载后该原样测试单独复跑通过（1 passed / 4.59s）。
随后按仓库 Windows CI 流程执行 `python scripts/ci_shards.py`，再独立执行
被该脚本排除的三个 webm 生命周期文件和低优先级预热文件：

| 测试批次 | 实际结果 |
|---|---|
| 分片 1 | 1683 passed、9 skipped、1 failed；386.91s |
| 分片 2 | 1889 passed、3 skipped；266.94s |
| 分片 3 | 1914 passed、3 skipped；290.49s |
| 分片 4 | 1948 passed、2 skipped；515.60s |
| webm 生命周期 | 41 passed；30.58s |
| 低优先级预热 | 27 passed；36.11s |

此轮覆盖合计 **7502 passed、17 skipped、1 failed**。唯一失败变为原有的
`test_flight_frame_pacing.py::test_flight_speed_writes_do_not_starve_frame_delivery`：
交付 40 帧，测试要求至少 `44.297 - 3` 帧。该文件原样单独复跑为 **5 passed / 8.34s**。
因此两个时序失败均单独复验通过，但**没有一次全量零失败的记录**，不宣称合并门禁全绿。
本次没有修改桌面 `pet/` 产品代码。

最终静态检查 `ruff check pet/ tests/ scripts/export_android_assets.py scripts/android_acceptance.py`
与 `git diff --check` 通过；资源与报告门禁 focused tests 为 151 passed。

## 六、未完成验收

- 真机未连接：真实耗电、温度、厂商后台清理和真实手机 30 分钟运行尚未验证。
- 模拟器长时采样被会话中断，仅有 355.407 秒，不能替代目标 30 分钟。
- 桌面两次全量覆盖各出现一个时序失败，虽单独复验通过，仍保留全量未全绿的结论。
