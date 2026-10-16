# -*- coding: utf-8 -*-
"""「快速识屏」打包接线守卫：动态 seam 的目标模块必须显式进包（2026-10-13 B1，切片 5 扩到两个）。

**这条守卫守的是一次真实的交付事故**：三个构建脚本都把 OCR 模型和 rapidocr 配置打进
了包，却没有一个把**引擎模块本身**推进 PyInstaller 的模块图。截图动作走的是动态
seam——``pet/screen_capture/actions.py::_resolve_engine`` 用 ``importlib`` 按字符串
（``OCR_MODULE = "ocr"``）解析 ``pet.screen_capture.ocr``，而全仓（``pet/`` 下）没有
任何一处静态 import 指向它。静态分析从入口出发摸不到这个模块，于是冻结包里"模型都在、
引擎不在"：产品不崩，只是右键「截图 → 提取文字」永远置灰。

切片 5 把识别搬进独立子进程（``<exe> --ocr-worker``）之后，同一个坑多了一个入口：
``pet.screen_capture.ocr_worker`` 的模块名只以**命令行字符串**的形式出现在代码里
（``ocr.worker_command``），静态分析同样摸不到。缺它不会崩——只是每次识屏报一句
"起不了本地 OCR 工作进程"。

所以要钉住五件事，缺一条这族测试就又会骗人：

1. **三个脚本都带**两个 ``--hidden-import``（``pet.screen_capture.ocr`` 与
   ``pet.screen_capture.ocr_worker``），且真的挂在 PyInstaller 调用上（写了但没传
   进去等于没写）；
2. **产物侧有门**：三个脚本都调 ``verify_rapidocr_models.py --app-dir``——只判写没写
   在源码里没用，得从产物模块图里读出来（门的行为测试在 test_verify_rapidocr_models.py）；
3. **假设前提还成立**：``pet/`` 下仍然没有静态 import 指向那个**宿主引擎模块**
   （有人加了静态 import 的那天，这条 hidden-import 仍然是承重的，但守卫要提醒他别
   当成多余行删掉）；
4. **冻结入口有路由**：``packaging/pet_entry*.py`` 必须在 import ``pet.app`` 之前
   把 ``--ocr-worker`` 分流出去——冻结包里 exe 自己就是解释器，工作端只能由那两条
   路由提供（``pet/__main__.py`` 在冻结启动时根本不参与）；
5. **判据是单一真相源**：门的期望模块清单来自 ``ocr.BUNDLE_MODULES``，不是在门里
   抄第二份字面量。

真机口径的证据（同一台机器、同一份源码，只差这一条参数：不带的包解析不出引擎、
菜单置灰；带的包认出字）见 ``.scratch/screen-capture/build_ocr_hidden.out``。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PS1 = REPO / "scripts" / "build_onedir.ps1"
SHELLS = {
    "linux": REPO / "scripts" / "build_linux.sh",
    "macos": REPO / "scripts" / "build_macos.sh",
}
#: 两个静态分析摸不到、只能靠 --hidden-import 进包的模块。
MODULE = "pet.screen_capture.ocr"
WORKER_MODULE = "pet.screen_capture.ocr_worker"
BUNDLED_MODULES = (MODULE, WORKER_MODULE)

#: 冻结入口（exe 的 ``__main__``）。两条都要能分流 --ocr-worker。
FROZEN_ENTRIES = (REPO / "packaging" / "pet_entry.py",
                  REPO / "packaging" / "pet_entry_no_chat.py")

#: 加静态 import 的人会在这里看到理由，而不是以为那行 hidden-import 是多余的。
STATIC_IMPORT_HINT = (
    "pet/ 下出现了一处指向 pet.screen_capture.ocr 的静态 import。构建脚本里的 "
    "--hidden-import pet.screen_capture.ocr 仍然是承重的（产品走的是 actions 的"
    "动态 seam），删掉它冻结包会再次解析不出引擎、菜单永远置灰。"
)


def test_windows_script_hidden_imports_the_dynamic_engines():
    text = PS1.read_text(encoding="utf-8")

    for module in BUNDLED_MODULES:
        assert f"'--hidden-import', '{module}'" in text, f"{module} 的 hidden-import 定义不见了"
    assert "@rapidocrHidden" in text, "定义必须真的被传进 PyInstaller（splat）"
    command = text[text.index("python -m PyInstaller"):text.index("$entry\n")]
    assert "@rapidocrHidden" in command, "splat 没出现在 PyInstaller 命令里"
    assert command.index("@rapidocrHidden") > command.index("@rapidocrData"), (
        "hidden-import 与 OCR 的那组参数应该挨在一起，便于一起读"
    )


@pytest.mark.parametrize("name", sorted(SHELLS))
def test_shell_scripts_hidden_import_the_dynamic_engines(name):
    text = SHELLS[name].read_text(encoding="utf-8")

    for module in BUNDLED_MODULES:
        assert f"--hidden-import {module}" in text, f"{module} 的 hidden-import 定义不见了"
    assert '"${RAPIDOCR_HIDDEN[@]}"' in text, "定义必须真的被传进 PyInstaller"
    command = text[text.index("args=("):text.index(")\n", text.index("args=("))]
    assert '"${RAPIDOCR_HIDDEN[@]}"' in command, "hidden-import 没在 args 数组里"
    assert '"${args[@]}" "$entry"' in text, "args 数组必须真的被交给 PyInstaller"


@pytest.mark.parametrize("script", [PS1, *SHELLS.values()])
def test_product_side_gate_reads_the_module_out_of_the_bundle(script):
    """只写 hidden-import 不够：还要有产物侧的门把"到底进没进包"读出来。

    锚在**真正的构建命令**上（不是注释里随便一个 "PyInstaller" 字样）：
    ``--app-dir`` 那一次必须在产物已经出来之后跑。
    """
    text = script.read_text(encoding="utf-8")
    anchor = (text.index("python -m PyInstaller") if script == PS1
              else text.index("-m PyInstaller"))

    assert text.count("verify_rapidocr_models.py --app-dir") == 1
    assert text.index("verify_rapidocr_models.py --app-dir") > anchor


def test_no_module_under_pet_statically_imports_the_engine():
    """动态 seam 的前提：``pet/`` 下没有静态 import 指向引擎模块。

    这条断言看着像"限制写法"，其实是**提醒**：它不是不许改，而是"改了也别删那条
    --hidden-import"（见 :data:`STATIC_IMPORT_HINT`）。
    """
    patterns = (
        re.compile(r"^\s*from\s+\.ocr\s+import\b", re.MULTILINE),
        re.compile(r"^\s*from\s+pet\.screen_capture\.ocr\s+import\b", re.MULTILINE),
        re.compile(r"^\s*from\s+pet\.screen_capture\s+import\s+ocr\b", re.MULTILINE),
        re.compile(r"^\s*from\s+\.\s+import\s+ocr\b", re.MULTILINE),
        re.compile(r"^\s*import\s+pet\.screen_capture\.ocr\b", re.MULTILINE),
    )
    offenders: list[str] = []
    for path in sorted((REPO / "pet").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in patterns):
            offenders.append(path.relative_to(REPO).as_posix())

    assert offenders == [], STATIC_IMPORT_HINT + f"（命中：{', '.join(offenders)}）"


def test_the_actions_seam_still_resolves_the_engine_dynamically():
    """seam 的形状（importlib + 字符串模块名）是上面那一切的成因，也要钉住。"""
    text = (REPO / "pet" / "screen_capture" / "actions.py").read_text(encoding="utf-8")

    assert "import importlib" in text
    assert 'importlib.import_module(f"{__package__}.{module_name}")' in text
    assert 'OCR_MODULE = "ocr"' in text


# ------------------------------------------------- 冻结入口必须分流 --ocr-worker


@pytest.mark.parametrize("entry", FROZEN_ENTRIES, ids=lambda p: p.name)
def test_frozen_entries_route_the_ocr_worker_flag(entry):
    """冻结包里 exe 自己就是解释器：工作端只能由入口的 ``--ocr-worker`` 分流提供。

    分流必须**早于** ``from pet.app import main``：晚一步就会把 Qt / 素材库 / 托盘
    整份拉起来，而这条路径存在的全部理由就是"别付那份成本"。
    """
    text = entry.read_text(encoding="utf-8")

    assert "ocr.OCR_WORKER_FLAG" not in text, "开关的字面量应该只有一份（ocr.py）"
    assert '"--ocr-worker" in sys.argv' in text
    assert "from pet.__main__ import _run_ocr_worker" in text
    app_import = text.index("\nfrom pet.app import main")
    assert text.index('"--ocr-worker" in sys.argv') < app_import


def test_the_package_entry_offers_the_worker_route():
    """源码态入口同样要能分流（冻结入口复用它的实现）。"""
    text = (REPO / "pet" / "__main__.py").read_text(encoding="utf-8")

    assert '"--ocr-worker" in sys.argv' in text
    assert "def _run_ocr_worker()" in text
    assert "from .screen_capture.ocr_worker import main as ocr_worker_main" in text
    route = text.index('"--ocr-worker" in sys.argv')
    app_import = text.index("\n    from .app import main as app_main")
    assert route < app_import, "分流必须早于 import pet.app，否则独立进程省的东西全白省"


def _load_verifier():
    """按文件路径加载构建期门脚本（``scripts/`` 不是包，import 不进来）。"""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "verify_rapidocr_models", REPO / "scripts" / "verify_rapidocr_models.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_rapidocr_models"] = module
    spec.loader.exec_module(module)
    return module


def test_gate_judges_the_modules_the_product_actually_needs():
    """门的判据必须等于产品声明的清单（写死第二份就会漂移）。"""
    module = _load_verifier()

    from pet.screen_capture import ocr

    assert ocr.BUNDLE_MODULES == (MODULE, WORKER_MODULE)
    assert module.required_bundle_modules() == ocr.BUNDLE_MODULES
