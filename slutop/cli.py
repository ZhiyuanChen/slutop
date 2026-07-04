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

"""Command-line entry point for slutop.

argparse provides the ergonomic flag surface (short flags, ``-1``); the parsed
options live in a :class:`chanfig.Config`, and all JSON/dict handling goes
through chanfig.
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import select
import sys
import termios
import time
import tty
from dataclasses import asdict
from datetime import datetime

from chanfig import Config, NestedDict
from rich.console import Console

from . import __version__
from .api import CliSource, Cluster, History, Node, Source, snapshot
from .tui.render import build_view, render_snapshot

ACTIVE_REFRESH_INTERVAL = 2.0
IDLE_REFRESH_INTERVAL = 5.0
NODE_REFRESH_INTERVAL = 30.0
MIN_REFRESH_INTERVAL = 0.1
INPUT_TICK_INTERVAL = 0.25


def build_config(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(
        prog="slutop",
        description="An interactive monitor for Slurm clusters.",
    )
    parser.add_argument("-1", "--once", action="store_true", help="report once and exit")
    parser.add_argument("-u", "--user", metavar="USER", help="only show jobs of USER")
    parser.add_argument("--me", action="store_true", help="only show your own jobs")
    parser.add_argument("-p", "--partition", metavar="PART", help="restrict to a partition")
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=ACTIVE_REFRESH_INTERVAL,
        metavar="SEC",
        help="active refresh interval (monitor mode)",
    )
    parser.add_argument(
        "--idle-interval",
        type=float,
        default=IDLE_REFRESH_INTERVAL,
        metavar="SEC",
        help="refresh interval after the queue is stable (monitor mode)",
    )
    parser.add_argument(
        "--node-interval",
        type=float,
        default=NODE_REFRESH_INTERVAL,
        metavar="SEC",
        help="node refresh interval when the queue is stable (monitor mode)",
    )
    parser.add_argument("-o", "--output", choices=["table", "json"], default="table", help="output format")
    parser.add_argument("--version", action="version", version=f"slutop {__version__}")
    args = parser.parse_args(argv)
    return Config(**vars(args))


def _filter_cluster(cluster: Cluster, user: str | None, partition: str | None) -> Cluster:
    if partition:
        cluster.nodes = [n for n in cluster.nodes if partition in n.partitions]
    jobs = cluster.jobs
    if user:
        jobs = [j for j in jobs if j.user == user]
    if partition:
        jobs = [j for j in jobs if j.partition == partition]
    cluster.jobs = jobs
    return cluster


def _payload(cluster: Cluster) -> NestedDict:
    """Serialise a snapshot into a chanfig NestedDict for JSON output."""
    return NestedDict(
        summary={
            "gpus_total": cluster.gpus_total,
            "gpus_used": cluster.gpus_used,
            "gpus_free": cluster.gpus_free,
            "cpus_total": cluster.cpus_total,
            "cpus_used": cluster.cpus_used,
            "cpus_free": cluster.cpus_free,
            "mem_total": cluster.mem_total,
            "mem_used": cluster.mem_used,
            "mem_free": cluster.mem_free,
            "running": len(cluster.running_jobs),
            "pending": len(cluster.pending_jobs),
        },
        nodes=[asdict(n) for n in cluster.nodes],
        jobs=[asdict(j) for j in cluster.jobs],
    )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _collect(source: Source, config: Config, user: str | None) -> Cluster:
    return _filter_cluster(snapshot(source), user, config.partition)


def _job_signature(cluster: Cluster) -> tuple:
    return tuple(
        (
            job.job_id,
            job.partition,
            job.state,
            job.reason,
            job.nodes,
            job.node_count,
            job.cpus,
            job.gpus,
            job.start_time,
            job.end_time,
        )
        for job in sorted(cluster.jobs, key=lambda j: j.job_id)
    )


def _bounded_interval(value: float, minimum: float = MIN_REFRESH_INTERVAL) -> float:
    return max(float(value), minimum)


class CachedCollector:
    """Collect jobs frequently while caching node snapshots between slower refreshes."""

    def __init__(self, source: Source, node_interval: float, clock=time.monotonic) -> None:
        self.source = source
        self.node_interval = _bounded_interval(node_interval)
        self.clock = clock
        self._nodes: list[Node] | None = None
        self._nodes_at = float("-inf")
        self._signature: tuple | None = None
        self.stable_refreshes = 0
        self.changed = True

    def collect(self, config: Config, user: str | None) -> Cluster:
        now = self.clock()
        jobs = self.source.jobs()
        cluster = Cluster(nodes=[], jobs=jobs)
        signature = _job_signature(cluster)
        self.changed = signature != self._signature
        self.stable_refreshes = 0 if self.changed else self.stable_refreshes + 1
        self._signature = signature

        nodes_due = self._nodes is None or self.changed or now - self._nodes_at >= self.node_interval
        if nodes_due:
            self._nodes = self.source.nodes()
            self._nodes_at = now

        assert self._nodes is not None
        return _filter_cluster(Cluster(nodes=list(self._nodes), jobs=jobs), user, config.partition)

    def next_interval(self, config: Config, cluster: Cluster) -> float:
        active = _bounded_interval(config.interval)
        idle = max(active, _bounded_interval(config.idle_interval))
        if self.changed or cluster.pending_jobs or self.stable_refreshes < 2:
            return active
        return idle


@contextlib.contextmanager
def _key_reader(stream=sys.stdin):
    """Yield ``read(timeout)`` -> a single keypress, or "" if none within ``timeout``.

    An interactive terminal is put in cbreak mode so keys register without Enter;
    a non-tty (piped output) just waits, leaving the refresh pacing unchanged.
    """
    if not stream.isatty():

        def read_idle(timeout: float) -> str:
            time.sleep(timeout)
            return ""

        yield read_idle
        return

    fd = stream.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:

        def read_key(timeout: float) -> str:
            ready, _, _ = select.select([stream], [], [], timeout)
            return stream.read(1) if ready else ""

        yield read_key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def _monitor(source: Source, config: Config, me: str | None, user: str | None) -> None:
    from rich.live import Live

    console = Console()
    history = History()
    collector = CachedCollector(source, config.node_interval)
    next_collect = 0.0
    with _key_reader() as read_key, Live(console=console, screen=True, auto_refresh=False) as live:
        while True:
            try:
                now = time.monotonic()
                if now >= next_collect:
                    cluster = collector.collect(config, user)
                    history.update(cluster)
                    live.update(
                        build_view(cluster, me=me, partition=config.partition, timestamp=_now(), history=history),
                        refresh=True,
                    )
                    next_collect = time.monotonic() + collector.next_interval(config, cluster)
                timeout = min(INPUT_TICK_INTERVAL, max(next_collect - time.monotonic(), 0.0))
                key = read_key(timeout)
            except KeyboardInterrupt:  # Ctrl-C
                break
            if key.lower() == "q":
                break


def main(argv: list[str] | None = None) -> int:
    config = build_config(argv)
    try:
        me = getpass.getuser()
    except Exception:  # noqa: BLE001 - getuser can raise on odd environments
        me = None
    user = me if config.me else config.user
    source = CliSource()

    if config.output == "json":
        print(_payload(_collect(source, config, user)).jsons())
        return 0

    if config.once:
        render_snapshot(_collect(source, config, user), me=me, partition=config.partition, timestamp=_now())
        return 0

    _monitor(source, config, me, user)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
