import re

from slutop.tui import theme

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

_ROLES = [
    "PRIMARY",
    "PRIMARY_HOVER",
    "PRIMARY_ACTIVE",
    "ACCENT",
    "SUCCESS",
    "INFO",
    "INFO_ALT",
    "WARNING",
    "WARNING_SOFT",
    "DANGER",
    "CRITICAL",
    "MUTED",
    "BORDER",
    "GAUGE_USED",
    "GAUGE_FREE",
]


def test_semantic_roles_are_valid_hex():
    for role in _ROLES:
        assert _HEX.match(getattr(theme, role)), role


def test_chart_sequence_is_hex():
    assert theme.CHART_SEQUENCE
    assert all(_HEX.match(color) for color in theme.CHART_SEQUENCE)
