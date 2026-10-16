# Android 桌宠第二阶段交付报告：插件化内核、点击闪烁修复、台词/音效/小鲸鱼

> 2026-10-16 补充：**当前交付为 0.2.1，最新结果见第九节**。前八节保留
> 0.2.0 草稿的历史记录，其中“尚无模拟器验证”等结论不代表本次交付状态。

基线：`feat/android-overlay-pet` 的 `15e0b7b`（0.1.0 首版）加本次未提交变更；
日期：2026-10-15。用途：本地直接安装的 0.2.0 测试 APK，非商店正式发布。
安装、构建、资源与设置契约见 [Android 文档](ANDROID.md)；首版授权、构建与
历史性能数字见 [首版报告](PR-REPORT-ANDROID-PET-2026-10-15.md)；交付格式遵循
[PR 报告模板](PR-REPORT-TEMPLATE.md)。

## 一、核心特性

1. **可选能力全部插件化**：新增模块内核（`modules/`），四个能力各自一个模块，
   `wander` / `speech` / `clickSound` / `companion`。设置页上的开关就是模块的
   启用位；**关闭的模块不会被创建**——不建窗口、不起线程、不占解码缓存、
   收不到逐帧回调，`dumpsys` 的 `modules=` 是当前真实存在的模块集合。
2. **修掉点击「闪烁 + 卡顿」**：定位到五个根因并逐个修复（详见第三节）——
   未解码帧不再与下一个动画的裁剪框混用、窗口不再随动画改尺寸、解码从三帧
   缓存改成字节预算 + 当前帧优先的预读、位图复用停止每帧 0.9 MB 分配、
   气泡窗口不再在每次点击时增删。
3. **台词可自定义**：设置页新增台词池（每行一条，留空回退内置 5 条，清洗规则
   与桌面 `_clean_self_talk_texts` 一致），并可调说话间隔（最短/最长，默认
   20–60 秒）与气泡停留（默认 3.2 秒）。
4. **点击音效（默认关）**：内置桌面默认包（MIT 的鸭叫按下/松开双声）经导出
   脚本进 `res/raw`；也可以选手机上的音频文件（持久读取权限，不新增权限）。
5. **生小鲸鱼**：长按菜单可生/退小鲸鱼，母宠 + 最多 4 只，每只独立窗口、
   独立位置与游走，出生 75% 大小，共用同一个解码器与缓存。
6. 版本 0.2.0（versionCode 2），素材导出增加点击音拷贝。
7. **点击 Q 弹**：把桌面的 220 ms 挤压脉冲（`pulse=sin(π·progress)`，宽 +10%、高 −15%，底中锚定）原样搬到手机端；点击和真实碰撞都会触发，宠物原地压扁回弹、不跳位。
8. **桌宠碰撞（可开关）**：按 `pet/collision.py` 移植——身体框内切三圆链碰撞体、深重叠优先、逆质量分离（质量按体积比、0.5–2.5 夹取）与法向/切向冲量（弹力、摩擦、冲量上限沿用桌面常量），并带一个扫掠检测，避免高速抛掷时两帧之间穿过去。拖动中的桌宠视为不可推动，所以手指永远赢。设置页可开关并调「撞后弹力」。
9. **点击音效真的能听见**：原先用 `USAGE_ASSISTANCE_SONIFICATION`，在 Android 上走**系统音量**流，系统音量一低/静音就完全听不见；现在改用媒体流（`USAGE_GAME` + `AUDIO_SESSION_ID_GENERATE`），并给内置音加了一份常驻的 `MediaPlayer` 备用播放器——`SoundPool` 还没加载完（或加载失败）时由它出声，所以第一次点击就有声音。打开开关时还会立刻响一声试听，用来当场确认音源可用。

## 二、修改文件说明

统计命令：已跟踪文件用 `git diff --numstat`；新增文件用 `wc -l`。
`android/**/build/`、`dist-android/`、签名与 JVM 崩溃日志仍按 `.gitignore` 不入库；
既有用户 `.venv/` 保留。

### 修改的既有文件

| 文件 | 增删 | 改了什么与原因 |
|---|---|---|
| `android/app/src/main/java/io/github/dshpet/mobile/PetOverlayService.kt` | +509/-165 | 从单宠改成多宠宿主：`petMap` 持有母宠与 0..4 号小鲸鱼的身份与引擎，`Surface` 持有各自的窗口/视图/气泡/解码游标；实现 `ModuleHost` 与 `PetView.Listener`，接上模块注册表、生/退小鲸鱼、气泡复用、窗口事务与解码计数；新增 `SPAWN`/`EXIT` 命令与 `publishState()`。 |
| `android/app/src/main/java/io/github/dshpet/mobile/FrameLoader.kt` | +260/-48 | 解码器重写：字节预算 LRU、每宠一个游标、最近帧优先的预读计划、位图复用池（带「可能仍在屏幕上」的保护，绝不 `recycle()`）、预热队列、命中/未命中/复用计数；关闭后迟到结果丢弃。 |
| `android/app/src/main/java/io/github/dshpet/mobile/MainActivity.kt` | +107/-45 | 设置页拆成各模块自己的区块并新增音源选择器（`OpenDocument` + 持久读取权限）与文件名解析；模块开关就是功能开关；恢复默认同时收回小鲸鱼。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetView.kt` | +65/-29 | 显示状态收敛成不可分三元组（`DisplayState`），未解码帧不再换裁剪框；改为按并集窗口内的偏移绘制，镜像绕内容中心；新增按压回调（音效在按下时发声）。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetPreferences.kt` | +124/-10 | 新增台词池、说话间隔/时长、点击音效开关/音量/音源、小鲸鱼开关与小鲸鱼位置；`PetOptions` 增加 `enables(moduleId)` 与归一化（最短 ≤ 最长、范围与非法值回退）。 |
| `android/app/src/main/java/io/github/dshpet/mobile/AssetCatalog.kt` | +8/-1 | 目录新增 `unionCrop`（全部动画裁剪框的并集，由纯函数求出，清单 schema 不变）与 `clipsIn(group)`、`framePath(index)`。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetEngine.kt` | +12/-0 | 新增 `stopWandering()`（关掉游走模块时从移动/转向收回待机）与 `placeAt()`（小鲸鱼出生定位）。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetRuntime.kt` | +13/-1 | 可观测计数扩展：`windowOps`（窗口几何事务）、`bubbles`、`staleFrames`、`lastPhrase`、`audioPlays`；`RuntimeState` 增加小鲸鱼数量与当前模块集合。 |
| `android/app/src/main/res/values/strings.xml` | +24/-2 | 新增模块与设置文案（小鲸鱼、台词池、间隔、音效、音源），版本行改 0.2.0。 |
| `android/app/src/main/res/values-en/strings.xml` | +24/-2 | 对应英文文案与版本行。 |
| `android/app/src/androidTest/java/io/github/dshpet/mobile/DeviceAcceptanceTest.kt` | +43/-32 | 适配新的 `PetView` 构造与共享等待工具；偏好往返覆盖新增设置；新增「并集覆盖每段裁剪框」断言。 |
| `android/app/src/androidTest/java/io/github/dshpet/mobile/ReleaseVelocityTest.kt` | +1/-1 | 适配新的 `PetView` 构造。 |
| `scripts/export_android_assets.py` | +16/-0 | `copy_click_sounds()`：把桌面默认点击音（MIT 的 `Ya1.mp3`/`Ya2.mp3`）拷成 `res/raw/click_press.mp3` 与 `click_release.mp3`，缺文件即构建失败；保持「素材单源，手机不另存手工副本」。 |
| `tests/test_android_assets.py` | +23/-1 | 新增两项导出契约：音效落到 `res/raw` 且字节一致、缺音源必须失败。 |
| `android/app/build.gradle.kts` | +3/-2 | 版本 0.2.0/2；导出任务的输入补上 `assets/sounds/duck`（否则改音效不会触发重新导出）。 |
| `scripts/build_android.ps1` | +1/-1 | 产物名 `dsh-pet-android-0.2.0-debug.apk`。 |
| `android/NOTICE.txt` | +7/-0 | 登记 APK 内新增的内置点击音（MIT，MeteorNOX/DeepSeek-Balance-Whale-Widget）。 |
| `docs/ANDROID.md` | +77/-23 | 使用说明、模块表与「关掉就不占性能」的口径、窗口与解码契约（并集窗口、字节预算缓存、不可分显示状态）、设置准入表新增 8 行、验收命令新增帧耗时与模块采样。 |
| `scripts/android_acceptance.py` | +613/-52 | 验收脚本升级：`dumpsys` 改成读全量 `key=value`（新键缺失时不报错，旧包也能跑）；窗口数断言改为「`windows == pets`」；新增 6 项脚本化检查（模块默认集合、用户台词进气泡、生/退小鲸鱼、点击音效、空闲期窗口事务、解码健康度）；新增 `--frames LABEL` 帧耗时探针（重置-交互-读取 `dumpsys gfxinfo`，落 `gfxinfo-<label>.txt` + 解析后的分位数，旧包同样能跑）与 `--module-sweep SECONDS` 逐模块关闭采样。 |
| `tests/test_android_acceptance.py` | +154/-0 | 新增 9 项无设备单测：当前与 0.1.0 两代 dump 的解析、`ServiceRecord` 噪声下的取值顺序、模块集合解析、计数与增量、`gfxinfo` 解析（缺字段给 None）、PSS/CPU 两代 `dumpsys` 格式、采样汇总。 |

