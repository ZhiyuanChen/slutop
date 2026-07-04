import io

from slutop.api import Cluster, Job, Node
from slutop.cli import CachedCollector, _filter_cluster, _key_reader, _payload, build_config


class FakeSource:
    def __init__(self) -> None:
        self.nodes_calls = 0
        self.jobs_calls = 0
        self.job_state = "RUNNING"

    def nodes(self) -> list[Node]:
        self.nodes_calls += 1
        return [Node(name=f"node{self.nodes_calls}", partitions=["gpu"], gpus_total=8)]

    def jobs(self) -> list[Job]:
        self.jobs_calls += 1
        return [Job(job_id=1001, partition="gpu", state=self.job_state, gpus=1)]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


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


def test_filter_cluster_restricts_nodes_jobs_and_summary(cluster: Cluster):
    filtered = _filter_cluster(cluster, user=None, partition="debug")
    payload = _payload(filtered)
    assert [n.name for n in filtered.nodes] == ["node3"]
    assert filtered.jobs == []
    assert payload["summary"]["gpus_total"] == 8
    assert payload["summary"]["gpus_free"] == 8


def test_cached_collector_reuses_nodes_until_ttl_or_job_change():
    source = FakeSource()
    clock = Clock()
    config = build_config(["--node-interval", "30"])
    collector = CachedCollector(source, node_interval=config.node_interval, clock=clock)

    first = collector.collect(config, user=None)
    assert [n.name for n in first.nodes] == ["node1"]
    assert (source.jobs_calls, source.nodes_calls) == (1, 1)

    clock.now = 10.0
    second = collector.collect(config, user=None)
    assert [n.name for n in second.nodes] == ["node1"]
    assert (source.jobs_calls, source.nodes_calls) == (2, 1)

    source.job_state = "PENDING"
    third = collector.collect(config, user=None)
    assert [n.name for n in third.nodes] == ["node2"]
    assert (source.jobs_calls, source.nodes_calls) == (3, 2)

    clock.now = 41.0
    fourth = collector.collect(config, user=None)
    assert [n.name for n in fourth.nodes] == ["node3"]
    assert (source.jobs_calls, source.nodes_calls) == (4, 3)


def test_cached_collector_adapts_refresh_interval():
    source = FakeSource()
    clock = Clock()
    config = build_config(["-i", "2", "--idle-interval", "5"])
    collector = CachedCollector(source, node_interval=30, clock=clock)

    cluster = collector.collect(config, user=None)
    assert collector.next_interval(config, cluster) == 2.0

    cluster = collector.collect(config, user=None)
    assert collector.next_interval(config, cluster) == 2.0

    cluster = collector.collect(config, user=None)
    assert collector.next_interval(config, cluster) == 5.0

    source.job_state = "PENDING"
    cluster = collector.collect(config, user=None)
    assert collector.next_interval(config, cluster) == 2.0


def test_key_reader_non_tty_waits_and_returns_empty():
    # A non-tty stream (piped output) must not touch termios; it just paces.
    with _key_reader(io.StringIO()) as read_key:
        assert read_key(0) == ""
