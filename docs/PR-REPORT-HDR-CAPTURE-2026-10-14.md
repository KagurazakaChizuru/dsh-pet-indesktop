# HDR 显示器截图通道（DXGI Desktop Duplication，FP16 scRGB → sRGB 8-bit）—— 实机与成色证据

> **基线**：`ef1c8e4`（`feat/screen-capture-p0` HEAD，复制图像同时塞无损 PNG）
> **分支**：`feat/screen-capture-p0`　**日期**：2026-10-14
> **范围**：4 个文件（实现 2、测试 1、文档 1；另有一份不随 git 走的真机探针）
> **关联**：本报告接续 [`PR-REPORT-SCREEN-CAPTURE-P0-2026-10-14.md`](PR-REPORT-SCREEN-CAPTURE-P0-2026-10-14.md)
> 的遗留项「HDR 屏成色」；参照实现是 flameshot PR #4974 的
> `src/utils/windowshdrcapture.cpp`（Windows 专用 HDR 路径）。

## 一、核心特性

HDR 常开的屏幕上，`QScreen.grabWindow`（GDI BitBlt）拿到的是 Windows **按 SDR
参考折叠过**的 8-bit 图，肉眼观感发白雾（用户在 P0 里用 PixPin 对比确认）。本片给
冻结帧加一条**HDR 专用通道**：用 DXGI Desktop Duplication 读 DWM 合成的 FP16
scRGB 桌面，自己做「按本机 SDR 白点归一 → 按 SDR 范围钳制 → sRGB 编码」三步换算。

| # | 能力 | 说明 |
|---|---|---|
| 1 | `hdr_capture.hdr_state(screen)` | DisplayConfig 读「高级颜色（HDR）是否启用 + SDR 白点系数」。本机实测 `(True, 3.5)`（= 280 nits）。只读、零副作用、不碰 DXGI |
| 2 | `hdr_capture.grab_hdr_sdr(screen)` | DXGI 复制会话抓 FP16 → sRGB 8-bit QImage（设备像素、dpr=1.0、标 sRGB）。**任何一步失败返回 `None`，绝不抛给调用方** |
| 3 | `pixels.grab_screen_image` 接线 | HDR 屏先试新通道，拿不到就落回原 `grabWindow` 路径（**回退路径行为一字未改**）；逃生门 `DSH_PET_DISABLE_HDR_CAPTURE=1` 直接跳过新通道 |
| 4 | 会话按屏缓存 + 分级退避 | 连续截图复用 D3D11 设备与会话；失败退避 60s，「桌面模式给不出 FP16 帧」这种判定级失败退避 900s |

**红线 / 不变量**

- **抓帧主路径不许被这条通道影响**：HDR 没开、读不到、驱动拒绝、别的应用占着
  复制会话、帧格式不符、QImage 分配失败——一律 `None` + 一行日志，调用方落回 GDI。
- **绝不交出黑图**：刚开的复制会话第一帧是**未初始化的全零 FP16 面**（本机实测），
  遇到全零会再等一帧，仍全零就判失败（真·全黑桌面在 GDI 那边同样是黑，不丢内容）。
- **坐标口径不变**：返回图仍是「设备像素 + dpr=1.0」，`crop_selection` 的换算口径不动。
- **SDR 内容不许被动过**：已知 SDR 色块两条路逐字节相同（§五，Δ0×8 色）。
- 不新增运行时依赖（纯 ctypes，不引 comtypes），不动打包脚本。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/screen_capture/hdr_capture.py` | +1196 / −0（新增） | HDR 抓帧通道本体：DisplayConfig 判定（`hdr_state`）+ DXGI/D3D11 复制会话（`_Session`）+ FP16→sRGB 换算（`_srgb_lut` / `fp16_scrgb_to_srgb8`）+ QImage 组装（`_qimage_rgb888`）+ 会话缓存与分级退避 |
| `pet/screen_capture/pixels.py` | +34 / −3 | `grab_screen_image` 接线：新增 `_grab_hdr_screen(screen)`（三层闸 + 兜底 `except`），`grab_screen_image` 先试它、`None` 就走原来那条 `grabWindow` 路径；模块 docstring 更新为现状 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_screen_capture_hdr_capture.py` | +692 / −0（新增） | 53 例：换算数学（含**全部 65536 个 FP16 位模式**对一遍标量参考实现）、Win32 结构体尺寸契约、`hdr_state` 判定矩阵、`grab_hdr_sdr` 的失败/退避/缓存路径、全零首帧重试、`pixels` 接线四条回退路径与逃生门 |

