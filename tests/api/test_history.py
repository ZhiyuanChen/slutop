from slutop.api import Cluster, History


def test_history_accumulates(json_source):
    h = History()
    c = Cluster(nodes=json_source.nodes(), jobs=json_source.jobs())
    h.update(c)
    h.update(c)
    assert len(h) == 2
    assert round(h.gpu[-1], 2) == round(13 / 32 * 100, 2)  # 13 GPUs used of 32


def test_history_respects_maxlen(json_source):
    h = History(maxlen=3)
    c = Cluster(nodes=json_source.nodes(), jobs=json_source.jobs())
    for _ in range(5):
        h.update(c)
    assert len(h) == 3
