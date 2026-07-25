# KrishiSetu DPDP Act 2023 Compliance

**Status**: Phase F implementation complete
**Last reviewed**: 2026-07-24
**Grievance Officer**: grievance@krishisetu.in (configure via `DPDP_GRIEVANCE_OFFICER_EMAIL`)
**Statutory SLA**: Acknowledge grievances within 24 hours; resolve within 30 days

---

## 1. Scope

This document maps KrishiSetu's implementation to the **Digital Personal Data Protection Act, 2023** (DPDP), which governs the processing of personal data of Indian residents (data principals) by entities (data fiduciaries).

KrishiSetu is a **Data Fiduciary** — we determine the purposes and means of processing farmers' personal data. We are NOT a Significant Data Fiduciary (SDF) at our current scale; if we cross the SDF threshold (to be notified by the Data Protection Board), we will appoint a Data Protection Officer and conduct annual audits.

**Personal data processed**: name, phone number, Aadhaar (during e-KYC, stored only as SHA-256 hash), bank account (encrypted), plot location (geospatial), crop disease photos, voice queries, transaction history.

**Sensitive personal data**: Aadhaar number, bank account, biometric (voice, only during query processing).

---

## 2. DPDP Section-by-Section Compliance Map

### Section 4 — Lawful Processing

> Personal data may be processed only for a lawful purpose, with the consent of the data principal.

**Implementation**:
- Consent is required for every data-processing purpose (`domains/consent/`)
- 11 enumerated purposes (e.g. `identity_verification`, `disease_diagnosis`, `ndvi_monitoring`)
- Consent is **per-purpose** (granular) — user can grant disease diagnosis without granting NDVI monitoring
- The consent banner (`components/consent/consent-banner.tsx`) is shown on first dashboard visit
- No pre-ticked checkboxes — explicit opt-in only

### Section 5 — Notice

> Before processing personal data, the Data Fiduciary shall give a clear, plain-language notice.

**Implementation**:
- `ConsentNotice` model (`privacy.consent_notices`) stores versioned notice text
- Each notice has a `version`, `summary`, `full_text`, `text_hash`, `effective_from`
- The consent banner shows the summary with a link to the full notice
- The `notice_version` is recorded on every consent grant — we can reproduce the exact notice shown to any user at any time (DPDP audit requirement)

### Section 6 — Consent

> Consent must be free, specific, informed, unambiguous, and revocable.

**Implementation**:
- **Free**: no consequence for declining optional consent (required consent is for identity verification only)
- **Specific**: per-purpose, not bundled
- **Informed**: summary + full text + version shown before grant
- **Unambiguous**: explicit click on "Accept selected" — no implicit consent
- **Revocable**: user can withdraw any consent at any time via `/dashboard/privacy` or `/api/v1/consent/withdraw`
- Withdrawal is **as easy as granting** — same UI, same number of clicks (DPDP requirement)

### Section 7 — Verifiable Consent

> Consent of a parent or lawful guardian is required for processing personal data of a child (under 18).

