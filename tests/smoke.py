# -*- coding: utf-8 -*-
"""
Smoke test for the webm-backed media layer + window behavior（真实 webm 素材）。

Run: python tests/smoke.py
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from pet import catalog  # noqa: E402
from pet.config import Config  # noqa: E402
from pet.library import MovieLibrary  # noqa: E402
from pet.window import PetWindow  # noqa: E402

#: 素材数量的**下界**（2026-09-17 实测 106 段）。用下界而不是精确值：加素材不会假红，
#: 而"素材被整体/大面积删掉"能被抓住。校准方式与行数预算一致：只随实测调整并注明日期。
MIN_EXPECTED_CLIPS = 100


def _wait_until(app: QApplication, predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timeout waiting for condition")


def main() -> int:
    app = QApplication([])
    lib = MovieLibrary()  # 真实 webm：assets/videos

    # 1. 素材全量可加载，帧数/时长有效
    #    ⚠ 本脚本**不被 pytest 收集**，也不在 run-gates.ps1 / CI 里，只能手工运行；
    #    因此断言要刻意避免"同义反复"——早先写成 set(names) == 目录 rglob(...)（与
    #    library 同一来源），实测删掉 40/106 段素材仍然 PASS。
    names = lib.names()
    asset_dir = catalog.resolve_character_video_dir(catalog.DEFAULT_CHARACTER)
    assert len(names) >= MIN_EXPECTED_CLIPS, f"素材疑似丢失：{len(names)} < {MIN_EXPECTED_CLIPS}"
    # 核心动画必须都在：针对性删掉 idle/turn/drag/moves 会被这条抓住
    for core in (catalog.IDLE, catalog.TURN, catalog.DRAG, *catalog.MOVES):
        assert core in names, f"核心动画缺失：{core}"
    for name in names:
        # 每个名字都必须解析到**真实存在**的素材文件（库说有、盘上没有 → 红）
        path = lib.clip_path(name)
        assert path is not None and os.path.exists(path), name
        assert lib.frames(name) >= 1, (name, lib.frames(name))
        assert lib.duration(name) > 0, (name, lib.duration(name))

    # 2. 透明通道：待机首帧同时含透明与不透明像素
    idle = lib.movie(catalog.IDLE)
    idle.jumpToFrame(0)
    img = idle.currentPixmap().toImage()
    alphas = set()
    for x in range(0, img.width(), 20):
        for y in range(0, img.height(), 10):
            alphas.add(img.pixelColor(x, y).alpha())
    assert len(alphas) >= 2, sorted(alphas)

    # 3. 播放推进
    idle.start()
    _wait_until(app, lambda: idle.currentFrameNumber() >= 1)
    assert idle.currentFrameNumber() >= 1
    idle.stop()

    # 4. 窗口实例化：尺寸/初始动画/透明 mask
    cfg = Config(base=os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_cfg"))
    win = PetWindow(lib, cfg)
    win.show()
    assert win.anim == catalog.IDLE
    # 核心分类必须都被识别出来（任一为空说明分类回归）
    assert win.idles and win.turns and win.clicks and win.acts, (
        len(win.idles), len(win.turns), len(win.clicks), len(win.acts))
    # 可见轮廓：走公有 API `character_local_region()`（轮廓未算出时它返回整块画布，
    # 所以"变小了"即说明轮廓已算出），不再断言私有 `_mask_bounds`。
    # mask() 的平台语义单独断言：Windows 上按设计**不再 setMask**（1-bit 裁剪会破坏
    # 半透明边缘，见 window.py 的 _sync_mask），因此 mask() 恒为空才是正确行为。
    _wait_until(
        app,
        lambda: (
            win.character_local_region().width() < catalog.CANVAS_W
            or win.character_local_region().height() < catalog.CANVAS_H
        ),
        timeout=8.0,
    )
    region = win.character_local_region()
    assert 0 < region.width() <= catalog.CANVAS_W, region
    assert 0 < region.height() <= catalog.CANVAS_H, region
    if os.name == "nt":
        assert win.mask().isEmpty(), "Windows 路径不应 setMask"
    else:
        assert not win.mask().isEmpty(), "非 Windows 应 setMask 出透明穿透区域"
    assert win.width() == int(round(catalog.CANVAS_W * win.scale))
    assert win.height() == int(round((catalog.CANVAS_H + catalog.PAD) * win.scale))

    # 5. 缩放：底边不动
    bottom = win.geometry().bottom()
    win.change_scale(1.25)
    assert win.geometry().bottom() == bottom
    assert win.width() == int(round(catalog.CANVAS_W * 1.25))
    win.change_scale(1.0)

    # 6. 点击回应：仅待机时可点；播完回待机缓冲
    win._on_click()
    # 用窗口实际识别出的 click 分类，并核对它对应**真实存在**的素材文件；
    # 不用 catalog.CLICKS —— 那是脱节的旧常量表（名字带空格，与真实文件名对不上）
    assert win.anim in win.clicks, win.anim
    assert os.path.exists(os.path.join(asset_dir, "click", f"{win.anim}.webm")), win.anim
    win._on_anim_ended(win.anim)
    assert win.anim == catalog.IDLE

    # 7. 转向：东张西望播完翻转朝向
    facing_before = win.facing
    win._switch(catalog.TURN)
    win._on_anim_ended(catalog.TURN)
    assert win.facing != facing_before

    # 8. 移动：空间足够则生成移动计划（帧驱动位移：tick 只做守卫，位置随解码帧推进）
    win._cancel_move()
    ok = win._try_move()
    assert isinstance(ok, bool)
    if ok:
        assert win._move_plan is not None
        x0 = win.x()
        win._on_move_tick()
        assert win.x() == x0  # tick 不再插值：位置完全由 _on_frame 帧驱动
        win._cancel_move()

    # 9. 「不移动」：状态机不再进入移动动画；手动移动仍可走动；开关持久化
    win.set_no_move(True)
    assert win.no_move is True and cfg.get("no_move") is True
    for _ in range(200):
        win._cancel_move()
        win._pick_next()
        assert win.anim not in catalog.MOVES, win.anim
    win._cancel_move()
    win._trigger_move(catalog.MOVES[0])
    assert win.anim in catalog.MOVES, win.anim
    win._cancel_move()
    win.set_no_move(False)
    assert win.no_move is False and cfg.get("no_move") is False

    win.close()
    print("\n=== ALL SMOKE TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())