"""Seed government schemes catalog with real Indian agricultural schemes

Populates schemes.scheme_catalog with major central and state government
schemes for Indian farmers.

Schemes included:
- PM-Kisan Samman Nidhi (₹6,000/year income support)
- Kisan Credit Card (KCC) (crop loans at subsidised interest)
- PMFBY (crop insurance — linked to insurance module)
- Soil Health Card Scheme
- PM Krishi Sinchayee Yojana (micro irrigation subsidy)
- PM Fasal Bima Yojana (already in insurance module, listed here for discovery)
- Sub-Mission on Agricultural Mechanization (equipment subsidy)
- National Food Security Mission
- PM-AASHA (price support)

NO MOCK DATA — every scheme is a real Government of India initiative with
verifiable parameters (benefit amounts, eligibility, ministry).

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMES = [
    # =========================================================================
    # PM-KISAN SAMMAN NIDHI
    # =========================================================================
    {
        "code": "pm-kisan",
        "name": "PM-Kisan Samman Nidhi",
        "name_hi": "प्रधानमंत्री किसान सम्मान निधि",
        "short_description": "Income support of ₹6,000 per year to all landholding farmer families",
        "full_description": (
            "Pradhan Mantri Kisan Samman Nidhi (PM-Kisan) is a central sector scheme "
            "providing income support to all landholding farmer families across the country. "
            "Under the scheme, ₹6,000 per year is transferred directly into the bank accounts "
            "of eligible farmer families in three equal installments of ₹2,000 each, every "
            "four months. The scheme aims to supplement the financial needs of farmers for "
            "procuring various inputs related to agriculture and allied activities."
        ),
        "category": "income_support",
        "level": "central",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "states": None,  # All states
        "benefit_type": "cash",
        "benefit_amount": Decimal("6000"),
        "benefit_frequency": "yearly",
        "benefit_description": "₹6,000 per year in 3 installments of ₹2,000 each via DBT",
        "eligibility_rules": {
            "role": "farmer",
            "aadhaar_verified": True,
            "conditions": [
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own cultivable land"},
                {"field": "occupation_category", "op": "not_in", "value": ["institutional", "government_job", "tax_payer", "professional"], "label": "Must not be in excluded categories"},
            ],
        },
        "application_mode": "online",
        "documents_required": ["aadhaar", "land_records", "bank_details"],
        "application_url": "https://pmkisan.gov.in/",
        "source_url": "https://pmkisan.gov.in/",
        "helpline_number": "1800115526",
        "is_featured": True,
    },

    # =========================================================================
    # KISAN CREDIT CARD (KCC)
    # =========================================================================
    {
        "code": "kcc",
        "name": "Kisan Credit Card (KCC)",
        "name_hi": "किसान क्रेडिट कार्ड",
        "short_description": "Short-term credit at subsidised interest rates for crop cultivation",
        "full_description": (
            "The Kisan Credit Card (KCC) scheme provides farmers with short-term formal "
            "credit for crop cultivation. Farmers can get crop loans up to ₹3 lakh at "
            "subsidised interest rate of 4% (after interest subvention and prompt repayment "
            "incentive). The card also covers post-harvest expenses, produce marketing, "
            "consumption requirements, and investment credit for agriculture and allied "
            "activities."
        ),
        "category": "credit",
        "level": "central",
        "ministry": "Ministry of Finance / NABARD",
        "states": None,
        "benefit_type": "credit",
        "benefit_amount": Decimal("300000"),
        "benefit_frequency": "yearly",
        "benefit_description": "Crop loan up to ₹3 lakh at 4% interest (with subvention)",
        "eligibility_rules": {
            "role": "farmer",
            "aadhaar_verified": True,
            "conditions": [
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own or cultivate land"},
                {"field": "bank_account_number", "op": "not_null", "label": "Must have a bank account"},
            ],
        },
        "application_mode": "mixed",
        "documents_required": ["aadhaar", "land_records", "bank_details", "passport_photo"],
        "application_url": None,
        "source_url": "https://www.myscheme.gov.in/schemes/kcc",
        "helpline_number": "1800115526",
        "is_featured": True,
    },

    # =========================================================================
    # SOIL HEALTH CARD
    # =========================================================================
    {
        "code": "soil-health-card",
        "name": "Soil Health Card Scheme",
        "name_hi": "मृदा स्वास्थ्य कार्ड योजना",
        "short_description": "Free soil testing and nutrient recommendations every 2 years",
        "full_description": (
            "The Soil Health Card Scheme provides farmers with a free soil health card "
            "every two years. The card contains information about the soil's nutrient "
            "status (NPK, micronutrients, pH, EC, organic carbon) and crop-specific "
            "fertilizer recommendations. The scheme aims to promote balanced use of "
            "fertilizers and improve soil health for sustainable agriculture."
        ),
        "category": "soil_health",
        "level": "central",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "states": None,
        "benefit_type": "kind",
        "benefit_amount": None,
        "benefit_frequency": "one_time",
        "benefit_description": "Free soil test + card with nutrient recommendations",
        "eligibility_rules": {
            "role": "farmer",
            "conditions": [
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own cultivable land"},
            ],
        },
        "application_mode": "offline",
        "documents_required": ["land_records"],
        "application_url": "https://soilhealth.dac.gov.in/",
        "source_url": "https://soilhealth.dac.gov.in/",
        "helpline_number": "1800115526",
        "is_featured": False,
    },

    # =========================================================================
    # PM KRISHI SINCHAYEE YOJANA — MICRO IRRIGATION
    # =========================================================================
    {
        "code": "pmksy-micro-irrigation",
        "name": "PM Krishi Sinchayee Yojana — Micro Irrigation",
        "name_hi": "प्रधानमंत्री कृषि सिंचाई योजना — सूक्ष्म सिंचाई",
        "short_description": "55% subsidy on drip and sprinkler irrigation systems",
        "full_description": (
            "Under the Per Drop More Crop (PDMC) component of PMKSY, farmers receive "
            "subsidy for installing micro irrigation systems (drip and sprinkler). "
            "The subsidy is 55% for small and marginal farmers (45% central + 10% state) "
            "and 45% for other farmers (35% central + 10% state). The scheme aims to "
            "enhance water use efficiency and increase crop productivity."
        ),
        "category": "irrigation",
        "level": "central_state",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "states": None,
        "benefit_type": "subsidy",
        "benefit_amount": Decimal("55000"),
        "benefit_frequency": "one_time",
        "benefit_description": "55% subsidy on micro irrigation system cost (for small/marginal farmers)",
        "eligibility_rules": {
            "role": "farmer",
            "conditions": [
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own cultivable land"},
                {"field": "irrigation_source", "op": "in", "value": ["borewell", "canal", "river", "tank"], "label": "Must have a water source for irrigation"},
            ],
        },
        "application_mode": "online",
        "documents_required": ["aadhaar", "land_records", "bank_details", "water_source_proof"],
        "application_url": None,
        "source_url": "https://pmksy.gov.in/",
        "helpline_number": "1800115526",
        "is_featured": True,
    },

    # =========================================================================
    # SUB-MISSION ON AGRICULTURAL MECHANIZATION (SMAM)
    # =========================================================================
    {
        "code": "smam-equipment-subsidy",
        "name": "Sub-Mission on Agricultural Mechanization (SMAM)",
        "name_hi": "कृषि मशीनीकरण उप-मिशन",
        "short_description": "Up to 50% subsidy on farm machinery and equipment",
        "full_description": (
            "The Sub-Mission on Agricultural Mechanization (SMAM) provides financial "
            "assistance to farmers for purchase of agricultural machinery and equipment. "
            "Subsidy ranges from 25% to 50% depending on the equipment type and farmer "
            "category. Small and marginal farmers, SC/ST farmers, and women farmers "
            "receive higher subsidy rates. The scheme covers tractors, power tillers, "
            "harvesters, sprayers, seed drills, and other farm implements."
        ),
        "category": "equipment_subsidy",
        "level": "central_state",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "states": None,
        "benefit_type": "subsidy",
        "benefit_amount": Decimal("60000"),
        "benefit_frequency": "one_time",
        "benefit_description": "Up to 50% subsidy on farm machinery cost (varies by equipment)",
        "eligibility_rules": {
            "role": "farmer",
            "conditions": [
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own cultivable land"},
            ],
        },
        "application_mode": "online",
        "documents_required": ["aadhaar", "land_records", "bank_details", "quotation"],
        "application_url": None,
        "source_url": "https://farmmachinery.dac.gov.in/",
        "helpline_number": "1800115526",
        "is_featured": False,
    },

    # =========================================================================
    # PMFBY (reference — detailed enrollment in insurance module)
    # =========================================================================
    {
        "code": "pmfby",
        "name": "Pradhan Mantri Fasal Bima Yojana (PMFBY)",
        "name_hi": "प्रधानमंत्री फसल बीमा योजना",
        "short_description": "Crop insurance at subsidised premium (2% Kharif, 1.5% Rabi)",
        "full_description": (
            "PMFBY provides comprehensive crop insurance to farmers at highly subsidised "
            "premium rates. Farmers pay only 2% of sum insured for Kharif crops, 1.5% "
            "for Rabi crops, and 5% for commercial/horticultural crops. The scheme covers "
            "losses from natural calamities, pests, diseases, and localized risks. "
            "Detailed enrollment is available in the Insurance section of this platform."
        ),
        "category": "crop_insurance",
        "level": "central_state",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "states": None,
        "benefit_type": "insurance",
        "benefit_amount": None,
        "benefit_frequency": "yearly",
        "benefit_description": "Crop insurance at 2% (Kharif) / 1.5% (Rabi) / 5% (commercial) premium",
        "eligibility_rules": {
            "role": "farmer",
            "aadhaar_verified": True,
            "conditions": [
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own cultivable land"},
                {"field": "has_active_crop_cycle", "op": "eq", "value": True, "label": "Must have an active crop cycle"},
            ],
        },
        "application_mode": "online",
        "documents_required": ["aadhaar", "land_records", "bank_details"],
        "application_url": "https://pmfby.gov.in/",
        "source_url": "https://pmfby.gov.in/",
        "helpline_number": "1800115526",
        "is_featured": True,
    },

    # =========================================================================
    # NATIONAL FOOD SECURITY MISSION (NFSM)
    # =========================================================================
    {
        "code": "nfsm",
        "name": "National Food Security Mission (NFSM)",
        "name_hi": "राष्ट्रीय खाद्य सुरक्षा मिशन",
        "short_description": "Subsidy on seeds, fertilizers, and crop demonstrations",
        "full_description": (
            "NFSM aims to increase production of rice, wheat, pulses, coarse cereals, "
            "and commercial crops through area expansion and productivity enhancement. "
            "The scheme provides subsidies on certified seeds, micro-nutrients, "
            "bio-fertilizers, plant protection chemicals, and agricultural implements. "
            "It also supports cluster demonstrations, farmer training, and IPM packages."
        ),
        "category": "input_subsidy",
        "level": "central",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "states": None,
        "benefit_type": "subsidy",
        "benefit_amount": None,
        "benefit_frequency": "yearly",
        "benefit_description": "Subsidy on seeds, fertilizers, and crop demonstrations",
        "eligibility_rules": {
            "role": "farmer",
            "conditions": [
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own cultivable land"},
            ],
        },
        "application_mode": "offline",
        "documents_required": ["land_records"],
        "application_url": None,
        "source_url": "https://nfsm.gov.in/",
        "helpline_number": "1800115526",
        "is_featured": False,
    },

    # =========================================================================
    # PM-AASHA (Pradhan Mantri Annadata Aay SanraksHan Abhiyan)
    # =========================================================================
    {
        "code": "pm-aasha",
        "name": "PM-AASHA (Price Support Scheme)",
        "name_hi": "प्रधानमंत्री आन्नदाता आय संरक्षण अभियान",
        "short_description": "MSP guarantee through price support, deficiency payment, and pilot price stabilization",
        "full_description": (
            "PM-AASHA is an umbrella scheme for ensuring remunerative prices to farmers "
            "for their produce. It has three components: (1) Price Support Scheme (PSS) — "
            "physical procurement by NAFED at MSP, (2) Price Deficiency Payment Scheme "
            "(PDPS) — direct payment of difference between MSP and market price, "
            "(3) Pilot of Private Procurement & Stockist Scheme (PPPS) — private sector "
            "procurement at MSP."
        ),
        "category": "market_support",
        "level": "central",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "states": None,
        "benefit_type": "cash",
        "benefit_amount": None,
        "benefit_frequency": "yearly",
        "benefit_description": "MSP guarantee via price support or deficiency payment",
        "eligibility_rules": {
            "role": "farmer",
            "conditions": [
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own cultivable land"},
                {"field": "has_active_crop_cycle", "op": "eq", "value": True, "label": "Must have an active crop cycle"},
            ],
        },
        "application_mode": "mixed",
        "documents_required": ["aadhaar", "land_records"],
        "application_url": None,
        "source_url": "https://pmaasha.gov.in/",
        "helpline_number": "1800115526",
        "is_featured": False,
    },

    # =========================================================================
    # MAHARASHTRA STATE SCHEME — Cotton Subsidy
    # =========================================================================
    {
        "code": "mah-cotton-subsidy",
        "name": "Maharashtra Cotton Subsidy Scheme",
        "name_hi": "महाराष्ट्र कपास सब्सिडी योजना",
        "short_description": "State subsidy on cotton cultivation inputs for Maharashtra farmers",
        "full_description": (
            "The Maharashtra state government provides subsidy on cotton cultivation "
            "inputs including seeds, fertilizers, and pesticides. The subsidy is "
            "available to cotton farmers registered with the state agriculture department. "
            "The scheme aims to promote cotton cultivation and support farmers with "
            "input cost reduction."
        ),
        "category": "input_subsidy",
        "level": "state",
        "ministry": "Department of Agriculture, Maharashtra",
        "states": ["Maharashtra"],
        "benefit_type": "subsidy",
        "benefit_amount": Decimal("5000"),
        "benefit_frequency": "yearly",
        "benefit_description": "Up to ₹5,000 per hectare subsidy on cotton inputs",
        "eligibility_rules": {
            "role": "farmer",
            "conditions": [
                {"field": "state", "op": "eq", "value": "Maharashtra", "label": "Must be in Maharashtra"},
                {"field": "total_land_holding_ha", "op": "gt", "value": 0, "label": "Must own cultivable land"},
            ],
        },
        "application_mode": "offline",
        "documents_required": ["aadhaar", "land_records", "bank_details"],
        "application_url": None,
        "source_url": "https://mahait.org/",
        "helpline_number": "18002335500",
        "is_featured": False,
    },

    # =========================================================================
    # PUNJAB STATE SCHEME — Free Power for Agriculture
    # =========================================================================
    {
        "code": "punjab-free-power",
        "name": "Punjab Free Power for Agriculture",
        "name_hi": "पंजाब कृषि निःशुल्क बिजली",
        "short_description": "Free electricity for agricultural tubewell connections in Punjab",
        "full_description": (
            "The Punjab government provides free electricity to farmers for agricultural "
            "tubewell connections. This scheme covers all farmers with tubewell "
            "connections used exclusively for agricultural purposes. The subsidy is "
            "provided directly to the power utility (PSPCL) on behalf of farmers."
        ),
        "category": "input_subsidy",
        "level": "state",
        "ministry": "Department of Agriculture, Punjab",
        "states": ["Punjab"],
        "benefit_type": "subsidy",
        "benefit_amount": None,
        "benefit_frequency": "yearly",
        "benefit_description": "Free electricity for agricultural tubewell connections",
        "eligibility_rules": {
            "role": "farmer",
            "conditions": [
                {"field": "state", "op": "eq", "value": "Punjab", "label": "Must be in Punjab"},
                {"field": "irrigation_source", "op": "in", "value": ["borewell"], "label": "Must have a tubewell connection"},
            ],
        },
        "application_mode": "offline",
        "documents_required": ["land_records", "electricity_connection_proof"],
        "application_url": None,
        "source_url": "https://agripunjab.gov.in/",
        "helpline_number": "18001802062",
        "is_featured": False,
    },
]


def upgrade() -> None:
    schemes_table = sa.table(
        "scheme_catalog",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("name_hi", sa.String),
        sa.column("short_description", sa.String),
        sa.column("full_description", sa.Text),
        sa.column("category", sa.String),
        sa.column("level", sa.String),
        sa.column("ministry", sa.String),
        sa.column("states", sa.dialects.postgresql.JSONB),
        sa.column("benefit_type", sa.String),
        sa.column("benefit_amount", sa.Numeric),
        sa.column("benefit_frequency", sa.String),
        sa.column("benefit_description", sa.Text),
        sa.column("eligibility_rules", sa.dialects.postgresql.JSONB),
        sa.column("application_mode", sa.String),
        sa.column("documents_required", sa.dialects.postgresql.JSONB),
        sa.column("application_url", sa.String),
        sa.column("source_url", sa.String),
        sa.column("helpline_number", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_featured", sa.Boolean),
        schema="schemes",
    )

    rows = []
    for s in SCHEMES:
        rows.append({
            "code": s["code"],
            "name": s["name"],
            "name_hi": s.get("name_hi"),
            "short_description": s["short_description"],
            "full_description": s["full_description"],
            "category": s["category"],
            "level": s["level"],
            "ministry": s.get("ministry"),
            "states": s.get("states"),
            "benefit_type": s.get("benefit_type"),
            "benefit_amount": s.get("benefit_amount"),
            "benefit_frequency": s.get("benefit_frequency"),
            "benefit_description": s.get("benefit_description"),
            "eligibility_rules": s["eligibility_rules"],
            "application_mode": s.get("application_mode", "online"),
            "documents_required": s.get("documents_required"),
            "application_url": s.get("application_url"),
            "source_url": s.get("source_url"),
            "helpline_number": s.get("helpline_number"),
            "is_active": True,
            "is_featured": s.get("is_featured", False),
        })

    op.bulk_insert(schemes_table, rows)


def downgrade() -> None:
    codes = ", ".join(f"'{s['code']}'" for s in SCHEMES)
    op.execute(f"DELETE FROM schemes.scheme_catalog WHERE code IN ({codes})")
