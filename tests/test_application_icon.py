# -*- coding: utf-8 -*-
"""正式桌宠图标（窗口/标题栏用的应用图标）——运行期加载契约 + 三端打包接线。

**为什么需要这个文件**：``--icon assets/icon.ico`` 只把图标写进可执行文件/应用包的
**文件图标**资源；Qt 窗口（设置窗、对话框）标题栏上的那一个走的是 ``setWindowIcon``
——在此之前产品没有任何一处设过它，于是原生标题栏摆的是系统给的通用图标。本文件为
新的唯一入口 ``pet/application_icon.py::load_application_icon()`` 钉住三条硬契约：

1. **双候选、cwd 无关**：冻结包取 ``sys._MEIPASS/assets/icon.ico``，源码运行取仓库根下的
   同一相对路径（与 ``pet/game_fps.py::bundled_backend_path`` 同一约定）。候选由
   ``__file__`` 解析，与当前工作目录无关。
2. **缺件/坏件安全回退**：候选不存在、或存在但读不出（截断/非法字节）都返回**空图标**、
   不抛异常；第一个候选坏掉时继续试下一个（``_MEIPASS`` 里那份坏掉不该让图标整体消失）。
3. **不能早于 QApplication**：应用还没建起来时构造一个从文件加载的 ``QIcon`` **会让进程
   直接死掉**（本机实测：无任何 Qt 应用时 ``QIcon("assets/icon.ico")`` 进程退出码 127，
   而空的 ``QIcon()`` 安然无恙）。所以进加载之前先看 ``QGuiApplication.instance()``；
   没有就返回空图标且**不写缓存**。缓存跟着应用实例走：同一应用内第二次调用返回同一个
   对象，应用被销毁重建后缓存自动失效（测试会重建 QApplication）。

打包面同样在此钉住：``--icon`` 之外**还必须把这一份真的打进包**（``--add-data``），否则
冻结版窗口图标静默消失；``packaging/dsh-pet.iss`` 的 ``SetupIconFile`` 与安装目录递归
拷贝一并断言（安装包不需要额外条目，但要有证据）。多尺寸契约取自图标生成器
``scripts/make_icon.py`` 的 ``ICON_SIZES``，不在这里抄第二份字面量。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
ICON_FILE = REPO / "assets" / "icon.ico"
PS1 = REPO / "scripts" / "build_onedir.ps1"
SHELLS = {
    "macos": REPO / "scripts" / "build_macos.sh",
    "linux": REPO / "scripts" / "build_linux.sh",
}
ISS = REPO / "packaging" / "dsh-pet.iss"
PACKAGING_DOC = REPO / "docs" / "ONEDIR_PACKAGING.md"

import pet.application_icon as application_icon  # noqa: E402  —— 被测模块（唯一入口）

app = QApplication.instance() or QApplication([])

#: 产品侧声明的相对路径（构建脚本里的 ``--add-data`` 目标必须与它一致）。
RELATIVE = application_icon.APPLICATION_ICON_RELATIVE_PATH
RELATIVE_POSIX = "/".join(RELATIVE)
ADD_DATA_WINDOWS = '--add-data "' + RELATIVE_POSIX.replace("/", "\\") + ";" + RELATIVE[0] + '"'
ADD_DATA_POSIX = f'--add-data "{RELATIVE_POSIX}:{RELATIVE[0]}"'

#: 无 QApplication 的现场：把模块里的 ``QGuiApplication`` 换成只会老实回答"没有"的桩。
_NO_APPLICATION = type("_NoApplication", (), {"instance": staticmethod(lambda: None)})


def _load_make_icon():
    """按文件路径加载图标生成器（``scripts/`` 不是包，import 不进来）。"""
    spec = importlib.util.spec_from_file_location("make_icon", REPO / "scripts" / "make_icon.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_icon"] = module
    spec.loader.exec_module(module)
    return module


def _icon_sizes(icon) -> list[tuple[int, int]]:
    return sorted((size.width(), size.height()) for size in icon.availableSizes())


def _declared_icon_sizes() -> list[tuple[int, int]]:
    """生成器声明的尺寸档位（ICO 多尺寸契约的唯一真相源）。"""
    return sorted((size, size) for size in _load_make_icon().ICON_SIZES)


def _write_mono_icon(path: Path, size: int) -> None:
    """写一个**尺寸与仓库那份不同**的合法 ICO（用来证明读到的是哪一个候选）。"""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (size, size), (12, 34, 56, 255)).save(path, format="ICO", sizes=[(size, size)])


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    """每个用例都从"没缓存过"开始（缓存是本模块唯一的可变状态）。"""
    monkeypatch.setattr(application_icon, "_ICON_CACHE", None, raising=False)


# ------------------------------------------------------------------ 一、路径契约


def test_candidates_prefer_the_frozen_copy_then_the_source_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    candidates = application_icon.application_icon_candidates()

    assert candidates == (tmp_path / "assets" / "icon.ico", ICON_FILE)


def test_source_runs_resolve_to_the_repository_root(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.chdir(tmp_path)

    assert application_icon.application_icon_candidates() == (ICON_FILE,)


def test_loading_ignores_the_current_working_directory(tmp_path, monkeypatch):
    """cwd 换到哪里都读到同一份（源码路径按 ``__file__`` 解析，不靠相对路径）。"""
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.chdir(tmp_path)

    icon = application_icon.load_application_icon()

    assert _icon_sizes(icon) == _declared_icon_sizes()


# ------------------------------------------------------------------ 二、加载契约


def test_the_committed_icon_keeps_every_size_the_generator_declares():
    """多尺寸是 ICO 的存在理由：Windows 从 16 到 256 各有用途，缩放即发虚。"""
    icon = application_icon.load_application_icon()

    assert not icon.isNull()
    sizes = _icon_sizes(icon)
    assert sizes == _declared_icon_sizes()
    for required in (16, 32, 48, 256):
        assert (required, required) in sizes, f"ICO 里少了 {required}px 档"


def test_the_frozen_copy_wins_when_it_is_there(tmp_path, monkeypatch):
    _write_mono_icon(tmp_path / "assets" / "icon.ico", 37)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert _icon_sizes(application_icon.load_application_icon()) == [(37, 37)]


def test_a_corrupt_frozen_copy_falls_through_to_the_source_tree(tmp_path, monkeypatch):
    broken = tmp_path / "assets" / "icon.ico"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"\x00\x01\x02 not an icon at all")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    icon = application_icon.load_application_icon()

    assert not icon.isNull(), "坏掉的_MEIPASS 副本必须让位给源码树那一份"
    assert _icon_sizes(icon) == _declared_icon_sizes()


def test_missing_candidates_return_a_null_icon_without_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(application_icon, "APPLICATION_ICON_RELATIVE_PATH",
                        ("assets", "definitely-not-here.ico"))

    icon = application_icon.load_application_icon()

    assert icon.isNull()
    assert application_icon._ICON_CACHE is None, "失败结果不进缓存（文件补回来就该自愈）"


def test_a_single_corrupt_candidate_returns_a_null_icon(tmp_path, monkeypatch):
    broken = tmp_path / "assets" / "only.ico"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"garbage")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(application_icon, "APPLICATION_ICON_RELATIVE_PATH",
                        ("assets", "only.ico"))

    icon = application_icon.load_application_icon()

    assert icon.isNull()
    assert application_icon._ICON_CACHE is None


def test_no_qt_application_means_no_icon_and_no_cache(monkeypatch):
    """应用还没起来就构造 QIcon 会让进程死掉（见模块 docstring 的「必须在 Qt GUI 应用
    建好之后…」一段）。"""
    monkeypatch.setattr(application_icon, "QGuiApplication", _NO_APPLICATION)

    icon = application_icon.load_application_icon()

    assert icon.isNull()
    assert application_icon._ICON_CACHE is None


def test_icon_is_never_built_before_an_application_exists_in_a_fresh_process():
    """独立解释器里复现同一条：先没有任何 Qt 应用 → 空图标、退出码 0、什么都没缓存。

    留在子进程里跑是刻意的：本进程里 QApplication 早就有了，"没有应用"这个前提
    只能由干净解释器提供（也正是崩溃能发生在真实启动路径上的形态）。
    """
    script = (
        "import json\n"
        "import pet.application_icon as ai\n"
        "fresh = ai._ICON_CACHE is None\n"
        "icon = ai.load_application_icon()\n"
        "print(json.dumps({'fresh': fresh, 'null': icon.isNull(),\n"
        "                  'cached': ai._ICON_CACHE is not None}))\n"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(REPO))
    completed = subprocess.run([sys.executable, "-c", script], cwd=str(REPO), env=env,
                               capture_output=True, text=True, timeout=300)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload == {"fresh": True, "null": True, "cached": False}


def test_the_icon_is_built_once_per_application():
    first = application_icon.load_application_icon()

    assert application_icon.load_application_icon() is first
    assert application_icon.load_application_icon() is first


def test_the_cache_does_not_outlive_its_application(monkeypatch):
    holder = {"app": object()}

    class _SwappableApplication:
        @staticmethod
        def instance():
            return holder["app"]

    monkeypatch.setattr(application_icon, "QGuiApplication", _SwappableApplication)

    first = application_icon.load_application_icon()
    holder["app"] = object()  # 旧应用没了、新应用起来
    second = application_icon.load_application_icon()

    assert not first.isNull() and not second.isNull()
    assert second is not first, "换了应用实例就必须重新构造（旧 QIcon 属于旧应用）"


# ------------------------------------------------------------------ 三、脚本语法


@pytest.mark.parametrize("name", sorted(SHELLS))
def test_shell_build_scripts_stay_syntactically_valid(name):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("这台机器没有 bash（脚本语法门在 Linux/macOS 上生效）")

    completed = subprocess.run([bash, "-n", str(SHELLS[name])], capture_output=True, text=True,
                               timeout=120)

    assert completed.returncode == 0, completed.stderr


def test_windows_build_script_stays_syntactically_valid():
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        pytest.skip("这台机器没有 Windows PowerShell（语法门在 Windows 构建机上生效）")

    command = (
        f"$errors = $null; [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{PS1}', [ref]$null, [ref]$errors) > $null; "
        "if ($errors.Count -eq 0) { exit 0 } else { $errors | ForEach-Object { $_.Message }; exit 1 }"
    )
    completed = subprocess.run([str(powershell), "-NoProfile", "-Command", command],
                               capture_output=True, text=True, timeout=180)

    assert completed.returncode == 0, completed.stdout + completed.stderr


# ------------------------------------------------------------------ 四、打包接线


def test_the_windows_build_bundles_the_runtime_icon():
    text = PS1.read_text(encoding="utf-8")

    assert ADD_DATA_WINDOWS in text, f"没有把运行期图标打进包：期望 {ADD_DATA_WINDOWS}"
    command = text[text.index("python -m PyInstaller"):text.index("$entry\n")]
    assert ADD_DATA_WINDOWS in command, "--add-data 必须真的挂在 PyInstaller 命令上"


@pytest.mark.parametrize("name", sorted(SHELLS))
def test_the_shell_builds_bundle_the_runtime_icon(name):
    text = SHELLS[name].read_text(encoding="utf-8")

    assert ADD_DATA_POSIX in text, f"没有把运行期图标打进包：期望 {ADD_DATA_POSIX}"
    command = text[text.index("args=("):text.index(")\n", text.index("args=("))]
    assert ADD_DATA_POSIX in command, "--add-data 必须真的在 args 数组里"
    assert '"${args[@]}" "$entry"' in text, "args 数组必须真的被交给 PyInstaller"


def test_the_installer_ships_the_bundled_copy_without_extra_entries():
    """安装包不需要为图标加条目：它递归拷 onedir 整棵树，那条规则才是承重的。"""
    text = ISS.read_text(encoding="utf-8")

    assert 'SetupIconFile=..\\' + RELATIVE_POSIX.replace("/", "\\") in text
    assert re.search(r'Source:\s*"\{#MyAppDir\}\\?\*";\s*DestDir:\s*"\{app\}";'
                     r'\s*Flags:[^"\n]*recursesubdirs[^"\n]*createallsubdirs', text), \
        "安装包里没有递归拷贝 onedir 产物，图标会被漏掉"


def test_the_runtime_asset_is_the_icon_the_builds_already_generate():
    """打包脚本生成的那一份 == 运行期要读的那一份（换形象只需重跑 make_icon）。"""
    windows = PS1.read_text(encoding="utf-8")

    assert "scripts\\make_icon.py" in windows
    assert windows.index("scripts\\make_icon.py") < windows.index("python -m PyInstaller")
    macos = SHELLS["macos"].read_text(encoding="utf-8")
    assert "scripts/make_icon.py --icns" in macos
    assert ICON_FILE.is_file(), f"{ICON_FILE.relative_to(REPO).as_posix()} 不在树上"


def test_packaging_doc_registers_the_runtime_manifest():
    text = PACKAGING_DOC.read_text(encoding="utf-8")

    assert RELATIVE_POSIX in text
    for script in ("build_onedir.ps1", "build_macos.sh", "build_linux.sh"):
        assert script in text
    assert "tests/test_application_icon.py" in text
