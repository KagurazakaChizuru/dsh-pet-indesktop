# -*- coding: utf-8 -*-
"""D12：独立设置进程 → 主进程的「退出子肥鱼」指令通道（零 Qt 纯逻辑）。

设计稿：``.scratch/single-overlay-window/PHASE4_DESIGN.md``（§4 D12 / §5 4.2c）。

问题：子肥鱼是**进程内 sprite**，独立设置进程（``--settings``，
settings.lock 单实例）里点「一键退出子肥鱼」无法跨进程删 sprite；已退役的
旧回退链（runtime 标记/slot 锁 + taskkill 子进程）在进程内形态下找不到任何
目标，按钮必然静默失效。

机制：设置进程把一条指令原子写进配置目录的运行时状态文件，主进程（overlay
壳 / legacy AppShell）经 config 目录 watcher + 定时轮询消费，命中后执行各自的
``clear_spawned_pets`` / ``exit_pet``。4.4b 起**两个拓扑共用这一条通道**（多进程
多宠退役层删除后不再有跨进程子宠；见 modern_settings_dialog._on_clear_spawned_pets）。

硬约束（本模块承载的纯逻辑部分）：

- **原子写**：临时文件 + ``os.replace``（命名与 ``overlay_spawn_state`` /
  ``Config.save`` 同惯例），读取方永远看到完整 JSON 或旧内容；
- **消费即删**：``consume_command`` 读到内容就摘除文件——包括损坏/未知/陈旧
  指令，否则 3s 轮询会把坏文件永远重放；读失败（被占用/权限）不摘除，留给下
  一轮重试，绝不吞掉用户的一次点击；
- **损坏/未知指令静默跳过**：返回 None + 一行日志，绝不抛给 GUI；
- **陈旧丢弃**：``issued_at`` 超过 ``DEFAULT_MAX_AGE_S`` 的指令视为"桌宠当时
  没在跑"，丢弃并留日志（否则设置页关掉桌宠后再开，会突然清空全部子肥鱼）；
- **身份**：``target`` 为 slot 编号 = 只退那一只；``None`` = 全部子肥鱼。

拓扑门 ``is_overlay_topology`` 也收口在本模块：设置进程必须按拓扑分流，而
``pet/__main__.py --settings`` 禁止导入重量级模块（pet.app / overlay_shell，
会连带素材库/ffmpeg/托盘），所以 env 读取的唯一实现放在这个零 Qt 模块，
``overlay_shell.is_overlay_topology`` 只做转发（对外入口名不变）。
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# T5：开发期一次性分流 flag（不进 Config/设置页/schema）。
ENV_TOPOLOGY = "PET_RENDER_TOPOLOGY"
TOPOLOGY_OVERLAY = "overlay"

# 指令文件：运行时状态文件，刻意不带 config- 前缀——既不进旧 slot 配置 glob
# （agent_link/config 迁移），也不与 runtime 标记 glob 相撞。与
# overlay-active-pets.json 平级。
COMMAND_FILENAME = "overlay-settings-command.json"
COMMAND_VERSION = 1

# 已知指令：设置页「一键退出子肥鱼」（全部子肥鱼 / 指定 slot 身份）。
CMD_EXIT_SPAWNED_PETS = "exit_spawned_pets"
KNOWN_COMMANDS = frozenset({CMD_EXIT_SPAWNED_PETS})

# 指令保鲜窗口：超过即视为"写下时主进程不在跑"。
DEFAULT_MAX_AGE_S = 120.0

_SLOT_INSTANCE_RE = re.compile(r"^slot-(\d+)$")


def is_overlay_topology() -> bool:
    """当前进程是否 overlay 拓扑（T5：唯一 env 读取实现）。

    T5 默认化：默认 overlay；``PET_RENDER_TOPOLOGY=legacy`` 为 dev 逃生门
    （不进 Config/设置页/schema，启动时定死不做运行时切换）。"""
    return os.environ.get(ENV_TOPOLOGY, "").strip().lower() != "legacy"


def slot_from_instance_id(instance_id) -> int | None:
    """``"slot-3"`` → 3；主身份/非法值 → None（纯逻辑，设置页分流用）。"""
    match = _SLOT_INSTANCE_RE.match(str(instance_id or "").strip())
    if match is None:
        return None
    return int(match.group(1))


def command_path(config_dir: Path | str) -> Path:
    """指令文件路径：``<config_dir>/overlay-settings-command.json``。"""
    return Path(config_dir) / COMMAND_FILENAME


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_target(target) -> int | None:
    """target 合法化：None 或 >=1 的 int；其它（含 bool/字符串）→ None 表示非法。"""
    if target is None:
        return None
    if isinstance(target, bool) or not isinstance(target, int):
        return None
    return target if target >= 1 else None


def write_command(config_dir: Path | str, command: str, *, target=None,
                  now: float | None = None, issuer_pid: int | None = None) -> bool:
    """原子写一条指令（tmp + ``os.replace``）。返回是否落盘成功。

    写失败只返回 False + 留日志，不抛：调用方是设置页按钮回调，环境不可写
    （只读盘/目录被文件占住）不该炸掉设置窗口。
    """
    name = str(command or "")
    if name not in KNOWN_COMMANDS:
        logger.warning("指令通道：拒绝写入未知指令 %r", command)
        return False
    clean_target = _normalize_target(target)
    if target is not None and clean_target is None:
        logger.warning("指令通道：拒绝写入非法 target %r", target)
        return False
    path = command_path(config_dir)
    payload = {
        "version": COMMAND_VERSION,
        "command": name,
        "target": clean_target,
        "issued_at": time.time() if now is None else float(now),
        "issuer_pid": os.getpid() if issuer_pid is None else int(issuer_pid),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        logger.warning("指令通道：写指令文件失败: %s", path, exc_info=True)
        return False
    return True


def _read_text(path: Path) -> str | None:
    """读指令文件正文；缺失返回空串语义（None=读不到，调用方区分处理）。

    返回 ``""`` 表示"文件不存在"（正常常态），返回 None 表示读失败
    （占用/权限/编码）——两者对调用方的处置不同：前者静默，后者保留重试。
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError:
        logger.warning("指令通道：指令文件不可读，留给下一轮重试: %s", path)
        return None


