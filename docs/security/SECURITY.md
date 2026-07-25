# KrishiSetu Security Architecture

**Status**: Production-ready (Phase F complete)
**Last reviewed**: 2026-07-24
**Owner**: Security team / Grievance Officer
**Threat model**: Adversary with network access, no insider access, targets PII of Indian farmers (Aadhaar, bank accounts, plot locations)

---

## 1. Executive Summary

KrishiSetu processes sensitive personal data of Indian farmers — Aadhaar numbers (during e-KYC), bank account details (for insurance payouts), plot geolocations, and crop disease photos. A breach would expose farmers to identity theft, financial fraud, and targeted disinformation.

Phase F implements **defense-in-depth** with five independent layers:

1. **Transport** — TLS 1.2+ with HSTS preload (no plaintext fallback)
2. **Edge** — nginx with strict CSP, rate limiting, bot mitigation
3. **Application** — FastAPI middleware chain (security headers, request size limit, SQLi heuristic, CSRF, CORS)
4. **Data** — AES-256-GCM field-level encryption, bcrypt password hashing, SHA-256 Aadhaar hashing, Postgres RLS
5. **Audit** — append-only audit trail of every PII access, consent grant, payment, and admin action

This document maps each layer to the **OWASP Top 10 (2021)** and the **DPDP Act 2023**.

---

## 2. OWASP Top 10 (2021) — Coverage Map

| # | OWASP Risk | KrishiSetu Mitigation | Verification |
|---|-----------|----------------------|--------------|
| A01 | Broken Access Control | RBAC with 5 roles, 30+ permissions; per-row scoping in service layer; `require_permissions()` dependency on every state-changing endpoint | `tests/integration/test_auth.py`, `tests/unit/test_security.py` |
| A02 | Cryptographic Failures | AES-256-GCM field-level encryption (`core/encryption.py`); bcrypt (12 rounds) for passwords; SHA-256 + salt for Aadhaar; TLS 1.2+ in transit | `tests/unit/test_encryption.py` |
| A03 | Injection | SQLAlchemy ORM/Core (parameterized queries) everywhere; input sanitizer (`core/input_sanitizer.py`); SQLi heuristic middleware logs suspicious input | `tests/unit/test_input_sanitizer.py` |
| A04 | Insecure Design | Threat-modeled at architecture time; security review required for every new endpoint; ADR-0001 mandates FastAPI + Postgres + JWT | `docs/architecture/` |
| A05 | Security Misconfiguration | Single source of truth (`core/config.py`); production disables `/docs`, `/redoc`, `/openapi.json`; env vars validated at startup | `tests/unit/test_config.py` |
| A06 | Vulnerable Components | `bandit` + `pip-audit` + `npm audit` + Trivy in CI; dependabot enabled; pinned versions in `pyproject.toml` | `.github/workflows/security-scan.yml` |
| A07 | Identification & Auth Failures | OTP-based auth with rate limiting (5/min on `/auth/verify-otp`); account lockout after 5 failed attempts; refresh token rotation; JWT secret ≥ 32 chars | `core/security.py`, `core/rate_limiter.py` |
| A08 | Software & Data Integrity Failures | Pinned dependencies; pre-signed S3 URLs (no unsigned uploads); Razorpay webhook HMAC verification | `integrations/razorpay.py`, `core/storage.py` |
| A09 | Security Logging & Monitoring | Structured audit log (`audit.audit_logs`, append-only); 60+ audited action types; CSP violation reporting endpoint; SQLi/CSRF violation counters in Redis | `core/audit_logger.py`, `domains/audit/routes.py` |
| A10 | Server-Side Request Forgery | No server-side fetch of user-supplied URLs; integration clients (IMD, OWM, Sentinel Hub, UIDAI) use fixed base URLs with circuit breakers | `integrations/*.py` |

---

## 3. Security Middleware Chain

The middleware order in `krishisetu/main.py` (outermost first on the request path):

