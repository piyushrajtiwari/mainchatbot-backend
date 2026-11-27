"""HTTP concerns shared by all API routes, without buffering chat streams."""

import logging
from time import perf_counter
from uuid import uuid4
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("mainchatbot.requests")
DOC_PATHS = {"/docs", "/redoc", "/docs/oauth2-redirect"}


class CoreMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        response_started = False
        status_code = 500

        async def send_response(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Process-Time"] = f"{perf_counter() - started:.6f}"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                if scope["path"] not in DOC_PATHS:
                    headers["Content-Security-Policy"] = (
                        "default-src 'self'; script-src 'self'; "
                        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
                    )
                if scope["path"] == "/auth" or scope["path"].startswith("/auth/"):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        except Exception:
            # Never leak exception strings, credentials, or reset tokens to clients/logs.
            logger.error("Unhandled request failure request_id=%s", request_id)
            if response_started:
                raise  # A streaming response cannot be replaced after its headers.
            response = JSONResponse(
                {"detail": "Internal server error", "request_id": request_id},
                status_code=500,
            )
            await response(scope, receive, send_response)
        finally:
            # Do not log query strings, bodies, cookies, or authorization headers.
            logger.info(
                "request_id=%s method=%s status=%s duration_ms=%.2f",
                request_id, scope["method"], status_code,
                (perf_counter() - started) * 1000,
            )


def configure_middleware(
    app: FastAPI, *, origins: list[str], frontend_url: str | None = None
) -> None:
    """Register once, before startup. CORS wraps core errors as well as successes."""
    allowed_origins = list(origins)
    if frontend_url:
        parsed = urlsplit(frontend_url)
        allowed_origins.append(f"{parsed.scheme}://{parsed.netloc}")
    normalized = list(dict.fromkeys(origin.rstrip("/") for origin in allowed_origins))
    for origin in normalized:
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password or "*" in origin):
            raise ValueError("CORS origins must be explicit HTTP(S) origins without paths or credentials")
    app.add_middleware(CoreMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=normalized,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "Authorization"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
        max_age=600,
    )
