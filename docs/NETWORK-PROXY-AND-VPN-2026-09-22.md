# 代理 / VPN 对桌宠联网功能的影响（2026-09-22）

> **基线**：`0983706`（Merge PR #180）＋ `fix/music-lyric-system-proxy`（PR #181）
> **实测环境**：Windows，系统代理 `http://127.0.0.1:12450`（全局模式 VPN 客户端进程 `core`），
> CPython 3.11.1，全部数字为 2026-09-22 本机单次实测（每项 1 次，含冷连接）
> **缘由**：用户反馈「合并后识别不到网易云的歌词、快进进度也不行了」，真因是**系统代理把歌词取词拖到超时**
> （完整证据链见 [`PR-REPORT-MUSIC-LYRIC-SYSTEM-PROXY-2026-09-22.md`](PR-REPORT-MUSIC-LYRIC-SYSTEM-PROXY-2026-09-22.md)），
> 与相关机制见 [`PR-REPORT-music-lyric-align-2026-09-22.md`](PR-REPORT-music-lyric-align-2026-09-22.md)。

## 一句话结论

桌宠的联网功能**都吃 Windows 的"系统代理"设置**（`urllib.request` 会自动读注册表 / 环境变量，
`getproxies()` 就是它看到的代理）。开着 VPN 时**不能一概而论**：有的功能会**变慢甚至彻底失效**
（歌词取词实测 20~41 秒 → 超时），有的反而**只有代理才能用**（更新清单走 jsdelivr）。
所以正确姿势是**分流 / 规则模式**，并且**保留 localhost 绕过**——不是"全局开"也不是"全局关"。

## 一、受影响功能清单（逐条实测）

| 功能 | 出口代码 | 端点 | 开着系统代理时的表现 | 结论 / 应对 |
|---|---|---|---|---|
| **歌词取词** | `pet/music_lyric.py` | `c.y.qq.com`、`lrclib.net`、`music.163.com` | 三源单次 **41.28 / 22.14 / 20.39 秒**，全部超过 `HTTP_TIMEOUT`（8s）→ 每首未缓存曲目都是 `0行, 耗时 9.00s`；直连 **0.58 / 0.83 / 0.25 秒** | **首选直连**（PR #181，`ProxyHandler({})`）；直连坏掉时**回退一次**系统代理（2026-10-16，见 §六），用户无需自己配 |
| **TTS 语音合成**（语音报时 / 点击台词朗读 / 节日语音 / 设置页试听，edge-tts） | `pet/voice_chime_service.py`（`edge_tts.list_voices` 与 `Communicate`）、`pet/settings_standalone.py`（独立设置进程试听，同一条通道） | `speech.platform.bing.com`（Microsoft） | 音色列表端点**直连 2.08s 成功**；走代理 2.26s（也成功）——两者差异不大 | 两边都可用。**不要**为修歌词把它一起绕掉：海外用户/直连不稳的网络需要它走代理 |
| **本机 CosyVoice 语音预缓存**（可选，需自建服务） | `pet/self_talk_voice.py`（`DEFAULT_SERVER = "http://127.0.0.1:9880"`） | **本地** `127.0.0.1:9880` | 若代理把 localhost 也吃了 → `/health` 连不上、预缓存整批失败 | 代理设置里**必须保留** `localhost;127.*` 绕过（Windows 默认的 `ProxyOverride` 就含它，别删） |
| **DSH / Harness 联动与本地探活** | `pet/dsh_responder.py`（`http://127.0.0.1:<port>`）、`pet/harness_launcher.py`（`socket.create_connection(("127.0.0.1", port))`） | **本地** | 同上：localhost 被代理 → 联动请求发不出去、Harness 端口探活误判 | 同上 |
| **更新检查** | `pet/updater.py` | `api.github.com`、`cdn/fastly/gcore.jsdelivr.net`、`pan.quark.cn` | **jsdelivr 直连失败**（`WinError 10054 远程主机强迫关闭了一个现有的连接`），**走代理 1.45s 成功**；GitHub API 直连 0.69s / 走代理 1.41s 都可用 | 这一类**需要代理**（或把 jsdelivr 域名在分流里指向代理） |
| **余额 / 峰谷提示** | `pet/balance.py` | 用户自配 `base_url`（常见 `api.deepseek.com`） | 取决于端点在国内还是海外 | 按端点分流；国内端点直连即可 |
| **主动识屏（视觉）** | `pet/vision.py` | 用户自配视觉端点（超时下限 60s） | 慢代理下会一直等到超时（用户观感：点了没反应） | 按端点分流；排查时看日志里的请求耗时 |
| **AI 对话** | `pet/chat/providers.py` | 用户自配对话端点 | 同上（海外端点通常需要代理，国内端点直连更快） | 按端点分流 |
| **点击音效** | `pet/click_sound.py` | **不联网**：本地素材 + 本地转码缓存 `sounds_cache/` | 无影响 | 与代理无关。（先前报告里误写成"音效下载"，此处更正） |

