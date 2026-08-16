"""
Middleware base class and optimized pipeline compilation.
Starlette-inspired middleware architecture with call_next pattern.
"""

import binascii
import json
from collections.abc import Awaitable, Callable
from typing import Any

import itsdangerous

from velocix.core.request import Request
from velocix.core.response import Response


class BaseMiddleware:
    """
    Base class for middleware (Starlette pattern).

    Middleware wraps the application and can:
    - Inspect/modify requests before handler
    - Inspect/modify responses after handler
    - Short-circuit request handling
    - Add context to request.state
    """

    __slots__ = ("app",)

    def __init__(self, app: Callable[[Request], Awaitable[Response]]) -> None:
        self.app = app

    async def __call__(self, request: Request) -> Response:
        """
        Process request through middleware chain.
        Override this method to implement custom middleware logic.
        """
        return await self.app(request)


class BaseHTTPMiddleware(BaseMiddleware):
    """
    HTTP middleware with dispatch pattern (like Starlette).

    Provides call_next() helper for clean middleware implementation.
    """

    async def __call__(self, request: Request) -> Response:
        """
        Call dispatch method with call_next helper.
        """

        async def call_next(req: Request) -> Response:
            """Call next middleware/handler in chain"""
            return await self.app(req)

        return await self.dispatch(request, call_next)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Override this method to implement middleware logic.

        Example:
            async def dispatch(self, request, call_next):
                # Before handler
                request.state.start_time = time.time()

                # Call handler
                response = await call_next(request)

                # After handler
                duration = time.time() - request.state.start_time
                response.headers['X-Process-Time'] = str(duration)

                return response
        """
        return await call_next(request)


def build_middleware_stack(
    handler: Callable[[Request], Awaitable[Any]],
    middlewares: list[type[BaseMiddleware] | Callable[..., Any]],
) -> Callable[[Request], Awaitable[Any]]:
    """
    Build and cache compiled middleware chain (Starlette pattern).

    Middlewares are applied in reverse order so that the first
    middleware in the list is the outermost layer.

    Example:
        middlewares = [Auth, CORS, Logging]
        # Execution order: Auth -> CORS -> Logging -> Handler
    """
    if not middlewares:
        return handler

    app = handler
    for middleware_class in reversed(middlewares):
        app = middleware_class(app)
    return app


class SessionMiddleware(BaseHTTPMiddleware):
    """
    Signed session middleware (Starlette pattern).

    Stores the session as a signed, timestamped JSON cookie. The session
    dict is exposed via ``request.session`` and is written back to the
    cookie only when it changes, so idle sessions expire naturally via
    ``max_age``. Tampered or expired cookies load as an empty session.

    Usage:
        app.add_middleware(partial(SessionMiddleware, secret_key="..."))

    Args:
        app: Next middleware/handler in the chain
        secret_key: Key used to sign session cookies (keep secret!)
        session_cookie: Cookie name (default: "session")
        max_age: Session lifetime in seconds (default: 14 days)
        path: Cookie path (default: "/")
        same_site: SameSite policy: strict | lax | none (default: lax)
        https_only: Only send the cookie over HTTPS (default: False)
        domain: Cookie domain (default: None -> host only)
    """

    def __init__(
        self,
        app: Callable[[Request], Awaitable[Response]],
        secret_key: str,
        session_cookie: str = "session",
        max_age: int = 14 * 24 * 3600,
        path: str = "/",
        same_site: str = "lax",
        https_only: bool = False,
        domain: str | None = None,
    ):
        super().__init__(app)
        self.signer = itsdangerous.TimestampSigner(str(secret_key))
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.path = path
        self.same_site = same_site
        self.https_only = https_only
        self.domain = domain

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Load the session before the handler, write it back after."""
        initial_session_was_empty = True
        initial_session: dict[str, Any] = {}
        cookie = request.cookies.get(self.session_cookie)
        if cookie:
            try:
                data = self.signer.unsign(cookie.encode("utf-8"), max_age=self.max_age)
                session = json.loads(data)
                if isinstance(session, dict):
                    initial_session = dict(session)
                    initial_session_was_empty = False
                else:
                    session = {}
            except (itsdangerous.BadSignature, binascii.Error, json.JSONDecodeError):
                # Tampered, expired, or malformed cookie -> start fresh
                session = {}
        else:
            session = {}
        request.session = session

        response = await call_next(request)

        # Re-read the session: handlers may rebind request.session
        session = request._session or {}

        if session and initial_session_was_empty:
            # Session was created during this request
            response.set_cookie(
                self.session_cookie,
                self.signer.sign(json.dumps(session).encode("utf-8")).decode("utf-8"),
                max_age=self.max_age,
                path=self.path,
                domain=self.domain,
                secure=self.https_only,
                httponly=True,
                samesite=self.same_site,
            )
        elif session and not initial_session_was_empty:
            # Rewrite only when the session changed, so idle sessions expire
            if session != initial_session:
                response.set_cookie(
                    self.session_cookie,
                    self.signer.sign(json.dumps(session).encode("utf-8")).decode("utf-8"),
                    max_age=self.max_age,
                    path=self.path,
                    domain=self.domain,
                    secure=self.https_only,
                    httponly=True,
                    samesite=self.same_site,
                )
        elif not session and not initial_session_was_empty:
            # Session was cleared during this request
            response.delete_cookie(self.session_cookie, path=self.path, domain=self.domain)

        return response


