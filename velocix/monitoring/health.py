"""Health check endpoints with comprehensive dependency checking"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from velocix.core.response import JSONResponse

_startup_time = time.time()


class HealthCheck:
    """Health check with custom dependency checks"""

    __slots__ = ("_checks", "_timeout")

    def __init__(self, timeout: float = 5.0) -> None:
        self._checks: dict[str, Callable[[], Awaitable[tuple[bool, dict[str, Any]]]]] = {}
        self._timeout = timeout

    def add_check(
        self, name: str, check_func: Callable[[], Awaitable[tuple[bool, dict[str, Any]]]]
    ) -> None:
        """Add a custom health check"""
        self._checks[name] = check_func

    def remove_check(self, name: str) -> None:
        """Remove a health check"""
        self._checks.pop(name, None)

    async def run_checks(self) -> tuple[bool, dict[str, Any]]:
        """Run all health checks with timeout"""
        results: dict[str, Any] = {}
        all_healthy = True

        async def run_single_check(name: str, check: Callable) -> tuple[str, bool, dict[str, Any]]:
            try:
                is_healthy, details = await asyncio.wait_for(check(), timeout=self._timeout)
                return name, is_healthy, details
            except TimeoutError:
                return name, False, {"error": "Check timeout"}
            except Exception as e:
                return name, False, {"error": str(e)}

        tasks = [run_single_check(name, check) for name, check in self._checks.items()]
        check_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in check_results:
            if isinstance(result, BaseException):
                all_healthy = False
                results["unknown"] = {"status": "unhealthy", "error": str(result)}
            else:
                name, is_healthy, details = result
                if not is_healthy:
                    all_healthy = False
                results[name] = {"status": "healthy" if is_healthy else "unhealthy", **details}

        return all_healthy, results


_global_health_check = HealthCheck()


def get_health_checker() -> HealthCheck:
    """Get global health checker instance"""
    return _global_health_check


async def health_check(request: Any) -> JSONResponse:
    """Basic health check endpoint (liveness probe) - always returns 200"""
    uptime = time.time() - _startup_time

    return JSONResponse(
        {"status": "healthy", "uptime_seconds": round(uptime, 2), "timestamp": time.time()}
    )


async def readiness_check(request: Any) -> JSONResponse:
    """Readiness check (readiness probe) - checks dependencies"""
    checks: dict[str, Any] = {"api": {"status": "ready"}}
    all_ready = True

    app = request.app if hasattr(request, "app") else None

    if app and hasattr(app.state, "websocket_manager"):
        try:
            count = app.state.websocket_manager.get_connection_count()
            checks["websocket"] = {"status": "ready", "connections": count}
        except Exception as e:
            checks["websocket"] = {"status": "unavailable", "error": str(e)}
            all_ready = False

    is_healthy, custom_checks = await _global_health_check.run_checks()
    if custom_checks:
        checks.update(custom_checks)
        if not is_healthy:
            all_ready = False

    status_code = 200 if all_ready else 503
    status = "ready" if all_ready else "not_ready"

    uptime = time.time() - _startup_time

    return JSONResponse(
        {
            "status": status,
            "uptime_seconds": round(uptime, 2),
            "timestamp": time.time(),
            "checks": checks,
        },
        status_code=status_code,
    )


async def startup_check(request: Any) -> JSONResponse:
    """Startup check (startup probe) - indicates if app has started"""
    app = request.app if hasattr(request, "app") else None

    if app and hasattr(app, "_startup_complete") and app._startup_complete:
        return JSONResponse({"status": "started", "timestamp": time.time()})

    return JSONResponse({"status": "starting", "timestamp": time.time()}, status_code=503)


async def detailed_health_check(request: Any) -> JSONResponse:
    """Detailed health check with all metrics"""
    uptime = time.time() - _startup_time

    checks: dict[str, Any] = {"api": {"status": "healthy", "uptime_seconds": round(uptime, 2)}}

    app = request.app if hasattr(request, "app") else None

    if app:
        if hasattr(app.state, "websocket_manager"):
            try:
                count = app.state.websocket_manager.get_connection_count()
                checks["websocket"] = {"status": "healthy", "active_connections": count}
            except Exception as e:
                checks["websocket"] = {"status": "unhealthy", "error": str(e)}

        if hasattr(app.state, "db_pool"):
            try:
                pool = app.state.db_pool
                checks["database"] = {
                    "status": "healthy",
                    "pool_size": getattr(pool, "size", "unknown"),
                }
            except Exception as e:
                checks["database"] = {"status": "unhealthy", "error": str(e)}

        if hasattr(app.state, "cache"):
            try:
                cache = app.state.cache
                checks["cache"] = {"status": "healthy", "type": cache.__class__.__name__}
            except Exception as e:
                checks["cache"] = {"status": "unhealthy", "error": str(e)}

    is_healthy, custom_checks = await _global_health_check.run_checks()
    checks.update(custom_checks)

    all_healthy = all(
        check.get("status") == "healthy" for check in checks.values() if isinstance(check, dict)
    )

    status_code = 200 if all_healthy else 503

    return JSONResponse(
        {
            "status": "healthy" if all_healthy else "unhealthy",
            "uptime_seconds": round(uptime, 2),
            "timestamp": time.time(),
            "checks": checks,
        },
        status_code=status_code,
    )
