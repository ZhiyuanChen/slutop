from slutop.api import Cluster, snapshot


def test_snapshot_builds_cluster_from_source(json_source):
    cluster = snapshot(json_source)
    assert isinstance(cluster, Cluster)
    assert [n.name for n in cluster.nodes] == ["node1", "node2", "node3", "node4"]
    assert len(cluster.jobs) == 2
