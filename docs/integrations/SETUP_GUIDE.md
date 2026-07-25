# KrishiSetu — External API Integration Setup Guide

This guide covers how to configure each external API integration for production use.

## Quick Start

All integrations are configured via environment variables in `apps/api/.env`.
In development mode (ENV=development), all APIs use synthetic data — no keys needed.

To go live, set `ENV=production` and configure the API keys below.

## Integration Status Check

After configuring, verify all integrations are working:

```bash
# Get auth token (admin)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/send-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"YOUR_ADMIN_PHONE","purpose":"login"}' | jq -r '.debug_otp')

# Login
curl -s -X POST http://localhost:8000/api/v1/auth/verify-otp \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"YOUR_ADMIN_PHONE\",\"otp\":\"$TOKEN\"}" | jq -r '.access_token'

# Check integrations
curl -s http://localhost:8000/api/v1/health/integrations \
  -H "Authorization: Bearer <TOKEN>" | jq .
```

---

## 1. IMD Weather API (Primary Weather Source)

**Purpose**: Official Indian weather data (current conditions, 7-day forecast, agromet advisories)

**Registration**: https://mausam.imd.gov.in/

**Configuration**:
```env
IMD_API_KEY=your_imd_api_key_here
```

**Rate Limits**: 60 requests/minute (platform-enforced)

**Dev Mode**: Synthetic data based on Indian climatology (monthly temp baselines, monsoon precip probabilities, latitude adjustment, time-of-day variation)

**Verification**: Check that current weather endpoint returns real data:
```bash
curl http://localhost:8000/api/v1/weather/district/Pune?state=Maharashtra
# Response should have source: "imd" (not "synthetic")
```

---

## 2. OpenWeatherMap API (Fallback Weather Source)

**Purpose**: Backup weather source when IMD is unavailable

**Registration**: https://openweathermap.org/api

**Configuration**:
```env
OPENWEATHERMAP_API_KEY=your_owm_api_key_here
```

**Rate Limits**: 60 requests/minute (free tier), 1,000 calls/day

**Dev Mode**: Returns None (OWM is optional — only used as fallback)

**Cost**: Free tier (1,000 calls/day), paid plans start at $40/month

---

## 3. Sentinel Hub API (Satellite Imagery)

**Purpose**: Sentinel-2 L2A satellite imagery for NDVI computation

**Registration**: https://www.sentinel-hub.com/dashboard/

**Configuration**:
```env
SENTINEL_HUB_CLIENT_ID=your_client_id
SENTINEL_HUB_CLIENT_SECRET=your_client_secret
```

**Rate Limits**: 30 requests/minute (free tier), 1,000 processing units/month

**Dev Mode**: Synthetic NDVI data based on:
- Monthly NDVI baselines (Kharif peak 0.65, Rabi moderate 0.40)
- Plot-specific deterministic variation
- Clustered cloud generation
- Spatial sine wave variation

**Cost**: Free tier (sufficient for ~1,000 plots), paid plans for larger scale

**Dependencies**: Requires `rasterio` for TIFF parsing:
```bash
pip install rasterio
# Or in Docker: already included in ML inference service
```

---

## 4. ISRIC SoilGrids API (Soil Data)

**Purpose**: Free global soil property predictions at 250m resolution

**Registration**: None required — free public API

**Configuration**: None needed (always live)

**URL**: https://rest.isric.org/soilgrids/v2.0/properties/query

**Rate Limits**: ~50 requests/minute (platform-enforced)

