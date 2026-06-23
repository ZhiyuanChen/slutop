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

"""Sources of cluster state.

A :class:`Source` knows how to produce :class:`~slutop.api.models.Node` and
:class:`~slutop.api.models.Job` lists. :class:`CliSource` reads them from the
Slurm command-line tools, preferring ``--json`` and degrading gracefully where a
command or Slurm version does not support it. We deliberately never link against
``libslurm``/``pyslurm`` -- that version coupling is what bit-rots the other
Slurm monitors.
"""

from __future__ import annotations

import subprocess

from chanfig import NestedDict

from .models import Job, Node


class Source:
    """Abstract provider of cluster state.

    New backends (e.g. a ``slurmrestd`` REST source, or an optional accelerated
    one) only need to implement :meth:`nodes` and :meth:`jobs`, returning the
    typed models; everything downstream is source-agnostic.
    """

    def nodes(self) -> list[Node]:
        raise NotImplementedError

    def jobs(self) -> list[Job]:
        raise NotImplementedError


class CliSource(Source):
    """Read cluster state from the Slurm CLI (``scontrol``, ``sinfo``, ``squeue``)."""

    # Node sources in preference order. ``scontrol show node --json`` returns a
    # clean per-node ``nodes`` list on Slurm >=23.02; ``sinfo --json`` carries a
    # flat ``nodes`` list on Slurm <=21.08 (on newer Slurm its top-level key is
    # ``sinfo`` partition/state groups, which have no ``nodes`` list, so we skip).
    _NODE_COMMANDS = (
        ("scontrol", "show", "node", "--json"),
        ("sinfo", "--json"),
    )

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._node_command: tuple[str, ...] | None = None  # memo of the working node command

    def _run(self, *cmd: str) -> str:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, check=True)  # noqa: S603
        return result.stdout

    def _json(self, *cmd: str) -> NestedDict | None:
        """Run a command and parse its JSON stdout, or return ``None`` if it fails."""
        try:
            out = self._run(*cmd)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None  # e.g. "unrecognized option '--json'" on older Slurm
        try:
            return NestedDict.from_jsons(out)
        except (ValueError, TypeError):
            return None

    def nodes(self) -> list[Node]:
        commands = (self._node_command,) if self._node_command else self._NODE_COMMANDS
        for cmd in commands:
            data = self._json(*cmd)
            if data is not None and data.get("nodes"):
                self._node_command = cmd
                return [Node.from_node(n) for n in data["nodes"]]
        return self._nodes_text()

    def jobs(self) -> list[Job]:
        data = self._json("squeue", "--json")
        if data is not None:
            jobs = [Job.from_squeue(j) for j in data.get("jobs") or []]
            self._patch_usernames(jobs)
            return jobs
        return self._jobs_text()

    def _patch_usernames(self, jobs: list[Job]) -> None:
        """Backfill usernames left empty by ``squeue --json`` (a 21.08 quirk).

        This is the JSON-with-text-fallback pattern in miniature: the structured
        output is missing a field, so we top it up from a parseable format query.
        """
        if not any(not job.user for job in jobs):
            return
        try:
            out = self._run("squeue", "-h", "-a", "-o", "%i|%u")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return
        mapping: dict[int, str] = {}
        for line in out.splitlines():
            jid, _, user = line.partition("|")
            jid = jid.strip()
            if jid.isdigit():
                mapping[int(jid)] = user.strip()
        for job in jobs:
            if not job.user and job.job_id in mapping:
                job.user = mapping[job.job_id]

    # -- Text/format fallbacks for Slurm builds without --json -----------------
    # Implemented lazily: the JSON path covers Slurm >= 20.11 (sinfo/squeue) and
    # the structured v0.0.4x parsers via scontrol, i.e. the overwhelming majority
    # of live clusters. The hooks exist so the fallback can be added without
    # touching the rest of the codebase.

    def _nodes_text(self) -> list[Node]:
        raise NotImplementedError("no JSON node source available and the text fallback is not implemented yet")

    def _jobs_text(self) -> list[Job]:
        raise NotImplementedError("squeue --json is unavailable and the text fallback is not implemented yet")


class JsonSource(Source):
    """A source backed by pre-captured node/job JSON (for tests/replay).

    ``nodes`` accepts any payload with a top-level ``nodes`` list (``sinfo --json``
    on Slurm <=21.08 or ``scontrol show node --json`` on newer Slurm).
    """

    def __init__(self, nodes: str, jobs: str) -> None:
        self._nodes = NestedDict.from_jsons(nodes)
        self._jobs = NestedDict.from_jsons(jobs)

    def nodes(self) -> list[Node]:
        return [Node.from_node(n) for n in self._nodes.get("nodes") or []]

    def jobs(self) -> list[Job]:
        return [Job.from_squeue(j) for j in self._jobs.get("jobs") or []]
