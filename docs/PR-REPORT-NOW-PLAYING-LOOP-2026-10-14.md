# 歌词/会话采样链路：常驻事件循环（去掉每拍新建/销毁 asyncio 循环）—— 性能修复报告

> 分支 `perf/now-playing-loop`（基于 main `ffc80a6`）。范围：`pet/now_playing.py` 一个文件。
> 来源：2026-10-14 实机性能剖析（py-spy 火焰图 + 线程级采样），用户反馈"CPU/内存太高"。

## 一、修改文件说明

| 文件 | 增删 | 改了什么 + 为什么 |
|---|---|---|
| `pet/now_playing.py` | +19 / −5 | 新增 `_run_sync()`：调用线程的 thread-local 常驻事件循环；`skip_track` / `toggle_play_pause` / `play_session_for` / `get_now_playing` / 会话探针 `_facts_async_bounded` 共 5 处 `asyncio.run()` 换走它。原实现每拍采样都新建+销毁一个事件循环——py-spy 火焰图上 `new_event_loop`/线程引导合计占采样线程近一半（实测火焰图见下）。主线程不许跑 SMTC 查询的纪律不变（只是循环寿命变了）。 |

## 二、性能分析

实测（Win11，Python 3.13.7，无音乐播放——采样链的常态）：

| 口径 | 数字 | 样本 |
|---|---|---|
| 每拍采样耗时（旧 `asyncio.run`） | **3.7ms** | n=8 暖循环 |
| 每拍采样耗时（新常驻循环） | **2.3ms**（−38%） | n=8 暖循环 |
| 线程/循环抖动 | 每拍新建事件循环 → 不再新建 | py-spy 火焰图对照 |

- 稳态开销：采样线程每 1s 一拍（`POLL_MS`），每拍省 1.4ms；更大的收益在消除"每拍新建/销毁循环"的线程引导抖动（火焰图里 `_bootstrap`/`new_event_loop` 合计 ~6% 的 Python 采样份额消失）。
- 新增系统调用/网络/线程：**零**（循环复用，不新增任何东西；循环随线程退出由解释器回收）。
- 内存：常驻循环每线程一份（KB 级），换来不再每拍分配/释放整个循环。

## 三、实机运行记录

- 本机真机对比（上面表格的数字来源）：同机同状态跑 `pet.now_playing.get_now_playing()` 暖循环 8 拍取均值，新旧两份代码各一遍（旧代码在 `D:/dsh-pet-src-wt-release` 的 main 工作区，新代码在本分支工作区）。
- 测试：`tests/test_now_playing_{media_type,session,session_probe}.py` + `test_lyric_sources.py` + `test_music_lyric.py` → **192 passed**；ruff 零告警。
- 如实登记：无音乐播放时的 SMTC 查询本身（WinRT 调用）是每拍的大头，本片只去掉循环 churn；想让"没在播歌"更省，需要降频/会话监听驱动（后续片，见 `music_lyric_controller` 的采样节奏）。
