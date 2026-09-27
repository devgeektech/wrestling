"""Build absolute media URLs for local disk or S3 (signed)."""

from __future__ import annotations


def absolute_media_url(file_field, request=None) -> str | None:
    """
    Return a usable absolute URL for a FileField/ImageField.

    - S3 / remote: field.url is already https://… (often signed) — return as-is.
    - Local /media/: join with request.build_absolute_uri when request is present.
    """
    if not file_field:
        return None
    try:
        url = file_field.url
    except (ValueError, AttributeError):
        return None
    if not url:
        return None
    if url.startswith('http://') or url.startswith('https://'):
        return url
    if request is not None:
        return request.build_absolute_uri(url)
    return url
