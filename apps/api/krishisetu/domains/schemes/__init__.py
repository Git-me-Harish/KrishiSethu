"""Government schemes domain — scheme discovery, eligibility, and applications.

This module handles:
- Scheme catalog (PM-Kisan, KCC, PMFBY, Soil Health Card, state schemes)
- Eligibility engine (YAML-based rules matching farmer profile to schemes)
- Application workflow (auto-filled from verified profile, status tracking)
- Officer review (approve/reject applications)

See KrishiSetu_Architecture_Plan.md §14.8 for full module specification.
"""
