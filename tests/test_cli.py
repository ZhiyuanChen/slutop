import io

from slutop.api import Cluster
from slutop.cli import _key_reader, _payload, build_config


def test_build_config_parses_flags():
    config = build_config(["-1", "-p", "gpu", "--me", "-i", "3", "--idle-interval", "8", "--node-interval", "21"])
    assert config.once is True
    assert config.partition == "gpu"
    assert config.me is True
    assert config.interval == 3.0
    assert config.idle_interval == 8.0
    assert config.node_interval == 21.0
    assert config.output == "table"


def test_build_config_defaults():
    config = build_config([])
    assert config.once is False
    assert config.interval == 2.0
    assert config.idle_interval == 5.0
    assert config.node_interval == 30.0
    assert config.user is None


def test_payload_summary_and_serialisation(cluster: Cluster):
    payload = _payload(cluster)
    assert payload["summary"]["gpus_total"] == 32
    assert payload["summary"]["gpus_free"] == 11
    assert len(payload["nodes"]) == 4
    assert "summary" in payload.jsons()  # chanfig JSON serialisation


def test_key_reader_non_tty_waits_and_returns_empty():
    # A non-tty stream (piped output) must not touch termios; it just paces.
    with _key_reader(io.StringIO()) as read_key:
        assert read_key(0) == ""
