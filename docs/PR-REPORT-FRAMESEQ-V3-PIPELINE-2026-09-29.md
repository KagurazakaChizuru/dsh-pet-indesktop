# 帧序列统一档位 v3（`unblend-white-v3`）全量重出与打包部署（2026-09-29）

> **基线**：`ebf971e`（fix(collision): 拖拽成员速度通道）+ 工作树未提交 WIP（含 R1/R2 帧序列表与 09-28/09-29 各批）
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-29　**拓扑**：`PET_RENDER_TOPOLOGY=overlay`
> **范围**：`pet/frameseq_provision.py` 为主的 4 个产品/工具文件的累计 diff + 3 个新增测试文件 + 106 段素材世代重出（素材不入 git，随包）
> **关联**：[`PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md`](PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md) §十四（R1/R2 把冷集接入帧序列）、
> `.scratch/HANDOFF-20260929.md`、`.scratch/overnight-20260929/MORNING-REPORT.md`、`.scratch/asset-pipeline-20260929/`

## 一、核心特性

把「首跑自动供给」的帧序列从**三代混档**（热集无损 / 冷集 Q80 / 反解 v2）收敛为
**一档**：全部 clip 统一 `libwebp lossy q70 (bgra straight, unblend-white-v3)`。
`ENCODER_DESC` 串写进每个世代的 `meta.json` 并成为**采纳条件之一**，因此改档前的
三代产物一律不再被采纳（宁可重转，不拿旧档产物顶替）。106 段源 webm 已全量重出，
磁盘占用按同一棵树同口径实测 **573.3MB → 379.1MB**（−194.2MB / −33.9%）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 统一档串 | `ENCODER_DESC = "libwebp lossy q70 (bgra straight, unblend-white-v3)"`；旧档串进 `LEGACY_ENCODER_DESCS`，只用于「识别旧产物」 |
| 2 | 两段式转换 | ffmpeg 一次调用写**无损中间帧** → Pillow 逐帧 `unblend_v3`（反解白底混合 → 低 alpha 收色 → alpha 微缩 1px）→ 原地 Q70 |
| 3 | 采纳闸门 | 世代目录名带戳 + meta 戳 + 名字戳 = meta 戳前缀 + meta 帧数 = 磁盘帧数 + **meta encoder = 当前档串**，五条全过才采纳，否则回退 WebM |
| 4 | v4 镂空还原**挂起** | `restore_hair_holes` 已实现（`HOLE_RESTORE_ENABLED = False`，零开销直通）：实机误切白色鲸鳍，等用户给精确残留坐标后重标定 |

**红线 / 不变量**：
- **帧内容永不哈希/解码**（采纳只看带戳 meta 与帧数）；采纳前只对**源 webm** 重算 sha256，不做 `(mtime_ns, size)` 记忆（同尺寸 + mtime 复原的替换会命中 stat 记忆，静默播旧素材）。
- **绝不原地覆盖在用世代目录**：先转 `<世代名>.tmp/`，成功后 `os.rename` 原子发布；重建走 `.replacing/` 且发布成功后才删旧目标。
- 回退路径（`PET_FRAMESEQ=0`、无世代目录、档不符）必须是**已存在且行为不变**的 WebM 播放，不得因为重出素材而退化。

## 二、修改文件说明

> **归因口径**（沿用 09-27 报告 §二）：`git diff` 是相对 HEAD 的**累计** diff。同一文件
> 若被多条线改过，**不按行数拆分、也不做逐 hunk 归属**；下表「本批」一栏的依据是
> `pet/frameseq_provision.py` 模块 docstring 与本批的测试/素材现场，不是 mtime。

### 实现

