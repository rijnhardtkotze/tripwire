# tripwire

Behavioural tripwires for programmable banking

## CI

GitHub Actions CI is defined in `.github/workflows/ci.yml`.

- Runs on Blacksmith's `blacksmith-2vcpu-ubuntu-2404` runner
- Uses a `python:3.11-slim` container
- Syncs dependencies with `uv sync`
- Runs `uv run --with pytest pytest` only when Python tests are detected
