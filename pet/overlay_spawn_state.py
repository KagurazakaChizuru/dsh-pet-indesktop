# -*- coding: utf-8 -*-
"""Phase 4.2b：overlay 拓扑的活跃宠集合 + 无锁 slot 身份分配 + 每身份几何持久化。

设计稿：.scratch/single-overlay-window/PHASE4_DESIGN.md（D5/D6/T5）。

- **D5 活跃宠集合**：启动恢复依据 = 显式"活跃宠"清单（运行时状态文件
  ``overlay-active-pets.json``），**不是**"slot 配置存在"。旧多进程路径里
  "退出子肥鱼"只关进程、slot 配置保留；若按配置存在复活，退出的子肥鱼会在
  重启后复活，与旧语义冲突。清单是运行时状态，不进 Config schema/设置页。
- **D6 无锁 slot 分配器**：进程内扫 ``config-slot-N.json`` + 活跃身份分配
  最小空闲 N，替代 ``spawn_in_process_window`` 的文件锁分配（app.py:2789-2807
  旧语义）。overlay 拓扑由 D4 进程门保证单实例，不再需要 slot 锁做跨进程互斥。
- **每身份几何持久化**：每只子肥鱼按各自 slot 身份把 rx/ry/facing/scale 合并
  写回 ``config-slot-N.json``（命名冻结：``agent_link.other_instances_use_agent``
  依赖 ``config-*.json`` glob，T5）。

纯逻辑零 Qt（便于单测）：磁盘访问只走 Path + json，写盘原子（tmp + replace，
对齐 Config.save / slot_manager 既有惯例）。
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from pathlib import Path

from .config import atomic_replace_with_retry

# 活跃宠清单：运行时状态文件。刻意不带 config- 前缀——既不进旧 slot 配置
# glob（agent_link/config 迁移），也不与 runtime 标记 glob 相撞。
ACTIVE_PETS_FILENAME = "overlay-active-pets.json"
ACTIVE_PETS_VERSION = 1
# slot 扫描上限（128：与前垃圾槽位分配器的 max_scan_slots 同口径）
MAX_SCAN_SLOTS = 128

_GEOMETRY_KEYS = ("rx", "ry", "facing", "scale")
_SLOT_CONFIG_RE = re.compile(r"^config-slot-(\d+)\.json$")


class SpawnStateError(Exception):
    """slot 身份分配失败（前 MAX_SCAN_SLOTS 个身份均被占用）。"""


# ------------------------------------------------------------------ 活跃宠清单
def active_pets_path(config_dir: Path | str) -> Path:
    """活跃宠清单路径：``<config_dir>/overlay-active-pets.json``。"""
    return Path(config_dir) / ACTIVE_PETS_FILENAME


def normalize_slots(slots) -> list[int]:
    """去重并保持顺序的正整数 slot 列表（非法条目丢弃）。"""
    result: list[int] = []
    seen: set[int] = set()
    for item in slots or ():
        try:
            slot = int(item)
        except (TypeError, ValueError):
            continue
        if slot < 1 or slot in seen:
            continue
        seen.add(slot)
        result.append(slot)
    return result


def load_active_slots(config_dir: Path | str) -> list[int]:
    """读活跃宠清单（spawn 顺序）。

    防御性回退：文件缺失 = 首次运行语义（旧版主配置兼容）；文件损坏、不是
    对象、缺首字段 ``version``、``slots`` 非列表 → 一律按"只有主宠"处理
    （返回空清单），绝不把损坏状态当成活跃集合。
    """
    path = active_pets_path(config_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        logging.warning("overlay: 活跃宠清单不可读，按只有主宠处理: %s", path)
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        logging.warning("overlay: 活跃宠清单损坏，按只有主宠处理: %s", path)
        return []
    if not isinstance(data, dict) or data.get("version") != ACTIVE_PETS_VERSION:
        logging.warning("overlay: 活跃宠清单缺首字段 version，按只有主宠处理: %s", path)
        return []
    slots = data.get("slots")
    if not isinstance(slots, list):
        logging.warning("overlay: 活跃宠清单 slots 非法，按只有主宠处理: %s", path)
        return []
    return normalize_slots(slots)


def save_active_slots(config_dir: Path | str, slots) -> bool:
    """原子写活跃宠清单（tmp + os.replace，瞬时占用有界重试）。返回是否落盘成功。"""
    path = active_pets_path(config_dir)
    payload = {
        "version": ACTIVE_PETS_VERSION,
        "slots": normalize_slots(slots),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            atomic_replace_with_retry(temp, path)
        finally:
            temp.unlink(missing_ok=True)
    except OSError:
        logging.warning("overlay: 写活跃宠清单失败: %s", path, exc_info=True)
        return False
    return True


# ------------------------------------------------------------------ 无锁 slot 分配
def slot_config_path(config_dir: Path | str, slot_id: int) -> Path:
    """slot 身份对应的配置文件路径（命名冻结，T5）。"""
    return Path(config_dir) / f"config-slot-{int(slot_id)}.json"


def scan_slot_configs(config_dir: Path | str | None) -> set[int]:
    """扫目录内已有 ``config-slot-N.json`` 的 slot 编号集合（无目录 → 空集）。"""
    if not config_dir:
        return set()
    try:
        files = list(Path(config_dir).glob("config-slot-*.json"))
    except OSError:
        return set()
    slots: set[int] = set()
    for path in files:
        match = _SLOT_CONFIG_RE.match(path.name)
        if match:
            slots.add(int(match.group(1)))
    return slots


def allocate_slot(config_dir: Path | str | None = None, *, active_slots=(),
                  max_slots: int = MAX_SCAN_SLOTS) -> int:
    """无锁身份分配（D6）：取最小空闲 N。

    已占用 = 目录内已有 ``config-slot-N.json`` 的身份 ∪ 进程内活跃身份。
    slot 配置身份一经分配即保留（"退出子肥鱼配置保留"），因此分配单调增长、
    永不与既有身份相撞——复用一个保留身份会静默覆盖它的位置/设置记忆。
    """
    taken = scan_slot_configs(config_dir)
    for slot in normalize_slots(active_slots):
        taken.add(slot)
    for candidate in range(1, int(max_slots) + 1):
        if candidate not in taken:
            return candidate
    raise SpawnStateError(f"overlay: 前 {max_slots} 个 slot 身份均已被占用")


def _load_slot_config(config_dir: Path | str, slot_id: int) -> dict:
    """读 slot 配置原始 dict；缺失/损坏/非对象 → 空 dict（不落盘、不报错）。"""
    try:
        raw = slot_config_path(config_dir, slot_id).read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logging.warning("overlay: slot 配置损坏，几何按未记录处理: %s",
                        slot_config_path(config_dir, slot_id))
        return {}
    return data if isinstance(data, dict) else {}


def _finite(value):
    """有限浮点（NaN/Inf/非数值 → None）。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean_geometry(geometry) -> dict:
    """只保留合法几何键（rx/ry 有限数、facing 枚举、scale 正有限数）。"""
    result: dict = {}
    if not isinstance(geometry, dict):
        return result
    for key in ("rx", "ry"):
        number = _finite(geometry.get(key))
        if number is not None:
            result[key] = number
    facing = geometry.get("facing")
    if facing in ("left", "right"):
        result["facing"] = facing
    scale = _finite(geometry.get("scale"))
    if scale is not None and scale > 0:
        result["scale"] = scale
    return result


