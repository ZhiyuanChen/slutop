from pathlib import Path

import pytest

from slutop.api import Cluster, JsonSource

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sinfo_text() -> str:
    return (FIXTURES / "sinfo_v0.0.37.json").read_text()


@pytest.fixture
def squeue_text() -> str:
    return (FIXTURES / "squeue_v0.0.37.json").read_text()


@pytest.fixture
def json_source() -> JsonSource:
    return JsonSource(
        (FIXTURES / "sinfo_v0.0.37.json").read_text(),
        (FIXTURES / "squeue_v0.0.37.json").read_text(),
    )


@pytest.fixture
def cluster(json_source: JsonSource) -> Cluster:
    return Cluster(nodes=json_source.nodes(), jobs=json_source.jobs())


# -- Slurm 25.11 (data_parser/v0.0.44): structured numbers + list states ------


@pytest.fixture
def nodes_v44_text() -> str:
    return (FIXTURES / "nodes_v0.0.44.json").read_text()


@pytest.fixture
def squeue_v44_text() -> str:
    return (FIXTURES / "squeue_v0.0.44.json").read_text()


@pytest.fixture
def cluster_v44(nodes_v44_text: str, squeue_v44_text: str) -> Cluster:
    source = JsonSource(nodes_v44_text, squeue_v44_text)
    return Cluster(nodes=source.nodes(), jobs=source.jobs())
