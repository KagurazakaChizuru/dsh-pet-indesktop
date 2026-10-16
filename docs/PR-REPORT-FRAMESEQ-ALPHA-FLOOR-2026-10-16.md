# 帧序列 alpha 底板清理（`unblend-white-v5`，2026-10-16）

> **基线**：`b7a697f`（`origin/main`，含 #288 每屏一窗多屏）
> **分支**：`fix/frameseq-faint-alpha`（worktree `D:/dsh-pet-wt-alpha-floor`）　**日期**：2026-10-16
> **范围**：9 个文件（实现 1、构建门 1、测试 3 + 新增 1、文档/登记 2 + 新增报告 1）。
> 实现 + 测试 + 登记的合计 = **+465 / −69**（不含本报告自身——它的行数随修订变化，
> 自指没法对账）；逐文件增删见 §二，精确值以 `git show --numstat` 为准：
> **本地已提交，未构建、未部署、未 tag/release**；分支与 PR 状态以 PR 页为准（不写进本报告）
> **本报告的提交 SHA**：本报告在实现/测试提交之后的独立文档提交里（不自指 SHA——写进去
> 会被任何一次 amend/变基作废）；取自 `git log --oneline`。
> **关联**：[`PR-REPORT-FRAMESEQ-V3-PIPELINE-2026-09-29.md`](PR-REPORT-FRAMESEQ-V3-PIPELINE-2026-09-29.md)（被本报告取代档位口径）

## 一、核心特性

用户反馈：桌宠**整个矩形**在白色区域里显出一块浅灰（"白底整块色差"），不是只有拖动时才
出现。根因（本机实测，非推断）：抠图把整块背景留成了 `a = 1`。

| 证据 | 实测值（本机，源 `assets/characters/shenshen/videos/`） |
|---|---|
| 源 webm 首帧 `a == 1` 占比 | idle 82.02% / drag 82.14% / move 81.74%（`a == 0` 只有 0.5%） |
| 现有 v3 产物同帧 `a == 1` 占比 | 81.62% / 81.81% / 81.42%（磁盘上既有的世代目录，`encoder=…unblend-white-v3`） |
| 角落像素（底板） | `(0,0,0,1)` → 叠在白底上 **254**（纯背景 255） |
| 处置后 | `(0,0,0,0)`；`a == 1` 占比 **0.0000** → 白底 **255** |

`a = 1` 叠在任何背景上都是 `dst × 254/255`：白底 255 → **254**，整块矩形比背景暗一档
（其它底色按比例各自压暗一档，深灰底因取整看不出来）。`erode_alpha` 够不到它——它不在
轮廓的 1px 环上，而是**铺满整个底板**，邻域全是 1，3×3 最小值滤波对它恒等。

**改法**（一行接线 + 两个纯函数）：档链尾加一步 `floor_faint_alpha`——把 **恰好等于 1**
的 alpha 清成 0、这些像素的 RGB 一并置 0；`a = 0` 原样、`a >= 2` 一个位不动。档位串与
meta 标记换成 `unblend-white-v5`（`white-v5`），v3 与更早的世代按既有迁移机制自动不采纳、
后台/构建期按新档重出。

**红线 / 不变量**：

- **只改 `a == 1`**：判据是相等而不是"≤ 某阈值"（`a = 0` 本来就透明，`a >= 2` 承载真实的
  半透明过渡：发丝、AA 边）；
- **不改 q70、不加大 erode、不开 v4、不泛删毛发**：编码参数一字未动，`UNBLEND_ERODE_PX`
  仍是 1，`HOLE_RESTORE_ENABLED` 仍是 `False`（挂起）；
- **源身份不变**：世代目录名仍 = 源 webm 的 sha256 前 12 位，meta 仍写全量 `source_sha256`
  ——改档靠 encoder 串失效，**不伪造源戳**；
- 供给链/构建门/缓存 key 同步：档串出现在运行时采纳闸门、构建硬门与 CI 缓存 key 三处，
  全部跟着换（§五）；
- 帧数契约、原子发布、退避、预算、退役清扫等既有语义一字未动。

## 二、修改文件说明

