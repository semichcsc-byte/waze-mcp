# Waze MCP server — container image (HTTP transport).
#
# Build:  docker build -t waze-mcp .
# Run:    docker run -p 8000:8000 waze-mcp
# Auth:   docker run -p 8000:8000 -e WAZE_MCP_AUTH_TOKEN=secret waze-mcp
#
# The MCP endpoint is served at http://<host>:8000/mcp ; /health is unauthenticated.

FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE server.py ./
RUN pip install --no-cache-dir .

# Drop privileges: run as an unprivileged user instead of root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
ENV WAZE_MCP_TRANSPORT=streamable-http \
    WAZE_MCP_HOST=0.0.0.0 \
    WAZE_MCP_PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

ENTRYPOINT ["waze-mcp"]
