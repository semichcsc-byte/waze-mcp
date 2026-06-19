"""Waze MCP server.

Exposes Waze routing / travel-time tools over the Model Context Protocol,
using the free ``pywaze`` library (no API key required). ``pywaze`` talks to
Waze's public livemap endpoints directly — it is the same library that Home
Assistant's "Waze Travel Time" integration uses under the hood.

Tools (all read-only, structured output):
    - get_travel_time : fastest-route duration + distance between two points
    - get_routes      : up to N alternative routes with street names
    - geocode_address : resolve an address to coordinates

Transports: stdio (default) or HTTP (``--transport streamable-http``/``sse``),
the latter with optional bearer-token auth and a ``/health`` endpoint.

Configuration via environment: WAZE_MCP_REGION, WAZE_MCP_TIMEOUT,
WAZE_MCP_CACHE_TTL, WAZE_MCP_AUTH_TOKEN, WAZE_MCP_TRANSPORT/HOST/PORT.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from pywaze import route_calculator
from pywaze.route_calculator import WRCError

# Quiet httpx's INFO request logging — it would otherwise emit full request URLs
# (including origin/destination coordinates) to stderr.
logging.getLogger("httpx").setLevel(logging.WARNING)

mcp = FastMCP("waze")

Vehicle = Literal["car", "taxi", "motorcycle"]

_REGIONS = {"US", "NA", "EU", "IL", "AU"}

# pywaze expects None for a regular car, or an uppercase string otherwise.
_VEHICLE_MAP: dict[str, str | None] = {
    "car": None,
    "taxi": "TAXI",
    "motorcycle": "MOTORCYCLE",
}

# --- Configuration (overridable via environment) ---------------------------
DEFAULT_REGION = os.environ.get("WAZE_MCP_REGION", "EU").upper()
REQUEST_TIMEOUT = float(os.environ.get("WAZE_MCP_TIMEOUT", "60"))
# Cache identical lookups for this many seconds (0 disables). Spares Waze's
# unofficial endpoints when the same query repeats.
CACHE_TTL = float(os.environ.get("WAZE_MCP_CACHE_TTL", "60"))

# Read-only + talks to an external service. Advertised so hosts can safely
# auto-approve: the tools never mutate anything.
_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


# --- Structured output models ----------------------------------------------
class TravelTime(BaseModel):
    """Fastest-route summary."""

    duration_minutes: float = Field(description="Estimated travel time, minutes.")
    distance_km: float = Field(description="Route distance in kilometres.")
    route_name: str = Field(description="Primary road(s) of the route.")


class Route(TravelTime):
    """A single route alternative, including its street list."""

    street_names: list[str] = Field(
        default_factory=list, description="Street names along the route."
    )


class RoutesResult(BaseModel):
    """Container for several route alternatives."""

    routes: list[Route]


class GeocodeResult(BaseModel):
    """Resolved coordinates for an address."""

    lat: float
    lng: float
    bounds: dict[str, float] | None = None


class WazeError(RuntimeError):
    """Raised when a Waze lookup fails or returns no result."""


# --- Tiny in-process TTL cache ---------------------------------------------
_cache: dict[tuple, tuple[float, object]] = {}


def _cache_get(key: tuple) -> object | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    stored_at, value = hit
    if CACHE_TTL <= 0 or (time.monotonic() - stored_at) > CACHE_TTL:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: tuple, value: object) -> None:
    if CACHE_TTL > 0:
        _cache[key] = (time.monotonic(), value)


def _normalize_region(region: str) -> str:
    """Validate and upper-case a region code (US, NA, EU, IL, AU)."""
    code = region.strip().upper()
    if code not in _REGIONS:
        raise ValueError(
            f"Unsupported region '{region}'. Use one of: "
            f"{', '.join(sorted(_REGIONS))}."
        )
    return code


@mcp.tool(annotations=_READ_ONLY)
async def get_travel_time(
    origin: str,
    destination: str,
    region: str = DEFAULT_REGION,
    vehicle_type: Vehicle = "car",
    avoid_toll_roads: bool = False,
    avoid_ferries: bool = False,
    real_time: bool = True,
) -> TravelTime:
    """Calculate travel time and distance for the fastest Waze route.

    ``origin`` and ``destination`` accept either a street address or
    ``"lat,lng"`` coordinates. Returns the single best (fastest) route.
    """
    region_code = _normalize_region(region)
    vehicle = _VEHICLE_MAP.get(vehicle_type.lower())
    key = (
        "tt", origin, destination, region_code, vehicle,
        avoid_toll_roads, avoid_ferries, real_time,
    )
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        async with route_calculator.WazeRouteCalculator(
            region=region_code, timeout=REQUEST_TIMEOUT
        ) as client:
            routes = await client.calc_routes(
                origin,
                destination,
                vehicle_type=vehicle,
                avoid_toll_roads=avoid_toll_roads,
                avoid_ferries=avoid_ferries,
                alternatives=1,
                real_time=real_time,
            )
    except (WRCError, httpx.HTTPError) as exc:
        raise WazeError(f"Waze request failed: {exc}") from exc

    if not routes:
        raise WazeError("No route found between the specified locations.")

    best = routes[0]
    result = TravelTime(
        duration_minutes=round(best.duration, 1),
        distance_km=round(best.distance, 2),
        route_name=best.name,
    )
    _cache_set(key, result)
    return result


@mcp.tool(annotations=_READ_ONLY)
async def get_routes(
    origin: str,
    destination: str,
    region: str = DEFAULT_REGION,
    alternatives: int = 3,
    vehicle_type: Vehicle = "car",
    avoid_toll_roads: bool = False,
    avoid_ferries: bool = False,
    real_time: bool = True,
) -> RoutesResult:
    """Get several alternative Waze routes between two locations.

    Returns up to ``alternatives`` routes (capped at 5), each with duration,
    distance, route name, and the street names along the way.
    """
    region_code = _normalize_region(region)
    vehicle = _VEHICLE_MAP.get(vehicle_type.lower())
    n_paths = min(max(1, alternatives), 5)
    key = (
        "routes", origin, destination, region_code, n_paths, vehicle,
        avoid_toll_roads, avoid_ferries, real_time,
    )
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        async with route_calculator.WazeRouteCalculator(
            region=region_code, timeout=REQUEST_TIMEOUT
        ) as client:
            routes = await client.calc_routes(
                origin,
                destination,
                vehicle_type=vehicle,
                avoid_toll_roads=avoid_toll_roads,
                avoid_ferries=avoid_ferries,
                alternatives=n_paths,
                real_time=real_time,
            )
    except (WRCError, httpx.HTTPError) as exc:
        raise WazeError(f"Waze request failed: {exc}") from exc

    if not routes:
        raise WazeError("No routes found between the specified locations.")

    result = RoutesResult(
        routes=[
            Route(
                duration_minutes=round(r.duration, 1),
                distance_km=round(r.distance, 2),
                route_name=r.name,
                street_names=r.street_names,
            )
            for r in routes
        ]
    )
    _cache_set(key, result)
    return result


@mcp.tool(annotations=_READ_ONLY)
async def geocode_address(address: str, region: str = DEFAULT_REGION) -> GeocodeResult:
    """Resolve a street address to geographic coordinates using Waze."""
    region_code = _normalize_region(region)
    key = ("geo", address, region_code)
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        async with route_calculator.WazeRouteCalculator(
            region=region_code, timeout=REQUEST_TIMEOUT
        ) as client:
            coords = await client.address_to_coords(address)
    except (WRCError, httpx.HTTPError) as exc:
        raise WazeError(f"Waze request failed: {exc}") from exc

    result = GeocodeResult(
        lat=coords["lat"], lng=coords["lon"], bounds=coords.get("bounds") or None
    )
    _cache_set(key, result)
    return result


def _build_http_app(transport: str, token: str | None):
    """Build the Starlette app for an HTTP transport, adding a ``/health``
    endpoint and (when ``token`` is set) bearer-token authentication."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse
    from starlette.routing import Route

    app = (
        mcp.streamable_http_app()
        if transport == "streamable-http"
        else mcp.sse_app()
    )

    async def health(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app.router.routes.append(Route("/health", health, methods=["GET"]))

    if token:
        expected = f"Bearer {token}"

        class _BearerAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.url.path == "/health":
                    return await call_next(request)
                if request.headers.get("authorization") != expected:
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
                return await call_next(request)

        app.add_middleware(_BearerAuth)

    return app


def main() -> None:
    """Run the MCP server.

    Defaults to stdio (how MCP clients normally launch it). Pass
    ``--transport streamable-http`` (or ``sse``) to serve over HTTP so a
    remote host — e.g. Microsoft Scout's "Remote / Local URL" mode — can
    connect. For HTTP, optionally require a bearer token via ``--auth-token``
    or ``WAZE_MCP_AUTH_TOKEN``; a ``/health`` endpoint is always available.
    """
    parser = argparse.ArgumentParser(description="Waze MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=os.environ.get("WAZE_MCP_TRANSPORT", "stdio"),
        help="Transport to use (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("WAZE_MCP_HOST", "127.0.0.1"),
        help="Bind host for HTTP transports (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WAZE_MCP_PORT", "8000")),
        help="Bind port for HTTP transports (default: 8000).",
    )
    parser.add_argument(
        "--auth-token",
        default=None,
        help=(
            "Require this bearer token on HTTP requests "
            "(or set WAZE_MCP_AUTH_TOKEN). stdio is unaffected."
        ),
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    token = args.auth_token or os.environ.get("WAZE_MCP_AUTH_TOKEN")
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    import uvicorn

    app = _build_http_app(args.transport, token)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
