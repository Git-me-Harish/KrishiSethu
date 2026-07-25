# KrishiSetu Penetration Test Plan

**Status**: Pre-launch plan
**Last updated**: 2026-07-24
**Test window**: 2 weeks before public launch (target: TBD)
**Testing firm**: [To be selected — shortlist includes ThreatFactor, Lucideus, ISOEH]
**Bug bounty**: HackerOne / Intigriti program to launch 1 week after pentest

---

## 1. Objectives

1. **Identify exploitable vulnerabilities** before public launch, with priority on:
   - PII exposure (Aadhaar, bank account, plot location, photos)
   - Authentication/authorization bypass
   - Payment fraud (escrow tampering, refund abuse)
   - DPDP non-compliance (consent bypass, erasure failure)
2. **Verify the effectiveness** of Phase F security controls (encryption, CSRF, audit, RBAC)
3. **Establish a security baseline** for ongoing bug bounty comparison
4. **Satisfy regulatory expectations** (DPDP Section 8(4) requires reasonable security safeguards)

---

## 2. Scope

### 2.1 In-scope targets

| Target | URL | Notes |
|--------|-----|-------|
| API (production staging) | https://staging-api.krishisetu.in | All `/api/v1/*` endpoints |
| Web frontend | https://staging.krishisetu.in | Next.js 14 app |
| WebSocket (future) | wss://staging-api.krishisetu.in/ws | When implemented |
| Mobile (future) | N/A | Out of scope for v1 |

### 2.2 Out-of-scope
- Production environment (`api.krishisetu.in`) — staging only
- Third-party services (Razorpay, UIDAI, IMD) — test against their sandboxes
- DoS / DDoS (we have Cloudflare; volumetric testing requires coordination)
- Social engineering of KrishiSetu staff
- Physical security

### 2.3 Test accounts provided
The testing firm will receive:
- 1× admin account
- 2× agri_officer accounts (different districts)
- 3× farmer accounts (with plots, disease reports, policies)
- 2× supplier accounts (with products, orders)
- 1× insurer account
- Staging API tokens for each role

---

## 3. Test Methodology

Aligned with **OWASP Web Security Testing Guide (WSTG) v4.2** and **PTES** (Penetration Testing Execution Standard).

### 3.1 Phases

1. **Reconnaissance** (1 day) — enumerate endpoints from OpenAPI spec, identify tech stack
2. **Authentication testing** (2 days) — OTP bypass, password reset abuse, JWT tampering, session fixation
3. **Authorization testing** (2 days) — IDOR, privilege escalation, RBAC bypass
4. **Input validation** (2 days) — SQLi, XSS, SSRF, command injection, XXE
5. **Business logic** (2 days) — payment tampering, escrow bypass, refund abuse, consent bypass
6. **Crypto review** (1 day) — JWT secret strength, encryption key management, password hashing
7. **Configuration review** (1 day) — security headers, TLS, CORS, cookie flags
8. **API-specific** (1 day) — rate limit bypass, mass assignment, GraphQL introspection (N/A)
9. **DPDP-specific** (1 day) — consent bypass, DSR workflow abuse, erasure incompleteness
10. **Reporting** (2 days) — findings write-up, severity rating, remediation recommendations

### 3.2 Severity rating (CVSS v3.1)

| Severity | CVSS Range | Examples |
|----------|-----------|----------|
| Critical | 9.0–10.0 | Auth bypass, RCE, SQLi extracting PII |
| High | 7.0–8.9 | IDOR exposing other users' PII, payment tampering |
| Medium | 4.0–6.9 | CSRF on state-changing endpoint, missing security headers |
| Low | 0.1–3.9 | Verbose error messages, information disclosure |
| Informational | 0.0 | Best-practice recommendations |

---

## 4. Specific Test Cases

### 4.1 Authentication
- [ ] OTP brute-force (should rate-limit after 5 attempts)
- [ ] OTP replay (same OTP should not work twice)
- [ ] OTP interception (no plaintext OTP in logs/responses)
- [ ] JWT secret brute-force (use `jwt_tool` with rockyou wordlist)
- [ ] JWT algorithm confusion (try `alg: none`, `alg: HS256` vs `RS256`)
- [ ] Refresh token reuse (rotated token should be invalidated)
- [ ] Account lockout bypass (try different IPs / user-agents)
- [ ] Password reset token reuse
- [ ] Session fixation (login should rotate session)

