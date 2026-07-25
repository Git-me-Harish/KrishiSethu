"""NDVI domain — satellite imagery, vegetation health, anomaly detection.

This module handles:
- NDVI observations (per-plot, time-series)
- NDVI rasters (S3-hosted GeoTIFFs)
- NDVI anomaly alerts (drop detection)
- District NDVI aggregation (heatmap for officers)

External integrations:
- Sentinel Hub (https://www.sentinel-hub.com/) — primary satellite imagery source
- Copernicus Open Access Hub — alternative direct download
- Landsat 8/9 — backup when Sentinel-2 has cloud cover

NDVI Formula:
    NDVI = (NIR - Red) / (NIR + Red)

Sentinel-2 bands:
- B04 (Red)     — 665nm, 10m resolution
- B08 (NIR)     — 842nm, 10m resolution
- SCL (Scene Classification Layer) — for cloud masking

NDVI values:
- 0.6 to 1.0    — Healthy vegetation
- 0.2 to 0.6    — Sparse/moderate vegetation
- 0.1 to 0.2    — Bare soil
- < 0.1         — Water, snow, clouds

See KrishiSetu_Architecture_Plan.md §14.5 for full module specification.
"""
