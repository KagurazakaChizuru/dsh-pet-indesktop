# -*- coding: utf-8 -*-
"""overlay 文件投喂（4.1c）：拖文件喂 sprite。

旧链（file_eater.FileEaterDropHandler）是绑在 PetWindow 上的事件过滤器；
overlay 是全屏窗（逐像素穿透），拖放事件只在命中 sprite 的非透明区
才会送达——因此落点是 ShellOverlayWindow 的原生 dragEnter/drop 覆写，
命中判定复用 overlay.sprite_at（与穿透同一口径），统计/动画选择复用
file_eater 的模块级纯函数（不复制口径）。

- dragEnter/dragMove：本地文件 URL + 命中 sprite → acceptProposedAction，
  否则 ignore（事件落回下层应用——全屏 overlay 不抢桌面拖放）；
- drop：统计（file_eaten_stats.json 同格式同路径）+ 吃相关动画
  （_pick_eating_animation 同规则，经 behavior.play_once 一次性播放）+
  气泡反馈（_bubble_cb 接缝，4.1c-④ 气泡落地后接线，缺省静默）。
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from types import SimpleNamespace

from .file_eater import (
    STATS_FILE_NAME,
    STATS_HISTORY_LIMIT,
    _default_stats,
    _load_stats,
    _measure_path,
    _pick_eating_animation,
    _save_stats,
)

logger = logging.getLogger(__name__)


def _local_paths(mime) -> list[str]:
    if not mime.hasUrls():
        return []
    return [url.toLocalFile() for url in mime.urls()
            if url.isLocalFile() and url.toLocalFile()]


class SpriteFeedingController:
    """overlay 投喂控制器：统计 + 吃动画 + 气泡接缝（duck-typed config）。"""

    def __init__(self, overlay, sprite, config, behavior, *, rng=random) -> None:
        self._overlay = overlay
        self._sprite = sprite
        self._config = config
        self._behavior = behavior
        self._rng = rng
        cfg_dir = getattr(config, "dir", None)
        self.stats_path = Path(cfg_dir) / STATS_FILE_NAME if cfg_dir else None
        self._bubble_cb = None  # 4.1c-④ 气泡反馈接缝（shell 接线）
        # 解读询问接缝（壳接线，口径同旧 file_eater.eat_paths:183-186）：
        # 未注入（无聊天变体/未接线）时为 None，静默降级。
        self.interpret_offer = None

    # ---------------------------------------------------------------- 拖放判定
    def accepts(self, event) -> bool:
        paths = _local_paths(event.mimeData())
        return bool(paths) and self._overlay.sprite_at(event.position()) is not None

    def handle_drag_enter(self, event) -> None:
        if self.accepts(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def handle_drop(self, event) -> dict | None:
        paths = _local_paths(event.mimeData())
        if not paths or self._overlay.sprite_at(event.position()) is None:
            event.ignore()
            return None
        result = self.eat_paths(paths)
        event.acceptProposedAction()
        return result

    # ---------------------------------------------------------------- 反馈
    def eat_paths(self, paths) -> dict:
        """统计 + 吃动画 + 气泡（file_eater.eat_paths 同口径，文件保持不动）。"""
        files = folders = total_bytes = 0
        for raw in paths:
            fc, dc, size = _measure_path(Path(raw))
            files += fc
            folders += dc
            total_bytes += size
        stats = self._record(files, folders, files + folders, total_bytes)
        self._play_eating_animation()
        self._show_feedback(files, folders, total_bytes, stats)
        # 解读询问接缝（壳注入 FileInterpretController.offer；未注入/无聊天模块
        # 时为 None）——旧 ``file_eater.eat_paths`` 吃完后同一位置调用。
        offer = self.interpret_offer
        if callable(offer):
            offer(paths)
        return {"files": files, "folders": folders,
                "bytes": total_bytes, "stats": stats}

    def _record(self, files: int, folders: int, items: int, total_bytes: int) -> dict:
        if self.stats_path is None:
            return _default_stats()
        stats = _load_stats(self.stats_path)
        stats["feed_count"] += 1
        stats["file_count"] += max(0, files)
        stats["folder_count"] += max(0, folders)
        stats["item_count"] += max(0, items)
        stats["total_bytes"] += max(0, total_bytes)
        stats["history"].append({
            "time": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "files": max(0, files),
            "folders": max(0, folders),
            "bytes": max(0, total_bytes),
        })
        del stats["history"][:-STATS_HISTORY_LIMIT]
        _save_stats(self.stats_path, stats)
        return stats

    def _play_eating_animation(self) -> None:
        cats = self._behavior._categories(self._sprite.library)
        name = _pick_eating_animation(SimpleNamespace(acts=list(cats["acts"])))
        if name:
            self._behavior.play_once(self._sprite, name)

    def _show_feedback(self, files: int, folders: int, total_bytes: int,
                       stats: dict) -> None:
        cb = self._bubble_cb
        if callable(cb):
            try:
                cb(files, folders, total_bytes, stats)
            except Exception:
                logger.debug("overlay: 投喂气泡反馈失败", exc_info=True)