| 文件 | 增删（`git diff --numstat`，相对 HEAD） | 改动意图 |
|---|---|---|
| `pet/frameseq_provision.py` | +2037 / −80 | **累计**（含 09-27 的 R2 供给序/磁盘准入 + 本批 v3）。本批：`ENCODER_DESC` 统一档、`LEGACY_ENCODER_DESCS`、`convert_clip` 两段式（无损中间帧 → `unblend_frames_in_place` → Q70）、`unblend_v3`/`unblend_rgba`/邻居收色/`restore_hair_holes`（挂起）、采纳闸门加 encoder 校验、`current_generation` |
| `pet/frameseq_clip.py` | +235 / −21 | **累计**（含 09-27 R1 帧表懒列 + 09-29 M1 帧表现推）。本批相关：帧 0 冷解码路径与 `FIRST_FRAME_WARM_TRIVIAL`（见共享素材库报告） |
| `tools/convert_frameseq.py` | +23 / −9 | 转换入口：`--force` 逃生门、`--include` 过滤；本批用于 106 段**全量重出**的批量调用 |

### 素材（不入 git，随包分发）

| 位置 | 变化 | 说明 |
|---|---|---|
| `assets/characters/shenshen/frameseq/**` | 106 个世代目录重出（09-29 14:17–15:33 落盘） | 目录名 `<clip>.g<源 sha256 前 12 位>/`；每目录 `meta.json` + 241 帧 `f_%04d.webp` |
| 同上 | 11 个**无戳**旧目录保留 | 热集旧格式（`待机呼吸休闲/`、`点击回应-*/` 等）；**不采纳、不补戳、也不删**（可能正被旧版本实例读取） |

### 测试

| 文件 | 增删 / 行数 | 覆盖 |
|---|---|---|
| `tests/test_frameseq_unblend.py` | 新增 204 行（未跟踪） | 反解数学（逐像素口径） |
| `tests/test_frameseq_unblend_v3.py` | 新增 328 行（未跟踪） | v3 全链：反解 → 收色 → alpha 微缩 |
| `tests/test_frameseq_unblend_v4.py` | 新增 464 行（未跟踪） | `restore_hair_holes`（当前挂起，测试锁「挂起时直通」与「开启时行为」） |
| `tests/test_frameseq_provision.py` | +2542 / −162（**累计**，含 R2 + 本批） | 采纳闸门五条、发布/回滚、退役与回朝、`unblend_v3` 接入 |

### 未改动（故意）

`pet/webm_clip.py` 的 webm 播放路径、`pet/library.py` 的采纳入口（本批只换素材与 meta
档串，走的是同一条 `current_generation` 闸门）、`pet/config.py`（**未新增任何配置键**）。

## 三、实现要点

1. **为什么不让 ffmpeg 一趟做完**：素材是白底抠图，半透明像素存值里混着白
   （`stored = 角色色 × a + 255 × (1-a)`），必须在**有损编码之前**按 alpha 反解——
   先有损再反解等于把白晕连量化噪声一起固化。ffmpeg 侧理论上能用 `geq` 把反解和编码
   合成一趟（模块 docstring 记的实测：`geq` 41ms/帧，比 Python 逐帧快 ~1.6x），但：
   ① 反解在这里是**纯函数**（`unblend_rgba`，逐像素口径由单测钉住；`geq` 只能靠真跑
   ffmpeg 验）；② v3 的收色要**邻域**信息（最近的不透明邻居颜色），`geq` 表达不了；
   ③ 逐帧粒度让关机窗口里的「停手单位」是一次 unlink 而不是一整趟编码。
2. **档串作为身份的一部分**：`meta.encoder != ENCODER_DESC` 即不采纳。这条同时承担
   「旧档不能顶替」与「v4 未定档前不得悄悄混入」两件事——挂起 v4 时档串保持不变，
   故挂起期间的产物与「反解 → 收色 → 微缩」完全相同，不需要第二套闸门。
3. **收色（低 alpha 亮色邻居）**：v3 修的是「半透明像素反解后仍发白」——按最近的不透明
   邻居颜色接管 Cb/Cr、保留亮度，避免白晕在 Q70 下被量化为灰边。

