from __future__ import annotations

import asyncio
import datetime as dt
import json

from db import Chat, Message, User
from net.net import (
    EVENT_ERROR,
    EVENT_SECURE_READY,
    Net,
    TYPE_DELETE,
    TYPE_DELIVERY_ACK,
    TYPE_EDIT,
    TYPE_ONLINE_PING,
    TYPE_ONLINE_PONG,
    TYPE_REACTION,
    TYPE_READ_ACK,
    TYPE_TEXT,
    NetEvent,
)
from textual.widgets import Button, Input, ListItem, ListView, Log, Static



class MessengerMixin:
    net: Net | None
    selected_chat_id: int | None
    last_online_check_at: dt.datetime | None
    net_start_error: str | None
    spinner_index: int

    _event_task: asyncio.Task[None] | None
    _presence_task: asyncio.Task[None] | None
    _spinner_task: asyncio.Task[None] | None

    def _start_background_tasks(self) -> None:
        if self.net is not None and (self._event_task is None or self._event_task.done()):
            self._event_task = asyncio.create_task(self._net_event_loop())
        if self.net is not None and (self._presence_task is None or self._presence_task.done()):
            self._presence_task = asyncio.create_task(self._presence_loop())
        if self._spinner_task is None or self._spinner_task.done():
            self._spinner_task = asyncio.create_task(self._spinner_loop())

    async def _net_event_loop(self) -> None:
        while True:
            if self.net is None:
                await asyncio.sleep(1)
                continue
            try:
                event = await self.net.next_event(timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            await self._handle_net_event(event)

    async def _handle_net_event(self, event: NetEvent) -> None:
        if event.kind == EVENT_ERROR:
            self._refresh_status_bar(extra=f"net error: {event.payload.get('error', 'unknown')}")
            return

        if event.kind in (TYPE_ONLINE_PING, TYPE_ONLINE_PONG):
            self._refresh_chat_list()
            self._refresh_chat_header()
            return

        if event.kind in (
            TYPE_TEXT,
            TYPE_DELIVERY_ACK,
            TYPE_READ_ACK,
            TYPE_EDIT,
            TYPE_DELETE,
            TYPE_REACTION,
            EVENT_SECURE_READY,
        ):
            self._refresh_chat_list()
            if event.chat_id is not None and self.selected_chat_id == event.chat_id:
                self._refresh_messages()
                if event.kind == TYPE_TEXT and self.net:
                    await self.net.mark_chat_read(event.chat_id, notify_peer=True)
            self._refresh_chat_header()

    async def _presence_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            if self.net is None:
                continue

            chats = self.net.list_chats()
            for chat in chats:
                peer = self._peer_for_chat(chat)
                try:
                    await self.net.send_online_ping(peer.address)
                except Exception:
                    continue

            try:
                await self.net.mark_stale_users_offline(threshold_seconds=75)
            except Exception:
                pass

            self.last_online_check_at = dt.datetime.now()
            self._refresh_chat_list()
            self._refresh_chat_header()
            self._refresh_status_bar()

    async def _spinner_loop(self) -> None:
        while True:
            await asyncio.sleep(0.35)
            self.spinner_index = (self.spinner_index + 1) % len(SPINNER_FRAMES)
            self._refresh_chat_list()
            if self._selected_chat_has_pending_outgoing():
                self._refresh_messages()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "message-input":
            await self._send_current_message()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if item is None or not item.id:
            return
        if not item.id.startswith("chat-"):
            return
        chat_id = int(item.id.split("-", 1)[1])
        self.selected_chat_id = chat_id
        self._refresh_chat_header()
        self._refresh_messages()
        if self.net:
            await self.net.mark_chat_read(chat_id, notify_peer=True)
            self._refresh_chat_list()

    async def _send_current_message(self) -> None:
        if self.net is None:
            return
        if self.selected_chat_id is None:
            self._refresh_status_bar(extra="Сначала выбери чат.")
            return
        input_widget = self.query_one("#message-input", Input)
        text = input_widget.value.strip()
        if not text:
            return
        chat = Chat.get_by_id(self.selected_chat_id)
        peer = self._peer_for_chat(chat)
        await self.net.send_text(peer.address, text)
        input_widget.value = ""
        self._refresh_chat_list()
        self._refresh_messages()

    def create_chat_offer(self, peer_address: str, *, peer_username: str | None = None) -> str:
        if self.net is None:
            raise RuntimeError("Net is not initialized")
        chat = self.net.get_or_create_chat(peer_address, peer_username=peer_username)
        offer = self.net.create_handshake_offer(peer_address)
        self.selected_chat_id = chat.id
        self._refresh_chat_list()
        self._refresh_chat_header()
        self._refresh_messages()
        return json.dumps(offer, ensure_ascii=False)

    def join_chat_from_offer(
        self,
        peer_address: str,
        offer_raw: str,
        *,
        peer_username: str | None = None,
    ) -> str:
        if self.net is None:
            raise RuntimeError("Net is not initialized")
        chat = self.net.get_or_create_chat(peer_address, peer_username=peer_username)
        offer = json.loads(offer_raw)
        if not isinstance(offer, dict):
            raise ValueError("OFFER должен быть JSON-объектом")
        reply = self.net.apply_handshake_offer(peer_address, offer)
        self.selected_chat_id = chat.id
        self._refresh_chat_list()
        self._refresh_chat_header()
        self._refresh_messages()
        return json.dumps(reply, ensure_ascii=False)

    def complete_chat_with_reply(self, peer_address: str, reply_raw: str) -> None:
        if self.net is None:
            raise RuntimeError("Net is not initialized")
        reply = json.loads(reply_raw)
        if not isinstance(reply, dict):
            raise ValueError("REPLY должен быть JSON-объектом")
        self.net.apply_handshake_reply(peer_address, reply)
        self._refresh_chat_list()
        self._refresh_chat_header()

    def _refresh_chat_list(self) -> None:
        if self.net is None:
            return
        list_view = self.query_one("#chat-list", ListView)
        list_view.clear()

        chats = self.net.list_chats()
        if chats and self.selected_chat_id is None:
            self.selected_chat_id = chats[0].id
        if chats and self.selected_chat_id not in {chat.id for chat in chats}:
            self.selected_chat_id = chats[0].id

        selected_index = 0
        for index, chat in enumerate(chats):
            peer = self._peer_for_chat(chat)
            last_message = (
                Message.select()
                .where(Message.chat == chat)
                .order_by(Message.sent_at.desc())
                .first()
            )

            unread_count = (
                Message.select()
                .where(
                    (Message.chat == chat)
                    & (Message.sender == peer)
                    & (Message.is_read == False)  # noqa: E712
                )
                .count()
            )

            if last_message is None:
                preview = "(нет сообщений)"
                status_icon = "·"
            else:
                preview = self._short_message_preview(last_message)
                status_icon = self._chat_last_status_icon(last_message, peer)

            unread = f" [{unread_count}]" if unread_count > 0 else ""
            text = f"{peer.username}{unread}\n{status_icon} {preview}"
            item = ListItem(Static(text), id=f"chat-{chat.id}")
            list_view.append(item)
            if self.selected_chat_id == chat.id:
                selected_index = index

        if chats and list_view.index != selected_index:
            list_view.index = selected_index

    def _refresh_chat_header(self) -> None:
        if self.net is None:
            return
        header = self.query_one("#chat-header", Static)
        if self.selected_chat_id is None:
            header.update("Чат не выбран")
            return
        chat = Chat.get_or_none(Chat.id == self.selected_chat_id)
        if chat is None:
            header.update("Чат не выбран")
            return
        peer = self._peer_for_chat(chat)
        secure_icon = "🔐" if self.net.has_secure_channel(peer.address) else "🔓"
        if peer.is_online:
            status = "онлайн"
        else:
            status = f"был в сети {self._format_age(peer.last_seen)} назад"
        header.update(f"{secure_icon} {peer.username} · {status}")

    def _refresh_messages(self) -> None:
        if self.net is None:
            return
        log = self.query_one("#messages-log", Log)
        log.clear()
        if self.selected_chat_id is None:
            log.write_line("Выбери чат слева.")
            return
        chat = Chat.get_or_none(Chat.id == self.selected_chat_id)
        if chat is None:
            log.write_line("Чат не найден.")
            return

        peer = self._peer_for_chat(chat)
        messages = self.net.list_messages(chat, limit=300, include_deleted=True)
        log_width = log.size.width if log.size.width > 0 else 80
        for message in messages:
            body = "<удалено>" if message.is_deleted else (message.text or "")
            sent_time = message.sent_at.strftime("%H:%M")
            is_outgoing = message.sender_id == self.net.local_user.id
            if is_outgoing:
                icon = self._message_status_icon(message, peer)
                line = f"{body}  {sent_time} {icon}"
                log.write_line(line.rjust(max(20, log_width - 2)))
            else:
                line = f"{message.sender.username}: {body}  {sent_time}"
                log.write_line(line)

    def _chat_last_status_icon(self, message: Message, peer: User) -> str:
        if self.net is None:
            return "·"
        if message.sender_id != self.net.local_user.id:
            return "←"
        return self._message_status_icon(message, peer)

    def _message_status_icon(self, message: Message, peer: User) -> str:
        if message.is_read:
            return "✓✓"
        if message.is_delivered:
            return "✓"
        spinner = SPINNER_FRAMES[self.spinner_index]
        return spinner if peer.is_online else spinner

    @staticmethod
    def _short_message_preview(message: Message) -> str:
        text = "<удалено>" if message.is_deleted else (message.text or "")
        text = text.replace("\n", " ").strip()
        if len(text) > 42:
            return text[:39] + "..."
        return text or "(пусто)"

    def _selected_chat_has_pending_outgoing(self) -> bool:
        if self.net is None or self.selected_chat_id is None:
            return False
        chat = Chat.get_or_none(Chat.id == self.selected_chat_id)
        if chat is None:
            return False
        query = Message.select().where(
            (Message.chat == chat)
            & (Message.sender == self.net.local_user)
            & (Message.is_delivered == False)  # noqa: E712
            & (Message.is_deleted == False)  # noqa: E712
        )
        return query.exists()

    def _peer_for_chat(self, chat: Chat) -> User:
        if self.net is None:
            raise RuntimeError("Net is not initialized")
        local_id = self.net.local_user.id
        if chat.user1_id == local_id:
            return chat.user2
        return chat.user1

    def _refresh_status_bar(self, *, extra: str | None = None) -> None:
        status_widget = self.query_one("#i2pd-status", Static)
        online_age = (
            self._format_age(self.last_online_check_at) + " назад"
            if self.last_online_check_at
            else "ещё не проверялись"
        )
        if self.net is None:
            text = "Net=OFFLINE"
            if self.net_start_error:
                text += f" ({self.net_start_error})"
            text += " | i2p checks disabled"
        else:
            text = f"Net=ONLINE | Address={self.net.address[:24]}... | Online check: {online_age}"
        if extra:
            text += f" | {extra}"
        status_widget.update(text)

    @staticmethod
    def _format_age(ts: dt.datetime | None) -> str:
        if ts is None:
            return "никогда"
        seconds = int((dt.datetime.now() - ts).total_seconds())
        if seconds < 60:
            return f"{seconds}с"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}м"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}ч"
        days = hours // 24
        return f"{days}д"