**Dev Mode**: Always live (no synthetic fallback — ISRIC is free and doesn't require a key)

**Properties fetched**:
- pH (phh2o) at 5-15cm depth
- Soil organic carbon (soc)
- Clay percentage
- Sand percentage
- Silt percentage

---

## 5. UIDAI Aadhaar e-KYC API

**Purpose**: Aadhaar OTP-based identity verification for farmers

**Registration**: https://uidai.gov.in/developers/

**Configuration**:
```env
UIDAI_API_KEY=your_uidai_api_key
UIDAI_API_URL=https://api.uidai.gov.in
```

**Rate Limits** (UIDAI-imposed):
- Max 5 OTP requests per hour per Aadhaar
- Max 20 OTP requests per day per Aadhaar
- 60-second cooldown between requests
- OTP expires after 10 minutes
- Max 3 verification attempts per OTP

**Dev Mode**: Test OTP is printed to API logs (same pattern as phone OTP):
```
============================================================
Aadhaar e-KYC OTP
Masked Aadhaar: XXXX-XXXX-1234
Transaction ID: abc123def456
OTP: 456789
============================================================
```

**Security**:
- Aadhaar number is NEVER stored in plaintext
- Only SHA-256 hash (with application salt) is stored
- All communication uses TLS 1.3
- Request payload encrypted with UIDAI's RSA-2048 public key
- Masked Aadhaar (XXXX-XXXX-1234) returned in responses

**Endpoints**:
- `POST /api/v1/auth/aadhaar/send-otp` — Send Aadhaar OTP
- `POST /api/v1/auth/aadhaar/verify-otp` — Verify OTP and mark user as Aadhaar-verified

---

## 6. MSG91 SMS Gateway

**Purpose**: Send OTP and notification SMS to farmers

**Registration**: https://msg91.com/

**Configuration**:
```env
MSG91_AUTH_KEY=your_msg91_auth_key
```

**Rate Limits**: 10 requests/second (transactional route)

**Dev Mode**: SMS is logged to stdout (ConsoleSMSBackend):
```
============================================================
SMS to 9876543210 | Purpose: login
OTP: 123456
============================================================
```

**Setup Steps**:
1. Register at MSG91
2. Add sender ID (e.g., "KRSHST") — requires TRAI approval
3. Create an OTP template
4. Set the template ID in `krishisetu/core/sms.py` (line `self.otp_template_id`)
5. Set MSG91_AUTH_KEY in .env

**Cost**: ~₹0.25 per SMS (transactional route), prepaid balance

---

## 7. FCM Push Notifications (Future)

**Purpose**: Push notifications for weather alerts, scheme notifications, order updates

**Registration**: https://firebase.google.com/cloud-messaging

**Configuration**:
```env
FCM_SERVER_KEY=your_fcm_server_key
```

**Status**: Stub configured, not yet wired to notification dispatch

---

## Rate Limiter & Circuit Breaker

All external API calls are protected by a rate limiter with circuit breaker pattern:

| Service | Max Requests | Window | Circuit Threshold | Recovery |
|---------|-------------|--------|-------------------|----------|
| IMD | 60 | 1 minute | 5 failures | 5 minutes |
| OWM | 60 | 1 minute | 5 failures | 5 minutes |
| Sentinel Hub | 30 | 1 minute | 5 failures | 5 minutes |
| ISRIC | 50 | 1 minute | 5 failures | 5 minutes |
| UIDAI | 5 | 1 minute | 5 failures | 5 minutes |
| MSG91 | 600 | 1 minute | 5 failures | 5 minutes |

When the circuit opens (after 5 consecutive failures), the platform stops calling
that API for 5 minutes and uses fallback/synthetic data instead. After 5 minutes,
the circuit half-opens (allows one test call). If the test succeeds, the circuit
closes and normal operation resumes.

Usage in code:
```python
from krishisetu.core.rate_limiter import get_rate_limiter

limiter = get_rate_limiter()
allowed, reason = await limiter.check("imd")
if not allowed:
    logger.warning("ext_api.skipped", service="imd", reason=reason)
    return None  # Use fallback

try:
    result = await api_call()
    await limiter.record_success("imd")
except Exception:
    await limiter.record_failure("imd")
    raise
```

---

## Environment Variable Summary

Create `apps/api/.env` with the following (all optional in dev mode):

```env
# Environment
ENV=production  # Change from development to production

# External APIs (all optional — platform works in dev mode without them)
IMD_API_KEY=                    # From mausam.imd.gov.in
OPENWEATHERMAP_API_KEY=         # From openweathermap.org
SENTINEL_HUB_CLIENT_ID=         # From sentinel-hub.com
SENTINEL_HUB_CLIENT_SECRET=     # From sentinel-hub.com
UIDAI_API_KEY=                  # From uidai.gov.in
UIDAI_API_URL=https://api.uidai.gov.in
MSG91_AUTH_KEY=                 # From msg91.com
FCM_SERVER_KEY=                 # From firebase.google.com (future)
```

After updating .env, restart the API:
```bash
docker compose -f infra/docker-compose.yml restart api worker celery-beat
```

Then verify with the integration health check:
```bash
curl -s http://localhost:8000/api/v1/health/integrations \
  -H "Authorization: Bearer <ADMIN_TOKEN>" | jq .
```