> **测量口径**：歌词/更新/GitHub 的数字是**直连与走代理各打一次真实请求**；
> TTS 那一行测的是 edge-tts 的**音色列表端点**（HTTPS，与合成同一个主机），
> 合成走的是同主机的 WSS——本次**没有**单独测 WSS 握手耗时，只测了同主机的 HTTPS 可达性。
> 音效"不联网"这一条是读代码确认的（`pet/click_sound.py` 只做本地转码，素材在
> `assets/sounds/`），不是靠观察推断。

## 二、30 秒判断"是不是代理干的"

```bash
# 1. 当前系统代理（ProxyEnable=0x0 或 getproxies 返回 {} 就是没在用）
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" | findstr /i "proxy"
python -c "import urllib.request; print(urllib.request.getproxies())"

# 2. 关掉系统代理，重做同一个操作
#    ——立刻恢复基本就实锤（2026-09-22 实测：关掉后歌词马上回来）

# 3. 想量化某个端点该不该走代理：直连 / 走代理各打一次同样的 GET
python - <<'PY'
import time, urllib.request
def probe(url, proxy):
    op = urllib.request.build_opener(urllib.request.ProxyHandler(
        {} if proxy is None else {"https": proxy}))
    req = urllib.request.Request(url, headers={"User-Agent": "probe"})
    t0 = time.monotonic()
    try:
        with op.open(req, timeout=8) as r:
            return "%.2fs (%d bytes)" % (time.monotonic() - t0, len(r.read()))
    except Exception as e:
        return "%.2fs %s: %s" % (time.monotonic() - t0, type(e).__name__, str(e)[:70])
for url in ["https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w=test&format=json",
            "https://cdn.jsdelivr.net/gh/MerZlin/dsh-pet-indesktop@main/update.json"]:
    print(url[:60], "| 直连:", probe(url, None), "| 走代理:", probe(url, "http://127.0.0.1:12450"))
PY
```

日志关键字（`%APPDATA%\dsh-pet-standalone\pet-<pid>.log`）：

| 想定位的功能 | 日志信号 |
|---|---|
| 歌词取词 | `歌词取词完成: <歌手> - <歌名> -> 0行, 耗时 9.00s`（三源全超时）；PR #181 起还有 `歌词请求失败 <主机>（x.xxs）: <路线> <异常类型> [HTTP <状态>] [（服务端 Retry-After: <值>，按该响应不换路、不重试）]`（2026-10-16 起带路线名，如 `直连 TimeoutError`；两条路都试过时一条里同时含 `直连 …；系统代理 …`。2026-10-17 起**只记类型/状态/Retry-After，不写异常文本**——异常文本可能夹带内部代理地址或凭据）；另有 `歌词请求跳过 <主机>：剩余预算不足 …`（预算已耗尽，没发请求）与 `歌词请求回退系统代理成功 <主机>（x.xxs）`（只在真走了代理时出现） |
| 歌词是否绕了代理 | PR #181 起每进程一行 INFO（2026-10-16 起**不回显代理地址/凭据**）：`歌词请求：检测到系统代理，首选直连；仅在直连传输失败或 HTTP 500/502/504 时回退系统代理一次`。**"有代理"只认 http/https 条目**：`no`（绕过名单）与其它协议不算；命中系统代理绕过表、或响应带了 `Retry-After`（含 HTTP 日期与无效值）时都不换路（没这行 = 本机没有可用的系统代理配置） |
| TTS 音色 | 音色下架/回退相关文案（`voice_chime`），以及合成耗时 |
| 更新检查 | 更新清单请求失败的 URL（jsdelivr 三个镜像依次尝试） |

## 三、推荐配置（按推荐度）

1. **分流 / 规则模式（首选）**：VPN 客户端按域名决定直连还是走代理（国内直连、海外走代理），
   并保留 `localhost;127.*` 绕过。这样每类功能都走它该走的路。
2. **全局模式 + 绕过名单**：必须直连的加进绕过：
   `*.qq.com`、`music.163.com`、`lrclib.net`（歌词已由代码直连，这里是双保险）、
   `*.deepseek.com`（若余额/对话端点是它）、`localhost`、`127.*`。
   **不要**把 `speech.platform.bing.com`、`*.jsdelivr.net`、`api.github.com` 加进绕过名单——
   它们多数情况反而需要代理（jsdelivr 本次实测直连直接失败）。
3. **临时完全关掉系统代理**：只建议用来排障（能立刻验证"是不是代理干的"）。
   代价：更新检查会走不通（jsdelivr 直连失败），TTS 能否直连取决于你的网络。

## 四、代码侧的口径（为什么不做"全局绕过代理"）

