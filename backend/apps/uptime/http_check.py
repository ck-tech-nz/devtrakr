import time
from dataclasses import dataclass
from typing import Optional
import requests

from apps.uptime.url_safety import check_url_safety


# Cap the bytes we read off the wire for body matching to avoid OOMing the worker
# on a monitored URL that happens to stream a large response.
MAX_BODY_BYTES = 256 * 1024  # 256 KB is plenty for a health check JSON


@dataclass
class CheckResult:
    is_up: bool
    status_code: Optional[int]
    response_ms: Optional[int]
    error: str


def _parse_expected_status(expected: str) -> list[int]:
    return [int(s.strip()) for s in expected.split(",") if s.strip()]


def _read_capped_body(resp: requests.Response, cap: int = MAX_BODY_BYTES) -> str:
    """Read at most `cap` bytes from the streaming response and decode as text."""
    buf = bytearray()
    for chunk in resp.iter_content(chunk_size=4096, decode_unicode=False):
        if not chunk:
            continue
        buf.extend(chunk)
        if len(buf) >= cap:
            break
    encoding = resp.encoding or "utf-8"
    try:
        return buf[:cap].decode(encoding, errors="replace")
    except LookupError:
        return buf[:cap].decode("utf-8", errors="replace")


def perform_check(monitor) -> CheckResult:
    expected_codes = _parse_expected_status(monitor.expected_status)

    # Re-verify URL safety right before the request to catch DNS changes since
    # the monitor was created (TOCTOU mitigation, not airtight).
    safe, reason = check_url_safety(monitor.url)
    if not safe:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error=reason)

    start = time.monotonic()
    try:
        resp = requests.get(monitor.url, timeout=monitor.timeout_secs, stream=True)
    except requests.exceptions.Timeout:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error="timeout")
    except requests.exceptions.ConnectionError:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error="connection error")
    except requests.exceptions.RequestException as exc:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error=str(exc)[:200])

    try:
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code not in expected_codes:
            return CheckResult(
                is_up=False, status_code=resp.status_code,
                response_ms=elapsed_ms, error=f"status {resp.status_code}",
            )

        if monitor.expected_body:
            body = _read_capped_body(resp)
            if monitor.expected_body not in body:
                return CheckResult(
                    is_up=False, status_code=resp.status_code,
                    response_ms=elapsed_ms, error="body mismatch",
                )

        return CheckResult(
            is_up=True, status_code=resp.status_code,
            response_ms=elapsed_ms, error="",
        )
    finally:
        resp.close()
