# slutop
# Copyright (C) 2026-Present  Zhiyuan Chen <this@zyc.ai>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Rich rendering of a cluster snapshot.

The headline is GPU availability (where are the free GPUs?), with a job overlay
and the current user's jobs surfaced. Colors follow the semantic roles in
:mod:`slutop.tui.theme`.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..api.collector import PollStatus
from ..api.history import History
from ..api.models import Cluster, Job, Node
from . import theme as t

BAR_WIDTH = 8
NODE_JOB_DETAIL_LIMIT = 8
SPARK_WIDTH = 24
USER_JOB_DETAIL_LIMIT = 8
_SPARK_LEVELS = "▁▂▃▄▅▆▇█"
_NODESET_RE = re.compile(r"(?P<prefix>[^\[,]+)\[(?P<body>[^\]]+)\]")


def fmt_mem(mib: float) -> str:
    """Human-readable memory from MiB (binary units)."""
    gib = mib / 1024
    if gib >= 1024:
        return f"{gib / 1024:.1f}T"
    if gib >= 1:
        return f"{gib:.0f}G"
    return f"{mib:.0f}M"


def fmt_duration(seconds: int) -> str:
    """Compact ``d-hh:mm`` style duration."""
    seconds = max(int(seconds), 0)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d{hours:02d}h"
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def fmt_age(seconds: float) -> str:
    """Compact age label for freshness indicators."""
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def fmt_time(epoch: int | None, now: int | None = None) -> str:
    """Compact wall-clock or relative time for Slurm epoch fields."""
    if not epoch:
        return ""
    now = int(datetime.now().timestamp()) if now is None else now
    delta = epoch - now
    if delta >= 0:
        return f"in {fmt_duration(delta)}"
    return f"{fmt_duration(-delta)} ago"


