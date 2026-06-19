"""Unit tests for the Waze MCP server.

``pywaze`` is fully mocked, so these run offline (no calls to Waze).
"""

from __future__ import annotations

import pytest
from pywaze.route_calculator import CalcRoutesResponse, WRCError

import server


class _FakeClient:
    """Stand-in for pywaze's WazeRouteCalculator async context manager."""

    def __init__(self, *, routes=None, coords=None, error=None):
        self._routes = routes if routes is not None else []
        self._coords = coords
        self._error = error
        self.calls = 0
        self.last_kwargs: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def calc_routes(self, *args, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._routes

    async def address_to_coords(self, *args, **kwargs):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._coords


@pytest.fixture(autouse=True)
def _clear_cache():
    server._cache.clear()
    yield
    server._cache.clear()


def _patch(monkeypatch, **kwargs) -> _FakeClient:
    fake = _FakeClient(**kwargs)
    monkeypatch.setattr(
        server.route_calculator, "WazeRouteCalculator", lambda **_: fake
    )
    return fake


def _route(duration, distance, name, streets=()):
    return CalcRoutesResponse(
        duration=duration,
        distance=distance,
        name=name,
        street_names=list(streets),
    )


async def test_get_travel_time_returns_best_route(monkeypatch):
    _patch(monkeypatch, routes=[_route(24.93, 26.37, "A5", ["A5"])])
    result = await server.get_travel_time("a", "b", region="EU")
    assert result.duration_minutes == 24.9
    assert result.distance_km == 26.37
    assert result.route_name == "A5"


async def test_get_routes_caps_alternatives(monkeypatch):
    fake = _patch(monkeypatch, routes=[_route(10, 5, "A1"), _route(12, 6, "A2")])
    result = await server.get_routes("a", "b", alternatives=99)
    assert len(result.routes) == 2
    assert fake.last_kwargs["alternatives"] == 5  # capped before the request


async def test_geocode_normalises_empty_bounds(monkeypatch):
    _patch(monkeypatch, coords={"lat": 41.0, "lon": -8.0, "bounds": {}})
    result = await server.geocode_address("Porto")
    assert result.lat == 41.0
    assert result.lng == -8.0
    assert result.bounds is None


async def test_invalid_region_raises(monkeypatch):
    _patch(monkeypatch, routes=[_route(1, 1, "x")])
    with pytest.raises(ValueError, match="Unsupported region"):
        await server.get_travel_time("a", "b", region="ZZ")


async def test_no_route_raises(monkeypatch):
    _patch(monkeypatch, routes=[])
    with pytest.raises(server.WazeError):
        await server.get_travel_time("a", "b", region="EU")


async def test_backend_error_is_wrapped(monkeypatch):
    _patch(monkeypatch, error=WRCError("boom"))
    with pytest.raises(server.WazeError):
        await server.get_travel_time("a", "b", region="EU")


async def test_results_are_cached(monkeypatch):
    fake = _patch(monkeypatch, routes=[_route(10, 5, "A1")])
    await server.get_travel_time("a", "b", region="EU")
    await server.get_travel_time("a", "b", region="EU")
    assert fake.calls == 1  # second call served from cache


async def test_tools_registered_and_read_only():
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {"get_travel_time", "get_routes", "geocode_address"}
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