def slot_config_exists(config_dir: Path | str, slot_id: int) -> bool:
    """slot 身份配置文件是否存在（复活前置：身份记忆还在才复活）。"""
    try:
        return slot_config_path(config_dir, slot_id).is_file()
    except OSError:
        return False


def read_slot_geometry(config_dir: Path | str, slot_id: int) -> dict:
    """读 slot 身份持久化的几何（rx/ry/facing/scale）；无记录/损坏 → 空 dict。"""
    return _clean_geometry(_load_slot_config(config_dir, slot_id))


def read_slot_config(config_dir: Path | str, slot_id: int) -> dict | None:
    """读 slot 身份配置的原始 dict（**通用只读读点**，B7b 的 per-slot 取源入口）。

    旧实现（base-2786c15）：每只桌宠是独立进程、各读自己的
    ``config-slot-N.json``（``Config(instance_id="slot-N")`` + ``window.py``
    逐键读 ``self.cfg``）。单进程壳只有一份主配置，per-slot 取源必须从这份文件
    读回来——本函数就是那条"读点"，语义与 ``Config`` 的加载口径对齐：

    - 文件缺失 / 不可读 → ``None``：旧启动语义是"按主配置落种"，调用方据此
      **继承主配置**（不是回默认值）；
    - 内容损坏（非 JSON）→ ``{}``：旧 ``Config.reload`` 的口径是备份 + 整份回
      默认值；这里**只读**（不备份、不落盘、不改主配置），空 dict 让调用方逐键
      走默认值回退；
    - 非法 JSON 类型（数组/标量）→ ``{}``（同上）；
    - 合法对象 → 原样 dict（含空对象 ``{}``）。

    纯读、无副作用；调用方负责缓存（配置同步边界读一次，不逐帧读）。
    """
    if not slot_config_exists(config_dir, slot_id):
        return None
    data = _load_slot_config(config_dir, slot_id)
    return data if isinstance(data, dict) else {}


