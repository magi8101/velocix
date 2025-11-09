"""Security headers middleware"""
from typing import Any
from types import MappingProxyType
from velocix.core.middleware import BaseMiddleware


class SecurityHeadersMiddleware(BaseMiddleware):
    """Add security headers to responses"""
    
    __slots__ = ("app", "_headers")
    
    def __init__(
        self,
        app: Any,
        csp: str | None = "default-src 'self'",
        hsts: str | None = "max-age=31536000; includeSubDomains",
        frame_options: str | None = "DENY",
        content_type_nosniff: bool = True,
        xss_protection: str | None = "1; mode=block",
        referrer_policy: str | None = "strict-origin-when-cross-origin",
        permissions_policy: str | None = None
    ) -> None:
        super().__init__(app)
        
        headers = {}
        
        if csp:
            headers["content-security-policy"] = csp
        
        if hsts:
            headers["strict-transport-security"] = hsts
        
        if frame_options:
            headers["x-frame-options"] = frame_options
        
        if content_type_nosniff:
            headers["x-content-type-options"] = "nosniff"
        
        if xss_protection:
            headers["x-xss-protection"] = xss_protection
        
        if referrer_policy:
            headers["referrer-policy"] = referrer_policy
        
        if permissions_policy:
            headers["permissions-policy"] = permissions_policy
        
        self._headers = MappingProxyType(headers)
    
    async def __call__(self, request: Any) -> Any:
        """Add security headers to response"""
        response = await self.app(request)
        
        for key, value in self._headers.items():
            response.headers[key] = value
        
        return response
