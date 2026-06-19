# Waze MCP Server

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

## Requirements

- **Python 3.10+** (this project was set up with Python 3.13 via Homebrew; the macOS
  system Python 3.9 will **not** work — `pywaze` and `mcp` require 3.10+).

## Setup

The virtual environment is already created in `.venv`. To recreate it from scratch:

```bash
/opt/homebrew/bin/python3.13 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Run

```bash
./.venv/bin/python server.py
```

The server speaks MCP over **stdio**, so it is normally launched by your MCP client
rather than run by hand. Use the configs below.

> Replace the paths if you move the project. The absolute paths assume the current
> location.

### Run over HTTP (remote hosts)

By default the server uses **stdio**. To let a remote host connect over HTTP — for
example Microsoft Scout's **Remote / Local URL** mode — start it with the
`streamable-http` transport:

```bash
./.venv/bin/python server.py --transport streamable-http --host 127.0.0.1 --port 8000
```

The MCP endpoint is then served at `http://<host>:<port>/mcp`. Flags:

- `--transport` — `stdio` (default), `streamable-http`, or `sse`
- `--host` / `--port` — bind address for the HTTP transports (default `127.0.0.1:8000`)

> Exposing the server beyond `localhost` puts an unauthenticated tool endpoint on the
> network. Keep it bound to `127.0.0.1`, or place it behind a tunnel / reverse proxy
> with authentication.

### VS Code

Add to `.vscode/mcp.json` (workspace) or your user `mcp.json`:

```json
{
  "servers": {
    "waze": {
      "type": "stdio",
      "command": "/Users/serge/Library/Mobile Documents/com~apple~CloudDocs/Projects/waze-mcp/.venv/bin/python",
      "args": ["/Users/serge/Library/Mobile Documents/com~apple~CloudDocs/Projects/waze-mcp/server.py"]
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
      "command": "/Users/serge/Library/Mobile Documents/com~apple~CloudDocs/Projects/waze-mcp/.venv/bin/python",
      "args": ["/Users/serge/Library/Mobile Documents/com~apple~CloudDocs/Projects/waze-mcp/server.py"]
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add waze -- \
  "/Users/serge/Library/Mobile Documents/com~apple~CloudDocs/Projects/waze-mcp/.venv/bin/python" \
  "/Users/serge/Library/Mobile Documents/com~apple~CloudDocs/Projects/waze-mcp/server.py"
```

## Notes & caveats

- **Unofficial data source.** Waze has no official public API. `pywaze` calls Waze's
  internal livemap endpoints — the same ones the website uses. They can change or be
  rate-limited without notice, and heavy use may be against Waze's Terms of Service.
- **Regions.** `EU` covers Europe; use `US`/`NA` for North America, `IL` for Israel,
  `AU` for Australia. Default is `EU`.
- **Privacy.** Origin/destination coordinates are sent only to `waze.com`. The
  underlying HTTP client logs request URLs at INFO level to **stderr** (not stdout, so
  it does not interfere with the MCP protocol).

## Credits

- Routing/geocoding by [`pywaze`](https://github.com/eifinger/pywaze) (Kevin Stillhammer),
  based on [WazeRouteCalculator](https://github.com/kovacsbalu/WazeRouteCalculator).
- "Powered by Waze."
