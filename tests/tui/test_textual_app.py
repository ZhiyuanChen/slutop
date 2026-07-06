import pytest
from textual.widgets import Static, TabbedContent

from slutop.tui.textual_app import SlutopApp


@pytest.mark.asyncio
async def test_textual_app_renders_switchable_panels(json_source):
    app = SlutopApp(
        json_source,
        active_interval=2,
        idle_interval=5,
        node_interval=30,
        me="yuanle",
        user=None,
        partition="gpu",
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        assert app.query_one("#panels", TabbedContent).active == "nodes"
        for selector in (
            "#summary",
            "#nodes-panel",
            "#users-panel",
            "#pending-panel",
            "#soon-free-panel",
            "#my-jobs-panel",
            "#jobs-panel",
        ):
            widget = app.query_one(selector, Static)
            assert widget.content
        assert app.query_one("#nodes").region.height > 0
        assert app.query_one("#nodes-panel").region.height > 0
        assert "node1" in app.export_screenshot()
        await pilot.press("2")
        await pilot.pause()
        assert app.query_one("#panels", TabbedContent).active == "users"
        assert app.query_one("#users").region.height > 0
        assert app.query_one("#users-panel").region.height > 0
        assert "dugang" in app.export_screenshot()
        await pilot.press("3")
        await pilot.pause()
        assert app.query_one("#panels", TabbedContent).active == "pending"
        assert app.query_one("#pending").region.height > 0
        assert app.query_one("#pending-panel").region.height > 0
        assert "Resources" in app.export_screenshot()
        await pilot.press("5")
        await pilot.pause()
        assert app.query_one("#panels", TabbedContent).active == "my-jobs"
        assert app.query_one("#my-jobs").region.height > 0
        assert app.query_one("#my-jobs-panel").region.height > 0
        assert "yuanle" in app.export_screenshot()
