import io

from rich.console import Console

from slutop.api import Cluster, History, Job, Node, PollStatus
from slutop.tui.render import (
    build_view,
    expand_nodelist,
    fmt_age,
    fmt_duration,
    fmt_mem,
    node_table,
    sparkline,
    users_table,
)


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


def test_expand_nodelist():
    assert expand_nodelist("node[1-2],gpu007") == ["node1", "node2", "gpu007"]
    assert expand_nodelist("node[001-002,010]") == ["node001", "node002", "node010"]


def test_sparkline_levels():
    line = sparkline([0, 50, 100], vmax=100).plain
    assert len(line) == 3
    assert line[0] == "▁"  # 0%
    assert line[-1] == "█"  # 100%


def test_sparkline_empty():
    assert sparkline([]).plain == ""


def test_build_view_renders_without_error(cluster: Cluster):
    console = Console(file=io.StringIO(), width=120)
    console.print(build_view(cluster, me="yuanle", partition="gpu", timestamp="2026-06-23 14:30:05"))
    out = console.file.getvalue()
    assert "slutop" in out
    assert "node1" in out
    assert "2026-06-23 14:30:05" in out  # timestamp shown top-right
    assert "pending reasons" in out
    assert "soon free" in out
    assert "my jobs" in out
    assert "users" in out
    assert "#1001" in out  # node job/user overlay


def test_node_table_expands_running_jobs_per_node():
    cluster = Cluster(
        nodes=[
            Node(
                name="node1",
                partitions=["gpu"],
                state="mixed",
                cpus_total=64,
                cpus_alloc=12,
                mem_total=1024,
                mem_alloc=512,
                gpus_total=8,
                gpus_used=3,
            )
        ],
        jobs=[
            Job(job_id=101, name="train-a", user="alice", state="RUNNING", nodes="node1", gpus=1, cpus=4),
            Job(job_id=102, name="train-b", user="alice", state="RUNNING", nodes="node1", gpus=1, cpus=4),
            Job(job_id=103, name="eval", user="bob", state="RUNNING", nodes="node1", gpus=1, cpus=4),
            Job(job_id=201, name="waiting", user="carol", state="PENDING", nodes="node1", gpus=1, cpus=4),
        ],
    )
    console = Console(file=io.StringIO(), width=120, no_color=True)
    console.print(node_table(cluster))
    out = console.file.getvalue()
    assert "3 jobs" in out
    assert "alice x2, bob" in out
    assert "#101" in out
    assert "#102" in out
    assert "#103" in out
    assert "train-a" in out
    assert "#201" not in out


def test_users_table_aggregates_jobs_by_user():
    cluster = Cluster(
        nodes=[],
        jobs=[
            Job(job_id=101, name="train-a", user="alice", state="RUNNING", nodes="node1", gpus=1, cpus=4),
            Job(job_id=102, name="train-b", user="alice", state="PENDING", reason="Resources", gpus=2, cpus=8),
            Job(job_id=103, name="eval", user="bob", state="RUNNING", nodes="node[2-3]", gpus=2, cpus=16),
        ],
    )
    console = Console(file=io.StringIO(), width=120, no_color=True)
    console.print(users_table(cluster))
    out = console.file.getvalue()
    assert "alice" in out
    assert "1/2" in out  # alice's running/pending GPUs
    assert "4/8" in out  # alice's running/pending CPUs
    assert "Resources" in out
    assert "#101" in out
    assert "#102" in out
    assert "node1" in out
    assert "bob" in out
    assert "2/0" in out  # bob's running/pending GPUs


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
    assert "nodes 7s old" not in out
    assert "jobs: squeue timeout" in out
