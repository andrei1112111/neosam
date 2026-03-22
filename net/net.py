from __future__ import annotations

import asyncio
import base64
import contextlib
import datetime as dt
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from crypto.crypto import SecureChannel
    from db import Chat, Message, MessageReaction, MyProfile, User
    from net.i2p_sam import (
        SAM_HOST,
        SAM_PORT,
        SAMIdentity,
        SAMIncomingPacket,
        SAMProtocolError,
        SAMTransport,
        SAMWireFormatError,
        decode_message,
    )
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from crypto.crypto import SecureChannel
    from db import Chat, Message, MessageReaction, MyProfile, User
    from net.i2p_sam import (
        SAM_HOST,
        SAM_PORT,
        SAMIdentity,
        SAMIncomingPacket,
        SAMProtocolError,
        SAMTransport,
        SAMWireFormatError,
        decode_message,
    )


NET_SCHEMA = "neosam-net"
NET_VERSION = 1
INVITE_SCHEMA = "neosam-invite"
INVITE_VERSION = 1

TYPE_TEXT = "text"
TYPE_HANDSHAKE_INIT = "handshake_init"
TYPE_HANDSHAKE_REPLY = "handshake_reply"
TYPE_DELIVERY_ACK = "delivery_ack"
TYPE_READ_ACK = "read_ack"
TYPE_EDIT = "edit"
TYPE_DELETE = "delete"
TYPE_REACTION = "reaction"
TYPE_ONLINE_PING = "online_ping"
TYPE_ONLINE_PONG = "online_pong"
TYPE_PROFILE_REQUEST = "profile_request"
TYPE_PROFILE_RESPONSE = "profile_response"
TYPE_CHAT_READY = "chat_ready"

EVENT_SECURE_READY = "secure_ready"
EVENT_ERROR = "error"


class NetError(RuntimeError):
    pass


class NetStateError(NetError):
    pass


class NetProtocolError(NetError):
    pass


