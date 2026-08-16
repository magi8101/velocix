"""
HTTP Exceptions with structured error handling.
Starlette-inspired exception hierarchy with context and headers support.
"""

import time
import traceback
from collections.abc import Callable
from typing import Any


class HTTPException(Exception):
    """
    Base HTTP exception with structured error details (Starlette pattern).

    Supports:
    - Custom status codes
    - Error details and messages
    - Additional headers
    - Error codes for API clients
    - Context data for debugging
    - Timestamp tracking
    """

    __slots__ = ("status_code", "detail", "headers", "error_code", "context", "timestamp")

    def __init__(
        self,
        status_code: int,
        detail: str = "",
        headers: dict[str, str] | None = None,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail or self._default_detail()
        self.headers = headers or {}
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context or {}
        self.timestamp = time.time()
        super().__init__(self.detail)

    def _default_detail(self) -> str:
        """Get default detail message for status code"""
        default_messages = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            405: "Method Not Allowed",
            409: "Conflict",
            422: "Unprocessable Entity",
            429: "Too Many Requests",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
            504: "Gateway Timeout",
        }
        return default_messages.get(self.status_code, "HTTP Exception")

    def to_dict(self) -> dict[str, Any]:
        """
        Convert exception to structured dict for JSON response.
        Compatible with API clients expecting structured errors.
        """
        return {
            "error": {
                "code": self.error_code,
                "message": self.detail,
                "status_code": self.status_code,
                "timestamp": self.timestamp,
                "context": self.context,
            }
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(status_code={self.status_code}, detail={self.detail!r})"


class BadRequest(HTTPException):
    """400 Bad Request"""

    def __init__(self, detail: str = "Bad Request") -> None:
        super().__init__(400, detail)


class Unauthorized(HTTPException):
    """401 Unauthorized"""

    def __init__(self, detail: str = "Unauthorized", headers: dict[str, str] | None = None) -> None:
        # Add WWW-Authenticate header if not provided
        if headers is None:
            headers = {"WWW-Authenticate": "Bearer"}
        super().__init__(401, detail, headers=headers)


class Forbidden(HTTPException):
    """403 Forbidden"""

    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(403, detail)


class NotFound(HTTPException):
    """404 Not Found"""

    def __init__(self, detail: str = "Not Found") -> None:
        super().__init__(404, detail)


class MethodNotAllowed(HTTPException):
    """405 Method Not Allowed"""

    def __init__(
        self, detail: str = "Method Not Allowed", allowed_methods: list[str] | None = None
    ) -> None:
        headers = {}
        if allowed_methods:
            headers["Allow"] = ", ".join(allowed_methods)
        super().__init__(405, detail, headers=headers)


class ValidationError(HTTPException):
    """
    422 Unprocessable Entity - Validation failed.
    Compatible with pydantic/msgspec validation errors.
    """

    def __init__(
        self,
        detail: str | dict[str, Any] | list = "Validation Error",
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        if errors:
            context = {"errors": errors}
        elif isinstance(detail, dict):
            context = detail
            detail = "Validation Error"
        else:
            context = {}

        super().__init__(422, str(detail), context=context)


class InternalServerError(HTTPException):
    """500 Internal Server Error"""

    def __init__(
        self, detail: str = "Internal Server Error", original_exception: Exception | None = None
    ) -> None:
        context = {}
        if original_exception:
            context["original_error"] = str(original_exception)
            context["error_type"] = type(original_exception).__name__
        super().__init__(500, detail, context=context)


class ServiceUnavailable(HTTPException):
    """503 Service Unavailable"""

    def __init__(self, detail: str = "Service Unavailable", retry_after: int | None = None) -> None:
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        super().__init__(503, detail, headers=headers)


class RequestTimeout(HTTPException):
    """408 Request Timeout"""

    def __init__(self, detail: str = "Request Timeout") -> None:
        super().__init__(408, detail)


class Conflict(HTTPException):
    """409 Conflict"""

    def __init__(self, detail: str = "Conflict") -> None:
        super().__init__(409, detail)


class TooManyRequests(HTTPException):
    """429 Too Many Requests"""

    def __init__(self, detail: str = "Too Many Requests", retry_after: int | None = None) -> None:
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        super().__init__(429, detail, headers=headers)


class NoMatchFound(Exception):
    """
    Raised by ``request.url_for()`` when no route matches the given name.
    Starlette-compatible.
    """

    def __init__(self, name: str, path_params: dict[str, Any] | None = None) -> None:
        self.name = name
        self.path_params = path_params or {}
        super().__init__(f"No route found for name {name!r}")


class WebSocketDisconnect(Exception):
    """
    WebSocket disconnection exception (Starlette pattern).
    Raised when WebSocket connection is closed.
    """

    def __init__(self, code: int = 1000, reason: str = "") -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket disconnected: {code} - {reason}")


class ErrorHandler:
    """
    Global error handler with logging and context (Starlette-inspired).

    Provides:
    - Custom exception handlers
    - Debug mode with stack traces
    - Structured error responses
    - Request context tracking
    """

    __slots__ = ("_handlers", "_debug", "_logger")

    def __init__(self, debug: bool = False) -> None:
        self._handlers: dict[
            type[Exception], Callable[[Exception, dict[str, Any]], dict[str, Any]]
        ] = {}
        self._debug = debug

        # Setup logging
        import logging

        self._logger = logging.getLogger("velocix.errors")

    def add_handler(
        self,
        exc_type: type[Exception],
        handler: Callable[[Exception, dict[str, Any]], dict[str, Any]],
    ) -> None:
        """
        Add custom exception handler.

        Handler signature: (exception, context) -> error_dict
        """
        self._handlers[exc_type] = handler

    def handle_exception(
        self, exc: Exception, request_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Handle exception with context and logging.

        Returns structured error dict suitable for JSON response.
        """
        context = request_context or {}

        # Check for custom handler (most specific first)
        for exc_type in type(exc).__mro__:
            if exc_type in self._handlers:
                handler = self._handlers[exc_type]
                try:
                    return handler(exc, context)
                except Exception as handler_exc:
                    self._logger.exception(f"Exception handler failed: {handler_exc}")
                    # Fall through to default handling

        # Handle HTTPException
        if isinstance(exc, HTTPException):
            exc.context.update(context)
            return exc.to_dict()

        # Handle unknown exceptions
        self._logger.exception("Unhandled exception", extra=context)

        error_detail: dict[str, Any] | str
        if self._debug:
            error_detail = {
                "message": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc().split("\n"),
            }
        else:
            error_detail = "Internal Server Error"

        return {
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": error_detail,
                "status_code": 500,
                "timestamp": time.time(),
                "context": context if self._debug else {},
            }
        }

    def log_exception(
        self, exc: Exception, request_path: str | None = None, request_method: str | None = None
    ) -> None:
        """Log exception with request context"""
        extra = {}
        if request_path:
            extra["path"] = request_path
        if request_method:
            extra["method"] = request_method

        if isinstance(exc, HTTPException):
            if exc.status_code >= 500:
                self._logger.error(f"HTTP {exc.status_code}: {exc.detail}", extra=extra)
            else:
                self._logger.warning(f"HTTP {exc.status_code}: {exc.detail}", extra=extra)
        else:
            self._logger.exception("Unhandled exception", extra=extra)
