from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "i2pd.conf"


@dataclass(frozen=True, slots=True)
class I2PDConfig:
    sam_host: str = "127.0.0.1"
    sam_port: int = 7656
    http_host: str = "127.0.0.1"
    http_port: int = 7070
    router_port: int | None = None
    ntcp2_port: int | None = None
    ssu2_port: int | None = None

    def incoming_tcp_port(self, fallback: int | None = None) -> int | None:
        return self.ntcp2_port or self.router_port or fallback

    def incoming_udp_port(self, fallback: int | None = None) -> int | None:
        return self.ssu2_port or self.router_port or fallback


def load_i2pd_config(path: str | Path | None = None) -> I2PDConfig:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return I2PDConfig()

    sam_host = "127.0.0.1"
    sam_port = 7656
    http_host = "127.0.0.1"
    http_port = 7070
    router_port: int | None = None
    ntcp2_port: int | None = None
    ssu2_port: int | None = None
    current_section: str | None = None

    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip().lower()
            continue
        if "=" not in line:
            continue

        key, value = (part.strip() for part in line.split("=", 1))
        value = _strip_inline_comment(value)
        if not value:
            continue

        section = current_section or ""
        if section == "":
            if key == "port":
                router_port = _parse_int(value, router_port)
            continue

        if section == "sam":
            if key == "address":
                sam_host = value
            elif key == "port":
                sam_port = _parse_int(value, sam_port)
            continue

        if section == "http":
            if key == "address":
                http_host = value
            elif key == "port":
                http_port = _parse_int(value, http_port)
            continue

        if section == "ntcp2" and key == "port":
            ntcp2_port = _parse_int(value, ntcp2_port)
            continue

        if section == "ssu2" and key == "port":
            ssu2_port = _parse_int(value, ssu2_port)

    return I2PDConfig(
        sam_host=sam_host,
        sam_port=sam_port,
        http_host=http_host,
        http_port=http_port,
        router_port=router_port,
        ntcp2_port=ntcp2_port,
        ssu2_port=ssu2_port,
    )


def _strip_inline_comment(value: str) -> str:
    for marker in (" #", " ;"):
        if marker in value:
            value = value.split(marker, 1)[0]
    return value.strip()


def _parse_int(value: str, default: int | None) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return default


__all__ = ["DEFAULT_CONFIG_PATH", "I2PDConfig", "load_i2pd_config"]
