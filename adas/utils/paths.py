"""Path safety utilities for write operations."""

from __future__ import annotations

from pathlib import Path


def assert_safe_write_path(path: Path, base: Path) -> None:
    """Raise ValueError if path does not resolve under base.

    Prevents directory traversal when paths originate from user-supplied or
    generated content. Has no effect when called with paths that stay inside
    the project workspace.
    """
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        raise ValueError(
            f"Write path '{path}' is outside the allowed base directory '{base}'. "
            "Check your configuration or arguments."
        )
