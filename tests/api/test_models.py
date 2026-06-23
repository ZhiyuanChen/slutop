from slutop.api import Cluster
from slutop.api.models import _state_str, _unwrap


def _node(cluster: Cluster, name: str):
    return next(n for n in cluster.nodes if n.name == name)


# -- Slurm 25.11 (data_parser/v0.0.44) schema handling ------------------------


def test_unwrap_number_form():
    assert _unwrap({"set": True, "infinite": False, "number": 48}) == 48
    assert _unwrap({"set": False, "infinite": False, "number": 0}) is None  # unset
    assert _unwrap({"set": True, "infinite": True, "number": 0}) is None  # infinite
    assert _unwrap(7) == 7  # flat v0.0.37 passes through
    assert _unwrap("gpu:8") == "gpu:8"


def test_state_str_handles_list_and_string():
    assert _state_str(["MIXED"]) == "MIXED"
    assert _state_str(["DOWN", "DRAIN"]) == "DOWN DRAIN"
    assert _state_str("mixed") == "mixed"  # v0.0.37 single string
    assert _state_str(None) == ""


def test_v44_node_parsing(cluster_v44: Cluster):
    busy = _node(cluster_v44, "compute-0001")
    assert (busy.cpus_total, busy.cpus_alloc) == (128, 64)  # plain ints
    assert (busy.gpus_total, busy.gpus_used, busy.gpus_free) == (8, 8, 0)
    assert busy.state == "MIXED"  # list -> string
    assert busy.usable and not busy.available

    idle = _node(cluster_v44, "compute-0002")
    assert idle.gpus_free == 8 and idle.available

    down = _node(cluster_v44, "compute-0003")  # state ["DOWN", "DRAIN"]
    assert down.usable is False and down.available is False


def test_v44_job_parsing(cluster_v44: Cluster):
    jobs = {j.job_id: j for j in cluster_v44.jobs}
    run = jobs[109]
    assert run.running is True
    assert run.cpus == 48 and run.node_count == 2  # {set,infinite,number} unwrapped
    assert run.gpus == 16  # from tres_alloc_str
    assert run.start_time == 1782239747

    pend = jobs[110]
    assert pend.pending is True  # job_state ["PENDING"]
    assert pend.gpus == 24  # falls back to tres_req_str when alloc is empty
    assert pend.cpus == 24
    assert pend.time_limit is None  # infinite -> None
    assert pend.reason == "Resources"


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
