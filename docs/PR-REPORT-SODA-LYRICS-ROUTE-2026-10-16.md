# 汽水音乐「歌词不显示」：歌词请求的有界路线回退（2026-10-16）

> **基线**：`b7a697f`（Merge PR #288，`origin/main`）
> **分支**：`fix/soda-lyrics-route`　**日期**：2026-10-16
> **范围**：6 个文件（实现 1、测试 1、文档 3 改动 + 本报告为新增）；改动合计 `+649 / −64`（不含本报告，逐文件见 §二）
> **关联**：现场调查报告 [`../.scratch/soda-lyrics/REPORT.md`](../.scratch/soda-lyrics/REPORT.md)
> （本机只读取证，未改产品）；代理口径文档
> [`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md)（本次已同步 §一/§二/§四 并追加 §六）；
> 上一次歌词网络改动 [`PR-REPORT-MUSIC-LYRIC-SYSTEM-PROXY-2026-09-22.md`](PR-REPORT-MUSIC-LYRIC-SYSTEM-PROXY-2026-09-22.md)

## 一、核心特性

**解决什么问题**：汽水音乐（SMTC `source_app_user_model_id = 汽水音乐`）在播时气泡只显示
歌名、不显示歌词。取词链本身是好的（会话识别、标题不清洗、查询串原样带出都已被调查报告
证明无遗漏），死的是**网络出口**：该曲（`莫小檀 - 荒(一念间天荒仙灭)`）在网易云曲库与
lrclib 里都没有，**只有 QQ 音乐有**，而本机 QQ 源**直连恒 HTTP 500**，于是三源全灭 →
`0 行` → 气泡常驻标题。同一分钟走系统代理的对照请求**200 并真的取回 36 行**
（调查报告 §4）。

**用户看到什么变化**：直连这条路坏掉、而本机配着系统代理时，歌词链会自动再走一次代理
（**只一次**），于是"只有代理能出网"的机器也能取到词；直连通畅时行为一位不变（不额外发
请求、不碰代理）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 直连仍是首选 | 每次请求先走 `ProxyHandler({})` 直连；成功即返回，代理一次都不碰 |
| 2 | 有界回退 | 直连**传输失败**或 **HTTP 500/502/504**，且本机确有系统代理、且预算足够时，**回退一次**系统代理 |
| 3 | 拒绝/限流不换路 | 401/403/404/429/503 是对方的明确答复，不换路也不重试；响应带的 `Retry-After` 写进日志 |
| 4 | 共享预算 | 直连与回退共用 `fetch_lyrics` 的同一份截止预算（`HTTP_TIMEOUT + 1.0`），一次请求不会变成 2 倍超时 |
| 5 | 日志脱敏 | 路线日志只写"直连 / 系统代理"，**不回显代理地址与凭据**（旧实现会打印代理 URL） |
| 6 | 失败优雅 | 两路都失败 → 返回 `None` + 一条 WARNING（两条路各自的异常类型都在里面），取词整体语义不变 |

**红线 / 不变量**（本改动不允许破坏）：

- 直连 opener 仍是 `ProxyHandler({})`（`test_lyric_request_bypasses_system_proxy` 保持绿），
  且超时仍是 `HTTP_TIMEOUT`（同一用例断言）；
- 直连成功时**恰好一次**传输尝试、代理零接触；
- `fetch_lyrics` 的用户可见延迟上限不变（≤ `HTTP_TIMEOUT + 1.0` = 9s）；
- 不新增线程 / 后台服务 / 配置键；不改其它任何 HTTP 调用的出口策略；
- 失败原因仍落在 INFO 可见级别（WARNING），不静默吞掉。

## 二、修改文件说明

`git diff --numstat`：

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/music_lyric.py` | +213 / −42 | 见下（逐函数） |

逐项（都在 `pet/music_lyric.py`）：

| 位置 | 改动 |
|---|---|
| 模块 docstring「网络边界」 | 「一律直连」→「首选直连，直连坏掉时回退一次系统代理」，补上 2026-10-16 的反向证据与本报告链接 |
| `_route_logged`（原 `_proxy_bypass_logged`） | 语义从"绕过代理已记一行"改为"路线策略已记一行"，故改名 |
| `_FALLBACK_STATUSES = {500, 502, 504}`（新） | 允许换路的 HTTP 状态白名单；其余状态一律不换路 |
| `_MIN_ATTEMPT_BUDGET = 0.25`（新） | 一次尝试的最小剩余预算；低于它就**不发**那次请求（注定来不及的那发只会白占连接） |
| `_build_opener()` docstring | 明说它是"首选路线"而不是唯一路线；行为未变（仍是 `ProxyHandler({})`） |
| `_system_proxies()`（新） | 读系统代理配置，`{}` = 没配（也就没有第二条路）。返回值可能含凭据，**只在本模块内部用，不进日志** |
| `_note_route_once()`（原 `_note_proxy_bypass_once`） | 每个进程一行 INFO 说明路线策略；**删掉原来打印的代理 URL**（脱敏） |
| `_open_via_system_proxy()`（新） | 回退路线：`ProxyHandler(proxies)`（**显式**用刚读到的配置，避免第二次读注册表，也便于断言） |
| `_may_switch_to_proxy(exc)`（新） | 判据函数：`HTTPError` 仅 500/502/504 换路；其余异常必须是传输类（`OSError` 家族 —— `URLError`/`TimeoutError`/连接重置都在内 —— 以及协议层的 `http.client.HTTPException`） |
| `_retry_after_seconds(exc)`（新） | 解析限流响应的 `Retry-After`（整数秒）供日志使用；**该响应既不换路也不重试** |
| `_attempt_timeout(deadline, now=)`（新） | 把绝对截止时刻换算成本次尝试的超时（`min(HTTP_TIMEOUT, 剩余预算)`），剩余不足返回 `None`；`now` 参数让首次尝试与预算取同一时刻读数（否则首次会拿到 `7.999…`） |
| `_decode_json_body(raw)`（新） | 原来内联在 `_http_get_json` 里的"剥 JSONP + `json.loads`"抽成函数：解析失败**不**触发换路（路线是好的，数据坏了） |
| `_warn_request_failed(url, started, detail)`（新） | 统一失败 WARNING 格式（主机 + 耗时 + 详情），保住原来那条可 grep 的日志形状 |
| `_http_get_json(url, *, referer, deadline=None)` | 主体重写：直连 → （三条件全中才）回退一次 → 解析；新增 `deadline` 参数 |
| `_fetch_from_qq/lrclib/netease` | 各加 `*, deadline=None` 并透传给自己的每次 `_http_get_json`（默认 `None` → 保持"自带一份 `HTTP_TIMEOUT` 预算"的旧口径，直接调用/单测不受影响） |
| `fetch_lyrics` | 把已经是局部变量的 `deadline = time.monotonic() + HTTP_TIMEOUT + 1.0` **提到 submit 之前**并透传给三个源（原来是"算完不用"）；docstring 补预算共享口径 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_music_lyric.py` | +400 / −12 | 新增 20 例（107 → 127 收集数）：路线决策真值表、预算行为、日志脱敏、汽水曲目离线集成；另修一处**既有**用例的真网络泄漏（见下） |

新增用例清单：

| 用例 | 钉住什么 |
|---|---|
| `test_direct_success_is_one_attempt_and_never_touches_proxy` | 直连成功 = 1 次尝试、代理 0 次 |
| `test_no_system_proxy_means_no_fallback` | 没配代理 → 失败就是失败，不凭空造第二次请求 |
| `test_transport_failure_falls_back_to_system_proxy_once` | 传输失败 → 恰好 2 次尝试，且第二次真的走代理 opener |
| `test_gateway_statuses_fall_back_to_system_proxy[500/502/504]` | 500/502/504 且无 `Retry-After` 时允许换路（参数化 3 例） |
| `test_rejection_and_throttle_statuses_do_not_switch_route[401/403/404/429/503]` | 拒绝/不存在/限流不换路（参数化 5 例） |
| `test_throttle_retry_after_is_surfaced_in_log` | 429 的 `Retry-After: 30` 进日志、且仍不换路 |
| `test_both_routes_failing_are_both_reported` | 两路都失败：`None` + 日志里两条异常类型都可辨 |
| `test_fallback_shares_the_deadline_budget_instead_of_doubling` | 回退拿到的是**剩余**预算（3s 用掉后只剩 5s），不是第二份 8s |
| `test_fallback_is_skipped_when_remaining_budget_is_gone` | 剩 0.12s → 不发回退请求，日志说明是预算原因 |
| `test_exhausted_deadline_sends_no_request_at_all` | 截止时刻已过 → 连直连也不发 |
| `test_proxy_address_and_credentials_never_reach_the_log` | 两路失败时日志无代理地址、无凭据 |
| `test_proxy_address_never_reaches_the_route_log` | 回退成功那条 INFO 同样无地址/凭据 |
| `test_system_proxy_route_policy_is_logged_once` | 路线策略每进程一行、带"直连"、不带地址（替换原 `test_bypassing_system_proxy_is_logged_once`） |
| `TestSodaTrackOfflineIntegration::test_qq_direct_500_gets_lyrics_after_proxy_fallback` | **症状回归**：真实 SMTC 元数据（汽水在播曲目）+ 录制响应形态 → 直连 500 时靠回退拿到歌词，且搜索串带真实歌名/歌手、明细请求带录制的真 songmid |
| `TestSodaTrackOfflineIntegration::test_same_track_without_proxy_route_gets_nothing` | 对照：没有代理可回退时这条链就是 0 行（修的就是它） |
| `test_stale_pending_playback_never_leaks_across_songs`（既有用例，补 1 行桩） | 该用例驱动 `_start_track` 却**没桩掉取词线程**，本机真实环境实测它真会往三个歌词源发请求（并等 9s 让进程退出）。补 `_fetch_worker` 无操作桩后，本文件测试期网络请求 **0 次**、文件耗时 13.9s → 2.8s。属既有测试卫生问题，本 PR 顺带收口（否则我的改动会让它在真机上多打一次代理请求） |

### 未改动（看起来相关但故意没动）

| 文件 / 行为 | 为什么不动 |
|---|---|
| `pet/now_playing.py::_play_session_async`（调查报告 G2：`SodaMusic.exe` 匹配不上中文 app_id） | 启动入口「打开汽水音乐并播放」，与"歌词不显示"是**独立问题**，本轮明确不做 |
| `pet/music_lyric.py::_name_matches`（G3：繁简字形） | 字形归一（`時/时`）同样独立；且当时 QQ 端点已不可达，该曲是否受字形影响无法复验 |
| `pet/weather.py` 的 `use_proxy` 分流、`pet/updater.py`、edge-tts 代理 | **不全局改**其它 HTTP 出口；本改动只落在歌词模块内部 |
| 代理绕过表（`proxy_bypass`） | 回退**尊重**系统代理绕过表：若用户把歌词源域名放进绕过名单，回退会退化成第二次直连（不报错，只是没效果）。刻意不改——那是用户的显式配置 |

## 三、实现要点

**路线判据（三条全中才回退，且只回退一次）**

1. 本机确实配了系统代理（`urllib.request.getproxies()` 非空）；
2. 直连这次的失败是**传输失败**或 **HTTP 500/502/504**；
3. 剩余预算够一次尝试（`>= _MIN_ATTEMPT_BUDGET`）。

判据实现只有一处（`_may_switch_to_proxy`），三种源的 5 个请求点全部复用；没有在调用点
各判各的。

**为什么不对 401/403/404/429/503 换路**：这些是**路由无关**的结果（权限、不存在、限流），
换条路重打只会把同一个答复再触发一次——而 `429/503` 正是服务端在请我们**别**再打。
`Retry-After` 的落实形式就是"该响应下既不换路、也不重试，并把服务端给的等待时间写进日志"：
本模块内**不存在**其它重试路径，调用方侧还有既有的同曲 5 分钟冷却
（`MusicLyricController._no_lyric_until`）兜住"立刻再来一次"。

**预算怎么"不翻倍"**：`fetch_lyrics` 里那份 `HTTP_TIMEOUT + 1.0` 的 `deadline` 现在被透传到
每一次 `_http_get_json`；直连与回退的超时都是 `min(HTTP_TIMEOUT, 剩余预算)`，两者**共享**
同一份预算。于是：

- 直连很快失败（现场常见：0.4s 拿到 500）→ 回退还有 ~8s，够用；
- 直连跑满 8s → 回退只剩 ~1s，会先被预算闸拦住（低于 0.25s 直接不发）；
- 单个源内连续两次请求（QQ 搜索 → 明细）也从同一预算里扣，因此**整趟取词**仍受 9s 死线
  兜住——反而比改动前更紧（改动前 QQ 两次请求各自最多 8s、合计最多 16s，只是外层 9s
  到点就丢弃结果，后台线程空转）。

**为什么把截止时刻做成参数而不是新建状态**：三个源在同一条线程池里跑，用模块级/线程局部
变量记"当前取词"会引入隐式状态；显式 `deadline` 参数让"哪次请求花掉了多少预算"在日志与
单测里都可读（`test_fallback_shares_the_deadline_budget_instead_of_doubling` 就是直接断言
两次尝试各自拿到的 timeout）。

**备选方案与取舍**

| 备选 | 为什么没选 |
|---|---|
| 恢复"一律跟随系统代理" | 2026-09-22 的事故反过来：代理会把三源拖到 20~41s（全部超时）。押单一路线就是这次问题的一半 |
| 直连与代理**并发**发，谁先回用谁 | 失败场景下会把每个请求变成两发（并发翻倍、对端压力翻倍），且违背"不任意追加并发"的约束 |
| 按源固定出口（QQ 走代理、其余直连） | 现场证据只覆盖本机此时此刻；换网络/换城市就失效，且等于把"哪条路活"写死进代码 |
| 记住上次成功的路线，下次先用它 | 需要新增跨请求状态（且要处理用户中途开关代理），本轮明确不做配置/状态扩展 |
| 失败后按 `Retry-After` 起定时器重试 | 违背"不新增线程/后台服务"，也让一次取词的行为变得不可预测 |

## 四、性能分析

**方法（可复现，全部本机回环、不联网）**

```bash
# 检出：D:/dsh-pet-wt-soda-lyrics（本 PR） vs D:/dsh-pet-wt-multiscreen（基线 adb6a89）
python .scratch/soda-lyrics-route/bench_route_success.py
MUSIC_LYRIC_REPO=D:/dsh-pet-wt-multiscreen python .scratch/soda-lyrics-route/bench_route_success.py
```

环境：Windows / CPython 3.13.7 / 虚拟环境 `D:/dsh-pet-src/.venv`；
端点：本脚本自起的 `127.0.0.1` HTTP 服务（`/ok` → 200，`/boom` → 500）。

| 指标 | 本 PR | 基线 | 归属 |
|---|---|---|---|
| 直连成功端到端中位（回环，n=30 × 3 轮） | 47.33 / 48.84 / 46.92 ms | 49.03 / 48.05 / 47.44 ms | 热路径（无变化，差异在噪声内） |
| 直连 500 路径端到端中位（回环，n=30 × 3 轮） | 95.75 / 94.46 / 97.29 ms | 47.11 / 46.96 / 47.55 ms | 新增路径（= 多一次往返；仅在"直连失败且配着代理"时发生） |
| `_may_switch_to_proxy` | 0.191 ~ 0.206 µs/次（n=200 000） | n/a | 新增判据（每条失败请求一次） |
| `_retry_after_seconds` | 0.417 µs/次（n=200 000） | n/a | 新增判据（仅 HTTPError 且非白名单状态时） |
| `_attempt_timeout` | 0.236 µs/次（n=200 000） | n/a | 新增（每次尝试一次） |
| `_system_proxies()` 的字典归一 | 0.392 µs/次（n=200 000） | n/a | 新增 |
| `urllib.request.getproxies()` 真实调用 | 103.4 µs/次（n=200） | 104.5 µs/次（n=200） | 既有 OS 边界（基线也有；本 PR 多调的频率见下） |

**逐条回答**：

1. **稳态开销**：直连成功是热路径——它与基线**同量级**（47~49ms 回环），因为新增的判据
   一条都没走（`_system_proxies()` 每个进程只在第一行日志那里调一次，之后 `_route_logged`
   直接返回）；成功路径的额外成本 ≈ 0。失败路径多出的 48ms 是**一次真实的 HTTP 往返**，
   不是计算开销。
2. **新增路径的绝对成本与触发频率**：成本 = 至多一次系统代理请求，且它的超时被压到
   **剩余预算**（≤ `HTTP_TIMEOUT`）。触发频率 = "直连失败（传输失败或 5xx）**且**本机配着
   代理"——现场形态是"每次取词里 QQ 那一条"（调查报告 §3 的 7 次取词 7 次 QQ 500），
   即一次取词最多多 1~2 个请求；不失败就没有任何新增网络。
3. **新增的系统调用 / 网络 / 磁盘 / 线程**：**无新增线程、无新增定时器、无磁盘写入**。
   网络只在上述失败路径 +1 个请求。系统调用方面多出的是 `getproxies()`（读注册表/环境变量，
   实测 103.4 µs/次）：每进程一次（日志行）+ **每条直连失败的请求一次**——相对那条请求
   本身的 8s 级别等待，可忽略。
4. **内存与缓存**：无新增容器/缓存；只多两个模块级常量（`frozenset` 含 3 个 int、一个
   float）与一个布尔标志。线程池、缓存、`_SOURCES` 结构均未变。
5. **最坏延迟**：单个 `_http_get_json` ≤ `HTTP_TIMEOUT`（两路共享预算），整次 `fetch_lyrics`
   仍 ≤ `HTTP_TIMEOUT + 1.0` = 9s，与改动前一致——这正是"不做两次完整超时"的验收点。

> 时序相关无新增：本 PR 没有新增线程、定时器或事件循环，新增用例里的预算场景用**受控时钟**
> （`_LyricClock`）而不是 `sleep`，因此不需要跑"满载 3 遍"的时序族复跑。

## 五、实机运行记录

**环境**：Windows（本机，真桌面会话）；CPython 3.13.7；仓库检出 `D:/dsh-pet-wt-soda-lyrics`
（`fix/soda-lyrics-route`）；基线检出 `D:/dsh-pet-wt-multiscreen`（`adb6a89`，只读导入）。
本节所有命令都在本机真实执行，输出为原始粘贴。

### 5.1 根因前提的现场复现（来自本案调查报告，本轮未重跑真实端点）

调查报告 `.scratch/soda-lyrics/REPORT.md` §3 记录了部署实例自身的日志：

```
22:08:03 WARNING 歌词请求失败 c.y.qq.com（5.35s）: HTTPError: HTTP Error 500
22:08:03 INFO    歌词取词完成: 莫小檀 - 荒(一念间天荒仙灭) -> 0行, 耗时 5.36s   ← 汽水当前会话的曲目
```

§4 的单变量对照（同 URL、同 UA、同分钟）：

```
| 实验 | 直连（产品现行为） | 走系统代理 127.0.0.1:7890 |
| 真实三首 | 4/4 500 | 莫小檀-荒 36 行（songmid 0009sdl21zLVyO）、柯以汀-泪海 28 行、FLOW-Howling 66 行 |
```

**诚实边界**：真实端点（c.y.qq.com 直连 500 / 代理 200）的**实测发生在调查报告那一轮**，
本轮按任务要求**没有再打真实端点**（当时该端点已进限流窗口，继续探测只会加重它，
且换 IP 规避在任务里被明确排除）。因此本 PR 不主张"真实端点此刻仍是这个形态"，只主张
"代码在这个形态下会按判据回退"。

### 5.2 本机回环实测：真 HTTP 服务器 + 真 socket 驱动路线机器

```bash
python .scratch/soda-lyrics-route/probe_route_loopback.py                        # 本 PR
MUSIC_LYRIC_REPO=D:/dsh-pet-wt-multiscreen python .scratch/soda-lyrics-route/probe_route_loopback.py   # 基线
```

7 个场景 + 1 个"现场形态"计时场景在本 PR 上全绿、在基线红 5 条（原始输出节选）：

```
环境：Python 3.13.7，直连端点 127.0.0.1:11381，代理端点 127.0.0.1:11382，代理失败端点 127.0.0.1:11383，慢端点 127.0.0.1:11384
说明：已对**本探针**关闭 Windows 的 localhost 代理绕过（回环靶子才走得到代理路线）
[PASS] 直连成功只走一次 :: 51ms direct=1 proxy=0
[PASS] 直连 500 回退代理成事 :: 94ms direct=1 proxy=['http://127.0.0.1:11381/search']
[PASS] 404 不换路 :: direct=1 proxy=0
[PASS] 429 不换路且读出 Retry-After :: direct=1 proxy=0 log=['歌词请求失败 127.0.0.1（0.05s）: 直连 HTTPError: HTTP Error 429: Too Many Requests（服务端 Retry-After: 30s，按该响应不换路、不重试）']
[PASS] 无系统代理不回退 :: direct=1 proxy=0
[PASS] 预算耗尽不回退 :: 348ms direct=1 proxy=0 got=None
[PASS] 两路失败两条原因都在日志 :: direct=1 proxy-fail=1 log=['...；系统代理 HTTPError: HTTP Error 500: Internal Server Error']
[PASS] 现场形态（直连 5.3s 失败 + 代理 1.5s）在 9s 预算内成事 :: 6.90s / 预算 9.00s got='QQ_SEARCH'
结论：全部通过

# 基线（同一份探针脚本，只读导入基线检出）
[FAIL] 直连 500 回退代理成事 :: 48ms direct=1 proxy=[]
[FAIL] 429 不换路且读出 Retry-After :: direct=1 proxy=0 log=['歌词请求失败 127.0.0.1（0.05s）: HTTPError: HTTP Error 429: Too Many Requests']
[FAIL] 预算耗尽不回退 :: 0ms direct=0 proxy=0 got="TypeError: _http_get_json() got an unexpected keyword argument 'deadline'"
[FAIL] 两路失败两条原因都在日志 :: direct=1 proxy-fail=0 log=['歌词请求失败 127.0.0.1（0.05s）: HTTPError: HTTP Error 500: Internal Server Error']
[FAIL] 现场形态（直连 5.3s 失败 + 代理 1.5s）在 9s 预算内成事 :: 0.00s / 预算 9.00s got="TypeError: ..."
结论：失败项 ['直连 500 回退代理成事', '429 不换路且读出 Retry-After', '预算耗尽不回退', '两路失败两条原因都在日志', '现场形态（直连 5.3s 失败 + 代理 1.5s）在 9s 预算内成事']
```

最后那条**现场形态**用的是调查报告里的真实时间形状（直连 5.3s 才吐 500、代理 1.5s 给 200），
在 `fetch_lyrics` 的那一份 9s 预算里 **6.90s 拿到结果**——这正是"共享预算"要保住的东西：
不共享的话两次超时会叠到 16s，9s 死线会先把整趟取词判死。

- **断言有效性（消融式对照）**：同一份探针在基线上红 5 条，其中"直连 500 回退代理成事"
  与"现场形态…成事"正是本 PR 的验收点（基线 `direct=1 proxy=[]` 且取不到结果）；
  "429 不换路"在基线的红是因为**日志里没有 `Retry-After`**（基线本来就没有回退功能，
  谈不上换路），这一条只算新诊断的覆盖，不冒充行为修复——如实标注。
- **探针第一次跑就抓到一个真实细节**：Windows 的系统代理绕过表默认含 localhost/127.*，
  而 urllib 的 `ProxyHandler` **尊重**该表——靶子是回环地址时"代理那条路"会被自动绕过
  （首轮观察到 `direct=2 proxy=0`）。真实歌词源是公网域名，不在绕过表里；探针因此显式关闭
  该表好让代理路线在回环上可测。**这条也写进了文档的已知限制**（见 §七）。

### 5.3 用户可见行为

本轮**未**在真实桌宠上点播验证——任务明确要求不操作播放、不碰用户配置，且真实端点已进
限流窗口。可核对的是链路两端：调查报告已证明"会话识别 / 查询串 / 三源顺序"无遗漏，
本 PR 用真实元数据（`莫小檀` / `荒(一念间天荒仙灭)` / songmid `0009sdl21zLVyO`）把
"元数据 → 查询 → 命中 → 明细 → 解析"整链在离线用例里跑通（`TestSodaTrackOfflineIntegration`）。
**不主张**"用户此刻一定能看到歌词"：QQ 端点本身在密集请求下会 500（调查报告 §4 的诚实边界），
回退只解决"路线选错"，不解决"服务端限流"。

### 5.4 边界与失败路径的实机观察

- 没配系统代理时（`test_no_system_proxy_means_no_fallback` / 探针第 5 条）：失败仍然只有
  一次尝试，行为与基线一致。
- 预算耗尽（探针第 6 条，真慢端点 0.4s + 0.3s 预算）：**一个回退请求都没发**
  （`direct=1 proxy=0`），日志点明是预算原因。
- 日志脱敏：两条新用例断言日志不含代理地址/凭据（`127.0.0.1:12450`、`alice`、`s3cr3t`）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | `All checks passed!`（系统 Python 的 ruff 0.16.6；仓库 `.venv` 里是 0.16.7，同样全绿） |
| 聚焦（本文件） | `pytest -q tests/test_music_lyric.py`（`QT_QPA_PLATFORM=offscreen`） | **127 passed**（基线 107 collected → +20）；另用默认随机序跑 3 遍各 127 passed（顺序无关） |
| 相关族 + 文档纪律 | `pytest -q tests/test_music_lyric.py tests/test_lyric_sources.py tests/test_music_title.py tests/test_now_playing_media_type.py tests/test_window_pause.py tests/test_pr_report_discipline.py` | **394 passed** |
| 全量（权威口径：系统 Python） | `python -m pytest -q`（全仓，offscreen） | 见 §6.1 |
| 全量（仓库 `.venv`，38 包） | `/d/dsh-pet-src/.venv/Scripts/python.exe -m pytest -q` | 1 failed / 7909 passed / 27 skipped —— 唯一红是 `tests/test_screen_capture_ocr.py` 的 `ModuleNotFoundError: No module named 'omegaconf'`，属**解释器缺依赖**（该 venv 没装 `requirements.txt:85` 的 omegaconf），与本改动无关，见 §6.2 |
| 断言有效性（消融） | 同一份回环探针跑基线检出 | 基线红 5/8（见 §5.2），证明新用例/探针能区分新旧实现 |
| 架构红线 | `tests/test_architecture.py` | 含在全量内 |
| 测试期真实网络 | 全文件跑完 grep `歌词请求` | 0 条（修掉既有泄漏前为 4 条真实请求） |

### 6.1 全量结果

```bash
# 权威口径（本机系统 Python，含 requirements 全量依赖）
cd D:/dsh-pet-wt-soda-lyrics && QT_QPA_PLATFORM=offscreen python -m pytest -q
```

```
7924 passed, 15 skipped, 3121 warnings in 1367.63s (0:22:47)
```

`0 failed`。同机同期还有兄弟代理在工作（CPU 争用），耗时比 CI 慢属正常。

> 对照：用仓库内 `D:/dsh-pet-src/.venv`（38 包，缺 `omegaconf`）跑同一套得到
> `1 failed, 7909 passed, 27 skipped`（21:18），唯一的红是 `omegaconf` 缺失导致的
> 截图/OCR 用例，与本改动无关——排查证据见 §6.2。两个口径的 skip 数差（15 vs 27）
> 同样来自解释器缺依赖。

### 6.2 关于那条与本改动无关的红（解释器缺依赖）

用仓库里的 `D:/dsh-pet-src/.venv`（`pip list` 38 项）跑全量时唯一的红是：

```
FAILED tests/test_screen_capture_ocr.py::test_self_built_sessions_are_injected_into_the_engine_cfg
E   ModuleNotFoundError: No module named 'omegaconf'
```

排查证据：① 单独重跑同样红（不是时序/顺序问题）；② `python -c "import omegaconf"` 在该 venv 里同样失败；
③ `omegaconf` 是 `requirements.txt:85` 声明的依赖；④ 本机**系统 Python**
（`C:\Users\me\AppData\Local\Programs\Python\Python313\python.exe`，441 个包）里有它，用它跑全量即为
§6.1 的结果；⑤ `git diff --name-only` 显示本 PR 只碰 `pet/music_lyric.py`、`tests/test_music_lyric.py`
与三个文档，截图/OCR 链路一行未动。结论：那是**选了不完整的解释器**造成的环境红，不是本改动的回归；
本报告的全量口径以系统 Python 为准。（没有为该测试去 `pip install`：那是改动用户环境，超出本轮范围。）

## 七、已知限制与后续

1. **QQ 端点自身会限流**：回退解决的是"路线选错"，不解决"服务端拒绝"。密集请求下两路都会
   500（调查报告 §4），此时用户仍是"暂无歌词"——本 PR 不承诺"源无词/服务端拒绝也一定出词"。
2. **直连慢失败吃掉预算**：直连若跑到 7~8s 才失败，回退只剩不到 1s，大概率来不及（会被预算
   闸拦住并发一条说明日志）。这是"不把总延迟翻倍"的代价，取舍见 §三。
3. **回退尊重系统的代理绕过表**：用户若把歌词源域名放进绕过名单，回退会退化成第二次直连
   （不报错、只是没效果）。刻意不改用户配置。
4. **只回退一次**：不在同一请求内做周期重试；失败后由既有的同曲 5 分钟冷却兜住再来一次。
5. **本轮没做的两件事**（独立问题，已在调查报告登记 G2/G3）：启动入口的中文 app_id 匹配
   （`SodaMusic.exe` vs `汽水音乐`）、歌手名字形归一（`時/时`）。
6. **真实端点未复测**：见 §5.1 的诚实边界。下次复测请先确认 QQ 端点已出限流窗口，且**只打
   必要的两次**（直连一次、代理一次），不要重复探测。

## 八、风险与回滚

- **影响面**：仅 `pet/music_lyric.py` 的出口策略；不新增配置键、不涉及落盘格式（缓存版本
  `_CACHE_VERSION` 未变）、不改任何设置页/菜单入口。
- **触发前提**：只有"本机配着系统代理"且"直连失败（传输/5xx）"时才多一个请求；其它情况
  与基线逐字一致。
- **回滚**：`git revert` 该提交即可，无残留状态（既没有写入新键，也没有新增落盘数据）；
  唯一"残留"是日志文案回到旧形态。
- **风险点**：如果用户的代理本身是有害的（2026-09-22 那种 +20s 的慢代理），回退会在直连
  失败后再等一段（受剩余预算约束、绝不超过 9s 死线）——相比"直接 0 行"，这是可接受的
  交换；且回退只在直连已经失败之后发生。

## 九、全量追加（本轮实测粘贴）

```
$ cd D:/dsh-pet-wt-soda-lyrics && QT_QPA_PLATFORM=offscreen python -m pytest -q
........................................................................ [  1%]
...
........................................................................ [ 99%]
........................................................................ [100%]
7924 passed, 15 skipped, 3121 warnings in 1367.63s (0:22:47)
```

聚焦与相关族（同一解释器）：

```
$ python -m pytest -q tests/test_music_lyric.py            → 127 passed
$ python -m pytest -q tests/test_music_lyric.py tests/test_lyric_sources.py \
      tests/test_music_title.py tests/test_now_playing_media_type.py \
      tests/test_window_pause.py tests/test_pr_report_discipline.py
                                                            → 394 passed
$ python -m ruff check pet tests scripts                    → All checks passed!
```

产物（未入库，`.scratch/` 被 gitignore）：

| 文件 | 作用 |
|---|---|
| `.scratch/soda-lyrics-route/probe_route_loopback.py` / `probe-loopback.log` / `probe-loopback-baseline.log` | 本机回环实测（真实 HTTP 服务器 + 真实 socket），本 PR 8 场景全绿 / 基线红 5 |
| `.scratch/soda-lyrics-route/bench_route_success.py` / `bench-new.log` / `bench-baseline.log` | 热路径与失败路径 A/B、判据单价（§四 的数字来源） |
| `.scratch/soda-lyrics-route/full-suite-syspython.log` / `full-suite.log` | 两个解释器的全量原始日志 |

---

## 十、第二轮：提交前核查的三处修正（2026-10-17）

> 本节是**追加**，不改上面首轮的结论与数字（首轮的全量基线 `7924 passed / 15 skipped / 0 failed`
> 仍以上文 §6.1 为准，原始日志在 `.scratch/soda-lyrics-route/full-suite-syspython.log`）。
> 本节的三处改动的验证口径只有 **focused + 相关族 + ruff**（见 §十.4），全量由 CI 跑。

### 十.1 改了什么（三处）

| # | 问题 | 修法 |
|---|---|---|
| 1 | 「有系统代理」被当成"有第二条路"，但 `getproxies()` 里的 `no` 是**绕过名单**、`ftp`/`all` 对本 URL 无效；命中系统代理绕过表时 `ProxyHandler` 本来就会放行成直连——这两种情况下"回退"实际是**同一条直连路再打一次**，日志还会谎称走了代理 | 新增 `_configured_proxies()`（只认 `http`/`https` 条目）与 `_fallback_proxy(url)`（只认 URL **实际协议**有代理，且 `urllib.request.proxy_bypass(host)` 为假）；不满足就不回退，成功日志只在**真走了代理**时才出现 |
| 2 | 5xx 也会带 `Retry-After`（整数秒 / HTTP 日期 / 无效值），而 `_may_switch_to_proxy` 只看状态码 → 日志写着"不换路、不重试"，实际却换路重打了一遍 | `_may_switch_to_proxy` 在 500/502/504 上先看 `_retry_after(exc)`：**只要该头存在（三种形态都算）就不换路**；`_retry_after` 改为返回规范化短串（整数/日期/无效值/空值都保留可读形态），只用于日志 |
| 3 | 失败日志直接写 `str(exc)`：`URLError`/`http.client.InvalidURL` 的文本可能夹带**内部代理地址甚至凭据**（`<urlopen error ... http://user:pass@proxy.internal:8080>`） | 新增 `_failure_detail(exc)`：只输出**异常类型 + HTTP 状态 + Retry-After**；两条路仍分别可辨（`直连 URLError；系统代理 InvalidURL`）。不做 redaction 表、不动其它日志字段 |

判据仍然"最小状态、不新增框架"：全部沿用标准库语义（`ProxyHandler` 按 URL scheme 装
`*_open`、`proxy_bypass` 的绕过判定），没有自建规则、没有新增线程/配置/状态。

### 十.2 修改文件说明（第二轮）

| 文件 | 增删 | 说明 |
|---|---|---|
| `pet/music_lyric.py` | 见 PR 的 `git diff --numstat` | `_configured_proxies` / `_fallback_proxy` / `_retry_after`（取代 `_retry_after_seconds`）/ `_failure_detail` 新增；`_may_switch_to_proxy` 加 `Retry-After` 闸；`_http_get_json` 改用新判据与新日志；注释里"网关类故障"改为**具体状态码**（500 / 502 / 504） |
| `tests/test_music_lyric.py` | 同上 | 新增 21 例（参数化后）：`no` 单独存在、协议不匹配 4 种、绕过表命中、成功日志不谎称代理、5xx × 4 种 `Retry-After` 形态 × 3 个状态码、无 `Retry-After` 的对照、异常文本不落日志；`_RouteStub` 增加 `proxies` / `bypass` 两个替身旋钮（真实现会读用户注册表，测试不该依赖） |
| `docs/NETWORK-PROXY-AND-VPN-2026-09-22.md` | 同上 | §二 日志行格式、§六 的口径补上"只有真代理路才算 / Retry-After 阻止换路" |

### 十.3 实机运行记录（第二轮，本机真跑）

**红→绿（消融对照）**：把产品文件临时回退到首轮提交 `488a43f`（`git stash`）后，同一批用例

```
$ QT_QPA_PLATFORM=offscreen python -m pytest tests/test_music_lyric.py -q -p no:randomly
20 failed, 128 passed in 3.54s
```

20 条红覆盖三处改动各自的判据（协议/绕过/`no` 各自的红、5xx+`Retry-After` 12 条红、
两条日志相关红）；恢复后同一命令 **148 passed**。

**本机回环探针（真实 HTTP 服务器 + 真实 socket，不联网）**：

```
$ python .scratch/soda-lyrics-route/probe_route_loopback.py
[PASS] 直连成功只走一次 :: 51ms direct=1 proxy=0
[PASS] 直连 500 回退代理成事 :: 92ms direct=1 proxy=['http://127.0.0.1:5864/search']
[PASS] 404 不换路 :: direct=1 proxy=0
[PASS] 429 不换路且读出 Retry-After :: ... : 直连 HTTPError HTTP 429（服务端 Retry-After: 30，按该响应不换路、不重试）
[PASS] 无系统代理不回退 :: direct=1 proxy=0
[PASS] 预算耗尽不回退 :: 353ms direct=1 proxy=0 got=None
[PASS] 两路失败两条原因都在日志 :: 直连 HTTPError HTTP 500；系统代理 HTTPError HTTP 500（无异常文本）
[PASS] 现场形态（直连 5.3s 失败 + 代理 1.5s）在 9s 预算内成事 :: 6.90s / 预算 9.00s
结论：全部通过
```

注意第 4/7 条的日志形态已是第二轮格式：**没有异常文本**，只有类型 + 状态 + `Retry-After`。

### 十.4 性能分析（第二轮，实测）

方法：`python .scratch/soda-lyrics-route/bench_route_success.py`（本机回环，n=200 000 / n=200 ×3 轮）。

| 指标 | 实测 | 归属 |
|---|---|---|
| `_may_switch_to_proxy(500)`（无 `Retry-After`） | 0.418 µs/次 | 失败路径，每条失败请求一次 |
| `_may_switch_to_proxy(500 + Retry-After: HTTP 日期)` | 2.963 µs/次（多出的是头读取 + 规范化） | 同上 |
| `_retry_after(429)` / `_failure_detail(502)` | 0.895 / 0.599 µs/次 | 同上 |
| `_fallback_proxy(url)` | 2.212 µs/次（`proxy_bypass` 用替身时） | 失败路径一次 |
| `urllib.request.proxy_bypass(host)` 真实调用 | **147.8 µs/次**（n=200，读 HKCU 注册表） | OS 边界 |
| `urllib.request.getproxies()` 真实调用 | 102.7 µs/次（n=200） | OS 边界 |
| 直连成功端到端中位（回环，n=30 ×3） | 48.43 / 47.57 / 50.46 ms | 热路径（与首轮/基线同量级） |
| 直连 500 路径端到端中位（回环，n=30 ×3） | 102.10 / 102.93 / 102.34 ms | 失败路径 = 多一次真实往返 |

逐条：② 新增路径绝对成本 = 判据约 **3 µs**（计算）+ 失败路径上**一次注册表读取**
（`proxy_bypass` 147.8 µs，只在直连已经失败之后发生，相对那次 ≥0.4s 的失败可忽略）；
③ **无新增线程/定时器/磁盘写入**；网络只在真回退时 +1 个请求；④ 无新增缓存，只多两个
模块级常量与一个辅助函数；① 成功路径的判据一条都不走（除每进程一次的路线日志），
端到端与首轮同量级。

### 十.5 测试与验证（第二轮）

| 门 | 命令 | 结果 |
|---|---|---|
| 静态 | `python -m ruff check pet tests scripts` | `All checks passed!` |
| 聚焦 | `pytest -q tests/test_music_lyric.py` | **148 passed**（首轮 127 → +21）；默认随机序 3 遍各 148 passed |
| 相关族 + 文档纪律 | 6 个文件 | **415 passed** |
| 消融 | 产品文件回退到 `488a43f` | **20 failed / 128 passed** → 恢复后 148 passed |
| 全量 | 本轮**未跑**（首轮已有 `7924 passed / 15 skipped / 0 failed` 作底；三处改动只动判据与日志字段，回归面由聚焦族覆盖）→ 由 CI 跑全量 | CI |
| 本轮未做 | 真实端点请求、真机点播、读用户 APPDATA | 按任务边界，未做 |

### 十.6 状态（第二轮结束时）

- 分支 `fix/soda-lyrics-route`，本轮最终 HEAD 见文末「附录：HEAD 记录」。
- 三处改动**只跑了 focused + 相关族 + ruff**；首轮的全量数字不与之混算。
- 仍未做：merge / 部署 / tag / release；真实端点复测（QQ 端点限流窗口）。

---

## 附录：HEAD 记录

| 提交 | SHA | 内容 | 验证口径 |
|---|---|---|---|
| 第一轮（2026-10-16） | `488a43f` | 直连首选 + 有界单次回退（实现、测试、AGENTS/网络文档、本报告首轮章节） | 聚焦 127 + 相关族 394 + ruff + **全量 7924 passed / 15 skipped / 0 failed** |
| 第二轮（2026-10-17） | `4746a34` | 三处修正（真代理路判据 / `Retry-After` 闸 / 日志只记类型与状态）+ 本报告 §十 | focused 148 + 相关族 415 + ruff（**未重跑全量**，交 CI；首轮全量数字不与本轮混算） |

- 分支：`fix/soda-lyrics-route`（`origin/MerZlin/dsh-pet-indesktop`），基线 `b7a697f`（= `origin/main` #288）；主线 PR：[#291](https://github.com/MerZlin/dsh-pet-indesktop/pull/291)，全量交该 PR 的 CI 跑。
- 本节所在提交只追加记录，无实现改动；分支最终 HEAD 见 `git log -1`（本轮实现提交为 `4746a34`）。
- 全量原始日志（本机，`.scratch/` 被 gitignore）：
  - 权威口径（系统 Python 441 包）：`.scratch/soda-lyrics-route/full-suite-syspython.log` →
    `7924 passed, 15 skipped, 3121 warnings in 1367.63s`（见 §6.1）。
  - 仓库 `.venv`（38 包，缺 `omegaconf`）：`.scratch/soda-lyrics-route/full-suite.log` →
    `1 failed, 7909 passed, 27 skipped`，唯一红是环境缺依赖（见 §6.2）。