def _split_nodelist(nodes: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(nodes):
        if char == "[":
            depth += 1
        elif char == "]":
            depth = max(depth - 1, 0)
        elif char == "," and depth == 0:
            parts.append(nodes[start:index])
            start = index + 1
    parts.append(nodes[start:])
    return parts


def expand_nodelist(nodes: str) -> list[str]:
    """Expand common Slurm nodelist expressions like ``node[001-003,007]``."""
    if not nodes:
        return []
    expanded: list[str] = []
    for item in _split_nodelist(nodes):
        item = item.strip()
        if not item:
            continue
        match = _NODESET_RE.fullmatch(item)
        if match is None:
            expanded.append(item)
            continue
        prefix = match.group("prefix")
        for part in match.group("body").split(","):
            if "-" in part:
                start, end = part.split("-", 1)
                width = max(len(start), len(end))
                for index in range(int(start), int(end) + 1):
                    expanded.append(f"{prefix}{index:0{width}d}")
            else:
                expanded.append(f"{prefix}{part}")
    return expanded


def node_jobs(cluster: Cluster) -> dict[str, list[Job]]:
    """Map node names to running jobs, using the job nodelist expression."""
    jobs_by_node: dict[str, list[Job]] = {}
    for job in cluster.running_jobs:
        for node in expand_nodelist(job.nodes):
            jobs_by_node.setdefault(node, []).append(job)
    return jobs_by_node


def _job_state(job: Job) -> tuple[str, str]:
    if job.running:
        return "R", t.SUCCESS
    if job.pending:
        return "PD", t.WARNING
    return job.state[:2] or "?", t.MUTED


def _node_job_summary(jobs: Sequence[Job]) -> Text:
    if not jobs:
        return Text("")
    user_counts = Counter(job.user or "?" for job in jobs)
    users = ", ".join(
        f"{user} x{count}" if count > 1 else user
        for user, count in sorted(user_counts.items(), key=lambda item: item[0])
    )
    label = f"{len(jobs)} job{'s' if len(jobs) != 1 else ''}"
    return Text(f"{label} · {users}", style=t.ACCENT)


def _job_resources(job: Job) -> Text:
    parts: list[str] = []
    if job.gpus:
        parts.append(f"{job.gpus} gpu")
    if job.cpus:
        parts.append(f"{job.cpus} cpu")
    return Text(" · ".join(parts), style=t.MUTED)


def _job_time(job: Job) -> Text:
    if job.pending and job.start_time:
        return Text(f"starts {fmt_time(job.start_time)}", style=t.MUTED)
    if job.running and job.end_time:
        return Text(f"ends {fmt_time(job.end_time)}", style=t.MUTED)
    return Text("")


def _job_label(job: Job) -> Text:
    label = job.name
    if not label and job.pending and job.reason not in ("", "None"):
        label = job.reason
    return Text(label, style=t.MUTED)


def _job_info(job: Job) -> Text:
    parts: list[str] = []
    if job.name:
        parts.append(job.name)
    if job.pending and job.reason not in ("", "None"):
        parts.append(job.reason)
    if job.pending and job.start_time:
        parts.append(f"starts {fmt_time(job.start_time)}")
    if job.running and job.end_time:
        parts.append(f"ends {fmt_time(job.end_time)}")
    return Text(" · ".join(parts), style=t.MUTED)


def sparkline(values: Sequence[float], width: int = SPARK_WIDTH, vmax: float = 100.0) -> Text:
    """Render a Unicode block sparkline of the most recent ``width`` values.

    Values are scaled against a fixed ``vmax`` (default 100%) so the line shows
    absolute utilization rather than an auto-zoomed shape.
    """
    vals = list(values)[-width:]
    if not vals:
        return Text("")
    levels = _SPARK_LEVELS
    chars = []
    for value in vals:
        frac = 0.0 if vmax <= 0 else max(0.0, min(value / vmax, 1.0))
        chars.append(levels[min(int(frac * len(levels)), len(levels) - 1)])
    return Text("".join(chars), style=t.INFO_ALT)


def _node_style(node: Node) -> str:
    if not node.usable:
        return t.DANGER
    if node.gpus_free > 0:
        return t.PRIMARY
    return t.WARNING  # usable but fully allocated


def usage_bar(used: float, total: float, width: int = BAR_WIDTH) -> Text:
    """A utilization gauge: bay = used, fog = free."""
    if total <= 0:
        return Text("·" * width, style=t.MUTED)
    used_cells = min(round(used / total * width), width)
    return Text("█" * used_cells, style=t.GAUGE_USED) + Text("█" * (width - used_cells), style=t.GAUGE_FREE)


def _free_label(text: str, has_free: bool) -> Text:
    return Text(f" {text}", style=f"bold {t.PRIMARY}" if has_free else t.MUTED)


def resource_cell(used: float, total: float, free_text: str, has_free: bool, usable: bool) -> Text:
    """A gauge + ``free/total`` label for one resource on one node."""
    if not usable:
        # Node is down/drained: capacity exists but is not available.
        return Text("█" * BAR_WIDTH, style=t.DANGER) + Text(f" {free_text}", style=t.DANGER)
    return usage_bar(used, total) + _free_label(free_text, has_free)


def cluster_gauge(used: float, free: float, unavailable: float, width: int = 24) -> Text:
    """A cluster-wide stacked gauge: muted = used, green = free, red = unavailable (down)."""
    total = used + free + unavailable
    if total <= 0:
        return Text("·" * width, style=t.MUTED)
    used_cells = round(used / total * width)
    unavail_cells = round(unavailable / total * width)
    free_cells = max(width - used_cells - unavail_cells, 0)
    return (
        Text("█" * used_cells, style=t.GAUGE_USED)
        + Text("█" * free_cells, style=t.GAUGE_FREE)
        + Text("█" * unavail_cells, style=t.DANGER)
    )


def status_line(status: PollStatus | None) -> Text:
    """Render polling freshness/error state for the summary header."""
    if status is None:
        return Text("")
    parts: list[tuple[str, str]] = []
    if status.jobs_stale:
        parts.append((f"jobs stale {fmt_age(status.jobs_age)}", t.WARNING))
    if status.nodes_stale:
        parts.append((f"nodes stale {fmt_age(status.nodes_age)}", t.WARNING))
    if status.error:
        parts.append((status.error, t.DANGER))
    if not parts:
        return Text("")
    text = Text()
    for index, (part, style) in enumerate(parts):
        if index:
            text.append("  ·  ", style=t.MUTED)
        text.append(part, style=style)
    return text


def summary_panel(
    cluster: Cluster,
    timestamp: str | None = None,
    history: History | None = None,
    status: PollStatus | None = None,
) -> Panel:
    running = len(cluster.running_jobs)
    pending = len(cluster.pending_jobs)

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")  # label
    grid.add_column()  # gauge
    grid.add_column(style=t.MUTED)  # used/total (slash-aligned)
    grid.add_column()  # trend sparkline (monitor mode)

    def trend(series: Sequence[float]) -> Text:
        return sparkline(series) if len(series) >= 2 else Text("")

    gpu_hist = history.gpu if history else []
    cpu_hist = history.cpu if history else []
    mem_hist = history.mem if history else []

    # Right-pad the "used" side to a common width so the slash lines up across rows.
    used = (str(cluster.gpus_used), str(cluster.cpus_used), fmt_mem(cluster.mem_used))
    total = (str(cluster.gpus_total), str(cluster.cpus_total), fmt_mem(cluster.mem_total))
    uw = max(len(u) for u in used)

    def ratio(index: int) -> Text:
        return Text(f"{used[index]:>{uw}}/{total[index]}", style=t.MUTED)

    grid.add_row(
        "GPU",
        cluster_gauge(cluster.gpus_used, cluster.gpus_free, cluster.gpus_unavailable),
        ratio(0),
        trend(gpu_hist),
    )
    grid.add_row(
        "CPU",
        cluster_gauge(cluster.cpus_used, cluster.cpus_free, cluster.cpus_unavailable),
        ratio(1),
        trend(cpu_hist),
    )
    grid.add_row(
        "MEM",
        cluster_gauge(cluster.mem_used, cluster.mem_free, cluster.mem_unavailable),
        ratio(2),
        trend(mem_hist),
    )
    grid.add_row(
        "jobs",
        Text.assemble((f"{running} running", t.SUCCESS), "  ·  ", (f"{pending} pending", t.WARNING)),
        "",
        "",
    )
    content: RenderableType = grid
    header = Text(timestamp or "", justify="right", style=t.MUTED)
    status_text = status_line(status)
    if status_text.plain:
        if timestamp:
            header = Text.assemble((timestamp, t.MUTED), "  ", status_text, justify="right")
        else:
            header = Text.assemble(status_text, justify="right")
    if timestamp or status_text.plain:
        content = Group(header, grid)
    return Panel(
        content,
        title=Text("slutop", style=f"bold {t.PRIMARY}"),
        title_align="left",
        border_style=t.BORDER,
        box=box.ROUNDED,
    )


def node_table(cluster: Cluster, partition: str | None = None) -> Table:
    nodes = cluster.nodes
    if partition:
        nodes = [n for n in nodes if partition in n.partitions]
    # Group by partition, then free GPUs first within each; unusable nodes sink.
    nodes = sorted(nodes, key=lambda n: (",".join(n.partitions), not n.usable, -n.gpus_free, n.name))
    jobs_by_node = node_jobs(cluster)

    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style=f"bold {t.PRIMARY}",
        border_style=t.BORDER,
        show_edge=False,
        expand=True,
    )
    table.add_column("PART", no_wrap=True)
    table.add_column("NODE/JOB", no_wrap=True)
    table.add_column("STATE", no_wrap=True)
    table.add_column("GPU/USER", no_wrap=True)
    table.add_column("CPU/REQ", no_wrap=True)
    table.add_column("MEM/TIME", no_wrap=True)
    table.add_column("JOBS/NAME", min_width=12, ratio=1, no_wrap=True, overflow="ellipsis")
    for node in nodes:
        style = _node_style(node)
        jobs = sorted(jobs_by_node.get(node.name, []), key=lambda job: (job.user or "", job.job_id))
        table.add_row(
            ",".join(node.partitions),
            Text(node.name, style=style),
            Text(node.state.lower(), style=style),
            resource_cell(
                node.gpus_used, node.gpus_total, f"{node.gpus_free}/{node.gpus_total}", node.gpus_free > 0, node.usable
            ),
            resource_cell(
                node.cpus_alloc, node.cpus_total, f"{node.cpus_free}/{node.cpus_total}", node.cpus_free > 0, node.usable
            ),
            resource_cell(
                node.mem_alloc,
                node.mem_total,
                f"{fmt_mem(node.mem_free)}/{fmt_mem(node.mem_total)}",
                node.mem_free > 0,
                node.usable,
            ),
            _node_job_summary(jobs),
        )
        for job in jobs[:NODE_JOB_DETAIL_LIMIT]:
            state, state_style = _job_state(job)
            table.add_row(
                "",
                Text(f"  └─ #{job.job_id}", style=t.MUTED),
                Text(state, style=state_style),
                Text(job.user or "?", style=t.ACCENT),
                _job_resources(job),
                _job_time(job),
                _job_label(job),
            )
        if len(jobs) > NODE_JOB_DETAIL_LIMIT:
            table.add_row(
                "",
                Text("  └─ …", style=t.MUTED),
                "",
                "",
                "",
                "",
                Text(f"+{len(jobs) - NODE_JOB_DETAIL_LIMIT} more", style=t.MUTED),
            )
    return table


