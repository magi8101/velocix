"""Test client for ASGI applications with comprehensive features"""

import asyncio
from io import BytesIO
from typing import Any
from urllib.parse import urlencode, urlparse


class TestResponse:
    """HTTP response from test client with enhanced functionality"""

    __slots__ = ("status_code", "headers", "body", "content", "_json_cache")

    def __init__(self, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.content = body
        self._json_cache: Any | None = None

    def json(self) -> Any:
        """Parse JSON response with caching"""
        if self._json_cache is None:
            import orjson

            self._json_cache = orjson.loads(self.body)
        return self._json_cache

    def text(self) -> str:
        """Get response as text"""
        return self.body.decode("utf-8")

    def raise_for_status(self) -> None:
        """Raise exception if status code indicates error"""
        if 400 <= self.status_code < 600:
            raise AssertionError(f"Request failed with status {self.status_code}: {self.text()}")

    def __repr__(self) -> str:
        return f"TestResponse(status_code={self.status_code}, length={len(self.body)})"


class WebSocketTestSession:
    """WebSocket test session for testing WebSocket endpoints"""

    __slots__ = ("_send_queue", "_receive_queue", "_closed")

    def __init__(self) -> None:
        self._send_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._closed = False

    async def send(self, message: dict[str, Any]) -> None:
        """Send message to application"""
        await self._receive_queue.put(message)

    async def receive(self) -> dict[str, Any]:
        """Receive message from application"""
        return await self._send_queue.get()

    async def send_text(self, data: str) -> None:
        """Send text message"""
        await self.send({"type": "websocket.receive", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        """Send binary message"""
        await self.send({"type": "websocket.receive", "bytes": data})

    async def send_json(self, data: Any) -> None:
        """Send JSON message"""
        import orjson

        json_str = orjson.dumps(data).decode()
        await self.send_text(json_str)

    async def receive_text(self) -> str:
        """Receive text message"""
        message = await self.receive()
        return str(message.get("text", ""))

    async def receive_bytes(self) -> bytes:
        """Receive binary message"""
        message = await self.receive()
        return bytes(message.get("bytes", b""))

    async def receive_json(self) -> Any:
        """Receive JSON message"""
        import orjson

        text = await self.receive_text()
        return orjson.loads(text)

    async def close(self, code: int = 1000) -> None:
        """Close WebSocket"""
        self._closed = True
        await self.send({"type": "websocket.disconnect", "code": code})


class TestClient:
    """Test client for making requests to ASGI app with full HTTP support"""

    __slots__ = ("app", "_lifespan_started", "_base_url", "_cookies", "_headers")

    def __init__(
        self, app: Any, base_url: str = "http://testserver", headers: dict[str, str] | None = None
    ) -> None:
        self.app = app
        self._lifespan_started = False
        self._base_url = base_url
        self._cookies: dict[str, str] = {}
        self._headers = headers or {}

    async def __aenter__(self) -> "TestClient":
        await self._startup()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._shutdown()

    async def _startup(self) -> None:
        """Execute app startup via ASGI lifespan"""
        if self._lifespan_started:
            return

        self._lifespan_started = True
        await self._run_lifespan("lifespan.startup")

    async def _shutdown(self) -> None:
        """Execute app shutdown via ASGI lifespan"""
        await self._run_lifespan("lifespan.shutdown")

    async def _run_lifespan(self, message_type: str) -> None:
        """Drive the app's ASGI lifespan protocol"""
        completed: asyncio.Event = asyncio.Event()
        failure: list[str] = []
        sent = False

        async def receive() -> dict[str, Any]:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": message_type}
            await asyncio.Event().wait()
            return {"type": message_type}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == f"{message_type}.complete":
                completed.set()
            elif message["type"] == f"{message_type}.failed":
                failure.append(str(message.get("message", "")))
                completed.set()

        task = asyncio.create_task(
            self.app(
                {
                    "type": "lifespan",
                    "asgi": {"version": "3.0", "spec_version": "2.0"},
                },
                receive,
                send,
            )
        )

        try:
            await asyncio.wait_for(completed.wait(), timeout=10)
        except TimeoutError as exc:
            raise RuntimeError(f"Lifespan {message_type} timed out") from exc
        finally:
            if not task.done():
                task.cancel()

        if failure:
            raise RuntimeError(f"Lifespan {message_type} failed: {failure[0]}")

    def _merge_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        """Merge default headers with request headers"""
        merged = self._headers.copy()
        if headers:
            merged.update(headers)

        if self._cookies:
            cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
            merged["cookie"] = cookie_header

        return merged

    def _parse_cookies(self, response_headers: dict[str, str]) -> None:
        """Parse and store cookies from response"""
        set_cookie = response_headers.get("set-cookie")
        if set_cookie:
            for cookie_str in set_cookie.split(";"):
                if "=" in cookie_str:
                    key, value = cookie_str.split("=", 1)
                    self._cookies[key.strip()] = value.strip()

    async def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        json: Any | None = None,
        params: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes]] | None = None,
        follow_redirects: bool = False,
    ) -> TestResponse:
        """Make HTTP request with comprehensive features including params, files, and redirects"""
        import orjson

        if params:
            query_string = urlencode(params)
            if "?" in path:
                path = f"{path}&{query_string}"
            else:
                path = f"{path}?{query_string}"

        merged_headers = self._merge_headers(headers)

        if json is not None:
            body = orjson.dumps(json)
            merged_headers["content-type"] = "application/json"

        if files:
            boundary = "----WebKitFormBoundary" + "".join(
                __import__("random").choices("0123456789abcdef", k=16)
            )
            body = self._build_multipart(files, boundary)
            merged_headers["content-type"] = f"multipart/form-data; boundary={boundary}"

        parsed_url = urlparse(path)
        path_part = parsed_url.path or "/"
        query_string_bytes = parsed_url.query.encode() if parsed_url.query else b""

        scope = {
            "type": "http",
            "method": method.upper(),
            "path": path_part,
            "query_string": query_string_bytes,
            "headers": [(k.lower().encode(), v.encode()) for k, v in merged_headers.items()],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
            "http_version": "1.1",
        }

        body_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {
                    "type": "http.request",
                    "body": body or b"",
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        response_started = False
        response_status = 200
        response_headers: dict[str, str] = {}
        response_body = BytesIO()

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_started, response_status, response_headers

            if message["type"] == "http.response.start":
                response_started = True
                response_status = message["status"]
                response_headers = {k.decode(): v.decode() for k, v in message.get("headers", [])}
            elif message["type"] == "http.response.body":
                response_body.write(message.get("body", b""))

        await self.app(scope, receive, send)

        self._parse_cookies(response_headers)

        response = TestResponse(
            status_code=response_status, headers=response_headers, body=response_body.getvalue()
        )

        if follow_redirects and 300 <= response_status < 400:
            location = response_headers.get("location")
            if location:
                return await self.request(
                    method, location, headers=headers, follow_redirects=follow_redirects
                )

        return response

    def _build_multipart(self, files: dict[str, tuple[str, bytes]], boundary: str) -> bytes:
        """Build multipart/form-data body"""
        body = BytesIO()

        for field_name, (filename, content) in files.items():
            body.write(f"--{boundary}\r\n".encode())
            body.write(
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode()
            )
            body.write(b"Content-Type: application/octet-stream\r\n\r\n")
            body.write(content)
            body.write(b"\r\n")

        body.write(f"--{boundary}--\r\n".encode())
        return body.getvalue()

    async def websocket_connect(
        self, path: str, params: dict[str, str] | None = None
    ) -> WebSocketTestSession:
        """Connect to WebSocket endpoint"""
        if params:
            query_string = urlencode(params)
            path = f"{path}?{query_string}"

        session = WebSocketTestSession()

        scope = {
            "type": "websocket",
            "path": path,
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "ws",
        }

        async def receive() -> dict[str, Any]:
            return await session._receive_queue.get()

        async def send(message: dict[str, Any]) -> None:
            await session._send_queue.put(message)

        asyncio.create_task(self.app(scope, receive, send))

        await session.send({"type": "websocket.connect"})

        return session

    async def get(self, path: str, **kwargs: Any) -> TestResponse:
        """GET request"""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> TestResponse:
        """POST request"""
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> TestResponse:
        """PUT request"""
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> TestResponse:
        """DELETE request"""
        return await self.request("DELETE", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> TestResponse:
        """PATCH request"""
        return await self.request("PATCH", path, **kwargs)
