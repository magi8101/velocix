"""Response compression middleware with zstd and gzip support"""
import gzip
import zlib
from typing import Any, Optional
from velocix.core.middleware import BaseMiddleware
from velocix.core.response import Response, StreamingResponse

HAS_ZSTD = False
HAS_BROTLI = False
zstd: Any = None
brotli: Any = None

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    pass

try:
    import brotli  # type: ignore
    HAS_BROTLI = True
except ImportError:
    pass


class CompressionMiddleware(BaseMiddleware):
    """Compress responses based on Accept-Encoding"""
    
    __slots__ = (
        "app",
        "_minimum_size",
        "_compressible_types",
        "_zstd_compressor",
        "_brotli_quality"
    )
    
    def __init__(
        self,
        app: Any,
        minimum_size: int = 500,
        compressible_types: frozenset[str] | None = None,
        zstd_level: int = 3,
        brotli_quality: int = 4
    ) -> None:
        super().__init__(app)
        self._minimum_size = minimum_size
        self._brotli_quality = brotli_quality
        
        if compressible_types is None:
            self._compressible_types = frozenset({
                "text/html",
                "text/plain",
                "text/css",
                "text/javascript",
                "application/javascript",
                "application/json",
                "application/xml",
                "text/xml",
                "application/x-ndjson"
            })
        else:
            self._compressible_types = compressible_types
        
        # Initialize zstd compressor if available
        self._zstd_compressor: Any = None
        if HAS_ZSTD:
            self._zstd_compressor = zstd.ZstdCompressor(level=zstd_level)
    
    async def __call__(self, request: Any) -> Any:
        """Compress response if supported"""
        response = await self.app(request)
        
        if isinstance(response, StreamingResponse):
            return response
        
        if not self._should_compress(response):
            return response
        
        encoding = self._get_preferred_encoding(request)
        
        if not encoding:
            return response
        
        compressed = self._compress(response.body, encoding)
        
        if compressed and len(compressed) < len(response.body):
            response.body = compressed
            response.headers["content-encoding"] = encoding
            response.headers["content-length"] = str(len(compressed))
            response.headers["vary"] = "Accept-Encoding"
        
        return response
    
    def _should_compress(self, response: Response) -> bool:
        """Check if response should be compressed"""
        if len(response.body) < self._minimum_size:
            return False
        
        if "content-encoding" in {k.lower() for k in response.headers}:
            return False
        
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        
        return content_type in self._compressible_types
    
    def _get_preferred_encoding(self, request: Any) -> str | None:
        """Get preferred encoding from Accept-Encoding header"""
        headers = request.headers
        
        for key, value in headers.items():
            if key == b"accept-encoding":
                encodings = value.decode("latin-1").lower()
                
                if HAS_ZSTD and "zstd" in encodings:
                    return "zstd"
                
                if HAS_BROTLI and "br" in encodings:
                    return "br"
                
                if "gzip" in encodings:
                    return "gzip"
                
                if "deflate" in encodings:
                    return "deflate"
        
        return None
    
    def _compress(self, data: bytes, encoding: str) -> bytes | None:
        """Compress data with specified encoding"""
        try:
            if encoding == "zstd" and self._zstd_compressor:
                return bytes(self._zstd_compressor.compress(data))
            
            elif encoding == "br" and HAS_BROTLI:
                return bytes(brotli.compress(data, quality=self._brotli_quality))
            
            elif encoding == "gzip":
                return gzip.compress(data, compresslevel=6)
            
            elif encoding == "deflate":
                return zlib.compress(data, level=6)
        
        except Exception:
            return None
        
        return None
