"""Logging, request tracing, and security header middleware.

Pure ASGI middleware is used here (rather than ``BaseHTTPMiddleware``) so
request/response bodies are streamed straight through without being buffered
into memory, and so headers can be injected onto every response -- including
ones raised from exception handlers -- by hooking the ASGI ``send`` callable
directly.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"

access_logger = logging.getLogger("app.access")


class JsonLogFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    # Standard attributes every LogRecord carries; anything else in
    # record.__dict__ was passed in via `extra=` and should be surfaced.
    _STANDARD_ATTRS = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self._STANDARD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(json_logs: bool) -> None:
    """Configure stdlib logging for the app process.

    When ``json_logs`` is True, all handlers on the root logger emit a single
    JSON object per line (suitable for log aggregators). Otherwise a plain
    human-readable format is used, which is friendlier for local development.
    """
    root = logging.getLogger()

    handler = logging.StreamHandler()
    if json_logs:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )

    root.handlers.clear()
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level == logging.WARNING:
        root.setLevel(logging.INFO)


class RequestLoggingMiddleware:
    """Pure ASGI middleware: request-id propagation + one access log line per request.

    Implemented as a class (rather than ``BaseHTTPMiddleware``) so it plugs
    straight into ``app.add_middleware(RequestLoggingMiddleware)`` and so
    request/response bodies are streamed through untouched -- only the ASGI
    ``send`` callable is wrapped to inject the response header and capture
    the status code for logging.
    """

    def __init__(
        self,
        app: ASGIApp,
        excluded_paths: frozenset[str] = frozenset({"/healthz"}),
    ) -> None:
        self.app = app
        self.excluded_paths = excluded_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming_request_id = headers.get(REQUEST_ID_HEADER)
        request_id = (
            incoming_request_id.decode("latin-1")
            if incoming_request_id
            else str(uuid.uuid4())
        )
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        path = scope.get("path", "")
        method = scope.get("method", "")
        start = time.perf_counter()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                raw_headers = list(message.get("headers", []))
                raw_headers.append((REQUEST_ID_HEADER, request_id.encode("latin-1")))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if path not in self.excluded_paths:
                duration_ms = (time.perf_counter() - start) * 1000
                access_logger.info(
                    "%s %s %s %.2fms",
                    method,
                    path,
                    status_holder.get("status", 0),
                    duration_ms,
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "status": status_holder.get("status", 0),
                        "duration_ms": round(duration_ms, 2),
                    },
                )


class SecurityHeadersMiddleware:
    """Pure ASGI middleware: adds standard security response headers.

    A class-based ASGI middleware (not ``BaseHTTPMiddleware``) so it applies
    uniformly to every response -- including ones generated by exception
    handlers -- without buffering the response body.
    """

    def __init__(self, app: ASGIApp, hsts_enabled: bool) -> None:
        self.app = app
        self.extra_headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
        ]
        if hsts_enabled:
            self.extra_headers.append(
                (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.extend(self.extra_headers)
                message["headers"] = raw_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