`git diff --numstat`（本地提交；**本报告不写自身提交的 SHA**——写进去就会被任何一次
amend/变基作废，实际 SHA 由 `git log -1 --format=%H` 取）：

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/frameseq_provision.py` | +134 / −50 | ① 新增 `FAINT_ALPHA = 1`、`faint_alpha_mask`（判据：`a` 恰好等于 1）、`floor_faint_alpha`（清 alpha + 归零 RGB，无 `a==1` 时**原对象返回**）；② `unblend_v3` 的返回链尾接上这一步（`floor_faint_alpha(erode_alpha(restore_hair_holes(rectified)))`）；③ `ENCODER_DESC` → `…unblend-white-v5`、`UNBLEND_MARK` → `white-v5`，并把旧 v3 串登记进 `LEGACY_ENCODER_DESCS`（只作历史识别）；④ 模块/函数文档同步（管线步骤、档号为何跳过 v4、微缩前/后等价证明、实测耗时）。**非文档的净代码约 55 行**，其中 40 行是新函数本体。 |
| `scripts/check_frameseq_bundle.py` | +6 / −6 | 构建门内镜像的世代常量（`ENCODER_DESC` / `UNBLEND_MARK`）与源码行号注释同步。门不改判据——它本来就只比对档串，改的是它认的那一档。 |
| `tests/test_frameseq_provision.py` | +48 / −6 | ① 冻结串用例改判 v5（含 `LEGACY_ENCODER_DESCS` 新增 v3、`FAINT_ALPHA == 1`、`HOLE_RESTORE_ENABLED is False`）；② 新增库级回归 `test_library_rejects_v3_generation_and_adopts_v5`：磁盘上的 v3 世代不被 `MovieLibrary` 采纳（回退 WebM）、进 `plan_clips` 待转清单，同一路径换成新档 meta 后 `rescan_frameseq` 采纳、待转清单清空。 |
| `tests/test_frameseq_unblend_v4.py` | +10 / −6 | 挂起语义的参考实现跟着当前档走：`_v3_without_holes` → `_chain_without_holes`（链尾补 `floor_faint_alpha`）并更新注释——挂起语义要证的仍是"少了镂空这一步，逐位相同"，只是"相同"的基准档已经是 v5。 |
| `tests/test_frameseq_bundle_gate.py` | +17 / −0 | 新增 `test_superseded_v3_generation_fails`：**刚被取代的 v3 产物在构建期同样判陈旧**（磁盘上现存的素材正是这一档），并要求该串登记在 provision 的 LEGACY 清单里。 |
| `tests/test_frameseq_alpha_floor.py` | 新增 +240 | v5 单测 + 真实素材回归（§六）。 |

### 文档与登记

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `AGENTS.md` | +8 / −0 | 「Context pointers」加一条：改帧序列编码档/反解链（`ENCODER_DESC`/`unblend_v3`/`floor_faint_alpha`）或构建门档串时读本报告；写明当前档是 v5、v4 不是档。 |
| `docs/INDEX.md` | +2 / −1 | PR 报告存档新增本报告一行（档位变更的现行口径），并在 v3 报告那一行的「何时必读」补一句指向本报告（否则读者会以为 v3 仍是当前档）。 |
| `docs/PR-REPORT-FRAMESEQ-ALPHA-FLOOR-2026-10-16.md` | 新增（本文） | 本报告（`tests/test_pr_report_discipline.py` 强制校验的三节 + 索引登记均已满足）。 |

### 未改动（明确写出来，避免评审以为漏了）

- `tools/convert_frameseq.py`：只转发到核心实现，档串不落在这个文件；它的模块文档里还
  留着"热集无损 / 冷集 `-quality 80`（`ENCODER_DESC_LOSSY`）"这段**改档前的历史描述**
  （该常量在本仓已不存在）——属**既有文档债**，与本次改动无关，本批不动它（登记在 §七）。
- `docs/ONEDIR_PACKAGING.md`：帧序列缓存 key 的构成写的是"源 webm 摘要 + 转换器/供给实现
  摘要 + 当前编码档 + 平台/Python/Pillow/imageio-ffmpeg 版本"，没有硬编码档串 → 无需改。
- `.github/workflows/build-{windows,macos,linux}.yml`：缓存 key 由
  `scripts/prepare_frameseq_bundle.py --print-cache-key` 现算，workflow 里没有档串 → 无需改。
- `pet/library.py`：它的文档只说"`ENCODER_DESC` = Q70 + 白底反解"，不写版本号 → 无需改。
- 历史 PR 报告（`PR-REPORT-FRAMESEQ-V3-PIPELINE-2026-09-29.md` 等）：是当时的事实记录，
  不回填。

## 三、实现要点

```python
def floor_faint_alpha(im):
    _red, _green, _blue, alpha = im.split()
    faint = faint_alpha_mask(alpha)          # a 恰好等于 1 的掩膜
    if faint.getbbox() is None:
        return im                            # 无 a==1：原对象返回（稳态零成本）
    colors = im.convert("RGB")               # convert 是拷贝（不改入参）
    colors.paste((0, 0, 0), (0, 0), faint)
    return Image.merge("RGBA", (*colors.split(), ImageChops.subtract(alpha, faint)))
