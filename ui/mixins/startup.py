from __future__ import annotations

from textual import events
from textual.containers import Container, Vertical
from textual.widget import Widget
from textual.widgets import Button, Static


class StartupMixin:
    startup_page_classes: list[type[Widget]]
    startup_index: int
    startup_active: bool

    def _current_startup_page(self) -> Widget | None:
        host = self.query_one("#startup-pages", Container)
        children = list(host.children)
        if not children:
            return None
        child = children[0]
        return child if isinstance(child, Widget) else None

    def _startup_next_is_blocked(self) -> bool:
        page = self._current_startup_page()
        if page is None:
            return False
        return bool(getattr(page, "startup_next_disabled", False))

    async def _show_startup(self) -> None:
        self.query_one("#startup-shell", Container).display = True
        self.query_one("#app-shell", Vertical).display = False
        await self._render_startup_page()
        self._refresh_startup_controls()

    async def _startup_prev(self) -> None:
        if not self.startup_active:
            return
        if self.startup_index > 0:
            self.startup_index -= 1
            await self._render_startup_page()
        self._refresh_startup_controls()

    async def _startup_next(self) -> None:
        if not self.startup_active:
            return
        if self._startup_next_is_blocked():
            self._refresh_startup_controls()
            return
        if self.startup_index >= len(self.startup_page_classes) - 1:
            await self._finish_startup()
            return
        self.startup_index += 1
        await self._render_startup_page()
        self._refresh_startup_controls()

    async def _render_startup_page(self) -> None:
        host = self.query_one("#startup-pages", Container)
        await host.remove_children()

        if not self.startup_page_classes:
            return

        page_cls = self.startup_page_classes[self.startup_index]
        page_widget: Widget
        try:
            page_widget = page_cls()
        except Exception as exc:
            page_widget = Static(
                f"Не удалось загрузить страницу {getattr(page_cls, '__name__', page_cls)}: {exc}"
            )
        await host.mount(page_widget)

    def _refresh_startup_controls(self) -> None:
        try:
            prev_btn = self.query_one("#startup-prev", Button)
            prev_btn.disabled = self.startup_index == 0
        except Exception:
            pass

        try:
            next_btn = self.query_one("#startup-next", Button)
            next_btn.disabled = len(self.startup_page_classes) == 0 or self._startup_next_is_blocked()
        except Exception:
            pass

    async def _finish_startup(self) -> None:
        self.startup_active = False
        self.query_one("#startup-shell", Container).display = False
        self._start_bootstrap()

    async def on_key(self, event: events.Key) -> None:
        if not self.startup_active:
            return

        key = event.key.lower()
        if key in ("a", "left"):
            await self._startup_prev()
            event.stop()
            return
        if key in ("d", "right"):
            await self._startup_next()
            event.stop()
