from __future__ import annotations

import asyncio
import contextlib
import re
import urllib.error
import urllib.request
from html import unescape

from rich.text import Text


async def collect_i2p_status() -> dict[str, str]:
    zero_metrics = zero_i2p_status()
    sam_ok = await _check_sam()
    html = await asyncio.to_thread(_fetch_http_page)

    if not sam_ok or not html:
        zero_metrics["summary"] = "Состояние: подключения нет"
        return zero_metrics

    metrics = _parse_metrics(html)
    metrics["summary"] = "Состояние: подключение есть"
    return metrics


def format_i2p_header(status: dict[str, str]) -> Text:
    tqsr_value = status["tunnel_success_rate"]
    routers_value = status["routers"]
    floodfills_value = status["floodfills"]
    header = Text()
    header.append(
        f"TQSR {tqsr_value}",
        style=_tqsr_style(tqsr_value),
    )
    header.append(f" | Received {status['received']}")
    header.append(f" | Sent {status['sent']}")
    header.append(" | ")
    header.append(
        f"Routers {routers_value}",
        style=_routers_style(routers_value),
    )
    header.append(" | ")
    header.append(
        f"Floodfills {floodfills_value}",
        style=_floodfills_style(floodfills_value),
    )
    return header


def zero_i2p_status() -> dict[str, str]:
    return {
        "summary": "Состояние: подключения нет",
        "connected": "0",
        "tunnel_success_rate": "0",
        "received": "0",
        "sent": "0",
        "routers": "0",
        "floodfills": "0",
        "leasesets": "0",
        "online_check": "0",
    }


async def _check_sam() -> bool:
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", 7656),
            timeout=2.0,
        )
        writer.write(b"HELLO VERSION MIN=3.1 MAX=3.1\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        return b"RESULT=OK" in line
    except Exception:
        return False
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()


def _fetch_http_page() -> str | None:
    for url in ("http://127.0.0.1:7070/stats", "http://127.0.0.1:7070/"):
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return None


def _parse_metrics(html: str) -> dict[str, str]:
    text = _normalize_html_text(html)
    return {
        "summary": "Состояние: подключение есть",
        "connected": "1",
        "tunnel_success_rate": _find_value(
            text,
            (
                r"Tunnel creation success rate[^0-9%]*([0-9]+(?:\.[0-9]+)?\s*%?)",
                r"tunnel.*success.*?([0-9]+(?:\.[0-9]+)?\s*%?)",
            ),
        ),
        "received": _find_transfer_rate(text, ("Received", "RX")),
        "sent": _find_transfer_rate(text, ("Sent", "TX")),
        "routers": _find_value(text, (r"Routers[^0-9]*([0-9][0-9,\s]*)",)),
        "floodfills": _find_value(text, (r"Floodfills[^0-9]*([0-9][0-9,\s]*)",)),
        "leasesets": _find_value(text, (r"LeaseSets[^0-9]*([0-9][0-9,\s]*)",)),
        "online_check": "0",
    }


def _normalize_html_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _find_transfer_rate(text: str, labels: tuple[str, ...]) -> str:
    unit_pattern = r"(?:[KMGTPE]?i?B/s|B/s)"
    for label in labels:
        escaped_label = re.escape(label)
        patterns = (
            rf"{escaped_label}\s*:?\s*[^(]*\(([0-9]+(?:\.[0-9]+)?\s*{unit_pattern})\)",
            rf"{escaped_label}\s*:?\s*([0-9]+(?:\.[0-9]+)?\s*{unit_pattern})",
        )
        value = _find_value(text, patterns)
        if value != "0":
            return value
    return "0"


def _find_value(text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return "0"


def _tqsr_style(value: str) -> str:
    normalized = value.strip().replace("%", "").replace(",", ".")
    try:
        percent = float(normalized)
    except ValueError:
        return ""

    if percent < 20:
        return "red"
    if percent < 50:
        return "yellow"
    return "green"


def _routers_style(value: str) -> str:
    count = _parse_int_metric(value)
    if count is None:
        return ""
    if count < 200:
        return "red"
    if count < 600:
        return "yellow"
    return "green"


def _floodfills_style(value: str) -> str:
    count = _parse_int_metric(value)
    if count is None:
        return ""
    if count < 100:
        return "red"
    if count < 300:
        return "yellow"
    return "green"


def _parse_int_metric(value: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", value)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None
