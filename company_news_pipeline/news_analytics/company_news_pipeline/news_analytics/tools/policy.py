"""Outbound privacy filtering and public URL policy."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit


_PRIVATE_ID = re.compile(r"\b(?:SYNTHETIC_[A-Z]+|MOCK_[A-Z]+)_?[A-Z0-9_-]*\b", re.I)
_LONG_NUMERIC_ID = re.compile(r"\b\d{10,20}\b")
_MONEY = re.compile(r"\b\d[\d\s,.]*\s*(?:₽|руб(?:лей|ля)?|RUB|USD|EUR)\b", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)")


def sanitize_outbound_query(query: str) -> tuple[str, list[str]]:
    warnings = []
    sanitized = query
    for pattern, label in ((_PRIVATE_ID, "synthetic identifier"), (_LONG_NUMERIC_ID, "long numeric identifier"),
                           (_MONEY, "exact financial value"), (_EMAIL, "email address"), (_PHONE, "phone number")):
        new_value, count = pattern.subn(" ", sanitized)
        if count:
            warnings.append(f"Removed {label} from outbound query")
        sanitized = new_value
    sanitized = " ".join(sanitized.split())
    return sanitized, warnings


def validate_public_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Only public HTTP/HTTPS URLs are allowed")
    host = parts.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Local and private hosts are blocked")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))}
    except OSError as exc:
        raise ValueError("URL host could not be resolved") from exc
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise ValueError("Local, private, and reserved network addresses are blocked")
    return url
