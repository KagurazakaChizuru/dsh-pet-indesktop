# -*- coding: utf-8 -*-
"""打包前帧序列完整性硬门（scripts/check_frameseq_bundle.py）测试。

素材树全部用 ``tmp_path`` 造（不碰真实 106 段 / 53MB 素材），每个用例只注入
一种缺陷，断言**退出码 + 报错关键词**——门是构建管线的一环，它的契约就是
「非零退出 + 说清怎么补」。

四类断言：

1. 判定行为：完整树 0 退出；缺子树 / 缺单段产物 / 世代档陈旧 / meta 损坏
   逐类 1 退出，且报错能指出路径与补法；
2. 硬约束：零 Qt 零第三方依赖（AST 扫 import）、只读（跑完素材树字节级不变）；
3. 接线：``build_onedir.ps1`` 的非 GIF 分支在 PyInstaller 起跑前调用本门、
   非零即中止，GIF 分支跳过；``build_macos.sh`` / ``build_linux.sh`` 同口径
   （源码文本断言——行为测试看不到「有没有接上」）；
4. 供给入口（``scripts/prepare_frameseq_bundle.py``，2026-10-11）：先跑本门验证
   素材是否完整，缺才调 ``tools/convert_frameseq.py``，转完再验一次；**坏缓存
   不许被盲跳过**（唯一放行依据是验证器的真实退出码）。命令委派用注入的假
   runner 断言（不真转 106 段 / 28 min），缓存 key 的构件逐条断言可复现。

世代常量与 ``pet/frameseq_provision.py`` 的同源性由 ``TestGenerationHomology``
从 provision 源码**文本提取**后逐条比对：provision 改档而门内常量没跟，即红。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_frameseq_bundle.py"
BUILD_SCRIPT = ROOT / "scripts" / "build_onedir.ps1"
PROVISION_SOURCE = ROOT / "pet" / "frameseq_provision.py"

# 旧档串（改档前的产物）：用来构造「世代陈旧」的假素材。取自
# pet/frameseq_provision.py 的 LEGACY_ENCODER_DESCS，只作测试输入。
LEGACY_ENCODER = "libwebp lossy q70 (bgra straight, unblend-white)"
# 旧反解标记（v2）
LEGACY_UNBLEND = "white"
# **刚被取代的那一代**（v3）：改档到 v5 后，磁盘上现存的产物正是这一档——构建门
# 必须判它陈旧（否则 v3 素材会被静默打进包，用户看到的就是带 a==1 底板的桌宠）。
SUPERSEDED_ENCODER = "libwebp lossy q70 (bgra straight, unblend-white-v3)"
SUPERSEDED_UNBLEND = "white-v3"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_frameseq_bundle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclass 装饰器依赖模块已在 sys.modules 里（按路径加载不会自动登记）
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()


# --------------------------------------------------------------------------- 造素材


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _other_stamp_sha(digest: str) -> str:
    """另一份源的 sha，**前缀就与目录戳不符**（首字符换掉即错开前 12 位）。"""
    head = "f" if not digest.startswith("f") else "0"
    return head * GATE.GEN_STAMP_HEX + digest[GATE.GEN_STAMP_HEX:]


def _other_source_sha(digest: str) -> str:
    """另一份源的 sha，**前缀与目录戳一致**、尾部不同（冒充戳但指向别的源）。"""
    last = "0" if digest[-1] != "0" else "1"
    return digest[:-1] + last


def _make_clip(
    characters_dir: Path,
    character: str,
    stem: str,
    *,
    folder: str = "idle",
    generation: bool = True,
    encoder: str | None = None,
    unblend: str | None = None,
    meta: str = "ok",
    meta_frames: int = 1,
    frame_files: int = 1,
) -> tuple[Path, Path]:
    """造一段假 clip：webm +（可选）其世代目录与 meta.json。

    ``meta`` 取值：``"ok"`` 当前档 / ``"missing"`` 不写 meta.json /
    ``"corrupt"`` 写坏 JSON。``meta_frames`` / ``frame_files`` 用来造
    「meta 记 24 帧、磁盘只有 3 帧」这类半成品世代目录。
    """
    videos = characters_dir / character / "videos" / folder
    videos.mkdir(parents=True, exist_ok=True)
    webm = videos / f"{stem}.webm"
    webm.write_bytes(b"fake-webm:" + stem.encode("utf-8"))
    if not generation:
        return webm, Path()
    digest = _sha256(webm)
    gen = (characters_dir / character / "frameseq" / folder
           / f"{stem}{GATE.GEN_INFIX}{digest[:GATE.GEN_STAMP_HEX]}")
    gen.mkdir(parents=True, exist_ok=True)
    for index in range(frame_files):
        (gen / f"f_{index + 1:04d}.webp").write_bytes(b"frame")
    if meta == "missing":
        return webm, gen
    if meta == "corrupt":
        (gen / "meta.json").write_text("{ 这不是 JSON", encoding="utf-8")
        return webm, gen
    payload = {
        "fps": 24.0,
        "source": f"{stem}.webm",
        "frames": meta_frames,
        "encoder": GATE.ENCODER_DESC if encoder is None else encoder,
        "unblend": GATE.UNBLEND_MARK if unblend is None else unblend,
        "source_sha256": digest,
    }
    (gen / "meta.json").write_text(json.dumps(payload), encoding="utf-8")
    return webm, gen


def _patch_source_sha(gen: Path, value: str | None) -> None:
    """改写世代目录 meta.json 的 ``source_sha256``（``None`` = 删掉该键）。"""
    path = gen / "meta.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if value is None:
        payload.pop("source_sha256", None)
    else:
        payload["source_sha256"] = value
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run(characters_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--characters-dir", str(characters_dir)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(ROOT), check=False,
    )


def _snapshot(root: Path) -> list[tuple[str, int, int]]:
    return sorted(
        (str(path.relative_to(root)), path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
    )


# --------------------------------------------------------------------------- 判定行为


class TestGateVerdicts:
    def test_complete_tree_passes(self, tmp_path):
        characters = tmp_path / "characters"
        for character in ("shenshen", "other"):
            for stem in ("待机呼吸休闲", "左转奔跑", "写代码"):
                _make_clip(characters, character, stem, meta_frames=3, frame_files=3)
        result = _run(characters)
        assert result.returncode == 0, result.stderr
        assert "shenshen: 3 个 clip" in result.stdout
        assert "other: 3 个 clip" in result.stdout
        # 摘要要交代世代档（构建日志里能看见以哪一档为基准放行）
        assert GATE.ENCODER_DESC in result.stdout
        assert GATE.UNBLEND_MARK in result.stdout

    def test_nested_clip_folder_passes(self, tmp_path):
        # events/balance 这类二级目录也在门内（rglob 口径）
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "余额播报", folder="events/balance")
        result = _run(characters)
        assert result.returncode == 0, result.stderr

    def test_missing_frameseq_subtree_fails(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "待机呼吸休闲", generation=False)
        result = _run(characters)
        assert result.returncode == 1
        assert "frameseq" in result.stderr
        assert "待机呼吸休闲" in result.stderr
        # 报错必须说清怎么补（同步素材源 / 先跑离线供给）
        assert "同步" in result.stderr

    def test_missing_single_clip_fails(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "待机呼吸休闲")
        _, stale_gen = _make_clip(characters, "shenshen", "左转奔跑")
        # 只剩旧戳目录（模拟源已换版 / 产物没跟上）：当前戳目录不存在
        for item in stale_gen.iterdir():
            item.unlink()
        stale_gen.rmdir()
        result = _run(characters)
        assert result.returncode == 1
        assert "左转奔跑" in result.stderr
        assert "缺" in result.stderr
        assert "待机呼吸休闲" not in result.stderr  # 完好 clip 不误报

    def test_stale_encoder_fails(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码", encoder=LEGACY_ENCODER)
        result = _run(characters)
        assert result.returncode == 1
        assert "世代" in result.stderr
        assert LEGACY_ENCODER in result.stderr  # 报错要给出实际档串
        assert GATE.ENCODER_DESC in result.stderr  # 与当前档对照

    def test_stale_unblend_mark_fails(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码", unblend=LEGACY_UNBLEND)
        result = _run(characters)
        assert result.returncode == 1
        assert "世代" in result.stderr
        assert LEGACY_UNBLEND in result.stderr

    def test_superseded_v3_generation_fails(self, tmp_path):
        """刚被取代的 v3 产物：构建期同样判陈旧（磁盘上现存素材正是这一档）。"""
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码",
                   encoder=SUPERSEDED_ENCODER, unblend=SUPERSEDED_UNBLEND)
        result = _run(characters)
        assert result.returncode == 1, result.stdout
        assert "世代" in result.stderr
        assert SUPERSEDED_ENCODER in result.stderr
        assert GATE.ENCODER_DESC in result.stderr
        # 同源守卫：这一档必须在 provision 的 LEGACY 清单里（改档不许漏登记）
        assert SUPERSEDED_ENCODER in PROVISION_SOURCE.read_text(encoding="utf-8")

    def test_corrupt_meta_fails(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码", meta="corrupt")
        result = _run(characters)
        assert result.returncode == 1
        assert "meta.json" in result.stderr

    def test_missing_meta_file_fails(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码", meta="missing")
        result = _run(characters)
        assert result.returncode == 1
        assert "meta.json" in result.stderr

    def test_partial_frame_set_fails(self, tmp_path):
        # 半成品世代目录（meta 记 24 帧、磁盘只有 3 帧）：运行时采纳闸门会拒收，
        # 用户看到的就是未转换素材——构建门必须拦住
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码", meta_frames=24, frame_files=3)
        result = _run(characters)
        assert result.returncode == 1
        assert "帧数" in result.stderr
        assert "24" in result.stderr and "3" in result.stderr

    def test_zero_frame_generation_fails(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码", meta_frames=0, frame_files=0)
        result = _run(characters)
        assert result.returncode == 1
        assert "帧数" in result.stderr

    def test_absent_characters_dir_fails(self, tmp_path):
        result = _run(tmp_path / "nope")
        assert result.returncode == 1
        assert "assets" in result.stderr or "素材" in result.stderr

    def test_empty_material_tree_fails(self, tmp_path):
        # 素材树在但没有一个 clip：构建环境异常，不许静默放行
        characters = tmp_path / "characters"
        (characters / "shenshen" / "videos").mkdir(parents=True)
        result = _run(characters)
        assert result.returncode == 1
        assert "webm" in result.stderr

    def test_failure_list_capped_at_twenty(self, tmp_path):
        characters = tmp_path / "characters"
        # 先造一段完好的 clip，让 frameseq 子树存在 → 25 段缺产物落到「单段缺产物」类
        _make_clip(characters, "shenshen", "待机呼吸休闲")
        for index in range(25):
            _make_clip(characters, "shenshen", f"缺失段{index:02d}", generation=False)
        result = _run(characters)
        assert result.returncode == 1
        listed = [line for line in result.stderr.splitlines() if line.startswith("    - ")]
        assert len(listed) == 20, result.stderr
        assert "其余 5 条省略" in result.stderr

    def test_multiline_reporting_covers_each_class(self, tmp_path):
        # 四类缺陷同场：每一类都要出现在报错里（不因先出现的类别吞掉后面的）
        characters = tmp_path / "characters"
        _make_clip(characters, "完整的", "待机呼吸休闲")
        _make_clip(characters, "缺产物的", "写代码", generation=False)
        _make_clip(characters, "档陈旧的", "左转奔跑", encoder=LEGACY_ENCODER)
        _make_clip(characters, "meta坏的", "漂浮踏步", meta="corrupt")
        result = _run(characters)
        assert result.returncode == 1
        for needle in ("frameseq", "缺", "世代", "meta.json"):
            assert needle in result.stderr
        for character in ("缺产物的", "档陈旧的", "meta坏的"):
            assert character in result.stderr


# --------------------------------------------------------------------------- 源身份（astra F4）


class TestSourceIdentity:
    """``meta.source_sha256`` 是运行时采纳条件，构建门必须同样验。

    运行时（``pet/frameseq_provision.py::_complete_meta`` / ``current_generation``）
    要求三件事同时成立：摘要是 64 位小写十六进制 ∧ 以世代目录戳（目录名前 12 位）开头
    ∧ 等于**当前源 webm 的完整 sha256**。目录名对了而摘要缺失 / 非 hex / 与戳不符 /
    指向另一份源时运行时拒收那份产物并回退 WebM 播放——用户看到的就是未转换素材，
    正是这道门要拦的静默缺口。
    """

    @staticmethod
    def _clip_with_identity(tmp_path, mutate) -> Path:
        """造一段 clip，再按 ``mutate(digest) -> str | None`` 改写 meta 的源摘要。"""
        characters = tmp_path / "characters"
        webm, gen = _make_clip(characters, "shenshen", "写代码")
        _patch_source_sha(gen, mutate(_sha256(webm)))
        return characters

    def test_valid_identity_passes(self, tmp_path):
        # 正例守卫：真实摘要（默认写法）必须放行，新校验不许误伤
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码")
        report = GATE.check_bundle(characters)
        assert report.ok, report.problems
        assert _run(characters).returncode == 0

    def test_missing_source_sha_fails(self, tmp_path):
        """旧版无戳产物（meta 没有 source_sha256）：运行时不给身份凭证即拒收。"""
        characters = self._clip_with_identity(tmp_path, lambda _digest: None)
        report = GATE.check_bundle(characters)
        assert [p.kind for p in report.problems] == ["bad_source_identity"], report.problems
        assert "64 位十六进制" in report.problems[0].detail
        result = _run(characters)
        assert result.returncode == 1
        assert "源身份" in result.stderr
        assert "source_sha256" in result.stderr

    def test_non_hex_source_sha_fails(self, tmp_path):
        """非 hex（也含长度不对）的摘要：不是合法的源身份。"""
        characters = self._clip_with_identity(tmp_path, lambda _digest: "z" * 64)
        report = GATE.check_bundle(characters)
        assert [p.kind for p in report.problems] == ["bad_source_identity"], report.problems
        assert "64 位十六进制" in report.problems[0].detail
        assert _run(characters).returncode == 1

    def test_source_sha_stamp_mismatch_fails(self, tmp_path):
        """摘要与目录戳前缀不符：目录名换过、或 meta 与目录不是一套产物。"""
        characters = self._clip_with_identity(tmp_path, _other_stamp_sha)
        report = GATE.check_bundle(characters)
        assert [p.kind for p in report.problems] == ["bad_source_identity"], report.problems
        detail = report.problems[0].detail
        assert "目录戳" in detail
        assert _run(characters).returncode == 1

    def test_source_sha_pointing_to_another_source_fails(self, tmp_path):
        """摘要戳对得上、但指向**另一份源**：源换版后产物没跟上，运行时同样拒收。"""
        characters = self._clip_with_identity(tmp_path, _other_source_sha)
        report = GATE.check_bundle(characters)
        assert [p.kind for p in report.problems] == ["bad_source_identity"], report.problems
        assert "当前源" in report.problems[0].detail
        assert _run(characters).returncode == 1


# --------------------------------------------------------------------------- 硬约束


class TestGateConstraints:
    def test_script_imports_stdlib_only(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    imported.add("." * node.level + (node.module or ""))
                elif node.module:
                    imported.add(node.module.split(".")[0])
        assert imported, "脚本必须至少导入 argparse/sys"
        assert imported <= set(sys.stdlib_module_names), f"非标准库依赖: {imported}"
        assert "pet" not in imported, "构建门不许 import pet 包（会连带 PySide6）"
        assert not any(name.lower().startswith("pyside") for name in imported)

    def test_gate_is_read_only(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "完整的", "待机呼吸休闲")
        _make_clip(characters, "缺产物的", "写代码", generation=False)
        before = _snapshot(characters)
        result = _run(characters)
        assert result.returncode == 1
        assert _snapshot(characters) == before, "门只许读：素材树一个字节都不许动"


# --------------------------------------------------------------------------- 常量同源


def _source_constant(name: str) -> str:
    text = PROVISION_SOURCE.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\s*=\s*(.+)$", text, flags=re.MULTILINE)
    assert match, f"pet/frameseq_provision.py 里找不到 {name}（改名/删除了？）"
    raw = match.group(1).split("#", 1)[0].strip()
    return raw


class TestGenerationHomology:
    """门内世代常量必须与 pet/frameseq_provision.py 的运行时口径逐字一致。"""

    def test_encoder_desc_matches_provision(self):
        assert GATE.ENCODER_DESC == ast.literal_eval(_source_constant("ENCODER_DESC"))

    def test_unblend_mark_matches_provision(self):
        assert GATE.UNBLEND_MARK == ast.literal_eval(_source_constant("UNBLEND_MARK"))

    def test_generation_dir_naming_matches_provision(self):
        assert GATE.GEN_INFIX == ast.literal_eval(_source_constant("GEN_INFIX"))
        assert GATE.GEN_STAMP_HEX == ast.literal_eval(_source_constant("GEN_STAMP_HEX"))

    def test_stamp_is_sha256_prefix(self, tmp_path):
        characters = tmp_path / "characters"
        webm, gen = _make_clip(characters, "shenshen", "待机呼吸休闲")
        assert gen.name.endswith(_sha256(webm)[:GATE.GEN_STAMP_HEX])

    def test_source_sha_length_matches_provision(self):
        # 身份凭证的长度口径写死在 provision ``_complete_meta`` 的 ``_is_hex(stamp, 64)``
        # 里（没有模块级常量可提取）：按源码文本比对，运行时改长度即红。
        text = PROVISION_SOURCE.read_text(encoding="utf-8")
        assert f"_is_hex(stamp, {GATE.SOURCE_SHA_HEX})" in text

    def test_provision_constants_are_not_legacy(self):
        # 防线自证：门认的档串必须不在 provision 的 LEGACY_ENCODER_DESCS 里
        # （否则门会把旧世代当当前档放行）
        text = PROVISION_SOURCE.read_text(encoding="utf-8")
        block = text.split("LEGACY_ENCODER_DESCS", 1)[1].split(")", 1)[0]
        assert GATE.ENCODER_DESC not in block


# --------------------------------------------------------------------------- 接线


def _build_text() -> str:
    return BUILD_SCRIPT.read_text(encoding="utf-8")


def _enclosing_gate_block(text: str) -> str:
    """取调用本门的那段 ``if (-not $isGif) { ... }`` 语句原文。"""
    call = text.index("check_frameseq_bundle")
    start = text.rindex("if (-not $isGif) {", 0, call)
    end = text.index("}", call)
    return text[start:end + 1]


class TestBuildScriptWiring:
    def test_gate_runs_before_pyinstaller(self):
        text = _build_text()
        assert text.index("check_frameseq_bundle") < text.index("python -m PyInstaller")

    def test_non_gif_branch_calls_gate_and_aborts_on_failure(self):
        block = _enclosing_gate_block(_build_text())
        assert "check_frameseq_bundle" in block
        assert "$LASTEXITCODE" in block, "门非零必须中止构建"
        assert "throw" in block

    def test_gif_branch_skips_gate(self):
        text = _build_text()
        # 脚本调用点只有一个，且它在 `if (-not $isGif)` 里 → GIF 变体天然跳过
        assert text.count("check_frameseq_bundle.py") == 1
        assert _enclosing_gate_block(text).startswith("if (-not $isGif) {")
        call = text.index("check_frameseq_bundle")
        assert text[call - 800:call].count("GIF") >= 1, "注释要说明 GIF 变体为何跳过"


# --------------------------------------------------------------------------- 三端 shell 接线

SHELL_SCRIPTS = {
    "macos": ROOT / "scripts" / "build_macos.sh",
    "linux": ROOT / "scripts" / "build_linux.sh",
}
SHELL_CALL = "scripts/check_frameseq_bundle.py"


def _shell_text(name: str) -> str:
    return SHELL_SCRIPTS[name].read_text(encoding="utf-8")


def _shell_gate_block(text: str) -> str:
    """取 shell 脚本里调用本门的那段 ``if [[ "$needs_frameseq" == "1" ]]; then ... fi``。"""
    call = text.index(SHELL_CALL)
    start = text.rindex('if [[ "$needs_frameseq"', 0, call)
    end = text.index("\nfi\n", call)
    return text[start:end + 4]


class TestShellBuildScriptWiring:
    """macOS / Linux 的构建脚本本身必须带硬门，不能只在 workflow 里加。

    只在 workflow 里加 = 本地构建、以及任何绕过 workflow 的构建仍然会打出
    缺帧序列的静默降级包（Windows 的门就装在 ``build_onedir.ps1`` 里）。
    """

    @pytest.mark.parametrize("name", sorted(SHELL_SCRIPTS))
    def test_gate_runs_before_pyinstaller(self, name):
        text = _shell_text(name)
        assert SHELL_CALL in text
        assert text.index("check_frameseq_bundle") < text.index("-m PyInstaller")

    @pytest.mark.parametrize("name", sorted(SHELL_SCRIPTS))
    def test_gate_failure_aborts_build_explicitly(self, name):
        text = _shell_text(name)
        block = _shell_gate_block(text)
        assert "check_frameseq_bundle.py" in block
        assert "exit 1" in block, "门非零必须显式中止（不靠 set -e 隐式兜底）"
        assert '"$PYTHON_BIN"' in block, "必须用构建用的解释器跑门（与 PyInstaller 同环境）"
        assert set(("set -euo pipefail",)).issubset(set(text.splitlines()))

    @pytest.mark.parametrize("name", sorted(SHELL_SCRIPTS))
    def test_gif_only_variants_skip_gate(self, name):
        text = _shell_text(name)
        decision = text[text.index("needs_frameseq=0"):text.index(SHELL_CALL)]
        assert "gif" in decision and "gif-chat" in decision, "GIF 变体没有 frameseq 这一层"
        assert "needs_frameseq=1" in decision

    @pytest.mark.parametrize("name", sorted(SHELL_SCRIPTS))
    def test_gate_is_called_once_and_before_any_variant_build(self, name):
        text = _shell_text(name)
        # 一次调用即可覆盖全部变体：门是整树体检（全角色全 clip），与变体无关
        assert text.count("check_frameseq_bundle.py") == 1
        assert text.index(SHELL_CALL) < text.index('for variant in "${variant_list[@]}"')
        assert text.index(SHELL_CALL) < text.index("-m PyInstaller")


# --------------------------------------------------------------------------- 素材供给入口

PREPARE_SCRIPT = ROOT / "scripts" / "prepare_frameseq_bundle.py"


def _load_prepare():
    spec = importlib.util.spec_from_file_location("prepare_frameseq_bundle", PREPARE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREPARE = _load_prepare()


class RecordingRunner:
    """记录真实 argv、按队列返回退出码的假 runner（不执行任何命令、不碰 GUI）。"""

    def __init__(self, *codes: int):
        self.codes = list(codes)
        self.calls: list[list[str]] = []

    def __call__(self, argv, cwd=None):
        self.calls.append(list(argv))
        code = self.codes.pop(0) if self.codes else 0
        return subprocess.CompletedProcess(argv, code, stdout="", stderr="")

    @property
    def steps(self) -> list[str]:
        return [Path(call[1]).name for call in self.calls]


class TestPrepareDelegation:
    """供给入口的命令委派：先验 → 缺才转 → 再验；坏缓存不盲跳过。

    真转 106 段要 ~28 min，所以委派行为用假 runner 断言：入口的契约是
    「按真实退出码决定调什么」，这正是注入 runner 能完整覆盖的部分。
    """

    @staticmethod
    def _prepare(characters: Path, runner: RecordingRunner, **kwargs):
        return PREPARE.prepare(characters_dir=characters, character="shenshen",
                              include="random,events", runner=runner, **kwargs)

    def test_complete_material_skips_conversion(self, tmp_path, capsys):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "待机呼吸休闲")
        runner = RecordingRunner(0)
        assert self._prepare(characters, runner) == 0
        assert runner.steps == ["check_frameseq_bundle.py"], "素材已完整不许再转"
        out = capsys.readouterr().out
        assert "跳过转换" in out

    def test_missing_material_converts_then_revalidates(self, tmp_path):
        characters = tmp_path / "characters"
        (characters / "shenshen" / "videos").mkdir(parents=True)
        runner = RecordingRunner(1, 0, 0)
        assert self._prepare(characters, runner) == 0
        assert runner.steps == ["check_frameseq_bundle.py", "convert_frameseq.py",
                                "check_frameseq_bundle.py"]

    def test_broken_cache_is_not_blindly_skipped(self, tmp_path):
        # 缓存里是陈旧/半成品产物：验证器判红 → 必须重转 → 再验（再验仍红就判红）
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "写代码", encoder=LEGACY_ENCODER)
        runner = RecordingRunner(1, 0, 1)
        assert self._prepare(characters, runner) == 1
        assert runner.steps == ["check_frameseq_bundle.py", "convert_frameseq.py",
                                "check_frameseq_bundle.py"]

    def test_converter_failure_stops_with_real_exit_code(self, tmp_path, capsys):
        characters = tmp_path / "characters"
        runner = RecordingRunner(1, 7)
        assert self._prepare(characters, runner) == 7, "必须原样冒泡转换器退出码"
        assert runner.steps == ["check_frameseq_bundle.py", "convert_frameseq.py"]
        captured = capsys.readouterr()
        assert "转换失败" in (captured.out + captured.err)

    def test_force_reconverts_even_when_complete(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "待机呼吸休闲")
        runner = RecordingRunner(0, 0, 0)
        assert self._prepare(characters, runner, force=True) == 0
        assert runner.steps == ["check_frameseq_bundle.py", "convert_frameseq.py",
                                "check_frameseq_bundle.py"]
        assert "--force" in runner.calls[1]

    def test_converter_covers_all_folders(self, tmp_path):
        # 门槛是全树 106 段：只转热集 11 段会让其余 95 段继续判缺
        characters = tmp_path / "characters"
        runner = RecordingRunner(1, 0, 0)
        self._prepare(characters, runner)
        argv = runner.calls[1]
        assert argv[1] == PREPARE.CONVERTER_REL
        assert argv[argv.index("--character") + 1] == "shenshen"
        assert argv[argv.index("--include") + 1] == "random,events"

    def test_validator_targets_the_same_material_tree(self, tmp_path):
        characters = tmp_path / "characters"
        runner = RecordingRunner(1, 0, 0)
        self._prepare(characters, runner)
        argv = runner.calls[0]
        assert argv[1] == PREPARE.VALIDATOR_REL
        assert argv[argv.index("--characters-dir") + 1] == str(characters)

    def test_both_commands_run_with_one_interpreter(self, tmp_path):
        characters = tmp_path / "characters"
        runner = RecordingRunner(1, 0, 0)
        self._prepare(characters, runner)
        assert runner.calls[0][0] == runner.calls[1][0] == sys.executable


class TestPrepareConstraints:
    """硬约束：零 Qt 零第三方依赖、不启动 GUI、不写素材树以外的位置。"""

    def test_script_imports_stdlib_only_and_no_qt(self):
        tree = ast.parse(PREPARE_SCRIPT.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    imported.add("." * node.level + (node.module or ""))
                elif node.module:
                    imported.add(node.module.split(".")[0])
        assert imported, "脚本必须至少导入 argparse/sys"
        assert imported <= set(sys.stdlib_module_names), f"非标准库依赖: {imported}"
        assert "pet" not in imported, "供给入口不许 import pet 包（会连带 PySide6 起 GUI）"

    def test_never_touches_user_runtime_or_gui(self, tmp_path):
        text = PREPARE_SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("QApplication", "QMessageBox", "uninstall_cleanup",
                          "APPDATA", "XDG_CONFIG_HOME"):
            assert forbidden not in text, f"构建期供给不许碰 {forbidden}"

    def test_validate_only_does_not_write_material_tree(self, tmp_path):
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "待机呼吸休闲")
        before = _snapshot(characters)
        runner = RecordingRunner(0)   # 假 runner：真实验证器只读，这里断的是入口不写盘
        PREPARE.prepare(characters_dir=characters, character="shenshen",
                        include="random,events", runner=runner)
        assert _snapshot(characters) == before


class TestCacheKey:
    """缓存 key：源文件 hash + 转换器版本 + 编码档 + 平台/依赖版本（缺一即可能命中错缓存）。"""

    @staticmethod
    def _tree(tmp_path) -> Path:
        characters = tmp_path / "characters"
        _make_clip(characters, "shenshen", "待机呼吸休闲")
        return characters

    def test_key_is_stable_and_cache_safe(self, tmp_path):
        characters = self._tree(tmp_path)
        first = PREPARE.cache_key(characters)
        assert first == PREPARE.cache_key(characters), "同输入必须同 key（否则缓存永不命中）"
        assert re.fullmatch(r"[A-Za-z0-9._-]+", first), f"key 只能是安全字符: {first}"

    def test_key_changes_with_source_material(self, tmp_path):
        characters = self._tree(tmp_path)
        before = PREPARE.cache_key(characters)
        _make_clip(characters, "shenshen", "左转奔跑")
        assert PREPARE.cache_key(characters) != before

    def test_key_changes_with_encoder_grade(self, tmp_path, monkeypatch):
        characters = self._tree(tmp_path)
        before = PREPARE.cache_key(characters)
        monkeypatch.setattr(PREPARE.gate, "ENCODER_DESC", "libwebp lossy q99 (another grade)")
        assert PREPARE.cache_key(characters) != before, "改档必须换 key（旧档产物会被门判陈旧）"

    def test_key_changes_with_environment(self, tmp_path):
        characters = self._tree(tmp_path)
        assert PREPARE.cache_key(characters, env="a") != PREPARE.cache_key(characters, env="b")

    def test_key_ignores_derived_frameseq_files(self, tmp_path):
        """key 只看源 webm：把派生帧也算进去会让 key 随产物自变（缓存永不命中）。"""
        characters = self._tree(tmp_path)
        before = PREPARE.cache_key(characters)
        derived = next((characters / "shenshen" / "frameseq").rglob("f_*.webp"))
        derived.write_bytes(b"rewritten derived frame" * 64)
        assert PREPARE.cache_key(characters) == before

    def test_environment_label_covers_platform_python_and_deps(self):
        label = PREPARE.environment_label()
        assert PREPARE.platform_slug() in label
        major, minor = sys.version_info[:2]
        assert f"py{major}.{minor}" in label
        # ffmpeg 每平台是不同的构建（imageio-ffmpeg wheel），webp 编码走 Pillow
        assert "pillow" in label.lower()
        assert "imageio-ffmpeg" in label.lower()

    def test_platform_slug_is_filesystem_and_cache_safe(self):
        slug = PREPARE.platform_slug()
        assert re.fullmatch(r"[a-z0-9._-]+", slug), slug

    def test_cli_prints_same_key_as_library(self):
        # 真素材树（assets/characters 已入库，CI 上也在）跑真命令，与库内同源比对
        characters = ROOT / "assets" / "characters"
        result = subprocess.run(
            [sys.executable, str(PREPARE_SCRIPT), "--print-cache-key"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT), check=False,
        )
        assert result.returncode == 0, result.stderr
        printed = result.stdout.strip().splitlines()
        assert len(printed) == 1, printed
        assert printed[0] == PREPARE.cache_key(characters)

    def test_cli_refuses_foreign_material_root(self, tmp_path):
        # 转换器只服务仓库内的 assets/characters（无「外部素材根」参数）：指向别处
        # 必须当场拒绝，否则会出现「验的是 A 树、转的是 B 树」的静默错配
        result = subprocess.run(
            [sys.executable, str(PREPARE_SCRIPT), "--characters-dir", str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT), check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "--characters-dir" in result.stderr


class TestPrepareRealMaterial:
    """本机素材完整时跑真命令：验证器放行即不许重转（不重写 379 MiB / 28 min）。"""

    def test_complete_repo_material_validates_without_converting(self):
        characters = ROOT / "assets" / "characters"
        if not characters.is_dir():
            pytest.skip("本机没有 assets/characters 素材树")
        if not GATE.check_bundle(characters).ok:
            pytest.skip("本机素材树不完整（干净检出的 CI 必然如此）——本机才有真素材")
        result = subprocess.run(
            [sys.executable, str(PREPARE_SCRIPT), "--characters-dir", str(characters),
             "--character", "shenshen"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT), check=False,
            # 子进程输出强制 UTF-8：默认跟随本机 locale（中文 Windows 为 cp936），
            # 而这里按 utf-8 解码 ⇒ 中文全成替换字符、断言必然落空（本机已复现）。
            # **只作用于这个子进程**——不能给测试进程本身设 PYTHONIOENCODING，
            # 那会让 test_module_level_validation 假红（见 DEV-ENV）。
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert result.returncode == 0, result.stderr
        assert "跳过转换" in result.stdout
        assert "新转" not in result.stdout, "素材已完整时不许启动转换"
