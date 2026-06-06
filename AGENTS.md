# AGENTS.md

## Repository guidance

- Use `uv` for local setup and builds.
- Keep GitHub Actions in `.github/workflows/ci.yml` pinned to immutable action SHAs.
- The CI job runs on `blacksmith-2vcpu-ubuntu-2404` in a `python:3.11-slim` container.
- Detect Python tests without traversing `.venv` or other generated directories.

## Validation

- Run `uv sync` before building or testing.
- Run `uv build` for packaging checks.
- Run `uv run --with pytest pytest` only when Python tests are present.
