from slutop.api import CachedCollector, Cluster, Job, Node, filter_cluster


class FakeSource:
    def __init__(self) -> None:
        self.nodes_calls = 0
        self.jobs_calls = 0
        self.job_state = "RUNNING"
        self.fail_jobs = False
        self.fail_nodes = False

    def nodes(self) -> list[Node]:
        self.nodes_calls += 1
        if self.fail_nodes:
            raise RuntimeError("scontrol timeout")
        return [Node(name=f"node{self.nodes_calls}", partitions=["gpu"], gpus_total=8)]

    def jobs(self) -> list[Job]:
        self.jobs_calls += 1
        if self.fail_jobs:
            raise RuntimeError("squeue timeout")
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


def test_cached_collector_limits_node_refresh_during_job_churn():
    source = FakeSource()
    clock = Clock()
    collector = CachedCollector(source, node_interval=30, clock=clock, change_node_interval=5)

    collector.collect()
    source.job_state = "PENDING"
    clock.now = 2.0
    cluster = collector.collect()
    assert [n.name for n in cluster.nodes] == ["node1"]
    assert (source.jobs_calls, source.nodes_calls) == (2, 1)

    source.job_state = "RUNNING"
    clock.now = 5.0
    cluster = collector.collect()
    assert [n.name for n in cluster.nodes] == ["node2"]
    assert (source.jobs_calls, source.nodes_calls) == (3, 2)


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


def test_cached_collector_keeps_cached_jobs_after_transient_job_failure():
    source = FakeSource()
    collector = CachedCollector(source, node_interval=30)

    first = collector.collect()
    assert [j.state for j in first.jobs] == ["RUNNING"]

    source.fail_jobs = True
    second = collector.collect()
    assert [j.state for j in second.jobs] == ["RUNNING"]
    assert collector.status.jobs_stale is True
    assert collector.status.error == "jobs: squeue timeout"
    assert collector.next_interval(2, 5, second) == 2.0


def test_cached_collector_keeps_cached_nodes_after_transient_node_failure():
    source = FakeSource()
    clock = Clock()
    collector = CachedCollector(source, node_interval=30, clock=clock)

    collector.collect()
    source.fail_nodes = True
    clock.now = 31.0
    second = collector.collect()
    assert [n.name for n in second.nodes] == ["node1"]
    assert collector.status.nodes_stale is True
    assert collector.status.error == "nodes: scontrol timeout"
