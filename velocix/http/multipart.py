"""Multipart form data parsing with streaming"""
import os
import tempfile
from typing import Any, AsyncIterator


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
            await self._file.close()
        
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
                boundary = part[9:].strip('"')
                break
        
        if not boundary:
            raise ValueError("Missing boundary in content-type")
        
        fields: dict[str, Any] = {}
        files: dict[str, UploadFile] = {}
        
        total_size = 0
        field_count = 0
        
        async for chunk in self._read_body(receive):
            total_size += len(chunk)
            
            if total_size > self._max_size:
                raise ValueError(f"Form data exceeds max size {self._max_size}")
        
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
