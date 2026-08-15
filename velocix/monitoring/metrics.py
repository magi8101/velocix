"""Prometheus metrics integration with comprehensive tracking"""

import time
from collections import defaultdict
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from velocix.core.middleware import BaseMiddleware
from velocix.core.response import Response

REQUEST_COUNT = Counter(
    "velocix_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

REQUEST_DURATION = Histogram(
    "velocix_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

REQUEST_IN_PROGRESS = Gauge(
    "velocix_http_requests_in_progress", "HTTP requests currently being processed", ["method"]
)

REQUEST_SIZE = Histogram(
    "velocix_http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "endpoint"],
    buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
)

RESPONSE_SIZE = Histogram(
    "velocix_http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "endpoint", "status"],
    buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
)

ERROR_COUNT = Counter(
    "velocix_http_errors_total", "Total HTTP errors", ["method", "endpoint", "exception", "status"]
)

WEBSOCKET_CONNECTIONS = Gauge(
    "velocix_websocket_connections_active", "Active WebSocket connections"
)

WEBSOCKET_MESSAGES = Counter(
    "velocix_websocket_messages_total", "Total WebSocket messages", ["direction", "type"]
)

WEBSOCKET_ERRORS = Counter(
    "velocix_websocket_errors_total", "Total WebSocket errors", ["error_type"]
)

DEPENDENCY_DURATION = Histogram(
    "velocix_dependency_duration_seconds",
    "Dependency resolution duration",
    ["dependency"],
    buckets=(0.0001, 0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1),
)

CACHE_OPERATIONS = Counter(
    "velocix_cache_operations_total", "Total cache operations", ["operation", "result"]
)

MIDDLEWARE_DURATION = Histogram(
    "velocix_middleware_duration_seconds",
    "Middleware execution duration",
    ["middleware"],
    buckets=(0.0001, 0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1),
)

RATE_LIMIT_HITS = Counter(
    "velocix_rate_limit_hits_total", "Total rate limit hits", ["key", "limit_type"]
)

APP_INFO = Info("velocix_app", "Velocix application information")


class MetricsCollector:
    """Advanced metrics collector with aggregation"""

    __slots__ = ("_request_times", "_endpoint_stats", "_enabled")

    def __init__(self, enabled: bool = True) -> None:
        self._request_times: dict[str, list[float]] = defaultdict(list)
        self._endpoint_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"count": 0, "errors": 0}
        )
        self._enabled = enabled

    def record_request_time(self, endpoint: str, duration: float) -> None:
        """Record request timing"""
        if not self._enabled:
            return

        times = self._request_times[endpoint]
        times.append(duration)

        if len(times) > 1000:
            times.pop(0)

    def record_endpoint_call(self, endpoint: str, is_error: bool = False) -> None:
        """Record endpoint call"""
        if not self._enabled:
            return

        stats = self._endpoint_stats[endpoint]
        stats["count"] += 1
        if is_error:
            stats["errors"] += 1

    def get_percentile(self, endpoint: str, percentile: float) -> float | None:
        """Get percentile for endpoint"""
        times = self._request_times.get(endpoint, [])
        if not times:
            return None

        sorted_times = sorted(times)
        index = int(len(sorted_times) * percentile)
        return sorted_times[min(index, len(sorted_times) - 1)]

    def get_endpoint_stats(self, endpoint: str) -> dict[str, Any]:
        """Get endpoint statistics"""
        stats = self._endpoint_stats.get(endpoint, {"count": 0, "errors": 0})
        times = self._request_times.get(endpoint, [])

        if not times:
            return {"count": stats["count"], "errors": stats["errors"], "error_rate": 0.0}

        return {
            "count": stats["count"],
            "errors": stats["errors"],
            "error_rate": stats["errors"] / stats["count"] if stats["count"] > 0 else 0.0,
            "avg_duration": sum(times) / len(times),
            "p50": self.get_percentile(endpoint, 0.5),
            "p95": self.get_percentile(endpoint, 0.95),
            "p99": self.get_percentile(endpoint, 0.99),
        }

    def reset(self) -> None:
        """Reset all metrics"""
        self._request_times.clear()
        self._endpoint_stats.clear()