```

- **为什么归零像素的 RGB 也置 0（而不是留着或置 255）**：这些像素已经全透明，屏幕上
  看不见任何颜色；但存值要自洽——"`a == 0` 的像素 RGB 必须是 0"是预乘透明的读法，
  置 0 在任何实现里都不会漏色，置 255 会在"把 RGB 直接当颜色用"的实现里漏出一圈白。
  实测这一步对绝大多数像素是**空操作**（底板本来就被源/编码器存成 `(0,0,0,1)`）：
  真素材上 `a == 1` 的像素里 99.0–99.5% 的 RGB 已经是 0，只有微缩环上那 ≈0.5%
  （idle 1355 px）带着非 0 颜色（最大 ≈170），置 0 正是为它们准备的。
- **位置**：`unblend_v3` 的**最后一步**（微缩之后、Q70 编码之前）。与放在微缩之前
  **逐位等价**：清理把 0/1 都映射成 0（`F(0) = F(1) = 0`，其余不变）是单调不增的，
  而微缩取的是 3×3 最小值（`min F(x) = F(min x)`）——单测钉住了这一条。放最后是因为
  它产出的就是发布出去的像素，且 WebP 的 alpha 走**无损位流**（落盘读回仍是 0）。
- **为什么档号是 v5 而不是 v4**：v4 在本仓已经专指"镂空还原"
  （`HOLE_RESTORE_ENABLED` / `HOLE_*` 参数表 / `tests/test_frameseq_unblend_v4.py`），
  而它**从未启用、现在仍挂起**（实机误切白色鲸鳍）。底板清理若也叫 v4 会变成两个 v4；
  叫 v5 = "v3 三步 + 底板清理，v4 不在里面"。**没有任何一份产物是"v4 产物"**。
- **备选方案与否决理由**：① 在 ffmpeg 阶段做（`geq`/`lut`）——阶段一必须无损且要把每一
  帧交给 Pillow，多一次整帧 pass 反而慢，且判据要"恰好等于 1"（`geq` 只能靠真跑验）；
  ② 加一个"地板 alpha"参数到 `erode_alpha`——那会把"清 1"和"啃 1px"两件事混成一个开关，
  违反"只改 `a == 1`、不加大 erode"的红线；③ 改源视频重抠图——超出本刀范围，且源 webm
  是入库素材。

## 四、性能分析

**方法（可复现）**：
`python .scratch/frameseq-alpha-floor/time_floor.py`；环境 Windows / Python 3.13.7 /
Pillow 12.2 / imageio-ffmpeg 7.1；样本 = 源 webm（idle 待机呼吸休闲）第 1 帧，640×360、
`a == 1` 占 82.0%；每项 n=30（`unblend_v3` 两项 n=10，单帧 ≈50ms 量级）。

| 指标 | 实测（中位数 ms/帧） | 归属 |
|---|---|---|
| `floor_faint_alpha`（底板帧：82% 是 `a==1`） | **4.64**（min 4.33 / max 5.56） | 新增 |
| `floor_faint_alpha`（无 `a==1` 的帧） | **1.31**（min 1.24 / max 1.57） | 新增（稳态） |
| `faint_alpha_mask` 单项 | 0.76 | 新增（上两项的主要构成） |
| `unblend_v3`（v5，含清理） | **51.71** | 既有一帧成本 +5.6ms |
| `unblend_v3`（v3，清理替换为直通） | **46.08** | 既有一帧成本 |
| Q70 重编码（`quality=70, method=4`） | 44.58 | 既有 |
| 单帧端到端（阶段二 + 编码） | ≈96ms（v3 为 ≈91ms，**+5.5%**） | 热路径 |

**结论**：

1. **稳态开销**：不变。清扫、采纳闸门、哈希、退避等路径一个字节都没动；新步骤只在阶段二
   逐帧执行，且无 `a==1` 的帧早退（1.31ms 是"扫一遍掩膜"的成本，掩膜本身 0.76ms）。
2. **新增路径的绝对成本与触发频率**：+4.6ms/帧（有底板时），触发频率 = **每一帧**（底板
   就在画面里）；对 25,500 帧的整份素材 ≈ +2 分钟（41 分钟量级里 +5%，**不改变**"几十
   分钟级后台重编码"的量级判断）。
3. **有没有新的系统调用 / 网络 / 磁盘 / 线程**：没有。纯内存 Pillow C 原语（`point` +
   `getbbox` + `paste` + `subtract` + `merge`），无 Python 逐像素循环、无新增派生进程、
   无新增文件。
4. **内存与缓存**：单帧多 1 张 L 掩膜 + 1 张 RGB 拷贝（640×360：230KB + 691KB 峰值），
   随帧释放；无跨帧缓存、无新增常驻结构。
5. **产物体积（附带收益，单帧样本）**：同一帧 Q70 编码 14124 → **13744** B（idle，
   −2.7%）、14436 → 13964（drag，−3.3%）、14566 → 14074（move，−3.4%）——底板变成
   "整块均匀全透明"后编码器省下一点。**注**：这是 3 帧样本，不能直接外推整份素材；
   全量重出后的真实体积与包体变化见 §七「未验」。

## 五、供给链 / 构建门 / 缓存 key（改档的传播面）

| 环节 | 位置 | 现状 |
|---|---|---|
| 运行时采纳闸门 | `pet/frameseq_provision.py::current_generation`（生产者与 `MovieLibrary.rescan_frameseq` 共用同一谓词） | `meta.encoder` 必须等于 `…unblend-white-v5`；v3 及更早一律不采纳 |
| 构建硬门 | `scripts/check_frameseq_bundle.py`（被 `build_onedir.ps1` / `build_macos.sh` / `build_linux.sh` 在 PyInstaller 前调用） | 镜像常量已同步到 v5（同一份判据），v3 素材判陈旧 ⇒ 拒绝出包 |
| CI 缓存 key | `scripts/prepare_frameseq_bundle.py::cache_key` = `schema + 源摘要 + 转换器摘要 + 档位 + 平台/依赖` | 实测**两个分量各自变化**：档位分量 `…white-v3|white-v3` → `…white-v5|white-v5`；转换器摘要覆盖 `pet/frameseq_provision.py` 的内容 ⇒ 也变。key：`frameseq-win32-amd64-0eefdac0…` → `frameseq-win32-amd64-43409415…`。**源摘要不变**（源 webm 未动） |
| 同源守卫 | `tests/test_frameseq_bundle_gate.py::TestGenerationHomology` | 门内常量必须逐字等于 provision 的常量（改档漏同步即红）——本次已同步并通过 |
| CI workflow | `.github/workflows/build-*.yml` | 无硬编码档串（key 现算）⇒ 无需改动 |

## 六、测试与验证

### 6.1 先红后绿

| 阶段 | 命令 | 结果 |
|---|---|---|
| 红（实现前） | `python -m pytest -q tests/test_frameseq_alpha_floor.py` | **7 failed**（`AttributeError: module … has no attribute 'floor_faint_alpha'`）×3 + 梯度/管线 4 条 |
| 绿（实现后） | 同上 | **7 passed** |
| 既有族回归修正 | `python -m pytest -q tests/test_frameseq_unblend_v4.py` | 先 **1 failed**（挂起语义的参考链未含新步骤，正是"改档必须显式跟"的证据）→ 改参考链后 passed |

新增 `tests/test_frameseq_alpha_floor.py`（240 行）覆盖：

1. **梯度 0/1/2/3/255 + 全 256 档**：掩膜只命中 1；产物 alpha `[0,0,2,3,255]`；
   归零像素 RGB = `(0,0,0)`（**不是 255**）；其余像素逐位不动；入参不被修改；
   无 `a==1` 的帧**返回原对象**；非 RGBA 输入当场 `ValueError`。
2. **管线末段位置**：`unblend_v3` 产物里 `a==1` 计数为 0；与"把 `floor_faint_alpha` 换成
   直通"的同一管线逐像素对账——`a>=2` 的像素 alpha 与 RGB **逐位相同**、`a==1` 的像素
   alpha 归零且 RGB 归零、没有任何像素 alpha 被抬高。含**反空过自证**
   （改动前确实存在 `a==1` 的像素，断言能区分）。
3. **真实素材单帧（idle / drag / move 各一帧，参数化 3 例）**：真 ffmpeg（产品同一份
   `imageio_ffmpeg` exe + 同一组阶段一参数）抓源 webm 第 1 帧 → 真 `unblend_frames_in_place`
   原地 Q70 落盘 → 读回解码后断言：
   - 前提：源帧与"改动前产物"的 `a==1` 占比都 > 50%（实测 82%）；
   - 新产物 `a==1` 计数 **0**（WebP alpha 无损位流 ⇒ 落盘读回仍是 0）；
   - 角落像素 alpha **1 → 0**，白底合成 **254 → 255**（整数合成，逐像素精确）；
   - `a>=2` 的像素 alpha 逐位不变、无像素 alpha 被抬高；
   - 管线末段：`a>=2` 的像素 RGBA 逐位不变；
   - **编码损失另算**（不冒充逐位相同）：可见像素上有损 RGB 与阶段二输出的偏差
     `(max, mean)` 不许比改动前差一个量级以上（本机 idle：new 53 / 4.5 对 base 201 / 6.2）。

### 6.2 门

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts tools` | **All checks passed** |
| 聚焦（新） | `pytest -q tests/test_frameseq_alpha_floor.py` | 7 passed |
| 相关族（帧序列全家） | `pytest -q tests/test_frameseq_{provision,bundle_gate,clip,unblend,unblend_v3,unblend_v4,alpha_floor}.py tests/test_convert_frameseq.py` | **261 passed / 1 skipped**，skip = `test_frameseq_bundle_gate.py::TestPrepareRealMaterial`「本机素材树不完整（干净检出的 CI 必然如此）」——本 worktree 没有 frameseq 派生物（不入库），且主工作树的 v3 素材**按新档判正是"陈旧"**，这条跳过是改档的预期结果 |
| 线程族高负载复跑（3 遍） | `pytest -q tests/test_frameseq_provision.py` ×3 | **110 passed** ×3（14.80s / 16.04s / 14.49s，负载下不抖；本改动不碰线程/时序，复跑是保险） |
| 全量 | `python -m pytest -q`（本机，**本刀自身树上跑一次**：`origin/main` `b7a697f` + 本刀提交，**不是与其它分支组合后的树**；日志 `.scratch/frameseq-alpha-floor/full-suite.log`） | **7911 passed / 15 skipped / 0 failed**（`1388.81s` = 0:23:08，`EXIT=0`；无 FAILED/ERROR 行）。本刀新增的 9 条用例（底板 7 + 库级改档 1 + 构建门 1）已含在内。**组合口径另算**：交付前本分支已合入 `origin/main`（含歌词 #291），合并后全树相对 `origin/main` 只多本报告的 9 个文件（其余逐字节相同），故组合树的全量**交 PR #292 的 CI 三端跑**，本机不重复跑；合并后的相关族另在本机复跑（见下行） |
| 合并后相关族复跑（本机） | `pytest -q tests/test_frameseq_{provision,bundle_gate,clip,unblend,unblend_v3,unblend_v4,alpha_floor}.py tests/test_convert_frameseq.py` 与 `tests/test_music_lyric.py tests/test_pr_report_discipline.py`；`ruff check pet tests scripts tools` | 合入 `origin/main`（`056dc2a`，含 #291）后：帧序列族 **261 passed / 1 skipped**（与合并前逐条相同）、歌词族 + 报告纪律 **319 passed**、ruff 全绿 |
| 断言有效性 | ① 撤掉实现（`floor_faint_alpha` 不存在）② 把它替换为直通（`unblend_v3` 链尾不再清理） | ① **7 failed**（AttributeError ×3 + 梯度/管线 4 条）；② **4 failed / 3 passed**（`a==1` 得 187602 而非 0、角落与管线对账同时红）——断言确实能区分新旧实现 |

