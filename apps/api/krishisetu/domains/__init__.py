"""Identity domain — authentication, Aadhaar e-KYC, sessions, RBAC.

This module will be implemented in Phase 1, Sprint 2 (weeks 3-4).

Planned components:
- `models.py`  — User, Session, OTP, AadhaarVerification SQLAlchemy models
- `schemas.py` — Pydantic request/response schemas
- `services.py` — Business logic (OTP generation, JWT issuance, etc.)
- `repository.py` — Database access layer
- `routes.py`  — FastAPI routes (/auth/send-otp, /auth/verify-otp, etc.)

See KrishiSetu_Architecture_Plan.md §14.1 for full module specification.
"""
