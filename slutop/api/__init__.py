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

"""slutop's data layer: cluster models, sources, and snapshotting.

This subpackage is UI-free and importable on its own, so it can be reused in
scripts and dashboards independently of the terminal monitor.
"""

from .history import History
from .models import Cluster, Job, Node
from .snapshot import snapshot
from .source import CliSource, JsonSource, Source
from .tres import parse_gres, parse_mem, parse_tres

__all__ = [
    "CliSource",
    "Cluster",
    "History",
    "Job",
    "JsonSource",
    "Node",
    "Source",
    "parse_gres",
    "parse_mem",
    "parse_tres",
    "snapshot",
]
