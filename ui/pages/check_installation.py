from __future__ import annotations

import asyncio
from asyncio import create_task

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Static
from rich.console import RenderableType
from rich.text import Text

from ui.i2p_status import collect_i2p_status, zero_i2p_status


class LargeHello(Widget):
    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def render(self) -> RenderableType:
        return Text(self._text, style="bold", justify="center")


class CheckInstallationPage(Widget):
    DEFAULT_CSS = """
    CheckInstallationPage {
        width: 100%;
        height: 100%;
    }

    #welcome-layout {
        width: 100%;
        height: 100%;
    }

    #welcome-stack {
        width: 100%;
        height: 100%;
    }

    #welcome-index {
        width: auto;
        content-align: left top;
        text-style: bold;
        margin: 1 0 0 1;
    }

    .scroll-container {
        width: 100%;
        height: auto;
        overflow-y: auto;
    }

    .content-container {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1;
    }

    LargeHello {
        width: 100%;
        height: auto;
        color: $text;
        border: none;
        content-align: center middle;
        padding: 1;
    }

    .status-summary {
        width: 100%;
        height: auto;
        padding: 1 2;
        color: $text;
        border: none;
        content-align: center middle;
        margin-top: 1;
        text-style: bold;
    }

    .status-block {
        width: 100%;
        height: auto;
        padding: 1 2;
        color: $text;
        background: $surface;
        border: solid $primary;
        margin-top: 1;
    }

    #top-spacer {
        height: 1fr;
    }

    #bottom-spacer {
        height: 1fr;
    }

    #bottom-margin {
        height: 2vh;
    }

    #welcome-controls {
        width: 100%;
        height: 3;
        align-horizontal: center;
    }

    #startup-next {
        border: none;
        background: transparent;
        text-style: bold;
    }

    #startup-prev {
        border: none;
        background: transparent;
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._status_task: asyncio.Task[None] | None = None
        self.startup_next_disabled = True

    def compose(self) -> ComposeResult:
        with Container(id="welcome-layout"):
            with Vertical(id="welcome-stack"):
                yield Static("проверка подключения к i2p", id="welcome-index")
                yield Static(id="top-spacer")
                with ScrollableContainer(classes="scroll-container"):
                    with Container(classes="content-container"):
                        yield LargeHello("Проверка подключения к сети I2P")
                        yield Static("Состояние: проверяем подключение...", id="status-summary", classes="status-summary")
                        yield Static("Следующее обновление через: 5с", id="status-countdown", classes="status-summary")
                        yield Static(self._format_status_lines(zero_i2p_status()), id="status-details", classes="status-block")
                yield Static(id="bottom-spacer")
                with Horizontal(id="welcome-controls"):
                    yield Button("<< назад", id="startup-prev")
                    yield Button("вперед >>", id="startup-next", disabled=True)
                yield Static(id="bottom-margin")

    def on_mount(self) -> None:
        self._status_task = create_task(self._load_status())

    def on_unmount(self) -> None:
        if self._status_task is not None:
            self._status_task.cancel()

    async def _load_status(self) -> None:
        while True:
            status = await collect_i2p_status()
            self.startup_next_disabled = status["connected"] != "1"
            self.query_one("#status-summary", Static).update(status["summary"])
            self.query_one("#status-details", Static).update(
                self._format_status_lines(status)
            )
            self.query_one("#startup-next", Button).disabled = self.startup_next_disabled
            for remaining in range(5, 0, -1):
                self.query_one("#status-countdown", Static).update(
                    f"Следующее обновление через: {remaining}с"
                )
                await asyncio.sleep(1)

    @staticmethod
    def _format_status_lines(status: dict[str, str]) -> str:
        return "\n".join(
            (
                f"Tunnel creation success rate: {status['tunnel_success_rate']}",
                f"Received: {status['received']}",
                f"Sent: {status['sent']}",
                f"Routers: {status['routers']}",
                f"Floodfills: {status['floodfills']}",
                f"LeaseSets: {status['leasesets']}",
                f"Проверка online чатов: {status['online_check']}",
            )
        )