## 七、实机运行记录

**本机真实环境**（Windows / Python 3.13.7 / Pillow 12.2 / imageio-ffmpeg 7.1，仓库内
真素材 106 段 webm），**未部署、未联网、未改动用户运行时目录**。

### 7.1 根因现场复现 + 改动前后对照（既有素材，非重转）

命令：`python .scratch/frameseq-alpha-floor/probe_alpha_floor.py`
（对 idle/drag/move 各取源 webm 第 1 帧；`--v3-root` 指向主工作树磁盘上**既有的 v3 世代
产物**做交叉核对；对照图与 `probe.json` 落 `.scratch/frameseq-alpha-floor/out/`）

```
idle: baseline a1=0.8162 corner=(0,0,0,1) → new a1=0.0000 corner=(0,0,0,0) | bytes 14124→13744
drag: baseline a1=0.8181 corner=(0,0,0,1) → new a1=0.0000 corner=(0,0,0,0) | bytes 14436→13964
move: baseline a1=0.8142 corner=(0,0,0,1) → new a1=0.0000 corner=(0,0,0,0) | bytes 14566→14074
磁盘 v3 世代 …gdeb965d05a85: a1=0.8162 corner=(0,0,0,1) encoder='libwebp lossy q70 (bgra straight, unblend-white-v3)'
磁盘 v3 世代 …g31373a860266: a1=0.8181 corner=(0,0,0,1) encoder='…unblend-white-v3'
磁盘 v3 世代 …g79882aedd7b7: a1=0.8142 corner=(0,0,0,1) encoder='…unblend-white-v3'
```

