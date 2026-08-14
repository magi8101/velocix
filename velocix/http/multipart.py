"""Multipart form data parsing with streaming"""
import os
import tempfile
from typing import Any, AsyncIterator

from python_multipart.multipart import MultipartParser, parse_options_header


class UploadFile:
    """Uploaded file wrapper"""
    
    __slots__ = (
        "filename",
        "content_type",
        "file_path",
        "_file",
        "_closed"
    )
    
    def __init__(
        self,
        filename: str,
        content_type: str = "application/octet-stream"
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self.file_path = ""
        self._file: Any = None
        self._closed = False
    
    async def write(self, data: bytes) -> None:
        """Write data to temp file"""
        if not self._file:
            fd, self.file_path = tempfile.mkstemp()
            self._file = os.fdopen(fd, "wb")
        
        self._file.write(data)
    
    async def read(self, size: int = -1) -> bytes:
        """Read file contents"""
        if self._closed:
            raise ValueError("File already closed")
        
        if not self.file_path:
            return b""
        
        if self._file and not self._file.closed:
            self._file.close()
        
        with open(self.file_path, "rb") as f:
            return f.read(size)
    
    async def close(self) -> None:
        """Close and delete temp file"""
        if self._closed:
            return
        
        self._closed = True
        
        if self._file and not self._file.closed:
            self._file.close()
        
        if self.file_path and os.path.exists(self.file_path):
            os.unlink(self.file_path)
    
    def __repr__(self) -> str:
        return f"UploadFile(filename={self.filename!r}, content_type={self.content_type!r})"


class MultipartForm:
    """Multipart form data parser"""
    
    __slots__ = ("_max_size", "_max_fields")
    
    def __init__(
        self,
        max_size: int = 10 * 1024 * 1024,
        max_fields: int = 1000
    ) -> None:
        self._max_size = max_size
        self._max_fields = max_fields
    
    async def parse(
        self,
        receive: Any,
        content_type: str
    ) -> dict[str, Any]:
        """Parse multipart form data"""
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("Not multipart/form-data")
        
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):].strip('"')
                break
        
        if not boundary:
            raise ValueError("Missing boundary in content-type")
        
        chunks = []
        total_size = 0
        async for chunk in self._read_body(receive):
            total_size += len(chunk)
            if total_size > self._max_size:
                raise ValueError(f"Form data exceeds max size {self._max_size}")
            chunks.append(chunk)
        
        parsed: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        current_field: bytes = b""
        current_value: bytes = b""
        
        def on_part_begin() -> None:
            nonlocal current, current_field, current_value
            current = {"headers": {}, "chunks": []}
            current_field = b""
            current_value = b""
        
        def on_header_field(data: bytes, start: int, end: int) -> None:
            nonlocal current_field
            current_field += data[start:end]
        
        def on_header_value(data: bytes, start: int, end: int) -> None:
            nonlocal current_value
            current_value += data[start:end]
        
        def on_header_end() -> None:
            nonlocal current_field, current_value
            key = current_field.strip().lower()
            if key:
                current["headers"][key] = current_value.strip()
            current_field = b""
            current_value = b""
        
        def on_part_data(data: bytes, start: int, end: int) -> None:
            current["chunks"].append(data[start:end])
        
        def on_part_end() -> None:
            parsed.append(current)
        
        parser = MultipartParser(
            boundary=boundary,
            callbacks={
                "on_part_begin": on_part_begin,
                "on_header_field": on_header_field,
                "on_header_value": on_header_value,
                "on_header_end": on_header_end,
                "on_part_data": on_part_data,
                "on_part_end": on_part_end,
            },
        )
        
        try:
            for chunk in chunks:
                parser.write(chunk)
            parser.finalize()
        except Exception as exc:
            raise ValueError(f"Invalid multipart form data: {exc}") from exc
        
        fields: dict[str, Any] = {}
        files: dict[str, UploadFile] = {}
        
        for i, part in enumerate(parsed):
            if i >= self._max_fields:
                raise ValueError(f"Form data exceeds max fields {self._max_fields}")
            
            disposition = part["headers"].get(b"content-disposition", b"")
            _, params = parse_options_header(disposition)
            name = params.get(b"name", b"").decode("latin-1")
            if not name:
                continue
            
            data = b"".join(part["chunks"])
            filename = params.get(b"filename")
            
            if filename is not None:
                file_type = part["headers"].get(b"content-type", b"").decode("latin-1")
                upload = UploadFile(
                    filename.decode("latin-1"),
                    file_type or "application/octet-stream"
                )
                await upload.write(data)
                files[name] = upload
            else:
                fields[name] = data.decode("utf-8", errors="replace")
        
        return {"fields": fields, "files": files}
    
    async def _read_body(self, receive: Any) -> AsyncIterator[bytes]:
        """Read request body in chunks"""
        while True:
            message = await receive()
            
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if body:
                    yield body
                
                if not message.get("more_body", False):
                    break
            
            elif message["type"] == "http.disconnect":
                break
    
    def validate_file(
        self,
        upload: UploadFile,
        allowed_types: list[str] | None = None,
        max_size: int | None = None
    ) -> bool:
        """Validate uploaded file"""
        if allowed_types and upload.content_type not in allowed_types:
            return False
        
        if max_size and os.path.getsize(upload.file_path) > max_size:
            return False
        
        return True