## 四、性能分析

**方法（可复现，本节全部数字由本次补报告时现场重测或从磁盘元数据直接计算）**

```bash
# ① 素材世代清点与编码档分布（逐目录读 meta.json + 累加 *.webp 字节）
cd D:/dsh-pet-src && .venv/Scripts/python.exe -c "<rglob '*.g<hex>' + meta.json encoder + 字节累加>"
# ② 打包产物大小与时间
ls -la D:/dsh-pet-src/dist-onedir/            # dsh-pet-standalone-webm-chat-portable.zip
ls -la D:/dsh-pet/dsh-pet-standalone-webm-chat.exe
# ③ 部署树内的素材是否就是 v3（同一段脚本跑 D:/dsh-pet/_internal/assets/...）
```

环境：Windows / `.venv` Python 3.13.7 / PySide6；素材 `assets/characters/shenshen`（106 段源 webm）。

| 指标 | 实测 | 归属 |
|---|---|---|
| 帧序列世代目录（重出后） | **106** 个，encoder 全部 = `... unblend-white-v3` | 磁盘 |
| 帧序列总字节（重出后） | **379.1 MB** / 25,423 帧 | 磁盘 |
| 帧序列总字节（v3 之前） | **573.3 MB**（11 段无损 147.8MB + 95 段 Q80 425.5MB）——实测自 v3 之前的部署包 `D:/dsh-pet-backup-20260929`（同相对位置、同 106 段） | 磁盘 |
| 变化 | **−194.2 MB / −33.9%** | 磁盘 |
| 便携包 zip | **750,757,441 B = 716.0 MiB**（`dist-onedir/`，mtime 09-29 16:06） | 分发 |
| 部署包 exe | 24,582,709 B，mtime 09-29 **15:52**（晚于素材重出完成 15:33） | 分发 |
| 部署树内素材 | `D:/dsh-pet/_internal/assets/.../frameseq` = 106 个世代全 v3、**379.1 MB** | 实机安装 |
| 逐帧转换成本 | `geq` 41ms/帧、Python 逐帧约为其 1.6x（≈66ms/帧）——模块 docstring 记录的实测口径 | 一次性后台供给 |

**结论（逐条回答模板四问）**

1. **稳态开销**：播放路径一点没变——帧序列播放仍走 `FrameSeqClip` + 同一张帧表，
   本批只改**编码档与磁盘上的字节**；`PET_FRAMESEQ=0` 的回退路径同样未变。
   **没有在 v3 之后重跑流畅度实测**（见下条）。
2. **新增路径的绝对成本与触发频率**：新增成本全部在**首跑供给**这一条一次性路径上：
   转换改为「ffmpeg 一趟 + Pillow 逐帧」，帧数 25,423，按上表 ~66ms/帧外推 ≈28 分钟
   （**外推，非本批实测**）；转换在低优先级后台跑，磁盘准入 `free ≥ max(1GiB, 源×20)`。
3. **有无新的系统调用 / 网络 / 磁盘 / 线程**：无网络；无新增常驻线程（沿用既有供给
   worker）；磁盘侧是「写一份新世代 + 删旧世代」，条数与总字节**下降**。
4. **内存与缓存**：meta 读法未变（不读帧内容）；世代目录数从「三代并存」收敛为
   「一代 + 11 个不采纳的旧无戳目录」，缓存侧无新增长寿命结构。

**已知的实测空白（诚实登记）**：流畅度那组数字（`.scratch/overnight-20260929/fluency-run2-frameseq.json`：
tick 最大 76.1ms、>250ms 动画断帧 0 次、剔除 py-spy 采样窗口后 12 分钟内 >100ms 停顿 0 次）
采集于 **09-29 00:41**，**早于**本次 v3 重出（14:17–15:33），因此它证明的是「帧序列管线」
的流畅度，**不能当作 v3 的实测**。v3 只换编码档，属同路径换字节，但**按纪律不写成 v3 已验**。

