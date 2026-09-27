"""Range-aware media file serving for /media/ URLs."""

from __future__ import annotations

import mimetypes
import os
import posixpath
import re
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.utils._os import safe_join
from django.utils.http import http_date
from django.utils.translation import gettext as _
from django.views.static import was_modified_since

_RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')
_CHUNK_SIZE = 64 * 1024


def _resolve_media_path(path: str) -> tuple[Path, os.stat_result]:
    """Resolve and validate a path under MEDIA_ROOT."""
    normalized = posixpath.normpath(path).lstrip('/')
    fullpath = Path(safe_join(settings.MEDIA_ROOT, normalized))
    if fullpath.is_dir():
        raise Http404(_('Directory indexes are not allowed here.'))
    if not fullpath.exists():
        raise Http404(_('"%(path)s" does not exist') % {'path': fullpath})
    return fullpath, fullpath.stat()


def _parse_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    """
    Parse a single Range header value.

    Returns (start, end) inclusive, or None if invalid / unsatisfiable.
    """
    match = _RANGE_RE.match(range_header.strip())
    if not match:
        return None

    start_str, end_str = match.groups()
    if not start_str and not end_str:
        return None

    if start_str:
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
    else:
        # suffix range: bytes=-500
        suffix = int(end_str)
        if suffix <= 0:
            return None
        start = max(file_size - suffix, 0)
        end = file_size - 1

    if start < 0 or end < start or start >= file_size:
        return None

    end = min(end, file_size - 1)
    return start, end


def _file_iterator(file_path: Path, start: int, length: int):
    """Yield chunks from file_path starting at byte start for length bytes."""
    with file_path.open('rb') as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def serve_media(request, path: str):
    """
    Serve uploaded media with HTTP byte-range support.

    - No Range header: 200 + full file
    - Valid Range: 206 Partial Content
    - Invalid / unsatisfiable Range: 416 Range Not Satisfiable
    """
    fullpath, statobj = _resolve_media_path(path)
    file_size = statobj.st_size

    if not was_modified_since(request.META.get('HTTP_IF_MODIFIED_SINCE'), statobj.st_mtime):
        response = HttpResponse(status=304)
        response['Last-Modified'] = http_date(statobj.st_mtime)
        response['Accept-Ranges'] = 'bytes'
        return response

    content_type, encoding = mimetypes.guess_type(str(fullpath))
    content_type = content_type or 'application/octet-stream'

    range_header = request.META.get('HTTP_RANGE')
    if range_header:
        byte_range = _parse_byte_range(range_header, file_size)
        if byte_range is None:
            response = HttpResponse(status=416)
            response['Content-Range'] = f'bytes */{file_size}'
            response['Accept-Ranges'] = 'bytes'
            return response

        start, end = byte_range
        length = end - start + 1
        response = StreamingHttpResponse(
            _file_iterator(fullpath, start, length),
            status=206,
            content_type=content_type,
        )
        response['Content-Length'] = str(length)
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response['Accept-Ranges'] = 'bytes'
        response['Last-Modified'] = http_date(statobj.st_mtime)
        if encoding:
            response['Content-Encoding'] = encoding
        return response

    response = StreamingHttpResponse(
        _file_iterator(fullpath, 0, file_size),
        content_type=content_type,
    )
    response['Content-Length'] = str(file_size)
    response['Accept-Ranges'] = 'bytes'
    response['Last-Modified'] = http_date(statobj.st_mtime)
    if encoding:
        response['Content-Encoding'] = encoding
    return response
