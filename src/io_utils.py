"""Shared I/O helpers: atomic JSON writes and logging configuration."""

import json
import logging
import os
import tempfile
from pathlib import Path

_logging_configured = False


def write_json_atomic(data, path):
    """Write ``data`` as JSON to ``path`` atomically.

    The JSON is first written to a temporary file in the same directory as
    ``path`` (so the final ``os.replace`` is atomic on the same filesystem),
    flushed, and fsynced before being moved into place. If anything goes
    wrong the temporary file is removed and the exception is re-raised.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent = 2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def configure_logging(level=logging.INFO):
    """Configure root logging once, writing to stderr with a consistent format."""
    global _logging_configured
    if _logging_configured:
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _logging_configured = True
