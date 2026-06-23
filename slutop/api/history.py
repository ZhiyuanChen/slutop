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

"""Rolling history of cluster utilization, for the monitor-mode trend sparklines."""

from __future__ import annotations

from collections import deque

from .models import Cluster


def _pct(used: float, total: float) -> float:
    return 100.0 * used / total if total else 0.0


class History:
    """Fixed-length rolling history of cluster GPU/CPU/MEM utilization percentages."""

    def __init__(self, maxlen: int = 240) -> None:
        self.maxlen = maxlen
        self.gpu: deque[float] = deque(maxlen=maxlen)
        self.cpu: deque[float] = deque(maxlen=maxlen)
        self.mem: deque[float] = deque(maxlen=maxlen)

    def update(self, cluster: Cluster) -> None:
        """Append the current utilization sample for each resource."""
        self.gpu.append(_pct(cluster.gpus_used, cluster.gpus_total))
        self.cpu.append(_pct(cluster.cpus_used, cluster.cpus_total))
        self.mem.append(_pct(cluster.mem_used, cluster.mem_total))

    def __len__(self) -> int:
        return len(self.gpu)