def users_table(cluster: Cluster) -> Table:
    """Aggregate jobs by user, with expandable job rows under each user."""
    jobs_by_user: dict[str, list[Job]] = {}
    for job in cluster.jobs:
        jobs_by_user.setdefault(job.user or "?", []).append(job)

    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style=f"bold {t.PRIMARY}",
        border_style=t.BORDER,
        show_edge=False,
        expand=True,
    )
    table.add_column("USER / JOB")
    table.add_column("ST")
    table.add_column("RUN", justify="right")
    table.add_column("PD", justify="right")
    table.add_column("GPU R/PD", justify="right")
    table.add_column("CPU R/PD", justify="right")
    table.add_column("NODES")
    table.add_column("INFO")

    def summary(jobs: Sequence[Job]) -> tuple[int, int, int, int, int, int, set[str]]:
        running = [job for job in jobs if job.running]
        pending = [job for job in jobs if job.pending]
        nodes: set[str] = set()
        for job in running:
            nodes.update(expand_nodelist(job.nodes))
        return (
            len(running),
            len(pending),
            sum(job.gpus for job in running),
            sum(job.gpus for job in pending),
            sum(job.cpus for job in running),
            sum(job.cpus for job in pending),
            nodes,
        )

    rows = []
    for user, jobs in jobs_by_user.items():
        running, pending, running_gpus, pending_gpus, running_cpus, pending_cpus, nodes = summary(jobs)
        rows.append((user, jobs, running, pending, running_gpus, pending_gpus, running_cpus, pending_cpus, nodes))
    rows.sort(key=lambda row: (-row[4], -row[5], -row[2], -row[3], row[0]))

    if not rows:
        table.add_row(Text("no jobs", style=t.MUTED), "", "", "", "", "", "", "")
        return table

    for user, jobs, running, pending, running_gpus, pending_gpus, running_cpus, pending_cpus, nodes in rows:
        pending_reasons = Counter(job.reason for job in jobs if job.pending and job.reason not in ("", "None"))
        reason_text = ", ".join(
            f"{reason} x{count}" if count > 1 else reason
            for reason, count in sorted(pending_reasons.items(), key=lambda item: (-item[1], item[0]))[:3]
        )
        table.add_row(
            Text(user, style=t.ACCENT if running else t.WARNING),
            "",
            str(running),
            str(pending),
            f"{running_gpus}/{pending_gpus}",
            f"{running_cpus}/{pending_cpus}",
            str(len(nodes)) if nodes else "",
            Text(reason_text, style=t.MUTED),
        )
        for job in sorted(jobs, key=_job_sort_key)[:USER_JOB_DETAIL_LIMIT]:
            state, state_style = _job_state(job)
            where = job.nodes if job.running else str(job.node_count or "")
            table.add_row(
                Text(f"  └─ #{job.job_id}", style=t.MUTED),
                Text(state, style=state_style),
                "",
                "",
                str(job.gpus) if job.gpus else "",
                str(job.cpus) if job.cpus else "",
                where,
                _job_info(job),
            )
        if len(jobs) > USER_JOB_DETAIL_LIMIT:
            table.add_row(
                Text("  └─ …", style=t.MUTED),
                "",
                "",
                "",
                "",
                "",
                "",
                Text(f"+{len(jobs) - USER_JOB_DETAIL_LIMIT} more", style=t.MUTED),
            )
    return table


