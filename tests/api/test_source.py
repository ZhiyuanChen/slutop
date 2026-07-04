import subprocess

import pytest

from slutop.api import CliSource


def test_clisource_21_08_path(monkeypatch, sinfo_text, squeue_text, fake_pwd):
    """Slurm 21.08: scontrol --json is unsupported, so fall back to sinfo --json.
    squeue --json leaves user_name empty, so the owner is resolved from user_id --
    with no second squeue call (any extra command is an error here)."""
    from slutop.api import models

    monkeypatch.setattr(models, "_UID_NAMES", {})
    monkeypatch.setattr(models, "pwd", fake_pwd({2099: "yuanle", 2001: "dugang"}))

    def fake_run(self, *cmd):
        if cmd[:2] == ("scontrol", "show"):
            raise subprocess.CalledProcessError(1, cmd, stderr="unrecognized option '--json'")
        if cmd == ("sinfo", "--json"):
            return sinfo_text
        if cmd == ("squeue", "--json"):
            return squeue_text
        raise AssertionError(cmd)  # no backfill / no extra subprocess

    monkeypatch.setattr(CliSource, "_run", fake_run)
    src = CliSource()
    assert [n.name for n in src.nodes()] == ["node1", "node2", "node3", "node4"]
    assert {j.user for j in src.jobs()} == {"yuanle", "dugang"}  # resolved via user_id


def test_clisource_25_11_path(monkeypatch, nodes_v44_text, squeue_v44_text):
    """Slurm 25.11: scontrol show node --json is preferred; user_name is populated."""

    def fake_run(self, *cmd):
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


def test_clisource_no_json_source_raises(monkeypatch):
    def fake_run(self, *cmd):
        if "--json" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="unrecognized option '--json'")
        raise AssertionError(cmd)

    monkeypatch.setattr(CliSource, "_run", fake_run)
    with pytest.raises(NotImplementedError):
        CliSource().nodes()
