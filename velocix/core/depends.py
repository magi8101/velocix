"""
Dependency injection system with FastAPI/Starlette-inspired patterns.
Provides efficient dependency resolution with caching and async support.
"""

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

# Signature cache for performance
_sig_cache: dict[int, inspect.Signature] = {}
_type_hints_cache: dict[int, dict[str, Any]] = {}
# Precomputed resolution plan per handler: (plan, needs_request_flag)
# plan: tuple of (param_name, kind, extra)
# kind: "request" | "depends" | "path" ; extra: Depends instance or type hint
_plan_cache: dict[int, tuple[tuple[tuple[str, str, Any], ...], bool]] = {}

T = TypeVar("T")


class Depends:
    """
    Dependency marker with caching support (FastAPI pattern).

    Usage:
        async def get_db(request: Request):
            return Database()

        @app.get("/users")
        async def get_users(db: Database = Depends(get_db)):
            return await db.fetch_all()

    Args:
        dependency: Callable that returns the dependency
        use_cache: Whether to cache the result per request (default: True)
    """

    __slots__ = ("dependency", "use_cache", "_is_async")

    def __init__(self, dependency: Callable[..., Any], *, use_cache: bool = True) -> None:
        self.dependency = dependency
        self.use_cache = use_cache
        self._is_async = asyncio.iscoroutinefunction(dependency)

    def __repr__(self) -> str:
        dep_name = getattr(self.dependency, "__name__", repr(self.dependency))
        return f"Depends({dep_name}, use_cache={self.use_cache})"

    @property
    def is_async(self) -> bool:
        """Check if dependency is async"""
        return self._is_async


def _get_signature(func: Callable[..., Any]) -> inspect.Signature:
    """Get cached function signature"""
    func_id = id(func)
    if func_id not in _sig_cache:
        _sig_cache[func_id] = inspect.signature(func)
    return _sig_cache[func_id]


def _get_type_hints_cached(func: Callable[..., Any]) -> dict[str, Any]:
    """Get cached type hints"""
    func_id = id(func)
    if func_id not in _type_hints_cache:
        try:
            _type_hints_cache[func_id] = get_type_hints(func)
        except Exception:
            _type_hints_cache[func_id] = {}
    return _type_hints_cache[func_id]


def get_resolution_plan(handler: Callable[..., Any]) -> tuple[tuple[str, str, Any], ...]:
    """Return the cached per-handler resolution plan (built on first call)."""
    return _build_resolution_plan(handler)


def get_plan_and_needs_request(
    handler: Callable[..., Any],
) -> tuple[tuple[tuple[str, str, Any], ...], bool]:
    """One cached lookup returning (plan, needs_request_flag)."""
    func_id = id(handler)
    entry = _plan_cache.get(func_id)
    if entry is None:
        _build_resolution_plan(handler)
        entry = _plan_cache[func_id]
    return entry


def _build_resolution_plan(handler: Callable[..., Any]) -> tuple[tuple[str, str, Any], ...]:
    """Precompute the per-handler resolution plan once, then cache it."""
    func_id = id(handler)
    entry = _plan_cache.get(func_id)
    if entry is None:
        sig = _get_signature(handler)
        type_hints = _get_type_hints_cached(handler)
        plan: list[tuple[str, str, Any]] = []
        for param_name, param in sig.parameters.items():
            # Skip self and cls parameters
            if param_name in ("self", "cls"):
                continue
            # Inject request object
            if param_name == "request":
                plan.append((param_name, "request", None))
            # Handle Depends() marker
            elif isinstance(param.default, Depends):
                plan.append((param_name, "depends", param.default))
            # Path parameter with type conversion
            else:
                plan.append((param_name, "path", type_hints.get(param_name)))
        plan_tuple = tuple(plan)
        needs_request = any(kind in ("request", "depends") for _, kind, _ in plan_tuple)
        entry = (plan_tuple, needs_request)
        _plan_cache[func_id] = entry
    return entry[0]


