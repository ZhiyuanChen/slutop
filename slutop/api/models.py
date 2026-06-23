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

"""Typed domain models for a cluster snapshot.

These are deliberately decoupled from how the data is fetched: a :class:`Node`
or :class:`Job` is built from a :class:`~chanfig.NestedDict` (parsed Slurm JSON)
via the ``from_*`` constructors, so the rest of slutop never touches raw Slurm
output formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chanfig import NestedDict

from .tres import parse_gres, parse_tres

# Node base-states / flags (lower-cased substrings) that make a node unusable for new work.
_UNUSABLE_STATES = (
    "down",
    "drain",
    "fail",
    "maint",
    "unknown",
    "not_responding",
    "reserved",
    "power_down",
    "powering_down",
)


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _epoch_or_none(value: object) -> int | None:
    n = _as_int(value, 0)
    return n or None


@dataclass
class Node:
    """A compute node and its current resource allocation."""

    name: str
    partitions: list[str] = field(default_factory=list)
    state: str = ""
    cpus_total: int = 0
    cpus_alloc: int = 0
    mem_total: float = 0.0  # MiB
    mem_alloc: float = 0.0  # MiB
    gpus_total: int = 0
    gpus_used: int = 0
    gres: str = ""

    @property
    def cpus_free(self) -> int:
        return max(self.cpus_total - self.cpus_alloc, 0)

    @property
    def mem_free(self) -> float:
        return max(self.mem_total - self.mem_alloc, 0.0)

    @property
    def gpus_free(self) -> int:
        return max(self.gpus_total - self.gpus_used, 0)

    @property
    def usable(self) -> bool:
        """Whether the node can accept new work (not down/drained/reserved)."""
        state = self.state.lower()
        return not any(flag in state for flag in _UNUSABLE_STATES)

    @property
    def available(self) -> bool:
        """Whether the node is usable *and* has at least one free GPU."""
        return self.usable and self.gpus_free > 0

    @classmethod
    def from_sinfo(cls, node: NestedDict) -> Node:
        """Build a :class:`Node` from one entry of ``sinfo --json``."""
        tres = parse_tres(node.get("tres"))
        used = parse_tres(node.get("tres_used"))
        gpus_total = _as_int(tres.get("gpu")) or _as_int(parse_gres(node.get("gres")).get("gpu"))
        gpus_used = _as_int(used.get("gpu")) or _as_int(parse_gres(node.get("gres_used")).get("gpu"))
        return cls(
            name=node.get("name", ""),
            partitions=list(node.get("partitions") or []),
            state=str(node.get("state", "")),
            cpus_total=_as_int(node.get("cpus")),
            cpus_alloc=_as_int(node.get("alloc_cpus")),
            mem_total=float(_as_int(node.get("real_memory"))),
            mem_alloc=float(_as_int(node.get("alloc_memory"))),
            gpus_total=gpus_total,
            gpus_used=gpus_used,
            gres=node.get("gres", "") or "",
        )


@dataclass
class Job:
    """A job in the queue (running, pending, or otherwise)."""

    job_id: int
    name: str = ""
    user: str = ""
    account: str = ""
    partition: str = ""
    state: str = ""
    reason: str = ""
    nodes: str = ""  # Slurm nodelist expression, e.g. "node[1-3]"
    node_count: int = 0
    cpus: int = 0
    gpus: int = 0
    start_time: int | None = None
    end_time: int | None = None
    time_limit: int | None = None  # minutes

    @property
    def running(self) -> bool:
        return self.state.upper().startswith("RUN")

    @property
    def pending(self) -> bool:
        return self.state.upper().startswith(("PEND", "PD"))

    @classmethod
    def from_squeue(cls, job: NestedDict) -> Job:
        """Build a :class:`Job` from one entry of ``squeue --json``."""
        alloc = parse_tres(job.get("tres_alloc_str"))
        req = parse_tres(job.get("tres_req_str"))
        gpus = _as_int(alloc.get("gpu")) or _as_int(req.get("gpu"))
        return cls(
            job_id=_as_int(job.get("job_id")),
            name=job.get("name", "") or "",
            user=job.get("user_name", "") or "",
            account=job.get("account", "") or "",
            partition=job.get("partition", "") or "",
            state=str(job.get("job_state", "")),
            reason=job.get("state_reason", "") or "",
            nodes=job.get("nodes", "") or "",
            node_count=_as_int(job.get("node_count")),
            cpus=_as_int(job.get("cpus")),
            gpus=gpus,
            start_time=_epoch_or_none(job.get("start_time")),
            end_time=_epoch_or_none(job.get("end_time")),
            time_limit=_epoch_or_none(job.get("time_limit")),
        )


@dataclass
class Cluster:
    """A point-in-time snapshot of the whole cluster."""

    nodes: list[Node] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)

    @property
    def gpus_total(self) -> int:
        return sum(n.gpus_total for n in self.nodes)

    @property
    def gpus_used(self) -> int:
        return sum(n.gpus_used for n in self.nodes)

    @property
    def gpus_free(self) -> int:
        return sum(n.gpus_free for n in self.nodes if n.usable)

    @property
    def gpus_unavailable(self) -> int:
        """Capacity on down/drained nodes (neither used nor usable-free)."""
        return max(self.gpus_total - self.gpus_used - self.gpus_free, 0)

    @property
    def cpus_total(self) -> int:
        return sum(n.cpus_total for n in self.nodes)

    @property
    def cpus_used(self) -> int:
        return sum(n.cpus_alloc for n in self.nodes)

    @property
    def cpus_free(self) -> int:
        return sum(n.cpus_free for n in self.nodes if n.usable)

    @property
    def cpus_unavailable(self) -> int:
        return max(self.cpus_total - self.cpus_used - self.cpus_free, 0)

    @property
    def mem_total(self) -> float:
        return sum(n.mem_total for n in self.nodes)

    @property
    def mem_used(self) -> float:
        return sum(n.mem_alloc for n in self.nodes)

    @property
    def mem_free(self) -> float:
        return sum(n.mem_free for n in self.nodes if n.usable)

    @property
    def mem_unavailable(self) -> float:
        return max(self.mem_total - self.mem_used - self.mem_free, 0.0)

    @property
    def running_jobs(self) -> list[Job]:
        return [j for j in self.jobs if j.running]

    @property
    def pending_jobs(self) -> list[Job]:
        return [j for j in self.jobs if j.pending]