**与交接文档的口径差异（双来源冲突，按 AGENTS §7 摆出来）**：`.scratch/HANDOFF-20260929.md:11`
记「106 段全量重出（721→379MB）；便携包 908→716MB」。其中 **379MB 与 716MB 与本次实测吻合**；
**721MB 与 908MB 未能复测**——本机现存的两棵可比树（`D:/dsh-pet-backup-20260929`、
`D:/dsh-pet-prev-v2`，均为 v3 之前的包）实测帧序列为 **573.3 MB**，旧 zip 已被 09-29 16:06 的
新 zip 覆盖。因此本报告以 **573.3 → 379.1 MB** 为准，721/908 仅作交接记录引用，**不作证据**。

## 五、实机运行记录

**本机真实环境（不是 CI、不是 mock）**：

1. **部署包内的素材就是 v3（本人现场核验）**
   命令：读 `D:/dsh-pet/_internal/assets/characters/shenshen/frameseq` 下所有 `.g<hex>` 目录的
   `meta.json` 与 `*.webp` 字节。输出：`deployed stamped gens: 106 {'libwebp lossy q70 (bgra straight, unblend-white-v3)': 106} 379.1 MB`。
   —— 这是「重出的素材真的随包发布到实机」的直接证据（不是只看源仓库）。
2. **部署的进程活着且是这一版**
   `tasklist`：`dsh-pet-standalone-webm-chat.exe  39276  Console  1  193,396 K`；
   `Get-CimInstance Win32_Process`：`ProcessId=39276　CreationDate=2026/9/29 16:06:51　CommandLine=D:\dsh-pet\dsh-pet-standalone-webm-chat.exe  --slot 0`。
   部署包 exe 的 mtime 是 **15:52**、便携包 zip 是 **16:06**，进程创建于 **16:06:51**——
   时间序上「素材重出（15:33）→ 打包（15:52/16:06）→ 启动（16:06:51）」闭合。
   **边界（不许外推）**：PyInstaller 把 `pet/**` 编进 PYZ，包内无 `.pyc` 可直接比对，
   故「部署包里跑的 `frameseq_provision.py` 是哪一版」**只经时间序推断，未做字节级验证**。
3. **用户可见行为的确认（用户实测，非自动）**：`.scratch/HANDOFF-20260929.md:11` 记录
   「**用户实机验收通过（"很不赖"）**」——即用户在部署版上目视接受了统一档位的画质。
   主观画质无法自动化，这条就是它的证据形式；**本补报告未重新征集用户意见**。
4. **本该失败 / 本该挂起的路径**：v4 镂空还原**默认挂起**（`HOLE_RESTORE_ENABLED = False`）。
   实机观测：开启后**误切白色鲸鳍**（残留灰白块与白色艺术品在该判据的形状特征上同构），
   故直通、零开销。用户确认过的真实残留位置：`idle/f_0001` 画布 239-242 × 236-240，灰白微蓝
   (176,201,216)，被发卷四面包死。
5. **无法自动验证的能力**：① 主观画质（Q70 + 反解边缘、发丝边缘）——只能人眼；
   ② 屏幕上真实呈现（GPU/present）；③ macOS/Linux 全未验证；
   ④ 重出素材的**一次性**转换过程在别人机器上的观感（转完前的回退仍走 WebM）。

## 六、测试与验证

