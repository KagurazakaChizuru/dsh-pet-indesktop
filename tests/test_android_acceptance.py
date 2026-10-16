"""The acceptance script's parsing contract; no device, SDK or APK required."""
from scripts.android_acceptance import (Device, counter, deltas, parse_cpu, parse_dump, parse_gfxinfo,
                                        parse_modules, parse_pss, summarize_samples)


def test_switching_off_the_last_module_accepts_an_empty_enabled_set(tmp_path):
    class DeviceWithNoModules(Device):
        def launch(self):
            return "already running"

        def runtime(self):
            return {"running": "true", "modules": "[]"}

        def wait(self, predicate, description, timeout=30):
            return super().wait(predicate, description, timeout=.01)

    device = DeviceWithNoModules("unused-adb", "fake-os-boundary", tmp_path)
    assert device.set_module("collision", False) == []

#: The current dump, as `dumpsys activity service` prints the service's own lines.
DUMP = """running=true paused=false interactive=true
pets=3 windows=3 draws=8412
windowOps=37 bubbles=1 stale=0 audio=2
decoded=9031 reused=8120 hits=8900 misses=131 cached=26 cacheKB=23456
modules=[companion, speech, wander] frames=8412 customPhrases=2
mode=IDLE x=301.5 y=418.0 clip=idle_979fb57debe4
phrase=只属于我的台词
gesture=none
"""

#: 0.1.0 prints two lines plus a mode; every newer key must simply stay absent.
OLD_DUMP = """running=true paused=false interactive=true
windows=1 draws=12 decoded=9
mode=IDLE x=301.5 y=418.0 clip=idle_979fb57debe4
gesture=none
"""

GFXINFO = """Applications Graphics Acceleration Info:
Uptime: 123456 Realtime: 123456

** Graphics info for pid 4321 [io.github.dshpet.mobile] **

Stats since: 1234ns
Total frames rendered: 240
Janky frames: 12 (5.00%)
Janky frames (legacy): 12 (5.00%)
50th percentile: 6ms
90th percentile: 9ms
95th percentile: 12ms
99th percentile: 21ms
Number Missed Vsync: 3
Number High input latency: 0
Number Slow UI thread: 2
Number Slow bitmap uploads: 0
Number Slow issue draw commands: 5
"""

TOP = """Tasks: 600 total, 1 running
  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS
 4321 u0_a123      20   0 3.5G 120M 60M S 27.4  3.1   1:02.33 io.github.dshpet.mobile
"""

MEMINFO = """
** MEMINFO in pid 4321 [io.github.dshpet.mobile] **
                   Pss  Private  Private  SwapPss      Rss     Heap     Heap     Heap
                 Total    Dirty    Clean    Dirty    Total     Size    Alloc     Free
TOTAL PSS:    57000  TOTAL RSS:    91000
"""


def test_parse_dump_reads_every_pair_on_every_line():
    values = parse_dump(DUMP)
    assert values["pets"] == "3"
    assert values["windows"] == "3"
    assert values["windowOps"] == "37"
    assert values["stale"] == "0"
    assert values["audio"] == "2"
    assert values["cacheKB"] == "23456"
    assert values["customPhrases"] == "2"
    assert values["x"] == "301.5"
    assert values["clip"] == "idle_979fb57debe4"
    assert values["phrase"] == "只属于我的台词"
    assert values["gesture"] == "none"


def test_parse_dump_keeps_a_bracket_list_that_contains_spaces():
    assert parse_dump(DUMP)["modules"] == "[companion, speech, wander]"
    assert parse_modules(parse_dump(DUMP)["modules"]) == {"companion", "speech", "wander"}
    assert parse_dump("modules=[wander] frames=1")["frames"] == "1"
    assert parse_modules("[]") == set()
    assert parse_modules(None) == set()


def test_parse_dump_leaves_the_keys_of_an_older_apk_missing():
    values = parse_dump(OLD_DUMP)
    assert values["windows"] == "1"
    assert values["mode"] == "IDLE"
    assert values["x"] == "301.5"
    assert values["gesture"] == "none"
    for key in ("pets", "windowOps", "bubbles", "stale", "audio", "cacheKB", "customPhrases",
                "modules", "frames", "phrase"):
        assert values.get(key) is None


def test_service_record_fields_do_not_win_over_the_service_dump():
    blob = ("  ServiceRecord{9a2d4c u0 io.github.dshpet.mobile/.PetOverlayService}\n"
            "    app=ProcessRecord{1 2 io.github.dshpet.mobile/1000}\n"
            "    windows=999 draws=0 mode=DRAG\n" + DUMP)
    values = parse_dump(blob)
    assert values["windows"] == "3"
    assert values["draws"] == "8412"
    assert values["mode"] == "IDLE"


def test_counter_and_deltas_read_missing_keys_as_zero():
    before, after = parse_dump(OLD_DUMP), parse_dump(DUMP)
    assert counter(before, "windowOps") == 0
    assert counter(after, "gesture") == 0
    assert deltas(before, after, ("pets", "windowOps", "decoded")) == {
        "pets": 3, "windowOps": 37, "decoded": 9022}


def test_parse_gfxinfo_reads_the_jank_numbers():
    values = parse_gfxinfo(GFXINFO)
    assert values["total_frames"] == 240
    assert values["janky_frames"] == 12
    assert values["janky_percent"] == 5.0
    assert values["p50_ms"] == 6
    assert values["p90_ms"] == 9
    assert values["p95_ms"] == 12
    assert values["p99_ms"] == 21
    assert values["missed_vsync"] == 3
    assert values["slow_ui_thread"] == 2
    assert values["slow_bitmap_uploads"] == 0
    assert values["slow_draw_commands"] == 5


def test_parse_gfxinfo_reports_missing_fields_as_none():
    values = parse_gfxinfo("Total frames rendered: 0\n")
    assert values["total_frames"] == 0
    assert values["janky_frames"] is None
    assert values["janky_percent"] is None
    assert values["p99_ms"] is None
    assert values["missed_vsync"] is None


def test_parse_pss_and_cpu_read_both_android_generations():
    assert parse_pss(MEMINFO) == 57000
    assert parse_pss("                TOTAL:   56066\n") == 56066
    assert parse_pss("no totals here") is None
    assert parse_cpu(TOP, 4321) == 27.4
    assert parse_cpu(TOP, 9999) is None


def test_summarize_samples_reports_pss_cpu_and_frame_rates():
    samples = [
        {"timestamp": 100.0, "pid": 4321, "memory": MEMINFO, "cpu": TOP,
         "runtime": parse_dump(OLD_DUMP)},
        {"timestamp": 110.0, "pid": 4321, "memory": MEMINFO, "cpu": TOP,
         "runtime": parse_dump(DUMP)},
    ]
    summary = summarize_samples(samples)
    assert summary["samples"] == 2
    assert summary["elapsed_seconds"] == 10.0
    assert summary["pss_kib"] == {"first": 57000, "last": 57000, "max": 57000, "median": 57000}
    assert summary["cpu_percent"] == {"median": 27.4, "max": 27.4}
    assert summary["frames"] == [12, 8412]
    assert summary["frames_per_second"] == 840.0
    assert summarize_samples([]) == {}
