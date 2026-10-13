# PR 报告：语音设置页整理 + 面向公众的默认后端（2026-10-13）

- **分支**：`feat/media-window-fallback`
- **触发**：机主 2026-10-13 原话「（语音界面）各种信息太复杂了，需要整理，写得更**人性化和简洁**一点」；同轮另一条设计原则「面向公众发包的话，这些引擎接入需要他们自己来做，**不能走我的API啊**」。
- **范围**：语音域**呈现层**（折叠 + 文案）+ 默认后端取值。**功能面未动**：字段键、读写、provider 切换、降级回退、缓存键全部保持原语义。
- **实现分工**：布局与文案由子代理实现，Lead 复核、补本报告、打包部署与终验。

## 修改文件说明

`git diff --numstat`（新增文件单列）：

```
8	5	docs/DEV-HANDOVER.md
27	0	docs/SETTINGS-CHANGE-GATES.md
8	3	pet/config.py
5	9	pet/modern_settings_dialog.py
20	0	pet/settings_widgets.py
11	8	pet/tts/doubao.py
3	4	pet/tts/edge.py
10	10	pet/tts/mimo.py
8	5	pet/tts/sapi.py
5	2	pet/voice_chime.py
59	32	pet/voice_chime_settings.py
6	3	tests/test_menu_layout.py
5	4	tests/test_voice_chime_mimo.py
1	1	tests/test_voice_chime_service.py
```

| 文件 | 说明 |
|---|---|
| `pet/voice_chime_tts_panel.py`（新增，217 行） | 折叠编排。**关键约束**：设置页的 `SettingRow` 会被 `_rebuild_domain_navigation` 搬进「语音」域平卡，容器嵌套会散架 ⇒ 折叠做在**行**上（一个折叠头行 + `setVisible` 管成员行），行序同时改 `SettingsCard` 的 layout 与 `.rows`（分隔线只认 `.rows` 顺序） |
| `pet/voice_chime_settings.py`（+59/−32） | 缩减为接线：建折叠头 / 凭据组标题、把字段行按后端登记给 panel；`_refresh_backend_controls` 改为「算可见性 → panel.apply」；文案人话化 |
| `pet/settings_widgets.py`（+20） | 新增 `reveal_settings_row()`：把搜索命中时"展开祖先折叠框 / 切页内标签"的逻辑搬进控件库，并支持行上的 `_reveal_fold` 回调——折叠不是 QWidget 嵌套，原祖先判定够不着，搜索命中会"存在但看不见" |
| `pet/modern_settings_dialog.py`（+5/−9 → **2401 行**，预算 2405） | 上述循环改成 1 行调用；域构建完补 `voice_chime_page.refresh_backend_rows()`（平卡运行期现造） |
| `pet/tts/{edge,mimo,sapi,doubao}.py` | 字段名/提示人话化；技术细节（接口地址、资源号 `seed-tts-2.0`、错误码、控制台路径、音色表链接）**移入各自 docstring**，界面不出现 |
| `pet/config.py`（+8/−3） | `voice_chime_tts_backend` 默认 `"mimo"` → `"edge"`：mimo/doubao 需用户自备 Key，当默认等于新装即静音 |
| `pet/voice_chime.py`（+5/−2） | `DEFAULT_BACKEND` 同步 `edge`，避免"默认"有两种含义（配置缺键 / 值非法时的落点） |
| `tests/*`（3 个既有文件） | 断言旧默认值的用例同步；`test_menu_layout` 语音页行数快照 18 → **23**（该快照在 sapi/doubao 接入后即已过期，改动前就是红的，本次一并校正） |
| `docs/SETTINGS-CHANGE-GATES.md`（+27） | 设置改动准入记录（是否值得进设置 / 逐项声明 / 准出对照 / 域位置） |
| `docs/DEV-HANDOVER.md`（+8/−5） | 配置表、尝试链与文件职责表（新增 `voice_chime_tts_panel.py`，行数按实测校准） |
| `tests/test_voice_chime_settings_layout.py`（新增，341 行） | 13 条新用例：折叠/展开、换后端置顶并收起其余、`hidden_when` 在展开的非当前后端内仍成立、凭据组只在有 Key 时出现、凭据状态文案、默认后端＝edge、**文案黑名单**（整页所有行的标题+提示不得含 `http`/`.com`/`seed-tts`/`uranus`/`55000000`/`voices.md`/`ark-skills`/`接口`/`错误码`/`资源号`/`uuid`/`sapi5`/`ffmpeg`/`comtypes`/`keyring`）、以及"这些细节仍在 provider docstring 里"（换地方存档而非丢失）、平卡搬家后行序仍成立、搜索命中折叠内的行会自动展开 |

未新增配置键；未动 `SETTINGS_DOMAIN_NAV`；未碰 `app.py` / `agent_link.py` / `context_menus`。

## 性能分析

