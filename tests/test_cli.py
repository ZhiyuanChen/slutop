from slutop.api import Cluster
from slutop.cli import _monitor, _payload, build_config


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


def test_monitor_runs_textual(monkeypatch):
    calls = []

    def fake_run_textual_monitor(source, **kwargs):
        calls.append((source, kwargs))

    monkeypatch.setattr("slutop.cli.run_textual_monitor", fake_run_textual_monitor)
    source = object()
    config = build_config(["-i", "3", "--idle-interval", "8", "--node-interval", "21", "-p", "gpu"])
    _monitor(source, config, me="alice", user="alice")
    assert calls == [
        (
            source,
            {
                "active_interval": 3.0,
                "idle_interval": 8.0,
                "node_interval": 21.0,
                "me": "alice",
                "user": "alice",
                "partition": "gpu",
            },
        )
    ]
