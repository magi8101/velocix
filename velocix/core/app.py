"""
ASGI application with lifespan management
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from velocix.core.depends import get_plan_and_needs_request, resolve_dependencies
from velocix.core.exceptions import ErrorHandler, HTTPException, NotFound
from velocix.core.middleware import BaseMiddleware, build_middleware_stack
from velocix.core.request import Request
from velocix.core.response import JSONResponse, Response, StreamingResponse
from velocix.core.router import Router

# Type alias for response types
ResponseType = Response | JSONResponse | StreamingResponse

logger = logging.getLogger("velocix")


class State:
    """Application state container"""

    pass


def cache_response(ttl: float = 60.0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Cache a route's serialized JSON response body for `ttl` seconds.

    The cached value is the orjson-serialized body (the most expensive part
    of a JSON response), keyed by method + path + query string. Only safe for
    handlers whose output does not depend on per-request state (auth, headers,
    cookies); opt-in per route.

    Usage:
        @app.get("/items")
        @cache_response(ttl=60)
        async def items(request):
            return {"items": ITEMS}
    """

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        handler.__response_cache_ttl__ = ttl  # type: ignore[attr-defined]
        return handler

    return decorator


class Velocix:
    """Main ASGI application with cached middleware compilation"""

    __slots__ = (
        "router",
        "state",
        "_middleware_stack",
        "_exception_handlers",
        "_error_handler",
        "_startup_handlers",
        "_shutdown_handlers",
        "_background_tasks",
        "_compiled_middleware",
        "_startup_complete",
        "_response_cache",
    )

    def __init__(self, debug: bool = False) -> None:
        self.router = Router()
        self.state = State()
        self._middleware_stack: list[type[BaseMiddleware] | Callable[..., Any]] = []
        self._exception_handlers: dict[type[Exception], Any] = {}
        self._startup_handlers: list[Any] = []
        self._shutdown_handlers: list[Any] = []
        self._background_tasks: set[Any] = set()
        self._compiled_middleware: Any = None
        self._startup_complete: bool = False
        self._response_cache: dict[str, tuple[float, bytes, int]] = {}
        self._error_handler = ErrorHandler(debug=debug)

        self._setup_default_exception_handlers()

    def route(
        self, path: str, methods: set[str] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for adding routes"""

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            methods_set = methods or {"GET"}
            for method in methods_set:
                self.router.add_route(method, path, handler)
            return handler

        return decorator

    def get(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for GET routes"""
        return self.route(path, {"GET"})

    def post(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for POST routes"""
        return self.route(path, {"POST"})

    def put(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for PUT routes"""
        return self.route(path, {"PUT"})

    def delete(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for DELETE routes"""
        return self.route(path, {"DELETE"})

    def patch(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for PATCH routes"""
        return self.route(path, {"PATCH"})

    def websocket(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for WebSocket routes"""
        return self.route(path, {"WEBSOCKET"})

    def add_middleware(self, middleware_class: type[BaseMiddleware] | Callable[..., Any]) -> None:
        """Add middleware to stack"""
        self._middleware_stack.append(middleware_class)

    def add_exception_handler(
        self,
        exc_class: type[Exception],
        handler: Callable[[Request, Exception], Awaitable[ResponseType]],
    ) -> None:
        """Register exception handler"""
        self._exception_handlers[exc_class] = handler

    def on_startup(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """Register startup handler"""
        self._startup_handlers.append(func)
        return func

    def on_shutdown(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """Register shutdown handler"""
        self._shutdown_handlers.append(func)
        return func

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """ASGI entry point"""
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        elif scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)

    async def _handle_lifespan(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Handle ASGI lifespan events"""
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                try:
                    for handler in self._startup_handlers:
                        result = handler()
                        if asyncio.iscoroutine(result):
                            await result
                    self._startup_complete = True
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    logger.exception("Startup failed")
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})

            elif message["type"] == "lifespan.shutdown":
                try:
                    self._startup_complete = False
                    for task in self._background_tasks:
                        task.cancel()

                    await asyncio.gather(*self._background_tasks, return_exceptions=True)

                    for handler in self._shutdown_handlers:
                        result = handler()
                        if asyncio.iscoroutine(result):
                            await result

                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as exc:
                    logger.exception("Shutdown failed")
                    await send({"type": "lifespan.shutdown.failed", "message": str(exc)})
                break

    async def _handle_http(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Handle HTTP request"""
        request: Request | None = None
        try:
            handler, path_params = self.router.resolve(scope["method"], scope["path"])
            if handler is None:
                raise NotFound(f"Route not found: {scope['path']}")
            response = await self._process_request(scope, receive, handler, path_params)
        except Exception as exc:
            if request is None:
                request = Request(scope, receive)
                request.app = self
            response = await self._handle_exception(request, exc)

        await self._send_response(response, send)

    async def _handle_websocket(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Handle WebSocket connection"""
        from velocix.websocket.connection import WebSocket

        ws = WebSocket(scope, receive, send)

        try:
            handler, path_params = self.router.resolve("WEBSOCKET", ws.path)
        except Exception:
            handler, path_params = None, {}

        if handler is None:
            await send({"type": "websocket.close", "code": 1000})
            return

        ws.path_params = path_params

        try:
            await handler(ws)
        except Exception:
            logger.exception("WebSocket handler error")
            try:
                await ws.close(1011)
            except Exception:
                pass

    async def _process_request(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        handler: Callable[..., Any],
        path_params: dict[str, Any],
    ) -> ResponseType:
        """Process HTTP request with error handling and middleware"""
        request: Request | None = None
        try:
            if self._middleware_stack:
                if self._compiled_middleware is None:
                    self._compiled_middleware = build_middleware_stack(
                        self._execute_handler, self._middleware_stack
                    )

                # One plan lookup per request, stashed on the Request so the
                # middleware terminal re-reads it without another lookup.
                entry = get_plan_and_needs_request(handler)
                request = self._init_request(scope, receive, handler, path_params)
                request._plan = entry
                response = await self._compiled_middleware(request)
                # Middleware should return ResponseType, but type system sees Any
                if isinstance(response, (Response, JSONResponse, StreamingResponse)):
                    return response
                return JSONResponse(
                    {"error": "Invalid response type from middleware"}, status_code=500
                )

            # No middleware: pass everything explicitly so _execute_handler
            # never re-reads handler/plan/path_params off the Request.
            plan, needs_request, cache_ttl, call_mode = get_plan_and_needs_request(handler)
            if needs_request:
                request = self._init_request(scope, receive, handler, path_params)
                return await self._execute_handler(
                    request, scope, handler, path_params, plan, cache_ttl, call_mode
                )
            return await self._execute_handler(
                None, scope, handler, path_params, plan, cache_ttl, call_mode
            )

        except Exception as exc:
            if request is None:
                request = Request(scope, receive)
                request.app = self
            return await self._handle_exception(request, exc)

    def _init_request(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        handler: Callable[..., Any],
        path_params: dict[str, Any],
    ) -> Request:
        """Build a Request and attach the resolved handler/params"""
        request = Request(scope, receive)
        request.app = self
        request.path_params = path_params
        request._handler = handler
        return request

    async def _execute_handler(
        self,
        request: Request | None,
        scope: dict[str, Any] | None = None,
        handler: Callable[..., Any] | None = None,
        path_params: dict[str, Any] | None = None,
        plan: tuple[tuple[str, str, Any], ...] | None = None,
        cache_ttl: float | None = None,
        call_mode: int = 2,
    ) -> ResponseType:
        """Execute route handler with dependency injection"""
        if handler is None:
            # Called through the middleware stack with a real Request
            handler = request._handler  # type: ignore[union-attr]
            if handler is None:
                # Fallback for handlers invoked outside the normal request path
                handler, _ = self.router.resolve(request.method, request.path)  # type: ignore[union-attr]
                if handler is None:
                    raise NotFound()
            path_params = request.path_params  # type: ignore[union-attr]

        if plan is None:
            entry = getattr(request, "_plan", None) if request is not None else None
            if entry is None:
                entry = get_plan_and_needs_request(handler)
            plan, _, cache_ttl, call_mode = entry

        # Response cache hit: reuse the serialized body, skip handler + orjson.
        # method/path/query are only needed to build the cache key, so defer
        # extracting them until we know the route is actually cached.
        if cache_ttl is not None:
            if request is not None:
                method = request.method
                path = request.path
                query_string = request.query_string
            else:
                assert scope is not None
                method = scope["method"]
                path = scope["path"]
                query_string = scope["query_string"]
            cache_key = f"{method}:{path}?{query_string.decode('latin-1')}"
            cached = self._response_cache.get(cache_key)
            if cached is not None and cached[0] > time.time():
                return JSONResponse.from_body(cached[1], cached[2])

        if call_mode == 1:
            result = await handler(request)
        elif call_mode == 0:
            result = await handler()
        else:
            kwargs = await resolve_dependencies(handler, request, path_params, plan)
            result = await handler(**kwargs)

        # dict is the common case (JSON handlers), so check it first; JSONResponse
        # subclasses Response, so a single Response check covers both.
        if isinstance(result, dict):
            response: ResponseType = JSONResponse(result)
        elif isinstance(result, Response):
            response = result
        elif isinstance(result, StreamingResponse):
            response = result
        elif isinstance(result, str):
            response = Response(result, media_type="text/plain")
        elif result is None:
            response = Response(b"", status_code=204)
        else:
            response = JSONResponse(result)

        # Cache the serialized body only for dict/JSON responses
        if cache_ttl is not None and isinstance(response, JSONResponse):
            self._response_cache[cache_key] = (
                time.time() + cache_ttl,
                bytes(response.body),
                response.status_code,
            )

        return response

    async def _handle_exception(self, request: Request, exc: Exception) -> ResponseType:
        """Handle exceptions with registered handlers"""
        # Handle HTTPException first
        if isinstance(exc, HTTPException):
            return JSONResponse(
                exc.to_dict(), status_code=exc.status_code, headers=exc.headers or None
            )

        # Check custom handlers
        for exc_class, handler in self._exception_handlers.items():
            if isinstance(exc, exc_class):
                result = await handler(request, exc)
                if isinstance(result, (Response, JSONResponse, StreamingResponse)):
                    return result
                else:
                    return JSONResponse(
                        {"error": "Invalid response from exception handler"}, status_code=500
                    )

        # Log unhandled exceptions
        logger.exception("Unhandled exception")
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    async def _send_response(
        self,
        response: Response | StreamingResponse,
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Send response to ASGI server"""
        if isinstance(response, StreamingResponse):
            await send(
                {
                    "type": "http.response.start",
                    "status": response.status_code,
                    "headers": response.asgi_headers(),
                }
            )

            content_iterator = response.content
            if callable(content_iterator):
                content_iterator = content_iterator()

            async for chunk in content_iterator:
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )

            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                }
            )
        else:
            await send(
                {
                    "type": "http.response.start",
                    "status": response.status_code,
                    "headers": response.asgi_headers(),
                }
            )

            await send(
                {
                    "type": "http.response.body",
                    "body": response.body,
                    "more_body": False,
                }
            )

    def _setup_default_exception_handlers(self) -> None:
        """Setup default exception handlers"""
        pass

    def add_background_task(self, coro: Coroutine[Any, Any, None]) -> None:
        """Schedule background task"""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
