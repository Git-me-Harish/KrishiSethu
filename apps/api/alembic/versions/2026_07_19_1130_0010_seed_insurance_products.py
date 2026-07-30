"""

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# PMFBY products for major states and crops
# Format: (slug, name, crop_slug, crop_name, season, season_year, state,
#          sum_insured_per_ha, farmer_premium_rate, coverage_start, coverage_end,
#          claim_cutoff_yield_kg_per_ha)
#
# Sum insured values are typical PMFBY rates (₹/ha) for 2024-25
# Premium rates: 2% Kharif, 1.5% Rabi (PMFBY operational guidelines)
# Cutoff yields are state-level threshold yields (kg/ha) for widespread risk
PRODUCTS = [
    # =========================================================================
    # Kharif 2026 — Maharashtra
    # =========================================================================
    ("pmfby-rice-kharif-2026-maharashtra", "PMFBY Rice Kharif 2026 - Maharashtra",
     "rice", "Rice (Paddy)", "kharif", 2026, "Maharashtra",
     Decimal("55000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("2500")),
    ("pmfby-cotton-kharif-2026-maharashtra", "PMFBY Cotton Kharif 2026 - Maharashtra",
     "cotton", "Cotton", "kharif", 2026, "Maharashtra",
     Decimal("75000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1200")),
    ("pmfby-soybean-kharif-2026-maharashtra", "PMFBY Soybean Kharif 2026 - Maharashtra",
     "soybean", "Soybean", "kharif", 2026, "Maharashtra",
     Decimal("45000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1800")),
    ("pmfby-tur-kharif-2026-maharashtra", "PMFBY Pigeon Pea Kharif 2026 - Maharashtra",
     "tur", "Pigeon Pea (Tur)", "kharif", 2026, "Maharashtra",
     Decimal("65000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1200")),
    ("pmfby-groundnut-kharif-2026-maharashtra", "PMFBY Groundnut Kharif 2026 - Maharashtra",
     "groundnut", "Groundnut", "kharif", 2026, "Maharashtra",
     Decimal("50000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1500")),

    # =========================================================================
    # Kharif 2026 — Punjab
    # =========================================================================
    ("pmfby-rice-kharif-2026-punjab", "PMFBY Rice Kharif 2026 - Punjab",
     "rice", "Rice (Paddy)", "kharif", 2026, "Punjab",
     Decimal("65000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("3500")),
    ("pmfby-cotton-kharif-2026-punjab", "PMFBY Cotton Kharif 2026 - Punjab",
     "cotton", "Cotton", "kharif", 2026, "Punjab",
     Decimal("80000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1400")),
    ("pmfby-maize-kharif-2026-punjab", "PMFBY Maize Kharif 2026 - Punjab",
     "maize", "Maize", "kharif", 2026, "Punjab",
     Decimal("45000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("3500")),

    # =========================================================================
    # Kharif 2026 — Karnataka
    # =========================================================================
    ("pmfby-rice-kharif-2026-karnataka", "PMFBY Rice Kharif 2026 - Karnataka",
     "rice", "Rice (Paddy)", "kharif", 2026, "Karnataka",
     Decimal("58000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("2800")),
    ("pmfby-maize-kharif-2026-karnataka", "PMFBY Maize Kharif 2026 - Karnataka",
     "maize", "Maize", "kharif", 2026, "Karnataka",
     Decimal("42000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("3200")),
    ("pmfby-groundnut-kharif-2026-karnataka", "PMFBY Groundnut Kharif 2026 - Karnataka",
     "groundnut", "Groundnut", "kharif", 2026, "Karnataka",
     Decimal("48000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1600")),

    # =========================================================================
    # Kharif 2026 — Tamil Nadu
    # =========================================================================
    ("pmfby-rice-kharif-2026-tamilnadu", "PMFBY Rice Kharif 2026 - Tamil Nadu",
     "rice", "Rice (Paddy)", "kharif", 2026, "Tamil Nadu",
     Decimal("60000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("3000")),
    ("pmfby-groundnut-kharif-2026-tamilnadu", "PMFBY Groundnut Kharif 2026 - Tamil Nadu",
     "groundnut", "Groundnut", "kharif", 2026, "Tamil Nadu",
     Decimal("52000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1700")),
    ("pmfby-cotton-kharif-2026-tamilnadu", "PMFBY Cotton Kharif 2026 - Tamil Nadu",
     "cotton", "Cotton", "kharif", 2026, "Tamil Nadu",
     Decimal("72000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1300")),

    # =========================================================================
    # Kharif 2026 — Uttar Pradesh
    # =========================================================================
    ("pmfby-rice-kharif-2026-up", "PMFBY Rice Kharif 2026 - Uttar Pradesh",
     "rice", "Rice (Paddy)", "kharif", 2026, "Uttar Pradesh",
     Decimal("52000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("2600")),
    ("pmfby-maize-kharif-2026-up", "PMFBY Maize Kharif 2026 - Uttar Pradesh",
     "maize", "Maize", "kharif", 2026, "Uttar Pradesh",
     Decimal("40000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("3000")),
    ("pmfby-tur-kharif-2026-up", "PMFBY Pigeon Pea Kharif 2026 - Uttar Pradesh",
     "tur", "Pigeon Pea (Tur)", "kharif", 2026, "Uttar Pradesh",
     Decimal("62000"), Decimal("0.02"), "2026-06-01", "2026-10-31", Decimal("1100")),

    # =========================================================================
    # Rabi 2026-27 — Punjab
    # =========================================================================
    ("pmfby-wheat-rabi-2026-punjab", "PMFBY Wheat Rabi 2026-27 - Punjab",
     "wheat", "Wheat", "rabi", 2026, "Punjab",
     Decimal("55000"), Decimal("0.015"), "2026-11-01", "2027-03-31", Decimal("4000")),
    ("pmfby-mustard-rabi-2026-punjab", "PMFBY Mustard Rabi 2026-27 - Punjab",
     "mustard", "Mustard", "rabi", 2026, "Punjab",
     Decimal("48000"), Decimal("0.015"), "2026-11-01", "2027-03-31", Decimal("1800")),

    # =========================================================================
    # Rabi 2026-27 — Uttar Pradesh
    # =========================================================================
    ("pmfby-wheat-rabi-2026-up", "PMFBY Wheat Rabi 2026-27 - Uttar Pradesh",
     "wheat", "Wheat", "rabi", 2026, "Uttar Pradesh",
     Decimal("50000"), Decimal("0.015"), "2026-11-01", "2027-03-31", Decimal("3500")),
    ("pmfby-mustard-rabi-2026-up", "PMFBY Mustard Rabi 2026-27 - Uttar Pradesh",
     "mustard", "Mustard", "rabi", 2026, "Uttar Pradesh",
     Decimal("45000"), Decimal("0.015"), "2026-11-01", "2027-03-31", Decimal("1600")),
    ("pmfby-gram-rabi-2026-up", "PMFBY Gram (Chickpea) Rabi 2026-27 - Uttar Pradesh",
     "gram", "Gram (Chickpea)", "rabi", 2026, "Uttar Pradesh",
     Decimal("52000"), Decimal("0.015"), "2026-11-01", "2027-03-31", Decimal("1500")),

    # =========================================================================
    # Rabi 2026-27 — Maharashtra
    # =========================================================================
    ("pmfby-wheat-rabi-2026-maharashtra", "PMFBY Wheat Rabi 2026-27 - Maharashtra",
     "wheat", "Wheat", "rabi", 2026, "Maharashtra",
     Decimal("48000"), Decimal("0.015"), "2026-11-01", "2027-03-31", Decimal("2800")),
    ("pmfby-gram-rabi-2026-maharashtra", "PMFBY Gram Rabi 2026-27 - Maharashtra",
     "gram", "Gram (Chickpea)", "rabi", 2026, "Maharashtra",
     Decimal("50000"), Decimal("0.015"), "2026-11-01", "2027-03-31", Decimal("1300")),

    # =========================================================================
    # Rabi 2026-27 — Karnataka
    # =========================================================================
    ("pmfby-wheat-rabi-2026-karnataka", "PMFBY Wheat Rabi 2026-27 - Karnataka",
     "wheat", "Wheat", "rabi", 2026, "Karnataka",
     Decimal("46000"), Decimal("0.015"), "2026-11-01", "2027-03-31", Decimal("2600")),

    # =========================================================================
    # Commercial/Horticultural crops (5% premium) — all states
    # =========================================================================
    ("pmfby-sugarcane-kharif-2026-maharashtra", "PMFBY Sugarcane Kharif 2026 - Maharashtra",
     "sugarcane", "Sugarcane", "kharif", 2026, "Maharashtra",
     Decimal("95000"), Decimal("0.05"), "2026-06-01", "2027-05-31", Decimal("70000")),
    ("pmfby-sugarcane-kharif-2026-up", "PMFBY Sugarcane Kharif 2026 - Uttar Pradesh",
     "sugarcane", "Sugarcane", "kharif", 2026, "Uttar Pradesh",
     Decimal("90000"), Decimal("0.05"), "2026-06-01", "2027-05-31", Decimal("68000")),
    ("pmfby-banana-kharif-2026-maharashtra", "PMFBY Banana Kharif 2026 - Maharashtra",
     "banana", "Banana", "kharif", 2026, "Maharashtra",
     Decimal("120000"), Decimal("0.05"), "2026-06-01", "2027-05-31", None),
    ("pmfby-banana-kharif-2026-tamilnadu", "PMFBY Banana Kharif 2026 - Tamil Nadu",
     "banana", "Banana", "kharif", 2026, "Tamil Nadu",
     Decimal("125000"), Decimal("0.05"), "2026-06-01", "2027-05-31", None),
]


def upgrade() -> None:
    products_table = sa.table(
        "insurance_products",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("product_type", sa.String),
        sa.column("insurer_name", sa.String),
        sa.column("crop_slug", sa.String),
        sa.column("crop_name", sa.String),
        sa.column("season", sa.String),
        sa.column("season_year", sa.Integer),
        sa.column("state", sa.String),
        sa.column("district", sa.String),
        sa.column("sum_insured_per_ha", sa.Numeric),
        sa.column("farmer_premium_rate", sa.Numeric),
        sa.column("coverage_start_date", sa.Date),
        sa.column("coverage_end_date", sa.Date),
        sa.column("claim_cutoff_yield", sa.Numeric),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
        schema="insurance",
    )

    rows = []
    for (slug, name, crop_slug, crop_name, season, season_year, state,
         sum_insured, premium_rate, cov_start, cov_end, cutoff_yield) in PRODUCTS:
        # Determine insurer (AIC of India is the primary PMFBY insurer)
        insurer = "Agriculture Insurance Company of India"

        description = (
            f"Pradhan Mantri Fasal Bima Yojana (PMFBY) for {crop_name} in {state} "
            f"during {season.title()} {season_year}. "
            f"Sum insured: ₹{sum_insured:,}/ha. "
            f"Farmer premium: {float(premium_rate)*100}% (subsidized). "
            f"Coverage: {cov_start} to {cov_end}."
        )

        rows.append({
            "slug": slug,
            "name": name,
            "product_type": "pmfby",
            "insurer_name": insurer,
            "crop_slug": crop_slug,
            "crop_name": crop_name,
            "season": season,
            "season_year": season_year,
            "state": state,
            "district": None,  # All districts in the state
            "sum_insured_per_ha": sum_insured,
            "farmer_premium_rate": premium_rate,
            "farmer_premium_min": None,
            "farmer_premium_max": None,
            "coverage_start_date": cov_start,
            "coverage_end_date": cov_end,
            "claim_cutoff_yield": cutoff_yield,
            "description": description,
            "is_active": True,
        })

    op.bulk_insert(products_table, rows)


def downgrade() -> None:
    slugs = ", ".join(f"'{p[0]}'" for p in PRODUCTS)
    op.execute(f"DELETE FROM insurance.insurance_products WHERE slug IN ({slugs})")