_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector"""
    return _metrics_collector


class MetricsMiddleware(BaseMiddleware):
    """Middleware for collecting comprehensive HTTP metrics"""

    __slots__ = ("app", "_track_sizes", "_track_in_progress", "_collector", "_exclude_paths")

    def __init__(
        self,
        app: Any,
        track_sizes: bool = True,
        track_in_progress: bool = True,
        collector: MetricsCollector | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._track_sizes = track_sizes
        self._track_in_progress = track_in_progress
        self._collector = collector or _metrics_collector
        self._exclude_paths = set(exclude_paths or ["/metrics", "/health"])

    async def __call__(self, request: Any) -> Any:
        """Collect request metrics"""
        path = request.path

        if path in self._exclude_paths:
            return await self.app(request)

        method = request.method

        if self._track_in_progress:
            REQUEST_IN_PROGRESS.labels(method=method).inc()

        start_time = time.perf_counter_ns()

        try:
            if self._track_sizes and hasattr(request, "headers"):
                content_length = request.headers.get(b"content-length")
                if content_length:
                    try:
                        size = int(content_length.decode())
                        endpoint = self._normalize_endpoint(path)
                        REQUEST_SIZE.labels(method=method, endpoint=endpoint).observe(size)
                    except (ValueError, UnicodeDecodeError):
                        pass

            response = await self.app(request)

            duration_seconds = (time.perf_counter_ns() - start_time) / 1_000_000_000

            endpoint = self._normalize_endpoint(path)
            status = str(response.status_code)

            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration_seconds)

            self._collector.record_request_time(endpoint, duration_seconds)
            self._collector.record_endpoint_call(endpoint, is_error=False)

            if self._track_sizes and hasattr(response, "body") and response.body:
                RESPONSE_SIZE.labels(method=method, endpoint=endpoint, status=status).observe(
                    len(response.body)
                )

            return response

        except Exception as exc:
            duration_seconds = (time.perf_counter_ns() - start_time) / 1_000_000_000

            endpoint = self._normalize_endpoint(path)
            status = "500"

            ERROR_COUNT.labels(
                method=method, endpoint=endpoint, exception=exc.__class__.__name__, status=status
            ).inc()

            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration_seconds)

            self._collector.record_request_time(endpoint, duration_seconds)
            self._collector.record_endpoint_call(endpoint, is_error=True)

            raise

        finally:
            if self._track_in_progress:
                REQUEST_IN_PROGRESS.labels(method=method).dec()

    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for metrics (reduce cardinality)"""
        if path == "/":
            return "/"

        if path.startswith("/api/"):
            parts = path.split("/")
            if len(parts) > 4:
                return "/".join(parts[:4]) + "/*"

        parts = path.split("/")
        if len(parts) > 3:
            return "/".join(parts[:3]) + "/*"

        return path


def metrics_endpoint(request: Any) -> Response:
    """Endpoint for Prometheus scraping with custom metrics"""
    metrics = generate_latest(REGISTRY)
    return Response(content=metrics, media_type=CONTENT_TYPE_LATEST)


def update_websocket_metrics(count: int) -> None:
    """Update WebSocket connection count"""
    WEBSOCKET_CONNECTIONS.set(count)


def record_websocket_message(direction: str, message_type: str = "text") -> None:
    """Record WebSocket message with type"""
    WEBSOCKET_MESSAGES.labels(direction=direction, type=message_type).inc()


def record_websocket_error(error_type: str) -> None:
    """Record WebSocket error"""
    WEBSOCKET_ERRORS.labels(error_type=error_type).inc()


def record_dependency_duration(dependency: str, duration: float) -> None:
    """Record dependency resolution duration"""
    DEPENDENCY_DURATION.labels(dependency=dependency).observe(duration)


def record_cache_operation(operation: str, result: str) -> None:
    """Record cache operation (hit/miss)"""
    CACHE_OPERATIONS.labels(operation=operation, result=result).inc()


def record_middleware_duration(middleware: str, duration: float) -> None:
    """Record middleware execution duration"""
    MIDDLEWARE_DURATION.labels(middleware=middleware).observe(duration)


def record_rate_limit_hit(key: str, limit_type: str) -> None:
    """Record rate limit hit"""
    RATE_LIMIT_HITS.labels(key=key, limit_type=limit_type).inc()


def set_app_info(version: str, **kwargs: str) -> None:
    """Set application information"""
    info = {"version": version}
    info.update(kwargs)
    APP_INFO.info(info)


class MetricsExporter:
    """Export metrics in various formats"""

    @staticmethod
    def export_prometheus() -> bytes:
        """Export in Prometheus format"""
        return generate_latest(REGISTRY)

    @staticmethod
    def export_json() -> dict[str, Any]:
        """Export metrics as JSON"""
        metrics: dict[str, Any] = {}

        for family in REGISTRY.collect():
            for sample in family.samples:
                key = f"{sample.name}"
                if sample.labels:
                    label_str = ",".join(f"{k}={v}" for k, v in sample.labels.items())
                    key = f"{key}{{{label_str}}}"

                metrics[key] = sample.value

        return metrics

    @staticmethod
    def get_summary() -> dict[str, Any]:
        """Get metrics summary"""
        collector = get_metrics_collector()

        return {
            "endpoints": {
                endpoint: collector.get_endpoint_stats(endpoint)
                for endpoint in list(collector._endpoint_stats.keys())
            }
        }


async def metrics_json_endpoint(request: Any) -> Response:
    """JSON metrics endpoint"""
    from velocix.core.response import JSONResponse

    exporter = MetricsExporter()
    metrics = exporter.export_json()

    return JSONResponse(metrics)


async def metrics_summary_endpoint(request: Any) -> Response:
    """Metrics summary endpoint"""
    from velocix.core.response import JSONResponse

    exporter = MetricsExporter()
    summary = exporter.get_summary()

    return JSONResponse(summary)