- **逐功能决定，不做全局**。歌词源已实测「代理有害」→ 代码里以**直连为首选**
  （`pet/music_lyric.py` 的 `_build_opener()` = `ProxyHandler({})`，见 PR #181）；
  直连**传输失败或 500/502/504** 时回退一次系统代理（2026-10-16，见 §六与
  [`PR-REPORT-SODA-LYRICS-ROUTE-2026-10-16.md`](PR-REPORT-SODA-LYRICS-ROUTE-2026-10-16.md)）。
  其余功能保持"跟随系统代理"，因为更新（jsdelivr）实测**只有代理能用**，
  而 TTS 端点直连/代理都可用但海外网络需要代理。
- 桌宠**不会**改用户的代理设置，也不主动关代理；歌词请求只影响它自己。
- 已知未做（2026-10-16 后更新）：歌词侧的"直连失败走代理兜底"**已落地为有界回退**
  （只回退一次、两路共享同一份预算，故失败路径不再从 9s 翻到 ~18s）。
  仍然没做的是：跟随系统的**代理绕过表**——若用户把歌词源域名放进绕过名单，
  回退会退化成第二次直连（不报错，只是没效果），这是刻意尊重用户配置的结果。

## 五、本次实测原始输出（2026-09-22）

```
# 单源对照（代理开启时）
qq（c.y.qq.com，2 次请求）  走系统代理 41.28s → 39 行   直连 0.58s → 39 行
lrclib.net                 走系统代理 22.14s → 35 行   直连 0.83s / 3.47s / 1.28s → 35 行
music.163.com              走系统代理 20.39s            直连 0.25s

# 真实网易云会话（蝴蝶 - 陶喆, position=None, app_id=cloudmusic.exe）
修复前 fetch_lyrics: 9.01s → None（0 行）
修复后 fetch_lyrics: 0.88s → 53 行

# 其他端点（ProxyEnable=0，显式对比直连/走代理）
TTS 音色列表(Microsoft)  直连 2.08s (170998 bytes)   走代理 2.26s (170998 bytes)
jsdelivr 更新清单        直连 0.22s URLError WinError 10054   走代理 1.45s (1976 bytes)
GitHub API               直连 0.69s (52124 bytes)    走代理 1.41s (52124 bytes)
```

> 说明：数字为单次取样，代表"量级与成败"，不是基准测试；复核请用 §二的探针命令重跑。

## 六、追补：代理也可能**只有它才通**（2026-10-16）

上面整份文档的取向是"代理有害"，但 2026-10-16 汽水音乐那次实测**方向反过来**：
同一个 URL、同一分钟，QQ 歌词源**直连恒 HTTP 500**，**走系统代理 200**（并真的取回
36 行歌词）。来源曲目在网易云与 lrclib 里都没有，于是三源全灭 → 「歌名在、歌词不在」。

结论：**两条路都可能死，也可能只有一条活**——固定押一条路就得靠用户自己配分流。
据此歌词请求改成了「直连首选 + 有界的单次回退」，判据与预算见
[`PR-REPORT-SODA-LYRICS-ROUTE-2026-10-16.md`](PR-REPORT-SODA-LYRICS-ROUTE-2026-10-16.md)。
本文档 §一/§二/§四 的相应表述已同步；§五（2026-09-22 的原始数字）保持历史原样。

> 诚实边界：追补的**实现**由本机回环探针（真实 HTTP 服务器 + 真实 socket，不联网）
> 与离线回归用例验证；**真实端点**（c.y.qq.com 直连 500 / 代理 200）的数字来自
> 上面那份调查报告的当次实测，2026-10-16 之后的代码改动**没有再打真实端点复测**
> （当时该端点已进限流窗口，继续探测只会加重它）。

### 六之一、回退的三个边界（2026-10-17 补）

"有系统代理"不等于"有第二条路"，回退能不能发生还看三件事——都按标准库语义判断，
不自建规则：

1. **只有 URL 实际协议（http/https）配了代理才算**。``getproxies()`` 里的 ``no`` 是
   绕过名单（`NO_PROXY`）、``ftp``/``all`` 对本 URL 无效：``ProxyHandler`` 按 URL 的
   scheme 装 ``*_open`` 处理器，没装到的协议它照样直连。所以只给 `no` 或只给
   `ftp` 时**不回退**（否则那只是同一发直连、日志还会谎称走了代理）。
2. **命中系统代理绕过表（`urllib.request.proxy_bypass`）的 URL 也不回退**：
   ``ProxyHandler.proxy_open`` 在这种情况直接放行成直连，回退等于重复直连。
   反过来说：用户把歌词源域名加进绕过名单时，"回退"不会发生，也不会报错——
   这是尊重用户配置的结果，不是缺陷。
3. **响应带 `Retry-After` 就不换路**（整数秒、HTTP 日期、无效值、空值都算"带了"）：
   5xx 也常带这个头，它的意思就是"过一会儿再打"，立刻换条路重打同样违背该请求。
