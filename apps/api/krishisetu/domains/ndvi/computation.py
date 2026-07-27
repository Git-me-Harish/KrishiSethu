"""NDVI computation pipeline.

Computes NDVI from Sentinel-2 band data:
    NDVI = (NIR - Red) / (NIR + Red)

Steps:
1. Apply cloud mask (using SCL band)
2. Compute NDVI per pixel
3. Compute summary statistics (mean, min, max, stddev)
4. Generate PNG thumbnail for quick preview (Phase 2 — requires PIL)

Cloud masking:
- SCL values 0, 1, 2, 3 (cloud shadow), 8, 9 (cloud), 10 (cirrus) are masked
- SCL values 4 (vegetation), 5 (bare soil), 6 (water), 7 (unclassified) are kept
- Snow (11) is kept but flagged

Uses pure Python (no numpy/rasterio dependency) to keep the deployment
lightweight. For production with high plot counts, migrate to numpy for
~50x performance improvement.
"""

from __future__ import annotations

import math
from decimal import Decimal

from krishisetu.core.logging import get_logger
from krishisetu.integrations.sentinel_hub import NDVIRasterStats, SentinelBandData

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# SCL values that should be masked (cloud, shadow, saturated, etc.)
# 0=NoData, 1=Saturated, 2=DarkArea, 3=CloudShadow, 8=CloudMedium, 9=CloudHigh, 10=Cirrus
CLOUD_MASK_SCL = {0, 1, 2, 3, 8, 9, 10}

# Valid SCL values (kept for NDVI computation)
VALID_SCL = {4, 5, 6, 7, 11}  # Vegetation, BareSoil, Water, Unclassified, Snow


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------


def compute_ndvi_stats(band_data: SentinelBandData) -> NDVIRasterStats:
    """Compute NDVI statistics from Sentinel-2 band data.

    Args:
        band_data: SentinelBandData with Red, NIR, and SCL bands.

    Returns:
        NDVIRasterStats with mean, min, max, stddev, cloud cover, and
        the computed NDVI raster.
    """
    width = band_data.width
    height = band_data.height
    total_pixels = width * height

    # Compute NDVI per pixel, applying cloud mask
    ndvi_raster: list[list[float]] = []
    valid_ndvi_values: list[float] = []
    cloud_pixels = 0

    for y in range(height):
        row: list[float] = []
        for x in range(width):
            scl_value = band_data.scl[y][x]

            # Check if pixel is cloudy
            if scl_value in CLOUD_MASK_SCL:
                cloud_pixels += 1
                row.append(float("nan"))  # Mark as no-data
                continue

            red = band_data.red[y][x]
            nir = band_data.nir[y][x]

            # Compute NDVI
            # NDVI = (NIR - Red) / (NIR + Red)
            denominator = nir + red
            if abs(denominator) < 1e-10:
                # Both bands are zero (water shadow, etc.)
                ndvi = 0.0
            else:
                ndvi = (nir - red) / denominator

            # Clamp to valid NDVI range [-1, 1]
            ndvi = max(-1.0, min(1.0, ndvi))

            row.append(ndvi)
            valid_ndvi_values.append(ndvi)

        ndvi_raster.append(row)

    # Compute statistics from valid pixels
    valid_count = len(valid_ndvi_values)
    cloud_cover_pct = (cloud_pixels / total_pixels) * 100 if total_pixels > 0 else 100.0

    if valid_count == 0:
        # All pixels are cloudy — return placeholder stats
        logger.warning(
            "ndvi.all_cloudy",
            cloud_pixels=cloud_pixels,
            total_pixels=total_pixels,
        )
        return NDVIRasterStats(
            ndvi_mean=Decimal("0.0000"),
            ndvi_min=Decimal("0.0000"),
            ndvi_max=Decimal("0.0000"),
            ndvi_stddev=Decimal("0.0000"),
            cloud_cover_pct=Decimal(str(round(cloud_cover_pct, 2))),
            valid_pixel_count=0,
            total_pixel_count=total_pixels,
            ndvi_raster=ndvi_raster,
        )

    # Compute statistics
    mean_ndvi = sum(valid_ndvi_values) / valid_count
    min_ndvi = min(valid_ndvi_values)
    max_ndvi = max(valid_ndvi_values)

    # Standard deviation
    variance = sum((v - mean_ndvi) ** 2 for v in valid_ndvi_values) / valid_count
    stddev_ndvi = math.sqrt(variance)

    logger.info(
        "ndvi.computed",
        valid_pixels=valid_count,
        total_pixels=total_pixels,
        cloud_cover_pct=round(cloud_cover_pct, 2),
        mean=round(mean_ndvi, 4),
        min=round(min_ndvi, 4),
        max=round(max_ndvi, 4),
        stddev=round(stddev_ndvi, 4),
    )

    return NDVIRasterStats(
        ndvi_mean=Decimal(str(round(mean_ndvi, 4))),
        ndvi_min=Decimal(str(round(min_ndvi, 4))),
        ndvi_max=Decimal(str(round(max_ndvi, 4))),
        ndvi_stddev=Decimal(str(round(stddev_ndvi, 4))),
        cloud_cover_pct=Decimal(str(round(cloud_cover_pct, 2))),
        valid_pixel_count=valid_count,
        total_pixel_count=total_pixels,
        ndvi_raster=ndvi_raster,
    )


