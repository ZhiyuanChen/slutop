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
import getpass
from dataclasses import asdict
from datetime import datetime

from chanfig import Config, NestedDict

from . import __version__
from .api import (
    ACTIVE_REFRESH_INTERVAL,
    IDLE_REFRESH_INTERVAL,
    NODE_REFRESH_INTERVAL,
    CliSource,
    Cluster,
    Source,
    filter_cluster,
    snapshot,
)
from .tui.render import render_snapshot
from .tui.textual_app import run_textual_monitor


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
    return filter_cluster(snapshot(source), user, config.partition)


def _monitor(source: Source, config: Config, me: str | None, user: str | None) -> None:
    run_textual_monitor(
        source,
        active_interval=config.interval,
        idle_interval=config.idle_interval,
        node_interval=config.node_interval,
        me=me,
        user=user,
        partition=config.partition,
    )


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
