from slutop.api import CachedCollector, Cluster, Job, Node, filter_cluster


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


def test_filter_cluster_restricts_nodes_jobs_and_summary(cluster: Cluster):
    filtered = filter_cluster(cluster, user=None, partition="debug")
    assert [n.name for n in filtered.nodes] == ["node3"]
    assert filtered.jobs == []
    assert filtered.gpus_total == 8
    assert filtered.gpus_free == 8


def test_cached_collector_reuses_nodes_until_ttl_or_job_change():
    source = FakeSource()
    clock = Clock()
    collector = CachedCollector(source, node_interval=30, clock=clock)

    first = collector.collect()
    assert [n.name for n in first.nodes] == ["node1"]
    assert (source.jobs_calls, source.nodes_calls) == (1, 1)

    clock.now = 10.0
    second = collector.collect()
    assert [n.name for n in second.nodes] == ["node1"]
    assert (source.jobs_calls, source.nodes_calls) == (2, 1)

    source.job_state = "PENDING"
    third = collector.collect()
    assert [n.name for n in third.nodes] == ["node2"]
    assert (source.jobs_calls, source.nodes_calls) == (3, 2)

    clock.now = 41.0
    fourth = collector.collect()
    assert [n.name for n in fourth.nodes] == ["node3"]
    assert (source.jobs_calls, source.nodes_calls) == (4, 3)


def test_cached_collector_adapts_refresh_interval():
    source = FakeSource()
    clock = Clock()
    collector = CachedCollector(source, node_interval=30, clock=clock)

    cluster = collector.collect()
    assert collector.next_interval(2, 5, cluster) == 2.0

    cluster = collector.collect()
    assert collector.next_interval(2, 5, cluster) == 2.0

    cluster = collector.collect()
    assert collector.next_interval(2, 5, cluster) == 5.0

    source.job_state = "PENDING"
    cluster = collector.collect()
    assert collector.next_interval(2, 5, cluster) == 2.0
