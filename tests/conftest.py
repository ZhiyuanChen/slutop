from pathlib import Path

import pytest

from slutop.api import Cluster, JsonSource

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sinfo_text() -> str:
    return (FIXTURES / "sinfo.json").read_text()


@pytest.fixture
def squeue_text() -> str:
    return (FIXTURES / "squeue.json").read_text()


@pytest.fixture
def json_source() -> JsonSource:
    return JsonSource(
        (FIXTURES / "sinfo.json").read_text(),
        (FIXTURES / "squeue.json").read_text(),
    )


@pytest.fixture
def cluster(json_source: JsonSource) -> Cluster:
    return Cluster(nodes=json_source.nodes(), jobs=json_source.jobs())
