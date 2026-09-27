"""Helpers for local disk vs S3-backed Django FileFields."""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


@contextmanager
def local_file_for_field(file_field, *, suffix: str | None = None):
    """
    Yield a filesystem Path for a FileField (local storage or S3).

    - Local storage: yields the existing path (file is not deleted).
    - Remote (S3): downloads to a temp file, yields it, then deletes the temp file.
    """
    if not file_field:
        yield None
        return

    try:
        local_path = Path(file_field.path)
        if local_path.is_file():
            yield local_path
            return
    except (NotImplementedError, ValueError, OSError):
        pass

    name = getattr(file_field, 'name', '') or ''
    ext = suffix or Path(name).suffix or '.bin'
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.close()
        with file_field.open('rb') as src, tmp_path.open('wb') as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)