**Implementation**:
- KrishiSetu is **not designed for users under 18**. The signup flow requires Aadhaar e-KYC, which fails for minors (UIDAI doesn't issue Aadhaar to minors without parent linking).
- If a minor attempts to register, the OTP-based auth fails at the UIDAI verification step.
- **Future**: explicit date-of-birth check at signup, with self-declaration of adulthood.

### Section 8 — Obligations of Data Fiduciary

> (1) Process data only for the purpose consented to.
> (2) Ensure accuracy and quality.
> (3) Not retain data beyond the necessary period.
> (4) Implement reasonable security safeguards.
> (5) Personal data breach notification.
> (6) [Breach notification to DPB and affected users.]

**Implementation**:
- **(1) Purpose limitation**: `has_active_consent()` check in services before processing — e.g. NDVI service refuses to fetch imagery if `ndvi_monitoring` consent is withdrawn
- **(2) Accuracy**: DSR correction workflow allows users to fix inaccurate data (`privacy/dsr` with `request_type=correction`)
- **(3) Retention**: `DPDP_DATA_RETENTION_DAYS=2555` (7 years, the maximum period for tax/insurance compliance); inactive accounts are anonymized after this period (future: Celery beat job)
- **(4) Security**: see `docs/security/SECURITY.md` — AES-256-GCM, audit logs, RBAC, etc.
- **(5) Breach logging**: every security event (CSRF violation, rate limit, suspicious input) is written to `audit.audit_logs`
- **(6) Breach notification**: documented in `SECURITY.md` Section 13.3 — 72-hour DPB notification, user notification in the form specified by the Board

### Section 11 — Right to Access

> The data principal has the right to obtain a summary of personal data processed and the processing activities.

**Implementation**:
- `POST /api/v1/privacy/dsr` with `request_type=access`
- SLA: 30 days (DPDP maximum)
- Auto-acknowledged within 24 hours (system-set `acknowledged_at`)
- Response includes:
  - Personal data summary (profile, plots, disease reports, policies, orders)
  - Processing purposes consented to
  - Third parties with whom data was shared (UIDAI, IMD, OWM, Razorpay, MSG91)
  - Retention period for each category

### Section 12 — Right to Correction and Erasure

> The data principal has the right to correction, completion, updating, and erasure of personal data.

**Implementation**:
- **Correction**: `POST /api/v1/privacy/dsr` with `request_type=correction` and `requested_changes={field: new_value}`. SLA: 15 days.
- **Erasure**: `POST /api/v1/privacy/erasure/confirm` with `confirm_phrase="DELETE MY ACCOUNT"`. This triggers:
  - Hard DELETE of `identity.users` row (cascades to plots, disease reports, etc.)
  - Anonymization of payment records (PII columns nulled; amounts/dates retained for tax compliance)
  - Anonymization of audit logs (actor_id nulled; action/outcome retained for security monitoring)
  - Anonymization of consent records (user_id nulled; aggregate counts retained for compliance reporting)
- **Exceptions** (per Section 12(2), we may refuse erasure if necessary for):
  - Compliance with law (tax records: 7 years per Income Tax Act)
  - Compliance with court order
  - Establishment of legal claim (insurance contracts: policy term + 3 years)
  - Performance of a public function

### Section 13 — Right of Grievance Redressal

> The data principal has the right to file a grievance with the Data Fiduciary, who must acknowledge and respond within the prescribed period.

**Implementation**:
- `POST /api/v1/privacy/grievances` with category, subject, description
- Categories: `unauthorized_access`, `consent_violation`, `data_quality`, `excessive_collection`, `retention_violation`, `other`
- Auto-acknowledged within 24 hours (DPDP requirement)
- SLA: 30 days (DPDP maximum)
- Grievance number format: `GRV-YYYYMMDD-XXXXXXXX` (e.g. `GRV-20260724-A1B2C3D4`)
- Officer endpoint: `GET/PATCH /api/v1/privacy/officer/grievances/{id}` (admin or agri_officer role)
- If unresolved within 30 days, the user can escalate to the **Data Protection Board of India** — escalation reference number is recorded

### Section 14 — Right to Nominate

> The data principal has the right to nominate any other individual to exercise their rights in the event of death or incapacity.

**Implementation**: **Future enhancement** — not yet implemented. Will be added before public launch. The schema includes a `nominee_id` column placeholder in `identity.users` (to be added in a future migration).

### Section 17 — Exemptions

> Processing of personal data is exempt from certain provisions for specified purposes (e.g. for legal proceedings, research, archival purposes).

**Implementation**:
- **Research**: only with explicit `research_anonymized` consent; data is aggregated and de-identified before analysis
- **Legal compliance**: payment records retained for 7 years (Income Tax Act); insurance records retained per IRDAI regulations
- We do NOT claim any exemption for law enforcement without a valid court order

---

## 3. Data Subject Rights (DSR) Workflow

```
User files DSR via /dashboard/privacy
       ↓
POST /api/v1/privacy/dsr
       ↓
DSR record created in privacy.data_subject_requests
  - status = acknowledged (auto-acked within 24h SLA)
  - due_at = now + SLA (15 or 30 days depending on type)
       ↓
Officer reviews at /api/v1/privacy/officer/dsr
       ↓
For access/portability:
  - Officer generates data export (JSON or CSV)
  - Uploads to S3 with pre-signed URL (7-day expiry)
  - PATCH /api/v1/privacy/officer/dsr/{id} with status=completed, export_url=...
  - User downloads from /dashboard/privacy
       ↓
For correction:
  - Officer reviews requested_changes
  - Either applies the correction (status=completed) or rejects (status=rejected with reason)
       ↓
For erasure:
  - User must confirm with phrase "DELETE MY ACCOUNT" via /privacy/erasure/confirm
  - System executes execute_erasure() (hard delete + anonymize)
  - User is immediately logged out
       ↓
Audit log entries written at every step (DSR_*_REQUESTED, DSR_*_FULFILLED, DSR_*_APPLIED)
```

---

## 4. Consent Lifecycle

```
First dashboard visit
       ↓
ConsentBanner shows ungranted purposes
       ↓
User selects purposes + clicks "Accept selected"
       ↓
POST /api/v1/consent/grant
       ↓
For each purpose:
  1. Withdraw any existing active grant (status=withdrawn, reason="superseded")
  2. Create new grant (status=granted, notice_version, notice_text_hash)
  3. Write audit log (CONSENT_GRANTED)
       ↓
User can later withdraw via /dashboard/privacy
       ↓
POST /api/v1/consent/withdraw
       ↓
Mark active grant as withdrawn
  - status = withdrawn
  - withdrawn_at, withdrawn_by, withdrawal_reason
  - Write audit log (CONSENT_WITHDRAWN)
       ↓
Services check has_active_consent() before processing
  - If withdrawn: service refuses with clear error
  - User is prompted to re-grant consent to use the feature
```

---

## 5. Data Retention Schedule

| Data Category | Retention Period | Legal Basis | Disposal Method |
|--------------|-----------------|-------------|-----------------|
| User identity (identity.users) | Active + 7 years inactive | DPDP + IT Act | Hard delete on erasure request; anonymize on retention expiry |
| Aadhaar hash | Same as user | DPDP | Hard delete with user |
| Bank account (encrypted) | Active + 7 years | Income Tax Act | Anonymize (set to NULL) on erasure; hard delete on retention expiry |
| Plot data | Same as user | DPDP | Hard delete with user |
| Disease reports + photos | 3 years | Disease surveillance | Hard delete after 3 years (anonymize for research if consented) |
| Insurance policies | Policy term + 3 years | IRDAI regulations | Hard delete after retention |
| Payment records | 7 years | Income Tax Act + GST | Anonymize (PII scrubbed) on erasure; hard delete after 7 years |
| Audit logs | 7 years | DPDP Section 8(5) | Anonymize (actor_id scrubbed) on erasure; hard delete after 7 years |
| Consent records | 7 years | DPDP audit requirement | Anonymize on erasure; hard delete after 7 years |
| Voice queries | 30 days | Service improvement | Hard delete after 30 days (transcript retained for ML improvement only with consent) |
| Server logs (structlog) | 90 days | Operational | Auto-rotate |

---

## 6. Third-Party Data Processors

KrishiSetu shares personal data with the following processors under DPDP-compliant data processing agreements:

| Processor | Data Shared | Purpose | Agreement |
|-----------|------------|---------|-----------|
| **UIDAI** | Aadhaar number (during e-KYC only) | Identity verification | UIDAI Authentication API Terms |
| **MSG91** | Phone number, OTP | SMS delivery | MSG91 DPA |
| **Razorpay** | Order amount, contact (for refund) | Payment processing | Razorpay DPA |
| **IMD** | District name | Weather data | IMD API Terms |
| **OpenWeatherMap** | Latitude/longitude (plot) | Weather forecast | OWM Terms |
| **Sentinel Hub** | Plot polygon (GeoJSON) | NDVI satellite imagery | Sentinel Hub Terms |
| **ISRIC SoilGrids** | Latitude/longitude | Soil composition | ISRIC Terms |
| **AWS** | All data (encrypted at rest) | Hosting | AWS DPA (DPDP-compliant) |

**Cross-border transfer**: All data is stored in **ap-south-1 (Mumbai)** — no cross-border transfer except for Razorpay (which may process in their Singapore region for routing; DPA ensures DPDP-compliant handling).

---

## 7. Grievance Officer

Per DPDP Section 8(9), we have appointed a Grievance Officer:

- **Name**: [To be appointed before public launch]
- **Email**: grievance@krishisetu.in (configured via `DPDP_GRIEVANCE_OFFICER_EMAIL`)
- **Phone**: [To be published]
- **Address**: [To be published]
- **Response SLA**: Acknowledge within 24 hours, resolve within 30 days (DPDP Section 13(3))

The Grievance Officer is responsible for:
- Acknowledging and resolving grievances filed via `/api/v1/privacy/grievances`
- Coordinating with the security team for breach notification
- Filing annual compliance reports
- Liaising with the Data Protection Board of India if escalations occur

---

## 8. Compliance Monitoring

### 8.1 Audit trail
Every consent grant, withdrawal, DSR, grievance, and PII access is written to `audit.audit_logs` with full context (who, what, when, where, why). See `docs/security/SECURITY.md` Section 11 for details.

### 8.2 Periodic reviews
- **Quarterly**: review access logs for unauthorized PII access
- **Annually**: full DPDP compliance audit (internal or third-party)
- **On-demand**: Data Protection Board may request audit reports

### 8.3 Metrics tracked
- Time-to-acknowledge grievances (target: < 24h)
- Time-to-resolve grievances (target: < 30d)
- Time-to-fulfill DSRs (target: < 30d for access, < 15d for correction)
- Number of consent withdrawals per month (high rate may indicate trust issue)
- Number of data breaches (target: 0)

---

## 9. User-Facing Documentation

- **Privacy Notice**: published at `/privacy-notice` (Next.js page, 10 languages)
- **Consent Banner**: shown on first dashboard visit, with summary + link to full notice
- **Privacy Center**: at `/dashboard/privacy`, contains:
  - Consent management (toggle per purpose)
  - DSR filing (access, correction, portability, restriction)
  - Account erasure (with confirmation phrase)
  - Grievance filing (with category selector)
  - List of past DSRs and grievances with status badges
- **Grievance Officer contact**: displayed in privacy center footer

---

## 10. Known Gaps and Roadmap

| Gap | Severity | Target Phase |
|-----|----------|--------------|
| Section 14 (Right to Nominate) not implemented | Medium | Phase G |
| Per-record salts for Aadhaar hashing (currently app-level salt) | Low | Phase G |
| Quarterly internal audit not yet scheduled | Medium | Before public launch |
| Data Protection Officer not appointed (only required if SDF) | N/A | Triggered at SDF threshold |
| Cross-border data transfer assessment for Razorpay | Low | Phase G |
| Automated retention enforcement (Celery beat job) | Medium | Phase G |
| Privacy Notice in 10 languages (currently English only) | High | Phase G |

---

## 11. References

- DPDP Act 2023 (full text): https://meity.gov.in/data-protection-framework
- DPDP Rules (draft): https://meity.gov.in/draft-dpdp-rules
- Data Protection Board of India: https://www.dpbi.gov.in/ (to be operationalized)
- MeitY FAQ: https://www.meity.gov.in/data-protection-framework/faqs
