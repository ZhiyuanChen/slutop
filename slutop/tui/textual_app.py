# slutop
# Copyright (C) 2026-Present  Zhiyuan Chen <this@zyc.ai>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Textual monitor app for slutop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from textual.app import App, ComposeResult
from textual.timer import Timer
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane
from textual.worker import Worker, WorkerState

from ..api import CachedCollector, Cluster, History, PollStatus, Source
from .render import (
    jobs_panel,
    my_jobs_table,
    nodes_panel,
    pending_reasons_panel,
    soon_free_panel,
    summary_panel,
    users_panel,
)

PANEL_IDS = ("nodes", "users", "pending", "soon-free", "my-jobs", "jobs")


@dataclass
class MonitorFrame:
    """One collected frame for the Textual UI."""

    cluster: Cluster
    status: PollStatus
    timestamp: str
    next_interval: float


class SlutopApp(App[None]):
    """Interactive Slurm monitor."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #panels {
        height: 1fr;
        padding: 0 1;
    }

    #panels ContentSwitcher {
        height: 1fr;
    }

    #panels TabPane {
        height: 1fr;
    }

    #summary {
        margin: 0 1 1 1;
    }

    Static.panel {
        width: 100%;
        height: 100%;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("1", "show_panel('nodes')", "Nodes"),
        ("2", "show_panel('users')", "Users"),
        ("3", "show_panel('pending')", "Pending"),
        ("4", "show_panel('soon-free')", "Soon Free"),
        ("5", "show_panel('my-jobs')", "My Jobs"),
        ("6", "show_panel('jobs')", "Jobs"),
    ]

    def __init__(
        self,
        source: Source,
        *,
        active_interval: float,
        idle_interval: float,
        node_interval: float,
        me: str | None = None,
        user: str | None = None,
        partition: str | None = None,
    ) -> None:
        super().__init__()
        self.source = source
        self.active_interval = active_interval
        self.idle_interval = idle_interval
        self.node_interval = node_interval
        self.me = me
        self.user = user
        self.partition = partition
        self.collector = CachedCollector(source, node_interval)
        self.history = History()
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="summary")
        with TabbedContent(id="panels", initial="nodes"):
            with TabPane("Nodes", id="nodes"):
                yield Static(id="nodes-panel", classes="panel")
            with TabPane("Users", id="users"):
                yield Static(id="users-panel", classes="panel")
            with TabPane("Pending", id="pending"):
                yield Static(id="pending-panel", classes="panel")
            with TabPane("Soon Free", id="soon-free"):
                yield Static(id="soon-free-panel", classes="panel")
            with TabPane("My Jobs", id="my-jobs"):
                yield Static(id="my-jobs-panel", classes="panel")
            with TabPane("Jobs", id="jobs"):
                yield Static(id="jobs-panel", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "slutop"
        self._request_refresh()

    def action_refresh(self) -> None:
        self._request_refresh()

    def action_show_panel(self, panel_id: str) -> None:
        if panel_id in PANEL_IDS:
            self.query_one("#panels", TabbedContent).active = panel_id

    def _request_refresh(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.run_worker(self._collect_frame, name="collect", group="slutop", thread=True, exclusive=True)

    def _collect_frame(self) -> MonitorFrame:
        cluster = self.collector.collect(self.user, self.partition)
        self.history.update(cluster)
        return MonitorFrame(
            cluster=cluster,
            status=self.collector.status,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            next_interval=self.collector.next_interval(self.active_interval, self.idle_interval, cluster),
        )

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name != "collect":
            return
        if event.state == WorkerState.SUCCESS:
            frame = event.worker.result
            assert isinstance(frame, MonitorFrame)
            self._render_frame(frame)
            self._timer = self.set_timer(frame.next_interval, self._request_refresh)
        elif event.state == WorkerState.ERROR:
            self.query_one("#summary", Static).update(f"collection failed: {event.worker.error}")
            self._timer = self.set_timer(self.active_interval, self._request_refresh)

    def _render_frame(self, frame: MonitorFrame) -> None:
        cluster = frame.cluster
        self.query_one("#summary", Static).update(
            summary_panel(cluster, timestamp=frame.timestamp, history=self.history, status=frame.status)
        )
        self.query_one("#nodes-panel", Static).update(nodes_panel(cluster, partition=self.partition))
        self.query_one("#users-panel", Static).update(users_panel(cluster))
        self.query_one("#pending-panel", Static).update(pending_reasons_panel(cluster))
        self.query_one("#soon-free-panel", Static).update(soon_free_panel(cluster))
        self.query_one("#my-jobs-panel", Static).update(my_jobs_table(cluster, me=self.me))
        self.query_one("#jobs-panel", Static).update(jobs_panel(cluster, me=self.me))


def run_textual_monitor(
    source: Source,
    *,
    active_interval: float,
    idle_interval: float,
    node_interval: float,
    me: str | None = None,
    user: str | None = None,
    partition: str | None = None,
) -> None:
    """Run the Textual monitor."""
    SlutopApp(
        source,
        active_interval=active_interval,
        idle_interval=idle_interval,
        node_interval=node_interval,
        me=me,
        user=user,
        partition=partition,
    ).run()