### 新增文件

| 文件 | 行数 | 作用 |
|---|---|---|
| `modules/PetModule.kt` | 107 | 模块 SPI：`PetModule`/`HostBoundModule`/`ModuleHost`/`ModuleMenu`/`PetEvent`/`ModuleFactory`。 |
| `modules/ModuleRegistry.kt` | 78 | 按启用位构造/释放模块，只向启用模块扇出逐帧、事件与菜单；提供 `activeIds()` 诊断。 |
| `modules/WanderModule.kt` | 24 | 自由游走模块：停用时把每只宠物收回待机。 |
| `modules/SpeechModule.kt` | 52 | 气泡与说话节奏模块：间隔随机、点击即说、停用时清理气泡并忘记节奏。 |
| `modules/ClickSoundModule.kt` | 134 | 点击音效模块：内置音走 `SoundPool`，自选文件走预热好的 `MediaPlayer`，80 ms 节流，停用时释放播放器。 |
| `modules/CompanionModule.kt` | 32 | 小鲸鱼策略模块：数量上限、菜单项、停用时收回全部小鲸鱼。 |
| `DisplayState.kt` | 32 | 「位图 + 裁剪框 + 镜像 + 版本号」不可分显示状态（点击闪烁的修复点）。 |
| `WindowGeometry.kt` | 46 | 并集窗口的位置、尺寸与内容偏移（纯函数）。 |
| `FrameBudget.kt` | 77 | 字节预算 LRU + 最近帧优先的预读计划 `LookaheadPlanner`（纯函数）。 |
| `PhraseBook.kt` | 32 | 台词清洗、回退与随机取用（对齐桌面规则）。 |
| `CompanionCodec.kt` | 37 | 小鲸鱼位置的单键存储编解码与上限/出生参数。 |
| `PetHandle.kt` / `ModuleIds.kt` | 10 / 15 | 宠物身份（纯数据）与模块 id 表。 |
| `ui/AppearanceSection.kt` 等 6 个 | 21+56+20+59+76+11 | 设置页按模块拆分的区块与共用控件。 |
| `src/test/.../` 9 个新测试类 + `modules/FakeHost.kt` | 40+57+59+42+69+40+68+62+137+91 | JVM 单测：显示状态、窗口几何回归、缓存预算与预读顺序、台词规则、小鲸鱼编解码、偏好归一化、模块生命周期与说话模块。 |
| `src/androidTest/.../DeviceModulesTest.kt` | 119 | 真机测试：模块启用集合、停用零气泡、小鲸鱼窗口与恢复、空闲期窗口事务为零、帧交付与解码健康度。 |
| `src/androidTest/.../TestSupport.kt` | 71 | 共享等待工具与手势记录监听器。 |

### 第二轮增量（同一天，用户真机实测反馈后）

用户实测反馈三点（点击没有 Q 弹、点击音效听不见、想要可开关的桌宠碰撞），
本轮新增/改动如下。表中数字是第二轮结束时的累计 `git diff --numstat`
（含第一轮），新增文件用 `wc -l`。