环境：本机 Windows 11（Ryzen 7 5800X / 32 GB），Python 3.11.9，venv `D:\dsh-pet\.venv`；脚本 `.scratch/bench_fold.py`，取中位数。

| 操作 | 次数 | 中位数 |
|---|---|---|
| 语音页构造 | 10 | **10.9 ms** |
| 整个设置对话框构造 | 5 | **518.5 ms**（本次仅多一次重排） |
| 切换后端（重排 + 显隐 + 修分隔线） | 60 | **0.57 ms**（最大 2.07 ms） |
| 展开/收起一个后端 | 60 | **0.10 ms**（最大 0.20 ms） |

无新增线程 / 网络 / 磁盘；无新增常驻结构（仅几个 dict 与行引用）。折叠后**同时可见的字段行由 12 降到 ≤4**（当前后端 + 凭据组）。

## 实机运行记录

命令与输出（均为本机真跑）：

- `ruff check .` → `All checks passed!`（改动前 + 最终树各一遍）。
- **全量 `pytest -q`：单进程跑不完，如实记录。** 本机连续三次撞原生 `0xC0000005`，落点各不相同，且崩前一路纯绿（0 failed）：
  1. `test_proactive.py::TestUXFixesRound3::test_self_talk_yields_to_important_bubble`（崩前 2915 passed / 9 skipped）；
  2. 去掉 `PYTHONIOENCODING` 后同落点（2871 passed / 9 skipped）；
  3. `--deselect` 掉上条后改崩在 `test_recovery_hints.py::test_enabling_mouse_through_shows_recovery_hint`（2943 passed / 9 skipped）。
  该用例单独跑 `1 passed`（1.27 s）。`.scratch/full-run.log`、`full-run2.log`（2026-10-11 留存）记录的是**同一现象、另外两个落点**。⇒ 判定为**本机既存的原生崩溃**，非本次改动引入；**不宣称"全量通过"**。
- **为取得真实覆盖改按文件切 10 片、各起独立进程顺序跑**（`.scratch/run_chunks.py`，每片 ≤500 例，崩溃自动二分）：
  `460 / 494+4skip / 487+3skip / 490+2skip / 489 / 437 / 490+3skip / 476 / 497+1skip / 157+1skip`，**10 片 exit 全 0**。
  **合计 4477 passed + 14 skipped = 4491/4491（等于 collect 总数），0 failed。** 日志在 `.scratch/chunks/`。
- **受影响的时序族满载复跑**：15 个烧机进程打满 16 核，跑「语音设置页 + 菜单域 + 语音报时服务（20 s tick / 后台合成线程 / QMediaPlayer）+ 设置页进程隔离 + 交互标签 + 设置与资源」共 **197 例 × 3 遍，每遍 `197 passed`**（73 / 73 / 76 s）。webm/ffmpeg 族本轮未碰、未满载。
- **Lead 复核**（本轮）：`ruff` 绿；`pytest -q tests/test_voice_chime_settings_layout.py tests/test_voice_chime_mimo.py tests/test_voice_chime.py tests/test_voice_chime_service.py tests/test_config_schema.py tests/test_architecture.py tests/test_menu_layout.py tests/test_no_credentials_in_source.py tests/test_no_console.py tests/test_tts_doubao.py` → **348 passed**；`modern_settings_dialog.py` **2401 行**（≤2405）、`window.py` **4489**（≤4510）。
- **真机观感**：以真实 Qt 窗口 `grab()` 截 8 张（`.scratch/shot-voice-*.png`：edge/doubao/mimo-展开 × 窗口/整页 + 720 px 窄 + 1600 px 宽），行序、文案、按钮、分隔线、窄宽度堆叠均正常。**未验**：150% 缩放 + 大字体下的换行、浅色主题（截图跟随本机＝深色）、钥匙串不可用支（「已保存（仅本次运行）」）只有单测覆盖。
- **真机使用旁证**：部署前读取机主本机 config，其 `voice_chime_tts_backend=doubao`、`voice_chime_doubao_speaker=zh_female_vv_uranus_bigtts`、`voice_chime_doubao_pitch=27` —— 即她**已在新语音页上自行改过音色与音调**（默认值改动不影响她，因为她有显式取值）。

## 未做 / 边界

1. 单进程全量 pytest 的原生崩溃**本轮不处理**（既存、非本次引入、历史同族先例），已在本报告如实登记。
2. 默认 `edge` 的连锁：目前只有 edge 声明 `is_fallback`，故默认 edge 时尝试链上只有它自己——失败即只出气泡，属既有语义；回退机制未改动，`DEV-HANDOVER` 已写明。
3. 环境陷阱（供后来者）：给全量 pytest 设 `PYTHONIOENCODING=utf-8` 会让 `test_module_level_validation`（用 `text=True` 按 GBK 解码子进程输出）**假红 3 条**；不要设。
