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

"""Parsers for Slurm TRES and GRES strings.

Slurm reports resources as TRES (Trackable RESources) strings such as
``cpu=128,mem=1031898M,billing=128,gres/gpu=8`` and GRES strings such as
``gpu:a100:8(IDX:0-7)``. These helpers turn them into plain mappings.
"""

from __future__ import annotations

from chanfig import FlatDict

# Slurm memory suffixes, normalised to mebibytes (MiB).
_MEM_UNITS = {"K": 1 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0**2, "P": 1024.0**3}


def parse_mem(value: str | int | float | None) -> float:
    """Return memory in MiB from a Slurm memory token (e.g. ``516G``, ``1031898M``)."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip()
    unit = value[-1].upper()
    if unit in _MEM_UNITS:
        try:
            return float(value[:-1]) * _MEM_UNITS[unit]
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def parse_tres(spec: str | None) -> FlatDict:
    """Parse a TRES string into a :class:`~chanfig.FlatDict`.

    ``gres/<name>`` keys are flattened to ``<name>`` (so ``gres/gpu`` becomes ``gpu``),
    memory is normalised to MiB, and counts are coerced to ``int`` where possible.
    """
    tres: FlatDict = FlatDict()
    if not spec:
        return tres
    for item in spec.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, _, raw = item.partition("=")
        key = key.strip()
        if key.startswith("gres/"):
            key = key[len("gres/") :]
        if key == "mem":
            tres[key] = parse_mem(raw)
            continue
        try:
            tres[key] = int(raw)
        except ValueError:
            try:
                tres[key] = float(raw)
            except ValueError:
                tres[key] = raw
    return tres


def parse_gres(spec: str | None) -> FlatDict:
    """Parse a GRES string (``gpu:8``, ``gpu:a100:8``, ``gpu:8(IDX:0-7)``) into name -> count."""
    gres: FlatDict = FlatDict()
    if not spec or spec in ("(null)", "N/A"):
        return gres
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        # Drop the ``(IDX:...)`` allocation annotation if present.
        paren = item.find("(")
        if paren != -1:
            item = item[:paren]
        parts = item.split(":")
        name = parts[0]
        try:
            count = int(parts[-1])
        except ValueError:
            count = 0
        gres[name] = gres.get(name, 0) + count
    return gres
