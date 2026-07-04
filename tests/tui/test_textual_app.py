import pytest
from textual.widgets import Static

from slutop.tui.textual_app import SlutopApp


@pytest.mark.asyncio
async def test_textual_app_renders_all_panels(json_source):
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
        for selector in ("#summary", "#nodes", "#pending", "#soon-free", "#my-jobs", "#jobs"):
            widget = app.query_one(selector, Static)
            assert widget.content
