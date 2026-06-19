"""Waze MCP server.

Exposes Waze routing / travel-time tools over the Model Context Protocol,
using the free ``pywaze`` library (no API key required). ``pywaze`` talks to
Waze's public livemap endpoints directly — it is the same library that Home
Assistant's "Waze Travel Time" integration uses under the hood.

Tools:
    - get_travel_time : fastest-route duration + distance between two points
    - get_routes      : up to N alternative routes with street names
    - geocode_address : resolve an address to coordinates

Transport: stdio (run with ``python server.py``).
"""

from __future__ import annotations

import argparse
import logging
from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP
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


def _normalize_region(region: str) -> str:
    """Validate and upper-case a region code (US, NA, EU, IL, AU)."""
    code = region.strip().upper()
    if code not in _REGIONS:
        raise ValueError(
            f"Unsupported region '{region}'. Use one of: "
            f"{', '.join(sorted(_REGIONS))}."
        )
    return code


@mcp.tool()
async def get_travel_time(
    origin: str,
    destination: str,
    region: str = "EU",
    vehicle_type: Vehicle = "car",
    avoid_toll_roads: bool = False,
    avoid_ferries: bool = False,
    real_time: bool = True,
) -> dict:
    """Calculate travel time and distance for the fastest Waze route.

    ``origin`` and ``destination`` accept either a street address or
    ``"lat,lng"`` coordinates. Returns the single best (fastest) route.
    """
    try:
        region_code = _normalize_region(region)
        vehicle = _VEHICLE_MAP.get(vehicle_type.lower())
        async with route_calculator.WazeRouteCalculator(region=region_code) as client:
            routes = await client.calc_routes(
                origin,
                destination,
                vehicle_type=vehicle,
                avoid_toll_roads=avoid_toll_roads,
                avoid_ferries=avoid_ferries,
                alternatives=1,
                real_time=real_time,
            )
    except (WRCError, ValueError, httpx.HTTPError) as exc:
        return {"error": str(exc)}

    if not routes:
        return {"error": "No route found between the specified locations."}

    best = routes[0]
    return {
        "duration_minutes": round(best.duration, 1),
        "distance_km": round(best.distance, 2),
        "route_name": best.name,
    }


@mcp.tool()
async def get_routes(
    origin: str,
    destination: str,
    region: str = "EU",
    alternatives: int = 3,
    vehicle_type: Vehicle = "car",
    avoid_toll_roads: bool = False,
    avoid_ferries: bool = False,
    real_time: bool = True,
) -> dict:
    """Get several alternative Waze routes between two locations.

    Returns up to ``alternatives`` routes (capped at 5), each with duration,
    distance, route name, and the street names along the way.
    """
    try:
        region_code = _normalize_region(region)
        vehicle = _VEHICLE_MAP.get(vehicle_type.lower())
        async with route_calculator.WazeRouteCalculator(region=region_code) as client:
            routes = await client.calc_routes(
                origin,
                destination,
                vehicle_type=vehicle,
                avoid_toll_roads=avoid_toll_roads,
                avoid_ferries=avoid_ferries,
                alternatives=min(max(1, alternatives), 5),
                real_time=real_time,
            )
    except (WRCError, ValueError, httpx.HTTPError) as exc:
        return {"error": str(exc)}

    if not routes:
        return {"error": "No routes found between the specified locations."}

    return {
        "routes": [
            {
                "duration_minutes": round(r.duration, 1),
                "distance_km": round(r.distance, 2),
                "route_name": r.name,
                "street_names": r.street_names,
            }
            for r in routes
        ]
    }


@mcp.tool()
async def geocode_address(address: str, region: str = "EU") -> dict:
    """Resolve a street address to geographic coordinates using Waze."""
    try:
        region_code = _normalize_region(region)
        async with route_calculator.WazeRouteCalculator(region=region_code) as client:
            coords = await client.address_to_coords(address)
    except (WRCError, ValueError, httpx.HTTPError) as exc:
        return {"error": str(exc)}

    return {
        "lat": coords["lat"],
        "lng": coords["lon"],
        "bounds": coords.get("bounds") or None,
    }


def main() -> None:
    """Run the MCP server.

    Defaults to stdio (how MCP clients normally launch it). Pass
    ``--transport streamable-http`` (or ``sse``) to serve over HTTP so a
    remote host — e.g. Microsoft Scout's "Remote / Local URL" mode — can
    connect. Use ``--host``/``--port`` to control the HTTP bind address.
    """
    parser = argparse.ArgumentParser(description="Waze MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Transport to use (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for HTTP transports (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port for HTTP transports (default: 8000).",
    )
    args = parser.parse_args()

    if args.transport != "stdio":
        mcp.settings.host = args.host
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