### 未改动（故意）

- `pet/screen_capture/overlay.py` 的 `DIM_ALPHA = 80`（「HDR 屏的 SDR 感知提亮会把
  重压暗抬成白雾，所以只到 80」）**没动**：那是框选遮罩的视觉参数，与抓帧通道无关；
  真要跟着新通道重调，得先有实机对比结论（见 §六遗留）。
- `requirements.txt`：**没有新增依赖**。仓库既有的 DXGI 用法（`.scratch/screen-capture/
  probe_hdr.py`、`pet/gpu_monitor.py`）都是 ctypes 手写虚表调用，本模块沿用同一套路，
  因此不动依赖与三个构建脚本（comtypes 只在任务书里作为「若用则须登记」的备选）。
- 打包脚本、`docs/ONEDIR_PACKAGING.md`：新模块是纯 Python + ctypes，静态 import 可收，
  无需 `--hidden-import`。

### 真机探针（不随 git 走，`.scratch/` 被 `.gitignore:71` 忽略）

| 文件 | 行数 | 作用 |
|---|---|---|
| `.scratch/screen-capture/probe_hdr_capture_ab.py` | 554 | 同屏 A/B：GDI → HDR → GDI → GDI 四张 + 已知色块带；打印 DXGI 能力表、逐帧格式诊断、亮度/差值分布/静态像素比对/差异热点图，产物落 `.scratch/screen-capture/hdr_ab/` |

## 三、实现要点

### 1. 判定与换算分开，判定只用只读 API

`hdr_state` 只走 DisplayConfig（`QueryDisplayConfig` + 三个 `DisplayConfigGetDeviceInfo`
查询：目标友好名、源 GDI 名、高级颜色状态、SDR 白点）。**SDR 屏在这一层就返回
`(False, 1.0)`，一次 DXGI 也不碰**。屏幕定位三级：`QScreen` → `MonitorFromPoint`（该屏
物理像素中心）拿 `HMONITOR`/`\\.\DISPLAY1`（多屏同型号也唯一）；字符串 → 先按 Qt6 的
友好名（本机 `QScreen.name()` 返回的是 "H27T22S" 型号名，不是 GDI 名）再按 GDI 名匹配，
**同名命中多个活动输出时返回失败**（宁可回退 GDI，也不猜错屏）；`None` → 主屏。

### 2. 换算：按 SDR 白点归一 → 钳制 → sRGB 编码，用位模式查表

scRGB 里 `1.0 == 80 nits`，而 SDR 白点是 `SDRWhiteLevel / 1000` 个 scRGB 单位（本机
3500 ⇒ 3.5 ⇒ 280 nits）。除以它让 SDR 白落回 1.0，超出的按 SDR 范围钳到 255，再走
sRGB 传递函数（线性 0.5 → **188**，不是截断的 128）。

实现细节上有一处**性能驱动的关键取舍**：逐像素 `astype(float32) + np.power` 在
2560×1440 上实测 **318ms**（多个 44MB 临时数组 + 1100 万次 `pow`），改用
**65536 项 FP16 位模式查表**后 **41ms**（建表 4ms + 一次 gather），结果与逐像素算法
**逐位相同**——测试里有一条把全部位模式（含 denormal、±inf、sNaN/qNaN）对一遍标量
参考实现的断言守着，因为「表索引错一格 / 字节序反了」这类缺陷普通断言看不出来。

### 3. 复制会话：`DuplicateOutput1` 优先，经典接口兜底，判据落在帧上

- `DuplicateOutput1`（文档指定的 HDR/高色深通道）成功时给的才是**带真实桌面内容的
  FP16 帧**——这是本机实测的结论，也正是 flameshot 用的那条路；
- 经典 `DuplicateOutput` 的稳态帧是 **BGRA8**（与文档一致），它给的唯一 FP16 帧是
  **刚开会话那一张未初始化的全零面**；所以「是不是 FP16」这层判据必须落在**帧**上，
  不能只看接口拿没拿到；
- `DuplicateOutput1` 在这台机器上**反复无常**（§五有整段时间全失败、过一阵全成功的
  原始 HRESULT）：因此失败时**不能**当成「这台机器永远不行」，退避按抖动算（60s）；
  只有「协商成功却仍给 BGRA8」才按桌面模式级判定退避（900s）。
