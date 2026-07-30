"""
Revision ID: 0004
Revises: 0003
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Crop data — sourced from ICAR / Ministry of Agriculture
# Format: (slug, name_en, name_hi, scientific_name, category, season,
#          duration_min, duration_max, water_mm)
CROPS = [
    # --- Cereals ---
    ("rice", "Rice", "चावल", "Oryza sativa", "cereals", "kharif", 90, 150, 1200),
    ("wheat", "Wheat", "गेहूं", "Triticum aestivum", "cereals", "rabi", 110, 140, 450),
    ("maize", "Maize", "मक्का", "Zea mays", "cereals", "kharif", 80, 110, 500),
    ("jowar", "Sorghum", "ज्वार", "Sorghum bicolor", "cereals", "kharif", 100, 130, 400),
    ("bajra", "Pearl Millet", "बाजरा", "Pennisetum glaucum", "cereals", "kharif", 75, 90, 350),
    ("ragi", "Finger Millet", "रागी", "Eleusine coracana", "cereals", "kharif", 110, 135, 400),
    ("barley", "Barley", "जौ", "Hordeum vulgare", "cereals", "rabi", 100, 120, 350),

    # --- Pulses ---
    ("tur", "Pigeon Pea", "अरहर", "Cajanus cajan", "pulses", "kharif", 150, 210, 400),
    ("gram", "Chickpea", "चना", "Cicer arietinum", "pulses", "rabi", 95, 120, 250),
    ("moong", "Green Gram", "मूंग", "Vigna radiata", "pulses", "kharif", 60, 75, 300),
    ("urad", "Black Gram", "उड़द", "Vigna mungo", "pulses", "kharif", 70, 90, 300),
    ("lentil", "Lentil", "मसूर", "Lens culinaris", "pulses", "rabi", 100, 130, 250),
    ("peas", "Field Pea", "मटर", "Pisum sativum", "pulses", "rabi", 100, 130, 250),

    # --- Oilseeds ---
    ("groundnut", "Groundnut", "मूंगफली", "Arachis hypogaea", "oilseeds", "kharif", 90, 120, 450),
    ("soybean", "Soybean", "सोयाबीन", "Glycine max", "oilseeds", "kharif", 90, 120, 500),
    ("mustard", "Mustard", "सरसों", "Brassica juncea", "oilseeds", "rabi", 110, 140, 250),
    ("sunflower", "Sunflower", "सूरजमुखी", "Helianthus annuus", "oilseeds", "kharif", 90, 110, 400),
    ("sesame", "Sesame", "तिल", "Sesamum indicum", "oilseeds", "kharif", 75, 95, 300),

    # --- Fibre ---
    ("cotton", "Cotton", "कपास", "Gossypium hirsutum", "fibre", "kharif", 150, 180, 700),
    ("jute", "Jute", "जूट", "Corchorus capsularis", "fibre", "kharif", 100, 120, 500),

    # --- Sugar ---
    ("sugarcane", "Sugarcane", "गन्ना", "Saccharum officinarum", "sugar", "kharif", 300, 365, 1500),

    # --- Plantation ---
    ("coconut", "Coconut", "नारियल", "Cocos nucifera", "plantation", "kharif", 0, 0, None),
    ("tea", "Tea", "चाय", "Camellia sinensis", "plantation", "rabi", 0, 0, None),
    ("coffee", "Coffee", "कॉफी", "Coffea arabica", "plantation", "rabi", 0, 0, None),
    ("rubber", "Rubber", "रबर", "Hevea brasiliensis", "plantation", "kharif", 0, 0, None),

    # --- Horticulture ---
    ("banana", "Banana", "केला", "Musa paradisiaca", "horticulture", "kharif", 300, 365, 1500),
    ("mango", "Mango", "आम", "Mangifera indica", "horticulture", "kharif", 0, 0, None),
    ("tomato", "Tomato", "टमाटर", "Solanum lycopersicum", "horticulture", "rabi", 70, 90, 600),
    ("onion", "Onion", "प्याज", "Allium cepa", "horticulture", "rabi", 100, 130, 400),
    ("potato", "Potato", "आलू", "Solanum tuberosum", "horticulture", "rabi", 90, 120, 500),

    # --- Spices ---
    ("chilli", "Chilli", "मिर्च", "Capsicum annuum", "spices", "kharif", 120, 150, 500),
    ("turmeric", "Turmeric", "हल्दी", "Curcuma longa", "spices", "kharif", 240, 270, 800),

    # --- Fodder ---
    ("fodder_maize", "Fodder Maize", "चारा मक्का", "Zea mays", "fodder", "kharif", 60, 75, 400),
]


def upgrade() -> None:
    # Use raw SQL for bulk insert (faster than individual INSERT statements)
    crops_table = sa.table(
        "crops",
        sa.column("slug", sa.String),
        sa.column("name_en", sa.String),
        sa.column("name_hi", sa.String),
        sa.column("scientific_name", sa.String),
        sa.column("crop_category", sa.String),
        sa.column("primary_season", sa.String),
        sa.column("duration_days_min", sa.Integer),
        sa.column("duration_days_max", sa.Integer),
        sa.column("water_requirement_mm", sa.Integer),
        sa.column("is_active", sa.Boolean),
        schema="farmer",
    )

    rows = [
        {
            "slug": slug,
            "name_en": name_en,
            "name_hi": name_hi,
            "scientific_name": sci,
            "crop_category": category,
            "primary_season": season,
            "duration_days_min": dur_min,
            "duration_days_max": dur_max,
            "water_requirement_mm": water,
            "is_active": True,
        }
        for (slug, name_en, name_hi, sci, category, season, dur_min, dur_max, water) in CROPS
    ]

    op.bulk_insert(crops_table, rows)


def downgrade() -> None:
    # Delete all seeded crops (preserves any user-added ones if we had a UI for that)
    op.execute("DELETE FROM farmer.crops WHERE slug IN :slugs")
    # Note: parameterized DDL doesn't work in Alembic; use explicit list
    slugs = ", ".join(f"'{c[0]}'" for c in CROPS)
    op.execute(f"DELETE FROM farmer.crops WHERE slug IN ({slugs})")
