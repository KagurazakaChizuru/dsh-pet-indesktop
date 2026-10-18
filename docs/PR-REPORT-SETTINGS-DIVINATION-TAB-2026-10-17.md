# 「互动 · 抽签」标签改名「趣味」+ 一级域准入守卫

2026-10-17 · 分支 `fix/divination-tab-and-domain-guards` · 基于 `main` = `25feda10`

## 一、修改文件说明

`git diff --numstat main`（本报告文件本身不计入）：

| 文件 | + | − | 改了什么、为什么 |
|---|---|---|---|
| `pet/settings_interaction.py` | 8 | 5 | `TAB_LABELS` 第四项「抽签」→「**趣味**」。她的归类要求是「抽签这个功能…归类为趣味」（2026-10-15），原先只有卡片名是抽签、标签也叫抽签，等于归类没落地。**容器层级不变**：仍是「互动」域的页内标签，不开一级域（一级域须 ≥2 稳组，见下文守卫与 `SETTINGS-CHANGE-GATES` 2026-10-17 记录）。同时把那段注释改成说明"标签名承载分类语义、卡片名承载功能名" |
| `tests/test_settings_interaction_tabs.py` | 2 | 2 | 标签期望与 docstring 跟着改名 |
| `tests/test_settings_sidebar_and_chrome.py` | 40 | 0 | 新增守卫 `test_new_top_level_domain_must_own_at_least_two_setting_groups`：逐域数 `SettingsSection`，**新增**一级域 <2 组即红；`文件识别`/`更新` 两个历史单组域走快照豁免，并反向钉住它们仍是 1 组 |
| `docs/SETTINGS-CHANGE-GATES.md` | 14 | 0 | 追加 2026-10-17 第二轮的变更记录（无新增/删除设置项；写明"标签名 ≠ 容器层级"） |
| `docs/DEV-HANDOVER.md` | 6 | 2 | §3.1 行数预算表按实测校正：`window.py` 预算 **4671** / 实测 **4529**；`modern_settings_dialog.py` 预算 **2535** / 实测 **2535**（原表 4632 / 2347 是更早分支的快照，已漂移），并注明"表只是快照、真值在测试常量" |
| `docs/INDEX.md` | 1 | 0 | 本报告登记 |

**没有**新增/删除任何配置键、设置行、菜单项；`Config` 默认值与 reload 白名单未动。

## 二、性能分析

本改动在产品路径上**只有一个字符串常量**（标签文案），没有新增分支、IO、线程或缓存：

| 量 | 命令 | 结果 |
|---|---|---|
| 标签文案像素宽度 | `QFontMetrics(dialog.font()).horizontalAdvance(...)`，对话框字体 13px | 「抽签」**26px**、「趣味」**26px**、「点击与音效」65px —— **零布局变化**（同为 2 个汉字，字宽合计一致） |
| 设置对话框构造耗时 | 离屏构造 5 次取中位数：`ModernSettingsDialog(Config(base=tmp), include_ai=True)` + `show()` + `processEvents()` | `[1451.1, 792.8, 819.8, 941.7, 832.0]` ms，中位 **832.0ms**、最小 792.8、最大 1451.1 —— 与本改动无关（首轮偏大是首次导入/字体缓存） |
| 新增守卫的运行时成本 | 仅测试进程内构造一次对话框并 `findChildren`，产品代码零开销 | `-k top_level_domain` 单跑 3.1–3.6s（与相邻用例同量级） |

环境：Windows 11 24H2 (26100)、PySide6 6.x、`QT_QPA_PLATFORM=offscreen`、样本量 5（构造耗时）/ 1 次渲染（字宽）。

## 三、实机运行记录

1. **标签实际渲染值**（真实 Qt 对象，非 mock）：
   ```
   TAB_KEYS   = ('click', 'self_talk', 'weather', 'divination')
   TAB_LABELS = ('点击与音效', '自言自语', '天气', '趣味')
   ```
2. **守卫不是摆设（旧红新绿）**：把快照里的「更新」临时移出 →
   `1 failed, 18 deselected`；恢复 → `1 passed, 18 deselected`。
3. **三道本地门**：
   - `ruff check .` → `All checks passed!`
   - 受影响族高负载复跑 3 遍 → `89 passed` / `89 passed` / `89 passed`
   - 全量 `scripts/ci_shards.py`（四片独立进程）→ 结果见 PR 描述
4. **界面行为**：侧栏仍是 10 个一级域、默认 800×560 下无需滚动（`test_default_window_shows_every_domain_without_scrolling` 通过）；「互动」域的四个页内标签按 `点击与音效 / 自言自语 / 天气 / 趣味` 排列，卡片名仍是「抽签」。

## 四、已知限制

- 标签名与卡片名不同（趣味 / 抽签）是**有意为之**：前者是分类语义、后者是功能名。若以后趣味域下真的长出第二个稳定设置组，应当**那时**再开一级域，并让守卫放行（它只对 <2 组的新域报错）。
- 预算表是快照，改预算常量时需同步 `docs/DEV-HANDOVER.md` §3.1（本报告已把该提示写进表下方）。