# ---------------------------------------------------------------------------
# Health classification
# ---------------------------------------------------------------------------


def classify_ndvi_health(ndvi_mean: float) -> str:
    """Classify NDVI mean into a health category.

    - healthy: NDVI >= 0.6 (dense, healthy vegetation)
    - moderate: 0.3 <= NDVI < 0.6 (moderate vegetation)
    - sparse: 0.1 <= NDVI < 0.3 (sparse vegetation, early growth)
    - bare: NDVI < 0.1 (bare soil, no vegetation)
    """
    if ndvi_mean >= 0.6:
        return "healthy"
    if ndvi_mean >= 0.3:
        return "moderate"
    if ndvi_mean >= 0.1:
        return "sparse"
    return "bare"


def get_health_color(health: str) -> str:
    """Get hex color for a health category (for UI rendering)."""
    return {
        "healthy": "#4CAF50",   # Green
        "moderate": "#FFEB3B",  # Yellow
        "sparse": "#FF9800",    # Orange
        "bare": "#DC2626",      # Red
    }.get(health, "#9CA3AF")


# ---------------------------------------------------------------------------
# NDVI color scale (for raster visualization)
# ---------------------------------------------------------------------------


def ndvi_to_color(ndvi: float) -> tuple[int, int, int]:
    """Map an NDVI value to an RGB color for visualization.

    Color scale (matches the reference UI):
    - 0.6 to 1.0: Green (#4CAF50 to darker green)
    - 0.3 to 0.6: Yellow-green to yellow
    - 0.1 to 0.3: Orange
    - -1 to 0.1: Red to brown (bare/water)

    Returns (R, G, B) tuple with values 0-255.
    """
    # Clamp to [-1, 1]
    ndvi = max(-1.0, min(1.0, ndvi))

    if ndvi >= 0.6:
        # Healthy vegetation: green
        # 0.6 -> #4CAF50, 1.0 -> darker green
        t = (ndvi - 0.6) / 0.4  # 0 to 1
        r = int(76 - t * 30)    # 76 -> 46
        g = int(175 - t * 20)   # 175 -> 155
        b = int(80 - t * 20)    # 80 -> 60
    elif ndvi >= 0.3:
        # Moderate: yellow-green to yellow
        t = (ndvi - 0.3) / 0.3  # 0 to 1
        r = int(255 - t * 180)  # 255 -> 75
        g = int(235 - t * 60)   # 235 -> 175
        b = int(59 + t * 20)    # 59 -> 79
    elif ndvi >= 0.1:
        # Sparse: orange
        t = (ndvi - 0.1) / 0.2  # 0 to 1
        r = int(220 + t * 35)   # 220 -> 255
        g = int(150 + t * 85)   # 150 -> 235
        b = int(50 + t * 9)     # 50 -> 59
    elif ndvi >= 0:
        # Bare soil: red to brown
        t = ndvi / 0.1  # 0 to 1
        r = int(180 + t * 40)   # 180 -> 220
        g = int(80 + t * 70)    # 80 -> 150
        b = int(40 + t * 10)    # 40 -> 50
    else:
        # Water: blue-ish
        t = (ndvi + 1) / 1.0    # 0 to 1
        r = int(50 - t * 30)    # 50 -> 20
        g = int(100 - t * 60)   # 100 -> 40
        b = int(180 - t * 50)   # 180 -> 130

    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


def detect_ndvi_anomaly(
    previous_ndvi: float,
    current_ndvi: float,
) -> tuple[str | None, float]:
    """Detect NDVI anomaly between two observations.

    Returns (anomaly_type, drop_magnitude) tuple. If no anomaly, returns
    (None, 0.0).

    Anomaly types:
    - severe_drop: NDVI dropped by more than 0.30
    - significant_drop: NDVI dropped by more than 0.15
    - low_vegetation: Current NDVI below 0.2 (bare soil when crop expected)
    """
    drop = previous_ndvi - current_ndvi

    if drop > 0.30:
        return "severe_drop", drop
    if drop > 0.15:
        return "significant_drop", drop
    if current_ndvi < 0.2 and previous_ndvi >= 0.3:
        # Sudden drop to bare soil
        return "low_vegetation", drop

    return None, 0.0
