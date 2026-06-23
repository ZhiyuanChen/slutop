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

from collections.abc import Sequence

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..api.history import History
from ..api.models import Cluster, Job, Node
from . import theme as t

BAR_WIDTH = 8
SPARK_WIDTH = 24
_SPARK_LEVELS = "▁▂▃▄▅▆▇█"


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


def summary_panel(cluster: Cluster, timestamp: str | None = None, history: History | None = None) -> Panel:
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
    if timestamp:
        content = Group(Text(timestamp, justify="right", style=t.MUTED), grid)
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

    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style=f"bold {t.PRIMARY}",
        border_style=t.BORDER,
        show_edge=False,
        expand=True,
    )
    table.add_column("PART")
    table.add_column("NODE")
    table.add_column("STATE")
    table.add_column("GPU")
    table.add_column("CPU")
    table.add_column("MEM")
    for node in nodes:
        style = _node_style(node)
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


def build_view(
    cluster: Cluster,
    me: str | None = None,
    partition: str | None = None,
    timestamp: str | None = None,
    history: History | None = None,
) -> RenderableType:
    """Build the full snapshot renderable (summary + nodes + jobs).

    Blocks are separated by a single blank line for an even vertical rhythm.
    """
    return Group(
        summary_panel(cluster, timestamp=timestamp, history=history),
        Text(""),
        node_table(cluster, partition=partition),
        Text(""),
        jobs_table(cluster, me=me),
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