| 文件 | 增删 | 改了什么与原因 |
|---|---|---|
| `android/app/src/main/java/io/github/dshpet/mobile/Collision.kt` | 新增 266 行 | 纯函数碰撞求解：三圆链碰撞体、AABB 粗筛 + 最深圆对、每对每 tick 一次冲量、逆质量分离（深重叠优先、最多 4 轮重算）、法向/切向冲量与扫掠检测；常量对齐 `pet/collision.py`。 |
| `android/app/src/main/java/io/github/dshpet/mobile/Squash.kt` | 新增 29 行 | 纯函数 Q 弹几何：220 ms、`sin(π·progress)`、宽 +10%/高 −15%、底中锚定，常量对齐 `pet/pet_sprite.py` 与 `pet/window.py`。 |
| `android/app/src/main/java/io/github/dshpet/mobile/modules/CollisionModule.kt` | 新增 62 行 | 碰撞模块：把每只宠物换算到同一空间（母宠源像素）求解，真实命中转成抛掷并触发 Q 弹，拖动中的宠物不可推动；关掉即不构造。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetView.kt` | 累计 +92/−29 | 增加 Q 弹：`squash()`/`advanceSquash(dt)` 与绘制时的目标矩形缩放；点击（含小鲸鱼）都会触发。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetEngine.kt` | 累计 +30/−0 | 新增 `shift()`（纯位移分离）与 `nudge()`（位移 + 冲量 + 进入抛掷），碰撞模块用它改写位置与速度。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetOverlayService.kt` | 累计 +529/−165 | 注册碰撞模块；`doFrame` 每帧调一次 `onTick`（碰撞在推进前结算，与桌面同序）并推进 Q 弹；`ModuleHost` 增加 `bodyBox`/`scaleRatio`/`squash`；`dump()` 增加 `ticks=`/`moduleInfo=`。 |
| `android/app/src/main/java/io/github/dshpet/mobile/PetPreferences.kt` | 累计 +139/−10 | 新增 `collision`（默认开）与 `collisionRestitution`（默认 0.82，0–1）及其归一化、存储与监听键。 |
| `android/app/src/main/java/io/github/dshpet/mobile/modules/ClickSoundModule.kt` | 新增 134 → 改 | 音效改走媒体流（`USAGE_GAME`），内置音常驻一份备用 `MediaPlayer`（`SoundPool` 未加载完/加载失败也能出声），打开开关时立刻响一声试听，`diagnostics()` 报出实际发声路径。 |
| `android/app/src/main/java/io/github/dshpet/mobile/modules/PetModule.kt` | 新增 107 → 改 | SPI 增加 `onTick(dt)`（整窝一次性回调，碰撞用）；`ModuleHost` 增加 `bodyBox`/`scaleRatio`/`squash`。 |
| `android/app/src/main/java/io/github/dshpet/mobile/modules/ModuleRegistry.kt` | 新增 78 → 改 | 转发 `onTick` 并计数 `ticksDispatched`。 |
| `android/app/src/main/java/io/github/dshpet/mobile/ModuleIds.kt` | 新增 15 → 改 | 增加 `collision` 模块 id。 |
| `android/app/src/main/java/io/github/dshpet/mobile/MainActivity.kt` | 累计 +109/−45 | 接入「桌宠碰撞」区块（开关 + 撞后弹力）。 |
| `android/app/src/main/res/values/strings.xml` / `values-en/strings.xml` | 累计 +27/−2 各 | 新增碰撞与试听提示文案。 |
| `android/app/src/test/java/.../SquashTest.kt` | 新增 51 行 | Q 弹几何：0/1 处恒等、峰值宽度/高度、底中锚定、越界钳制、时长等于 220 ms。 |
| `android/app/src/test/java/.../CollisionTest.kt` | 新增 135 行 | 碰撞数学：圆链位置、重叠分离、轻的被推更远、快撞产生真实命中、已分离不给冲量、**两帧之间穿过也能被扫掠抓到**、拖动不可推动、质量夹取、重合中心的确定性。 |
| `android/app/src/test/java/.../modules/CollisionModuleTest.kt` | 新增 114 行 | 模块接线：重叠挤开（并断言不误报命中、不放 Q 弹）、轻的走更远、真实命中把对方抛起并双方 Q 弹、单宠无事、**关掉即不构造且宠物一动不动**、长期多次结算不越界。 |
| `docs/ANDROID.md` | 累计 +88/−23 | 模块表与设置准入表加碰撞两行、使用说明提 Q 弹与试听、音效发声路径说明。 |


## 三、实现要点

### 3.1 点击「闪烁 + 卡顿」的五个根因与修法

0.1.0 的显示状态是「位图」和「裁剪框」两个独立字段（`PetView.present()`），
而解码器在帧没到货时返回 null。于是每次切动画（点击、拖拽、起步）的前 1–2 帧，
**新动画的裁剪框被套在上一段动画的位图上**——idle 的 252×274 与点击最宽的
412×270 相差 63% 宽度，画面必然错位拉伸。这是「闪」的第一来源。

| # | 根因（0.1.0 代码位置） | 修法（0.2.0） |
|---|---|---|
| F1 | `PetView.present()` 无条件改 `crop`，未解码时仍用旧位图；`FrameLoader.request()` 返回 null 表示「还没解码」 | 显示状态收敛成不可分三元组 `DisplayState`（位图 + 裁剪框 + 镜像 + 版本号）：帧没到就整体不换，绝不混用 |
| F2 | 窗口尺寸来自「当前动画的裁剪框」，每次切动画改尺寸；移动时每帧改位置 | 窗口固定为**全部动画裁剪框的并集**（`WindowGeometry.union`，设备上由各段 `crop_box` 求出，导出清单 schema 不变），创建后不再 resize；单帧只改窗口内部的绘制偏移。身体锚点语义不变，逐动画的屏幕位置与旧公式一致（`WindowGeometryTest` 用真值对照旧公式，容差 ≤1.5 px） |
| F3 | 解码器只缓存 3 帧、只预取 1 帧，而每帧都唯一 ⇒ 实测 decoded/s ≈ fps，零余量，任何抖动直接掉帧 | `FrameLoader` 重写：字节预算缓存（默认 24 MB ≈ 26 帧）、每只宠物一个游标、按「所有宠物的当前帧 → 所有宠物的 +1 → …」排解码顺序（`LookaheadPlanner`）、空闲时预热点击/拖拽动画首 2 帧 |
| F4 | 每帧把 640×360 ARGB 缩放到窗口，并每秒新分配约 24 个 0.9 MB 位图 | 位图复用池（`BitmapFactory.inBitmap`）；可能仍在屏幕上的位图不会被当作复用目标，且全程不调用 `recycle()`，只丢引用，避免视图拿着已回收位图 |
| F5 | 每次点击 `removeViewImmediate` + `addView` 一个新建的气泡窗口 | 气泡窗口每只宠物只创建一次，之后只改文本 + `updateViewLayout` + 显隐切换，零窗口增删 |

另外把 tick 间隔从固定 30 Hz 改成按当前动画帧率取整（24 fps 素材即 24 Hz），
移动/抛掷时提到 60 Hz：既省掉 6 次/秒的空转，又让位移更跟手。

### 3.2 插件化内核

`PetModule` 是唯一的能力接口（`enable/disable/onFrame/onEvent/menuItems/
onOptionsChanged/diagnostics`），`HostBoundModule` 收掉启用/停用的簿记。
`ModuleRegistry` 只在启用时构造模块、只向启用模块扇出事件，停用时调用
`disable()` 并丢弃实例。设置页上的四个开关（游走、台词气泡、点击音效、小鲸鱼）
**就是**模块的启用位，不另开一层「模块管理」页（归属唯一）。
`publishState()` 把当前模块集合放进 `RuntimeState`，于是「关掉就是真的没建」
可以被真机测试直接断言，而不是靠代码阅读。

### 3.3 台词与节奏

`PhraseBook` 对齐桌面 `config.py::_clean_self_talk_texts`：trim、丢空行、
每条截 120 字、去重、保序、**留空回退内置 5 条**（内置来自导出清单的
`phrases`，即桌面 `DEFAULT_SELF_TALK_TEXTS`）。间隔与气泡时长带范围与
归一化（最短 ≤ 最长，非法值回退默认），在 `PetOptions.normalized()` 里统一收口。

### 3.4 音效

内置音是桌面默认包（MIT 的 `Ya1.mp3`/`Ya2.mp3`，共 9.3 KB），由
`export_android_assets.py::copy_click_sounds()` 拷进 `res/raw`，缺文件即构建失败——
保持「素材单源，手机不另存手工副本」。默认关闭；按下（ACTION_DOWN）放按下声、
确认是点击（UP 且未移动）时放松开声，80 ms 节流，拖动/抛掷不会误触。
用户自选文件走持久化 URI + 预热好的 `MediaPlayer`（非内置音只响一次），
因为 content URI 的描述符不能安全地交给 `SoundPool`。

### 3.5 小鲸鱼

`CompanionModule` 持策略（上限 4、出生 75%、出生点在母宠身体右侧 + 24×序号），
服务持窗口。每只小鲸鱼是独立 `PetEngine` + 独立悬浮窗 + 独立归一化位置，
共用同一个解码器与缓存（键含动画 id，同角色帧天然共享）。位置随
出生/退出/拖拽结束/旋转/停止落盘，重启恢复；停用模块或恢复默认会全部收回。
不做宠物间碰撞，小鲸鱼也不说台词。

### 3.6 用户实测反馈后的三项（同一天的第二轮）

1. **点击 Q 弹**：`Squash` 是纯函数，常量逐字对齐桌面
   （`pet/pet_sprite.py::_squashed_rect` 与 `window.py::_squash_geometry`：
   220 ms、`pulse=sin(π·progress)`、`sx=1+0.10·pulse`、`sy=1−0.15·pulse`、
   水平居中 + 底部对齐）。进度由逐帧回调推进（`PetView.advanceSquash`），
   绘制时只改目标矩形，位图与裁剪框不变；点击（`performClick`）与碰撞真实命中
   都会触发，所以「戳一下会 Q 弹」和桌面一致。
2. **桌宠碰撞**：`Collision` 是纯函数，按 `pet/collision.py` 移植——
   `circles_from_rect` 三圆链（半径 = 短边一半）、AABB 粗筛 + 最深圆对、
   每对每 tick 只算一次冲量、逆质量分离（60% 有效重叠、slop 0.5、1–12 px 夹取、
   最深优先重算最多 4 轮）、法向冲量带 `IMPULSE_MIN_APPROACH_SPEED=80` 的
   非弹性门槛与 `impulse_cap=9000`，切向库仑摩擦 0.08；质量按体积比
   `clamp(ratio², 0.5, 2.5)`，所以 75% 的小鲸鱼比母宠轻、被撞得更远。
   额外加了一个**扫掠检测**（相对运动的二次方程求最早接触时刻），因为抛掷速度下
   一帧要跨约 200 源像素，纯离散检测会穿过去。刻意未移植并在文档里写明的：
   桌面的「连续 3 tick 重叠」防抖覆盖、静态世界（岛）与碰撞音效。
   `CollisionModule` 是模块，关掉即不构造、不检测。
3. **点击音效改为媒体流 + 常驻备用播放器**：见第一节第 9 条。诊断字段
   `moduleInfo=` 会打印 `audio=pool-press|media-press|silent-press loaded=N failed=M`，
   于是「到底哪条路在出声」在真机上可读，不用猜。


### 3.7 文档与版本

`docs/ANDROID.md` 重写了使用说明、模块表、窗口/解码契约与设置准入表（新增 8 行），
并把验收命令补上帧耗时探针与模块采样；`docs/INDEX.md` 登记本篇与新版
`ANDROID.md`；`android/NOTICE.txt` 补内置点击音的 MIT 署名。
版本 0.2.0（versionCode 2），`scripts/build_android.ps1` 的产物名与文档同步。


## 四、性能分析

环境：Windows 11，Ryzen 7 H 255，约 16 GB RAM；Microsoft JDK 17.0.20.1，
Gradle 8.11.1，AGP 8.10.1，Kotlin 2.1.21，Android SDK platform-36 +
build-tools 35.0.0。**本节只有构建机数字：本轮全程没有连接手机**
（`adb devices -l` 三次均为空），所以真机 CPU/内存/帧耗时/耗电一律没有，
不在此节冒充。

### 4.1 实测（命令 + 真实输出 + 样本量）

| 项目 | 命令 | 实测 |
|---|---|---|
| 素材导出（含点击音） | `./scripts/build_android.ps1 -Tasks testDebugUnitTest`（Gradle `:app:exportPetAssets`） | `{"clips": 11, "frames": 2651, "bytes": 37726794, "seconds": 22.256}`（1 次） |
| Kotlin 单元测试 | 同上 | **56 passed / 0 failed**（10 个测试类，`android/app/build/test-results/testDebugUnitTest/*.xml` 汇总），`BUILD SUCCESSFUL in 1m 47s` |
| Android lint | `-Tasks lintDebug` | `0 errors, 15 warnings, 6 hints`；`BUILD SUCCESSFUL in 1m 22s` |
| APK 构建 | `-Tasks assembleDebug` | `BUILD SUCCESSFUL in 24s`；`dist-android/dsh-pet-android-0.2.0-debug.apk` 55,189,262 字节；SHA-256 `cf1f64deb2b3708671048619794a2262fae29d35b447507c2c8524a56a044c9f` |
| 插桩测试包 | `-Tasks assembleDebugAndroidTest` | `BUILD SUCCESSFUL in 23s`（新增 4 项设备测试只编过，**未在设备上跑**） |
| APK 内核对 | `unzip -l` + `aapt dump badging` | `res/raw/click_press.mp3` 6,370 B、`click_release.mp3` 2,976 B；`assets/pet/manifest.json`；`.py` 文件 0 个；权限无 INTERNET；ABI 四个齐全；versionCode 2 / versionName 0.2.0 |
| Python 门禁 | `pytest -q tests/test_android_assets.py tests/test_pr_report_discipline.py` = **155 passed**；加上新增的 `tests/test_android_acceptance.py` 后 `pytest -q tests/test_android_acceptance.py tests/test_android_assets.py tests/test_pr_report_discipline.py` = **164 passed** | 见第五节 |
| 静态检查 | `ruff check scripts/export_android_assets.py tests/test_android_assets.py scripts/android_acceptance.py tests/test_android_acceptance.py`、`git diff --check` | `All checks passed!`、无空白/冲突错误（仅 CRLF 提示） |

APK 体积增量：0.1.0 的 55,103,154 → 0.2.0 的 55,189,262，**+86,108 字节**
（+84.1 KiB）= 9,346 字节点击音 + 模块/设置页带来的 dex 与资源增长。

### 4.2 稳态开销（设计口径，逐条回答，尚未真机验证）

- **新增路径成本与触发频率**：模块内核只在「启用集合变化」时做事（读偏好 →
  构造/释放），不引入定时器；说话节奏是在既有的逐帧回调里比较一次时间戳。
  点击音在启用时才构造 `SoundPool`（默认关闭），每次按压最多一次 80 ms 节流
  的播放。小鲸鱼每只多一个悬浮窗与一个引擎，上限 4。
- **新增系统调用/网络/磁盘/线程**：没有。解码线程数仍是 1（`DECODE_THREADS=1`），
  没有新增网络权限或后台服务；音效文件在 APK 内，运行时不读盘。
- **帧缓存内存**：0.1.0 是固定 3 帧（约 2.7 MB）；0.2.0 是 24 MB 字节预算
  （640×360 ARGB ≈ 921,600 B/帧 ⇒ 约 26 帧）+ 至多 3 张复用位图（约 2.7 MB）。
  即**驻留帧缓存增加约 21 MB**，这是本次用内存换流畅的明确取舍；
  真机 PSS 必须重测（0.1.0 的模拟器基线是 56,066–62,128 KiB）。
- **窗口事务**：待机时窗口位置与尺寸都不变 ⇒ 理论 0 次 `updateViewLayout`；
  0.1.0 每次切动画都要改一次窗口尺寸（idle 252×274 ↔ 点击 412×270）。
  移动/抛掷时仍按帧更新位置（与 0.1.0 相同）。这条由设备测试
  `theUnionWindowDoesNotMoveWhileThePetIsIdle` 把关，**尚未在设备上跑过**。
- **每帧分配**：0.1.0 每秒新建约 24 个 0.9 MB 位图；0.2.0 复用池命中时不再分配。
  复用率由 `dump()` 的 `reused/decoded` 给出，**尚未在设备上采样**。

### 4.3 第二轮（用户实测反馈后）重建后的最终数字

以下数字**取代**上面 4.1 表里的同名项：第二轮改了代码，产物与用例数都变了。

| 项目 | 实测 |
|---|---|
| Kotlin 单元测试 | **78 passed / 0 failed**（13 个测试类；新增 `SquashTest` 5 项、`CollisionTest` 11 项、`CollisionModuleTest` 6 项），`BUILD SUCCESSFUL in 24s` |
| Android lint | `BUILD SUCCESSFUL in 1m 4s`，0 errors（warning 数与 4.1 同量级） |
| APK | `dist-android/dsh-pet-android-0.2.0-debug.apk` **55,637,749 字节**，SHA-256 `6b1c967ca5eddfd435ad91dc8d93e643e2eb4953f56f0a4fc9301242dbcf29d0`；`BUILD SUCCESSFUL in 17s` |
| 插桩测试包 | `assembleDebugAndroidTest` 重新编译通过；**仍未在任何设备上运行** |
| Python 门禁 | `pytest -q tests/test_android_acceptance.py tests/test_android_assets.py tests/test_pr_report_discipline.py` = **164 passed**；`ruff check` 通过 |

APK 体积：0.1.0 的 55,103,154 → 第二轮 55,637,749，**+534,595 字节（+522 KiB）**。
增量全部是代码与资源（碰撞求解、Q 弹、音效备用播放器、设置页与文案），
素材没有变化。

碰撞的稳态成本（设计口径）：关闭时零成本——模块不构造、不检测、无回调；
开启时每帧 O(宠物对数)（5 只即 10 对，且先过 AABB 粗筛），只有真的重叠或
互相穿过时才写位置与速度；没有新增线程、定时器、系统调用或网络。
Q 弹同理：只在 220 ms 内改绘制矩形，位图与裁剪框不变。

### 4.4 尚缺的实测（必须由真机补）

PSS 与进程 CPU 稳态、`dumpsys gfxinfo` 的帧耗时分布（p50/p90/p95/p99 与
janky 比例）、`stale`/`hits`/`misses`/`reused` 的真实命中率、空闲期
`windowOps` 增量、5 只同屏时的解码是否仍够、以及 30 分钟长跑的耗电与温度。
对应命令见 `docs/ANDROID.md` §设备验收与性能采样与本报告第五节。


## 五、实机运行记录

### 5.1 本轮真实执行过的（本机，非 CI、非 mock）

- 工具链重装（上次的 `%LOCALAPPDATA%/dsh-pet-android` 已不存在）：
  `pwsh -File scripts/setup_android.ps1` → JDK 17.0.20.1 + SDK
  platform-36/build-tools 35.0.0 + platform-tools 就位，`~/.gradle` 里的
  Gradle 8.11.1 分发包与测试签名沿用。
- `testDebugUnitTest` / `lintDebug` / `assembleDebug` / `assembleDebugAndroidTest`
  四条命令真实跑过，输出见第四节表格。
- APK 真实产物：`dist-android/dsh-pet-android-0.2.0-debug.apk`
  （55,189,262 字节，SHA-256 `cf1f64deb2b3708671048619794a2262fae29d35b447507c2c8524a56a044c9f`，
  `SHA256SUMS.txt` 同步）。用 `aapt` 与 `unzip -l` 核对过包名、版本、权限、
  资源与「APK 内 Python 文件数 0」。
- Python 门禁 155 passed（含新增验收脚本单测后合计 164 passed）、ruff 通过、
  `git diff --check` 通过。
- `scripts/android_acceptance.py` 的改造用**伪 adb**（系统临时目录里的假
  `adb.cmd`，不是设备）跑过一次控制流：`--frames baseline` 退出码 0 并写出
  `gfxinfo-baseline.txt` 与解析后的分位数；同一探针对 0.1.0 格式的 dump 也能
  退出码 0（状态字段为 null）；`--measure-only --minutes 0.05` 产出 2 条样本且
  键集合与旧版一致。这只证明解析与控制流可用，**不是设备证据**。

### 5.2 没有执行过的（不得当作通过）

`adb devices -l` 在本轮三次检查中**都是空列表**，机器上没有手机也没有模拟器
镜像。因此：

- 插桩测试（原有 5 项 + 新增 4 项 `DeviceModulesTest`）只**编过**，**没有运行**；
- `scripts/android_acceptance.py` 的授权/跨应用/甩动/长按/锁屏/权限撤销全流程
  **没有运行**；
- `--frames` 帧耗时前后对照与 `--measure-only --minutes 30` 长跑 **没有运行**；
- 于是本报告没有任何真机 CPU、PSS、帧耗时、耗电或温度数字。

用户口径：本轮先交付编译产物，由用户在真机上试用后反馈，反馈通过再提交。
反馈回来时优先补这几项（命令已写进 `docs/ANDROID.md`）：

1. `.venv/Scripts/python.exe scripts/android_acceptance.py --adb "$LOCALAPPDATA/dsh-pet-android/sdk/platform-tools/adb.exe" --serial <真机序列号> --output .scratch/android-pet/acceptance-020`
2. 同上加 `--frames before`（装 0.1.0 包）与 `--frames after`（装 0.2.0 包），
   用同一个脚本做帧耗时前后对照。
3. `./scripts/build_android.ps1 -Tasks connectedDebugAndroidTest` 跑 9 项插桩测试。
4. 可选 `--module-sweep 60` 与 `--measure-only --minutes 30`。

### 5.3 红绿证据的实情

F1–F5 的修复点都写了聚焦测试（`DisplayStateTest`、`WindowGeometryTest`、
`FrameBudgetTest`、`LookaheadPlannerTest`、`DeviceModulesTest`），但这些测试是
**与实现同时写的、当前为绿**：本轮**没有产出「先红后绿」的成对记录**
（0.1.0 的旧规则只作为反例写在 `DisplayStateTest` 的注释里，没有在旧代码上
实跑一次红）。闪烁与卡顿这两项用户可见行为的判定，依赖第二节/第五节列出的
真机测量，而不是靠这些单测。这条差距如实登记，不用测试数量冒充行为验证。

### 5.4 第二轮的失败—修正记录（真实跑出来的红）

第二轮不是一次就绿。新写的碰撞测试在本地先红了三轮，每轮都是真实失败、修完再跑：

| 轮次 | 命令 | 红项 | 原因与修法 |
|---|---|---|---|
| 1 | `-Tasks testDebugUnitTest` | 5 项（`CollisionTest.aThrownPetIsNotMissedBetweenTwoFrames` 与 `CollisionModuleTest` 的 4 项） | 两个真 bug：① 扫掠接触报告的 overlap 是 1.0，但分离循环是「按当前位置重算重叠」，扫掠命中**没有当前重叠**，于是分离从未生效——桌面是把扫掠对的分离单独做一次，我漏了；② 测试里小鲸鱼的位置没换算到缩放后的碰撞空间，方向反了。修法：扫掠对单独分离一次并退出迭代；测试把引擎坐标换算到母宠空间。 |
| 2 | `-Tasks testDebugUnitTest` | 1 项（`CollisionTest.theShapeIsAThreeCircleChainInscribedInTheBodyBox`） | 我在测试里把中间圆的 y 写成 243（正确是 135），实现是对的。修期望值。 |
| 3 | `-Tasks testDebugUnitTest` | 无（78 passed / 0 failed） | — |

这三轮是「本轮新代码 ↔ 本轮新测试」之间的红绿。它证明新代码真的被测试盯住了
（两个 bug 是测试先发现的），但**不能**算作首版行为的回归红绿——没有在 0.1.0 的
实现上跑出过一次红。

## 六、未完成验收

- **没有真机（也没有模拟器）**：插桩测试、验收脚本全流程、帧耗时前后对照、
  30 分钟长跑全部未执行；本轮没有任何真机性能或耗电数字。
- **红→绿成对证据缺失**：见 §5.3，F1–F5 的聚焦测试是绿，但没有一次旧代码上
  的红记录。
- **并集窗口的触摸死区**：窗口触摸矩形从「贴合当前动画」变成「全部动画的并集」
  （默认尺寸下约 512×398 px，身体约 269×335 px）。Android 不允许把已被窗口
  消费的触摸转交下层应用，所以这是**已知取舍**：本轮只测量并写入文档，
  没有绕过，也没有在真机上确认实际手感。
- **桌面全量测试未跑**：本轮不碰 `pet/` 产品代码，只改了 Android 客户端、
  两个构建脚本、一个导出脚本与文档，因此按 `AGENTS.md` 的「聚焦 + 相关测试
  足够」口径只跑了 Android 侧门禁与 Python 聚焦门禁（155 passed）。若要合并，
  再按 `scripts/ci_shards.py` 补一次桌面全量。
- **模拟器数据一概没有**（本轮未安装模拟器镜像），所以也不存在「模拟器数字
  被当成真机结论」的风险。
- **第二轮的三项同样没有真机验证**：没有在手机上确认过「点击音效现在真的响」、
  「点击 Q 弹的手感」、「桌宠碰撞的挤开/弹开手感、会不会抖动」，也没有测过 5 只
  同屏时的碰撞与帧率。音效这一项尤其需要用户确认：上一轮用户报的就是「听不见」，
  本轮改了发声通道并加了试听，但**改完还没在手机上听过**。
- **碰撞常量的单位取舍**：数值逐字沿用桌面，单位是本引擎的源像素空间
  （0.1.0 起重力与速度上限也如此），因此触发速度与桌面相差一个渲染缩放比。
  这是刻意的选择，实际手感只能由真机确认；如果用户觉得「碰得太黏/太弹」，
  调的是设置页的撞后弹力，而不是去改代码里的单位。

## 九、0.2.1 点击反馈与碰撞修复（2026-10-16）

基线是用户实测有问题的未提交 0.2.0 草稿，不是干净 HEAD；全部原有改动保留。
当前安装/构建/默认值契约见 [ANDROID.md](ANDROID.md)，索引见 [INDEX.md](INDEX.md)。
本节证据目录为 `.scratch/android-pet/fix-021/`，以下 `logs/`、脚本、PNG、WAV
均相对于该目录。日期使用 Asia/Shanghai；AVD 屏幕/日志使用其自身时区。

### 9.1 修改文件说明

音效的按下/松开共用限流导致快点只响一次；异步准备丢首次请求、备用播放漏音量、
自选音源只在 prepare 时设置音量。Q 弹依赖服务 tick，暂停时进度永远是零；并集窗口
不足以容纳加宽后的图像。碰撞把已为身体左上角的引擎坐标再次加上身体框偏移，
在 75% 伙伴上产生不同大小的偏差。旧测试使用 `(0,0)` 身体框，掩盖了这个错误。

逐文件增删用 `git diff --no-index --numstat .scratch/android-pet/fix-021/baseline/src android/app/src`
对照开工快照；下表 `main/`、`test/`、`androidTest/` 均位于 `android/app/src/`，
Kotlin 文件的共同包路径为 `java/io/github/dshpet/mobile/`。标“新增”者相对开工草稿新增。

| 文件 | 增删 | 本轮改动与原因 |
|---|---:|---|
| `main/ClickAudio.kt`（新增） | +96/-0 | 共享点击/试听控制器；独立限流、有界待播、过期与音源代次校验、即时音量。 |
| `main/AndroidClickOutput.kt`（新增） | +154/-0 | 封装实际 SoundPool/MediaPlayer；所有路径应用音量，错误、超时和取消均释放资源。 |
| `main/modules/ClickSoundModule.kt` | +12/-172 | 接入共享播放器，移除固定 350ms 试听和重复生命周期逻辑，启停不自动发声。 |
| `main/MainActivity.kt` | +31/-2 | 设置试听及离开页面释放，状态提示；版本读 BuildConfig。 |
| `main/ui/ClickSoundSection.kt` | +19/-8 | 试听按钮、加载/失败状态、失效文件也能恢复内置音；按钮可换行。 |
| `main/PetPreferences.kt` | +2/-2 | 新装/缺键/重置启用音效，保留已保存的 false。 |
| `main/PetRuntime.kt` | +1/-0 | 音频错误状态单独发布，供设置页显示。 |
| `main/PetView.kt` | +29/-6 | 220ms ValueAnimator 独立驱动形变，重复点击重启，detach 取消复原。 |
| `main/Squash.kt` | +1/-1 | 共享最大加宽比例，窗口留白与形变不再各维护一个数值。 |
| `main/WindowGeometry.kt` | +8/-3 | 左右预留最大形变空间；位置与内容偏移反向抵消，身体锚点不动。 |
| `main/modules/CollisionModule.kt` | +4/-3 | 去掉重复身体偏移；诊断键避开解码器 `hits`。 |
| `main/PetOverlayService.kt` | +2/-1 | 去掉服务推进 Q 弹；停止时已保存的伙伴布局不被模块清理覆盖为空。 |
| `main/res/values/strings.xml` | +6/-2 | 中文试听/错误提示与格式化版本文案。 |
| `main/res/values-en/strings.xml` | +6/-2 | 对应英文文案。 |
| `test/ClickAudioTest.kt`（新增） | +121/-0 | 音源未就绪、快点、音量、取消、过期、失败及每类待播上界。只替换 Android 播放边界。 |
| `test/PetOptionsTest.kt` | +3/-2 | 新安装默认音效与音量。 |
| `test/WindowGeometryTest.kt` | +7/-3 | 形变峰值不裁边，原有屏幕锚点不移动。 |
| `test/modules/CollisionModuleTest.kt` | +66/-0 | 真身体框、不同缩放、误碰撞、拖拽、关停及五宠。 |
| `test/modules/FakeHost.kt` | +1/-1 | 身体框改成素材实际的 `[212,60,428,330]`。 |
| `androidTest/ClickSoundDeviceTest.kt`（新增） | +108/-0 | 实际播放器快点、prepareAsync、无效文件、关闭；亦用于外部 PCM 捕获。 |
| `androidTest/FeedbackRegressionTest.kt`（新增） | +158/-0 | 真实 View 逐帧像素观察，暂停、重复点击、尺寸/镜像、detach 与配置兼容。 |
| `androidTest/UpgradePreferencesTest.kt`（新增） | +38/-0 | 在两次真实安装之间验证设置保留，夹具用 commit 明确等待落盘。 |
| `android/app/build.gradle.kts` | +3/-3 | versionCode 3 / versionName 0.2.1；启用 BuildConfig 统一版本显示。 |
| `scripts/build_android.ps1` | +4/-2 | 从 Gradle output-metadata.json 取版本/产物名，消除手写旧文件名。 |
| `scripts/android_acceptance.py` | 累计 +624/-52 | 含继承草稿；本轮补碰撞行、改默认断言、区分播放计数与声音、关闭通知栏、允许模块全部关闭、滑条改用点触以避开系统导航手势。 |
| `tests/test_android_acceptance.py` | 本轮 +16/-1 | 补最后一个模块关闭后空集合也代表成功的回归。 |
| `docs/ANDROID.md` | +23/-13 | 版本、缺键/升级语义、试听、形变空间和伙伴停服保存契约。 |
| `docs/INDEX.md` | 本轮 +2/-2 | 更新当前版本和本报告第九节入口。 |
| 本报告 | 相对 HEAD +530/-0（含历史） | 保留 0.2.0 历史，追加本轮实证与限制。 |

没有删除用户文件；APK、SDK、密钥和采样文件不入库。未修改桌面 `pet/` 产品代码。

### 9.2 性能分析

环境：Windows 11 10.0.26200，Ryzen 7 H 255，16 逻辑核，约 15.3 GiB 可用物理内存；
API 35 Google APIs x86_64 AVD，1080×2340、density 440、SwiftShader 软件 GPU。
**这些是本机模拟器数字，不是真机耗电/流畅度结论。**

命令：`.venv/Scripts/python.exe .scratch/android-pet/fix-021/measure_households.py`。
每组先预热 48×宠物数次绘制，再采样约 20 秒、4 个样本，六组共 24 样本。
原始 `dumpsys meminfo`、`top`、运行计数及 HWUI 数据在 `performance35/`。
游走/台词/音效关闭，碰撞依次开关；绘制率为**所有窗口合计**，CPU 100% 表示一核。

| 宠数 | 碰撞 | CPU 中位 % | PSS 中位 KiB | 合计绘制/s | HWUI p95 ms | 未就绪帧 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | 关 | 27 | 139473.5 | 19.778 | 18 | 0 |
| 1 | 开 | 28 | 140738.5 | 20.048 | 18 | 0 |
| 2 | 关 | 73 | 148314 | 39.954 | 28 | 0 |
| 2 | 开 | 51 | 156640 | 40.067 | 18 | 0 |
| 5 | 关 | 184 | 147640 | 97.159 | 69 | 208 |
| 5 | 开 | 188 | 175988 | 97.039 | 73 | 200 |

顺序短样本有 JIT、GC、软件渲染和宿主调度噪声，不能把双宠开碰撞时 CPU 下降解读成
“碰撞优化了性能”。五宠已有明显帧延迟/解码压力，此次没有把它包装成优化成果。
固定大小并不保证目标 24fps：本机 60Hz 的离散 tick 下待机约 20 次绘制/秒/宠。

新增点击路径另测：`.venv/Scripts/python.exe .scratch/android-pet/fix-021/measure_taps.py`。
单宠暂停、所有可选模块关闭，实际输入 20 次点击，耗时 11.406 秒；新增 299 次绘制，
平均 **14.95 绘制/次**，`/proc/<pid>/stat` 进程 CPU 增量 2.77 秒，即 **138.5ms/次**。
HWUI p95 30ms，27/299 帧被系统记作 janky；包含点击动作换帧/解码及 Q 弹，
不是纯形变数学的计时。PSS 从 143371 到 138627 KiB。原始数据在 `tap-performance35/`。

- 稳态：Q 弹结束没有额外常驻刷新，暂停/锁屏仍能停止自动绘制；碰撞开关数据见上表。
- 触发频率：点击或真实碰撞触发一个 220ms 脉冲；音效同种事件至少间隔 80ms，待播每种至多一项，1 秒过期。
- 系统调用/线程：不增加网络或应用后台线程；保留原来的音频原生资源。试听按需另建一个输出，
  内置音最多一个 SoundPool + 两个 MediaPlayer，离开设置/切音源/关闭/再次试听均释放旧实例。
  prepare 最长等 5 秒，失败释放播放器；设置仍使用原 SharedPreferences 保存。
- 内存：没有增加帧缓存预算（仍为 24MiB），短样本 PSS 有 GC 波动，最高 183222 KiB；
  不能用短测证明长期无增长。没有真机 30 分钟长跑、耗电或温升结论。

### 9.3 实机运行记录（本机模拟器，非手机）

原故障红记录：`logs/red-geometry.log` 为 80 项中 4 项失败（默认值、误碰撞、真实击中、裁边）；
`logs/red-device.log` 三项失败，快点 `expected 2 but was 1`、暂停无形变、缺键仍关音效。
逐帧观察版本再次装旧 APK 验证：`logs/red-draw-observer.log` 明确失败
`no squashed frame drawn`；并非定时采样碰巧没看到动画。

修复后 API 26 和 API 35 实际安装、运行 Android 插桩测试。测试使用真实主线程、View、
Audio 输出、WindowManager 与前台服务；涵盖权限、重启、帧输出及本轮回归。
服务停启的伙伴丢失也是设备测试先红，随后加“停止后不再保存空布局”的修复转绿。

覆盖升级：API 26 安装 0.2.0，执行 `UpgradePreferencesTest -e upgradePhase before`，
`adb install -r` 安装 0.2.1，再执行 `-e upgradePhase after`，两端均 `OK (1 test)`。
音效关、碰撞关、音量 0.4、大小 1.3、台词和位置 0.2/0.3 均保留。
最初夹具用 apply 后立即结束 instrumentation，实际磁盘是 `<map />`；改用 commit
等待夹具落盘后复测。这个失败是夹具生命周期，不能作为升级迁移故障。

音频实证命令：`audio-env/Scripts/python.exe audio_probe.py --source builtin|custom --volume 0|0.5|1`
（从证据目录执行）。使用 SDK 自带 `emulator_controller.proto` 的 `streamAudio` 捕获真实
混音输出，每次调用 8 秒，实际返回约 3.15–3.21 秒 44.1kHz/16-bit/stereo PCM。
六次实际播放测试均 `OK (1 test)`，不是仅看 `audioPlays` 计数。
自选分支使用 `android.resource://` 音频夹具，未声称已验证所有手机文档提供方。

| 路径 | 应用音量 | PCM 峰值（16-bit） | 全捕获 RMS |
|---|---:|---:|---:|
| 内置备用播放器首次点击 | 0 | 3 | 0.162 |
| 内置备用播放器首次点击 | 0.5 | 125 | 8.823 |
| 内置备用播放器首次点击 | 1 | 255 | 17.561 |
| 自选音源 prepareAsync | 0 | 2 | 0.126 |
| 自选音源 prepareAsync | 0.5 | 127 | 8.825 |
| 自选音源 prepareAsync | 1 | 237 | 17.558 |

0 音量剩余为模拟器混音底噪；50%→100% 的 RMS 接近两倍。测试时实际媒体音量为 5/15。
尝试 `cmd media_session volume` 调音量被 API 35 AppOps 拒绝（调用包与 shell uid 不符），
没有将命令的打印当成设置成功；因此**没有验证“系统音量为零而媒体仍出声”这个组合**。
已验证实际输出非静音和两条播放路径的应用音量，尚未由人耳确认手机扬声器音量。
另外在桌宠未启动时，实际点设置页的 Preview 按钮，捕获 `audio-settings-preview.wav`：
应用音量 70%，PCM 峰值 164、RMS 12.277，确认了设置入口的真实播放接线。
`preview35/settings-preview.png` 已检查，音效行与按钮没有遮挡或越界。

真实触摸碰撞：运行 `collision_smoke.py`，关闭碰撞后把小宠拖到母宠上并松手，
截图 `collision35/off-overlapping.png` 看到重叠；通过设置开启碰撞，
`collision35/on-separated.png` 看到两宠被挤开。两窗口位置从
`[[513,1962,902,2236],[448,1917,966,2282]]` 变为
`[[651,1981,1040,2255],[370,1906,888,2271]]`。截图已人工图像复核。

跨应用/权限/锁屏脚本第一遍已确认权限拒绝入口、覆盖时钟应用、抛掷、暂停、
锁屏 2 秒绘制与解码计数不增长、解锁恢复；随后脚本被通知栏遮住，找不到台词设置行。
保留 `acceptance35/` 和 `acceptance35-final/` 两次失败证据；仅收起通知栏仍未解决。
按仓库纪律停止全流程重试，将台词段隔离检查，滑条操作改为点触以避开边缘拖动导航；
`logs/speech-isolated.log` 确认实际输入的 `dsh-pet-acceptance-line` 出现在气泡。
没有把这个独立通过写成完整历史脚本全流程通过；本次三项的独立验收及全部插桩测试已完成。

### 9.4 测试与交付

| 门 | 命令/证据 | 结果 |
|---|---|---|
| Android 单元测试 | `./scripts/build_android.ps1 -Tasks testDebugUnitTest` | 88 通过，0 失败 |
| Android lint / APK | 默认构建任务，`logs/delivery-build.log` | BUILD SUCCESSFUL；lint 无错误 |
| API 26 插桩 | `adb -s emulator-5556 shell am instrument -w ...AndroidJUnitRunner` | 15 通过；双安装测试默认跳过，单独 before/after 均通过 |
| API 35 插桩 | `logs/verified-device35-final.log`，交付 APK | 15 通过，双安装专用测试默认跳过；39.743 秒 |
| 高负载时序族 | `stress_feedback.py`；16 个 CPU 繁忙进程 | 每遍 6 项，连续 3 遍通过（`stress-synchronized.log`） |
| Python 全量 | `.venv/Scripts/python.exe scripts/ci_shards.py`，另跑四个隔离族 | 1695+1889+1901+1963+68 = **7516 通过，17 跳过** |
| Python 聚焦 | `pytest -q tests/test_android_assets.py tests/test_android_acceptance.py tests/test_pr_report_discipline.py` | **165 通过**，含本轮新增脚本回归 |
| 静态检查 | `ruff check pet tests scripts`、`git diff --check` | 通过 |

高负载最初失败是每 50ms 采样错过 220ms 短脉冲；改成 OnDrawListener 逐帧锁存、
CountDownLatch 同步及批量读像素，不延长产品动画，不删除断言。最后一个模块关闭时，
验收脚本把空集合误作未完成，新增 Python 回归先红后修复；这个修复也不改产品逻辑。

产物：`dist-android/dsh-pet-android-0.2.1-debug.apk`，55,259,426 字节，
`versionCode=3`、`versionName=0.2.1`；构建命令 `./scripts/build_android.ps1`。
SHA-256：`005e88c66e7081eb4ac75e23d842d64d0e862e4e03240d4e98922c0c191ffb3f`。
`apksigner verify --print-certs` 两版都通过，同一证书 SHA-256：
`6bff57ec335564392e4acce881b0fdb6cdd198ed2022148a3e0d268dac3db379`。
密钥没有复制到工作区，版本显示/产物文件名来自同一个 Gradle 版本。

**仍未验证**：验证期间 `adb devices -l` 只有 `emulator-5554` / `emulator-5556`，没有手机；
真机扬声器、厂商后台策略、30 分钟耗电/温升没有数据。Q 弹留白会略扩大透明触摸矩形，
没有绕过 Android 的触摸窗口限制。支持离线手动启动，不保证强制停止后常驻。

