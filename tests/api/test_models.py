from slutop.api import Cluster


def _node(cluster: Cluster, name: str):
    return next(n for n in cluster.nodes if n.name == name)


def test_node_gpu_accounting(cluster: Cluster):
    full = _node(cluster, "node1")
    assert (full.gpus_total, full.gpus_used, full.gpus_free) == (8, 8, 0)
    assert full.usable is True
    assert full.available is False  # usable but no free GPUs

    partial = _node(cluster, "node2")
    assert (partial.gpus_total, partial.gpus_used, partial.gpus_free) == (8, 5, 3)
    assert partial.available is True


def test_typed_gres_total_from_tres(cluster: Cluster):
    idle = _node(cluster, "node3")
    # gres is "gpu:a100:8" with empty tres_used; total still 8, used 0.
    assert idle.gpus_total == 8
    assert idle.gpus_used == 0
    assert idle.available is True


def test_down_node_not_available_despite_free_gpus(cluster: Cluster):
    down = _node(cluster, "node4")
    assert down.gpus_free == 8
    assert down.usable is False
    assert down.available is False


def test_cluster_free_excludes_unusable_nodes(cluster: Cluster):
    assert cluster.gpus_total == 32
    assert cluster.gpus_used == 13  # 8 + 5 + 0 + 0
    # free counts only usable nodes: node1(0) + node2(3) + node3(8); node4 is down.
    assert cluster.gpus_free == 11


def test_cluster_cpu_mem_aggregates(cluster: Cluster):
    # CPU: node4 is down, so its 128 cores are "unavailable", not "free".
    assert cluster.cpus_total == 512
    assert cluster.cpus_used == 176  # 128 + 48 + 0 + 0
    assert cluster.cpus_free == 208  # node1(0) + node2(80) + node3(128)
    assert cluster.cpus_unavailable == 128  # node4

    # The three GPU segments partition the total exactly.
    assert cluster.gpus_used + cluster.gpus_free + cluster.gpus_unavailable == cluster.gpus_total
    assert cluster.gpus_unavailable == 8  # node4

    # MEM segments also partition the total.
    assert cluster.mem_used + cluster.mem_free + cluster.mem_unavailable == cluster.mem_total


def test_job_parsing(cluster: Cluster):
    running = next(j for j in cluster.jobs if j.job_id == 1001)
    assert running.running is True
    assert running.gpus == 11  # from gres/gpu in tres_alloc_str
    assert running.nodes == "node[1-2]"

    pending = next(j for j in cluster.jobs if j.job_id == 1002)
    assert pending.pending is True
    assert pending.gpus == 32  # falls back to tres_req_str when alloc is empty
    assert pending.reason == "Resources"


def test_running_pending_partitions(cluster: Cluster):
    assert len(cluster.running_jobs) == 1
    assert len(cluster.pending_jobs) == 1