### 4.2 Authorization
- [ ] **IDOR** — access another farmer's plots via `GET /api/v1/plots/{other_user_id}`
- [ ] **Privilege escalation** — farmer tries `POST /api/v1/admin/users` (should 403)
- [ ] **Horizontal escalation** — farmer A tries to read farmer B's disease report
- [ ] **Vertical escalation** — agri_officer tries admin-only endpoints
- [ ] **Officer district bypass** — officer of District X tries to read plots in District Y
- [ ] **Mass assignment** — `PATCH /me` with `{"role": "admin"}` (should be ignored)
- [ ] **Path traversal** — `GET /api/v1/files/../../../etc/passwd`

### 4.3 Input validation
- [ ] SQLi on all `GET /?filter=` parameters
- [ ] SQLi on `q` search parameters (use `sqlmap`)
- [ ] XSS in disease report notes (stored)
- [ ] XSS in grievance description (stored, shown to officer)
- [ ] SSRF in plot polygon URL (if any)
- [ ] Command injection in filename (file upload)
- [ ] XXE in XML body (if any endpoint accepts XML)
- [ ] Path traversal in filename (`../../etc/passwd`)

### 4.4 Business logic
- [ ] **Payment tampering** — modify amount in Razorpay order creation
- [ ] **Escrow bypass** — release escrow without delivery confirmation
- [ ] **Refund abuse** — refund more than original amount
- [ ] **Double-spend** — pay for same order twice (idempotency check)
- [ ] **Consent bypass** — submit disease report with `disease_diagnosis` consent withdrawn (should fail)
- [ ] **Erasure incompleteness** — verify all PII is gone after erasure (check audit logs, consent records)
- [ ] **DSR SLA bypass** — file multiple DSRs to overwhelm the system

### 4.5 Crypto review
- [ ] Verify JWT secret is ≥ 32 chars (impossible to brute-force)
- [ ] Verify refresh token jti is rotated on each refresh
- [ ] Verify AES-256-GCM nonce is never reused (check encrypt_field implementation)
- [ ] Verify bcrypt rounds = 12 (config)
- [ ] Verify Aadhaar hash uses SHA-256 with salt
- [ ] Verify pre-signed S3 URLs have short expiry (≤ 7 days)

### 4.6 Configuration
- [ ] TLS 1.0/1.1 disabled (only 1.2+)
- [ ] HSTS header present with `includeSubDomains; preload`
- [ ] CSP header present and strict
- [ ] X-Frame-Options: DENY
- [ ] X-Content-Type-Options: nosniff
- [ ] CORS allows only `krishisetu.in` (no `*`)
- [ ] Cookies have `Secure`, `HttpOnly`, `SameSite` flags
- [ ] No `Server` header revealing nginx/uvicorn version
- [ ] `/docs`, `/redoc`, `/openapi.json` return 404 in production
- [ ] `.env` file is not web-accessible
- [ ] Debug mode is off in production (`ENV=production`)

### 4.7 Rate limiting
- [ ] `/auth/verify-otp` blocks after 5 attempts/minute
- [ ] `/disease-reports` blocks after 20/minute per user
- [ ] Global limit of 100/minute per IP enforced
- [ ] Rate limit response includes `Retry-After` header

### 4.8 File upload
- [ ] Upload `.exe` renamed to `.jpg` (should fail magic-byte check)
- [ ] Upload 11 MB image (should fail size limit)
- [ ] Upload image with EXIF GPS data (verify EXIF is stripped)
- [ ] Upload SVG with embedded JavaScript (should be rejected — SVG not in allowlist)
- [ ] Upload PDF with malicious JavaScript (should be rejected at parse if any)

### 4.9 DPDP-specific
- [ ] Withdraw consent for `disease_diagnosis` then try to submit a disease report (should fail with 403)
- [ ] File erasure request, verify all data is gone within 30 days (or immediately on confirm)
- [ ] File grievance, verify acknowledgement within 24 hours
- [ ] Verify audit log records every PII access (query audit logs for `pii.accessed`)
- [ ] Verify audit log is append-only (try UPDATE — should be denied at DB level)
- [ ] Verify consent notice version is recorded on each grant
- [ ] Verify a withdrawn consent can be re-granted (idempotent)

