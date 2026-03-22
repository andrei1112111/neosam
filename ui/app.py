from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Awaitable

from db import Chat, Message, MyProfile, Settings, User
from net.i2p_sam import SAM_HOST, SAM_PORT, SAMIdentity
from net.net import EVENT_ERROR, EVENT_SECURE_READY, Net
from rich.align import Align
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static, TextArea

from ui.auto_update import (
    AutoUpdater,
    ReleaseDownloadError,
    ReleaseLookupError,
    format_up_to_date_status,
    STATUS_CHECKING,
    STATUS_DOWNLOADING,
    STATUS_DOWNLOAD_ERROR,
    STATUS_LOOKUP_ERROR,
)
from ui.i2p_status import collect_i2p_status, format_i2p_header
from ui.mixins import StartupMixin
from ui.pages import quick_start


class ChatListItem(Static):
    def __init__(self, chat_id: int, renderable: Text, *, selected: bool) -> None:
        classes = "chat-list-item"
        if selected:
            classes += " chat-list-item-selected"
        super().__init__(renderable, classes=classes)
        self.chat_id = chat_id

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if hasattr(self.app, "_open_chat"):
            self.app._open_chat(self.chat_id)


class CMD_UI(StartupMixin, App):
    TITLE = "NeoSAM Messenger"
    PEER_ONLINE_FRESH_SECONDS = 45
    CSS = """
    #startup-shell {
        width: 100%;
        height: 100%;
    }

    #startup-pages {
        width: 100%;
        height: 100%;
    }

    #app-shell {
        width: 100%;
        height: 100%;
    }

    #network-header {
        width: 100%;
        height: 1;
    }

    #network-header-text {
        width: 1fr;
        height: 1;
        content-align: center middle;
    }

    #close-app {
        width: auto;
        height: 1;
        min-width: 0;
        padding: 0 1;
    }

    #messenger-body {
        width: 100%;
        height: 1fr;
    }

    #messenger-layout {
        width: 100%;
        height: 100%;
    }

    #chat-sidebar {
        width: 30%;
        height: 100%;
        padding: 1 1 0 1;
    }

    #chat-sidebar-title {
        width: 100%;
        height: auto;
        text-style: bold;
        content-align: center middle;
        padding: 0 1;
    }

    #chat-sidebar-actions {
        width: 100%;
        height: auto;
        align-horizontal: center;
        padding: 0 0 1 0;
    }

    #chat-list-scroll {
        width: 100%;
        height: 1fr;
        overflow-y: scroll;
        overflow-x: hidden;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-background: white;
        scrollbar-background-hover: white;
        scrollbar-background-active: white;
        scrollbar-color: white;
        scrollbar-color-hover: white;
        scrollbar-color-active: white;
    }

    #chat-list-items {
        width: 100%;
        height: auto;
    }

    .chat-list-item {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
        background: transparent;
    }

    .chat-list-item:hover {
        background: rgb(60,60,60);
    }

    .chat-list-item-selected {
        background: rgb(60,60,60);
    }

    .chat-list-empty {
        width: 100%;
        height: auto;
        padding: 0 1;
    }

    #chat-workspace {
        width: 1fr;
        height: 100%;
    }

    .app-screen {
        width: 100%;
        height: 100%;
    }

    #chat-home-screen {
        width: 100%;
        height: 100%;
    }

    #chat-home-placeholder {
        width: 100%;
        height: 100%;
        content-align: center middle;
        text-style: bold;
        padding: 0 2;
    }

    #chat-message-scroll {
        width: 100%;
        height: 100%;
        display: none;
        padding: 1 2;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #chat-message-items {
        width: 100%;
        height: auto;
    }

    .chat-message {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    .chat-message-own {
        background: rgb(32,32,32);
    }

    .chat-message-peer {
        background: $surface;
    }

    .chat-message-empty {
        width: 100%;
        height: auto;
        content-align: center middle;
        padding: 1 0;
    }

    #new-chat-screen {
        width: 100%;
        height: 100%;
        display: none;
    }

    #new-chat-back-row {
        width: 100%;
        height: auto;
        padding: 0 0 0 1;
    }

    #new-chat-top-spacer {
        height: 1fr;
    }

    #new-chat-bottom-spacer {
        height: 1fr;
    }

    #new-chat-card {
        width: 100%;
        height: auto;
        align-horizontal: center;
        padding: 0 3;
    }

    #new-chat-title {
        width: 100%;
        height: auto;
        content-align: center middle;
        text-style: bold;
        padding: 0 1;
    }

    #new-chat-action-row {
        width: 100%;
        height: auto;
        align-horizontal: center;
        margin-top: 0;
    }

    #create-chat {
        margin-right: 1;
    }

    #show-join-chat {
        margin-left: 1;
    }

    .page-button {
        width: auto;
        height: auto;
        border: none;
        background: $surface;
        color: $primary;
        text-style: bold;
        min-width: 0;
        padding: 0 1;
    }

    .page-label {
        width: 100%;
        height: auto;
        content-align: center middle;
        padding: 0 1;
    }

    .page-panel {
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    #create-chat-panel {
        display: none;
    }

    #join-chat-panel {
        display: none;
    }

    #invite-json {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin-top: 0;
        background: $surface;
        border: solid $primary;
    }

    #copy-invite {
        margin-top: 0;
    }

    #invite-input {
        width: 100%;
        height: 4;
        margin-top: 0;
        background: $surface;
        border: solid $primary;
    }

    #invite-submit {
        width: auto;
        height: auto;
        margin-top: 0;
    }

    #join-error {
        width: 100%;
        height: auto;
        content-align: center middle;
        color: $error;
        padding: 0 1;
    }

    #new-chat-status {
        width: 100%;
        height: auto;
        content-align: center middle;
        padding: 0 1;
        margin-top: 0;
    }

    #profile-footer {
        width: 100%;
        height: 1;
    }

    #profile-footer-left {
        width: 1fr;
        height: 1;
        content-align: left middle;
    }

    #profile-footer-right {
        width: auto;
        height: 1;
        content-align: right middle;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.startup_page_classes = list(quick_start)
        self.startup_index = 0
        self.startup_active = False
        self.current_view = "home"
        self.new_chat_mode: str | None = None
        self.selected_chat_id: int | None = None

        self.settings_row: Settings | None = None
        self.project_root = Path(__file__).resolve().parents[1]
        self.identity_path = Path("net/.sam_identity.json")
        self.auto_updater = AutoUpdater(project_root=self.project_root)
        self.net: Net | None = None
        self.net_error: str | None = None
        self.last_invite_json: str | None = None
        self.update_status = STATUS_CHECKING
        self._bootstrap_task: asyncio.Task[None] | None = None
        self._network_status_task: asyncio.Task[None] | None = None
        self._net_event_task: asyncio.Task[None] | None = None
        self._net_init_task: asyncio.Task[bool] | None = None
        self._net_warmup_task: asyncio.Task[None] | None = None
        self._invite_action_task: asyncio.Task[None] | None = None
        self._auto_update_task: asyncio.Task[None] | None = None
        self._presence_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        with Container(id="startup-shell"):
            yield Container(id="startup-pages")

        with Vertical(id="app-shell"):
            with Horizontal(id="network-header"):
                yield Static(Align.center("нет подключения"), id="network-header-text")
                yield Button("[ закрыть ]", id="close-app", classes="page-button")
            with Container(id="messenger-body"):
                with Horizontal(id="messenger-layout"):
                    with Vertical(id="chat-sidebar"):
                        yield Static("Чаты", id="chat-sidebar-title")
                        with Horizontal(id="chat-sidebar-actions"):
                            yield Button("[ новый чат ]", id="open-new-chat", classes="page-button")
                        with VerticalScroll(id="chat-list-scroll"):
                            yield Vertical(id="chat-list-items")
                    with Vertical(id="chat-workspace"):
                        with Vertical(id="chat-home-screen", classes="app-screen"):
                            yield Static(
                                "Здесь будет открыт выбранный чат.",
                                id="chat-home-placeholder",
                            )
                            with VerticalScroll(id="chat-message-scroll"):
                                yield Vertical(id="chat-message-items")

                        with Vertical(id="new-chat-screen", classes="app-screen"):
                            with Horizontal(id="new-chat-back-row"):
                                yield Button(
                                    "[ вернуться к чатам ]",
                                    id="back-to-chats",
                                    classes="page-button",
                                )
                            yield Static(id="new-chat-top-spacer")
                            with Vertical(id="new-chat-card"):
                                yield Static("Новый чат", id="new-chat-title")
                                with Horizontal(id="new-chat-action-row"):
                                    yield Button("[ создать чат ]", id="create-chat", classes="page-button")
                                    yield Button(
                                        "[ подключиться к чату ]",
                                        id="show-join-chat",
                                        classes="page-button",
                                    )
                                with Vertical(id="create-chat-panel", classes="page-panel"):
                                    yield Static("invite json", classes="page-label")
                                    yield Static("", id="invite-json")
                                    yield Button(
                                        "[ копировать invite ]",
                                        id="copy-invite",
                                        classes="page-button",
                                        disabled=True,
                                    )
                                with Vertical(id="join-chat-panel", classes="page-panel"):
                                    yield Static("вставь invite json", classes="page-label")
                                    yield TextArea(
                                        "",
                                        id="invite-input",
                                        compact=True,
                                        placeholder="invite JSON",
                                        show_line_numbers=False,
                                    )
                                    yield Button(
                                        "[ подключиться ]",
                                        id="invite-submit",
                                        classes="page-button",
                                        disabled=True,
                                    )
                                    yield Static("", id="join-error")
                                yield Static("", id="new-chat-status")
                            yield Static(id="new-chat-bottom-spacer")
            with Horizontal(id="profile-footer"):
                yield Static("- | Sam ip: -", id="profile-footer-left")
                yield Static(self.update_status, id="profile-footer-right")

    async def on_mount(self) -> None:
        self.settings_row = self._ensure_settings_row()
        self.startup_active = bool(self.startup_page_classes) and not self.settings_row.initialized
        self.query_one("#app-shell", Vertical).display = False
        self.query_one("#startup-shell", Container).display = False
        self._refresh_chat_sidebar()
        self._show_chat_home()

        if self.startup_active:
            await self._show_startup()
            return

        self._start_bootstrap()

    def _start_bootstrap(self) -> None:
        if self._bootstrap_task is None or self._bootstrap_task.done():
            self._bootstrap_task = asyncio.create_task(self._bootstrap())

    async def on_shutdown(self) -> None:
        if self._net_init_task:
            self._net_init_task.cancel()
            try:
                await self._net_init_task
            except asyncio.CancelledError:
                pass
        if self._invite_action_task:
            self._invite_action_task.cancel()
            try:
                await self._invite_action_task
            except asyncio.CancelledError:
                pass
        if self._presence_task:
            self._presence_task.cancel()
            try:
                await self._presence_task
            except asyncio.CancelledError:
                pass
        if self._net_warmup_task:
            self._net_warmup_task.cancel()
            try:
                await self._net_warmup_task
            except asyncio.CancelledError:
                pass
        if self._auto_update_task:
            self._auto_update_task.cancel()
            try:
                await self._auto_update_task
            except asyncio.CancelledError:
                pass
        if self._net_event_task:
            self._net_event_task.cancel()
            try:
                await self._net_event_task
            except asyncio.CancelledError:
                pass
        if self._network_status_task:
            self._network_status_task.cancel()
            try:
                await self._network_status_task
            except asyncio.CancelledError:
                pass
        if self._bootstrap_task:
            self._bootstrap_task.cancel()
            try:
                await self._bootstrap_task
            except asyncio.CancelledError:
                pass
        if self.net is not None:
            await self.net.close()
            self.net = None

    async def _bootstrap(self) -> None:
        if not self.settings_row:
            self.exit("Settings not initialized")
            return

        await self._ensure_local_identity_and_profile(allow_create=True)
        self._refresh_chat_sidebar()
        self._refresh_profile_footer()
        self.query_one("#app-shell", Vertical).display = True
        self._show_chat_home()
        if self._network_status_task is None or self._network_status_task.done():
            self._network_status_task = asyncio.create_task(self._network_status_loop())
        if self._auto_update_task is None or self._auto_update_task.done():
            self._auto_update_task = asyncio.create_task(self._run_auto_update())
        self._start_net_background()

    async def _finish_startup(self) -> None:
        if self.settings_row and not self.settings_row.initialized:
            initialized = await self._complete_first_run_setup()
            if not initialized:
                page = self._current_startup_page()
                if page is not None:
                    setattr(page, "startup_next_disabled", True)
                self._refresh_startup_controls()
                return

        self.startup_active = False
        self.query_one("#startup-shell", Container).display = False
        self._start_bootstrap()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "startup-prev" and self.startup_active:
            await self._startup_prev()
            return

        if button_id == "startup-next" and self.startup_active:
            await self._startup_next()
            return

        if button_id == "open-new-chat":
            self._show_new_chat_screen(reset=True)
            return

        if button_id == "close-app":
            self.exit()
            return

        if button_id == "back-to-chats":
            self._show_chat_home()
            return

        if button_id == "create-chat":
            self._set_new_chat_mode("create")
            self._update_join_error("")
            self._start_invite_action(
                self._handle_create_chat(),
                "Создаю invite...",
            )
            return

        if button_id == "show-join-chat":
            self._set_new_chat_mode("join")
            self._update_join_error("")
            self._update_new_chat_status("")
            self.query_one("#invite-input", TextArea).focus()
            return

        if button_id == "copy-invite":
            self._copy_last_invite()
            return

        if button_id == "invite-submit":
            if not self.query_one("#invite-input", TextArea).text.strip():
                self._update_join_error("Вставь invite JSON.")
                return
            self._start_invite_action(
                self._handle_join_chat(),
                "Подключаюсь к чату...",
            )

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "invite-input":
            return
        self._update_join_submit_enabled()
        if event.text_area.text.strip():
            self._update_join_error("")

    async def _network_status_loop(self) -> None:
        while True:
            status = await collect_i2p_status()
            self.query_one("#network-header-text", Static).update(
                self._format_network_header(status)
            )
            self._refresh_profile_footer()
            await asyncio.sleep(5)

    async def _complete_first_run_setup(self) -> bool:
        if not self.settings_row:
            return False

        user = await self._ensure_local_identity_and_profile(allow_create=True)
        if user is None:
            return False

        self.settings_row.initialized = True
        self.settings_row.save(only=[Settings.initialized])
        return True

    async def _ensure_net(self) -> bool:
        if self.net is not None:
            return True
        if self._net_init_task is not None and not self._net_init_task.done():
            return await self._net_init_task

        self._net_init_task = asyncio.create_task(self._create_net_object())
        try:
            return await self._net_init_task
        finally:
            if self._net_init_task is not None and self._net_init_task.done():
                self._net_init_task = None

    async def _create_net_object(self) -> bool:
        try:
            self.net = await Net.create(
                identity_path=self.identity_path,
                sam_host=SAM_HOST,
                sam_port=SAM_PORT,
                username="User",
                autostart=False,
            )
            self.net_error = None
        except Exception as exc:
            self.net = None
            self.net_error = str(exc)
            return False

        return True

    async def _ensure_net_started(self) -> bool:
        if not await self._ensure_net():
            return False

        assert self.net is not None
        try:
            await asyncio.wait_for(self.net.start(), timeout=60.0)
            self.net_error = None
        except TimeoutError:
            self.net_error = "timeout while connecting to i2p"
            return False
        except Exception as exc:
            self.net_error = str(exc)
            return False

        if self._net_event_task is None or self._net_event_task.done():
            self._net_event_task = asyncio.create_task(self._net_event_loop())
        self._start_presence_loop()
        return True

    def _start_net_background(self) -> None:
        if self._net_warmup_task is None or self._net_warmup_task.done():
            self._net_warmup_task = asyncio.create_task(self._warmup_net())

    async def _warmup_net(self) -> None:
        try:
            await self._ensure_net_started()
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    def _start_presence_loop(self) -> None:
        if self._presence_task is None or self._presence_task.done():
            self._presence_task = asyncio.create_task(self._presence_loop())

    async def _presence_loop(self) -> None:
        while True:
            if self.net is not None:
                try:
                    local_user_id = self.net.local_user.id
                    peer_addresses: list[str] = []
                    sidebar_changed = False
                    for chat in self.net.list_chats():
                        if chat.user1_id == local_user_id:
                            peer_addresses.append(chat.user2.address)
                        else:
                            peer_addresses.append(chat.user1.address)

                    for peer_address in dict.fromkeys(peer_addresses):
                        try:
                            if not await self.net.probe_peer(peer_address):
                                sidebar_changed = self._mark_peer_offline(peer_address) or sidebar_changed
                                continue
                            await self.net.send_online_ping(peer_address)
                        except Exception:
                            sidebar_changed = self._mark_peer_offline(peer_address) or sidebar_changed
                            continue

                    changed_count = await self.net.mark_stale_users_offline(
                        threshold_seconds=self.PEER_ONLINE_FRESH_SECONDS
                    )
                    sidebar_changed = bool(changed_count) or sidebar_changed
                    if sidebar_changed:
                        self._refresh_chat_sidebar()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

            await asyncio.sleep(30)

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
            except Exception as exc:
                self._update_new_chat_status(f"Ошибка сети: {exc}")
                await asyncio.sleep(0.5)
                continue

            if event.kind == EVENT_SECURE_READY:
                self._refresh_chat_sidebar()
                self._refresh_open_chat()
                self._update_new_chat_status(
                    f"Защищённый канал готов: {self._format_address(event.peer_address)}"
                )
                continue

            if event.kind == EVENT_ERROR:
                error = event.payload.get("error", "unknown")
                self._update_new_chat_status(f"Ошибка сети: {error}")
                continue

            self._refresh_chat_sidebar()
            self._refresh_open_chat()

    async def _handle_create_chat(self) -> None:
        self._set_new_chat_mode("create")
        if not await self._ensure_net():
            self.last_invite_json = None
            self.query_one("#invite-json", Static).update("")
            self.query_one("#copy-invite", Button).disabled = True
            self._update_new_chat_status(
                f"Не удалось создать invite: {self.net_error or 'нет подключения к i2p'}"
            )
            return

        assert self.net is not None
        invite_text = json.dumps(
            self.net.create_invite(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.last_invite_json = invite_text
        self.query_one("#invite-json", Static).update(invite_text)
        self.query_one("#copy-invite", Button).disabled = False
        self._update_new_chat_status("Invite JSON создан.")
        asyncio.create_task(self._ensure_net_started())

    async def _handle_join_chat(self) -> None:
        raw = self.query_one("#invite-input", TextArea).text.strip()
        if not raw:
            self._update_join_error("Вставь invite JSON.")
            return
        if not await self._ensure_net_started():
            self._update_join_error(
                f"Не удалось подключиться к чату: {self.net_error or 'нет подключения к i2p'}"
            )
            return

        try:
            invite = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._update_join_error(f"Invite JSON не распознан: {exc}")
            return

        assert self.net is not None
        try:
            await asyncio.wait_for(
                self.net.connect_with_invite(invite),
                timeout=120.0,
            )
        except TimeoutError:
            self._update_join_error("Не удалось подключиться к чату: timeout.")
            return
        except Exception as exc:
            self._update_join_error(f"Не удалось подключиться к чату: {exc}")
            return

        peer_address = invite.get("address", "-")
        self.query_one("#invite-input", TextArea).load_text("")
        self._update_join_error("")
        self._update_join_submit_enabled()
        self._update_new_chat_status(
            f"Invite принят. Ответ отправлен на {self._format_address(str(peer_address))}."
        )
        self._refresh_chat_sidebar()
        self._show_chat_home()

    async def _ensure_local_identity_and_profile(
        self,
        *,
        allow_create: bool,
    ) -> User | None:
        identity = await self._load_or_create_identity(allow_create=allow_create)
        if identity is None:
            return None

        return self._ensure_local_user(identity.public_destination)

    async def _load_or_create_identity(
        self,
        *,
        allow_create: bool,
    ) -> SAMIdentity | None:
        identity = self._load_identity_from_disk()
        if identity is not None or not allow_create:
            return identity

        try:
            identity = await asyncio.wait_for(
                SAMIdentity.create(
                    sam_host=SAM_HOST,
                    sam_port=SAM_PORT,
                ),
                timeout=5.0,
            )
        except TimeoutError:
            return None
        except Exception:
            return None

        try:
            self.identity_path.parent.mkdir(parents=True, exist_ok=True)
            self.identity_path.write_text(
                identity.to_json(pretty=True),
                encoding="utf-8",
            )
        except Exception:
            return None

        return identity

    def _load_identity_from_disk(self) -> SAMIdentity | None:
        if not self.identity_path.exists():
            return None
        try:
            raw = self.identity_path.read_text(encoding="utf-8")
            if not raw.strip():
                return None
            return SAMIdentity.from_json(raw)
        except Exception:
            return None

    @staticmethod
    def _ensure_local_user(address: str) -> User:
        user, _ = User.get_or_create(
            address=address,
            defaults={"username": "User"},
        )
        if user.username.strip().lower() in {"", "user", "me"} and user.username != "User":
            user.username = "User"
            user.save(only=[User.username])

        profile = MyProfile.select().first()
        if profile is None:
            MyProfile.create(
                user=user,
                display_name="User",
            )
            return user

        dirty_fields = []
        if profile.user_id != user.id:
            profile.user = user
            dirty_fields.append(MyProfile.user)
        if not profile.display_name or profile.display_name.strip().lower() in {"user", "me"}:
            profile.display_name = "User"
            dirty_fields.append(MyProfile.display_name)
        if dirty_fields:
            profile.save(only=dirty_fields)
        return user

    def _refresh_profile_footer(self) -> None:
        profile = MyProfile.select().first()
        address = "-"
        username = "-"
        if profile is not None:
            address = profile.user.address or "-"
            username = profile.user.username or "-"

        self.query_one("#profile-footer-left", Static).update(
            f"{self._format_username(username)} | Sam ip: {self._format_address(address)}"
        )

    def _refresh_chat_sidebar(self) -> None:
        profile = MyProfile.select().first()
        if profile is None:
            try:
                items = self.query_one("#chat-list-items", Vertical)
                items.remove_children()
                items.mount(Static("Чатов пока нет.", classes="chat-list-empty"))
            except Exception:
                pass
            return

        local_user = profile.user
        chats = (
            Chat.select()
            .where((Chat.user1 == local_user) | (Chat.user2 == local_user))
            .order_by(Chat.created_at.desc())
        )

        items = None
        try:
            items = self.query_one("#chat-list-items", Vertical)
            items.remove_children()
        except Exception:
            return

        widgets: list[Static] = []
        chat_ids: list[int] = []
        for chat in chats:
            chat_ids.append(chat.id)
            peer = chat.user2 if chat.user1_id == local_user.id else chat.user1
            last_message = (
                Message.select()
                .where(Message.chat == chat)
                .order_by(Message.sent_at.desc())
                .first()
            )
            preview = "(нет сообщений)"
            preview_text = Text(preview, style="dim")
            if last_message and last_message.text:
                preview = last_message.text.replace("\n", " ").strip()
                if len(preview) > 36:
                    preview = preview[:33] + "..."
                preview_text = Text(preview, style="dim")
                preview_text.append(
                    f"  {self._format_message_stamp(last_message.sent_at)}",
                    style="grey70",
                )
            is_online = self._peer_is_online(peer)
            status_dot = Text("● ", style="green" if is_online else "grey50")
            username = Text(peer.username, style="bold bright_white")
            renderable = Text()
            renderable.append_text(status_dot)
            renderable.append_text(username)
            renderable.append("\n")
            renderable.append_text(preview_text)
            widgets.append(
                ChatListItem(
                    chat.id,
                    renderable,
                    selected=chat.id == self.selected_chat_id,
                )
            )

        if self.selected_chat_id is not None and self.selected_chat_id not in chat_ids:
            self.selected_chat_id = None

        if not widgets:
            widgets = [Static("Чатов пока нет.", classes="chat-list-empty")]

        items.mount(*widgets)

    def _peer_is_online(self, peer: User) -> bool:
        if self.net is None or self.net_error:
            self._mark_peer_offline(peer.address)
            return False

        if not peer.is_online:
            return False

        cutoff = dt.datetime.now() - dt.timedelta(seconds=self.PEER_ONLINE_FRESH_SECONDS)
        if peer.last_seen < cutoff:
            self._mark_peer_offline(peer.address)
            return False

        return True

    @staticmethod
    def _mark_peer_offline(peer_address: str) -> bool:
        peer = User.get_or_none(User.address == peer_address)
        if peer is None or not peer.is_online:
            return False
        peer.is_online = False
        peer.save(only=[User.is_online])
        return True

    @staticmethod
    def _format_message_stamp(sent_at: dt.datetime) -> str:
        now = dt.datetime.now(sent_at.tzinfo) if sent_at.tzinfo else dt.datetime.now()
        if sent_at.date() == now.date():
            return sent_at.strftime("%H:%M")
        return sent_at.strftime("%d.%m")

    def _open_chat(self, chat_id: int) -> None:
        self.selected_chat_id = chat_id
        self._show_chat_home()

    def _refresh_open_chat(self) -> None:
        try:
            placeholder = self.query_one("#chat-home-placeholder", Static)
            scroll = self.query_one("#chat-message-scroll", VerticalScroll)
            items = self.query_one("#chat-message-items", Vertical)
        except Exception:
            return

        items.remove_children()
        profile = MyProfile.select().first()
        local_user = profile.user if profile is not None else None

        if self.selected_chat_id is None or local_user is None:
            placeholder.update("Здесь будет открыт выбранный чат.")
            placeholder.display = True
            scroll.display = False
            return

        chat = Chat.get_or_none(Chat.id == self.selected_chat_id)
        if chat is None or (chat.user1_id != local_user.id and chat.user2_id != local_user.id):
            self.selected_chat_id = None
            placeholder.update("Здесь будет открыт выбранный чат.")
            placeholder.display = True
            scroll.display = False
            return

        peer = chat.user2 if chat.user1_id == local_user.id else chat.user1
        placeholder.display = False
        scroll.display = True

        messages = (
            Message.select()
            .where(Message.chat == chat)
            .order_by(Message.sent_at.asc())
        )

        widgets: list[Static] = []
        for message in messages:
            sender_name = "Вы" if message.sender_id == local_user.id else (message.sender.username or peer.username)
            header = Text(sender_name, style="bold bright_white")
            header.append(f"  {self._format_message_stamp(message.sent_at)}", style="grey70")
            body = Text(message.text or "(пустое сообщение)")
            renderable = Text()
            renderable.append_text(header)
            renderable.append("\n")
            renderable.append_text(body)
            classes = "chat-message chat-message-own" if message.sender_id == local_user.id else "chat-message chat-message-peer"
            widgets.append(Static(renderable, classes=classes))

        if not widgets:
            widgets = [Static("Сообщений пока нет.", classes="chat-message-empty")]

        items.mount(*widgets)

    def _update_auto_update_status(self, text: str) -> None:
        self.update_status = text
        try:
            renderable: str | Text = text
            if text.startswith("✓ "):
                renderable = Text(text, style="green")
            self.query_one("#profile-footer-right", Static).update(renderable)
        except Exception:
            return

    async def _run_auto_update(self) -> None:
        self._update_auto_update_status(STATUS_CHECKING)
        try:
            await asyncio.to_thread(self.auto_updater.finalize_pending_update)
        except Exception:
            pass

        current_version = await asyncio.to_thread(self.auto_updater.read_local_version)
        try:
            release = await asyncio.to_thread(self.auto_updater.fetch_latest_release)
        except ReleaseLookupError:
            self._update_auto_update_status(STATUS_LOOKUP_ERROR)
            return

        if release is None or release.title == current_version:
            self._update_auto_update_status(format_up_to_date_status(current_version))
            return

        self._update_auto_update_status(STATUS_DOWNLOADING)
        try:
            await asyncio.to_thread(
                self.auto_updater.download_and_apply_release,
                release,
            )
        except ReleaseDownloadError:
            self._update_auto_update_status(STATUS_DOWNLOAD_ERROR)
            return

        self._restart_updated_app()

    def _restart_updated_app(self) -> None:
        argv = sys.argv[:] if sys.argv else [str(self.project_root / "main.py")]
        if not argv or not argv[0] or argv[0] == "-c":
            argv = [str(self.project_root / "main.py")]
        os.execv(sys.executable, [sys.executable, *argv])

    def _show_chat_home(self) -> None:
        self.current_view = "home"
        self.new_chat_mode = None
        self._refresh_chat_sidebar()
        self._refresh_open_chat()
        try:
            self.query_one("#chat-home-screen", Vertical).display = True
            self.query_one("#new-chat-screen", Vertical).display = False
            self.query_one("#create-chat-panel", Vertical).display = False
            self.query_one("#join-chat-panel", Vertical).display = False
            self._update_join_error("")
        except Exception:
            return

    def _show_new_chat_screen(self, *, reset: bool) -> None:
        self.current_view = "new-chat"
        try:
            self.query_one("#chat-home-screen", Vertical).display = False
            self.query_one("#new-chat-screen", Vertical).display = True
        except Exception:
            return
        if reset:
            self._set_new_chat_mode(None)
            self._update_join_error("")
            self._update_new_chat_status("")

    def _set_new_chat_mode(self, mode: str | None) -> None:
        self.new_chat_mode = mode
        try:
            self.query_one("#create-chat-panel", Vertical).display = mode == "create"
            self.query_one("#join-chat-panel", Vertical).display = mode == "join"
        except Exception:
            return
        self._update_join_submit_enabled()

    def _update_new_chat_status(self, text: str) -> None:
        try:
            self.query_one("#new-chat-status", Static).update(text)
        except Exception:
            return

    def _update_join_error(self, text: str) -> None:
        try:
            self.query_one("#join-error", Static).update(text)
        except Exception:
            return

    def _update_join_submit_enabled(self) -> None:
        try:
            input_widget = self.query_one("#invite-input", TextArea)
            submit_btn = self.query_one("#invite-submit", Button)
        except Exception:
            return

        if self.new_chat_mode != "join":
            submit_btn.disabled = True
            return
        if input_widget.disabled:
            submit_btn.disabled = True
            return
        submit_btn.disabled = not input_widget.text.strip()

    def _set_new_chat_controls_busy(self, busy: bool) -> None:
        try:
            self.query_one("#open-new-chat", Button).disabled = busy
            self.query_one("#back-to-chats", Button).disabled = busy
            self.query_one("#create-chat", Button).disabled = busy
            self.query_one("#show-join-chat", Button).disabled = busy
            self.query_one("#copy-invite", Button).disabled = busy or not self.last_invite_json
            self.query_one("#invite-input", TextArea).disabled = busy
        except Exception:
            return
        self._update_join_submit_enabled()

    def _copy_last_invite(self) -> None:
        if not self.last_invite_json:
            self._update_new_chat_status("Сначала создай invite.")
            return
        if self._copy_text_to_clipboard(self.last_invite_json):
            self._update_new_chat_status("Invite JSON скопирован в буфер обмена.")
            return
        self._update_new_chat_status("Не удалось скопировать invite в буфер обмена.")

    def _copy_text_to_clipboard(self, text: str) -> bool:
        if sys.platform == "darwin" and shutil.which("pbcopy"):
            try:
                subprocess.run(
                    ["pbcopy"],
                    input=text,
                    text=True,
                    check=True,
                    timeout=2.0,
                )
                return True
            except Exception:
                return False

        try:
            self.copy_to_clipboard(text)
            return True
        except Exception:
            return False

    def _start_invite_action(self, coro: Awaitable[None], message: str) -> None:
        if self._invite_action_task is not None and not self._invite_action_task.done():
            self._update_new_chat_status("Действие уже выполняется...")
            return
        self._update_new_chat_status(message)
        self._set_new_chat_controls_busy(True)
        self._invite_action_task = asyncio.create_task(self._run_invite_action(coro))

    async def _run_invite_action(self, coro: Awaitable[None]) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._update_new_chat_status(f"Ошибка: {exc}")
        finally:
            self._set_new_chat_controls_busy(False)

    @staticmethod
    def _format_network_header(status: dict[str, str]):
        if status.get("connected") != "1":
            return Align.center(Text("нет подключения", style="bold red"))
        return format_i2p_header(status)

    @staticmethod
    def _format_username(username: str) -> str:
        if len(username) > 14:
            return username[:11] + "...."
        return username

    @staticmethod
    def _format_address(address: str) -> str:
        if len(address) > 10:
            return address[:10] + "..."
        return address

    @staticmethod
    def _ensure_settings_row() -> Settings:
        row = Settings.select().order_by(Settings.id).first()
        if row is None:
            row = Settings.create(theme="neosam", initialized=False)
        elif not row.theme:
            row.theme = "neosam"
            row.save(only=[Settings.theme])
        return row