- 会话按显示器缓存（D3D11 设备 + 复制会话）：静态桌面上用过的复制会话再抓必然超时，
  此时**只重开复制会话、保留设备**（实测重开 2.3ms，而建设备 ~110ms）。

### 4. 线程与生命周期

整条抓帧在模块级 `RLock` 内串行（复制会话与其 immediate context 不能并发使用），
不碰 Qt 事件循环，也不碰 GUI 之外的 Qt 对象。COM 引用按「先派生后依赖」释放，失败
路径逐段 `release`（写这一层时踩过两次双重释放与一次指针泄漏，探针逐帧诊断把它们
逼出来了）。

## 四、性能分析

真机（Win11 10.0.26300 / H27T22S 2560×1440@170Hz HDR10 / AMD 核显驱动 DISPLAY1 /
RTX 4060 Laptop / dpr=1.0），命令：
`python .scratch/screen-capture/probe_hdr_capture_ab.py`，样本见
`.scratch/screen-capture/hdr_ab/probe_output.txt`。

| 环节 | 实测 | 样本/条件 |
|---|---|---|
| `hdr_state()` | **0.36–2.96ms** | 每次截图调用一次（DisplayConfig 三个查询） |
| 建会话（枚举 DXGI + `D3D11CreateDevice` + 开复制会话） | **108–113ms** | 每进程每屏一次 |
| 重开复制会话（保留设备） | **2.3ms** | 静态桌面上每次抓帧走这条 |
| `AcquireNextFrame` + 拷进 staging + Map | **6–35ms** | 2560×1440 FP16（14.7MB 读回） |
| FP16→sRGB8 换算（查表版） | **41ms** | 2560×1440，n=3 取最优；旧逐像素版 318ms |
| numpy→QImage | ~3ms | 一次 11MB 拷贝 |
| **整条 HDR 抓帧（会话已缓存）** | **59.0 / 59.5 / 61.2 / 62.0 / 62.5 / 62.6 ms** | 6 次连续测量（多次运行） |
| 同屏 GDI 抓帧（对照） | **64.1–82.0ms** | 同一探针同一次运行内的 `grabWindow` |
| 冷启动首张 HDR 图 | **≈200ms**（含建会话 110ms） | 每进程一次；失败退避期内则为 0–1ms |

**逐条回答**：

- **稳态开销**：会话缓存命中时，每次截图 HDR 通道 ~60ms，与既有 GDI 路径（~65ms）
  同级，**没有把截图变慢**；`hdr_state` 不到 3ms。
- **新增路径成本与触发频率**：只在「该屏 HDR 已启用」时触发；SDR 屏每次截图多付一次
  DisplayConfig 查询（<3ms）。失败后 60s（判定级 900s）内不再尝试，成本 0–1ms。
- **新的系统调用/网络/磁盘/线程**：新增 Win32 调用（DisplayConfig 查询、DXGI/D3D11 ICU）；
  **无网络、无磁盘**（像素只在内存里，与 `pet/vision.py` 同一约定）；**无线程**——不建
  任何线程，抓帧在调用线程内同步完成，也不进 Qt 事件循环。
- **内存**：一块 2560×1440 的 FP16 staging 纹理（14.7MB GPU 侧）+ 映射读回期间的一次
  行缓冲视图 + 一张 11MB 的 sRGB8 数组/QImage（后者下游本来就要） + 64KB 查表。
  会话缓存持有 D3D11 设备/复制会话（一块屏一份）；失败或元数据变化即整份释放。
- **打包体积**：无新增依赖，产物不变。

## 五、实机运行记录

全部真机命令与原始输出：`.scratch/screen-capture/hdr_ab/probe_output.txt`（每跑一次覆盖），
A/B 图与热点/放大对照图同目录。

1. **HDR 状态与白点**（真显示器，HDR 常开）：
   `hdr_state=True`、SDR 白点系数 `3.5`（= 280 nits）、DXGI 输出
   `ColorSpace=12 (RGB_FULL_G2084_NONE_P2020)`、`Rotation=1`、`BitsPerColor=10`、
   `MaxLuminance=374.0`、`Desktop=2560x1440`；定位 `QScreen("H27T22S") → \\.\DISPLAY1`。