---

## 5. Findings Template

Each finding should include:

```markdown
### [Finding ID] — [Title]

**Severity**: Critical | High | Medium | Low | Informational
**CVSS**: [score] ([vector])
**Endpoint**: [HTTP method + URL]
**Test case**: [reference to test case ID above]

**Description**:
[What was found, in plain English]

**Steps to reproduce**:
1. [step 1]
2. [step 2]
3. [step 3]

**Proof of concept**:
[HTTP request/response, screenshot, or code snippet]

**Impact**:
[What an attacker could do with this vulnerability]

**Remediation**:
[Specific code change or configuration update needed]

**References**:
- [OWASP WSTG ID]
- [CWE ID]
```

---

## 6. Rules of Engagement

1. **Test only against staging** — production is off-limits
2. **No destructive testing** — no DELETE requests that destroy data; use POST/PUT for testing
3. **No DoS** — keep request rate under 50/second
4. **No social engineering** — do not target KrishiSetu staff
5. **Report immediately** — Critical findings within 4 hours of discovery
6. **Don't access real user data** — use only the test accounts provided
7. **Coordinate disclosure** — 90-day embargo before public disclosure
8. **Out-of-scope findings** — report but don't exploit (e.g. vulnerabilities in third-party services)

---

## 7. Deliverables

The testing firm will deliver:

1. **Executive summary** (1 page) — overall risk posture, top 3 findings
2. **Detailed findings report** — all findings per template above, grouped by severity
3. **Remediation tracker** — spreadsheet tracking each finding to closure
4. **Re-test report** — after KrishiSetu remediates, the firm re-tests to verify
5. **Methodology appendix** — tools used, test cases executed, coverage matrix

---

## 8. Tooling Expectations

The firm is expected to use (at minimum):
- **Burp Suite Pro** — manual testing, repeater, intruder
- **OWASP ZAP** — automated baseline scan (we already run this in CI)
- **sqlmap** — SQL injection automation
- **JWT Tool** — JWT analysis and brute-force
- **ffuf / gobuster** — endpoint enumeration
- **nuclei** — template-based vulnerability scanner
- **trufflehog** — secret scanning in responses
- **nmap** — service fingerprinting (TLS ciphers, etc.)

---

## 9. Post-Test Activities

1. **Triage** (KrishiSetu, 1 day): classify each finding as Accept / Fix / Mitigate
2. **Remediation** (KrishiSetu, 1-2 weeks): fix Critical/High first, then Medium
3. **Re-test** (firm, 2-3 days): verify fixes
4. **Sign-off**: KrishiSetu + firm sign off on closure
5. **Bug bounty launch**: open HackerOne program with payouts:
   - Critical: ₹1,00,000
   - High: ₹50,000
   - Medium: ₹15,000
   - Low: ₹5,000

---

## 10. Success Criteria

The penetration test is considered **passed** if:
- **0 Critical findings** remain open after remediation
- **0 High findings** related to PII exposure or auth bypass remain open
- **All Medium findings** have a documented remediation plan
- The firm issues a **clean sign-off letter** for re-test

If Critical findings remain, **public launch is blocked** until resolved.

---

## 11. Budget and Timeline

| Item | Cost (₹) | Duration |
|------|---------|----------|
| Pentest (mid-tier Indian firm) | 8,00,000 – 15,00,000 | 2 weeks |
| Re-test | Included or +2,00,000 | 3 days |
| Bug bounty pool (year 1) | 5,00,000 | Ongoing |
| Internal engineering time | (sunk cost) | 2 weeks remediation |
| **Total** | ~₹15-20 lakh | ~6 weeks end-to-end |

---

## 12. References

- OWASP WSTG v4.2: https://owasp.org/www-project-web-security-testing-guide/
- PTES: http://www.pentest-standard.org/
- CVSS v3.1 calculator: https://www.first.org/cvss/calculator/3.1
- Bug bounty program design: https://docs.hackerone.com/programs/
