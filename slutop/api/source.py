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
    """Abstract provider of cluster state."""

    def nodes(self) -> list[Node]:
        raise NotImplementedError

    def jobs(self) -> list[Job]:
        raise NotImplementedError


class CliSource(Source):
    """Read cluster state from the Slurm CLI (``sinfo``, ``squeue``)."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        # Per-binary memo of whether ``--json`` is supported (None = untested).
        self._json_ok: dict[str, bool | None] = {}

    def _run(self, *cmd: str) -> str:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, check=True)  # noqa: S603
        return result.stdout

    def _json(self, binary: str, *args: str) -> NestedDict | None:
        """Run ``<binary> --json <args>`` and parse it, or return ``None`` if unsupported."""
        if self._json_ok.get(binary) is False:
            return None
        try:
            out = self._run(binary, "--json", *args)
        except subprocess.CalledProcessError:
            # e.g. "unrecognized option '--json'" on older Slurm.
            self._json_ok[binary] = False
            return None
        self._json_ok[binary] = True
        return NestedDict.from_jsons(out)

    def nodes(self) -> list[Node]:
        data = self._json("sinfo")
        if data is not None:
            return [Node.from_sinfo(n) for n in data.get("nodes") or []]
        return self._nodes_text()

    def jobs(self) -> list[Job]:
        data = self._json("squeue")
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
    # Implemented lazily: the JSON path covers Slurm >= 20.11 for sinfo/squeue,
    # which is the overwhelming majority of live clusters. The hooks exist so the
    # fallback can be added without touching the rest of the codebase.

    def _nodes_text(self) -> list[Node]:
        raise NotImplementedError("sinfo --json is unavailable and the text fallback is not implemented yet")

    def _jobs_text(self) -> list[Job]:
        raise NotImplementedError("squeue --json is unavailable and the text fallback is not implemented yet")


class JsonSource(Source):
    """A source backed by pre-captured ``sinfo``/``squeue`` JSON (for tests/replay)."""

    def __init__(self, sinfo: str, squeue: str) -> None:
        self._sinfo = NestedDict.from_jsons(sinfo)
        self._squeue = NestedDict.from_jsons(squeue)

    def nodes(self) -> list[Node]:
        return [Node.from_sinfo(n) for n in self._sinfo.get("nodes") or []]

    def jobs(self) -> list[Job]:
        return [Job.from_squeue(j) for j in self._squeue.get("jobs") or []]
