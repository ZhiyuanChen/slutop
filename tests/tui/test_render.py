import io

from rich.console import Console

from slutop.api import Cluster, History, PollStatus
from slutop.tui.render import build_view, fmt_age, fmt_duration, fmt_mem, sparkline


def test_fmt_mem():
    assert fmt_mem(1024) == "1G"
    assert fmt_mem(1024 * 1024) == "1.0T"
    assert fmt_mem(512) == "512M"


def test_fmt_duration():
    assert fmt_duration(90) == "1m"
    assert fmt_duration(3700) == "1h01m"
    assert fmt_duration(90000) == "1d01h"


def test_fmt_age():
    assert fmt_age(18) == "18s"
    assert fmt_age(125) == "2m05s"
    assert fmt_age(3700) == "1h01m"


def test_sparkline_levels():
    line = sparkline([0, 50, 100], vmax=100).plain
    assert len(line) == 3
    assert line[0] == "▁"  # 0%
    assert line[-1] == "█"  # 100%


def test_sparkline_empty():
    assert sparkline([]).plain == ""


def test_build_view_renders_without_error(cluster: Cluster):
    console = Console(file=io.StringIO(), width=120)
    console.print(build_view(cluster, me="someone", partition="gpu", timestamp="2026-06-23 14:30:05"))
    out = console.file.getvalue()
    assert "slutop" in out
    assert "node1" in out
    assert "2026-06-23 14:30:05" in out  # timestamp shown top-right


def test_build_view_with_history_shows_sparkline(json_source):
    c = Cluster(nodes=json_source.nodes(), jobs=json_source.jobs())
    h = History()
    for _ in range(5):
        h.update(c)
    console = Console(file=io.StringIO(), width=120, no_color=True)
    console.print(build_view(c, history=h))
    out = console.file.getvalue()
    assert any(level in out for level in "▁▂▃▄▅▆▇█")


def test_build_view_shows_poll_status(cluster: Cluster):
    console = Console(file=io.StringIO(), width=120, no_color=True)
    status = PollStatus(jobs_stale=True, jobs_age=18, nodes_age=7, error="jobs: squeue timeout")
    console.print(build_view(cluster, status=status))
    out = console.file.getvalue()
    assert "jobs stale 18s" in out
    assert "nodes 7s old" in out
    assert "jobs: squeue timeout" in out