```
Client request
  ↓
[1] RequestIDMiddleware           — assign request_id for tracing
[2] SecurityHeadersMiddleware     — add CSP, HSTS, X-Frame-Options, etc.
[3] RequestSizeLimitMiddleware    — reject bodies > MAX_REQUEST_BODY_BYTES (15 MB)
[4] SQLInjectionGuardMiddleware   — log suspicious patterns (does NOT block)
[5] ExceptionHandlerMiddleware    — convert unhandled exceptions to clean 500s
[6] LoggingMiddleware             — log every request with duration + status
[7] CSRFMiddleware                — enforce double-submit cookie on unsafe methods
[8] CORSMiddleware                — handle CORS preflight
  ↓
Route handler
```

**Why this order:**
- `SecurityHeaders` runs early so headers are applied even to error responses.
- `RequestSizeLimit` runs before any expensive processing to prevent memory exhaustion.
- `SQLInjectionGuard` is non-blocking; it logs for monitoring but doesn't reject (parameterized queries make injection impossible).
- `CSRF` runs late because it only matters for cookie-authenticated requests; Bearer-only requests are exempt.
- `CORS` is innermost so it can short-circuit preflight requests before they reach the application.

---

## 4. Authentication & Authorization

### 4.1 Authentication
- **OTP-based** (primary): 6-digit OTP sent via MSG91 SMS, verified within 5 minutes
- **Password-based** (secondary): bcrypt (12 rounds), 8+ char minimum, optional
- **JWT**: HS256, 30-min access tokens, 30-day refresh tokens with rotation
- **Account lockout**: 5 failed OTP/password attempts → 15-min lockout

### 4.2 Authorization (RBAC)

Five roles with explicit permission sets (defined in `domains/identity/permissions.py`):

| Role | Scope | Key Permissions |
|------|-------|-----------------|
| `farmer` | Own data only | plot:create, disease:report:submit, insurance:apply, marketplace:order, consent:manage:own |
| `agri_officer` | District | plot:read:district, plot:verify, disease:report:review, scheme:application:review, privacy:dsr:review |
| `supplier` | Own catalog | supplier:catalog:manage, supplier:order:fulfill |
| `insurer` | Insured plots | insurance:claim:review, ndvi:read:own |
| `admin` | All | user:read:all, user:update:role, audit:read, content:moderate |

Permissions are version-controlled in code (not DB) so every change is a Git commit with reviewer sign-off.

### 4.3 PII access auditing

Every read of an encrypted field (Aadhaar hash, bank account, GSTIN) writes to `audit.audit_logs` via `audit_log_pii_access()`. The audit entry records:
- **Who**: actor_id, actor_role
- **What**: action (e.g. `pii.accessed`), outcome
- **Which record**: resource_type, resource_id
- **Why**: purpose (e.g. `claim_review`, `kyc_verification`)
- **When**: timestamp (UTC)
- **Where**: IP, User-Agent, request_id

The audit table is **append-only** — DB grants deny UPDATE and DELETE to the application user (only INSERT and SELECT).

---

## 5. Encryption

### 5.1 At rest
- **Database**: PostgreSQL 16 with EBS volume encryption (in production)
- **Field-level**: AES-256-GCM via `core/encryption.py` for bank accounts, GSTIN, Aadhaar references in audit logs
- **Backups**: S3 server-side encryption (SSE-S3 or SSE-KMS)
- **S3 / MinIO**: server-side encryption enabled

### 5.2 In transit
- **Client → edge**: TLS 1.2+ with HSTS (2-year, includeSubDomains, preload-ready)
- **Edge → API**: TLS within VPC (mTLS available)
- **API → Postgres**: TLS via asyncpg `sslmode=verify-full`
- **API → Redis**: TLS via `rediss://` URL
- **API → external APIs** (IMD, OWM, UIDAI, Razorpay): HTTPS only; circuit breaker trips on TLS errors

### 5.3 Key management
- **JWT_SECRET**: 32+ random bytes, stored in AWS Secrets Manager (prod) or `.env` (dev)
- **ENCRYPTION_KEY**: 32 random bytes, base64-encoded, rotated annually
- **Key rotation**: `ENCRYPTION_KEY_PREVIOUS` env var allows old ciphertexts to decrypt with previous keys; new writes always use the primary key
- **CSRF_SECRET**: 32+ random bytes, separate from JWT_SECRET

