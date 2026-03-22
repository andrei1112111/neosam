from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class AddContactScreen(ModalScreen[None]):
    def compose(self) -> ComposeResult:
        with Container(id="modal-backdrop"):
            with Vertical(id="modal-card-contact"):
                yield Static("Новый контакт и handshake", id="modal-title")
                yield Static(
                    "Вариант A: «Создать чат» -> получаешь OFFER и передаёшь собеседнику.\n"
                    "Вариант B: «Присоединиться» -> вставляешь OFFER от собеседника, "
                    "получаешь REPLY и отправляешь обратно.\n"
                    "Финал: создатель вставляет REPLY через «Применить REPLY».",
                    id="modal-content",
                )
                yield Input(placeholder="Peer address", id="ac-peer-address")
                yield Input(placeholder="Peer username (optional)", id="ac-peer-username")
                yield Input(placeholder="Peer OFFER JSON", id="ac-offer")
                yield Input(placeholder="Peer REPLY JSON", id="ac-reply")
                yield Static(id="ac-output")
                with Horizontal(id="modal-actions"):
                    yield Button("Создать чат (OFFER)", id="ac-create", variant="primary")
                    yield Button("Присоединиться (REPLY)", id="ac-join")
                    yield Button("Применить REPLY", id="ac-apply-reply")
                    yield Button("Закрыть", id="ac-close")

    def on_mount(self) -> None:
        app: Any = self.app
        address = "N/A"
        if getattr(app, "net", None) is not None:
            address = app.net.address
        self.query_one("#ac-output", Static).update(f"Твой адрес:\n{address}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app: Any = self.app
        button_id = event.button.id
        peer_address = self.query_one("#ac-peer-address", Input).value.strip()
        peer_username = self.query_one("#ac-peer-username", Input).value.strip() or None
        offer_raw = self.query_one("#ac-offer", Input).value.strip()
        reply_raw = self.query_one("#ac-reply", Input).value.strip()

        try:
            if button_id == "ac-create":
                if not peer_address:
                    raise ValueError("Нужен peer address")
                offer_text = app.create_chat_offer(peer_address, peer_username=peer_username)
                self.query_one("#ac-output", Static).update(
                    f"Передай это собеседнику как OFFER:\n{offer_text}"
                )
            elif button_id == "ac-join":
                if not peer_address:
                    raise ValueError("Нужен peer address")
                if not offer_raw:
                    raise ValueError("Вставь OFFER JSON")
                reply_text = app.join_chat_from_offer(
                    peer_address,
                    offer_raw,
                    peer_username=peer_username,
                )
                self.query_one("#ac-output", Static).update(
                    f"Отправь это обратно создателю как REPLY:\n{reply_text}"
                )
            elif button_id == "ac-apply-reply":
                if not peer_address:
                    raise ValueError("Нужен peer address")
                if not reply_raw:
                    raise ValueError("Вставь REPLY JSON")
                app.complete_chat_with_reply(peer_address, reply_raw)
                self.query_one("#ac-output", Static).update(
                    "REPLY применён. Защищённый канал установлен."
                )
            elif button_id == "ac-close":
                self.dismiss(None)
        except Exception as exc:
            self.query_one("#ac-output", Static).update(f"Ошибка: {exc}")
