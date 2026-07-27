"""Sentinel Hub API client — satellite imagery for NDVI computation.

Sentinel Hub (https://www.sentinel-hub.com/) provides processed satellite
imagery via a simple API. We use it to fetch:
- Sentinel-2 L2A imagery (10m resolution, 5-day revisit)
- Custom band combinations (B04 Red, B08 NIR, SCL for cloud masking)
- Cloud-free mosaics (when available)

API access requires SENTINEL_HUB_CLIENT_ID and SENTINEL_HUB_CLIENT_SECRET
(https://www.sentinel-hub.com/dashboard/).

In development (no credentials), the client generates synthetic NDVI data
based on:
- Plot area (larger plots = more pixel variation)
- Current month (crops grow in Kharif/Rabi seasons)
- Random but deterministic variation (stable per plot per week)

This enables full development without API credentials while producing
realistic test data that varies by plot and time.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SentinelBandData:
    """Raw band data for a plot (fetched from Sentinel Hub).

    Each band is a 2D numpy array. The arrays are aligned (same shape).
    """

    red: list[list[float]]       # B04 (665nm)
    nir: list[list[float]]       # B08 (842nm)
    scl: list[list[int]]         # Scene Classification Layer
    width: int
    height: int
    observed_at: datetime
    cloud_cover_pct: float
    raw_metadata: dict[str, Any] | None = None


@dataclass
class NDVIRasterStats:
    """Statistics computed from an NDVI raster."""

    ndvi_mean: Decimal
    ndvi_min: Decimal
    ndvi_max: Decimal
    ndvi_stddev: Decimal
    cloud_cover_pct: Decimal
    valid_pixel_count: int
    total_pixel_count: int
    # The computed NDVI raster (2D array) — used for raster storage
    ndvi_raster: list[list[float]] | None = None


# ---------------------------------------------------------------------------
# Sentinel Hub API client
# ---------------------------------------------------------------------------


class SentinelHubClient:
    """Client for Sentinel Hub Process API.

    In production (SENTINEL_HUB_CLIENT_ID set), fetches real imagery.
    In development, generates synthetic NDVI data based on plot characteristics.
    """

    TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"  # noqa: S105 -- URL, not a credential
    PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"

    def __init__(self) -> None:
        self.client_id = settings().SENTINEL_HUB_CLIENT_ID
        self.client_secret = settings().SENTINEL_HUB_CLIENT_SECRET
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        """Whether the client makes real API calls."""
        return (
            self.client_id is not None
            and self.client_secret is not None
            and not settings().is_development
        )

    async def fetch_band_data(
        self,
        bbox: tuple[float, float, float, float],  # (west, south, east, north)
        plot_id,
        *,
        max_days_back: int = 14,
        width: int = 100,
        height: int = 100,
    ) -> SentinelBandData | None:
        """Fetch Sentinel-2 band data for a bounding box.

        Args:
            bbox: Bounding box in WGS84 (west, south, east, north)
            plot_id: Plot UUID (for logging and synthetic seed)
            max_days_back: Look back up to N days for cloud-free imagery
            width: Output raster width in pixels
            height: Output raster height in pixels

        Returns:
            SentinelBandData with Red, NIR, and SCL bands, or None if no
            suitable imagery is available.
        """
        if self.is_live:
            try:
                return await self._fetch_live(bbox, max_days_back, width, height)
            except Exception as e:
                logger.warning(
                    "sentinel.live_failed",
                    plot_id=str(plot_id),
                    error=str(e),
                )
                # Fall through to synthetic
        return self._generate_synthetic(bbox, plot_id, width, height)

    # -----------------------------------------------------------------------
    # Live API calls (production)
    # -----------------------------------------------------------------------

    async def _get_token(self) -> str:
        """Get OAuth2 access token from Sentinel Hub."""
        if self._token and self._token_expires_at and datetime.now(UTC) < self._token_expires_at:
            return self._token

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id.get_secret_value() if self.client_id else "",
                    "client_secret": (
                        self.client_secret.get_secret_value() if self.client_secret else ""
                    ),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        response.raise_for_status()
        data = response.json()

        self._token = data["access_token"]
        self._token_expires_at = datetime.now(UTC) + timedelta(
            seconds=data.get("expires_in", 3600) - 60  # 1 min buffer
        )
        return self._token

    async def _fetch_live(
        self,
        bbox: tuple[float, float, float, float],
        max_days_back: int,
        width: int,
        height: int,
    ) -> SentinelBandData | None:
        """Fetch real Sentinel-2 imagery via the Process API.

        Uses rasterio to parse the returned GeoTIFF into band arrays.
        Requires: pip install rasterio (included in ML service deps)
        """
        token = await self._get_token()
        now = datetime.now(UTC)
        time_from = (now - timedelta(days=max_days_back)).strftime("%Y-%m-%d")
        time_to = now.strftime("%Y-%m-%d")

        # Build the evalscript to fetch B04 (red), B08 (NIR), and SCL
        evalscript = """
        //VERSION=3
        function setup() {
            return {
                input: [{
                    bands: ["B04", "B08", "SCL"],
                    units: "REFLECTANCE"
                }],
                output: {
                    bands: 3,
                    sampleType: "FLOAT32"
                }
            };
        }

        function evaluatePixel(sample) {
            return [sample.B04, sample.B08, sample.SCL];
        }
        """

        # Build request body
        west, south, east, north = bbox
        request_body = {
            "input": {
                "bounds": {
                    "bbox": [west, south, east, north],
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{time_from}T00:00:00Z",
                                "to": f"{time_to}T23:59:59Z",
                            },
                            "maxCloudCoverage": 30,
                        },
                    }
                ],
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [
                    {
                        "identifier": "default",
                        "format": {"type": "image/tiff"},
                    }
                ],
            },
            "evalscript": evalscript,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.PROCESS_URL,
                json=request_body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "image/tiff",
                },
            )

        if response.status_code == 204:
            # No data available for the time range
            logger.info("sentinel.no_data", bbox=bbox, time_range=(time_from, time_to))
            return None

        response.raise_for_status()

        logger.info(
            "sentinel.fetched",
            bbox=bbox,
            bytes=len(response.content),
        )

        # Parse the TIFF response using rasterio
        return self._parse_tiff_response(
            response.content, width, height, now
        )

    def _parse_tiff_response(
        self,
        tiff_bytes: bytes,
        width: int,
        height: int,
        observed_at: datetime,
    ) -> SentinelBandData:
        """Parse GeoTIFF response from Sentinel Hub into band arrays.

        The TIFF contains 3 bands in order: B04 (Red), B08 (NIR), SCL.
        Uses rasterio's MemoryFile to parse in-memory TIFF data.
        """
        import numpy as np

        try:
            from rasterio.io import MemoryFile
        except ImportError as exc:
            logger.warning(
                "sentinel.rasterio_not_installed",
                note="Install rasterio: pip install rasterio. Falling back to synthetic.",
            )
            raise ImportError("rasterio is required for Sentinel Hub TIFF parsing") from exc

        # Parse the TIFF in memory
        with MemoryFile(tiff_bytes) as memfile:
            with memfile.open() as dataset:
                # Read all bands: shape (3, height, width)
                data = dataset.read()

                # Band 1: B04 (Red) — reflectance values [0, 1]
                red_band = data[0].tolist()

                # Band 2: B08 (NIR) — reflectance values [0, 1]
                nir_band = data[1].tolist()

                # Band 3: SCL (Scene Classification) — integer values
                scl_band = data[2].astype(int).tolist()

                # Calculate cloud cover from SCL
                scl_array = data[2].astype(int)
                cloud_pixels = int(np.sum(np.isin(scl_array, [0, 1, 2, 3, 8, 9, 10])))
                total_pixels = int(scl_array.size)
                cloud_cover_pct = (cloud_pixels / total_pixels) * 100 if total_pixels > 0 else 100.0

        logger.info(
            "sentinel.tiff_parsed",
            width=width,
            height=height,
            cloud_cover_pct=round(cloud_cover_pct, 2),
        )

        return SentinelBandData(
            red=red_band,
            nir=nir_band,
            scl=scl_band,
            width=width,
            height=height,
            observed_at=observed_at,
            cloud_cover_pct=cloud_cover_pct,
            raw_metadata={"source": "sentinel_hub", "format": "tiff"},
        )

    # -----------------------------------------------------------------------
    # Synthetic data generation (development)
    # -----------------------------------------------------------------------

    def _generate_synthetic(
        self,
        bbox: tuple[float, float, float, float],
        plot_id,
        width: int,
        height: int,
    ) -> SentinelBandData:
        """Generate synthetic band data for development.

        The synthetic NDVI is based on:
        - Current month (crops grow in Kharif/Rabi seasons)
        - Plot centroid (latitude affects growing season)
        - Deterministic seed (stable per plot per week)
        - Random pixel variation (realistic raster)
        """
        now = datetime.now(UTC)
        month = now.month

        # Deterministic seed per (plot, week)
        week_str = now.strftime("%Y-W%W")
        seed_str = f"{plot_id}:{week_str}"
        # Non-cryptographic: seeds a deterministic RNG for synthetic NDVI
        # data (dev/fallback mode), not used for any security purpose.
        seed = int(
            hashlib.md5(seed_str.encode(), usedforsecurity=False).hexdigest(), 16
        ) % (2**32)
        rng = random.Random(seed)  # noqa: S311 -- synthetic data generation, not security

        # Base NDVI by month (Indian cropping seasons)
        # Kharif (Jun-Oct): Peak vegetation
        # Rabi (Nov-Mar): Moderate vegetation
        # Zaid (Apr-Jun): Low vegetation (summer fallow)
        base_ndvi = {
            1: 0.35, 2: 0.40, 3: 0.35,  # Rabi
            4: 0.20, 5: 0.15, 6: 0.25,  # Zaid / pre-monsoon
            7: 0.45, 8: 0.60, 9: 0.65,  # Kharif (monsoon)
            10: 0.55, 11: 0.40, 12: 0.35,
        }[month]

        # Add plot-specific variation (some plots healthier than others)
        plot_variation = rng.uniform(-0.10, 0.10)
        target_mean = max(0.0, min(0.9, base_ndvi + plot_variation))

        # Generate raster with realistic spatial variation
        # Use a smooth noise pattern (sine waves) for spatial correlation
        ndvi_raster: list[list[float]] = []
        for y in range(height):
            row: list[float] = []
            for x in range(width):
                # Base value + sine wave variation + random noise
                wave1 = 0.05 * math.sin(x * 0.3) * math.cos(y * 0.3)
                wave2 = 0.03 * math.sin(x * 0.1 + y * 0.15)
                noise = rng.uniform(-0.08, 0.08)
                pixel_ndvi = target_mean + wave1 + wave2 + noise
                pixel_ndvi = max(-0.1, min(1.0, pixel_ndvi))
                row.append(pixel_ndvi)
            ndvi_raster.append(row)

        # Generate cloud cover (5-25% in most cases, occasionally higher)
        cloud_roll = rng.random()
        if cloud_roll < 0.7:
            cloud_cover = rng.uniform(0, 15)
        elif cloud_roll < 0.9:
            cloud_cover = rng.uniform(15, 30)
        else:
            cloud_cover = rng.uniform(30, 60)  # Cloudy

        # Generate SCL (Scene Classification Layer)
        # Values: 0=NoData, 1=Saturated, 2=DarkArea, 3=CloudShadow, 4=Vegetation,
        #         5=BareSoil, 6=Water, 7=Unclassified, 8=CloudMediumProba, 9=CloudHighProba,
        #        10=ThinCirrus, 11=SnowIce
        scl: list[list[int]] = []
        cloud_pixels = int(width * height * (cloud_cover / 100))

        # Generate cloud positions (clustered, not random)
        cloud_positions: set[tuple[int, int]] = set()
        if cloud_pixels > 0:
            num_clusters = max(1, int(cloud_pixels / 50))
            for _ in range(num_clusters):
                cx = rng.randint(0, width - 1)
                cy = rng.randint(0, height - 1)
                cluster_size = int(cloud_pixels / num_clusters)
                for _ in range(cluster_size):
                    dx = rng.randint(-3, 3)
                    dy = rng.randint(-3, 3)
                    px, py = cx + dx, cy + dy
                    if 0 <= px < width and 0 <= py < height:
                        cloud_positions.add((px, py))

        for y in range(height):
            row: list[int] = []
            for x in range(width):
                if (x, y) in cloud_positions:
                    # Cloud pixel
                    row.append(rng.choice([8, 9, 3]))  # Cloud or shadow
                else:
                    # Non-cloud — classify based on NDVI
                    ndvi = ndvi_raster[y][x]
                    if ndvi >= 0.5:
                        row.append(4)  # Vegetation
                    elif ndvi >= 0.2:
                        row.append(4)  # Vegetation (sparse)
                    else:
                        row.append(5)  # Bare soil
            scl.append(row)

        # Generate Red and NIR bands from NDVI
        # NDVI = (NIR - Red) / (NIR + Red)
        # Choose Red randomly, compute NIR from NDVI
        red: list[list[float]] = []
        nir: list[list[float]] = []
        for y in range(height):
            red_row: list[float] = []
            nir_row: list[float] = []
            for x in range(width):
                if (x, y) in cloud_positions:
                    # Cloud pixels have high reflectance in both bands
                    red_row.append(0.5 + rng.uniform(-0.1, 0.1))
                    nir_row.append(0.5 + rng.uniform(-0.1, 0.1))
                else:
                    ndvi = ndvi_raster[y][x]
                    # Choose Red reflectance (0.1-0.3 for soil/veg)
                    r = rng.uniform(0.10, 0.30)
                    # Compute NIR from NDVI: NIR = Red * (1 + NDVI) / (1 - NDVI)
                    if abs(1 - ndvi) < 0.01:
                        n = r * 50  # Cap to avoid div by zero
                    else:
                        n = r * (1 + ndvi) / (1 - ndvi)
                    n = max(0.0, min(1.0, n))  # Clamp to valid reflectance
                    red_row.append(r)
                    nir_row.append(n)
            red.append(red_row)
            nir.append(nir_row)

        return SentinelBandData(
            red=red,
            nir=nir,
            scl=scl,
            width=width,
            height=height,
            observed_at=now,
            cloud_cover_pct=cloud_cover,
            raw_metadata={"synthetic": True, "seed": seed_str, "base_ndvi": base_ndvi},
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_sentinel_client: SentinelHubClient | None = None


def get_sentinel_client() -> SentinelHubClient:
    """Get the singleton Sentinel Hub client instance."""
    global _sentinel_client
    if _sentinel_client is None:
        _sentinel_client = SentinelHubClient()
    return _sentinel_client