@dataclass(frozen=True, slots=True)
class NetEvent:
    kind: str
    peer_address: str
    chat_id: int | None = None
    message_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class Net:
    """
    Высокоуровневый сетевой слой:
    - транспорт через SAM (I2P)
    - протокол событий поверх транспорта
    - сохранение состояния в локальный DB (users/chats/messages/reactions)
    """

    def __init__(
        self,
        transport: SAMTransport,
        *,
        identity_path: Path,
        auto_delivery_ack: bool = True,
    ) -> None:
        self.transport = transport
        self.identity_path = identity_path
        self.auto_delivery_ack = auto_delivery_ack

        self._events: asyncio.Queue[NetEvent] = asyncio.Queue()
        self._receive_task: asyncio.Task[None] | None = None
        self._closed = False

        self._channels: dict[str, SecureChannel] = {}
        self._pending_handshakes: dict[str, SecureChannel] = {}
        self._pending_invites: dict[str, SecureChannel] = {}
        self._profile_sync_started: set[str] = set()
        self._chat_ready_sent: set[str] = set()
        self._chat_ready_waiters: dict[str, asyncio.Future[Chat]] = {}

        self._remote_to_local_message_id: dict[tuple[str, str], int] = {}
        self._local_to_remote_message_id: dict[tuple[str, int], str] = {}

        self._local_user_id: int | None = None

    @classmethod
    async def create(
        cls,
        *,
        identity_path: str | Path = Path("net/.sam_identity.json"),
        sam_host: str = SAM_HOST,
        sam_port: int = SAM_PORT,
        session_id: str | None = None,
        username: str | None = None,
        display_name: str | None = None,
        bio: str | None = None,
        autostart: bool = True,
        auto_delivery_ack: bool = True,
    ) -> "Net":
        path = Path(identity_path)
        identity = await cls._load_or_create_identity(
            path,
            sam_host=sam_host,
            sam_port=sam_port,
        )
        transport = await SAMTransport.create(
            identity=identity,
            sam_host=sam_host,
            sam_port=sam_port,
            session_id=session_id,
        )
        net = cls(
            transport,
            identity_path=path,
            auto_delivery_ack=auto_delivery_ack,
        )
        net.ensure_local_profile(
            username=username,
            display_name=display_name,
            bio=bio,
        )
        if autostart:
            await net.start()
        return net

    @property
    def address(self) -> str:
        return self.transport.identity.public_destination

    @property
    def local_user(self) -> User:
        if self._local_user_id is None:
            self.ensure_local_profile()
        if self._local_user_id is None:
            raise NetStateError("Local profile is not initialized")
        return User.get_by_id(self._local_user_id)

    @staticmethod
    async def _load_or_create_identity(
        path: Path,
        *,
        sam_host: str,
        sam_port: int,
    ) -> SAMIdentity:
        if path.exists():
            try:
                raw = path.read_text(encoding="utf-8")
                if raw.strip():
                    return SAMIdentity.from_json(raw)
            except Exception as exc:
                raise NetStateError(f"Failed to load identity from {path}") from exc

        identity = await SAMIdentity.create(
            sam_host=sam_host,
            sam_port=sam_port,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(identity.to_json(pretty=True), encoding="utf-8")
        return identity

    async def start(self) -> None:
        if self._closed:
            raise NetStateError("Net is already closed")
        await self.transport.start_listener()
        if self._receive_task and not self._receive_task.done():
            return
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def close(self) -> None:
        self._closed = True
        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None
        for waiter in self._chat_ready_waiters.values():
            if not waiter.done():
                waiter.cancel()
        self._chat_ready_waiters.clear()
        await self.transport.close()

    def ensure_local_profile(
        self,
        *,
        username: str | None = None,
        display_name: str | None = None,
        bio: str | None = None,
    ) -> User:
        profile = MyProfile.select().first()
        if profile:
            user = profile.user
            user_dirty = False
            if user.address != self.address:
                user.address = self.address
                user_dirty = True
            if username and user.username != username:
                user.username = username
                user_dirty = True
            if user_dirty:
                user.save()

            profile_dirty = False
            if display_name is not None and profile.display_name != display_name:
                profile.display_name = display_name
                profile_dirty = True
            if bio is not None and profile.bio != bio:
                profile.bio = bio
                profile_dirty = True
            if profile_dirty:
                profile.save()

            self._local_user_id = user.id
            return user

        base_username = username or f"user-{self.address[:10]}"
        user, _ = User.get_or_create(
            address=self.address,
            defaults={"username": base_username},
        )
        if username and user.username != username:
            user.username = username
            user.save(only=[User.username])

        profile, created = MyProfile.get_or_create(
            user=user,
            defaults={
                "display_name": display_name,
                "bio": bio,
            },
        )
        if not created:
            profile_dirty = False
            if display_name is not None and profile.display_name != display_name:
                profile.display_name = display_name
                profile_dirty = True
            if bio is not None and profile.bio != bio:
                profile.bio = bio
                profile_dirty = True
            if profile_dirty:
                profile.save()

        self._local_user_id = user.id
        return user

    def has_secure_channel(self, peer_address: str) -> bool:
        return peer_address in self._channels

    def create_handshake_offer(self, peer_address: str) -> dict[str, str]:
        channel = SecureChannel()
        package = channel.get_handshake_package()
        self._pending_handshakes[peer_address] = channel
        return package

    def create_invite(self) -> dict[str, str | int]:
        channel = SecureChannel()
        invite_id = secrets.token_urlsafe(12)
        package = channel.get_handshake_package()
        self._pending_invites[invite_id] = channel
        return {
            "schema": INVITE_SCHEMA,
            "version": INVITE_VERSION,
            "address": self.address,
            "invite_id": invite_id,
            "salt": package["salt"],
            "pkey": package["pkey"],
        }

    def apply_handshake_offer(
        self,
        peer_address: str,
        offer_package: dict[str, Any],
    ) -> dict[str, str]:
        if not isinstance(offer_package, dict):
            raise NetProtocolError("Handshake package must be a JSON object")

        salt_raw = offer_package.get("salt")
        if not isinstance(salt_raw, str) or not salt_raw:
            raise NetProtocolError("Handshake package must contain non-empty salt")
        try:
            decoded_salt = base64.b64decode(salt_raw.encode(), validate=True)
        except Exception as exc:
            raise NetProtocolError("Handshake salt is not valid base64") from exc

        channel = SecureChannel()
        channel.my_salt = decoded_salt
        channel.finalize_handshake(offer_package)
        self._channels[peer_address] = channel
        self._pending_handshakes.pop(peer_address, None)
        return channel.get_handshake_package()

    def apply_handshake_reply(
        self,
        peer_address: str,
        reply_package: dict[str, Any],
    ) -> None:
        if not isinstance(reply_package, dict):
            raise NetProtocolError("Handshake package must be a JSON object")

        channel = self._pending_handshakes.pop(peer_address, None)
        if channel is None:
            raise NetStateError(
                f"No pending handshake found for peer {peer_address}"
            )
        channel.finalize_handshake(reply_package)
        self._channels[peer_address] = channel

    async def connect_with_invite(
        self,
        invite: dict[str, Any],
        *,
        peer_username: str | None = None,
    ) -> Chat:
        if not isinstance(invite, dict):
            raise NetProtocolError("Invite must be a JSON object")
        if invite.get("schema") != INVITE_SCHEMA:
            raise NetProtocolError("Unsupported invite schema")
        if invite.get("version") != INVITE_VERSION:
            raise NetProtocolError("Unsupported invite version")

        peer_address = invite.get("address")
        invite_id = invite.get("invite_id")
        salt = invite.get("salt")
        pkey = invite.get("pkey")
        if not isinstance(peer_address, str) or not peer_address.strip():
            raise NetProtocolError("Invite must contain non-empty address")
        if not isinstance(invite_id, str) or not invite_id.strip():
            raise NetProtocolError("Invite must contain non-empty invite_id")
        if not isinstance(salt, str) or not salt.strip():
            raise NetProtocolError("Invite must contain non-empty salt")
        if not isinstance(pkey, str) or not pkey.strip():
            raise NetProtocolError("Invite must contain non-empty pkey")

        waiter = self._ensure_chat_ready_waiter(peer_address)
        reply_package = self.apply_handshake_offer(
            peer_address,
            {"salt": salt, "pkey": pkey},
        )
        reply_packet = self._packet(
            TYPE_HANDSHAKE_REPLY,
            invite_id=invite_id,
            package=reply_package,
        )
        try:
            await self._send_packet_with_destination_retry(
                peer_address,
                reply_packet,
                force_plain=True,
                wait_timeout=90.0,
            )
            if peer_username:
                peer = self.get_or_create_peer(peer_address, username=peer_username)
                self._touch_peer_online(peer)
            return await waiter
        except Exception:
            current_waiter = self._chat_ready_waiters.get(peer_address)
            if current_waiter is waiter:
                self._chat_ready_waiters.pop(peer_address, None)
            if not waiter.done():
                waiter.cancel()
            raise

    async def initiate_secure_channel(self, peer_address: str) -> dict[str, str]:
        package = self.create_handshake_offer(peer_address)

        packet = self._packet(
            TYPE_HANDSHAKE_INIT,
            package=package,
        )
        await self._send_packet(peer_address, packet, force_plain=True)
        return package

    async def probe_peer(self, peer_address: str) -> bool:
        return await self.transport.probe_destination(peer_address)

    async def send_online_ping(self, peer_address: str) -> None:
        packet = self._packet(
            TYPE_ONLINE_PING,
            sent_at=self._now().isoformat(),
        )
        await self._send_packet(peer_address, packet, force_plain=True)

    async def mark_stale_users_offline(self, *, threshold_seconds: int = 75) -> int:
        if threshold_seconds <= 0:
            raise ValueError("threshold_seconds must be positive")

        cutoff = self._now() - dt.timedelta(seconds=threshold_seconds)
        query = User.update(is_online=False).where(
            (User.is_online == True)  # noqa: E712
            & (User.address != self.address)
            & (User.last_seen < cutoff)
        )
        return query.execute()

    def get_or_create_peer(self, address: str, *, username: str | None = None) -> User:
        defaults = {"username": username or f"peer-{address[:10]}"}
        user, _ = User.get_or_create(address=address, defaults=defaults)
        if username and user.username != username:
            user.username = username
            user.save(only=[User.username])
        return user

    def get_or_create_chat(self, peer_address: str, *, peer_username: str | None = None) -> Chat:
        if peer_address == self.address:
            raise ValueError("Cannot create chat with self")
        local = self.local_user
        peer = self.get_or_create_peer(peer_address, username=peer_username)
        chat, _ = Chat.get_or_create_private_chat(local, peer)
        return chat

    def _ensure_chat_ready_waiter(self, peer_address: str) -> asyncio.Future[Chat]:
        waiter = self._chat_ready_waiters.get(peer_address)
        if waiter is None or waiter.done():
            loop = asyncio.get_running_loop()
            waiter = loop.create_future()
            self._chat_ready_waiters[peer_address] = waiter
        return waiter

    async def _begin_post_handshake_sync(
        self,
        peer_address: str,
        *,
        peer_username: str | None = None,
    ) -> None:
        if peer_username:
            peer = self.get_or_create_peer(peer_address, username=peer_username)
            self._touch_peer_online(peer)

        if peer_address in self._profile_sync_started:
            return
        self._profile_sync_started.add(peer_address)

        request = self._packet(
            TYPE_PROFILE_REQUEST,
            username=self.local_user.username,
            sent_at=self._now().isoformat(),
        )
        await self._send_packet_with_destination_retry(
            peer_address,
            request,
            require_secure=True,
            wait_timeout=90.0,
        )

    async def _send_profile_response(self, peer_address: str) -> None:
        response = self._packet(
            TYPE_PROFILE_RESPONSE,
            username=self.local_user.username,
            sent_at=self._now().isoformat(),
        )
        await self._send_packet_with_destination_retry(
            peer_address,
            response,
            require_secure=True,
            wait_timeout=90.0,
        )

    async def _send_chat_ready(self, peer_address: str) -> None:
        if peer_address in self._chat_ready_sent:
            return
        self._chat_ready_sent.add(peer_address)
        packet = self._packet(
            TYPE_CHAT_READY,
            username=self.local_user.username,
            sent_at=self._now().isoformat(),
        )
        try:
            await self._send_packet_with_destination_retry(
                peer_address,
                packet,
                require_secure=True,
                wait_timeout=90.0,
            )
        except Exception:
            self._chat_ready_sent.discard(peer_address)
            raise

    def _mark_chat_ready(self, peer_address: str, chat: Chat) -> None:
        waiter = self._chat_ready_waiters.get(peer_address)
        if waiter is None or waiter.done():
            return
        waiter.set_result(chat)

    def _upsert_peer_from_name(self, peer_address: str, username: str | None) -> User:
        clean_username = None
        if isinstance(username, str):
            stripped = username.strip()
            if stripped:
                clean_username = stripped
        user = self.get_or_create_peer(peer_address, username=clean_username)
        self._touch_peer_online(user)
        return user

    def list_chats(self) -> list[Chat]:
        local = self.local_user
        query = (
            Chat.select()
            .where((Chat.user1 == local) | (Chat.user2 == local))
            .order_by(Chat.created_at.desc())
        )
        return list(query)

    def list_messages(
        self,
        chat: Chat | int,
        *,
        limit: int | None = 100,
        include_deleted: bool = False,
    ) -> list[Message]:
        chat_obj = chat if isinstance(chat, Chat) else Chat.get_by_id(chat)
        query = Message.select().where(Message.chat == chat_obj)
        if not include_deleted:
            query = query.where(Message.is_deleted == False)  # noqa: E712
        query = query.order_by(Message.sent_at)
        if limit is not None:
            query = query.limit(limit)
        return list(query)

    async def send_text(
        self,
        peer_address: str,
        text: str,
        *,
        reply_to: int | Message | None = None,
        require_secure: bool = False,
        force_plain: bool = False,
    ) -> Message:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Message text cannot be empty")

        chat = self.get_or_create_chat(peer_address)
        reply_message = self._resolve_reply_message(chat, reply_to)
        message = Message.create(
            chat=chat,
            sender=self.local_user,
            text=clean_text,
            reply_to=reply_message,
        )
        packet = self._packet(
            TYPE_TEXT,
            message_id=str(message.id),
            text=clean_text,
            sent_at=message.sent_at.isoformat(),
            reply_to=str(reply_message.id) if reply_message else None,
        )
        await self._send_packet(
            peer_address,
            packet,
            force_plain=force_plain,
            require_secure=require_secure,
        )
        return message

    async def edit_message(
        self,
        message_id: int,
        new_text: str,
        *,
        notify_peer: bool = True,
    ) -> Message:
        message = Message.get_by_id(message_id)
        if message.sender_id != self.local_user.id:
            raise NetStateError("Only own messages can be edited")

        clean_text = new_text.strip()
        if not clean_text:
            raise ValueError("Edited text cannot be empty")

        message.text = clean_text
        message.is_edited = True
        message.edited_at = self._now()
        message.save()

        if notify_peer:
            peer_address = self._peer_address_for_chat(message.chat)
            packet = self._packet(
                TYPE_EDIT,
                message_id=str(message.id),
                text=clean_text,
            )
            await self._send_packet(peer_address, packet)

        return message

    async def delete_message(
        self,
        message_id: int,
        *,
        notify_peer: bool = True,
    ) -> Message:
        message = Message.get_by_id(message_id)
        if message.sender_id != self.local_user.id:
            raise NetStateError("Only own messages can be deleted")

        message.is_deleted = True
        message.deleted_at = self._now()
        message.save()

        if notify_peer:
            peer_address = self._peer_address_for_chat(message.chat)
            packet = self._packet(TYPE_DELETE, message_id=str(message.id))
            await self._send_packet(peer_address, packet)

        return message

    async def react_to_message(
        self,
        message_id: int,
        reaction: str,
        *,
        notify_peer: bool = True,
    ) -> MessageReaction:
        message = Message.get_by_id(message_id)
        reaction_value = reaction.strip()
        if not reaction_value:
            raise ValueError("Reaction cannot be empty")

        me = self.local_user
        record, _ = MessageReaction.get_or_create(
            message=message,
            user=me,
            reaction=reaction_value,
        )

        if notify_peer:
            peer_address = self._peer_address_for_chat(message.chat)
            if message.sender_id == self.local_user.id:
                wire_message_id = str(message.id)
            else:
                wire_message_id = self._local_to_remote_message_id.get((peer_address, message.id))
                if wire_message_id is None:
                    raise NetStateError("No remote id mapping for this message")

            packet = self._packet(
                TYPE_REACTION,
                message_id=wire_message_id,
                reaction=reaction_value,
            )
            await self._send_packet(peer_address, packet)

        return record

    async def mark_message_read(
        self,
        message_id: int,
        *,
        notify_peer: bool = True,
    ) -> Message:
        message = Message.get_by_id(message_id)
        fields: list[Any] = []
        if not message.is_read:
            message.is_read = True
            fields.append(Message.is_read)
        if message.read_at is None:
            message.read_at = self._now()
            fields.append(Message.read_at)
        if fields:
            message.save(only=fields)

        if notify_peer and message.sender_id != self.local_user.id:
            peer_address = message.sender.address
            remote_message_id = self._local_to_remote_message_id.get((peer_address, message.id))
            if remote_message_id:
                packet = self._packet(TYPE_READ_ACK, message_id=remote_message_id)
                await self._send_packet(peer_address, packet)

        return message

    async def mark_chat_read(
        self,
        chat: Chat | int,
        *,
        notify_peer: bool = True,
    ) -> list[Message]:
        chat_obj = chat if isinstance(chat, Chat) else Chat.get_by_id(chat)
        unread = list(
            Message.select()
            .where(
                (Message.chat == chat_obj)
                & (Message.sender != self.local_user)
                & (Message.is_read == False)  # noqa: E712
            )
            .order_by(Message.sent_at)
        )
        for message in unread:
            await self.mark_message_read(message.id, notify_peer=notify_peer)
        return unread

    async def next_event(self, *, timeout: float | None = None) -> NetEvent:
        if timeout is None:
            return await self._events.get()
        return await asyncio.wait_for(self._events.get(), timeout=timeout)

    def get_event_nowait(self) -> NetEvent | None:
        try:
            return self._events.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _send_packet(
        self,
        peer_address: str,
        packet: dict[str, Any],
        *,
        force_plain: bool = False,
        require_secure: bool = False,
    ) -> None:
        secure_channel = None if force_plain else self._channels.get(peer_address)
        if require_secure and secure_channel is None:
            raise NetStateError(
                f"Secure channel with peer {peer_address} is not established"
            )
        await self.transport.send(
            peer_address,
            packet,
            secure_channel=secure_channel,
        )

    async def _send_packet_with_destination_retry(
        self,
        peer_address: str,
        packet: dict[str, Any],
        *,
        force_plain: bool = False,
        require_secure: bool = False,
        wait_timeout: float = 90.0,
        retry_interval: float = 2.0,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + wait_timeout
        last_error: Exception | None = None

        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                message = (
                    f"Peer destination {peer_address} is not published in I2P yet "
                    "or peer is offline"
                )
                if last_error is not None:
                    raise NetStateError(message) from last_error
                raise NetStateError(message)

            try:
                if not await self.probe_peer(peer_address):
                    await asyncio.sleep(min(retry_interval, remaining))
                    continue
                await self._send_packet(
                    peer_address,
                    packet,
                    force_plain=force_plain,
                    require_secure=require_secure,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if not self._is_retryable_destination_error(exc):
                    raise
                await asyncio.sleep(min(retry_interval, remaining))

    async def _receive_loop(self) -> None:
        while not self._closed:
            try:
                incoming = await self.transport.receive()
                event = await self._handle_incoming(incoming)
                if event is not None:
                    await self._events.put(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._closed:
                    return
                await self._events.put(
                    NetEvent(
                        kind=EVENT_ERROR,
                        peer_address="",
                        payload={"error": str(exc)},
                    )
                )
                await asyncio.sleep(0.2)

    async def _handle_incoming(self, incoming: SAMIncomingPacket) -> NetEvent | None:
        peer_address = incoming.sender_destination
        secure_channel = self._channels.get(peer_address)
        try:
            payload = decode_message(
                incoming.envelope,
                secure_channel=secure_channel,
            )
        except SAMWireFormatError as exc:
            raise NetProtocolError(str(exc)) from exc
        except Exception as exc:
            raise NetProtocolError("Failed to decode incoming packet") from exc

        if not isinstance(payload, dict):
            raise NetProtocolError("Decoded payload must be a JSON object")

        packet_type = self._validate_packet(payload)
        if packet_type in {
            TYPE_PROFILE_REQUEST,
            TYPE_PROFILE_RESPONSE,
            TYPE_CHAT_READY,
        } and secure_channel is None:
            raise NetProtocolError(f"{packet_type} packet requires secure channel")
        peer = User.get_or_none(User.address == peer_address)
        if peer is not None:
            self._touch_peer_online(peer)
        if packet_type == TYPE_HANDSHAKE_INIT:
            return await self._handle_handshake_init(peer_address, payload)
        if packet_type == TYPE_HANDSHAKE_REPLY:
            return await self._handle_handshake_reply(peer_address, payload)
        if packet_type == TYPE_TEXT:
            return await self._handle_text(peer_address, payload)
        if packet_type == TYPE_DELIVERY_ACK:
            return self._handle_delivery_ack(peer_address, payload)
        if packet_type == TYPE_READ_ACK:
            return self._handle_read_ack(peer_address, payload)
        if packet_type == TYPE_EDIT:
            return self._handle_edit(peer_address, payload)
        if packet_type == TYPE_DELETE:
            return self._handle_delete(peer_address, payload)
        if packet_type == TYPE_REACTION:
            return self._handle_reaction(peer_address, payload)
        if packet_type == TYPE_ONLINE_PING:
            return await self._handle_online_ping(peer_address, payload)
        if packet_type == TYPE_ONLINE_PONG:
            return self._handle_online_pong(peer_address, payload)
        if packet_type == TYPE_PROFILE_REQUEST:
            return await self._handle_profile_request(peer_address, payload)
        if packet_type == TYPE_PROFILE_RESPONSE:
            return await self._handle_profile_response(peer_address, payload)
        if packet_type == TYPE_CHAT_READY:
            return self._handle_chat_ready(peer_address, payload)

        return NetEvent(
            kind=EVENT_ERROR,
            peer_address=peer_address,
            payload={"error": f"Unsupported packet type: {packet_type}"},
        )

    async def _handle_handshake_init(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        package = payload.get("package")
        if not isinstance(package, dict):
            raise NetProtocolError("Handshake package must be an object")
        reply_package = self.apply_handshake_offer(peer_address, package)

        reply = self._packet(
            TYPE_HANDSHAKE_REPLY,
            package=reply_package,
        )
        await self._send_packet_with_destination_retry(
            peer_address,
            reply,
            force_plain=True,
            wait_timeout=90.0,
        )
        return NetEvent(
            kind=EVENT_SECURE_READY,
            peer_address=peer_address,
            payload={"role": "responder"},
        )

    async def _handle_handshake_reply(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        package = payload.get("package")
        if not isinstance(package, dict):
            raise NetProtocolError("Handshake package must be an object")
        invite_id = payload.get("invite_id")
        if isinstance(invite_id, str) and invite_id:
            channel = self._pending_invites.pop(invite_id, None)
            if channel is not None:
                channel.finalize_handshake(package)
                self._channels[peer_address] = channel
            else:
                self.apply_handshake_reply(peer_address, package)
        else:
            self.apply_handshake_reply(peer_address, package)
        await self._begin_post_handshake_sync(peer_address)
        return NetEvent(
            kind=EVENT_SECURE_READY,
            peer_address=peer_address,
            payload={"role": "initiator"},
        )

    async def _handle_profile_request(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        username = payload.get("username")
        peer = self._upsert_peer_from_name(
            peer_address,
            username if isinstance(username, str) else None,
        )
        chat, _ = Chat.get_or_create_private_chat(self.local_user, peer)
        await self._send_profile_response(peer_address)
        await self._send_chat_ready(peer_address)
        return NetEvent(
            kind=TYPE_PROFILE_REQUEST,
            peer_address=peer_address,
            chat_id=chat.id,
            payload={"status": "response_sent"},
        )

    async def _handle_profile_response(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        username = payload.get("username")
        peer = self._upsert_peer_from_name(
            peer_address,
            username if isinstance(username, str) else None,
        )
        chat, _ = Chat.get_or_create_private_chat(self.local_user, peer)
        await self._send_chat_ready(peer_address)
        return NetEvent(
            kind=TYPE_PROFILE_RESPONSE,
            peer_address=peer_address,
            chat_id=chat.id,
            payload={"username": peer.username},
        )

    def _handle_chat_ready(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        username = payload.get("username")
        peer = self._upsert_peer_from_name(
            peer_address,
            username if isinstance(username, str) else None,
        )
        chat, _ = Chat.get_or_create_private_chat(self.local_user, peer)
        self._mark_chat_ready(peer_address, chat)
        return NetEvent(
            kind=TYPE_CHAT_READY,
            peer_address=peer_address,
            chat_id=chat.id,
            payload={"status": "ready", "username": peer.username},
        )

    async def _handle_text(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        text_raw = payload.get("text")
        if not isinstance(text_raw, str) or not text_raw.strip():
            raise NetProtocolError("Text packet must contain non-empty text")

        sender_name = payload.get("sender_name")
        username = sender_name if isinstance(sender_name, str) and sender_name else None
        peer = self.get_or_create_peer(peer_address, username=username)
        chat, _ = Chat.get_or_create_private_chat(self.local_user, peer)

        remote_message_id = self._coerce_wire_message_id(payload.get("message_id"))
        remote_reply_id = payload.get("reply_to")
        reply_to_message = None
        if remote_reply_id is not None:
            reply_wire_id = self._coerce_wire_message_id(remote_reply_id)
            if reply_wire_id is None:
                raise NetProtocolError("reply_to must be non-empty when provided")
            reply_to_message = self._resolve_remote_message(
                peer_address,
                reply_wire_id,
            )

        message = Message.create(
            chat=chat,
            sender=peer,
            text=text_raw.strip(),
            reply_to=reply_to_message,
            is_delivered=True,
            delivered_at=self._now(),
        )

        if remote_message_id is not None:
            self._remote_to_local_message_id[(peer_address, remote_message_id)] = message.id
            self._local_to_remote_message_id[(peer_address, message.id)] = remote_message_id
            if self.auto_delivery_ack:
                ack = self._packet(TYPE_DELIVERY_ACK, message_id=remote_message_id)
                await self._send_packet(peer_address, ack)

        return NetEvent(
            kind=TYPE_TEXT,
            peer_address=peer_address,
            chat_id=chat.id,
            message_id=message.id,
            payload={"text": message.text},
        )

    def _handle_delivery_ack(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        message = self._resolve_outgoing_message(payload)
        if message is None:
            return NetEvent(
                kind=TYPE_DELIVERY_ACK,
                peer_address=peer_address,
                payload={"status": "missing"},
            )

        fields: list[Any] = []
        if not message.is_delivered:
            message.is_delivered = True
            fields.append(Message.is_delivered)
        if message.delivered_at is None:
            message.delivered_at = self._now()
            fields.append(Message.delivered_at)
        if fields:
            message.save(only=fields)

        return NetEvent(
            kind=TYPE_DELIVERY_ACK,
            peer_address=peer_address,
            chat_id=message.chat_id,
            message_id=message.id,
            payload={"status": "ok"},
        )

    def _handle_read_ack(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        message = self._resolve_outgoing_message(payload)
        if message is None:
            return NetEvent(
                kind=TYPE_READ_ACK,
                peer_address=peer_address,
                payload={"status": "missing"},
            )

        fields: list[Any] = []
        if not message.is_delivered:
            message.is_delivered = True
            fields.append(Message.is_delivered)
        if message.delivered_at is None:
            message.delivered_at = self._now()
            fields.append(Message.delivered_at)
        if not message.is_read:
            message.is_read = True
            fields.append(Message.is_read)
        if message.read_at is None:
            message.read_at = self._now()
            fields.append(Message.read_at)
        if fields:
            message.save(only=fields)

        return NetEvent(
            kind=TYPE_READ_ACK,
            peer_address=peer_address,
            chat_id=message.chat_id,
            message_id=message.id,
            payload={"status": "ok"},
        )

    def _handle_edit(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        wire_message_id = self._coerce_wire_message_id(payload.get("message_id"))
        if wire_message_id is None:
            raise NetProtocolError("Edit packet must contain message_id")

        text_raw = payload.get("text")
        if not isinstance(text_raw, str) or not text_raw.strip():
            raise NetProtocolError("Edit packet must contain non-empty text")

        message = self._resolve_remote_message(peer_address, wire_message_id)
        if message is None:
            raise NetStateError("Incoming edit references unknown message")

        message.text = text_raw.strip()
        message.is_edited = True
        message.edited_at = self._now()
        message.save()

        return NetEvent(
            kind=TYPE_EDIT,
            peer_address=peer_address,
            chat_id=message.chat_id,
            message_id=message.id,
            payload={"text": message.text},
        )

    def _handle_delete(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        wire_message_id = self._coerce_wire_message_id(payload.get("message_id"))
        if wire_message_id is None:
            raise NetProtocolError("Delete packet must contain message_id")

        message = self._resolve_remote_message(peer_address, wire_message_id)
        if message is None:
            raise NetStateError("Incoming delete references unknown message")

        message.is_deleted = True
        message.deleted_at = self._now()
        message.save()

        return NetEvent(
            kind=TYPE_DELETE,
            peer_address=peer_address,
            chat_id=message.chat_id,
            message_id=message.id,
            payload={"status": "ok"},
        )

    def _handle_reaction(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        wire_message_id = self._coerce_wire_message_id(payload.get("message_id"))
        if wire_message_id is None:
            raise NetProtocolError("Reaction packet must contain message_id")

        reaction = payload.get("reaction")
        if not isinstance(reaction, str) or not reaction.strip():
            raise NetProtocolError("Reaction must be a non-empty string")

        message = self._resolve_remote_message(peer_address, wire_message_id)
        if message is None:
            raise NetStateError("Incoming reaction references unknown message")

        peer = self.get_or_create_peer(peer_address)
        record, _ = MessageReaction.get_or_create(
            message=message,
            user=peer,
            reaction=reaction.strip(),
        )

        return NetEvent(
            kind=TYPE_REACTION,
            peer_address=peer_address,
            chat_id=message.chat_id,
            message_id=message.id,
            payload={"reaction": record.reaction},
        )

    async def _handle_online_ping(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        user = self.get_or_create_peer(peer_address)
        self._touch_peer_online(user)

        packet = self._packet(
            TYPE_ONLINE_PONG,
            sent_at=self._now().isoformat(),
            request_sent_at=payload.get("sent_at"),
        )
        await self._send_packet(peer_address, packet, force_plain=True)

        return NetEvent(
            kind=TYPE_ONLINE_PING,
            peer_address=peer_address,
            payload={"status": "pong_sent"},
        )

    def _handle_online_pong(
        self,
        peer_address: str,
        payload: dict[str, Any],
    ) -> NetEvent:
        user = self.get_or_create_peer(peer_address)
        self._touch_peer_online(user)
        return NetEvent(
            kind=TYPE_ONLINE_PONG,
            peer_address=peer_address,
            payload={"sent_at": payload.get("sent_at")},
        )

    def _resolve_outgoing_message(self, payload: dict[str, Any]) -> Message | None:
        wire_message_id = self._coerce_wire_message_id(payload.get("message_id"))
        if wire_message_id is None:
            raise NetProtocolError("Packet must contain message_id")

        try:
            local_message_id = int(wire_message_id)
        except ValueError:
            return None

        return Message.get_or_none(
            (Message.id == local_message_id) & (Message.sender == self.local_user)
        )

    def _resolve_remote_message(self, peer_address: str, wire_message_id: str) -> Message | None:
        local_id = self._remote_to_local_message_id.get((peer_address, wire_message_id))
        if local_id is not None:
            return Message.get_or_none(Message.id == local_id)

        try:
            local_id = int(wire_message_id)
        except ValueError:
            return None

        peer = User.get_or_none(User.address == peer_address)
        if peer is None:
            return None

        message = Message.get_or_none((Message.id == local_id) & (Message.sender == peer))
        if message is not None:
            self._remote_to_local_message_id[(peer_address, wire_message_id)] = message.id
            self._local_to_remote_message_id[(peer_address, message.id)] = wire_message_id
        return message

    def _touch_peer_online(self, user: User) -> None:
        user.is_online = True
        user.last_seen = self._now()
        user.save(only=[User.is_online, User.last_seen])

    @staticmethod
    def _is_retryable_destination_error(exc: Exception) -> bool:
        if isinstance(exc, SAMProtocolError):
            text = str(exc).lower()
            return "leaseset not found" in text
        return False

    def _packet(self, packet_type: str, **payload: Any) -> dict[str, Any]:
        packet = {
            "schema": NET_SCHEMA,
            "version": NET_VERSION,
            "type": packet_type,
        }
        packet.update(payload)
        return packet

    @staticmethod
    def _validate_packet(payload: dict[str, Any]) -> str:
        if payload.get("schema") != NET_SCHEMA:
            raise NetProtocolError("Unsupported packet schema")
        if payload.get("version") != NET_VERSION:
            raise NetProtocolError("Unsupported packet version")
        packet_type = payload.get("type")
        if not isinstance(packet_type, str) or not packet_type:
            raise NetProtocolError("Packet type must be a non-empty string")
        return packet_type

    @staticmethod
    def _coerce_wire_message_id(raw_value: Any) -> str | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, int):
            return str(raw_value)
        if isinstance(raw_value, str):
            value = raw_value.strip()
            return value or None
        raise NetProtocolError("message_id must be string or int")

    def _resolve_reply_message(
        self,
        chat: Chat,
        reply_to: int | Message | None,
    ) -> Message | None:
        if reply_to is None:
            return None
        if isinstance(reply_to, Message):
            if reply_to.chat_id != chat.id:
                raise NetStateError("reply_to must reference a message in the same chat")
            return reply_to
        if isinstance(reply_to, int):
            message = Message.get_or_none((Message.id == reply_to) & (Message.chat == chat))
            if message is None:
                raise NetStateError(f"Message with id={reply_to} not found in this chat")
            return message
        raise TypeError("reply_to must be Message, int or None")

    def _peer_address_for_chat(self, chat: Chat) -> str:
        local_id = self.local_user.id
        if chat.user1_id == local_id:
            return chat.user2.address
        if chat.user2_id == local_id:
            return chat.user1.address
        raise NetStateError("Chat does not belong to local profile")

    @staticmethod
    def _now() -> dt.datetime:
        return dt.datetime.now()


__all__ = [
    "EVENT_ERROR",
    "EVENT_SECURE_READY",
    "NET_SCHEMA",
    "NET_VERSION",
    "Net",
    "NetError",
    "NetEvent",
    "NetProtocolError",
    "NetStateError",
    "TYPE_DELETE",
    "TYPE_DELIVERY_ACK",
    "TYPE_EDIT",
    "TYPE_CHAT_READY",
    "TYPE_HANDSHAKE_INIT",
    "TYPE_HANDSHAKE_REPLY",
    "TYPE_ONLINE_PING",
    "TYPE_ONLINE_PONG",
    "TYPE_PROFILE_REQUEST",
    "TYPE_PROFILE_RESPONSE",
    "TYPE_REACTION",
    "TYPE_READ_ACK",
    "TYPE_TEXT",
]