### 5.4 Hashing (one-way)
- **Passwords**: bcrypt (12 rounds)
- **Aadhaar**: SHA-256 with application-level salt (per-record salt planned for future)
- **Refresh token jti**: SHA-256 of the random jti string

---

## 6. Input Validation & Output Encoding

### 6.1 Input
- **Pydantic v2** validates every request body — type coercion fails loudly
- **Custom sanitizers** (`core/input_sanitizer.py`):
  - `sanitize_free_text()` — Unicode NFC, control-char strip, blocks `<script>`, `javascript:`, `on*=`
  - `sanitize_name()` — letters + spaces + hyphens + apostrophes only
  - `sanitize_filename()` — strips path traversal, replaces unsafe chars, enforces 255-char limit
  - `sanitize_sql_like()` — escapes `%` and `_` for LIKE patterns
  - `detect_sql_injection_attempt()` — heuristic pattern matching for monitoring

### 6.2 File uploads
- Per-context rules in `core/file_upload_security.py`:
  - Disease images: JPG/PNG/WebP, max 10 MB, magic-byte verified, EXIF stripped
  - Voice audio: WAV/MP3/M4A/OGG, max 5 MB, magic-byte verified
  - KYC documents: PDF/JPG/PNG, max 5 MB
- Magic-byte verification prevents `image.exe` renamed to `image.jpg`
- EXIF stripping on all images prevents GPS leakage from farmer photos
- Optional ClamAV scan via `AV_SCAN_URL` for production

### 6.3 Output
- All API responses are JSON — no HTML surface for XSS
- FastAPI's default JSON serializer escapes `<`, `>`, `&` to prevent XSS in JSON rendered as HTML
- Next.js auto-escapes all string interpolation in JSX

---

## 7. CSRF Protection

KrishiSetu uses **JWT Bearer tokens** for API auth, which are not vulnerable to classical CSRF. However, the **refresh-token cookie** is a cookie, so cookie-based requests need CSRF protection.

**Mechanism**: Double-submit cookie with HMAC signature.

