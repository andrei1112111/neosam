from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Awaitable

from db import MyProfile, Settings, User
from net.i2p_sam import SAM_HOST, SAM_PORT, SAMIdentity
from net.net import EVENT_ERROR, EVENT_SECURE_READY, Net
from rich.align import Align
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
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


class CMD_UI(StartupMixin, App):
    TITLE = "NeoSAM Messenger"
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

    #messenger-body {
        width: 100%;
        height: 1fr;
    }

    .app-screen {
        width: 100%;
        height: 100%;
    }

    #chat-home-screen {
        width: 100%;
        height: 100%;
    }

    #chat-home-top-spacer {
        height: 1fr;
    }

    #chat-home-bottom-spacer {
        height: 1fr;
    }

    #chat-home-card {
        width: 100%;
        height: auto;
        align-horizontal: center;
        padding: 0 2;
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
        self._invite_action_task: asyncio.Task[None] | None = None
        self._auto_update_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        with Container(id="startup-shell"):
            yield Container(id="startup-pages")

        with Vertical(id="app-shell"):
            yield Static(Align.center("нет подключения"), id="network-header")
            with Container(id="messenger-body"):
                with Vertical(id="chat-home-screen", classes="app-screen"):
                    yield Static(id="chat-home-top-spacer")
                    with Vertical(id="chat-home-card"):
                        yield Button("[ новый чат ]", id="open-new-chat", classes="page-button")
                    yield Static(id="chat-home-bottom-spacer")

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
        self._refresh_profile_footer()
        self.query_one("#app-shell", Vertical).display = True
        self._show_chat_home()
        if self._network_status_task is None or self._network_status_task.done():
            self._network_status_task = asyncio.create_task(self._network_status_loop())
        if self._auto_update_task is None or self._auto_update_task.done():
            self._auto_update_task = asyncio.create_task(self._run_auto_update())

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
            self.query_one("#network-header", Static).update(
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
        return True

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
                self._update_new_chat_status(
                    f"Защищённый канал готов: {self._format_address(event.peer_address)}"
                )
                continue

            if event.kind == EVENT_ERROR:
                error = event.payload.get("error", "unknown")
                self._update_new_chat_status(f"Ошибка сети: {error}")

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
                timeout=60.0,
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

    def _update_auto_update_status(self, text: str) -> None:
        self.update_status = text
        try:
            self.query_one("#profile-footer-right", Static).update(text)
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
            return Align.center("нет подключения")
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
