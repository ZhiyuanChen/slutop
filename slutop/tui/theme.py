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

"""Color palette and semantic roles for slutop's terminal UI.

A calm, technical palette: teal/green as the primary interaction color with
restrained neutrals. Red is reserved for genuine danger (errors, down nodes),
never for routine interaction.
"""

from __future__ import annotations

# -- Palette --------------------------------------------------------------
CARDINAL = "#8C1515"
CARDINAL_DARK = "#820000"
PALO_ALTO = "#175E54"
PALO_ALTO_LIGHT = "#2D716F"
PALO_ALTO_DARK = "#014240"
PALO_VERDE = "#279989"
OLIVE = "#8F993E"
BAY = "#6FA287"
SKY = "#4298B5"
LAGUNITA = "#007C92"
POPPY = "#E98300"
ILLUMINATING = "#FEDD5C"
SPIRITED = "#E04F39"
PLUM = "#620059"
STONE = "#7F7776"
FOG = "#DAD7CB"
FOG_DARK = "#B6B1A9"
ARCHWAY_DARK = "#2F2424"

# -- Semantic roles -------------------------------------------------------
PRIMARY = PALO_ALTO  # primary chrome: titles, headers, active states
PRIMARY_HOVER = PALO_ALTO_LIGHT
PRIMARY_ACTIVE = PALO_ALTO_DARK
ACCENT = CARDINAL  # brand accent, limited emphasis only
SUCCESS = PALO_VERDE  # free / healthy / available
INFO = LAGUNITA  # informational
INFO_ALT = SKY  # secondary informational, data figures, charts
WARNING = POPPY  # warnings, pending, at-capacity
WARNING_SOFT = ILLUMINATING
DANGER = SPIRITED  # errors, down/drained, destructive
CRITICAL = CARDINAL_DARK  # critical states only
MUTED = STONE  # secondary text
BORDER = FOG_DARK  # borders and dividers

# Utilization-gauge fills: a calm sage-on-grey gauge that holds up on both
# dark and light terminals (Bay and Stone are both mid-tones).
GAUGE_USED = STONE  # used portion of a utilization gauge (recessive neutral)
GAUGE_FREE = BAY  # free / unused portion (calm "available" green)

# Ordered hues for charts / grouped statuses (per product guidance).
CHART_SEQUENCE = (PALO_VERDE, LAGUNITA, SKY, OLIVE, POPPY, PLUM)