2. **已知 SDR 色块 A/B（成色锚点）**：屏幕上放一条 8 色条（黑/25%/50%/75% 灰/白/R/G/B），
   两条路各读一遍色块中心（13×13 均值）：

   ```
   black   期望=(0,0,0)       GDI=(0,0,0)       (Δ0)  HDR=(0,0,0)       (Δ0)
   gray25  期望=(64,64,64)    GDI=(64,64,64)    (Δ0)  HDR=(64,64,64)    (Δ0)
   gray50  期望=(128,128,128) GDI=(128,128,128) (Δ0)  HDR=(128,128,128) (Δ0)
   gray75  期望=(192,192,192) GDI=(192,192,192) (Δ0)  HDR=(192,192,192) (Δ0)
   white   期望=(255,255,255) GDI=(255,255,255) (Δ0)  HDR=(255,255,255) (Δ0)
   red/green/blue 同：Δ0
   ```

   → **归一化系数（3.5）与 sRGB 编码是对的**：HDR 通道不是「整幅提亮」，SDR 内容在
   两条路下逐字节一致。这是本片最关键的一条实机证据。

3. **A/B 两张图（供肉眼对比）**：`.scratch/screen-capture/hdr_ab/` 下
   `ab_gdi_1.png` / `ab_hdr.png` / `ab_gdi_2.png` / `ab_gdi_3.png`（2560×1440，
   同一屏连续四张：GDI → HDR → GDI → GDI），另有
   `hotspot_gdi_hdr_diffx5.png`（差异×5 放大 + 上下对照）与
   `crop_text_gdi_top_hdr_bottom_x3.png`（文字区 3 倍放大，上 GDI / 下 HDR）。

4. **逐像素统计（同一探针同一次运行，2560×1440；下文数字取自末次归档 run，跨 run 的波动见括注）**：整图 luma（编码域，Rec.709 系数）均值 GDI **127.41/127.49**、HDR **125.85**（多次运行落在 127.0–128.8 / 125.9–127.4），**中位数 63.7 对 63.6**，p1/p99 同为 4.1/255。

   用「多张 GDI 抓帧逐字节一致」的像素当运动掩码（这些像素在抓帧间隔里**确实没变**，
   于是差异只能来自路径本身）：

   | 比对 | 掩码内像素 | 逐字节同 | mean&#124;Δ&#124; | p90 | p99 | Δ>10 占比 |
   |---|---|---|---|---|---|---|
   | 自检：GDI vs GDI | 2,681,107 | 100% | 0.000 | 0 | 0 | 0% |
   | GDI vs HDR（2 帧掩码） | 2,681,107 | 71.2% | 2.944 | 7 | 69 | 4.7% |
   | GDI vs HDR（3 帧掩码） | 2,521,177 | 71.6% | 3.079 | 9 | 71 | 4.8% |

   （跨多次运行的区间：逐字节同 71.2–73.6%、mean 2.81–3.08、Δ>10 占 4.5–4.8%。）
   **两张与三张掩码几乎一样**（Δ>10 的像素 125,157 → 121,336）⇒ 差异不是「周期性变化
   的假阳性」。**符号**：`signed_mean_rgb = HDR − GDI = −2.68/−2.52/−2.34`，即这些静态
   像素上 HDR 通道平均略暗；Δ>10 的那 4.8% 子集里 GDI 均值 (193.5, 197.8, 197.3)、
   HDR 均值 (163.8, 165.7, 166.7)。

   **差异热点**（静态像素上的 `mean|HDR−GDI|`，12×7 屏幕分格）显示差异**集中在画面
   中部的窗口区**（最高 15.8），大片平坦区/边缘区是 0.0–0.2：

   ```
   行0: 0.3 0.2 2.3 [6.3 6.8 7.8 7.1 6.6] 2.6 0.3 1.5 0.0
   行1: 0.0 0.1 5.2 [8.7 2.8 11.1 10.4 5.6] 1.7 0.1 1.4 0.0
   行2: 0.1 0.2 3.9 [10.1 3.8 16.5 11.9 9.3] 1.9 0.2 0.1 0.1
   行3: 0.4 0.5 5.4 [11.7 1.6 5.1 7.6 6.2] 1.2 0.2 0.1 0.0
   ```

   该窗口区（x 600–1760, y 0–660）的同路径基线是 `mean=0.771–0.872 / >10 占
   1.4–1.7%`，跨路径是 `mean=8.257 / >10 占 13.4%`——**跨路径差是同路径运动噪声的
   10 倍**，所以这确实来自路径，不是桌面在动。差异形态是**文字/UI 边缘**（放大对照图里表现为字形
   轮廓），平坦区域与已知色块则完全一致。

   **诚实边界**：本探针能证明「平坦区与受控色块两路一致、差异集中在高频细节区且远超
   运动基线」，**不能**单独归因到底是 (a) Windows 给 GDI 折叠路径的 AA/量化与我们的
   scRGB→sRGB 不是同一条，还是 (b) 该窗口在两次抓帧之间重绘过（同一探针里 GDI 基线
   只有它的 1/10，倾向 (a)，但没到可下结论的程度）。要定性需要受控内容（HDR 视频/已知
   高频图案）再测一轮，见 §六。

