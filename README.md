# Waze MCP Server

[![CI](https://github.com/semichcsc-byte/waze-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/semichcsc-byte/waze-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A small [Model Context Protocol](https://modelcontextprotocol.io) server that exposes
**Waze** routing and travel-time tools to MCP clients (Claude Desktop, Claude Code,
VS Code, Cursor, …).

It uses the free [`pywaze`](https://github.com/eifinger/pywaze) library, which talks to
Waze's public livemap endpoints directly — the **same library Home Assistant's
"Waze Travel Time" integration uses**. No API key, no third-party proxy, no cost.

## Tools

| Tool | Description |
|------|-------------|
| `get_travel_time` | Fastest-route duration + distance between two locations |
| `get_routes` | Up to N alternative routes, each with street names |
| `geocode_address` | Resolve an address to latitude/longitude |

`origin` / `destination` accept a street address **or** `"lat,lng"` coordinates.
Optional params: `region` (US, NA, EU, IL, AU), `vehicle_type` (car, taxi, motorcycle),
`avoid_toll_roads`, `avoid_ferries`, `real_time`.

All tools are **read-only** (advertised via MCP tool annotations) and return
**structured output** (typed JSON). Identical lookups are cached briefly to spare
Waze's endpoints (see [Configuration](#configuration)).

## Requirements

- **Python 3.10+** — `pywaze` and `mcp` require it. (On macOS the system Python 3.9
  will not work; install a newer one, e.g. via Homebrew or python.org.)

## Setup

```bash
python3 -m venv .venv          # use a Python 3.10+ interpreter
./.venv/bin/pip install -r requirements.txt
```

Or install it as a package (uses `pyproject.toml`), which also adds a `waze-mcp`
command:

```bash
./.venv/bin/pip install -e .
```

> On Windows, the interpreter is `.venv\Scripts\python.exe` instead of
> `.venv/bin/python`.

## Configuration

All settings are optional and set via environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `WAZE_MCP_REGION` | `EU` | Default region (`US`/`NA`/`EU`/`IL`/`AU`) when a call omits it |
| `WAZE_MCP_TIMEOUT` | `60` | Per-request timeout (seconds) to Waze |
| `WAZE_MCP_CACHE_TTL` | `60` | Seconds to cache identical lookups (`0` disables) |
| `WAZE_MCP_AUTH_TOKEN` | — | If set, HTTP requests must send `Authorization: Bearer <token>` |
| `WAZE_MCP_TRANSPORT` | `stdio` | Default transport (`stdio`/`streamable-http`/`sse`) |
| `WAZE_MCP_HOST` / `WAZE_MCP_PORT` | `127.0.0.1` / `8000` | HTTP bind address |

CLI flags (`--transport`, `--host`, `--port`, `--auth-token`) override the
matching environment variable.

## Run

```bash
./.venv/bin/python server.py
```

The server speaks MCP over **stdio**, so it is normally launched by your MCP client
rather than run by hand. Use the configs below.

> In the client configs below, replace `/path/to/waze-mcp` with the absolute path to
> your clone.

### Run over HTTP (remote hosts)

By default the server uses **stdio**. To let a remote host connect over HTTP — for
example Microsoft Scout's **Remote / Local URL** mode — start it with the
`streamable-http` transport:

```bash
./.venv/bin/python server.py --transport streamable-http --host 127.0.0.1 --port 8000
```

The MCP endpoint is served at `http://<host>:<port>/mcp`, and an unauthenticated
`http://<host>:<port>/health` endpoint returns `ok` for liveness checks.

**Optional bearer-token auth** — require a token on every request (the `/health`
endpoint stays open):

```bash
WAZE_MCP_AUTH_TOKEN=secret \
  ./.venv/bin/python server.py --transport streamable-http --host 0.0.0.0 --port 8000
# or pass --auth-token secret
```

Clients then send `Authorization: Bearer secret` (e.g. Scout's *Bearer token* field).

> Without a token the HTTP endpoint is unauthenticated. Keep it bound to `127.0.0.1`,
> or set a token and/or place it behind a reverse proxy with TLS when exposing it
> beyond localhost.

### Docker

```bash
docker build -t waze-mcp .
docker run -p 8000:8000 waze-mcp                                 # http://localhost:8000/mcp
docker run -p 8000:8000 -e WAZE_MCP_AUTH_TOKEN=secret waze-mcp   # with auth
```

The image runs the `streamable-http` transport on `0.0.0.0:8000` and ships a
`/health` healthcheck.

### VS Code

Add to `.vscode/mcp.json` (workspace) or your user `mcp.json`:

```json
{
  "servers": {
    "waze": {
      "type": "stdio",
      "command": "/path/to/waze-mcp/.venv/bin/python",
      "args": ["/path/to/waze-mcp/server.py"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "waze": {
      "command": "/path/to/waze-mcp/.venv/bin/python",
      "args": ["/path/to/waze-mcp/server.py"]
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add waze -- \
  "/path/to/waze-mcp/.venv/bin/python" \
  "/path/to/waze-mcp/server.py"
```

## Notes & caveats

- **Unofficial data source.** Waze has no official public API. `pywaze` calls Waze's
  internal livemap endpoints — the same ones the website uses. They can change or be
  rate-limited without notice, and heavy use may be against Waze's Terms of Service.
- **Regions.** `EU` covers Europe; use `US`/`NA` for North America, `IL` for Israel,
  `AU` for Australia. Default is `EU`.
- **Privacy.** Origin/destination coordinates are sent only to `waze.com`. The
  HTTP client's request logging is quieted to `WARNING`, so addresses/coordinates are
  not written to the logs by default.

## Development

```bash
./.venv/bin/pip install -e ".[dev]"   # pytest, pytest-asyncio, ruff
./.venv/bin/ruff check .
./.venv/bin/pytest -q                  # tests mock Waze — no network needed
```

See [CONTRIBUTING.md](CONTRIBUTING.md). CI runs ruff + pytest on Python 3.10–3.13.

## Security

The server is read-only and needs no credentials. For the HTTP transport's auth and
hardening notes, see [SECURITY.md](SECURITY.md).

## Credits

- Routing/geocoding by [`pywaze`](https://github.com/eifinger/pywaze) (Kevin Stillhammer),
  based on [WazeRouteCalculator](https://github.com/kovacsbalu/WazeRouteCalculator).
- "Powered by Waze."

## License

[MIT](LICENSE) © 2026 Serge Michaux
