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

"""Adaptive cluster polling helpers."""

from __future__ import annotations

import time
from collections.abc import Callable

from .models import Cluster, Node
from .source import Source

ACTIVE_REFRESH_INTERVAL = 2.0
IDLE_REFRESH_INTERVAL = 5.0
NODE_REFRESH_INTERVAL = 30.0
MIN_REFRESH_INTERVAL = 0.1


def filter_cluster(cluster: Cluster, user: str | None, partition: str | None) -> Cluster:
    """Restrict a cluster snapshot to the requested user and partition."""
    if partition:
        cluster.nodes = [n for n in cluster.nodes if partition in n.partitions]
    jobs = cluster.jobs
    if user:
        jobs = [j for j in jobs if j.user == user]
    if partition:
        jobs = [j for j in jobs if j.partition == partition]
    cluster.jobs = jobs
    return cluster


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


def bounded_interval(value: float, minimum: float = MIN_REFRESH_INTERVAL) -> float:
    """Clamp refresh intervals so invalid values cannot busy-loop."""
    return max(float(value), minimum)


class CachedCollector:
    """Collect jobs frequently while caching node snapshots between slower refreshes."""

    def __init__(self, source: Source, node_interval: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.source = source
        self.node_interval = bounded_interval(node_interval)
        self.clock = clock
        self._nodes: list[Node] | None = None
        self._nodes_at = float("-inf")
        self._signature: tuple | None = None
        self.stable_refreshes = 0
        self.changed = True

    def collect(self, user: str | None = None, partition: str | None = None) -> Cluster:
        """Collect jobs and cached nodes, refreshing nodes when stale or jobs change."""
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
        return filter_cluster(Cluster(nodes=list(self._nodes), jobs=jobs), user, partition)

    def next_interval(self, active_interval: float, idle_interval: float, cluster: Cluster) -> float:
        """Return the next polling interval from the current cluster state."""
        active = bounded_interval(active_interval)
        idle = max(active, bounded_interval(idle_interval))
        if self.changed or cluster.pending_jobs or self.stable_refreshes < 2:
            return active
        return idle
