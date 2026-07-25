"""Farmer domain — plots, land records, crop cycles.

This module contains all farmer-owned geospatial and agricultural data:
- Plot registration with PostGIS boundaries
- Crop cycles (what crop is grown on which plot, when)
- Soil test history (Phase 2)
- Verification workflow (officer verifies plot ownership)

See KrishiSetu_Architecture_Plan.md §14.2 for full module specification.
"""
