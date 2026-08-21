"""Tests for opt-in route metrics.

Per-route metrics (hit counts, avg response time) are disabled by default
so the hot path skips the per-request counter mutation; enabling them via
Router(metrics_enabled=True) restores the tracking for get_metrics().
"""

from velocix import Router


def test_metrics_disabled_by_default():
    router = Router()

    def handler():
        return {}

    router.add_route("GET", "/users/{user_id}", handler)

    # First resolve populates the cache without attaching metrics
    router.resolve("GET", "/users/1")
    cached = router.route_cache["GET"]["/users/1"]
    assert cached.metrics is None

    # Cache hits must not accumulate counters
    router.resolve("GET", "/users/2")
    router.resolve("GET", "/users/3")
    assert router.get_metrics()["cache_hit_rate"] == 0
    assert router.get_metrics()["total_routes"] == 0  # only static routes counted


def test_metrics_enabled_tracks_hits():
    router = Router(metrics_enabled=True)

    def handler():
        return {}

    router.add_route("GET", "/users/{user_id}", handler)

    router.resolve("GET", "/users/1")
    first = router.route_cache["GET"]["/users/1"]
    assert first.metrics is not None

    # Warm the cache for /users/2 (first resolve is a miss), then each
    # subsequent resolve increments the cache-hit counter
    router.resolve("GET", "/users/2")
    for _ in range(4):
        router.resolve("GET", "/users/2")
    cached = router.route_cache["GET"]["/users/2"]
    assert cached.metrics is not None
    assert cached.metrics.hit_count >= 1
    assert cached.metrics.cache_hits == 4


def test_metrics_enabled_static_routes():
    router = Router(metrics_enabled=True)

    def handler():
        return {}

    router.add_route("GET", "/static", handler)
    router.resolve("GET", "/static")
    cached = router.route_cache["GET"]["/static"]
    # Static-route cache entries are created at registration with no metrics
    assert cached.metrics is None
