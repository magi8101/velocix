"""Request ID middleware for tracing"""

import secrets
from typing import Any

from velocix.core.middleware import BaseMiddleware


class RequestIDMiddleware(BaseMiddleware):
    """Add unique request ID for tracing"""

    __slots__ = ("app", "_header_name", "_header_name_bytes")

    def __init__(self, app: Any, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self._header_name = header_name
        self._header_name_bytes = header_name.lower().encode("latin-1")

    async def __call__(self, request: Any) -> Any:
        """Generate or extract request ID"""
        request_id = self._get_request_id(request)

        if not request_id:
            request_id = secrets.token_urlsafe(16)

        request.state.request_id = request_id

        response = await self.app(request)

        response.headers[self._header_name] = request_id

        return response

    def _get_request_id(self, request: Any) -> str | None:
        """Extract request ID from headers"""
        headers = request.headers
        header_lower = self._header_name_bytes

        for key, value in headers.items():
            if key.lower() == header_lower:
                return str(value.decode("latin-1"))

        return None