def write_slot_setting(config_dir: Path | str, slot_id: int, key: str, value,
                       *, user_customized: bool | None = None) -> bool:
    """把**一个** sprite 级设置键写进该 slot 身份配置（保留其它键；原子替换）。

    B7b：子肥鱼右键菜单/切角色的设置曾经只改运行态（写主配置会污染主宠），
    按旧契约它们本该落到**这只子肥鱼自己的** ``config-slot-N.json``——旧架构
    里"右键改大小"就是这个语义（``window.py:998-1001``：写本窗 cfg + 置位
    ``user_customized``）。

    ``user_customized=True``（用户主动设置）时一并置位该旗标，与旧契约一致：
    ``seed_slot_config_from_main`` 对已自定义的 slot 一个键都不碰（下次生成
    不被主设置刷新）。位置/朝向等后台自存写盘**不置位**（见
    ``write_slot_geometry``）——调用方按需传 None 保持原值。
    """
    name = str(key or "").strip()
    if not name:
        return False
    path = slot_config_path(config_dir, slot_id)
    data = _load_slot_config(config_dir, slot_id)
    data.setdefault("version", 4)
    data[name] = value
    if user_customized is not None:
        data["user_customized"] = bool(user_customized)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            atomic_replace_with_retry(temp, path)
        finally:
            temp.unlink(missing_ok=True)
    except OSError:
        logging.warning("overlay: 写 slot 设置键失败: %s (%s)", path, name,
                        exc_info=True)
        return False
    return True


def read_slot_collision_enabled(config_dir: Path | str, slot_id: int, *,
                                default: bool = True,
                                fallback: bool | None = None) -> bool:
    """读 slot 身份配置里的 ``collision_enabled``（旧契约：每只桌宠各自的 config）。

    旧实现（base-2786c15）：子宠进程按 ``--instance slot-N`` 起自己的 ``Config``
    （``config.py:683-689``：该 slot 文件不存在 → 先按主配置落种；存在 → 一个键
    都不碰），运行期读的也是**自己的** ``config-slot-N.json``（``window.py:3929``
    ``bool(self.cfg.get('collision_enabled', True))``）。本函数把这条语义收敛成
    一个只读"读点"：

    - 文件存在 + 键合法（``config._bool_or_default`` 口径，字符串 true/false 也认）
      → 该值；
    - 文件存在但缺键 / 值为 None / 类型非法 → ``default``（旧 Config 清洗填默认）；
    - 文件缺失 → ``fallback``（旧启动语义是"按主配置落种"，即继承主配置当前值；
      未给 ``fallback`` 时退 ``default``）；
    - 文件损坏 / 非 JSON 对象 → ``default``（旧 ``Config.reload`` 是备份 + 回默认
      值；这里**只读**：不备份、不落盘、绝不改主配置或别宠的文件）。

    纯读、无副作用；只在配置同步边界调用（不逐帧；目录事件与壳既有的 3s 兜底
    轮询都会触发，属既有轮询通道，非新增）。
    """
    if not slot_config_exists(config_dir, slot_id):
        return bool(default if fallback is None else fallback)
    data = _load_slot_config(config_dir, slot_id)
    if not data:
        return bool(default)  # 损坏/非对象/空对象：旧 Config 的默认值回退口径
    from .config import _bool_or_default  # 惰性：避免 config ↔ 本模块的导入环

    return bool(_bool_or_default(data.get("collision_enabled"), default))


def write_slot_geometry(config_dir: Path | str, slot_id: int, geometry) -> bool:
    """把几何键合并写回 slot 配置（保留该身份其它键；原子替换）。

    只覆盖几何键，绝不整文件重写：``config-slot-N.json`` 是该子肥鱼的完整
    配置身份（可能由 slot 落种/用户设置写就），几何只是其中一部分。
    """
    clean = _clean_geometry(geometry)
    if not clean:
        return False
    path = slot_config_path(config_dir, slot_id)
    data = _load_slot_config(config_dir, slot_id)
    data.setdefault("version", 4)
    data.update(clean)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            atomic_replace_with_retry(temp, path)
        finally:
            temp.unlink(missing_ok=True)
    except OSError:
        logging.warning("overlay: 写 slot 几何失败: %s", path, exc_info=True)
        return False
    return True