async def resolve_dependencies(
    handler: Callable[..., Any],
    request: Any,
    path_params: dict[str, Any] | None = None,
    plan: tuple[tuple[str, str, Any], ...] | None = None,
) -> dict[str, Any]:
    """
    Resolve dependencies from function signature (FastAPI pattern).

    Supports:
    - Request parameter injection
    - Path parameter injection with type conversion
    - Depends() marker for dependency injection
    - Async and sync dependencies
    - Per-request caching

    The resolution plan is precomputed once per handler, so handlers with no
    parameters (or only "request") skip all per-request signature work.
    Callers with the plan already in hand pass it in to avoid the lookup.

    Args:
        handler: Route handler function
        request: Request object
        path_params: Path parameters from URL
        plan: Precomputed resolution plan (optional)

    Returns:
        Dictionary of resolved dependencies
    """
    plan = _build_resolution_plan(handler) if plan is None else plan
    if not plan:
        return {}

    kwargs: dict[str, Any] = {}
    path_params = path_params or {}
    dep_cache: dict[str, Any] | None = None

    for param_name, kind, extra in plan:
        # Inject request object
        if kind == "request":
            kwargs[param_name] = request
            continue

        # Handle Depends() marker
        if kind == "depends":
            dep: Depends = extra
            # Initialize dependency cache on request state (lazily)
            if dep_cache is None:
                if not hasattr(request.state, "_depends_cache"):
                    request.state._depends_cache = {}
                dep_cache = request.state._depends_cache
            cache_key = f"_dep_{id(dep.dependency)}"

            # Use cached value if available
            if dep.use_cache and cache_key in dep_cache:
                kwargs[param_name] = dep_cache[cache_key]
            else:
                # Resolve dependency
                if dep.is_async:
                    result = await dep.dependency(request)
                else:
                    result = dep.dependency(request)

                # Cache if enabled
                if dep.use_cache:
                    dep_cache[cache_key] = result

                kwargs[param_name] = result
            continue

        # Inject path parameters with type conversion
        if param_name in path_params:
            raw_value = path_params[param_name]
            param_type = extra

            if param_type is not None:
                try:
                    # Type conversion
                    if param_type is int:
                        kwargs[param_name] = int(raw_value)
                    elif param_type is float:
                        kwargs[param_name] = float(raw_value)
                    elif param_type is bool:
                        kwargs[param_name] = raw_value.lower() in ("true", "1", "yes")
                    else:
                        kwargs[param_name] = raw_value
                except (ValueError, AttributeError):
                    # If conversion fails, use raw value
                    kwargs[param_name] = raw_value
            else:
                kwargs[param_name] = raw_value

    return kwargs


class DependencyCache:
    """
    Request-scoped dependency cache (FastAPI pattern).
    Automatically managed by resolve_dependencies.
    """

    __slots__ = ("_cache",)

    def __init__(self):
        self._cache: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get cached dependency"""
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Cache dependency"""
        self._cache[key] = value

    def clear(self) -> None:
        """Clear all cached dependencies"""
        self._cache.clear()

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __len__(self) -> int:
        return len(self._cache)


def inject(dependency: Callable[..., T]) -> T:
    """
    Type-safe dependency injection helper.

    Usage:
        async def get_db() -> Database:
            return Database()

        @app.get("/users")
        async def get_users(db: Database = inject(get_db)):
            return await db.fetch_all()

    This is a type-safe alternative to Depends() that works better
    with type checkers like mypy.
    """
    return Depends(dependency)  # type: ignore


# Cleanup old cache entries to prevent memory leaks
def cleanup_caches(max_size: int = 1000) -> None:
    """Clean up signature and type hints caches"""
    global _sig_cache, _type_hints_cache, _plan_cache

    if len(_sig_cache) > max_size:
        # Keep most recent entries
        sig_items = list(_sig_cache.items())
        _sig_cache = dict(sig_items[-max_size:])

    if len(_type_hints_cache) > max_size:
        hints_items = list(_type_hints_cache.items())
        _type_hints_cache = dict(hints_items[-max_size:])

    if len(_plan_cache) > max_size:
        plan_items = list(_plan_cache.items())
        _plan_cache = dict(plan_items[-max_size:])
