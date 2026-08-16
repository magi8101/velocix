"""Static file serving as an ASGI application.

Mount via app.mount(path, StaticFiles(directory=...)); the mount strips
the prefix from the scope before dispatch, so this app resolves paths
relative to its directory. Path traversal is blocked (resolved paths
must stay inside the configured directory).
"""

from pathlib import Path
from typing import Any

from velocix.core.response import FileResponse


class StaticFiles:
    """Serve files from a directory over ASGI.

    Args:
        directory: Root directory to serve from
        html: Serve index.html at the mount root (like StaticFiles(html=True))
    """

    __slots__ = ("directory", "html")

    def __init__(self, directory: str | Path, html: bool = False) -> None:
        self.directory = Path(directory)
        self.html = html

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI entry point: serve one request."""
        if scope["type"] != "http":
            return

        method = scope.get("method", "GET")
        rel_path = scope["path"].lstrip("/")

        if not rel_path:
            if self.html and (self.directory / "index.html").is_file():
                rel_path = "index.html"
            else:
                await self._send_error(send, 404, "Not Found")
                return

        file_path = self._resolve(rel_path)
        if file_path is None:
            await self._send_error(send, 404, "Not Found")
            return

        response = FileResponse(file_path)

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": response.asgi_headers(),
            }
        )
        if method == "HEAD":
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        content = response.content
        if callable(content):
            content = content()
        async for chunk in content:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    def _resolve(self, rel_path: str) -> Path | None:
        """Resolve a request path inside the directory, blocking traversal."""
        candidate = (self.directory / rel_path).resolve()
        root = self.directory.resolve()
        if not candidate.is_file() or not str(candidate).startswith(str(root)):
            return None
        return candidate

    @staticmethod
    async def _send_error(send: Any, status: int, message: str) -> None:
        body = message.encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
