import subprocess

import pytest

from slutop.api import CliSource


def test_clisource_21_08_path(monkeypatch, sinfo_text, squeue_text):
    """Slurm 21.08: scontrol --json is unsupported, so fall back to sinfo --json
    and backfill the empty usernames from a format query."""

    def fake_run(self, *cmd):
        if cmd[:2] == ("scontrol", "show"):
            raise subprocess.CalledProcessError(1, cmd, stderr="unrecognized option '--json'")
        if cmd == ("sinfo", "--json"):
            return sinfo_text
        if cmd == ("squeue", "--json"):
            return squeue_text
        if cmd[0] == "squeue":  # username backfill (%i|%u)
            return "1001|alice\n1002|bob\n"
        raise AssertionError(cmd)

    monkeypatch.setattr(CliSource, "_run", fake_run)
    src = CliSource()
    assert [n.name for n in src.nodes()] == ["node1", "node2", "node3", "node4"]
    assert {j.user for j in src.jobs()} == {"alice", "bob"}


def test_clisource_25_11_path(monkeypatch, nodes_v44_text, squeue_v44_text):
    """Slurm 25.11: scontrol show node --json is preferred; usernames already present
    (no backfill query needed)."""
    calls = []

    def fake_run(self, *cmd):
        calls.append(cmd)
        if cmd == ("scontrol", "show", "node", "--json"):
            return nodes_v44_text
        if cmd == ("squeue", "--json"):
            return squeue_v44_text
        raise AssertionError(cmd)

    monkeypatch.setattr(CliSource, "_run", fake_run)
    src = CliSource()
    nodes = src.nodes()
    assert nodes[0].name == "compute-0001"
    assert nodes[0].cpus_total == 128
    assert {j.user for j in src.jobs()} == {"alice", "bob"}
    assert ("squeue", "-h", "-a", "-o", "%i|%u") not in calls  # no backfill needed


def test_clisource_no_json_source_raises(monkeypatch):
    def fake_run(self, *cmd):
        if "--json" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="unrecognized option '--json'")
        raise AssertionError(cmd)

    monkeypatch.setattr(CliSource, "_run", fake_run)
    with pytest.raises(NotImplementedError):
        CliSource().nodes()
