"""Insurance domain — PMFBY policies, claims, evidence.

This module handles:
- Insurance product catalog (PMFBY and state crop insurance schemes)
- Policy enrollment (farmer buys insurance for a plot+crop)
- Claim filing (with auto-attached evidence from NDVI, disease, weather)
- Insurer claim review workflow

Key cross-module workflows:
- Disease → Claim: When a disease is detected on an insured plot, suggest claim filing
- NDVI drop → Claim: When NDVI anomaly detected on insured plot, attach as evidence
- Weather alert → Claim: When extreme weather hits an insured plot, attach as evidence

See KrishiSetu_Architecture_Plan.md §14.6 for full module specification.
"""
