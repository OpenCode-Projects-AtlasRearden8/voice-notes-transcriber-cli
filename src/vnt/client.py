"""Minimal HTTP helpers built on urllib (no third-party dependencies).

Only ever talks to plain, keyless HTTP endpoints. No authorization
headers are set, no keys are stored or sent.
"""

from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request


class ClientError(Exception):
    """Raised for network-level failures (DNS, refused connection, timeout)."""


def request(method: str, url: str, *, data: bytes | None = None,
            headers: dict[str, str] | None = None,
            timeout: float = 60.0) -> tuple[int, bytes]:
    """Perform an HTTP request, returning (status, body).

    HTTP error statuses (4xx/5xx) are returned normally; only transport
    failures raise :class:`ClientError`.
    """
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # server answered with an error code
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ClientError(f"{url}: {exc}") from exc


def post_json(url: str, payload: dict, *, timeout: float = 120.0) -> tuple[int, bytes]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(payload).encode("utf-8")
    return request("POST", url, data=data, headers=headers, timeout=timeout)


def get_json(url: str, *, timeout: float = 15.0) -> tuple[int, bytes]:
    headers = {"Accept": "application/json"}
    return request("GET", url, headers=headers, timeout=timeout)


def post_multipart(
    url: str,
    fields: dict[str, str],
    filename: str,
    content: bytes,
    content_type: str,
    *,
    timeout: float = 600.0,
) -> tuple[int, bytes]:
    """POST multipart/form-data (used by /v1/audio/transcriptions)."""
    boundary = f"vnt-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                f"\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n"
            f"\r\n"
        ).encode("utf-8")
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("ascii"))
    body = b"".join(parts)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    }
    return request("POST", url, data=body, headers=headers, timeout=timeout)
