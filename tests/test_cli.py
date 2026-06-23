from slutop.api import Cluster
from slutop.cli import _payload, build_config


def test_build_config_parses_flags():
    config = build_config(["-1", "-p", "gpu", "--me", "-i", "3"])
    assert config.once is True
    assert config.partition == "gpu"
    assert config.me is True
    assert config.interval == 3.0
    assert config.output == "table"


def test_build_config_defaults():
    config = build_config([])
    assert config.once is False
    assert config.interval == 5.0  # gentle on slurmctld
    assert config.user is None


def test_payload_summary_and_serialisation(cluster: Cluster):
    payload = _payload(cluster)
    assert payload["summary"]["gpus_total"] == 32
    assert payload["summary"]["gpus_free"] == 11
    assert len(payload["nodes"]) == 4
    assert "summary" in payload.jsons()  # chanfig JSON serialisation
