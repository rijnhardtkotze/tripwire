# CLAUDE.md

This file provides guidance for AI assistants working with the tripwire codebase.

## Project Overview

**Tripwire** is a Python library for behavioral tripwires in programmable banking. The project is in early development (v0.0.1).

## Tech Stack

- **Language:** Python 3.11+
- **Package Manager:** uv
- **Build Backend:** uv_build (PEP 517/518 compliant)
- **Tool Version Manager:** mise

## Project Structure

```text
tripwire/
├── src/tripwire/       # Main package source code
│   └── __init__.py     # Package entry point with main() function
├── pyproject.toml      # Project configuration and dependencies
├── mise.toml           # Tool version management (uv)
├── .python-version     # Python version specification (3.11)
├── LICENSE             # MIT License
└── README.md           # Project description
```

## Development Setup

```bash
# Install uv (if not using mise)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with mise (recommended)
mise install

# Sync dependencies
uv sync

# Install in development mode
uv pip install -e .
```

## Common Commands

```bash
# Run the CLI
uv run tripwire

# Run directly
uv run python -m tripwire

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Build the package
uv build
```

## Code Conventions

### Style Guidelines

- Follow PEP 8 style guidelines
- Use type hints for function signatures
- Include docstrings for modules and public functions
- Use triple-quoted docstrings with descriptions

### Example Pattern

```python
"""Module docstring describing purpose"""

def function_name(param: str) -> None:
    """Brief description of function.

    Longer description if needed.
    """
    pass
```

### Project Patterns

- Entry point defined in `pyproject.toml` under `[project.scripts]`
- Main module uses `if __name__ == "__main__":` guard
- Source code lives in `src/tripwire/` (src layout)

## Testing

Testing framework not yet configured. When adding tests:
- Place tests in a `tests/` directory at project root
- Use pytest as the testing framework
- Follow naming convention: `test_*.py` for test files

## Dependencies

Currently no external dependencies. Add dependencies to `pyproject.toml` via:
```bash
uv add <package-name>
```

## Git Workflow

- Main development happens on feature branches
- Commit messages should be clear and descriptive
- Keep commits focused and atomic

## Key Files

| File | Purpose |
| ------ | --------- |
| `src/tripwire/__init__.py` | Main module and CLI entry point |
| `pyproject.toml` | Project metadata, dependencies, build config |
| `mise.toml` | Developer tool versions |
| `.python-version` | Python version for the project |