def _job_sort_key(job: Job) -> tuple:
    # Pending first (you want to see what's waiting), then running; bigger GPU asks first.
    rank = 0 if job.pending else 1 if job.running else 2
    return (rank, -job.gpus, job.job_id)


def jobs_table(cluster: Cluster, me: str | None = None, limit: int = 15) -> Table:
    jobs = sorted(cluster.jobs, key=_job_sort_key)
    shown = jobs[:limit]

    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style=f"bold {t.PRIMARY}",
        border_style=t.BORDER,
        show_edge=False,
        expand=True,
    )
    table.add_column("JOBID", justify="right")
    table.add_column("USER")
    table.add_column("PART")
    table.add_column("ST")
    table.add_column("GPU", justify="right")
    table.add_column("NODES")
    table.add_column("INFO")
    for job in shown:
        mine = bool(me) and job.user == me
        if job.running:
            st_style = t.SUCCESS
        elif job.pending:
            st_style = t.WARNING
        else:
            st_style = t.MUTED
        st = "R" if job.running else "PD" if job.pending else (job.state[:2] or "?")
        info = job.reason if (job.pending and job.reason not in ("", "None")) else (job.nodes or "")
        user_text = Text(job.user or "?", style=f"bold {t.ACCENT}" if mine else "")
        table.add_row(
            str(job.job_id),
            user_text,
            job.partition,
            Text(st, style=st_style),
            str(job.gpus),
            str(job.node_count) if job.pending else job.nodes,
            info,
        )
    if len(jobs) > limit:
        table.caption = f"… and {len(jobs) - limit} more"
        table.caption_style = t.MUTED
    return table


