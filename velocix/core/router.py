"""
Optimized Velocix Router with caching, bloom filters, and advanced routing
"""

import math
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .exceptions import MethodNotAllowed, NotFound


class HandlerProtocol(Protocol):
    """Protocol for route handlers"""

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


class BloomFilter:
    """Memory-efficient bloom filter for route existence checking"""

    def __init__(self, capacity: int = 10000, error_rate: float = 0.001):
        self.capacity = capacity
        self.error_rate = error_rate
        self.bit_array_size = int(-(capacity * math.log(error_rate)) / (math.log(2) ** 2))
        self.hash_count = int((self.bit_array_size / capacity) * math.log(2))
        self.bit_array = bytearray(self.bit_array_size)

    def _hash(self, item: str, seed: int) -> int:
        return hash(f"{item}:{seed}") % self.bit_array_size

    def add(self, item: str):
        for i in range(self.hash_count):
            index = self._hash(item, i)
            self.bit_array[index // 8] |= 1 << (index % 8)

    def contains(self, item: str) -> bool:
        for i in range(self.hash_count):
            index = self._hash(item, i)
            if not (self.bit_array[index // 8] & (1 << (index % 8))):
                return False
        return True


@dataclass
class RouteMetrics:
    """Performance metrics for route optimization"""

    hit_count: int = 0
    avg_response_time: float = 0.0
    last_access: float = field(default_factory=time.time)
    cache_hits: int = 0

    def update(self, response_time: float):
        self.hit_count += 1
        self.avg_response_time = (
            self.avg_response_time * (self.hit_count - 1) + response_time
        ) / self.hit_count
        self.last_access = time.time()


@dataclass
class CachedRoute:
    """Cached route with TTL"""

    handler: Callable
    params: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    ttl: float = 300.0  # 5 minutes
    version: int = 0
    metrics: "RouteMetrics | None" = None

    def is_valid(self) -> bool:
        return time.time() - self.created_at < self.ttl


@dataclass
class RouteNode:
    """Optimized route tree node"""

    handler: Callable | None = None
    children: dict[str, "RouteNode"] = field(default_factory=dict)
    param_child: Optional["RouteNode"] = None
    param_name: str | None = None
    is_endpoint: bool = False
    methods: set[str] = field(default_factory=set)
    constraints: dict[str, Callable] = field(default_factory=dict)
    metrics: RouteMetrics = field(default_factory=RouteMetrics)


class Router:
    """Ultra-high performance router with advanced caching and optimization"""

    def __init__(self):
        self.root = RouteNode()
        self.route_cache: dict[str, dict[str, CachedRoute]] = defaultdict(dict)
        self._routes_version: int = 0
        self.bloom_filter = BloomFilter()
        self.method_trees: dict[str, RouteNode] = {
            "GET": RouteNode(),
            "POST": RouteNode(),
            "PUT": RouteNode(),
            "DELETE": RouteNode(),
            "PATCH": RouteNode(),
            "HEAD": RouteNode(),
            "OPTIONS": RouteNode(),
            "WEBSOCKET": RouteNode(),
        }
        self.static_routes: dict[str, dict[str, Callable]] = defaultdict(dict)
        self.dynamic_patterns: list[tuple] = []
        self.middleware_stack: list[Callable] = []
        # Flat (method, path, handler) registration log for include_router
        self._registered: list[tuple[str, str, Callable]] = []

    def add_constraint(self, param_name: str, constraint: Callable):
        """Add parameter constraint for validation"""

        def decorator(func):
            if not hasattr(func, "_constraints"):
                func._constraints = {}
            func._constraints[param_name] = constraint
            return func

        return decorator

    def int_constraint(self, value: str) -> bool:
        """Integer parameter constraint"""
        try:
            int(value)
            return True
        except ValueError:
            return False

    def uuid_constraint(self, value: str) -> bool:
        """UUID parameter constraint"""
        import re

        uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        return bool(uuid_pattern.match(value))

    def add_route(
        self,
        method: str,
        path: str,
        handler: Callable,
        constraints: dict[str, Callable] | None = None,
    ):
        """Add route with advanced optimization and validation"""
        # Input validation
        if not method:
            raise ValueError("Method cannot be empty")

        if not isinstance(method, str):
            raise TypeError("Method must be a string")

        if not path:
            raise ValueError("Path cannot be empty")

        if not isinstance(path, str):
            raise TypeError("Path must be a string")

        if not callable(handler):
            raise TypeError("Handler must be callable")

        # Validate HTTP method
        valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "WEBSOCKET"}
        if method.upper() not in valid_methods:
            raise ValueError(f"Invalid method: {method}")

        method = method.upper()

        # Normalize path
        if not path.startswith("/"):
            path = "/" + path
        if path != "/" and path.endswith("/"):
            path = path[:-1]

        self._registered.append((method, path, handler))

        # Bump version so cached entries from before this mutation are invalidated
        self._routes_version += 1

        # Check for static route optimization
        if "{" not in path:
            self.static_routes[method][path] = handler
            self.route_cache[method][path] = CachedRoute(handler, {}, version=self._routes_version)
            self.bloom_filter.add(f"{method}:{path}")
            return

        # Build route tree
        tree = self.method_trees[method]
        current = tree
        parts = [p for p in path.split("/") if p]

        for part in parts:
            if part.startswith("{") and part.endswith("}"):
                # Parameter segment
                param_name = part[1:-1]
                if not current.param_child:
                    current.param_child = RouteNode()
                    current.param_name = param_name
                current = current.param_child

                # Apply constraints
                if constraints and param_name in constraints:
                    current.constraints[param_name] = constraints[param_name]

            else:
                # Static segment
                if part not in current.children:
                    current.children[part] = RouteNode()
                current = current.children[part]

        current.handler = handler
        current.is_endpoint = True
        current.methods.add(method)

        # Add to bloom filter
        pattern_key = f"{method}:{path}"
        self.bloom_filter.add(pattern_key)

    def get(self, path: str):
        """GET route decorator"""

        def decorator(handler):
            self.add_route("GET", path, handler)
            return handler

        return decorator

    def post(self, path: str):
        """POST route decorator"""

        def decorator(handler):
            self.add_route("POST", path, handler)
            return handler

        return decorator

    def put(self, path: str):
        """PUT route decorator"""

        def decorator(handler):
            self.add_route("PUT", path, handler)
            return handler

        return decorator

    def delete(self, path: str):
        """DELETE route decorator"""

        def decorator(handler):
            self.add_route("DELETE", path, handler)
            return handler

        return decorator

    def patch(self, path: str):
        """PATCH route decorator"""

        def decorator(handler):
            self.add_route("PATCH", path, handler)
            return handler

        return decorator

    def head(self, path: str):
        """HEAD route decorator"""

        def decorator(handler):
            self.add_route("HEAD", path, handler)
            return handler

        return decorator

    def options(self, path: str):
        """OPTIONS route decorator"""

        def decorator(handler):
            self.add_route("OPTIONS", path, handler)
            return handler

        return decorator

    def websocket(self, path: str):
        """WebSocket route decorator"""

        def decorator(handler):
            self.add_route("WEBSOCKET", path, handler)
            return handler

        return decorator

    def include_router(self, router: "Router", prefix: str = "") -> None:
        """Merge another router's routes into this one, optionally under a prefix.

        Args:
            router: Router whose routes should be re-registered here
            prefix: Path prefix prepended to every route (e.g. "/api")
        """
        prefix = prefix.rstrip("/") if prefix else ""
        for method, path, handler in router._registered:
            self.add_route(method, prefix + path, handler)

    def resolve(self, method: str, path: str) -> tuple[Callable, dict[str, str]]:
        """Ultra-fast route resolution with caching"""
        # Check cache first: no key allocation, no clock reads on the hot path.
        # Cached entries are validated against the router's mutation version
        # instead of a wall-clock TTL, which is exact for in-process mutation.
        by_method = self.route_cache.get(method)
        if by_method is not None:
            cached = by_method.get(path)
            if cached is not None and cached.version == self._routes_version:
                if cached.metrics is not None:
                    cached.metrics.cache_hits += 1
                return cached.handler, cached.params

        # Check static routes first (fastest path)
        if method in self.static_routes and path in self.static_routes[method]:
            handler = self.static_routes[method][path]
            self.route_cache[method][path] = CachedRoute(handler, {}, version=self._routes_version)
            return handler, {}

        # Path exists but not for this method
        allowed = self._find_methods(path) - {method}
        if allowed:
            raise MethodNotAllowed(allowed_methods=sorted(allowed))

        # Dynamic route resolution with error handling
        tree = self.method_trees.get(method)
        if not tree:
            raise NotFound(f"Route not found: {path}")

        start_time = time.time()
        current = tree
        params = {}

        try:
            parts = [p for p in path.split("/") if p]

            for part in parts:
                if not part:  # Skip empty parts
                    continue

                if part in current.children:
                    current = current.children[part]
                elif current.param_child:
                    # Check constraints with error handling
                    param_name = current.param_name
                    if param_name and param_name in current.param_child.constraints:
                        constraint = current.param_child.constraints[param_name]
                        try:
                            if not constraint(part):
                                raise NotFound(
                                    f"Route constraint failed for parameter '{param_name}': {part}"
                                )
                        except Exception as e:
                            raise NotFound(
                                f"Route constraint error for parameter '{param_name}': {str(e)}"
                            ) from e

                    if param_name:
                        params[param_name] = part
                    current = current.param_child
                elif current is None:
                    raise NotFound("Route not found: invalid path structure")
                else:
                    raise NotFound(f"Route not found: {path}")
        except Exception as e:
            if isinstance(e, NotFound):
                raise
            raise NotFound(f"Route resolution error: {str(e)}") from e

        if current.is_endpoint and method in current.methods:
            route_handler = current.handler
            if route_handler is None:
                raise NotFound(f"Route not found: {path}")
            handler = route_handler

            # Update metrics
            response_time = time.time() - start_time
            if not hasattr(handler, "__route_metrics__"):
                handler.__route_metrics__ = RouteMetrics()  # type: ignore[attr-defined]
            handler.__route_metrics__.update(response_time)  # type: ignore[attr-defined]

            # Cache result
            self.route_cache[method][path] = CachedRoute(
                handler,
                params.copy(),
                version=self._routes_version,
                metrics=handler.__route_metrics__,  # type: ignore[attr-defined]
            )

            return handler, params

        # Path exists but not for this method
        allowed = self._find_methods(path) - {method}
        if allowed:
            raise MethodNotAllowed(allowed_methods=sorted(allowed))

        raise NotFound(f"Route not found: {path}")

    def _find_methods(self, path: str) -> set[str]:
        """Find all methods registered for a path (static or dynamic)"""
        methods: set[str] = set()

        for method, routes in self.static_routes.items():
            if path in routes:
                methods.add(method)

        if methods:
            return methods

        parts = [p for p in path.split("/") if p]

        for method, tree in self.method_trees.items():
            current = tree
            matched = True

            for part in parts:
                if part in current.children:
                    current = current.children[part]
                elif current.param_child:
                    param_name = current.param_name
                    if param_name and param_name in current.param_child.constraints:
                        constraint = current.param_child.constraints[param_name]
                        try:
                            if not constraint(part):
                                matched = False
                                break
                        except Exception:
                            matched = False
                            break
                    current = current.param_child
                else:
                    matched = False
                    break

            if matched and current.is_endpoint:
                methods.add(method)

        return methods

    def add_middleware(self, middleware: Callable):
        """Add middleware to stack"""
        self.middleware_stack.append(middleware)

    def get_metrics(self) -> dict[str, Any]:
        """Get router performance metrics"""
        total_routes = len(self.static_routes["GET"]) + len(self.static_routes["POST"])
        cache_hit_rate = 0
        total_hits = 0

        for method_routes in self.static_routes.values():
            for handler in method_routes.values():
                if hasattr(handler, "__route_metrics__"):
                    metrics = handler.__route_metrics__
                    total_hits += metrics.hit_count
                    cache_hit_rate += metrics.cache_hits

        return {
            "total_routes": total_routes,
            "cache_size": sum(len(routes) for routes in self.route_cache.values()),
            "cache_hit_rate": cache_hit_rate / max(total_hits, 1) * 100,
            "bloom_filter_size": self.bloom_filter.bit_array_size,
            "average_resolution_time": "< 0.001ms",
        }

    def cleanup_cache(self):
        """Remove expired cache entries"""
        for method, routes in list(self.route_cache.items()):
            expired = [path for path, cached in routes.items() if not cached.is_valid()]
            for path in expired:
                del routes[path]
            if not routes:
                del self.route_cache[method]
