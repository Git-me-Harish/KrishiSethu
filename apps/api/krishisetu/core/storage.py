"""S3-compatible object storage client.

Handles:
- Generating pre-signed upload URLs (client uploads directly to S3, bypassing API)
- Generating pre-signed download URLs (client downloads directly from S3)
- Server-side downloads (for ML inference — worker downloads image)
- Bucket creation on first run

Designed to work with:
- MinIO (local development)
- AWS S3 (production)
- Any S3-compatible service (DigitalOcean Spaces, Backblaze B2, etc.)

The pattern of using pre-signed URLs is critical for performance:
- Without it: farmer uploads image to API → API streams to S3 → API returns.
  For a 5MB image, this uses 5MB of API bandwidth and 5MB of S3 bandwidth.
- With it: API generates a pre-signed URL → farmer uploads directly to S3.
  API bandwidth is negligible; only S3 bandwidth is used.

All S3 keys follow a structured path convention:
- disease-reports/{farmer_id}/{report_id}/original.jpg
- disease-reports/{farmer_id}/{report_id}/thumbnail.jpg
- disease-reports/{farmer_id}/{report_id}/heatmap.png
- ndvi/{plot_id}/{date}.tiff
- voice/{user_id}/{timestamp}.wav
"""

from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)


class StorageClient:
    """S3-compatible object storage client.

    Singleton — initialized once on first access.
    """

    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings().S3_ENDPOINT,
            aws_access_key_id=settings().S3_ACCESS_KEY.get_secret_value(),
            aws_secret_access_key=settings().S3_SECRET_KEY.get_secret_value(),
            region_name=settings().S3_REGION,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )
        self._bucket = settings().S3_BUCKET_NAME
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        """Create the bucket if it doesn't exist (dev convenience)."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                logger.info("storage.bucket_creating", bucket=self._bucket)
                try:
                    self._client.create_bucket(Bucket=self._bucket)
                    logger.info("storage.bucket_created", bucket=self._bucket)
                except ClientError as create_err:
                    logger.error(
                        "storage.bucket_create_failed",
                        bucket=self._bucket,
                        error=str(create_err),
                    )
            else:
                logger.warning(
                    "storage.bucket_check_failed",
                    bucket=self._bucket,
                    error=str(e),
                )

    # -----------------------------------------------------------------------
    # Pre-signed URL generation
    # -----------------------------------------------------------------------

    def generate_upload_url(
        self,
        key: str,
        content_type: str = "image/jpeg",
        expires_in: int = 900,
    ) -> str:
        """Generate a pre-signed URL for uploading an object.

        The client uses this URL with HTTP PUT to upload the file directly
        to S3, bypassing the API. The URL expires after `expires_in` seconds.

        Args:
            key: S3 object key (e.g., "disease-reports/{farmer_id}/{report_id}/original.jpg")
            content_type: Expected MIME type of the upload
            expires_in: URL validity in seconds (default 15 minutes)

        Returns:
            Pre-signed URL string.
        """
        url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url

    def generate_download_url(
        self,
        key: str,
        expires_in: int = 900,
    ) -> str:
        """Generate a pre-signed URL for downloading an object.

        Used by the API to give the client a temporary URL to fetch the
        image. The URL expires after `expires_in` seconds.
        """
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url

    # -----------------------------------------------------------------------
    # Server-side operations (for workers)
    # -----------------------------------------------------------------------

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload bytes to S3 from server-side (e.g., generated thumbnails)."""
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def download_bytes(self, key: str) -> bytes:
        """Download an object's contents as bytes.

        Used by the ML worker to fetch the uploaded image for inference.
        """
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    async def download_bytes_async(self, key: str) -> bytes:
        """Async wrapper for download_bytes.

        Uses run_in_executor to avoid blocking the event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.download_bytes, key)

    def delete_object(self, key: str) -> None:
        """Delete an object from S3."""
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def object_exists(self, key: str) -> bool:
        """Check if an object exists in S3."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    # -----------------------------------------------------------------------
    # Key generation helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def disease_report_image_key(
        farmer_id: uuid.UUID,
        report_id: uuid.UUID,
        suffix: str = "original.jpg",
    ) -> str:
        """Generate S3 key for a disease report image.

        Path convention: disease-reports/{farmer_id}/{report_id}/{suffix}
        """
        return f"disease-reports/{farmer_id}/{report_id}/{suffix}"

    @staticmethod
    def disease_heatmap_key(
        farmer_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> str:
        """Generate S3 key for a disease prediction heatmap (Phase 2)."""
        return f"disease-reports/{farmer_id}/{report_id}/heatmap.png"

    @staticmethod
    def ndvi_raster_key(plot_id: uuid.UUID, date: str) -> str:
        """Generate S3 key for an NDVI raster tile.

        Path convention: ndvi/{plot_id}/{date}.tiff
        """
        return f"ndvi/{plot_id}/{date}.tiff"

    @staticmethod
    def voice_recording_key(user_id: uuid.UUID, timestamp: datetime | None = None) -> str:
        """Generate S3 key for a voice recording."""
        ts = timestamp or datetime.now(timezone.utc)
        return f"voice/{user_id}/{ts.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.wav"

    @staticmethod
    def product_image_key(supplier_id: uuid.UUID, product_id: uuid.UUID, suffix: str = "main.jpg") -> str:
        """Generate S3 key for a marketplace product image."""
        return f"products/{supplier_id}/{product_id}/{suffix}"


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_storage_client: StorageClient | None = None


def get_storage() -> StorageClient:
    """Get the singleton StorageClient instance."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
    return _storage_client
