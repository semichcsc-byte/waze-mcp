# Contributing

Thanks for your interest — issues and pull requests are welcome.

## Development setup

```bash
python3 -m venv .venv          # Python 3.10+
./.venv/bin/pip install -e ".[dev]"
```

## Checks (run before pushing)

```bash
./.venv/bin/ruff check .
./.venv/bin/pytest -q
```

The test suite mocks Waze, so it needs no network. CI runs the same checks on
Python 3.10–3.13.

## Guidelines

- Keep the tools **read-only** and the dependency footprint small.
- Add or update tests for any behaviour change.
- Make sure `ruff` and `pytest` are green before opening a PR.
- Be mindful that the Waze backend is unofficial: avoid adding anything that
  hammers the endpoints (the built-in cache exists for this reason).