def _parse(raw: str, *, now: float, max_age_s: float) -> dict | None:
    """校验指令正文：损坏/未知/缺字段/陈旧一律 None + 日志（绝不抛）。"""
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("指令通道：指令文件损坏，已跳过")
        return None
    if not isinstance(data, dict):
        logger.warning("指令通道：指令不是对象，已跳过")
        return None
    if data.get("version") != COMMAND_VERSION:
        logger.warning("指令通道：指令版本不匹配 (%r)，已跳过", data.get("version"))
        return None
    name = data.get("command")
    if name not in KNOWN_COMMANDS:
        logger.warning("指令通道：未知指令 %r，已跳过", name)
        return None
    issued_at = _finite(data.get("issued_at"))
    if issued_at is None:
        logger.warning("指令通道：指令缺少合法 issued_at，已跳过")
        return None
    if now - issued_at > float(max_age_s):
        logger.warning("指令通道：陈旧指令已丢弃 (%.1fs 前)",
                       now - issued_at)
        return None
    target = data.get("target")
    if target is not None and _normalize_target(target) is None:
        logger.warning("指令通道：指令 target 非法 (%r)，已跳过", target)
        return None
    return {
        "version": COMMAND_VERSION,
        "command": str(name),
        "target": _normalize_target(target),
        "issued_at": issued_at,
        "issuer_pid": data.get("issuer_pid"),
    }


def read_command(config_dir: Path | str, *, now: float | None = None,
                 max_age_s: float = DEFAULT_MAX_AGE_S) -> dict | None:
    """诊断用读（**不消费**）：返回合法指令 dict，否则 None。"""
    raw = _read_text(command_path(config_dir))
    if not raw:
        return None
    return _parse(raw, now=time.time() if now is None else float(now),
                  max_age_s=max_age_s)


def consume_command(config_dir: Path | str, *, now: float | None = None,
                    max_age_s: float = DEFAULT_MAX_AGE_S) -> dict | None:
    """消费指令：读到内容即摘除文件，返回合法指令 dict（否则 None）。

    摘除在解析**之前**：坏文件也必须在一次消费里消失，否则 3s 轮询会永远重放
    同一份坏内容。摘除失败则本轮不执行（宁可漏一次点击，也不让同一条指令被
    反复执行）。读失败不摘除（下一轮重试）。
    """
    path = command_path(config_dir)
    raw = _read_text(path)
    if not raw:
        return None
    try:
        path.unlink()
    except FileNotFoundError:
        pass  # 已被别的消费者摘走（overlay 只有主进程消费，防御而已）
    except OSError:
        logger.warning("指令通道：指令文件摘除失败，本轮不执行: %s", path)
        return None
    return _parse(raw, now=time.time() if now is None else float(now),
                  max_age_s=max_age_s)