1. Client requests `GET /api/v1/auth/csrf-token` (or it's set on first authenticated response)
2. Server sets two cookies:
   - `__Host-csrf` — 32-byte random token (URL-safe base64)
   - `__Host-csrf_sign` — HMAC-SHA256(token, CSRF_SECRET)
3. Client reads `__Host-csrf` via JavaScript and sends it as `X-CSRF-Token` header on every state-changing request
4. Server middleware (`CSRFMiddleware`) verifies:
   - Header == cookie
   - Cookie signature is valid HMAC
5. Mismatch → 403 with `CSRF_INVALID` error code

**Cookie attributes**:
- `__Host-` prefix — Secure, Path=/, no Domain (HTTPS only, apex domain only)
- `SameSite=Strict` — never sent on cross-site requests
- `Secure` — HTTPS only (in production)
- `HttpOnly=false` for `__Host-csrf` (JS must read it)
- `HttpOnly=true` for `__Host-csrf_sign` (server-only)

**Exemptions**:
- GET/HEAD/OPTIONS (safe methods)
- Bearer-only requests (no cookies → not vulnerable)
- Webhook endpoints (Razorpay uses HMAC signature verification instead)
- Public endpoints (health, CSP report)

---

## 8. Security Headers

Applied by `SecurityHeadersMiddleware` on every response, and reinforced by nginx at the edge:

| Header | Value | Purpose |
|--------|-------|---------|
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; ...` | Mitigates XSS, clickjacking, data injection |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | Forces HTTPS for 2 years |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-type confusion |
| `X-Frame-Options` | `DENY` | Clickjacking defense (legacy) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limits referrer leakage |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), ...` | Disables sensitive client APIs |
| `Cross-Origin-Opener-Policy` | `same-origin` | Browsing-context isolation |
| `Cross-Origin-Resource-Policy` | `same-origin` | Restricts resource embedding |
| `Cross-Origin-Embedder-Policy` | `require-corp` | Cross-origin isolation |
| `X-DNS-Prefetch-Control` | `off` | Disables DNS prefetch (anti-rebinding) |
| `Cache-Control` (sensitive paths) | `no-store, no-cache, must-revalidate` | Prevents PII caching in proxies |
| `Server` | `krishisetu` (scrubbed) | Hides underlying tech stack |

CSP violations are reported to `POST /api/v1/security/csp-report` and logged for monitoring.

---

## 9. Rate Limiting & Circuit Breakers

### 9.1 Rate limiting
- **Default**: 100 requests/minute per IP
- **Auth endpoints** (`/auth/verify-otp`, `/auth/login`): 5/minute per IP
- **ML endpoints** (`/disease-reports`, `/voice`): 20/minute per user
- Implementation: Redis sliding-window counter in `core/rate_limiter.py`
- On limit: HTTP 429 with `Retry-After` header

### 9.2 Circuit breakers
Every external API integration (IMD, OWM, Sentinel Hub, UIDAI, Razorpay) wraps calls in a circuit breaker:
- **Closed** (normal): requests go through
- **Open** (failure rate > 50% in 60s window): requests fail-fast with `SERVICE_UNAVAILABLE`
- **Half-open** (after 30s cooldown): one probe request; if successful, close

Prevents cascading failures when external services degrade.

---

## 10. File Upload Security

Multi-layer validation in `core/file_upload_security.py`:

1. **Extension allowlist** — per-context (disease image, voice, KYC, product, insurance, scheme)
2. **Magic byte verification** — actual file signature must match extension (defeats `image.exe` tricks)
3. **Size limit** — per-context (5–10 MB)
4. **Filename sanitization** — strips path traversal, replaces unsafe chars, enforces 255-char limit
5. **Image dimension sanity** — rejects images larger than 8000x8000 (DoS)
6. **EXIF stripping** — for all images, removes GPS coordinates and camera serial numbers
7. **Antivirus scan** (optional) — async ClamAV scan via `AV_SCAN_URL` for production

---

## 11. Audit Trail

### 11.1 What's audited
60+ action types across 9 categories (see `core/audit_logger.py:AuditAction`):
- Authentication (login success/failure, logout, OTP, account lockout)
- Authorization (permission denied, role change)
- PII access & modification
- Consent (grant, withdraw)
- Data Subject Rights (access, correction, erasure, portability, grievance)
- Farmer domain (plot CRUD, verification)
- Disease domain (report submit, review)
- Insurance domain (policy purchase, claim file/approve/reject)
- Marketplace & payments (order create/cancel, payment capture/refund, escrow release)
- Admin actions (user deactivate, content moderation, scheme approval)
- Security events (CSRF violation, rate limit exceeded, suspicious input, integration failure)

### 11.2 Audit log guarantees
- **Append-only**: DB grants deny UPDATE/DELETE to the application user
- **Structured**: JSONB `details` column for context (never contains raw PII — only field names)
- **Tamper-evident**: every entry has a UUID, timestamp, actor_id, request_id (correlates with application logs)
- **Searchable**: indexed on actor_id, action, resource_type, occurred_at
- **Retained**: 7 years (DPDP + tax compliance)

### 11.3 Query API
Admin-only (`admin:audit:read` permission):
- `GET /api/v1/audit/logs` — search with filters (actor, action, resource, date range)
- `GET /api/v1/audit/logs/{id}` — single log entry
- `GET /api/v1/audit/stats?hours=24` — aggregate stats for security monitoring

---

## 12. Secrets Management

### 12.1 Local development
- `.env` file in `apps/api/` (gitignored)
- `.env.example` documents required variables
- Never commit secrets — pre-commit hook scans for high-entropy strings

### 12.2 Production
- **AWS Secrets Manager** for all secrets (JWT_SECRET, ENCRYPTION_KEY, CSRF_SECRET, DB password, API keys)
- **IAM role** on the EC2/ECS task grants read access to specific secrets
- **Rotation**: JWT_SECRET every 90 days, ENCRYPTION_KEY annually (with `ENCRYPTION_KEY_PREVIOUS` for backward decryption)
- **Audit**: every secret access logged in CloudTrail

---

## 13. Incident Response

### 13.1 Detection
- **Real-time**: structured logs shipped to CloudWatch + OpenTelemetry traces
- **Alerts**:
  - Spike in `login.failed` events (>50 in 5 min) → Slack #security-alerts
  - Any `dsr.erasure.applied` → email to Grievance Officer
  - Any `security.csrf.violation` or `security.rate_limit.exceeded` spike → PagerDuty
  - CSP violation reports → aggregated hourly summary

### 13.2 Response
1. **Identify**: use `request_id` to correlate audit logs, application logs, and traces
2. **Contain**: rotate affected credentials (JWT_SECRET, ENCRYPTION_KEY) via Secrets Manager
3. **Eradicate**: deploy fix; revoke active sessions via `auth/logout-all`
4. **Recover**: restore from backup if data was corrupted
5. **Report**: file a grievance entry (yes, against ourselves) for tracking
6. **Postmortem**: blameless RCA within 7 days, published to `docs/security/incidents/`

### 13.3 DPDP breach notification
Per DPDP Section 8(6), if a breach is likely to result in significant harm to data principals:
- Notify the **Data Protection Board of India** within 72 hours
- Notify **affected users** "in such form and manner as may be specified"
- Document the breach, its effects, and remediation in `docs/security/incidents/`

---

## 14. Security Hardening Checklist (Phase F)

- [x] Content-Security-Policy with report-only mode supported
- [x] HSTS with preload-ready directives
- [x] All OWASP-recommended security headers
- [x] Field-level AES-256-GCM encryption for PII
- [x] Key rotation support (primary + previous keys)
- [x] Input sanitization (free text, names, filenames, SQL LIKE, URLs)
- [x] File upload security (magic bytes, size, EXIF stripping, AV hook)
- [x] CSRF protection (double-submit cookie with HMAC signature)
- [x] Request body size limit (15 MB default)
- [x] SQL injection heuristic monitoring (non-blocking)
- [x] Audit log (append-only, 60+ action types, structured)
- [x] Consent management (DPDP Section 4-7)
- [x] Data Subject Rights (DPDP Section 11-12)
- [x] Grievance redressal (DPDP Section 13)
- [x] Account erasure with PII anonymization (DPDP-compliant)
- [x] RBAC with 30+ permissions across 5 roles
- [x] Rate limiting (default + auth + ML tiers)
- [x] Circuit breakers on all external API calls
- [x] Bandit + pip-audit + npm audit + Trivy in CI
- [x] OWASP ZAP baseline scan in CI (PR-triggered)
- [x] nginx security headers config for production edge

---

## 15. Future Enhancements (Phase G+)

- **Per-record salts** for Aadhaar hashing (currently uses app-level salt)
- **WebAuthn** for passwordless auth (yubikey / platform authenticators)
- **CSP nonces** instead of `unsafe-inline` for Next.js styles
- **TruffleHog** in CI to scan for committed secrets
- **Snyk** for continuous dependency monitoring
- **Penetration test** by external firm before public launch (see `docs/security/PENETRATION_TEST.md`)
- **Bug bounty** program on HackerOne / Intigriti
- **DPDP Section 14** — Right to nominate (allow user to nominate someone to exercise rights on their behalf)
- **Data residency** — pin all data to ap-south-1 (Mumbai) region

---

## 16. References

- OWASP Top 10 (2021): https://owasp.org/Top10/
- OWASP Secure Headers Project: https://owasp.org/www-project-secure-headers/
- DPDP Act 2023 (full text): https://meity.gov.in/data-protection-framework
- Mozilla Observatory: https://observatory.mozilla.org/
- hstspreload.org: https://hstspreload.org/
- NIST SP 800-38D (GCM): https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf
