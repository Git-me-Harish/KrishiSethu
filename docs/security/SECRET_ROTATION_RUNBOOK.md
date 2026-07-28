# Secret Rotation Runbook

> **Audience:** KrishiSetu operators, on-call engineers, and the DPDP Grievance Officer.
> **Trigger:** Suspected leak, routine annual rotation, or offboarding of a team member with production access.
> **Goal:** Rotate every secret in the system in a way that (a) doesn't take the platform down and (b) lets us prove to an auditor that the old secret is dead.

---

## 0. Before you begin

1. **Confirm scope.** Is this a single-key rotation, or a full sweep after a suspected leak? A full sweep is the default unless you can prove only one key was exposed.
2. **Notify.** Email the on-call channel and the DPDP Grievance Officer (`DPDP_GRIEVANCE_OFFICER_EMAIL`) with the start time, expected end time, and which services may blip.
3. **Have backups.** A DB snapshot, a MinIO bucket listing, and the current `.env` file copied to `secrets/.env.pre-rotation-backup.<date>` (which is gitignored — see `.gitignore` line 110).
4. **Open a terminal at the repo root.** All commands below assume `cd krishisetu/`.

---

## 1. Inventory of secrets

The platform depends on the following secrets. Each is listed with its location, scope, and rotation procedure.

| # | Secret | Where it lives | Scope | Rotate procedure |
|---|---|---|---|---|
| 1 | `JWT_SECRET` | `apps/api/.env` (and root `.env` for docker-compose) | API + worker + celery-beat | §2 |
| 2 | `ENCRYPTION_KEY` | `apps/api/.env` | API only (PII field encryption) | §3 |
| 3 | `ENCRYPTION_KEY_PREVIOUS` | `apps/api/.env` | API only (decryption of legacy rows) | §3 |
| 4 | `CSRF_SECRET` | `apps/api/.env` | API only (double-submit cookie signing) | §4 |
| 5 | `POSTGRES_PASSWORD` | root `.env` | Postgres + API + worker + celery-beat | §5 |
| 6 | `MINIO_ROOT_PASSWORD` | root `.env` | MinIO + API + worker + celery-beat | §6 |
| 7 | `GOOGLE_OAUTH_CLIENT_SECRET` | `apps/api/.env` | API only (Google sign-in) | §7 |
| 8 | `OPENWEATHERMAP_API_KEY` | `apps/api/.env` | API only (weather) | §8 |
| 9 | `SENTINEL_HUB_CLIENT_SECRET` | `apps/api/.env` | API only (NDVI) | §9 |
| 10 | `MSG91_AUTH_KEY` | `apps/api/.env` | API only (SMS/OTP) | §10 |
| 11 | `FCM_SERVER_KEY` | `apps/api/.env` | API only (push notifications) | §11 |
| 12 | `UIDAI_API_KEY` | `apps/api/.env` | API only (Aadhaar e-KYC) | §12 |
| 13 | `RAZORPAY_KEY_SECRET` | `apps/api/.env` (env) — currently bypassed by `integrations/razorpay.py`, see T11 fix | API only (payments) | §13 |
| 14 | `RAZORPAY_WEBHOOK_SECRET` | `apps/api/.env` (env) — currently bypassed, see T11 fix | API only (webhook signature verify) | §13 |
| 15 | Firebase service-account JSON | `krishisethu-*-firebase-adminsdk-*.json` (root) | FCM push, Firestore, Cloud Storage, Auth | §14 |

---

## 2. JWT_SECRET

**What it protects:** Every access and refresh token minted by the API. If leaked, an attacker can forge tokens for any user.

**Generate new value:**
```bash
openssl rand -hex 32
```

**Rotate (zero-downtime — but all users will be force-logged-out):**
1. Update `JWT_SECRET` in `apps/api/.env` and root `.env`.
2. Restart API, worker, celery-beat: `docker compose -f infra/docker-compose.yml restart api worker celery-beat`
3. All existing refresh tokens become invalid instantly. Users will be redirected to `/login` on their next request.

**Verify:**
```bash
# Old token must be rejected
curl -H "Authorization: Bearer <old-jwt>" http://localhost:8000/api/v1/auth/me
# Expected: 401 Unauthorized

# Fresh login must work
curl -X POST http://localhost:8000/api/v1/auth/send-otp -d '{"phone":"<test-phone>"}'
# Expected: 200 OK
```

---

## 3. ENCRYPTION_KEY (and ENCRYPTION_KEY_PREVIOUS)

**What it protects:** Field-level encryption of PII at rest — currently wired but used by zero models (see T11). Once `EncryptedString` is applied to `bank_account_number` and `bank_ifsc` in T11, this key protects every farmer's bank details.

**Generate new value:**
```bash
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

**Rotate WITHOUT losing existing encrypted data:**
1. Move the current `ENCRYPTION_KEY` value into `ENCRYPTION_KEY_PREVIOUS` (as a JSON array element):
   ```bash
   # In apps/api/.env
   ENCRYPTION_KEY_PREVIOUS=["<old-base64-key>"]
   ENCRYPTION_KEY=<new-base64-key>
   ```
2. Restart API: `docker compose -f infra/docker-compose.yml restart api`
3. The API will decrypt existing rows using `ENCRYPTION_KEY_PREVIOUS` and encrypt new rows using `ENCRYPTION_KEY`.
4. **Backfill (one-time):** Once all PII rows have been re-written (e.g., after the next time each farmer's profile is updated), the old key is no longer needed. For a forced backfill, run:
   ```bash
   docker compose -f infra/docker-compose.yml exec api python -m krishisetu.scripts.reencrypt_pii
   ```
   (Script does not exist yet — to be added in T11.)
5. After backfill completes and is verified, clear `ENCRYPTION_KEY_PREVIOUS`.

**Verify:**
```bash
# API boots without errors
docker compose -f infra/docker-compose.yml logs api | tail -20
# Existing farmer profiles still display correctly in the web UI
```

---

## 4. CSRF_SECRET

**What it protects:** Double-submit CSRF cookie signing. If leaked, an attacker can forge CSRF tokens and bypass CSRF protection on state-changing endpoints.

**Generate new value:**
```bash
openssl rand -hex 32
```

**Rotate:**
1. Update `CSRF_SECRET` in `apps/api/.env`.
2. Restart API: `docker compose -f infra/docker-compose.yml restart api`
3. All existing CSRF cookies become invalid. Users will see a single failed mutation on their next state-changing request; the next page load issues a fresh cookie.

**Verify:**
```bash
# Hit a state-changing endpoint with an old CSRF cookie — must be rejected
curl -X POST -H "Cookie: csrf_token=<old>" -H "X-CSRF-Token: <old>" \
     http://localhost:8000/api/v1/consent/grant -d '{"purpose":"aadhaar_ekyc"}'
# Expected: 403 Forbidden (CSRF validation failed)
```

---

## 5. POSTGRES_PASSWORD

**What it protects:** Read/write access to every row in the database (farmers, plots, payments, audit logs, etc.).

**Generate new value:**
```bash
openssl rand -hex 16
```

**Rotate (requires brief downtime):**
1. Notify users of a 5-minute maintenance window.
2. Update `POSTGRES_PASSWORD` in root `.env`.
3. Connect to Postgres with the OLD password and change it:
   ```bash
   docker compose -f infra/docker-compose.yml exec postgres psql -U krishisetu -d krishisetu -c \
     "ALTER USER krishisetu WITH PASSWORD '<new-password>';"
   ```
4. Restart API, worker, celery-beat: `docker compose -f infra/docker-compose.yml restart api worker celery-beat`
5. Verify they reconnect successfully.

**Verify:**
```bash
# Old password must be rejected
PGPASSWORD=<old-password> psql -h 127.0.0.1 -U krishisetu -d krishisetu -c "SELECT 1;"
# Expected: password authentication failed

# New password must work
PGPASSWORD=<new-password> psql -h 127.0.0.1 -U krishisetu -d krishisetu -c "SELECT 1;"
# Expected: 1
```

---

## 6. MINIO_ROOT_PASSWORD

**What it protects:** Read/write access to every object in MinIO (disease images, NDVI rasters, ML models).

**Generate new value:**
```bash
openssl rand -hex 16
```

**Rotate:**
1. Update `MINIO_ROOT_PASSWORD` in root `.env`.
2. Change it inside MinIO:
   ```bash
   docker compose -f infra/docker-compose.yml exec minio mc admin user info local krishisetu
   docker compose -f infra/docker-compose.yml exec minio mc admin user reset local krishisetu
   # Then enter the new password interactively, OR use the MinIO console at
   # http://127.0.0.1:9002 with the OLD root credentials.
   ```
3. Restart API, worker, celery-beat: `docker compose -f infra/docker-compose.yml restart api worker celery-beat`

**Verify:**
```bash
# Old credentials must be rejected
AWS_ACCESS_KEY_ID=krishisetu AWS_SECRET_ACCESS_KEY=<old-password> \
  aws --endpoint-url http://127.0.0.1:9000 s3 ls
# Expected: Access Denied

# New credentials must work
AWS_ACCESS_KEY_ID=krishisetu AWS_SECRET_ACCESS_KEY=<new-password> \
  aws --endpoint-url http://127.0.0.1:9000 s3 ls
# Expected: bucket listing
```

---

## 7. GOOGLE_OAUTH_CLIENT_SECRET

**What it protects:** The Google OAuth flow — if leaked, an attacker can impersonate the KrishiSetu app in a Google sign-in flow and intercept authorization codes.

**Rotate (in Google Cloud Console):**
1. Go to https://console.cloud.google.com/apis/credentials
2. Select the KrishiSetu OAuth 2.0 Client ID.
3. Under "Client secret", click "Reset client secret" — Google invalidates the old secret immediately.
4. Copy the new secret into `GOOGLE_OAUTH_CLIENT_SECRET` in `apps/api/.env`.
5. Restart API: `docker compose -f infra/docker-compose.yml restart api`

**Verify:**
- Open an incognito window, go to `http://localhost:3000/login`, click "Continue with Google" — the OAuth flow should complete successfully.
- Old client secret (if you kept a copy for testing) should fail with `invalid_client`.

---

## 8. OPENWEATHERMAP_API_KEY

**Rotate:**
1. Sign in at https://home.openweathermap.org/api_keys
2. Click "Generate new key" — note the new key.
3. Delete the old key (or leave it for 24 hours if you want a soft cutover, then delete).
4. Update `OPENWEATHERMAP_API_KEY` in `apps/api/.env`.
5. Restart API: `docker compose -f infra/docker-compose.yml restart api`

**Verify:**
```bash
curl "https://api.openweathermap.org/data/2.5/weather?q=Mumbai&appid=<new-key>"
# Expected: 200 with weather JSON

curl "https://api.openweathermap.org/data/2.5/weather?q=Mumbai&appid=<old-key>"
# Expected: 401 Invalid API key
```

---

## 9. SENTINEL_HUB_CLIENT_SECRET

**Rotate:**
1. Sign in at https://services.sentinel-hub.com/oauth/login
2. Go to User Settings → OAuth clients → find the KrishiSetu client.
3. Click "Reset secret".
4. Update `SENTINEL_HUB_CLIENT_ID` / `SENTINEL_HUB_CLIENT_SECRET` in `apps/api/.env`.
5. Restart API: `docker compose -f infra/docker-compose.yml restart api`

**Verify:**
```bash
# Hit the NDVI refresh endpoint for a plot — should succeed (200 or 202)
curl -X POST -H "Authorization: Bearer <jwt>" \
     http://localhost:8000/api/v1/plots/<plot-id>/ndvi/refresh
```

---

## 10. MSG91_AUTH_KEY

**Rotate:**
1. Sign in at https://msg91.com
2. Go to API Keys — generate a new key.
3. Revoke the old key.
4. Update `MSG91_AUTH_KEY` in `apps/api/.env`.
5. Restart API: `docker compose -f infra/docker-compose.yml restart api`

**Verify:**
```bash
# Send a test OTP — should succeed
curl -X POST http://localhost:8000/api/v1/auth/send-otp -d '{"phone":"<test-phone>"}'
# Expected: 200, SMS delivered within 30 seconds
```

---

## 11. FCM_SERVER_KEY (legacy) — and/or Firebase service-account

**Note:** FCM server keys are legacy and deprecated by Firebase. The KrishiSetu platform should migrate to the Firebase Admin SDK (which uses the service-account JSON) for sending pushes. Until that migration is done, the FCM server key rotation is:

1. Sign in at https://console.firebase.google.com → KrishiSetu project → Cloud Messaging.
2. Under "Legacy server key", regenerate.
3. Update `FCM_SERVER_KEY` in `apps/api/.env`.
4. Restart API.

**Verify:** Send a test push to a registered device token — should arrive within 10 seconds.

If you've already migrated to the Admin SDK (the JSON file), see §14.

---

## 12. UIDAI_API_KEY

**Rotate:**
1. Contact the UIDAI partner portal administrator (whoever has the original onboarding email).
2. Request a new API key — UIDAI does not have a self-service portal for key rotation; this goes through their partner support.
3. Update `UIDAI_API_KEY` in `apps/api/.env`.
4. Restart API.

**Verify:**
```bash
# Trigger an Aadhaar OTP send — should succeed
curl -X POST -H "Authorization: Bearer <jwt>" \
     http://localhost:8000/api/v1/auth/aadhaar/send-otp \
     -d '{"aadhaar":"<test-aadhaar>"}'
# Expected: 200, UIDAI txn-id returned
```

---

## 13. RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET

**Important:** Currently `integrations/razorpay.py` reads these directly from `os.environ`, bypassing Pydantic Settings — see T11 remediation. Until T11 is complete, the rotation procedure is the same; just remember the env vars must be present in the API container's environment.

**Rotate:**
1. Sign in at https://dashboard.razorpay.com/app/keys
2. Click "Generate Key" — Razorpay shows the secret ONCE. Save it.
3. The old key becomes invalid immediately.
4. Update `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `apps/api/.env`.
5. For the webhook secret: go to https://dashboard.razorpay.com/app/webhooks — edit the KrishiSetu webhook, regenerate the secret, save.
6. Update `RAZORPAY_WEBHOOK_SECRET` in `apps/api/.env`.
7. Restart API: `docker compose -f infra/docker-compose.yml restart api`

**Verify:**
```bash
# Create a test payment order — should succeed
curl -X POST -H "Authorization: Bearer <jwt>" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/payments/orders \
     -d '{"amount":100,"reference_type":"insurance_premium","reference_id":"<policy-id>"}'
# Expected: 201, razorpay_order_id returned

# Send a test webhook with the new secret — should verify
# (Use Razorpay's "Send Test Webhook" button in the dashboard.)
```

---

## 14. Firebase service-account JSON

**What it protects:** Full Firebase Admin SDK access — mint custom Auth tokens, read/write Firestore, read/write Cloud Storage, send FCM pushes, and (depending on IAM bindings) pivot to other GCP resources.

**Rotate:**
1. Go to https://console.firebase.google.com → KrishiSetu project → Project Settings → Service Accounts.
2. Click "Generate new private key" — download the new JSON.
3. **Revoke the old key:** Go to https://console.cloud.google.com/iam-admin/serviceaccounts → select `firebase-adminsdk-fbsvc@krishisethu-8e872.iam.gserviceaccount.com` → KEYS tab → select the old key ID (`2fa055f29d2a3d253bb4de6b640eff2f023d6955`) → DELETE.
4. Replace the local JSON file with the new one.
5. Restart any service that reads the JSON.

**Verify:**
```bash
# Old key must be rejected by Firebase Auth
# (Try to mint a custom token using the old JSON — should fail with permission denied.)

# New key must work
# (Send a test FCM push using the new JSON — should arrive within 10 seconds.)
```

**Audit:** After rotation, audit GCP logs for any use of the old key since the file was created:
1. Go to https://console.cloud.google.com/logs/query
2. Filter: `protoPayload.authenticationInfo.principalEmail="firebase-adminsdk-fbsvc@krishisethu-8e872.iam.gserviceaccount.com"` AND `timestamp>="<file-creation-date>"`
3. Review every entry. If you see calls you didn't make, treat the Firebase project as compromised and rotate ALL service-account keys.

---

## 15. After rotation

1. Update the `secrets/.env.pre-rotation-backup.<date>` file with the new values (this is the new "previous" baseline).
2. Send a follow-up email to the on-call channel and the DPDP Grievance Officer confirming rotation is complete and which services were affected.
3. If the rotation was triggered by a suspected leak: file a DPDP incident report (see `docs/security/DPDP_COMPLIANCE.md` Section 10) within 72 hours.

---

## 16. Quick reference — generate new values

| Secret | Command |
|---|---|
| `JWT_SECRET` | `openssl rand -hex 32` |
| `CSRF_SECRET` | `openssl rand -hex 32` |
| `ENCRYPTION_KEY` | `python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"` |
| `POSTGRES_PASSWORD` | `openssl rand -hex 16` |
| `MINIO_ROOT_PASSWORD` | `openssl rand -hex 16` |
| Google OAuth secret | Google Cloud Console → Credentials → Reset |
| OpenWeatherMap key | https://home.openweathermap.org/api_keys → Generate |
| Sentinel Hub secret | Sentinel Hub dashboard → OAuth clients → Reset |
| MSG91 auth key | https://msg91.com → API Keys → Generate |
| FCM server key | Firebase Console → Cloud Messaging → Regenerate |
| UIDAI API key | Email UIDAI partner support |
| Razorpay key secret | https://dashboard.razorpay.com/app/keys → Generate |
| Razorpay webhook secret | https://dashboard.razorpay.com/app/webhooks → Edit → Regenerate |
| Firebase service-account JSON | Firebase Console → Project Settings → Service Accounts → Generate new private key |
