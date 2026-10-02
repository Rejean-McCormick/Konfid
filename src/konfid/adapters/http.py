from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from ..config import get_settings


class UpstreamUnavailable(RuntimeError):
    pass


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None
    half_open: bool = False


_CIRCUITS: dict[str, _CircuitState] = {}
_CLIENTS: dict[tuple, httpx.Client] = {}
_LOCK = threading.RLock()


def _shared_client(base_url: str, timeout: httpx.Timeout, verify, cert) -> httpx.Client:
    # Reuse connection pools across adapter instances. The client carries no
    # credentials; Authorization headers are supplied per request.
    key = (
        base_url,
        timeout.connect,
        timeout.read,
        timeout.write,
        timeout.pool,
        str(verify),
        str(cert),
    )
    with _LOCK:
        client = _CLIENTS.get(key)
        if client is None:
            client = httpx.Client(
                base_url=base_url,
                timeout=timeout,
                verify=verify,
                cert=cert,
                follow_redirects=False,
                trust_env=False,
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30,
                ),
            )
            _CLIENTS[key] = client
        return client


def close_http_clients() -> None:
    with _LOCK:
        clients = list(_CLIENTS.values())
        _CLIENTS.clear()
    for client in clients:
        try:
            client.close()
        except Exception:
            pass


class JsonHttpAdapter:
    def __init__(self, base_url: str, bearer_token: str | None = None, default_headers: dict | None = None):
        self.base_url = base_url.rstrip("/") + "/"
        self.bearer_token = bearer_token
        s = get_settings()
        self.headers = {"User-Agent": f"Konfid/{s.version}", **dict(default_headers or {})}
        self.timeout = httpx.Timeout(
            connect=s.http_connect_timeout_seconds,
            read=s.http_read_timeout_seconds,
            write=s.http_write_timeout_seconds,
            pool=s.http_pool_timeout_seconds,
        )
        self.max_response_bytes = s.http_max_response_bytes
        self.retry_attempts = s.http_retry_attempts
        self.retry_base = s.http_retry_base_seconds
        self.failure_threshold = s.http_circuit_failure_threshold
        self.reset_seconds = s.http_circuit_reset_seconds
        self.verify = s.outbound_ca_bundle or True
        self.cert = (
            (s.outbound_client_cert_file, s.outbound_client_key_file)
            if s.outbound_client_cert_file and s.outbound_client_key_file
            else None
        )
        self.client = _shared_client(self.base_url, self.timeout, self.verify, self.cert)

    def _circuit_allow(self) -> None:
        now = time.monotonic()
        with _LOCK:
            state = _CIRCUITS.setdefault(self.base_url, _CircuitState())
            if state.opened_at is not None:
                if now - state.opened_at < self.reset_seconds:
                    raise UpstreamUnavailable("UPSTREAM_CIRCUIT_OPEN")
                # Permit exactly one half-open probe after the reset period.
                state.opened_at = None
                state.failures = 0
                state.half_open = True
                return
            if state.half_open:
                raise UpstreamUnavailable("UPSTREAM_CIRCUIT_HALF_OPEN")

    def _success(self) -> None:
        with _LOCK:
            state = _CIRCUITS.setdefault(self.base_url, _CircuitState())
            state.failures = 0
            state.opened_at = None
            state.half_open = False

    def _failure(self) -> None:
        with _LOCK:
            state = _CIRCUITS.setdefault(self.base_url, _CircuitState())
            if state.half_open:
                # A failed probe immediately re-opens the circuit.
                state.half_open = False
                state.failures = self.failure_threshold
                state.opened_at = time.monotonic()
                return
            state.failures += 1
            if state.failures >= self.failure_threshold:
                state.opened_at = time.monotonic()

    def _read_json_response(self, response: httpx.Response) -> dict:
        declared = response.headers.get("content-length")
        if declared:
            try:
                if int(declared) > self.max_response_bytes:
                    raise UpstreamUnavailable("UPSTREAM_RESPONSE_TOO_LARGE")
            except ValueError:
                raise UpstreamUnavailable("UPSTREAM_CONTENT_LENGTH_INVALID")

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > self.max_response_bytes:
                raise UpstreamUnavailable("UPSTREAM_RESPONSE_TOO_LARGE")
            chunks.append(chunk)
        body = b"".join(chunks)
        if not body:
            return {}

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json" and not content_type.endswith("+json"):
            raise UpstreamUnavailable("UPSTREAM_CONTENT_TYPE_INVALID")
        try:
            value = json.loads(body)
        except json.JSONDecodeError as exc:
            raise UpstreamUnavailable("UPSTREAM_JSON_INVALID") from exc
        if not isinstance(value, dict):
            raise UpstreamUnavailable("UPSTREAM_JSON_OBJECT_REQUIRED")
        return value

    def post(self, path: str, payload: dict, headers: dict | None = None, *, idempotent: bool = False):
        if not path.startswith("/"):
            raise ValueError("adapter path must be absolute")
        self._circuit_allow()
        merged = dict(self.headers)
        if self.bearer_token:
            merged["Authorization"] = f"Bearer {self.bearer_token}"
        merged.update(headers or {})
        safe_to_retry = idempotent or "Idempotency-Key" in merged
        attempts = self.retry_attempts if safe_to_retry else 1
        # urljoin is retained to normalize the adapter path. The shared client's
        # base_url keeps connection pooling scoped to the intended authority.
        url = urljoin(self.base_url, path.lstrip("/"))
        last_exc: Exception | None = None

        for attempt in range(attempts):
            try:
                # Stream the response so a malicious or broken upstream cannot
                # force an unbounded allocation before max_response_bytes is checked.
                with self.client.stream("POST", url, json=payload, headers=merged) as response:
                    if response.status_code in {429, 502, 503, 504} and attempt + 1 < attempts:
                        raise UpstreamUnavailable(f"UPSTREAM_RETRYABLE_{response.status_code}")
                    response.raise_for_status()
                    result = self._read_json_response(response)
                self._success()
                return result
            except (httpx.TimeoutException, httpx.NetworkError, UpstreamUnavailable) as exc:
                last_exc = exc
                if attempt + 1 >= attempts:
                    self._failure()
                    break
                delay = self.retry_base * (2**attempt) + random.uniform(0, self.retry_base)
                time.sleep(delay)
            except httpx.HTTPStatusError as exc:
                self._failure()
                # Never include upstream response bodies in errors: they may be sensitive.
                raise UpstreamUnavailable(f"UPSTREAM_HTTP_{exc.response.status_code}") from exc
            except Exception as exc:
                self._failure()
                raise UpstreamUnavailable("UPSTREAM_PROTOCOL_ERROR") from exc
        raise UpstreamUnavailable("UPSTREAM_UNAVAILABLE") from last_exc
