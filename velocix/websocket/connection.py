"""
WebSocket connection handling with Starlette-inspired state machine.
Provides robust WebSocket support with proper state transitions.
"""
import asyncio
import orjson
from typing import Any, Optional, AsyncIterator
from enum import IntEnum


class WebSocketState(IntEnum):
    """WebSocket connection states (Starlette pattern)"""
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class WebSocketDisconnect(Exception):
    """
    WebSocket disconnection exception (Starlette pattern).
    Raised when WebSocket connection is closed unexpectedly.
    """
    def __init__(self, code: int = 1000, reason: str = "") -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket disconnected: {code} - {reason}")


class WebSocket:
    """
    WebSocket connection with Starlette-inspired API.
    
    Provides:
    - State machine for connection lifecycle
    - Text, binary, and JSON messaging
    - Async iteration support
    - Proper error handling
    - Subprotocol negotiation
    """
    
    __slots__ = (
        "scope",
        "_receive",
        "_send",
        "state",
        "client_state",
        "application_state",
        "_accepted",
        "_closed",
        "client_id",
        "path_params"
    )
    
    def __init__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        assert scope["type"] == "websocket", "Scope must be websocket"
        
        self.scope = scope
        self._receive = receive
        self._send = send
        self.state: Any = type("State", (), {})()
        
        # State tracking (Starlette pattern)
        self.client_state = WebSocketState.CONNECTING
        self.application_state = WebSocketState.CONNECTING
        
        self._accepted = False
        self._closed = False
        self.client_id = self._get_client_id()
        self.path_params: dict[str, Any] = scope.get("path_params", {})
    
    def _get_client_id(self) -> str:
        """Get client identifier from scope"""
        client = self.scope.get("client")
        if client:
            return f"{client[0]}:{client[1]}"
        return "unknown"
    
    @property
    def path(self) -> str:
        """WebSocket path"""
        return str(self.scope["path"])
    
    @property
    def headers(self) -> dict[bytes, bytes]:
        """Request headers"""
        return dict(self.scope.get("headers", []))
    
    @property
    def query_string(self) -> bytes:
        """Query string"""
        return bytes(self.scope.get("query_string", b""))
    
    async def accept(
        self,
        subprotocol: str | None = None,
        headers: list[tuple[bytes, bytes]] | None = None
    ) -> None:
        """
        Accept WebSocket connection (Starlette pattern).
        Must be called before sending/receiving messages.
        """
        if self._accepted:
            return
        
        # Wait for connect message if needed
        if self.client_state == WebSocketState.CONNECTING:
            message = await self._receive()
            if message["type"] != "websocket.connect":
                raise RuntimeError(
                    f'Expected "websocket.connect", got "{message["type"]}"'
                )
            self.client_state = WebSocketState.CONNECTED
        
        # Send accept message
        accept_msg: dict[str, Any] = {"type": "websocket.accept"}
        
        if subprotocol:
            accept_msg["subprotocol"] = subprotocol
        
        if headers:
            accept_msg["headers"] = headers
        
        await self._send(accept_msg)
        self._accepted = True
        self.application_state = WebSocketState.CONNECTED
    
    async def receive(self) -> dict[str, Any]:
        """
        Receive raw ASGI message (Starlette pattern).
        Handles state transitions properly.
        """
        if self.application_state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket is not connected. Call accept() first.")
        
        message = await self._receive()
        message_type = message["type"]
        
        if message_type == "websocket.disconnect":
            self.client_state = WebSocketState.DISCONNECTED
            self._closed = True
            raise WebSocketDisconnect(
                code=message.get("code", 1000),
                reason=message.get("reason", "")
            )
        
        if message_type == "websocket.receive":
            return message
        
        raise RuntimeError(
            f'Expected "websocket.receive" or "websocket.disconnect", '
            f'got "{message_type}"'
        )
    
    async def receive_text(self) -> str:
        """Receive text message (Starlette pattern)"""
        message = await self.receive()
        if "text" not in message:
            raise RuntimeError("Expected text message, got bytes")
        return str(message["text"])
    
    async def receive_bytes(self) -> bytes:
        """Receive binary message (Starlette pattern)"""
        message = await self.receive()
        if "bytes" not in message:
            raise RuntimeError("Expected bytes message, got text")
        return bytes(message["bytes"])
    
    async def receive_json(self, mode: str = "text") -> Any:
        """
        Receive JSON message (Starlette pattern).
        
        Args:
            mode: 'text' or 'binary' - how to receive JSON data
        """
        if mode not in {"text", "binary"}:
            raise ValueError("mode must be 'text' or 'binary'")
        
        if mode == "text":
            text = await self.receive_text()
        else:
            data = await self.receive_bytes()
            text = data.decode("utf-8")
        
        try:
            return orjson.loads(text)
        except orjson.JSONDecodeError as exc:
            raise RuntimeError(f"Malformed JSON data: {exc}")
    
    async def send_text(self, data: str) -> None:
        """Send text message (Starlette pattern)"""
        if self.application_state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket is not connected")
        
        await self._send({"type": "websocket.send", "text": data})
    
    async def send_bytes(self, data: bytes) -> None:
        """Send binary message (Starlette pattern)"""
        if self.application_state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket is not connected")
        
        await self._send({"type": "websocket.send", "bytes": data})
    
    async def send_json(self, data: Any, mode: str = "text") -> None:
        """
        Send JSON message (Starlette pattern).
        
        Args:
            data: Data to serialize as JSON
            mode: 'text' or 'binary' - how to send JSON data
        """
        if mode not in {"text", "binary"}:
            raise ValueError("mode must be 'text' or 'binary'")
        
        text = orjson.dumps(data).decode("utf-8")
        
        if mode == "text":
            await self.send_text(text)
        else:
            await self.send_bytes(text.encode("utf-8"))
    
    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close WebSocket connection (Starlette pattern).
        Idempotent - safe to call multiple times.
        """
        if self._closed:
            return
        
        self._closed = True
        self.application_state = WebSocketState.DISCONNECTED
        
        await self._send({
            "type": "websocket.close",
            "code": code,
            "reason": reason
        })
    
    async def iter_text(self) -> AsyncIterator[str]:
        """
        Iterate over incoming text messages (Starlette pattern).
        Stops iteration on disconnect.
        """
        try:
            while True:
                yield await self.receive_text()
        except WebSocketDisconnect:
            pass
    
    async def iter_bytes(self) -> AsyncIterator[bytes]:
        """
        Iterate over incoming binary messages (Starlette pattern).
        Stops iteration on disconnect.
        """
        try:
            while True:
                yield await self.receive_bytes()
        except WebSocketDisconnect:
            pass
    
    async def iter_json(self) -> AsyncIterator[Any]:
        """
        Iterate over incoming JSON messages (Starlette pattern).
        Stops iteration on disconnect.
        """
        try:
            while True:
                yield await self.receive_json()
        except WebSocketDisconnect:
            pass
    
    @property
    def client(self) -> Optional[tuple[str, int]]:
        """Get client address (host, port)"""
        return self.scope.get("client")
    
    @property
    def url(self) -> str:
        """Get full WebSocket URL"""
        scheme = "wss" if self.scope.get("scheme") == "wss" else "ws"
        server = self.scope.get("server", ("localhost", 80))
        path = self.path
        query = self.query_string.decode("latin-1")
        
        url = f"{scheme}://{server[0]}:{server[1]}{path}"
        if query:
            url += f"?{query}"
        
        return url
    
    def __repr__(self) -> str:
        return f"WebSocket(client_id={self.client_id!r}, path={self.path!r}, closed={self._closed})"


class WebSocketManager:
    """Manage multiple WebSocket connections"""
    
    __slots__ = ("_connections", "_connections_by_id", "_lock")
    
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._connections_by_id: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, ws: WebSocket) -> None:
        """Add connection to manager"""
        async with self._lock:
            self._connections.add(ws)
            self._connections_by_id[ws.client_id] = ws
    
    async def disconnect(self, ws: WebSocket) -> None:
        """Remove connection from manager"""
        async with self._lock:
            self._connections.discard(ws)
            self._connections_by_id.pop(ws.client_id, None)
    
    async def broadcast(self, message: dict[str, Any], exclude: WebSocket | None = None) -> None:
        """Broadcast message to all connections"""
        async with self._lock:
            connections = list(self._connections)
        
        tasks = []
        for ws in connections:
            if ws is not exclude and not ws._closed:
                tasks.append(ws.send_json(message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast_text(self, text: str, exclude: WebSocket | None = None) -> None:
        """Broadcast text to all connections"""
        async with self._lock:
            connections = list(self._connections)
        
        tasks = []
        for ws in connections:
            if ws is not exclude and not ws._closed:
                tasks.append(ws.send_text(text))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def send_to(self, client_id: str, message: dict[str, Any] | str) -> bool:
        """Send message to specific client"""
        ws = self._connections_by_id.get(client_id)
        
        if ws and not ws._closed:
            try:
                if isinstance(message, str):
                    await ws.send_text(message)
                else:
                    await ws.send_json(message)
                return True
            except Exception:
                return False
        return False
    
    async def close_all(self, code: int = 1000, reason: str = "") -> None:
        """Close all connections"""
        async with self._lock:
            connections = list(self._connections)
        
        tasks = [ws.close(code, reason) for ws in connections]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        async with self._lock:
            self._connections.clear()
            self._connections_by_id.clear()
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self._connections)
    
    def get_connections(self) -> list[WebSocket]:
        """Get list of all connections"""
        return list(self._connections)
    
    def __repr__(self) -> str:
        return f"WebSocketManager(connections={len(self._connections)})"