5. **通道可用性会反复无常（原始 HRESULT）**：同一次会话里探针会把逐格式 HRESULT 打出来。
   实测出现过两种状态：

   - 成功态：`DuplicateOutput1[FP16]=0x0`、`[BGRA8]=0x0`、`[FP16+BGRA8]=0x0`、经典 `0x0`，
     且前 3 帧里**帧 1、帧 2 都是带真实内容的 FP16**（换算后 mean≈124.6–126.4，300ms 内
     每帧 <1ms 轮询到手）；
   - 失败态：`DuplicateOutput1` 对**任何**格式表、任何设备标志（含 `BGRA=0/0x20`、
     feature level 11_1、默认适配器）都返回 `0x887a0004 DXGI_ERROR_UNSUPPORTED`，此时
     经典接口的帧是 BGRA8（`format=87`）。同一槽位传空设备指针返回 `E_INVALIDARG`
     （0x80070057），可确认槽位没记错——即不是调用约定写错，是驱动/OS 当时的拒绝。

   这正是「退避分级」的实测依据：协商失败按 60s 抖动退避（等它自己恢复），协商成功却
   仍给 BGRA8 才按 900s 判定退避。

6. **帧 0 是全零**：每次（重）开复制会话后，第一帧 `desc` 报 FP16 但内容全 0
   （`mean=0.00 max=0`），第二帧才是桌面图。因此 `grab_srgb8` 里有那条「全零再等一帧，
   仍全零就回退」的防守——**这条防守用探针验证过是必需的**（拿掉它就会把黑图当截图）。

7. **离屏测试**：`QT_QPA_PLATFORM=offscreen python -m pytest
   tests/test_screen_capture_hdr_capture.py tests/test_screen_capture_pixels.py -q`
   → **74 passed**（新 53 + 既有 21）。`python -m ruff check pet/ tests/test_screen_capture_hdr_capture.py`
   → 零告警。测试先红后绿，另做了 6 条消融验证（去掉钳制 / 量化改截断 / 去掉全零重试 /
   判定级退避缩回 60s / 逃生门失效 / 接线不判 `None`）：除「去掉钳制」外全部变红——
   那条如实登记：末尾量化那次 `clip` 兜住了行为，中间那次钳制是语义边界而非可观测差异。

## 六、遗留

1. **差异归因**（§五.4）：需要一轮受控内容实验（HDR 视频或已知高频图案）才能判定
   「GDI 折叠 vs scRGB 换算」与「窗口重绘」各占多少；本片的验收不依赖它。
2. **框选遮罩的 `DIM_ALPHA=80`**（`overlay.py`）是为「HDR 屏 SDR 感知提亮」调的，
   新通道上线后是否要重调，等上面的归因结论与用户肉眼反馈。
3. **`DuplicateOutput1` 反复无常**：本片用分级退避兜住（可用时 60ms 拿到 HDR 图，
   不可用时静默回退 GDI）。若这种抖动是驱动/OS 版本问题，长期方案是改用
   Windows.Graphics.Capture（WGC）——`requirements.txt` 里已有
   `winrt-Windows.*` 投影包（cp313 有轮子），但那是另一个量级的改动，未采用。
4. **多屏**：抓帧通道按屏定位与缓存都写好了（物理位置匹配），但本机只有一个显示器，
   **多屏路径没有真机验证**；`pixels` 的调用方目前也仍是主屏（P0 遗留）。
5. **HDR 关闭/切换**：会话元数据校验会在色彩空间变化时重建（含 HDR 关掉后自动回到
   GDI），但「HDR 开关过程当中抓一张」的时序没有专门真机验证。
