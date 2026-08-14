"""
Middleware base class and optimized pipeline compilation.
Starlette-inspired middleware architecture with call_next pattern.
"""
from typing import Any, Callable, Awaitable, Optional
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
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
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
    handler: Callable[[Request], Awaitable[Response]],
    middlewares: list[type[BaseMiddleware]]
) -> Callable[[Request], Awaitable[Response]]:
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
        max_age: int = 600
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers or []
        self.max_age = max_age
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
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
            
            response.raw_headers.extend([
                (b"access-control-allow-methods", methods.encode("latin-1")),
                (b"access-control-allow-headers", headers.encode("latin-1")),
                (b"access-control-max-age", str(self.max_age).encode("latin-1"))
            ])
        
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
        self,
        app: Callable[[Request], Awaitable[Response]],
        allowed_hosts: list[str] | None = None
    ):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts or ["*"]
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Validate host header"""
        if "*" in self.allowed_hosts:
            return await call_next(request)
        
        host = request.headers.get(b"host", b"").decode("latin-1")
        
        # Remove port if present
        if ":" in host:
            host = host.split(":")[0]
        
        if host not in self.allowed_hosts:
            return Response(
                b"Invalid host header",
                status_code=400
            )
        
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
        compresslevel: int = 9
    ):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
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
        response.raw_headers = [
            (k, v) for k, v in response.raw_headers
            if k != b"content-length"
        ]
        response.raw_headers.extend([
            (b"content-encoding", b"gzip"),
            (b"content-length", str(len(compressed)).encode("latin-1")),
            (b"vary", b"Accept-Encoding")
        ])
        
        return response
