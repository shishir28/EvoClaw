"""Path safety utilities for write operations."""

from __future__ import annotations

import os
import tempfile
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


def write_text_atomic(path: Path, content: str) -> None:
    """Write text through a same-directory temp file and atomic replace.

    The temp file lives beside the destination so os.replace is atomic on the
    target filesystem. This prevents partially-written JSON/markdown files if a
    process is interrupted mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
