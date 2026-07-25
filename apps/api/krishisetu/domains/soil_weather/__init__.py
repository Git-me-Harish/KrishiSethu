"""Soil & Weather domain — soil tests, weather observations, forecasts, alerts.

This module handles:
- Soil test results (SHC import, manual entry, ISRIC auto-populate)
- Weather observations (current conditions, time-series history)
- Weather forecasts (7-day, hourly)
- Extreme weather alerts (frost, hail, heat wave)

External integrations:
- IMD (India Meteorological Department) — primary weather source
- OpenWeatherMap — fallback weather source
- ISRIC SoilGrids — soil property predictions at 250m resolution
- State Soil Health Card portal — official soil test results

See KrishiSetu_Architecture_Plan.md §14.4 for full module specification.
"""
