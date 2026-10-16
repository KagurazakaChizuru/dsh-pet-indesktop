"""Exercise the installed APK through adb and Android UI, and retain evidence.

Use a dedicated emulator or test handset: this changes this app's permissions.
All waits poll real state with deadlines; timed observation windows measure
that drawing has stopped, rather than guessing when a transition will finish.

`--frames LABEL` is the before/after probe: it resets HWUI frame statistics, runs
one scripted interaction and writes `gfxinfo-<label>.txt` plus the parsed numbers
into `acceptance.json`, so the 0.1.0 build and the module kernel are measured by
the same code path. That probe reads only `draws`, `mode` and the OS window list,
so it also runs against a dump that has none of the newer keys.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from pathlib import Path

PACKAGE = "io.github.dshpet.mobile"
SERVICE = PACKAGE + "/.PetOverlayService"

#: The settings row that carries each module's enable bit. Both labels of every
#: row are passed to the UI lookups, because the device locale decides which one
#: a dump carries.
MODULE_ROWS = {
    "wander": ("Wander around", "自由游走"),
    "speech": ("Speech bubbles", "台词气泡"),
    "clickSound": ("Tap sound", "点击音效"),
    "companion": ("Baby whales", "小鲸鱼"),
    "collision": ("Pet collisions", "桌宠碰撞"),
}

DECODER_COUNTERS = ("decoded", "reused", "hits", "misses", "cached", "cacheKB", "stale")


def parse_dump(text: str) -> dict[str, str]:
    """Every `key=value` pair on every line of a service dump, values as strings.

    Keys the installed APK does not print stay absent instead of raising, so one
    parser reads the 0.1.0 dump (two lines plus `mode`) and the module kernel's.
    Framework fields of the ServiceRecord come before the service's own lines, so
    a later value wins over a same-named field.
    """
    values = dict(re.findall(r"(\w+)=(\[[^\]]*\])", text))
    values.update(re.findall(r"(\w+)=(\S+)", re.sub(r"\w+=\[[^\]]*\]", "", text)))
    return values


def parse_modules(value: str | None) -> set[str]:
    """The `modules=[a, b]` field as a set: the list carries spaces."""
    return {item.strip() for item in (value or "").strip("[]").split(",") if item.strip()}


def counter(dump: dict[str, str], name: str) -> int:
    """One dump counter; a key this build does not print reads 0."""
    try:
        return int(dump.get(name) or 0)
    except ValueError:
        return 0


def deltas(before: dict[str, str], after: dict[str, str], names: Iterable[str]) -> dict[str, int]:
    return {name: counter(after, name) - counter(before, name) for name in names}


def parse_gfxinfo(text: str) -> dict[str, object]:
    """The jank numbers of `dumpsys gfxinfo`; a field this build omits stays None."""
    values: dict[str, object] = {}
    total = re.search(r"Total frames rendered:\s*(\d+)", text)
    values["total_frames"] = int(total[1]) if total else None
    janky = re.search(r"Janky frames:\s*(\d+)\s*\(([\d.]+)%\)", text)
    values["janky_frames"] = int(janky[1]) if janky else None
    values["janky_percent"] = float(janky[2]) if janky else None
    percentiles = {match[1]: int(match[2])
                   for match in re.finditer(r"(\d+)(?:st|nd|rd|th) percentile:\s*(\d+)ms", text)}
    for rank in ("50", "90", "95", "99"):
        values[f"p{rank}_ms"] = percentiles.get(rank)
    for label, key in (("Number Missed Vsync", "missed_vsync"),
                       ("Number Slow UI thread", "slow_ui_thread"),
                       ("Number Slow bitmap uploads", "slow_bitmap_uploads"),
                       ("Number Slow issue draw commands", "slow_draw_commands")):
        found = re.search(re.escape(label) + r":\s*(\d+)", text)
        values[key] = int(found[1]) if found else None
    return values


def parse_pss(meminfo: str) -> int | None:
    """The process PSS in KiB: Android 8 prints `TOTAL:`, newer builds `TOTAL PSS:`."""
    for pattern in (r"TOTAL PSS:\s*(\d+)", r"TOTAL:\s*(\d+)"):
        found = re.search(pattern, meminfo)
        if found:
            return int(found[1])
    return None


def parse_cpu(top_output: str, pid: int) -> float | None:
    """The process `%CPU` from `top -b`; column 8 is what the soak summary reads."""
    for line in reversed(top_output.splitlines()):
        fields = line.split()
        if fields and fields[0] == str(pid) and len(fields) > 8:
            try:
                return float(fields[8])
            except ValueError:
                return None
    return None


def summarize_samples(samples: Sequence[dict]) -> dict:
    """PSS, CPU, frame and decode numbers over one sample window."""
    if not samples:
        return {}
    pss = [value for sample in samples if (value := parse_pss(sample["memory"])) is not None]
    cpu = [value for sample in samples if (value := parse_cpu(sample["cpu"], sample["pid"])) is not None]
    first, last = samples[0]["runtime"], samples[-1]["runtime"]
    elapsed = samples[-1]["timestamp"] - samples[0]["timestamp"]
    frames = counter(last, "draws") - counter(first, "draws")
    decoded = counter(last, "decoded") - counter(first, "decoded")
    return {
        "samples": len(samples),
        "elapsed_seconds": round(elapsed, 3),
        "pss_kib": {"first": pss[0], "last": pss[-1], "max": max(pss),
                    "median": statistics.median(pss)} if pss else None,
        "cpu_percent": {"median": statistics.median(cpu), "max": max(cpu)} if cpu else None,
        "frames": [counter(first, "draws"), counter(last, "draws")],
        "frames_per_second": round(frames / elapsed, 3) if elapsed > 0 else None,
        "decoded": [counter(first, "decoded"), counter(last, "decoded")],
        "decoded_per_second": round(decoded / elapsed, 3) if elapsed > 0 else None,
        "stale": counter(last, "stale") - counter(first, "stale"),
    }


class Device:
    def __init__(self, adb: str, serial: str, output: Path):
        self.adb, self.serial, self.output = adb, serial, output
        self.output.mkdir(parents=True, exist_ok=True)
        self.observations = []

    def run(self, *args: str) -> str:
        for attempt in range(3):
            result = subprocess.run([self.adb, "-s", self.serial, *map(str, args)],
                                    capture_output=True, encoding="utf-8", errors="replace", timeout=45)
            if result.returncode == 0 or "device offline" not in result.stderr or attempt == 2:
                break
            # An offline transport rejected the command before it reached Android.
            subprocess.run([self.adb, "-s", self.serial, "wait-for-device"],
                           capture_output=True, timeout=30, check=True)
        if result.returncode:
            raise RuntimeError(f"adb {args}: exit={result.returncode}: {result.stderr or result.stdout}")
        return result.stdout.strip()

    def shell(self, *args: str) -> str:
        return self.run("shell", *args)

    def record(self, name: str, value):
        self.observations.append({"name": name, "value": value, "at": time.time()})
        (self.output / "acceptance.json").write_text(json.dumps(
            {"serial": self.serial, "is_emulator": self.serial.startswith("emulator-"),
             "observations": self.observations}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name}: {value}", flush=True)

    def wait(self, predicate, description: str, timeout: float = 30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            threading.Event().wait(.15)
        raise AssertionError(f"Timed out: {description}")

    # ---- service dump ------------------------------------------------------

    def runtime(self) -> dict[str, str]:
        """The service dump as strings; a key the installed APK omits is absent."""
        return parse_dump(self.shell("dumpsys", "activity", "service", SERVICE))

    def number(self, name: str) -> int:
        return counter(self.runtime(), name)

    def modules(self) -> set[str]:
        return parse_modules(self.runtime().get("modules"))

    def service_absent(self) -> bool:
        """Whether the service's own dump is gone: `running` is its first key.

        The framework prints its own key/value fields around the record, so absence
        is read from the service's own key rather than from an empty dict.
        """
        return self.runtime().get("running") is None

    def household(self) -> tuple[int, int] | None:
        """(pets, windows) as the service reports them; None while it is not up."""
        dump = self.runtime()
        if dump.get("running") is None:
            return None
        return counter(dump, "pets"), counter(dump, "windows")

    def wait_windows(self, expected: int | None = None, timeout: float = 30) -> list[int]:
        """Wait until `windows` equals `pets` (or `expected`), and return both counts."""
        def ready():
            state = self.household()
            if state is None:
                return None
            pets, windows = state
            if expected is None:
                return list(state) if pets >= 1 and windows == pets else None
            return list(state) if windows == expected else None
        label = "pets" if expected is None else expected
        return self.wait(ready, f"pets/windows overlay count == {label}", timeout)

    def wait_household(self, expected: int, timeout: float = 30) -> list[int]:
        """Wait until `pets` and `windows` both equal `expected`: babies are windows too."""
        def ready():
            state = self.household()
            return list(state) if state == (expected, expected) else None
        return self.wait(ready, f"pets == windows == {expected}", timeout)

    # ---- UI hierarchy ------------------------------------------------------

    def raw_ui(self) -> str:
        """The UI hierarchy XML, saved verbatim whenever a lookup fails."""
        self.shell("uiautomator", "dump", "/sdcard/pet-ui.xml")
        return self.shell("cat", "/sdcard/pet-ui.xml")

    def ui(self):
        return ET.fromstring(self.raw_ui())

    def bounds(self, node: ET.Element) -> tuple[int, int, int, int]:
        left, top, right, bottom = map(int, re.findall(r"-?\d+", node.get("bounds", "")))
        return left, top, right, bottom

    def screen(self) -> tuple[int, int]:
        """The display size; `wm size` may print an override line first."""
        width, height = re.findall(r"(\d+)x(\d+)", self.shell("wm", "size"))[-1]
        return int(width), int(height)

    def on_screen(self, node: ET.Element, size: tuple[int, int] | None = None) -> bool:
        """Whether a node's centre is inside the display, so a tap can reach it.

        Compose dumps the off-screen rows of the settings page as well, so being
        present in the tree is not the same as being tappable.
        """
        width, height = size or self.screen()
        left, top, right, bottom = self.bounds(node)
        return (right > left and bottom > top
                and 0 <= (left + right) // 2 < width and 0 <= (top + bottom) // 2 < height)

    def node(self, *labels: str, classes: tuple[str, ...] = (), enabled: bool = True) -> ET.Element | None:
        """The first on-screen node of this app with one of these texts or classes.

        The dump carries every window, including the launcher's own labels, so a
        lookup is scoped to this package: the pet menu's "Settings" row must never
        resolve to the launcher's Settings icon.
        """
        texts = {label.casefold() for label in labels}
        size = self.screen()
        for candidate in self.ui().iter("node"):
            if candidate.get("package") != PACKAGE:
                continue
            if enabled and candidate.get("enabled") != "true":
                continue
            if not self.on_screen(candidate, size):
                continue
            if texts and candidate.get("text", "").casefold() in texts:
                return candidate
            if classes and any(name in candidate.get("class", "") for name in classes):
                return candidate
        return None

    def scroll(self, direction: int) -> None:
        """Scroll the settings page one screen: +1 towards the rows below, -1 back."""
        width, height = self.screen()
        start, end = (height * 3 // 4, height // 4) if direction > 0 else (height // 4, height * 3 // 4)
        self.shell("input", "swipe", width // 2, start, width // 2, end, "250")

    def row(self, *labels: str, classes: tuple[str, ...] = (), enabled: bool = True,
            passes: int = 4) -> ET.Element:
        """A settings row, scrolling until it is on screen.

        A row that cannot be found fails loudly with the UI dump: silently
        skipping it would turn a broken build into a green report.
        """
        for direction in (1, -1):
            for _ in range(passes):
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    found = self.node(*labels, classes=classes, enabled=enabled)
                    if found is not None:
                        return found
                    threading.Event().wait(.15)
                self.scroll(direction)
        path = self.output / "ui-missing.xml"
        path.write_text(self.raw_ui(), encoding="utf-8")
        raise AssertionError(f"UI row {labels or classes} not found; dump saved to {path}")

    def tap_node(self, node: ET.Element) -> None:
        left, top, right, bottom = self.bounds(node)
        self.shell("input", "tap", (left + right) // 2, (top + bottom) // 2)

    def tap_text(self, *labels: str):
        self.tap_node(self.row(*labels))

    def tap(self, x: int, y: int) -> None:
        self.shell("input", "tap", x, y)

    def long_press(self, x: int, y: int) -> None:
        """A still press past ViewConfiguration's long-press timeout opens the menu."""
        self.shell("input", "swipe", x, y, x, y, "1500")

    def slider(self, *labels: str) -> ET.Element:
        """The slider a labelled row owns; Compose puts the label in its description."""
        def found():
            texts = {label.casefold() for label in labels}
            size = self.screen()
            for candidate in self.ui().iter("node"):
                if (candidate.get("content-desc", "").casefold() in texts
                        and "SeekBar" in candidate.get("class", "")
                        and self.on_screen(candidate, size)):
                    return [candidate]
            return None
        return self.wait(found, f"slider {labels}", timeout=20)[0]

    def row_value(self, *labels: str) -> str | None:
        """The value a settings row prints on its own line, right of the label."""
        label = self.row(*labels)
        left, top, right, bottom = self.bounds(label)
        for candidate in self.ui().iter("node"):
            text = candidate.get("text", "")
            if not text or candidate is label:
                continue
            node_left, node_top, _, _ = self.bounds(candidate)
            if abs(node_top - top) <= max(1, (bottom - top) // 2) and node_left >= right:
                return text
        return None

    def shortest_gap(self) -> str | None:
        """Tap the track start; dragging from its right edge can trigger Android Back."""
        self.row("Shortest gap", "最短间隔")
        left, top, right, bottom = self.bounds(self.slider("Shortest gap", "最短间隔"))
        middle = (top + bottom) // 2
        self.tap(left + 2, middle)
        return self.row_value("Shortest gap", "最短间隔")

    def lines_field(self) -> ET.Element:
        """The phrases box, scrolled into view by the label that owns it."""
        self.row("Lines", "台词池")
        return self.row(classes=("EditText",))

    def field_text(self) -> str:
        found = self.node(classes=("EditText",), enabled=False)
        return found.get("text", "") if found is not None else ""

    def type_text(self, text: str) -> None:
        """`input text` runs on the device shell: spaces become `%s`, so stay ASCII."""
        if not re.fullmatch(r"[\w.-]+", text):
            raise ValueError(f"input text only accepts a plain ASCII token: {text!r}")
        self.shell("input", "text", text)

    def clear_lines_field(self) -> None:
        """Empty the phrases box: `input text` appends to whatever draft is there."""
        draft = self.field_text()
        if not draft:
            return
        self.shell("input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(min(len(draft), 120)):
            self.shell("input", "keyevent", "KEYCODE_DEL")
        remaining = self.field_text()
        if remaining:
            raise AssertionError(f"Phrases field cannot be cleared: {remaining!r}")

    def keyboard_visible(self) -> bool:
        """The soft keyboard covers the lower rows, so the save button waits it out."""
        return "mInputShown=true" in self.shell("dumpsys", "input_method")

    def hide_keyboard(self) -> None:
        """Back closes the soft keyboard, and finishes the activity when it is not up."""
        if not self.keyboard_visible():
            return
        self.shell("input", "keyevent", "KEYCODE_BACK")
        self.wait(lambda: not self.keyboard_visible(), "keyboard hidden")

    # ---- system windows ----------------------------------------------------

    def flags(self, block: str) -> int | None:
        """The legacy hex window flags; newer dumps name the flags instead."""
        legacy = re.search(r"\bfl=#([0-9a-fA-F]+)", block)
        return int(legacy[1], 16) if legacy else None

    def touchable(self, block: str) -> bool:
        flags = self.flags(block)
        return "NOT_TOUCHABLE" not in block and (flags is None or not flags & 0x10)

    def focusable(self, block: str) -> bool:
        flags = self.flags(block)
        return "NOT_FOCUSABLE" not in block and (flags is None or not flags & 0x08)

    def screenshot(self, name: str):
        for _ in range(3):
            result = subprocess.run([self.adb, "-s", self.serial, "exec-out", "screencap", "-p"],
                                    capture_output=True, timeout=30)
            if result.returncode == 0 and result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                (self.output / f"{name}.png").write_bytes(result.stdout)
                return
        raise RuntimeError(f"screenshot capture failed: {result.returncode}: {result.stderr!r}")

    def overlays(self) -> list[str]:
        """Every app overlay window block: the pets, the bubbles and the actions menu."""
        windows = self.shell("dumpsys", "window", "windows")
        return [block for block in re.split(r"\n  Window #", windows)
                if f"package={PACKAGE}" in block and "appop=SYSTEM_ALERT_WINDOW" in block]

    def bubble_windows(self) -> list[str]:
        """The pass-through overlay windows: the speech bubbles, never a pet."""
        return [block for block in self.overlays() if not self.touchable(block)]

    def action_menu(self) -> bool:
        """The long-press menu is the app's only overlay window that takes focus."""
        return any(self.touchable(block) and self.focusable(block)
                   and "mForceHideNonSystemOverlayWindow=true" not in block
                   for block in self.overlays())

    def pet_center(self):
        for block in self.overlays():
            if not self.touchable(block):
                continue
            if "mForceHideNonSystemOverlayWindow=true" in block:
                continue
            if self.focusable(block):
                continue
            match = re.search(r"\b(?:mFrame|frame)=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", block)
            if match:
                left, top, right, bottom = map(int, match.groups())
                return (left + right) // 2, (top + bottom) // 2
        raise AssertionError("Pet overlay window not found")

    # ---- app control -------------------------------------------------------

    def launch(self):
        self.shell("cmd", "statusbar", "collapse")
        return self.shell("am", "start", "-W", "-n", PACKAGE + "/.MainActivity")

    def go_home(self):
        home = self.shell("cmd", "package", "resolve-activity", "--brief", "-a",
                          "android.intent.action.MAIN", "-c", "android.intent.category.HOME").splitlines()[-1]
        self.shell("am", "start", "-W", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")
        self.wait(lambda: any(n.get("package") == home.split("/")[0] for n in self.ui().iter("node")),
                  "launcher in foreground")

    def ensure_running(self) -> dict:
        """Bring the pet up and drawing: the frame probe also runs on a fresh install."""
        dump = self.runtime()
        if dump.get("running") != "true":
            self.shell("appops", "set", PACKAGE, "SYSTEM_ALERT_WINDOW", "allow")
            self.shell("am", "force-stop", PACKAGE)
            self.launch()
            self.tap_text("Start", "启动")
            dump = self.wait(lambda: d if (d := self.runtime()).get("running") == "true" else None,
                             "pet running after the standalone start")
        if dump.get("paused") == "true":
            self.launch()
            self.tap_text("Resume", "继续")
            dump = self.wait(lambda: d if (d := self.runtime()).get("paused") == "false" else None,
                             "pet resumed for the probe")
        return dump

    def fling(self, x: int, y: int) -> dict:
        """Throw the pet away from the nearer edge and return the dump in flight."""
        _, height = self.screen()
        target_y = max(150, y - 500) if y > height / 2 else min(height - 150, y + 500)
        # Older adb input injects fewer MOVE samples; a 350ms fling remains fast
        # while supplying enough samples to the real platform VelocityTracker.
        self.shell("input", "swipe", x, y, x, target_y, "350")
        return self.wait(lambda: d if (d := self.runtime()).get("mode") == "THROWN" else None,
                         "fling enters thrown mode", timeout=5)

    def open_settings(self) -> None:
        """Open the settings screen from the pet's own menu, the way a user does."""
        x, y = self.pet_center()
        self.long_press(x, y)
        self.tap_text("Settings", "设置")
        self.wait(lambda: not self.action_menu(), "settings screen opened from the pet menu")

    def set_module(self, module: str, enabled: bool) -> list[str]:
        """Switch one module through its settings row and return the observed set."""
        self.launch()
        if (module in self.modules()) != enabled:
            self.tap_text(*MODULE_ROWS[module])
        def applied():
            snapshot = self.runtime()
            current = parse_modules(snapshot.get("modules"))
            if snapshot.get("running") == "true" and (module in current) == enabled:
                return {"modules": sorted(current)}
            return None

        return self.wait(applied, f"module {module} {'enabled' if enabled else 'disabled'}")["modules"]

    # ---- feature checks ----------------------------------------------------

    def check_module_defaults(self) -> None:
        """A fresh install enables every current module, including tap sound."""
        observed = self.wait(lambda: sorted(modules) if (modules := self.modules()) else None,
                             "module set in the service dump")
        assert set(MODULE_ROWS) <= set(observed), observed
        self.record("module_defaults", observed)

    def check_bubble_lines(self) -> None:
        """A line typed on the phone must be the line the bubble shows.

        The pool is emptied first because `input text` types into a real input
        connection: an appended draft would make the bubble show either line.
        """
        line = "dsh-pet-acceptance-line"
        self.launch()
        # Looked up before the keyboard opens and again after it closes: leaving the
        # field also commits the draft, and a committed row is a disabled button.
        self.row("Save lines", "保存台词", enabled=False)
        gap = self.shortest_gap()
        self.tap_node(self.lines_field())
        self.clear_lines_field()
        self.type_text(line)
        # A phone with a hardware keyboard shows no soft one, so the real proof that
        # the tap focused the field is the draft the device's own input connection got.
        keyboard = self.keyboard_visible()
        self.wait(lambda: line if line in self.field_text() else None, "typed line in the field")
        self.hide_keyboard()
        self.tap_node(self.row("Save lines", "保存台词", enabled=False))
        self.go_home()
        phrase = self.wait(lambda: p if (p := self.runtime().get("phrase")) == line else None,
                           "the user line becomes the bubble text", timeout=120)
        dump = self.runtime()
        assert counter(dump, "customPhrases") == 1, dump
        self.record("bubble_from_user_lines",
                    {"line": line, "phrase": phrase, "customPhrases": counter(dump, "customPhrases"),
                     "bubbles": counter(dump, "bubbles"), "shortest_gap": gap,
                     "keyboard_visible": keyboard})

    def check_baby_whales(self) -> None:
        """Two spawns and one removal, each confirmed by the pet and window counts."""
        spawned = []
        for expected in (2, 3):
            x, y = self.pet_center()
            self.long_press(x, y)
            self.tap_text("Spawn baby whale", "生小鲸鱼")
            spawned.append(self.wait_household(expected))
        x, y = self.pet_center()
        self.long_press(x, y)
        self.tap_text("Remove baby whale", "退出小鲸鱼")
        self.record("baby_whales", {"spawned": spawned, "removed": self.wait_household(2)})

    def check_click_sound(self) -> None:
        """Check dispatch and gating; audible output needs a separate audio capture."""
        self.set_module("clickSound", False)
        before = self.runtime()
        assert "clickSound" not in parse_modules(before.get("modules")), before
        enabled = self.set_module("clickSound", True)
        self.go_home()
        x, y = self.pet_center()
        audio = counter(before, "audio")
        self.tap(x, y)
        played = self.wait(lambda: a if (a := self.number("audio")) > audio else None,
                           "click sound accepted by the platform player")
        self.open_settings()
        disabled = self.set_module("clickSound", False)
        self.go_home()
        self.record("click_sound", {"enabled": enabled, "audio_plays": [audio, played],
                                    "disabled": disabled})

    def check_idle_churn(self) -> None:
        """An idle pet must not touch its window geometry.

        Wander, speech and pet-to-pet collision are switched off first: the
        observation needs a pet that is really parked, a bubble window is a window
        that moves on its own, and a collision (the household may still hold the
        baby whale the spawn check left behind) moves windows by design.
        """
        self.set_module("wander", False)
        quiet = self.set_module("speech", False)
        self.set_module("collision", False)
        self.go_home()
        self.wait(lambda: self.runtime().get("mode") == "IDLE", "pet parked in its idle loop")
        self.wait(lambda: not self.bubble_windows(), "no bubble window on screen")
        before = self.runtime()
        self.wait(lambda: self.number("draws") - counter(before, "draws") >= 40, "40 idle frames")
        after = self.runtime()
        observed = deltas(before, after, ("draws", "windowOps", "stale"))
        assert observed["windowOps"] == 0, {"before": before, "after": after}
        self.record("window_churn_while_idle",
                    {"modules": quiet, "draws": observed["draws"],
                     "windowOps": [counter(before, "windowOps"), counter(after, "windowOps")],
                     "stale": observed["stale"]})
        self.set_module("collision", True)
        self.set_module("wander", True)
        self.set_module("speech", True)
        self.go_home()

    def check_decoder_health(self) -> None:
        """Decoder counters over a window in which frames were really delivered."""
        before = self.runtime()
        delivered = self.wait(lambda: d if (d := self.number("draws") - counter(before, "draws")) >= 40 else None,
                              "40 delivered frames")
        observed = {"frames_delivered": delivered, **deltas(before, self.runtime(), DECODER_COUNTERS)}
        self.record("decoder_health", observed)

    # ---- frame probe -------------------------------------------------------

    def frames(self, label: str) -> dict:
        """HWUI frame statistics for one scripted interaction, saved verbatim.

        This is the before/after probe, so it touches only state both builds have:
        the `draws` and `mode` counters and the OS window list.
        """
        self.ensure_running()
        self.go_home()
        self.shell("dumpsys", "gfxinfo", PACKAGE, "reset")
        x, y = self.pet_center()
        for _ in range(5):
            drawn = self.number("draws")
            self.tap(x, y)
            self.wait(lambda: self.number("draws") >= drawn + 8, "tap animation advances")
            x, y = self.pet_center()
        self.fling(x, y)
        self.wait(lambda: self.runtime().get("mode") != "THROWN", "fling settles")
        x, y = self.pet_center()
        self.long_press(x, y)
        self.wait(self.action_menu, "long-press menu opens")
        self.shell("input", "keyevent", "KEYCODE_BACK")
        self.wait(lambda: not self.action_menu(), "long-press menu closes")
        raw = self.shell("dumpsys", "gfxinfo", PACKAGE)
        (self.output / f"gfxinfo-{label}.txt").write_text(raw, encoding="utf-8")
        state = self.runtime()
        observed = {**parse_gfxinfo(raw),
                    "state": {key: state.get(key) for key in ("pets", "windows", "modules", "frames")}}
        self.record(f"frames_{label}", observed)
        return observed

    # ---- sampling ----------------------------------------------------------

    def sample(self) -> dict:
        pid = self.shell("pidof", PACKAGE)
        if not pid.isdigit():
            raise RuntimeError("Pet process stopped during measurement")
        return {"timestamp": time.time(), "serial": self.serial, "pid": int(pid),
                "runtime": self.runtime(),
                "memory": self.shell("dumpsys", "meminfo", PACKAGE),
                "cpu": self.shell("top", "-b", "-d", "1", "-n", "2", "-p", pid),
                "threads": self.shell("ps", "-T", "-p", pid),
                "battery": self.shell("dumpsys", "battery")}

    def sample_window(self, seconds: float, path: Path) -> list[dict]:
        """The soak sampler over a bounded window; the raw samples land in `path`."""
        samples = []
        deadline = time.monotonic() + seconds
        with path.open("a", encoding="utf-8") as output:
            while True:
                sample = self.sample()
                samples.append(sample)
                output.write(json.dumps(sample, ensure_ascii=False) + "\n")
                output.flush()
                if time.monotonic() >= deadline:
                    return samples
                threading.Event().wait(min(5, max(0, deadline - time.monotonic())))

    def module_sweep(self, seconds: float) -> list[dict]:
        """Sample PSS, CPU, frames and decodes with one module switched off at a time."""
        self.ensure_running()
        path = self.output / "module-sweep.jsonl"
        path.unlink(missing_ok=True)
        results = []
        for module in MODULE_ROWS:
            off = self.set_module(module, False)
            self.go_home()
            samples = self.sample_window(seconds, path)
            on = self.set_module(module, True)
            self.go_home()
            summary = {"module": module, "seconds": seconds, "modules_off": off, "modules_on": on,
                       **summarize_samples(samples)}
            self.record(f"module_sweep_{module}", summary)
            results.append(summary)
        return results

    # ---- the full pass -----------------------------------------------------

    def check(self):
        self.record("android", self.shell("getprop", "ro.build.version.release"))
        self.shell("am", "force-stop", PACKAGE)
        self.shell("appops", "set", PACKAGE, "SYSTEM_ALERT_WINDOW", "deny")
        self.launch()
        nodes = list(self.ui().iter("node"))
        assert any(n.get("text") in ("Allow overlay", "允许悬浮显示") for n in nodes)
        self.screenshot("permission-denied")
        self.record("permission_denied", "permission action visible; service absent")
        assert self.service_absent()
        self.shell("appops", "set", PACKAGE, "SYSTEM_ALERT_WINDOW", "allow")
        if int(self.shell("getprop", "ro.build.version.sdk")) >= 33:
            self.shell("pm", "grant", PACKAGE, "android.permission.POST_NOTIFICATIONS")
        self.shell("am", "force-stop", PACKAGE)
        launches = []
        for _ in range(3):
            self.shell("am", "force-stop", PACKAGE)
            launches.append(self.launch())
        self.record("cold_launches", launches)
        self.tap_text("Start", "启动")
        self.wait(lambda: self.number("draws") >= 3, "first pet frames")
        self.go_home()
        self.screenshot("home-overlay")
        self.shell("am", "start", "-W", "-a", "android.settings.SETTINGS")
        self.wait(lambda: any(n.get("package") == "com.android.settings" for n in self.ui().iter("node")),
                  "system settings in foreground")
        self.record("over_settings", self.wait_windows())
        self.screenshot("system-settings")
        self.record("system_overlay_policy", "mForceHideNonSystemOverlayWindow=true" in
                    self.shell("dumpsys", "window", "windows"))
        self.go_home()
        self.wait(lambda: "mForceHideNonSystemOverlayWindow=true" not in
                  self.shell("dumpsys", "window", "windows"), "leave protected system screen")
        clock = self.shell("cmd", "package", "resolve-activity", "--brief", "-a",
                           "android.intent.action.SHOW_ALARMS").splitlines()[-1]
        if "/" in clock and " " not in clock:
            clock = self.shell("cmd", "package", "resolve-activity", "--brief", "-a",
                               "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                               clock.split("/")[0]).splitlines()[-1]
            self.shell("am", "start", "-W", "-a", "android.intent.action.MAIN", "-n", clock)
            self.wait(lambda: any(n.get("package") == clock.split("/")[0] for n in self.ui().iter("node")),
                      "clock activity in foreground")
            self.screenshot("other-app-overlay")
            self.record("other_app", clock)
            self.go_home()
        x, y = self.pet_center()
        self.record("fling", self.fling(x, y))
        self.wait(lambda: self.runtime().get("mode") != "THROWN", "fling settles")
        x, y = self.pet_center()
        self.long_press(x, y)
        self.tap_text("Pause", "暂停")
        self.wait(lambda: self.runtime().get("paused") == "true", "pause")
        baseline = self.runtime()
        threading.Event().wait(2)
        after = self.runtime()
        assert counter(after, "draws") == counter(baseline, "draws"), (baseline, after)
        self.record("paused_observation_2s", after)
        self.shell("input", "keyevent", "KEYCODE_SLEEP")
        self.record("screen_off", self.wait_windows(0))
        assert not self.overlays()
        baseline = self.runtime()
        threading.Event().wait(2)
        after = self.runtime()
        assert counter(after, "draws") == counter(baseline, "draws"), (baseline, after)
        assert counter(after, "decoded") == counter(baseline, "decoded"), (baseline, after)
        self.record("screen_off_observation_2s", after)
        self.shell("input", "keyevent", "KEYCODE_WAKEUP")
        self.shell("wm", "dismiss-keyguard")
        self.record("unlock", self.wait_windows())
        self.launch()
        self.tap_text("Resume", "继续")
        self.wait(lambda: self.runtime().get("paused") == "false", "resume")
        self.check_module_defaults()
        self.check_bubble_lines()
        self.check_baby_whales()
        self.check_click_sound()
        self.check_idle_churn()
        self.check_decoder_health()
        self.launch()
        self.tap_text("Stop", "停止")
        self.wait(lambda: self.service_absent() and not self.overlays(), "stop removes service and OS windows")
        self.record("explicit_stop", "service and application overlay windows absent")
        self.record("explicit_stop_observed",
                    {"service_dump_keys": sorted(self.runtime()), "overlay_windows": len(self.overlays())})
        self.tap_text("Start", "启动")
        self.wait(lambda: self.runtime().get("running") == "true", "restart before revocation")
        self.shell("appops", "set", PACKAGE, "SYSTEM_ALERT_WINDOW", "deny")
        self.wait(self.service_absent, "revoked permission stops service")
        self.record("permission_revoked", "service removed")
        self.shell("appops", "set", PACKAGE, "SYSTEM_ALERT_WINDOW", "allow")
        self.shell("am", "force-stop", PACKAGE)
        self.launch()
        self.tap_text("Start", "启动")
        self.wait(lambda: self.runtime().get("running") == "true", "restart after permission restored")
        self.go_home()
        self.record("result", "PASS")

    def measure(self, minutes: float):
        path = self.output / "performance.jsonl"
        deadline = time.monotonic() + minutes * 60
        with path.open("w", encoding="utf-8") as output:
            while True:
                record = self.sample()
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                if time.monotonic() >= deadline:
                    break
                threading.Event().wait(min(30, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minutes", type=float, default=0)
    parser.add_argument("--measure-only", action="store_true")
    parser.add_argument("--frames", metavar="LABEL",
                        help="only reset and read HWUI frame statistics, writing gfxinfo-LABEL.txt")
    parser.add_argument("--module-sweep", type=float, default=0, metavar="SECONDS",
                        help="sample each module with it switched off for SECONDS")
    args = parser.parse_args()
    device = Device(args.adb, args.serial, args.output)
    if args.frames:
        device.frames(args.frames)
    elif not args.measure_only:
        device.check()
    if args.minutes:
        device.measure(args.minutes)
    if args.module_sweep:
        device.module_sweep(args.module_sweep)


if __name__ == "__main__":
    main()
