# -*- coding: utf-8 -*-
"""随包 OCR 模型构建期硬门（``scripts/verify_rapidocr_models.py``）的行为测试。

这一族守两件事：

1. **门会红**：模型缺失、被截断、同名不同内容（静默换版）都必须判失败——这是它
   存在的全部理由（一个永远返回 0 的门比没有门更糟：它给人"已经查过了"的错觉）。
2. **判据不漏**：期望值来自 ``pet/screen_capture/ocr.py`` 的单一真相源，且文件
   名与 sha256 **逐项**核对——只查文件在不在，挡不住"同名换版"。

单测只碰 ``tmp_path`` 里的假模型与真实仓库资源，不删改任何随包文件。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

pytest.importorskip("PySide6", reason="判据来自 pet/screen_capture/ocr.py（顶部 import QImage）")


@pytest.fixture(scope="module")
def verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_rapidocr_models", REPO / "scripts" / "verify_rapidocr_models.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_rapidocr_models"] = module
    spec.loader.exec_module(module)
    return module


def _fake_dir(tmp_path: Path, files: dict[str, str]) -> Path:
    """按给定内容造一个假模型目录（内容决定 sha256）。"""
    directory = tmp_path / "models"
    directory.mkdir(exist_ok=True)
    for name, content in files.items():
        (directory / name).write_bytes(content.encode())
    return directory


def test_expected_values_come_from_the_engine_module(verifier):
    """判据必须来自产品那一份（单一真相源），不是脚本里抄的字面量。"""
    from pet.screen_capture import ocr

    directory, files, shas = verifier.load_expectations()

    assert files == ocr.MODEL_FILES
    assert shas == ocr.MODEL_SHA256
    assert directory == REPO.joinpath(*ocr.MODEL_RELATIVE_DIR)
    assert set(files) == set(shas), "每个模型都要有摘要，缺一个就有一份没被校验"


def test_repo_models_pass(verifier):
    """仓库里的随包模型必须过门（这就是构建时跑的那一次）。"""
    directory, files, shas = verifier.load_expectations()

    report = verifier.inspect(directory, files, shas)

    assert report["problems"] == []
    assert all(entry["sha256_ok"] for entry in report["models"])


def test_missing_model_fails(verifier, tmp_path):
    _, files, shas = verifier.load_expectations()
    assert len(files) >= 2
    missing = sorted(files.values())[0]
    directory = _fake_dir(tmp_path, {n: "x" for n in files.values() if n != missing})

    report = verifier.inspect(directory, files, shas)

    assert any(missing in problem for problem in report["problems"])
    assert not all(entry["sha256_ok"] for entry in report["models"])


def test_same_name_different_content_fails(verifier, tmp_path):
    """同名不同内容 = 静默换版：文件在、名字对，但摘要不符必须判失败。"""
    _, files, shas = verifier.load_expectations()
    directory = _fake_dir(tmp_path, {n: "not the real model" for n in files.values()})

    report = verifier.inspect(directory, files, shas)

    assert len(report["problems"]) == len(files)
    assert all("sha256" in problem for problem in report["problems"])


def test_missing_directory_fails(verifier, tmp_path):
    _, files, shas = verifier.load_expectations()

    report = verifier.inspect(tmp_path / "nope", files, shas)

    assert report["exists"] is False
    assert report["problems"]


def test_main_exit_codes_and_json(verifier, tmp_path, capsys):
    directory, _, _ = verifier.load_expectations()

    assert verifier.main([]) == 0
    assert "OK" in capsys.readouterr().out

    assert verifier.main(["--dir", str(directory), "--json"]) == 0
    payload = capsys.readouterr().out
    assert '"ok": true' in payload

    assert verifier.main(["--dir", str(tmp_path / "nope")]) == 1
    assert "FAIL" in capsys.readouterr().err


# ---------------------------------------------------------------- 构建接线
#
# 行为测试看不到"有没有接上"：门写得再对，没被构建脚本调用就什么也拦不住。
# 这一组按源码文本断言三个平台脚本的接线与顺序（同 tests/test_presentmon_packaging.py
# 的「构建接线」口径），以及文档面（打包文档 + 许可登记）。

PS1 = REPO / "scripts" / "build_onedir.ps1"
SHELLS = {
    "linux": REPO / "scripts" / "build_linux.sh",
    "macos": REPO / "scripts" / "build_macos.sh",
}
MODELS_ADD_DATA = "resources/rapidocr_models"
PACKAGING_DOC = REPO / "docs" / "ONEDIR_PACKAGING.md"
NOTICES = REPO / "THIRD_PARTY_NOTICES.md"


def test_windows_script_gates_models_twice_and_ships_them():
    text = PS1.read_text(encoding="utf-8")

    invocations = text.count(r"python scripts\verify_rapidocr_models.py")
    assert invocations == 2, f"只应有一前一后两处调用（实测 {invocations}）"
    assert (text.index(r"python scripts\verify_rapidocr_models.py")
            < text.index("python -m PyInstaller")), "构建期门必须排在 PyInstaller 之前"
    assert text.index("--app-dir $appDir") > text.index("python -m PyInstaller"), (
        "产物里的那次校验必须排在 PyInstaller 之后"
    )
    assert r"resources\rapidocr_models;resources\rapidocr_models" in text
    # rapidocr 的两份配置数据也要进包（只带模型时引擎构造就失败）
    assert r"$rapidocrDir\config.yaml;rapidocr" in text
    assert r"$rapidocrDir\default_models.yaml;rapidocr" in text
    assert "@rapidocrData" in text, "--add-data 参数数组必须真的被用上"


def test_app_dir_mode_judges_three_things_not_just_the_models(verifier, tmp_path,
                                                              monkeypatch):
    """产物侧那条门要判三件：引擎模块 + 模型 + rapidocr 配置（少判一件就漏一个坑）。

    2026-10-13 交叉审查 B1 的教训：模型与配置齐全、**引擎模块不在**的包照样打了出来，
    产品的表现是右键「截图 → 提取文字」永远置灰——所以模块那一件必须真判。
    """
    internal = tmp_path / "app" / "_internal"
    (internal / "resources" / "rapidocr_models").mkdir(parents=True)
    (internal / "rapidocr").mkdir(parents=True)
    for name in verifier.RAPIDOCR_BUNDLE_CONFIG_FILES:
        (internal / "rapidocr" / name).write_text("x", encoding="utf-8")
    assert set(verifier.RAPIDOCR_BUNDLE_CONFIG_FILES) == {
        "config.yaml", "default_models.yaml"}
    # 模块图那一半要读真产物才能拿到；这里只换掉"读"，判据与组装仍走产品代码。
    monkeypatch.setattr(verifier, "bundle_module_names", lambda _app: (set(), []))
    _, files, shas = verifier.load_expectations()

    report = verifier.inspect_app_dir(tmp_path / "app", files, shas,
                                      required_modules=("pet.screen_capture.ocr",))

    assert report["missing_bundle_modules"] == ["pet.screen_capture.ocr"]
    assert any("pet.screen_capture.ocr" in problem for problem in report["problems"])
    assert report["missing_rapidocr_config"] == []

    (internal / "rapidocr" / "config.yaml").unlink()
    report = verifier.inspect_app_dir(tmp_path / "app", files, shas,
                                      required_modules=("pet.screen_capture.ocr",))

    assert report["missing_rapidocr_config"] == ["config.yaml"]
    assert any("config.yaml" in problem for problem in report["problems"])


def test_required_bundle_modules_come_from_the_product(verifier):
    """判据必须来自产品那一份声明（``ocr.BUNDLE_MODULES``），不抄第二份字面量。"""
    from pet.screen_capture import ocr

    assert verifier.required_bundle_modules() == ocr.BUNDLE_MODULES
    assert verifier.required_bundle_modules() == (
        "pet.screen_capture.ocr", "pet.screen_capture.ocr_worker")


def test_missing_bundle_modules_is_a_pure_set_difference(verifier):
    required = ("pet.screen_capture.ocr", "pet.screen_capture.translate")

    assert verifier.missing_bundle_modules(set(required), required) == []
    assert verifier.missing_bundle_modules(
        {"pet.screen_capture.ocr"}, required) == ["pet.screen_capture.translate"]


def test_payload_paths_are_found_by_existence_not_by_platform_guess(verifier, tmp_path):
    """三端落点不同（Windows/Linux ``_internal``、macOS ``Contents/Resources``），
    而这条门是三端共用的**阻塞式**门——所以按"在不在"找，不按平台猜目录名。"""
    win = tmp_path / "app"
    (win / "_internal" / "rapidocr").mkdir(parents=True)
    assert verifier.find_payload(win, Path("rapidocr")) == win / "_internal" / "rapidocr"

    mac = tmp_path / "app.app"
    (mac / "Contents" / "Resources" / "resources" / "rapidocr_models").mkdir(parents=True)
    assert (verifier.find_payload(mac, Path("resources") / "rapidocr_models")
            == mac / "Contents" / "Resources" / "resources" / "rapidocr_models")

    # 直接把载荷目录递进来（``<app>/_internal`` 本身）时也要认
    payload = tmp_path / "payload"
    (payload / "rapidocr").mkdir(parents=True)
    assert verifier.find_payload(payload, Path("rapidocr")) == payload / "rapidocr"

    # 都没有：返回第一个候选（报错里的路径要是能直接去 ls 的那一个）
    empty = tmp_path / "empty"
    empty.mkdir()
    assert verifier.find_payload(empty, Path("rapidocr")) == empty / "_internal" / "rapidocr"


def test_bundle_module_names_fails_closed_without_an_archive(verifier, tmp_path):
    """读不出模块图＝这条门没验成，必须按失败处理（验不了就放过的门比没有门更糟）。"""
    empty = tmp_path / "empty-app"
    empty.mkdir()

    names, problems = verifier.bundle_module_names(empty)

    assert names == set()
    assert problems, "读不出产物模块图时必须给出理由，不能静默放行"


def test_windows_script_no_longer_excludes_the_ocr_runtime_deps():
    """numpy/cv2 是产品依赖：排除清单里再有它们＝冻结包 OCR 全线不可用。"""
    text = PS1.read_text(encoding="utf-8")

    for module in ("'cv2'", "'numpy'"):
        assert module not in text, f"{module} 仍在 --exclude-module 清单里"


@pytest.mark.parametrize("name", sorted(SHELLS))
def test_shell_scripts_gate_and_ship_the_models(name):
    text = SHELLS[name].read_text(encoding="utf-8")

    assert "scripts/verify_rapidocr_models.py" in text
    assert (text.index("scripts/verify_rapidocr_models.py")
            < text.index("-m PyInstaller")), "构建期门必须排在 PyInstaller 之前"
    assert f"{MODELS_ADD_DATA}:{MODELS_ADD_DATA}" in text
    assert "$RAPIDOCR_DIR/config.yaml:rapidocr" in text
    assert "$RAPIDOCR_DIR/default_models.yaml:rapidocr" in text
    # 产物侧也要判（与 Windows 同口径）：模块 + 模型 + 配置一次判完
    assert (text.index('verify_rapidocr_models.py --app-dir "$DIST_DIR/$name')
            > text.index("-m PyInstaller")), "产物里的那次校验必须排在 PyInstaller 之后"


def test_slim_lists_no_longer_treat_numpy_as_pollution():
    text = (REPO / "scripts" / "slim_bundle.py").read_text(encoding="utf-8")
    forbidden = text.split("FORBIDDEN_GLOBS = (")[1].split(")")[0]

    assert "numpy" not in forbidden
    assert "django" in forbidden and "hypothesis" in forbidden, "真污染不许顺手放开"
    assert "opencv_videoio_ffmpeg" in text.split("REMOVAL_GLOBS = (")[1].split(")")[0]


def test_packaging_doc_and_notices_register_the_models():
    doc = PACKAGING_DOC.read_text(encoding="utf-8")
    assert MODELS_ADD_DATA in doc
    assert "verify_rapidocr_models" in doc

    notices = NOTICES.read_text(encoding="utf-8")
    assert MODELS_ADD_DATA in notices
    from pet.screen_capture import ocr

    for section, digest in ocr.MODEL_SHA256.items():
        assert digest in notices, f"THIRD_PARTY_NOTICES.md 没登记 {section} 的 sha256"
