"""
ASGI application with lifespan management
"""
import asyncio
import logging
from typing import Any, Callable, Awaitable, Union, Coroutine

from velocix.core.router import Router
from velocix.core.request import Request
from velocix.core.response import Response, JSONResponse, StreamingResponse
from velocix.core.exceptions import HTTPException, NotFound, MethodNotAllowed, ErrorHandler
from velocix.core.depends import resolve_dependencies
from velocix.core.middleware import BaseMiddleware, build_middleware_stack

# Type alias for response types
ResponseType = Union[Response, JSONResponse, StreamingResponse]

logger = logging.getLogger("velocix")


class State:
    """Application state container"""
    pass


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
        "_startup_complete"
    )
    
    def __init__(self, debug: bool = False) -> None:
        self.router = Router()
        self.state = State()
        self._middleware_stack: list[type[BaseMiddleware]] = []
        self._exception_handlers: dict[type[Exception], Any] = {}
        self._startup_handlers: list[Any] = []
        self._shutdown_handlers: list[Any] = []
        self._background_tasks: set[Any] = set()
        self._compiled_middleware: Any = None
        self._startup_complete: bool = False
        self._error_handler = ErrorHandler(debug=debug)
        
        self._setup_default_exception_handlers()
    
    def route(
        self,
        path: str,
        methods: set[str] | None = None
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
    
    def add_middleware(self, middleware_class: type[BaseMiddleware]) -> None:
        """Add middleware to stack"""
        self._middleware_stack.append(middleware_class)
    
    def add_exception_handler(
        self,
        exc_class: type[Exception],
        handler: Callable[[Request, Exception], Awaitable[ResponseType]]
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
        send: Callable[[dict[str, Any]], Awaitable[None]]
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
        send: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Handle ASGI lifespan events"""
        while True:
            message = await receive()
            
            if message["type"] == "lifespan.startup":
                try:
                    for handler in self._startup_handlers:
                        await handler()
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
                        await handler()
                    
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as exc:
                    logger.exception("Shutdown failed")
                    await send({"type": "lifespan.shutdown.failed", "message": str(exc)})
                break
    
    async def _handle_http(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Handle HTTP request"""
        request = Request(scope, receive)
        request.app = self
        
        try:
            response = await self._process_request(request)
        except Exception as exc:
            response = await self._handle_exception(request, exc)
        
        await self._send_response(response, send)
    
    async def _handle_websocket(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]]
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
        except Exception as exc:
            logger.exception("WebSocket handler error")
            try:
                await ws.close(1011)
            except Exception:
                pass
    
    async def _process_request(self, request: Request) -> ResponseType:
        """Process HTTP request with error handling and middleware"""
        try:
            handler, path_params = self.router.resolve(request.method, request.path)
            
            if handler is None:
                raise NotFound(f"Route not found: {request.path}")
            
            request.path_params = path_params
            
            if self._compiled_middleware is None:
                self._compiled_middleware = build_middleware_stack(
                    self._execute_handler,
                    self._middleware_stack
                )
            
            response = await self._compiled_middleware(request)
            # Middleware should return ResponseType, but type system sees Any
            if isinstance(response, (Response, JSONResponse, StreamingResponse)):
                return response
            else:
                return JSONResponse({"error": "Invalid response type from middleware"}, status_code=500)
        
        except Exception as exc:
            return await self._handle_exception(request, exc)
    
    async def _execute_handler(self, request: Request) -> ResponseType:
        """Execute route handler with dependency injection"""
        handler, _ = self.router.resolve(request.method, request.path)
        
        if handler is None:
            raise NotFound()
        
        kwargs = await resolve_dependencies(handler, request, request.path_params)
        
        result = await handler(**kwargs)
        
        if isinstance(result, (Response, JSONResponse, StreamingResponse)):
            return result
        elif isinstance(result, dict):
            return JSONResponse(result)
        elif isinstance(result, str):
            return Response(result, media_type="text/plain")
        elif result is None:
            return Response(b"", status_code=204)
        else:
            return JSONResponse(result)
    
    async def _handle_exception(self, request: Request, exc: Exception) -> ResponseType:
        """Handle exceptions with registered handlers"""
        # Handle HTTPException first
        if isinstance(exc, HTTPException):
            return JSONResponse(
                exc.to_dict(),
                status_code=exc.status_code
            )
        
        # Check custom handlers
        for exc_class, handler in self._exception_handlers.items():
            if isinstance(exc, exc_class):
                result = await handler(request, exc)
                if isinstance(result, (Response, JSONResponse, StreamingResponse)):
                    return result
                else:
                    return JSONResponse({"error": "Invalid response from exception handler"}, status_code=500)
        
        # Log unhandled exceptions
        logger.exception("Unhandled exception")
        return JSONResponse(
            {"error": "Internal server error"},
            status_code=500
        )
    
    async def _send_response(self, response: Response | StreamingResponse, send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Send response to ASGI server"""
        if isinstance(response, StreamingResponse):
            await send({
                "type": "http.response.start",
                "status": response.status_code,
                "headers": [
                    (k.encode(), v.encode())
                    for k, v in response.headers.items()
                ],
            })
            
            content_iterator = response.content
            if callable(content_iterator):
                content_iterator = content_iterator()
            
            async for chunk in content_iterator:
                await send({
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": True,
                })
            
            await send({
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            })
        else:
            await send({
                "type": "http.response.start",
                "status": response.status_code,
                "headers": [
                    (k.encode(), v.encode())
                    for k, v in response.headers.items()
                ],
            })
            
            await send({
                "type": "http.response.body",
                "body": response.body,
                "more_body": False,
            })
    

    
    def _setup_default_exception_handlers(self) -> None:
        """Setup default exception handlers"""
        pass
    
    def add_background_task(self, coro: Coroutine[Any, Any, None]) -> None:
        """Schedule background task"""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
