# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub
(**Security → Report a vulnerability**) on this repository. If you cannot use
that, open an issue **without** sensitive details and ask for a private channel.

## Scope and security notes

- The server is **read-only** and needs **no credentials or API key**.
- It calls Waze's **unofficial** public livemap endpoints through the
  [`pywaze`](https://github.com/eifinger/pywaze) library. There is no official
  Waze API; endpoints may change or rate-limit without notice.
- **stdio** transport has no network surface — the MCP client launches it as a
  local subprocess.
- **HTTP** transports (`--transport streamable-http|sse`) expose an endpoint that
  is **unauthenticated by default**. To harden:
  - keep it bound to `127.0.0.1` (the default), and/or
  - set a bearer token via `--auth-token` or `WAZE_MCP_AUTH_TOKEN`, and/or
  - place it behind a reverse proxy with TLS when exposing it beyond localhost.
- The `/health` endpoint is intentionally unauthenticated and returns only `ok`.