class CORSMiddleware(BaseHTTPMiddleware):
    """
    CORS middleware (Starlette-inspired).

    Handles Cross-Origin Resource Sharing headers.
    """

    def __init__(
        self,
        app: Callable[[Request], Awaitable[Response]],
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        allow_credentials: bool = False,
        expose_headers: list[str] | None = None,
        max_age: int = 600,
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers or []
        self.max_age = max_age

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Add CORS headers to response"""
        # Handle preflight requests
        if request.method == "OPTIONS":
            response = Response(b"", status_code=200)
        else:
            response = await call_next(request)

        # Add CORS headers
        origin = request.headers.get(b"origin", b"").decode("latin-1")

        if "*" in self.allow_origins or origin in self.allow_origins:
            response.raw_headers.append(
                (b"access-control-allow-origin", origin.encode("latin-1") or b"*")
            )

        if self.allow_credentials:
            response.raw_headers.append((b"access-control-allow-credentials", b"true"))

        if request.method == "OPTIONS":
            methods = ", ".join(self.allow_methods)
            headers = ", ".join(self.allow_headers)

            response.raw_headers.extend(
                [
                    (b"access-control-allow-methods", methods.encode("latin-1")),
                    (b"access-control-allow-headers", headers.encode("latin-1")),
                    (b"access-control-max-age", str(self.max_age).encode("latin-1")),
                ]
            )

        if self.expose_headers:
            exposed = ", ".join(self.expose_headers)
            response.raw_headers.append(
                (b"access-control-expose-headers", exposed.encode("latin-1"))
            )

        return response


class TrustedHostMiddleware(BaseHTTPMiddleware):
    """
    Validate Host header (Starlette pattern).
    Prevents HTTP Host header attacks.
    """

    def __init__(
        self, app: Callable[[Request], Awaitable[Response]], allowed_hosts: list[str] | None = None
    ):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts or ["*"]

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Validate host header"""
        if "*" in self.allowed_hosts:
            return await call_next(request)

        host = request.headers.get(b"host", b"").decode("latin-1")

        # Remove port if present
        if ":" in host:
            host = host.split(":")[0]

        if host not in self.allowed_hosts:
            return Response(b"Invalid host header", status_code=400)

        return await call_next(request)


class GZipMiddleware(BaseHTTPMiddleware):
    """
    GZip compression middleware (Starlette-inspired).
    Compresses responses if client supports it.
    """

    def __init__(
        self,
        app: Callable[[Request], Awaitable[Response]],
        minimum_size: int = 500,
        compresslevel: int = 9,
    ):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Compress response if applicable"""
        import gzip

        # Check if client accepts gzip
        accept_encoding = request.headers.get(b"accept-encoding", b"").decode("latin-1")
        if "gzip" not in accept_encoding.lower():
            return await call_next(request)

        response = await call_next(request)

        # Skip responses without a body (streaming/file/SSE) and already-encoded responses
        if not hasattr(response, "body"):
            return response

        if any(k == b"content-encoding" for k, v in response.raw_headers):
            return response

        # Only compress if body is large enough
        if len(response.body) < self.minimum_size:
            return response

        # Compress body
        compressed = gzip.compress(response.body, compresslevel=self.compresslevel)

        # Only keep if compression actually helped
        if len(compressed) >= len(response.body):
            return response

        # Update response
        response.body = compressed
        response.raw_headers = [(k, v) for k, v in response.raw_headers if k != b"content-length"]
        response.raw_headers.extend(
            [
                (b"content-encoding", b"gzip"),
                (b"content-length", str(len(compressed)).encode("latin-1")),
                (b"vary", b"Accept-Encoding"),
            ]
        )

        return response
