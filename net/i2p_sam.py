from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import shlex
from dataclasses import dataclass
from typing import Any


SAM_HOST = "127.0.0.1"
SAM_PORT = 7656
SAM_HELLO = b"HELLO VERSION MIN=3.1 MAX=3.1\n"

WIRE_SCHEMA = "neosam-wire"
PLAIN_MODE = "plain"
ENCRYPTED_MODE = "encrypted"


class SAMError(RuntimeError):
    pass


class SAMProtocolError(SAMError):
    pass


class SAMWireFormatError(SAMError):
    pass


@dataclass(frozen=True, slots=True)
class SAMIdentity:
    public_destination: str
    private_destination: str
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "neosam-sam-identity",
            "version": self.version,
            "public_destination": self.public_destination,
            "private_destination": self.private_destination,
        }

    def to_json(self, *, pretty: bool = False) -> str:
        if pretty:
            return json.dumps(self.to_dict(), ensure_ascii=True, indent=2, sort_keys=True)
        return json.dumps(self.to_dict(), ensure_ascii=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SAMIdentity":
        if payload.get("schema") != "neosam-sam-identity":
            raise SAMWireFormatError("Unexpected SAM identity schema")
        return cls(
            public_destination=_require_string(payload, "public_destination"),
            private_destination=_require_string(payload, "private_destination"),
            version=_require_int(payload, "version", default=1),
        )

    @classmethod
    def from_json(cls, raw: str) -> "SAMIdentity":
        payload = _decode_json(raw)
        if not isinstance(payload, dict):
            raise SAMWireFormatError("SAM identity payload must be a JSON object")
        return cls.from_dict(payload)

    @classmethod
    async def create(
        cls,
        *,
        sam_host: str = SAM_HOST,
        sam_port: int = SAM_PORT,
    ) -> "SAMIdentity":
        public_destination, private_destination = await generate_sam_identity(
            sam_host=sam_host,
            sam_port=sam_port,
        )
        return cls(
            public_destination=public_destination,
            private_destination=private_destination,
        )


@dataclass(frozen=True, slots=True)
class SAMIncomingPacket:
    sender_destination: str
    envelope: dict[str, Any]

    @property
    def mode(self) -> str:
        return _require_string(self.envelope, "mode")


class SAMTransport:
    def __init__(
        self,
        identity: SAMIdentity,
        *,
        sam_host: str = SAM_HOST,
        sam_port: int = SAM_PORT,
        session_id: str | None = None,
    ) -> None:
        self.identity = identity
        self.sam_host = sam_host
        self.sam_port = sam_port
        self.session_id = session_id or f"neosam-{secrets.token_hex(6)}"
        self._incoming: asyncio.Queue[SAMIncomingPacket] = asyncio.Queue()
        self._listener_task: asyncio.Task[None] | None = None
        self._session_reader: asyncio.StreamReader | None = None
        self._session_writer: asyncio.StreamWriter | None = None
        self._closed = False

    @classmethod
    async def create(
        cls,
        *,
        identity: SAMIdentity | None = None,
        sam_host: str = SAM_HOST,
        sam_port: int = SAM_PORT,
        session_id: str | None = None,
    ) -> "SAMTransport":
        resolved_identity = identity or await SAMIdentity.create(
            sam_host=sam_host,
            sam_port=sam_port,
        )
        return cls(
            resolved_identity,
            sam_host=sam_host,
            sam_port=sam_port,
            session_id=session_id,
        )

    async def connect(self) -> str:
        if self._closed:
            raise SAMError("Transport is already closed")
        if self._session_writer and not self._session_writer.is_closing():
            return self.identity.public_destination

        reader, writer = await _open_sam_socket(self.sam_host, self.sam_port)
        try:
            await _sam_hello(reader, writer)
            command = (
                f"SESSION CREATE STYLE=STREAM ID={self.session_id} "
                f"DESTINATION={self.identity.private_destination} "
                "i2cp.leaseSetEncType=4,0 inbound.quantity=3 outbound.quantity=3\n"
            )
            writer.write(command.encode())
            await writer.drain()

            response = await reader.readline()
            text, fields = _parse_sam_line(response)
            if fields.get("RESULT") != "OK":
                raise SAMProtocolError(f"SESSION CREATE failed: {text}")
        except Exception:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            raise

        self._session_reader = reader
        self._session_writer = writer
        return self.identity.public_destination

    async def start_listener(self) -> None:
        await self.connect()
        if self._listener_task and not self._listener_task.done():
            return
        self._listener_task = asyncio.create_task(self._accept_loop())

    async def receive(self) -> SAMIncomingPacket:
        await self.start_listener()
        return await self._incoming.get()

    async def send(
        self,
        destination: str,
        payload: dict[str, Any],
        *,
        secure_channel: SecureChannel | None = None,
    ) -> None:
        envelope = encode_message(payload, secure_channel=secure_channel)
        await self.send_envelope(destination, envelope)

    async def send_envelope(self, destination: str, envelope: dict[str, Any]) -> None:
        await self.connect()
        reader, writer = await _open_sam_socket(self.sam_host, self.sam_port)
        try:
            await _sam_hello(reader, writer)
            command = (
                f"STREAM CONNECT ID={self.session_id} "
                f"DESTINATION={destination} SILENT=false\n"
            )
            writer.write(command.encode())
            await writer.drain()

            response = await reader.readline()
            text, fields = _parse_sam_line(response)
            if fields.get("RESULT") != "OK":
                raise SAMProtocolError(f"STREAM CONNECT failed: {text}")

            writer.write(_pack_envelope(envelope))
            await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def probe_destination(self, destination: str) -> bool:
        await self.connect()
        reader, writer = await _open_sam_socket(self.sam_host, self.sam_port)
        try:
            await _sam_hello(reader, writer)
            command = (
                f"STREAM CONNECT ID={self.session_id} "
                f"DESTINATION={destination} SILENT=false\n"
            )
            writer.write(command.encode())
            await writer.drain()

            response = await reader.readline()
            _, fields = _parse_sam_line(response)
            return fields.get("RESULT") == "OK"
        except Exception:
            return False
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def close(self) -> None:
        self._closed = True
        if self._listener_task:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None

        if self._session_writer:
            self._session_writer.close()
            with contextlib.suppress(Exception):
                await self._session_writer.wait_closed()
            self._session_writer = None
            self._session_reader = None

    async def _accept_loop(self) -> None:
        while not self._closed:
            writer: asyncio.StreamWriter | None = None
            try:
                reader, writer = await _open_sam_socket(self.sam_host, self.sam_port)
                await _sam_hello(reader, writer)

                writer.write(f"STREAM ACCEPT ID={self.session_id} SILENT=false\n".encode())
                await writer.drain()

                response = await reader.readline()
                text, fields = _parse_sam_line(response)
                if fields.get("RESULT") != "OK":
                    raise SAMProtocolError(f"STREAM ACCEPT failed: {text}")

                sender_line = await reader.readline()
                if not sender_line:
                    raise SAMProtocolError("SAM closed ACCEPT before sending peer destination")

                sender_destination = sender_line.decode().strip().split(" ", 1)[0]
                payload = (await reader.read()).decode().strip()
                if not payload:
                    continue

                envelope = parse_envelope(payload)
                await self._incoming.put(
                    SAMIncomingPacket(
                        sender_destination=sender_destination,
                        envelope=envelope,
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._closed:
                    break
                await asyncio.sleep(1)
            finally:
                if writer:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await writer.wait_closed()


def build_plain_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": WIRE_SCHEMA,
        "version": 1,
        "mode": PLAIN_MODE,
        "payload": payload,
    }


def build_encrypted_envelope(
    payload: dict[str, Any],
    secure_channel: SecureChannel,
) -> dict[str, Any]:
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "schema": WIRE_SCHEMA,
        "version": 1,
        "mode": ENCRYPTED_MODE,
        "ciphertext": secure_channel.encrypt(plaintext),
    }


def encode_message(
    payload: dict[str, Any],
    *,
    secure_channel: SecureChannel | None = None,
) -> dict[str, Any]:
    if secure_channel is None:
        return build_plain_envelope(payload)
    return build_encrypted_envelope(payload, secure_channel)


def parse_envelope(raw: str | dict[str, Any]) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else _decode_json(raw)
    if not isinstance(payload, dict):
        raise SAMWireFormatError("Envelope payload must be a JSON object")
    if payload.get("schema") != WIRE_SCHEMA:
        raise SAMWireFormatError("Unknown envelope schema")

    mode = payload.get("mode")
    if mode == PLAIN_MODE:
        body = payload.get("payload")
        if not isinstance(body, dict):
            raise SAMWireFormatError("Plain envelope payload must be a JSON object")
    elif mode == ENCRYPTED_MODE:
        _require_string(payload, "ciphertext")
    else:
        raise SAMWireFormatError("Envelope mode must be plain or encrypted")

    return payload


def decode_message(
    envelope: str | dict[str, Any],
    *,
    secure_channel: SecureChannel | None = None,
) -> dict[str, Any]:
    parsed = parse_envelope(envelope)
    if parsed["mode"] == PLAIN_MODE:
        return parsed["payload"]

    if secure_channel is None:
        raise SAMWireFormatError("SecureChannel is required to decrypt this envelope")

    plaintext = secure_channel.decrypt(_require_string(parsed, "ciphertext"))
    payload = _decode_json(plaintext)
    if not isinstance(payload, dict):
        raise SAMWireFormatError("Decrypted payload must be a JSON object")
    return payload


decode_envelope = decode_message


async def generate_sam_identity(
    *,
    sam_host: str = SAM_HOST,
    sam_port: int = SAM_PORT,
) -> tuple[str, str]:
    reader, writer = await _open_sam_socket(sam_host, sam_port)
    try:
        await _sam_hello(reader, writer)
        writer.write(b"DEST GENERATE SIGNATURE_TYPE=7\n")
        await writer.drain()

        response = await reader.readline()
        text, fields = _parse_sam_line(response)
        public_destination = fields.get("PUB")
        private_destination = fields.get("PRIV")
        if not public_destination or not private_destination:
            raise SAMProtocolError(f"DEST GENERATE failed: {text}")
        return public_destination, private_destination
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def _open_sam_socket(
    host: str,
    port: int,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_connection(host, port)


async def _sam_hello(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.write(SAM_HELLO)
    await writer.drain()
    response = await reader.readline()
    text, fields = _parse_sam_line(response)
    if fields.get("RESULT") != "OK":
        raise SAMProtocolError(f"SAM handshake failed: {text}")


def _pack_envelope(envelope: dict[str, Any]) -> bytes:
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


def _parse_sam_line(raw_line: bytes) -> tuple[str, dict[str, str]]:
    text = raw_line.decode().strip()
    if not text:
        raise SAMProtocolError("SAM closed the socket without a response")

    fields: dict[str, str] = {}
    for token in shlex.split(text):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value
    return text, fields


def _decode_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SAMWireFormatError("Payload is not valid JSON") from exc


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SAMWireFormatError(f"{key} must be a non-empty string")
    return value


def _require_int(payload: dict[str, Any], key: str, *, default: int | None = None) -> int:
    value = payload.get(key, default)
    if not isinstance(value, int):
        raise SAMWireFormatError(f"{key} must be an integer")
    return value


__all__ = [
    "ENCRYPTED_MODE",
    "PLAIN_MODE",
    "SAMError",
    "SAM_HOST",
    "SAMIdentity",
    "SAMIncomingPacket",
    "SAM_PORT",
    "SAMProtocolError",
    "SAMTransport",
    "SAMWireFormatError",
    "build_encrypted_envelope",
    "build_plain_envelope",
    "decode_envelope",
    "decode_message",
    "encode_message",
    "generate_sam_identity",
    "parse_envelope",
]