- 三段的 `a>=2` 像素 alpha 在编码→解码后**逐位相同**（`alpha_ge2_bitexact=True`），
  可见像素 RGB 的差异只来自有损重编码（`rgb_ge2_max_delta` 36–39，与改动前同机同编码器
  的自身误差带 36–41 同量级）。
- **对照图（ReadMediaFile 读回目视确认）**：`out/deviation_idle_white_x64.png`、
  `out/deviation_move_white_x64_vs_disk.png` —— 把"与纯白背景的偏离 ×64"并列：左（改动前
  / 磁盘磁盘现有 v3 产物）整个矩形是一片均匀灰（1/255 的整块色差，肉眼在原尺寸下只能靠
  大片色块边界察觉），右（新档）全黑 = 与背景**零偏离**，角色轮廓未变。`corner_*_white.png`
  维持原尺寸观感（1 档差异在此不可见，故另出 ×64 版本）。

### 7.2 供给链传播面（实测）

```
source_digest 相同: True
grade 新: …unblend-white-v5|white-v5  | grade 旧: …unblend-white-v3|white-v3
key 新: frameseq-win32-amd64-434094154849e69aeb335eed47a46b6b
key 旧: frameseq-win32-amd64-0eefdac0328ab771da8db392719aeaf3
```
即：**旧缓存不可能被新语义复用**，而源摘要（源身份）没有被动过。

