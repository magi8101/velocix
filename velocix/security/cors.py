"""CORS middleware"""
from typing import Any
from velocix.core.middleware import BaseMiddleware


class CORSMiddleware(BaseMiddleware):
    """Cross-Origin Resource Sharing middleware"""
    
    __slots__ = (
        "app",
        "_allow_origins",
        "_allow_origins_set",
        "_allow_methods",
        "_allow_methods_str",
        "_allow_headers",
        "_allow_headers_str",
        "_allow_credentials",
        "_max_age",
        "_max_age_str",
        "_has_wildcard"
    )
    
    def __init__(
        self,
        app: Any,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        allow_credentials: bool = False,
        max_age: int = 600
    ) -> None:
        super().__init__(app)
        self._allow_origins = allow_origins or ["*"]
        self._allow_origins_set = frozenset(self._allow_origins)
        self._has_wildcard = "*" in self._allow_origins_set
        self._allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
        self._allow_methods_str = ", ".join(self._allow_methods)
        self._allow_headers = allow_headers or ["*"]
        self._allow_headers_str = ", ".join(self._allow_headers)
        self._allow_credentials = allow_credentials
        self._max_age = max_age
        self._max_age_str = str(max_age)
    
    async def __call__(self, request: Any) -> Any:
        """Process CORS headers"""
        if request.method == "OPTIONS":
            from velocix.core.response import Response
            
            response = Response(b"", status_code=204)
            self._add_cors_headers(response, request)
            return response
        
        response = await self.app(request)
        self._add_cors_headers(response, request)
        
        return response
    
    def _add_cors_headers(self, response: Any, request: Any) -> None:
        """Add CORS headers to response"""
        origin = self._get_origin(request)
        
        if origin:
            response.headers["access-control-allow-origin"] = origin
        
        response.headers["access-control-allow-methods"] = self._allow_methods_str
        response.headers["access-control-allow-headers"] = self._allow_headers_str
        
        if self._allow_credentials:
            response.headers["access-control-allow-credentials"] = "true"
        
        response.headers["access-control-max-age"] = self._max_age_str
    
    def _get_origin(self, request: Any) -> str | None:
        """Get origin from request headers"""
        headers = request.headers
        
        for key, value in headers.items():
            if key == b"origin":
                origin = value.decode("latin-1")
                
                if self._has_wildcard:
                    return str(origin)
                
                if origin in self._allow_origins_set:
                    return str(origin)
                
                break
        
        return None
