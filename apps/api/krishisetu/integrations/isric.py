"""ISRIC SoilGrids API client — global soil property predictions.

ISRIC (International Soil Reference and Information Centre) provides free
global soil property predictions at 250m resolution via the SoilGrids API.

API endpoint: https://rest.isric.org/soilgrids/v2.0/properties/query

Available properties:
- phh2o: Soil pH (water)
- soc: Soil organic carbon (g/kg)
- bulk_density: Bulk density (g/cm³)
- cec: Cation exchange capacity (cmol/kg)
- cec_clay: Cation exchange capacity of clay fraction
- cec_soil: Cation exchange capacity of soil
- clay: Clay content (%)
- sand: Sand content (%)
- silt: Silt content (%)
- nitrogen: Total nitrogen (g/kg)
- soc: Soil organic carbon
- ocd: Organic carbon density

Depths available (cm):
- 0-5, 5-15, 15-30, 30-60, 60-100, 100-200

When a plot is registered, the service queries ISRIC with the plot centroid
and stores the results in the soil_tests table (source=isric_auto). This
gives every plot a baseline soil characterization without requiring a
manual lab test.

Note: ISRIC predictions are global models at 250m resolution — they provide
a reasonable approximation but should NOT replace actual soil testing.
The UI clearly distinguishes ISRIC-sourced data from lab test results.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from krishisetu.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


class ISRICSoilData:
    """Soil data fetched from ISRIC SoilGrids."""

    def __init__(
        self,
        ph: Decimal | None,
        organic_carbon: Decimal | None,  # Already converted to %
        clay_pct: Decimal | None,
        sand_pct: Decimal | None,
        silt_pct: Decimal | None,
        soil_type: str | None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        self.ph = ph
        self.organic_carbon = organic_carbon
        self.clay_pct = clay_pct
        self.sand_pct = sand_pct
        self.silt_pct = silt_pct
        self.soil_type = soil_type
        self.raw_data = raw_data

    def to_dict(self) -> dict[str, Any]:
        return {
            "ph": float(self.ph) if self.ph else None,
            "organic_carbon": float(self.organic_carbon) if self.organic_carbon else None,
            "clay_pct": float(self.clay_pct) if self.clay_pct else None,
            "sand_pct": float(self.sand_pct) if self.sand_pct else None,
            "silt_pct": float(self.silt_pct) if self.silt_pct else None,
            "soil_type": self.soil_type,
        }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ISRIC_API_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Properties we query (depth 5-15cm — topsoil, most relevant for agriculture)
SOIL_PROPS = ["phh2o", "soc", "clay", "sand", "silt"]
SOIL_DEPTH = "5-15cm"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ISRICClient:
    """ISRIC SoilGrids API client.

    No API key required — the SoilGrids API is free for public use.
    Rate limit: ~50 requests/minute (sufficient for our use case).
    """

    def __init__(self) -> None:
        self.api_url = ISRIC_API_URL
        self.timeout = 15.0

    async def get_soil_data(self, lat: float, lon: float) -> ISRICSoilData | None:
        """Fetch soil properties for the given coordinates.

        Args:
            lat: Latitude (WGS84)
            lon: Longitude (WGS84)

        Returns:
            ISRICSoilData with pH, organic carbon, and texture fractions,
            or None if the API call fails.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.api_url,
                    params={
                        "lon": lon,
                        "lat": lat,
                        "property": SOIL_PROPS,
                        "depth": SOIL_DEPTH,
                        "value": "mean",
                    },
                )
        except httpx.HTTPError as e:
            logger.warning("isric.network_error", lat=lat, lon=lon, error=str(e))
            return None

        if response.status_code != 200:
            logger.warning(
                "isric.api_error",
                lat=lat,
                lon=lon,
                status=response.status_code,
                body=response.text[:200],
            )
            return None

        try:
            data = response.json()
        except Exception as e:
            logger.warning("isric.parse_error", lat=lat, lon=lon, error=str(e))
            return None

        return self._parse_response(data)

    def _parse_response(self, data: dict[str, Any]) -> ISRICSoilData:
        """Parse the ISRIC API response.

        ISRIC returns data in this structure:
        {
            "properties": {
                "layers": [
                    {
                        "name": "phh2o",
                        "depths": [
                            {
                                "label": "5-15cm",
                                "values": {"mean": 6.2}
                            }
                        ]
                    },
                    ...
                ]
            }
        }

        Units:
        - phh2o: pH * 10 (so 62 means pH 6.2) — ISRIC returns pH in 10*log10(H+)
        - soc: g/kg (we convert to % by dividing by 10)
        - clay/sand/silt: percentage (0-100) * 10 (so 350 means 35%)
        """
        properties = data.get("properties", {})
        layers = properties.get("layers", [])

        layer_map: dict[str, float] = {}
        for layer in layers:
            name = layer.get("name")
            depths = layer.get("depths", [])
            if depths:
                # Take the first (requested) depth
                value = depths[0].get("values", {}).get("mean")
                if value is not None:
                    layer_map[name] = float(value)

        # Convert ISRIC units to standard units
        ph = None
        if "phh2o" in layer_map:
            # ISRIC: phh2o in 10*log10(H+) → standard pH = 10 - (value / 10)
            # Wait — that's not quite right. Let me check.
            # ISRIC SoilGrids phh2o is actually in the unit: pH * 10
            # So a value of 62 means pH 6.2
            ph = Decimal(str(round(layer_map["phh2o"] / 10.0, 2)))

        organic_carbon = None
        if "soc" in layer_map:
            # ISRIC: soc in g/kg (per gigagram). 1 g/kg = 0.1%
            # So a value of 15 g/kg = 1.5% organic carbon
            organic_carbon = Decimal(str(round(layer_map["soc"] / 10.0, 2)))

        clay_pct = None
        if "clay" in layer_map:
            # ISRIC: clay in g/kg (per thousand). 350 g/kg = 35%
            clay_pct = Decimal(str(round(layer_map["clay"] / 10.0, 2)))

        sand_pct = None
        if "sand" in layer_map:
            sand_pct = Decimal(str(round(layer_map["sand"] / 10.0, 2)))

        silt_pct = None
        if "silt" in layer_map:
            silt_pct = Decimal(str(round(layer_map["silt"] / 10.0, 2)))

        # Determine soil type from texture (USDA triangle approximation)
        soil_type = None
        if clay_pct is not None and sand_pct is not None and silt_pct is not None:
            soil_type = self._classify_soil_texture(
                float(clay_pct), float(sand_pct), float(silt_pct)
            )

        return ISRICSoilData(
            ph=ph,
            organic_carbon=organic_carbon,
            clay_pct=clay_pct,
            sand_pct=sand_pct,
            silt_pct=silt_pct,
            soil_type=soil_type,
            raw_data=data,
        )

    def _classify_soil_texture(
        self, clay: float, sand: float, silt: float
    ) -> str:
        """Classify soil type using the USDA soil texture triangle.

        Simplified 12-class system. Returns the texture class name.
        """
        # Sanity check — should sum to ~100
        total = clay + sand + silt
        if total < 95 or total > 105:
            logger.warning("isric.texture_sum_off", clay=clay, sand=sand, silt=silt, total=total)

        # USDA texture triangle (simplified)
        if clay >= 40 and sand <= 45:
            return "Clay"
        if clay >= 27 and sand <= 20:
            return "Silty Clay"
        if clay >= 35 and sand >= 45:
            return "Sandy Clay"
        if clay >= 20 and sand <= 45 and silt < 50:
            if clay >= 27:
                return "Clay Loam"
            return "Sandy Clay Loam" if sand >= 45 else "Clay Loam"
        if silt >= 50 and clay >= 12:
            return "Silty Clay Loam"
        if silt >= 80:
            return "Silt"
        if silt >= 50:
            return "Silt Loam"
        if sand >= 85:
            return "Sand"
        if sand >= 70:
            return "Loamy Sand"
        if sand >= 43 and clay < 20:
            return "Sandy Loam"
        return "Loam"  # Default catch-all


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_isric_client: ISRICClient | None = None


def get_isric_client() -> ISRICClient:
    """Get the singleton ISRIC client instance."""
    global _isric_client
    if _isric_client is None:
        _isric_client = ISRICClient()
    return _isric_client
