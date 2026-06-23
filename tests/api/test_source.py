import subprocess

import pytest

from slutop.api import CliSource


def test_clisource_json_path_and_username_backfill(monkeypatch, sinfo_text, squeue_text):
    calls = []

    def fake_run(self, *cmd):
        calls.append(cmd)
        if cmd[0] == "sinfo":
            return sinfo_text
        if cmd[0] == "squeue" and "--json" in cmd:
            return squeue_text
        if cmd[0] == "squeue":  # the username-backfill format query
            return "1001|alice\n1002|bob\n"
        raise AssertionError(cmd)

    monkeypatch.setattr(CliSource, "_run", fake_run)
    src = CliSource()

    nodes = src.nodes()
    assert [n.name for n in nodes] == ["node1", "node2", "node3", "node4"]

    jobs = src.jobs()
    # squeue --json leaves user_name empty; the backfill query fills it in.
    assert {j.user for j in jobs} == {"alice", "bob"}


def test_clisource_falls_back_when_json_unsupported(monkeypatch):
    def fake_run(self, *cmd):
        if "--json" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="unrecognized option '--json'")
        raise AssertionError(cmd)

    monkeypatch.setattr(CliSource, "_run", fake_run)
    src = CliSource()
    # Text fallback is not implemented yet, but the JSON failure must be detected
    # and routed to it (rather than crashing on the JSON parse).
    with pytest.raises(NotImplementedError):
        src.nodes()