### 7.3 边界与失败路径

- **无 `a==1` 的帧**：`test_floor_is_object_identity_when_nothing_faints_and_guards_mode`
  实测返回**原对象**（零开销），不是"新建一张一样的图"。
- **非 RGBA 输入**：当场 `ValueError`（工序契约，不许静默直通）——有用例。
- **全不透明帧**：既有 `test_fully_opaque_frame_is_untouched` 仍绿（清理无命中）。
- **半成品 / 帧数 / 发布**：本刀未碰这些路径，相关既有用例全绿（261 passed / 1 skipped）。

### 7.4 这次**没有**做的事（如实登记）

- **没有全量重转 25,500 帧**：本刀只做"实现 + 隔离 3 帧真素材验证"。磁盘上现存的 v3 世代
  仍未被替换（运行时会按启动预算逐 clip 重出，构建期由 CI 缓存 key 变化触发全量重出）。
  ⇒ **未验**：全量重出后的实际体积/包体大小、三端 CI 的 41 分钟级重转、真实部署包效果。
- **没有部署、没有构建**：本刀止于"本地提交 + 隔离 3 帧真素材验证"。分支**未部署、未构建、
  未 tag/release**；push 与开 PR 是本分支的交付步骤（PR 状态以 PR 页为准，不写进本报告）。