def my_jobs_table(cluster: Cluster, me: str | None, limit: int = 12) -> Panel:
    """Jobs owned by the current user, split by running/pending state through sorting."""
    table = jobs_table(
        Cluster(nodes=cluster.nodes, jobs=[job for job in cluster.jobs if me and job.user == me]), me=me, limit=limit
    )
    return Panel(
        table,
        title=Text("my jobs", style=f"bold {t.ACCENT}"),
        title_align="left",
        border_style=t.BORDER,
        box=box.ROUNDED,
    )


def pending_reasons_panel(cluster: Cluster) -> Panel:
    """Aggregate pending jobs by Slurm reason."""
    reasons: dict[str, tuple[int, int, set[str]]] = {}
    for job in cluster.pending_jobs:
        reason = job.reason if job.reason not in ("", "None") else "unknown"
        count, gpus, users = reasons.get(reason, (0, 0, set()))
        users.add(job.user or "?")
        reasons[reason] = (count + 1, gpus + job.gpus, users)

    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style=f"bold {t.PRIMARY}",
        border_style=t.BORDER,
        show_edge=False,
        expand=True,
    )
    table.add_column("REASON")
    table.add_column("JOBS", justify="right")
    table.add_column("GPU", justify="right")
    table.add_column("USERS")
    for reason, (count, gpus, users) in sorted(reasons.items(), key=lambda item: (-item[1][0], item[0])):
        table.add_row(reason, str(count), str(gpus), ", ".join(sorted(users)[:5]))
    if not reasons:
        table.add_row(Text("no pending jobs", style=t.MUTED), "", "", "")
    return Panel(
        table,
        title=Text("pending reasons", style=f"bold {t.WARNING}"),
        title_align="left",
        border_style=t.BORDER,
        box=box.ROUNDED,
    )


def soon_free_panel(cluster: Cluster, limit: int = 8, now: int | None = None) -> Panel:
    """Running jobs ordered by expected end time."""
    jobs = sorted(
        (job for job in cluster.running_jobs if job.end_time), key=lambda job: (job.end_time or 0, job.job_id)
    )
    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style=f"bold {t.PRIMARY}",
        border_style=t.BORDER,
        show_edge=False,
        expand=True,
    )
    table.add_column("FREE IN")
    table.add_column("JOBID", justify="right")
    table.add_column("USER")
    table.add_column("PART")
    table.add_column("GPU", justify="right")
    table.add_column("NODES")
    for job in jobs[:limit]:
        table.add_row(
            fmt_time(job.end_time, now=now), str(job.job_id), job.user or "?", job.partition, str(job.gpus), job.nodes
        )
    if not jobs:
        table.add_row(Text("no running jobs with end times", style=t.MUTED), "", "", "", "", "")
    elif len(jobs) > limit:
        table.caption = f"… and {len(jobs) - limit} more"
        table.caption_style = t.MUTED
    return Panel(
        table,
        title=Text("soon free", style=f"bold {t.INFO}"),
        title_align="left",
        border_style=t.BORDER,
        box=box.ROUNDED,
    )


def jobs_panel(cluster: Cluster, me: str | None = None) -> Panel:
    return Panel(
        jobs_table(cluster, me=me),
        title=Text("jobs", style=f"bold {t.PRIMARY}"),
        title_align="left",
        border_style=t.BORDER,
        box=box.ROUNDED,
    )


def nodes_panel(cluster: Cluster, partition: str | None = None) -> Panel:
    return Panel(
        node_table(cluster, partition=partition),
        title=Text("nodes", style=f"bold {t.PRIMARY}"),
        title_align="left",
        border_style=t.BORDER,
        box=box.ROUNDED,
    )


def users_panel(cluster: Cluster) -> Panel:
    return Panel(
        users_table(cluster),
        title=Text("users", style=f"bold {t.ACCENT}"),
        title_align="left",
        border_style=t.BORDER,
        box=box.ROUNDED,
    )


def build_view(
    cluster: Cluster,
    me: str | None = None,
    partition: str | None = None,
    timestamp: str | None = None,
    history: History | None = None,
    status: PollStatus | None = None,
) -> RenderableType:
    """Build the full snapshot renderable (summary + nodes + jobs).

    Blocks are separated by a single blank line for an even vertical rhythm.
    """
    return Group(
        summary_panel(cluster, timestamp=timestamp, history=history, status=status),
        Text(""),
        nodes_panel(cluster, partition=partition),
        Text(""),
        users_panel(cluster),
        Text(""),
        pending_reasons_panel(cluster),
        Text(""),
        soon_free_panel(cluster),
        Text(""),
        my_jobs_table(cluster, me=me),
        Text(""),
        jobs_panel(cluster, me=me),
    )


def render_snapshot(
    cluster: Cluster,
    me: str | None = None,
    partition: str | None = None,
    timestamp: str | None = None,
    console: Console | None = None,
) -> None:
    """Print a one-shot snapshot of the cluster."""
    (console or Console()).print(build_view(cluster, me=me, partition=partition, timestamp=timestamp))
