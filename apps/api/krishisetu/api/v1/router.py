"""API v1 router aggregator.

All domain routers are mounted here under the /api/v1 prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from krishisetu.api.v1 import health, integrations
from krishisetu.domains.identity.routes import (
    admin_router as identity_admin_router,
    me_router as identity_me_router,
    router as identity_router,
)
from krishisetu.domains.farmer.routes import (
    crops_router as farmer_crops_router,
    crop_cycles_router as farmer_crop_cycles_router,
    officer_router as farmer_officer_router,
    plots_router as farmer_plots_router,
)
from krishisetu.domains.disease.routes import (
    disease_router,
    diseases_router,
    officer_disease_router,
)
from krishisetu.domains.soil_weather.routes import (
    admin_weather_router,
    district_weather_router,
    plot_soil_router,
    plot_weather_router,
)
from krishisetu.domains.ndvi.routes import (
    ndvi_anomaly_router,
    officer_ndvi_router,
    plot_ndvi_router,
)
from krishisetu.domains.insurance.routes import (
    claims_router as insurance_claims_router,
    insurer_router as insurance_insurer_router,
    policies_router as insurance_policies_router,
    products_router as insurance_products_router,
)
from krishisetu.domains.marketplace.routes import (
    marketplace_router,
    supplier_router,
)
from krishisetu.domains.schemes.routes import (
    officer_router as schemes_officer_router,
    schemes_router,
)
from krishisetu.domains.voice.routes import router as voice_router
from krishisetu.domains.payment.routes import router as payment_router
from krishisetu.domains.consent.routes import (
    admin_router as consent_admin_router,
    router as consent_router,
)
from krishisetu.domains.privacy.routes import (
    officer_router as privacy_officer_router,
    router as privacy_router,
)
from krishisetu.domains.audit.routes import router as audit_router

api_router = APIRouter()

# Health & system
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(integrations.router, prefix="/health", tags=["health"])

# Identity & auth
api_router.include_router(identity_router, tags=["authentication"])
api_router.include_router(identity_me_router, tags=["profile"])
api_router.include_router(identity_admin_router, tags=["admin"])

# Farmer domain: plots, crop cycles, crops master data, officer verification
api_router.include_router(farmer_plots_router)
api_router.include_router(farmer_crop_cycles_router)
api_router.include_router(farmer_crops_router)
api_router.include_router(farmer_officer_router)

# Disease domain: disease reports, disease catalog, officer review
api_router.include_router(disease_router)
api_router.include_router(diseases_router)
api_router.include_router(officer_disease_router)

# Soil & Weather domain: weather observations, forecasts, alerts, soil tests
api_router.include_router(plot_weather_router)
api_router.include_router(plot_soil_router)
api_router.include_router(district_weather_router)
api_router.include_router(admin_weather_router)

# NDVI domain: vegetation health, anomaly alerts, district heatmap
api_router.include_router(plot_ndvi_router)
api_router.include_router(ndvi_anomaly_router)
api_router.include_router(officer_ndvi_router)

# Insurance domain: products, policies, claims, insurer review
api_router.include_router(insurance_products_router)
api_router.include_router(insurance_policies_router)
api_router.include_router(insurance_claims_router)
api_router.include_router(insurance_insurer_router)

# Marketplace domain: products, orders, supplier management
api_router.include_router(marketplace_router)
api_router.include_router(supplier_router)

# Schemes domain: govt scheme discovery, eligibility, applications, officer review
api_router.include_router(schemes_router)
api_router.include_router(schemes_officer_router)

# Voice domain: voice query (ASR + NLU), TTS
api_router.include_router(voice_router)

# Payment domain: Razorpay/UPI, escrow, refunds, webhooks
api_router.include_router(payment_router)

# Phase F: Consent (DPDP), Privacy (DSR + grievances), Audit (admin)
api_router.include_router(consent_router)
api_router.include_router(consent_admin_router)
api_router.include_router(privacy_router)
api_router.include_router(privacy_officer_router)
api_router.include_router(audit_router)
