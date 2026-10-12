# PR 报告：本地语音合成后端（SAPI5 离线）— 2026-10-12

> 起因：机主报「**本地实例语音合成失败**」并要求「**换一个稳定的 TTS，现阶段 TTS 合成速度太慢了，延迟太高**」。

## 一、修改文件说明

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/tts/sapi.py` | **新增** | Windows 本地语音（SAPI5）provider：零网络、零 Key、毫秒级。走 comtypes **晚绑定**（本机 `GetModule('sapi.dll')` 会报 `TYPE_E_CANTLOADLIBRARY`）；用 `SAPI.SpFileStream`（`Open(path, 3)` = SSFM_CREATE）把语音直接写成 wav，符合 `synth(text, plan, out_path)` 契约；`installed_voices()` 取系统已装音色（结果缓存），`pick_default_voice()` 优先中文 |
| `pet/tts/__init__.py` | +2 | `from . import edge, mimo, sapi`（import 即注册）+ `__all__` 加 `sapi` |
| `pet/config.py` | +4 | 新键 `voice_chime_sapi_voice`（默认 `""`＝自动挑中文音色）与 `voice_chime_sapi_rate`（默认 0，−10..10）——默认值 dict 与 `reload()` 白名单各两行 |
| `tests/test_config_schema.py`、`tests/test_voice_chime.py` | 各 +2 | 三处快照补两个新键（默认值快照 / 白名单快照 / 扁平键集） |

无新增第三方依赖（`comtypes` 是既有依赖，pycaw 已在用）。

## 二、性能分析

环境＝她的机器（Win11 24H2 / Ryzen 7 5800X），命令＝`pytest`/探针脚本，样本＝同一句中文。

| 路径 | 实测 |
|---|---|
| SAPI5 直测（`Microsoft Huihui Desktop`，21 字） | **首句 111 ms / 同进程第二句 19 ms**，产出 236,102 字节 wav |
| 走宠物 provider 链（`tts.get('sapi')` → `synth`，46 字） | **首句 166 ms / 复句 112 ms**，产出 398,990 字节 wav |
| 对照：edge-tts（同机、同文本） | 走公网 WSS，实测被服务端 **403**（`WSServerHandshakeError`），拿不到音频 |
| 对照：MiMo（公网 HTTP） | 秒级；机主反馈「太慢、延迟高」 |

归因（排查记录，均在日志/实测里）：本机时间与服务端偏差 **−0.6 秒**（不是时钟问题）；`edge-tts`
**7.2.8 已是 PyPI 最新版**（不是包旧了）⇒ 403 是微软侧对该客户端的拦截，我们这边无从修。
SAPI5 由操作系统本地合成，**不存在"服务端改规则"这一类不稳定**，也不需要 Key。

## 三、实机运行记录

```
── SAPI5 音色（本机）──
SAPI5 语音数: 3
  [0] Microsoft Huihui Desktop - Chinese (Simplified) | Language=804
  [1] Microsoft Zira Desktop - English (United States) | Language=409
  [2] Microsoft David Desktop - English (United States) | Language=409
选用: [0] Microsoft Huihui Desktop - Chinese (Simplified)
合成耗时: 111 ms；wav 236102 字节
第二次合成耗时: 19 ms

── 走宠物 provider 链 ──
provider: sapi | Windows 本地语音（离线，毫秒级）
availability: ''
plan: {'provider': 'sapi', 'voice': '', 'rate': 0, 'ext': 'wav'} | flavor: sapi||0
首句 166 ms / 复句 112 ms；产物 398990 字节
样音: H:\360MoveData\Users\KAZA\Desktop\本地语音样音-Huihui.wav

── 修复前的现场（日志实证）──
WARNING edge 合成失败：edge-tts 合成失败 → zh-CN-XiaoxiaoNeural 第1次: WSServerHandshakeError: 403 …
（16:30 / 16:45 / 17:00 / 17:15 / 17:30 每 15 分钟一次，全部失败）
```

- `ruff check .` → **All checks passed!**
- 聚焦：`tests/test_voice_chime_mimo.py`（含**每个已注册 provider 都要满足契约**的守卫，现在覆盖 sapi）
  + `test_config_schema.py` + `test_voice_chime.py` + `test_tts_edge.py` + `test_voice_chime_service.py`
  → **247 passed**。
- 部署：live 与 H: 都已换成本次构建（1026 文件），桌宠已重启（PID 56168，日志 0 ERROR）；
  回滚点 `dist-onedir\...bak-20261012-2141`。
- 机主配置：后端 `edge` → **`sapi`**（并保留 `voice_chime_tts_fallback=True` 作为兜底），
  改前已备份 `config.json.bak-20261012-214420`。
- **未验到的一格**：切换后到下一次报时（每 15 分）才会在 `voice_chime_cache/` 里出现新的 `.wav` ——
  写报告时缓存里还只有旧的 mp3（含一个 0 字节的半截产物，正是 edge 失败留下的）。
- 全量套件未跑通（与本改动无关）：已知在约 76% 处撞原生 access violation，单跑相关文件全绿。
