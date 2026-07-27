"""Helpers for safely consuming multipart uploads.

The naive ``await file.read()`` buffers the *entire* request body in memory
before any size check can run, so an attacker can OOM-kill the container with
a single large POST. ``read_upload_limited`` streams the body in fixed-size
chunks and aborts the moment the running total exceeds the limit.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

CHUNK_SIZE = 64 * 1024


async def read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload into memory, aborting as soon as it exceeds max_bytes.

    Raises 413 without ever holding more than ``max_bytes + CHUNK_SIZE``.
    """
    chunks: list[bytes] = []
    total = 0

    while chunk := await file.read(CHUNK_SIZE):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Max: {max_bytes} bytes.",
            )
        chunks.append(chunk)

    return b"".join(chunks)
