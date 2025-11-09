"""
Request object with lazy parsing and cached properties - Starlette-inspired optimizations
"""
import orjson
from typing import Any, Optional, AsyncIterator
from urllib.parse import parse_qs, unquote_plus
from http import cookies as http_cookies


def cookie_parser(cookie_string: str) -> dict[str, str]:
    """
    Parse Cookie header into dict of key/value pairs.
    Adapted from Starlette/Django for browser compatibility.
    """
    cookie_dict: dict[str, str] = {}
    for chunk in cookie_string.split(";"):
        if "=" in chunk:
            key, val = chunk.split("=", 1)
        else:
            key, val = "", chunk
        key, val = key.strip(), val.strip()
        if key or val:
            cookie_dict[key] = http_cookies._unquote(val)
    return cookie_dict


class ClientDisconnect(Exception):
    """Raised when client disconnects during request"""
    pass


class Request:
    """HTTP Request with lazy parsing and property caching"""
    
    __slots__ = (
        "scope",
        "_receive",
        "_send",
        "_body",
        "_json",
        "_form",
        "_query_params",
        "_cookies",
        "_url",
        "_base_url",
        "path_params",
        "state",
        "_method",
        "_path",
        "_headers",
        "_query_string",
        "_stream_consumed",
        "_is_disconnected"
    )
    
    def __init__(self, scope: dict[str, Any], receive: Any, send: Any = None) -> None:
        assert scope["type"] == "http", "Request scope must be 'http'"
        
        self.scope = scope
        self._receive = receive
        self._send = send
        
        # Lazy-loaded properties (Starlette pattern)
        self._body: bytes | None = None
        self._json: Any = None
        self._form: dict[str, Any] | None = None
        self._query_params: dict[str, str] | None = None
        self._cookies: dict[str, str] | None = None
        self._headers: dict[bytes, bytes] | None = None
        self._url: Optional[str] = None
        self._base_url: Optional[str] = None
        
        # Path parameters set by router
        self.path_params: dict[str, str] = scope.get("path_params", {})
        
        # State object for middleware
        self.state: Any = type("State", (), {})()
        
        # Pre-cache frequently accessed immutable properties
        self._method: str = scope["method"]
        self._path: str = scope["path"]
        self._query_string: bytes = scope.get("query_string", b"")
        
        # Stream state tracking
        self._stream_consumed: bool = False
        self._is_disconnected: bool = False
    
    @property
    def method(self) -> str:
        """HTTP method (cached)"""
        return self._method
    
    @property
    def path(self) -> str:
        """Request path (cached)"""
        return self._path
    
    @property
    def headers(self) -> dict[bytes, bytes]:
        """Request headers (cached)"""
        if self._headers is None:
            self._headers = dict(self.scope.get("headers", []))
        return self._headers
    
    @property
    def query_string(self) -> bytes:
        """Raw query string (cached)"""
        return self._query_string
    
    @property
    def url(self) -> str:
        """Full request URL (lazy, cached)"""
        if self._url is None:
            scheme = self.scope.get("scheme", "http")
            server = self.scope.get("server")
            path = self._path
            query = self._query_string.decode("latin-1")
            
            if server:
                host, port = server
                default_port = {"http": 80, "https": 443}[scheme]
                if port == default_port:
                    self._url = f"{scheme}://{host}{path}"
                else:
                    self._url = f"{scheme}://{host}:{port}{path}"
            else:
                self._url = path
            
            if query:
                self._url += f"?{query}"
        
        return self._url
    
    @property
    def base_url(self) -> str:
        """Base URL without path/query (lazy, cached)"""
        if self._base_url is None:
            scheme = self.scope.get("scheme", "http")
            server = self.scope.get("server")
            
            if server:
                host, port = server
                default_port = {"http": 80, "https": 443}[scheme]
                if port == default_port:
                    self._base_url = f"{scheme}://{host}"
                else:
                    self._base_url = f"{scheme}://{host}:{port}"
            else:
                self._base_url = ""
        
        return self._base_url
    
    @property
    def query_params(self) -> dict[str, str]:
        """Parsed query parameters (lazy, cached)"""
        if self._query_params is None:
            if self._query_string:
                qs = self._query_string.decode("utf-8")
                parsed = parse_qs(qs, keep_blank_values=True)
                # Take first value for each key (Starlette pattern)
                self._query_params = {k: v[0] if v else "" for k, v in parsed.items()}
            else:
                self._query_params = {}
        return self._query_params
    
    @property
    def cookies(self) -> dict[str, str]:
        """Parsed cookies (lazy, cached)"""
        if self._cookies is None:
            self._cookies = {}
            cookie_header = self.headers.get(b"cookie")
            if cookie_header:
                try:
                    self._cookies = cookie_parser(cookie_header.decode("latin-1"))
                except Exception:
                    # Malformed cookies, return empty dict
                    pass
        return self._cookies
    
    @property
    def client(self) -> Optional[tuple[str, int]]:
        """Client address (host, port) or None"""
        return self.scope.get("client")
    
    async def stream(self) -> AsyncIterator[bytes]:
        """
        Stream request body in chunks (Starlette pattern).
        Once consumed, subsequent calls will raise RuntimeError.
        """
        if hasattr(self, "_body") and self._body is not None:
            yield self._body
            yield b""
            return
        
        if self._stream_consumed:
            raise RuntimeError("Stream already consumed")
        
        while not self._stream_consumed:
            message = await self._receive()
            
            if message["type"] == "http.request":
                body_chunk = message.get("body", b"")
                if not message.get("more_body", False):
                    self._stream_consumed = True
                if body_chunk:
                    yield body_chunk
            elif message["type"] == "http.disconnect":
                self._is_disconnected = True
                raise ClientDisconnect()
        
        yield b""
    
    async def body(self) -> bytes:
        """
        Request body (cached after first read).
        Uses efficient stream aggregation pattern from Starlette.
        """
        if self._body is None:
            chunks: list[bytes] = []
            async for chunk in self.stream():
                chunks.append(chunk)
            self._body = b"".join(chunks)
        return self._body
    
    async def json(self) -> Any:
        """
        Parse JSON body (cached, uses orjson for speed).
        Returns None for empty body.
        """
        if self._json is None:
            body = await self.body()
            if body:
                self._json = orjson.loads(body)
            else:
                self._json = None
        return self._json
    
    async def form(self) -> dict[str, Any]:
        """
        Parse form data (application/x-www-form-urlencoded).
        Cached after first parse.
        """
        if self._form is None:
            body = await self.body()
            if body:
                form_data = parse_qs(body.decode("utf-8"), keep_blank_values=True)
                self._form = {k: v[0] if len(v) == 1 else v for k, v in form_data.items()}
            else:
                self._form = {}
        return self._form
    
    async def is_disconnected(self) -> bool:
        """Check if client has disconnected (non-blocking)"""
        return self._is_disconnected
    
    def __repr__(self) -> str:
        return f"Request(method={self._method!r}, path={self._path!r})"
    
    def __getitem__(self, key: str) -> Any:
        """Dict-like access to scope (Starlette compatibility)"""
        return self.scope[key]
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists in scope"""
        return key in self.scope
