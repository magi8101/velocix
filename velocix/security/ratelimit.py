"""Production-grade rate limiting with multiple algorithms and key-based limits"""
import time
import asyncio
from typing import Any, Dict, Optional
from collections import defaultdict, deque
from velocix.core.middleware import BaseMiddleware
from velocix.core.exceptions import HTTPException


class TokenBucket:
    """Token bucket rate limiter with configurable capacity and refill rate"""
    
    __slots__ = ("capacity", "tokens", "refill_rate", "last_refill")
    
    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens, return True if allowed"""
        now = time.time()
        elapsed = now - self.last_refill
        
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def available_tokens(self) -> int:
        """Get current available tokens"""
        now = time.time()
        elapsed = now - self.last_refill
        tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        return int(tokens)


class SlidingWindowLimiter:
    """Sliding window rate limiter with configurable window size"""
    
    __slots__ = ("limit", "window_size", "requests")
    
    def __init__(self, limit: int, window_size: float) -> None:
        self.limit = limit
        self.window_size = window_size
        self.requests: deque[float] = deque()
    
    def is_allowed(self) -> bool:
        """Check if request is allowed within sliding window"""
        now = time.time()
        cutoff = now - self.window_size
        
        while self.requests and self.requests[0] <= cutoff:
            self.requests.popleft()
        
        if len(self.requests) < self.limit:
            self.requests.append(now)
            return True
        return False
    
    def requests_in_window(self) -> int:
        """Get current request count in window"""
        now = time.time()
        cutoff = now - self.window_size
        
        while self.requests and self.requests[0] <= cutoff:
            self.requests.popleft()
        
        return len(self.requests)


class ProductionRateLimiter:
    """Multi-algorithm rate limiter with key-based limits"""
    
    __slots__ = ("_buckets", "_windows", "_global_bucket", "_global_window")
    
    def __init__(self) -> None:
        self._buckets: Dict[str, TokenBucket] = {}
        self._windows: Dict[str, SlidingWindowLimiter] = {}
        self._global_bucket: Optional[TokenBucket] = None
        self._global_window: Optional[SlidingWindowLimiter] = None
    
    def add_bucket_limit(self, key: str, capacity: int, refill_rate: float) -> None:
        """Add token bucket limit for specific key"""
        self._buckets[key] = TokenBucket(capacity, refill_rate)
    
    def add_window_limit(self, key: str, limit: int, window_size: float) -> None:
        """Add sliding window limit for specific key"""
        self._windows[key] = SlidingWindowLimiter(limit, window_size)
    
    def set_global_bucket(self, capacity: int, refill_rate: float) -> None:
        """Set global token bucket limit"""
        self._global_bucket = TokenBucket(capacity, refill_rate)
    
    def set_global_window(self, limit: int, window_size: float) -> None:
        """Set global sliding window limit"""
        self._global_window = SlidingWindowLimiter(limit, window_size)
    
    def is_allowed(self, key: str, tokens: int = 1) -> tuple[bool, dict[str, Any]]:
        """Check if request is allowed, return status and metadata"""
        metadata: dict[str, Any] = {}
        
        if self._global_bucket:
            if not self._global_bucket.consume(tokens):
                metadata["reason"] = "global_bucket_exceeded"
                metadata["available_tokens"] = self._global_bucket.available_tokens()
                return False, metadata
        
        if self._global_window:
            if not self._global_window.is_allowed():
                metadata["reason"] = "global_window_exceeded"
                metadata["requests_in_window"] = self._global_window.requests_in_window()
                return False, metadata
        
        if key in self._buckets:
            if not self._buckets[key].consume(tokens):
                metadata["reason"] = "bucket_exceeded"
                metadata["key"] = key
                metadata["available_tokens"] = self._buckets[key].available_tokens()
                return False, metadata
        
        if key in self._windows:
            if not self._windows[key].is_allowed():
                metadata["reason"] = "window_exceeded"
                metadata["key"] = key
                metadata["requests_in_window"] = self._windows[key].requests_in_window()
                return False, metadata
        
        metadata["allowed"] = True
        return True, metadata


class RateLimitMiddleware(BaseMiddleware):
    """Production rate limiter middleware with multiple algorithms"""
    
    __slots__ = ("app", "_limiter", "_key_func", "_error_handler")
    
    def __init__(
        self,
        app: Any,
        limiter: ProductionRateLimiter | None = None,
        key_func: Any | None = None,
        error_handler: Any | None = None
    ) -> None:
        super().__init__(app)
        self._limiter = limiter or ProductionRateLimiter()
        self._key_func = key_func or self._default_key_func
        self._error_handler = error_handler or self._default_error_handler
    
    async def __call__(self, request: Any) -> Any:
        """Check rate limit before processing request"""
        key = self._key_func(request)
        allowed, metadata = self._limiter.is_allowed(key)
        
        if not allowed:
            return await self._error_handler(request, metadata)
        
        # Add rate limit headers
        response = await self.app(request)
        self._add_headers(response, key, metadata)
        return response
    
    def _default_key_func(self, request: Any) -> str:
        """Default key function based on client IP"""
        headers = getattr(request, 'headers', {})
        
        if isinstance(headers, dict):
            forwarded_for = headers.get(b'x-forwarded-for', b'').decode()
            real_ip = headers.get(b'x-real-ip', b'').decode()
            
            if forwarded_for:
                return str(forwarded_for.split(',')[0].strip())
            if real_ip:
                return str(real_ip)
        
        scope = getattr(request, 'scope', {})
        client = scope.get('client')
        if client and len(client) >= 1:
            return str(client[0])
        
        return "unknown"
    
    async def _default_error_handler(self, request: Any, metadata: dict[str, Any]) -> Any:
        """Default error handler for rate limit exceeded"""
        from velocix.core.response import JSONResponse
        
        error_data = {
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests",
                "reason": metadata.get("reason", "unknown"),
                "retry_after": 60
            }
        }
        
        headers = {"Retry-After": "60"}
        return JSONResponse(error_data, status_code=429, headers=headers)
    
    def _add_headers(self, response: Any, key: str, metadata: dict[str, Any]) -> None:
        """Add rate limit headers to response"""
        if hasattr(response, 'headers'):
            response.headers["X-RateLimit-Key"] = key


# Global rate limiter instance
_global_limiter = ProductionRateLimiter()


def get_rate_limiter() -> ProductionRateLimiter:
    """Get global rate limiter instance"""
    return _global_limiter


# Alias for backward compatibility
RateLimiter = RateLimitMiddleware
