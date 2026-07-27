"""Unit tests for file upload security.

Verifies:
- Extension allowlist per context
- Magic byte verification (rejects `image.exe` renamed to `.jpg`)
- Size limit enforcement
- Filename sanitization
- EXIF stripping (best-effort — won't fail if Pillow is missing)
"""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile

from krishisetu.core.file_upload_security import (
    FileValidationError,
    UploadContext,
    strip_exif,
    validate_upload,
)


def _make_upload(
    filename: str, content: bytes, content_type: str = "application/octet-stream"
) -> UploadFile:
    """Build a FastAPI UploadFile from in-memory bytes."""
    file = UploadFile(filename=filename, file=io.BytesIO(content))
    file.headers = {"content-type": content_type}
    return file


# Minimal valid file headers (magic bytes)
JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 10 + b"JFIF" + b"\x00" * 100
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
WEBP_HEADER = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 100
WAV_HEADER = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 100
PDF_HEADER = b"%PDF-1.4\n" + b"\x00" * 100
EXE_RENAMED_JPG = b"MZ" + b"\x00" * 100  # Windows PE executable


class TestExtensionAllowlist:
    async def test_jpg_accepted_for_disease_image(self) -> None:
        file = _make_upload("leaf.jpg", JPEG_HEADER, "image/jpeg")
        result = await validate_upload(file, UploadContext.DISEASE_IMAGE)
        assert result.extension == ".jpg"

    async def test_svg_rejected_for_disease_image(self) -> None:
        file = _make_upload("xss.svg", b"<svg></svg>", "image/svg+xml")
        with pytest.raises(FileValidationError, match="not allowed"):
            await validate_upload(file, UploadContext.DISEASE_IMAGE)

    async def test_pdf_accepted_for_kyc_document(self) -> None:
        file = _make_upload("kyc.pdf", PDF_HEADER, "application/pdf")
        result = await validate_upload(file, UploadContext.KYC_DOCUMENT)
        assert result.extension == ".pdf"

    async def test_mp4_rejected_for_voice_audio(self) -> None:
        file = _make_upload("song.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")
        with pytest.raises(FileValidationError, match="not allowed"):
            await validate_upload(file, UploadContext.VOICE_AUDIO)


class TestMagicByteVerification:
    async def test_valid_jpg_passes(self) -> None:
        file = _make_upload("photo.jpg", JPEG_HEADER, "image/jpeg")
        result = await validate_upload(file, UploadContext.DISEASE_IMAGE)
        assert result.magic_validated is True
        assert result.category == "image"

    async def test_exe_renamed_to_jpg_rejected(self) -> None:
        file = _make_upload("evil.jpg", EXE_RENAMED_JPG, "image/jpeg")
        with pytest.raises(FileValidationError, match="magic"):
            await validate_upload(file, UploadContext.DISEASE_IMAGE)

    async def test_random_bytes_rejected(self) -> None:
        file = _make_upload("random.jpg", b"this is not an image", "image/jpeg")
        with pytest.raises(FileValidationError):
            await validate_upload(file, UploadContext.DISEASE_IMAGE)

    async def test_png_accepted(self) -> None:
        file = _make_upload("plot.png", PNG_HEADER, "image/png")
        result = await validate_upload(file, UploadContext.DISEASE_IMAGE)
        assert result.extension == ".png"

    async def test_pdf_with_image_content_accepted(self) -> None:
        """Scanned PDFs may actually be JPGs renamed to .pdf — accept them."""
        file = _make_upload("scan.pdf", JPEG_HEADER, "application/pdf")
        result = await validate_upload(file, UploadContext.KYC_DOCUMENT)
        assert result.magic_validated is True


class TestSizeLimit:
    async def test_empty_file_rejected(self) -> None:
        file = _make_upload("empty.jpg", b"", "image/jpeg")
        with pytest.raises(FileValidationError, match="empty"):
            await validate_upload(file, UploadContext.DISEASE_IMAGE)

    async def test_oversized_file_rejected(self) -> None:
        # 11 MB, just over the 10 MB limit for disease images
        big_content = JPEG_HEADER + b"\x00" * (11 * 1024 * 1024)
        file = _make_upload("huge.jpg", big_content, "image/jpeg")
        with pytest.raises(FileValidationError, match="exceeds"):
            await validate_upload(file, UploadContext.DISEASE_IMAGE)

    async def test_under_limit_accepted(self) -> None:
        # 1 MB
        content = JPEG_HEADER + b"\x00" * (1024 * 1024)
        file = _make_upload("normal.jpg", content, "image/jpeg")
        result = await validate_upload(file, UploadContext.DISEASE_IMAGE)
        assert result.size_bytes >= 1024 * 1024


class TestFilenameSanitization:
    async def test_path_traversal_blocked(self) -> None:
        file = _make_upload("../../etc/passwd.jpg", JPEG_HEADER, "image/jpeg")
        with pytest.raises(FileValidationError, match="filename"):
            await validate_upload(file, UploadContext.DISEASE_IMAGE)

    async def test_directory_stripped(self) -> None:
        file = _make_upload("/tmp/upload.jpg", JPEG_HEADER, "image/jpeg")
        result = await validate_upload(file, UploadContext.DISEASE_IMAGE)
        assert "/" not in result.filename
        assert result.filename == "upload.jpg"


class TestStripExif:
    def test_strip_exif_does_not_crash_on_invalid_input(self) -> None:
        # Invalid image bytes — should return original, not raise
        invalid = b"not an image at all"
        result = strip_exif(invalid)
        assert result == invalid  # returns original on failure

    def test_strip_exif_handles_valid_jpeg(self) -> None:
        # Create a minimal valid JPEG with Pillow (if available)
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
            return

        img = Image.new("RGB", (10, 10), color="red")
        out = io.BytesIO()
        img.save(out, format="JPEG")
        original = out.getvalue()

        stripped = strip_exif(original)
        # Stripped should be valid JPEG (starts with same magic bytes)
        assert stripped[:3] == b"\xff\xd8\xff"
        # Stripped size may be smaller (no EXIF) — but at minimum, it's valid