| 门 | 命令 | 结果 | 出处 |
|---|---|---|---|
| 帧序列聚焦（**本次补报告现场复跑**，2026-09-29 晚间） | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_frameseq_unblend.py tests/test_frameseq_unblend_v3.py tests/test_frameseq_unblend_v4.py tests/test_frameseq_provision.py tests/test_frameseq_clip.py` | **179 passed in 27.87s（rc=0）** | 本次 |
| 全量（本批之前最后一次记录） | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **3942 passed / 11 skipped / rc=0**（541.7s，`full-suite-20260928-b`） | `.scratch/windows-parity-20260926-a/full-suite-20260928-b/` |
| 全量（含 09-29 全部批次，交接记录） | 同上 | **4158 passed**（`.scratch/HANDOFF-20260929.md:7`）；**2026-10-01 已复跑：4187 passed / 0 failed** | 交接记录，**本次未复跑** |
| ruff | `.venv/Scripts/python.exe -m ruff check --no-cache pet tests tools` | 交接记录「必过」；本批证据见各批报告 | 交接记录 |
| 交付证据纪律 | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_pr_report_discipline.py -q` | **55 passed in 1.16s**（补报告前基线 43 passed；+6 份新报告 × 2 条参数化用例） | 本次 |

## 七、已知限制与后续

- **v4 镂空还原挂起中**：等用户给出精确残留坐标后重标定再开启；在档串不变的前提下
  开启它不会让已有 v3 世代失效（挂起期间产物与 v3 主链逐位相同）。
- **旧无戳 11 个热集目录不回收**：升级后旧版无戳帧集不会被自动删（可能被旧实例读取），
  需人工删除或重新打包——**已知残留**，不是遗漏。
- **绿幕支线（`VID_584` 吃手指 / `VID_587` 收蛋糕礼物）尚未入库**：抠图管线（BiRefNet +
  despill + 色度迁移 + 空洞切除）跑在 `.scratch/greenscreen-pipeline/`，成品未进
  `assets/`，因此**不在本批交付范围内**；其判据演化与教训见
  `.scratch/HANDOFF-20260929.md` 的绿幕各节。
- **W3 身体框裁剪**（体积再砍一半的主力）尚未立项。
- **依赖下限补充说明**（2026-10-01 二轮审查补记）：`requirements.txt` 的
  `Pillow>=10` 在本批改为 `Pillow>=10.3`——阶段二反解链路使用
  `ImageMath.lambda_eval`（`pet/frameseq_provision.py` 懒载点），该 API 在
  Pillow 10.3 之前的形态不可用；旧 Pillow 环境下本批按「不产出」失败收口
  （宁可不产出不出错），不会半残运行。
  **最低版本依据与验证（2026-10-01 补）**：
  下限 10.3 的依据 = **该 API 在 Pillow 10.3 发布说明中新增**（`lambda_eval`）。
  10.3 无 cp313 wheel（PyPI 实查 0 个；**10.4.0 起有正式 cp313 wheel**
  ——Python 3.13 上可安装的最老版本）——故本机（Python 3.13）**10.3 无法
  安装、未能实跑**（此为其自身限制，如实登记）。旁证阶梯已闭合：
  **10.4.0 与 12.3.0 实跑 `unblend_rgba`+`luma_band`（真实生产帧 640×360）
  逐字节一致**（sha256 双函数同值），11.0.0 复测同值——`10.3（索引证明）
  → 10.4（实测一致）→ 11.0（复测一致）→ 12.3（生产）`；整数域运算链
  对老版本 Pillow 语义稳定（≤3.12 用户按 10.3 下限安装时同样成立）。

## 八、风险与回滚

- **风险面**：只影响帧序列供给与素材字节；播放/回退路径、配置键、事件与线程模型均未动。
- **回滚**：① 代码回滚即可（无配置迁移、无新增键）；② 素材回滚需要恢复旧世代或用
  `tools/convert_frameseq.py --force` 按旧档重转——注意**档串必须在 meta 里一起回退**，
  否则采纳闸门会把新旧产物都当成「档不符」而全部回退 WebM（表现为「素材突然变慢」，
  而不是「播错素材」）。
- **不变量**：改档后**任何**旧世代都不会被采纳（失败模式是回退 WebM，不是播错帧）。