- **没有在真实桌面上看桌宠**：本机无 CU、按指令不动真实 APPDATA；用户可见行为的证据止于
  "合成到纯白底 254 → 255 + ×64 对照图"，**真机观感由用户验收**。
- `tools/convert_frameseq.py` 模块文档里的历史档位描述（`ENCODER_DESC_LOSSY`）是**既有
  文档债**，本批不动。
- 全量测试结果：**7911 passed / 15 skipped / 0 failed**（0:23:08，`EXIT=0`；日志
  `.scratch/frameseq-alpha-floor/full-suite.log`，未入库）——本次改动只有全量套件能证明
  "没有波及其它域"。参照：同仓近期全量口径 7840–7924 passed / 15 skipped（基线不同，
  不做逐例对比；本刀贡献 +9 条用例）。

## 八、已知限制与后续

- **v4（镂空还原）仍挂起**：本刀不含它，也没有打开它；开启需要用户给出**精确的残留位置**
  后重标定（现有判据在"发色包围的灰白实心块"这一步与白色鲸鳍同构）。
- **底板清理只认 1**：若别处（例如新素材）出现"整块 `a = 2`/`a = 3`"的底板，本刀不处理
  ——判据刻意写死为相等，宁可漏切也不动真实的半透明过渡。
- 旧 v3 世代目录**不会被本刀删除**：它们仍在磁盘上，等重出后按既有退役机制（打标记 + 满
  宽限 + 非当前 + 非在用）回收；升级期内磁盘可能双份（既有契约）。
- 迁移是**按启动预算**分批的（每个启动周期 1 个有等价旧产物的 clip），所以运行时会先回退
  WebM 播放、后台慢慢按新档重出——这是既有迁移路径，不是本刀新增的行为。

## 九、风险与回滚

- **影响面**：帧序列产物（`assets/characters/*/frameseq/`，不入库的派生物）+ 三端构建期
  重转 + 缓存 key。配置、设置页、schema 一律未动（**没有新增任何持久化键**）。
- **风险**：① 重出期间素材版本混用？不会——采纳闸门按 encoder 串，旧档产物一律不采纳；
  ② 半透明边缘被误伤？判据只命中 `a == 1`，且真实素材上 `a>=2` 的像素 alpha 逐位相同
  （单测 + 3 帧实测）；③ 体积/耗时退化？实测 −3% 体积、+5.5% 单帧耗时（同量级）。
- **回滚**：`git revert` 本提交即可（无落盘副作用、无配置迁移、无残留状态）；回滚后
  `ENCODER_DESC` 回到 v3，已重出的 v5 产物会因档位不符**不被采纳**并回退 WebM 播放，
  后台按 v3 重出——两个方向都只走既有迁移机制，不需要手工清理任何目录。

---

### HEAD / diff 摘要

- 分支基线 `b7a697f`（`origin/main`）；工作树 `D:/dsh-pet-wt-alpha-floor`（独占）
- 本报告描述的是**本地提交**，其 HEAD 与 `git diff --numstat` 见提交记录 / 本报告 §二
- 未部署、未构建；全量测试日志：`.scratch/frameseq-alpha-floor/full-suite.log`（本地、
  未入库）
