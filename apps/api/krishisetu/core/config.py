"""Application configuration loaded from environment variables.

All configuration is validated at startup via Pydantic Settings. A misconfigured
environment variable causes the application to fail fast at boot, rather than
fail mysteriously at runtime.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import (
    Field,
    HttpUrl,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """KrishiSetu application settings.

    All values are loaded from environment variables (or .env file in dev).
    Sensitive values use SecretStr to avoid accidental logging.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Environment ---
    # Defaults to "production": a missing/typo'd ENV must never silently unlock
    # development-only behaviour (debug OTP echo, /docs, permissive checks).
    ENV: Literal["development", "staging", "production"] = Field(
        default="production",
        description="Application environment profile",
    )
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Database ---
    DATABASE_URL: PostgresDsn = Field(
        ...,
        description="PostgreSQL async connection URL (postgresql+asyncpg://...)",
    )
    DB_POOL_SIZE: int = Field(default=20, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=5, le=120)
    DB_POOL_RECYCLE: int = Field(default=1800, ge=300, le=7200)

    # --- Redis ---
    REDIS_URL: RedisDsn = Field(..., description="Redis connection URL")

    # --- Security ---
    JWT_SECRET: SecretStr = Field(
        ...,
        min_length=32,
        description="JWT signing secret (use `openssl rand -hex 32` to generate)",
    )
    # Constrained to symmetric HMAC families only. An unconstrained str would
    # let a bad env value ("none") disable signature verification outright.
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = Field(default="HS256")
    JWT_ISSUER: str = Field(
        default="krishisetu-api",
        description="Value of the JWT `iss` claim (issued and required on decode)",
    )
    JWT_AUDIENCE: str = Field(
        default="krishisetu-app",
        description="Value of the JWT `aud` claim (issued and required on decode)",
    )
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1, le=1440)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=365)
    PASSWORD_BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=15)

    # Dedicated pepper for the Aadhaar lookup hash. Kept separate from
    # JWT_SECRET so that rotating the signing key does not silently break
    # Aadhaar duplicate detection. See core/security.py:hash_aadhaar.
    AADHAAR_HASH_PEPPER: SecretStr | None = Field(
        default=None,
        min_length=32,
        description="Pepper for Aadhaar hashing (min 32 chars, never rotate casually)",
    )
    AADHAAR_HASH_ITERATIONS: int = Field(
        default=310_000,
        ge=100_000,
        le=2_000_000,
        description="PBKDF2-HMAC-SHA256 iteration count for Aadhaar hashing",
    )

    # --- Object Storage ---
    S3_ENDPOINT: str = Field(..., description="S3-compatible endpoint URL")
    S3_ACCESS_KEY: SecretStr = Field(...)
    S3_SECRET_KEY: SecretStr = Field(...)
    S3_BUCKET_NAME: str = Field(default="krishisetu")
    S3_REGION: str = Field(default="ap-south-1")

    # --- CORS ---
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed CORS origins",
    )

    # --- Frontend ---
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend base URL — used for OAuth callback redirects",
    )

    # --- Rate Limiting ---
    RATE_LIMIT_DEFAULT: str = Field(default="100/minute")
    # Per-IP limit on credential-guessing endpoints (login, verify-otp, OAuth
    # callback). Enforced by core/rate_limiter.AuthRateLimitMiddleware.
    RATE_LIMIT_AUTH: str = Field(default="5/minute")
    # Refresh is a legitimate background call (every access-token expiry, on
    # every open tab), so it gets a looser budget than credential entry —
    # 5/minute per IP would break users behind a shared NAT.
    RATE_LIMIT_AUTH_REFRESH: str = Field(default="30/minute")
    RATE_LIMIT_ML: str = Field(default="20/minute")

    # --- Google OAuth ---
    # Register these in Google Cloud Console → Credentials → OAuth 2.0 Client IDs
    # The redirect URI must be added to "Authorized redirect URIs" in GCC.
    GOOGLE_OAUTH_CLIENT_ID: str = Field(
        default="",
        description="Google OAuth 2.0 client ID",
    )
    GOOGLE_OAUTH_CLIENT_SECRET: SecretStr | None = Field(
        default=None,
        description="Google OAuth 2.0 client secret",
    )
    GOOGLE_OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/v1/auth/google/callback",
        description=(
            "Redirect URI sent to Google during OAuth initiation. "
            "Must exactly match an entry in Google Cloud Console's "
            "'Authorized redirect URIs'."
        ),
    )

    # --- External APIs (optional in dev) ---
    IMD_API_KEY: SecretStr | None = None
    OPENWEATHERMAP_API_KEY: SecretStr | None = None
    SENTINEL_HUB_CLIENT_ID: SecretStr | None = None
    SENTINEL_HUB_CLIENT_SECRET: SecretStr | None = None
    UIDAI_API_KEY: SecretStr | None = None
    UIDAI_API_URL: HttpUrl | None = None
    MSG91_AUTH_KEY: SecretStr | None = None
    FCM_SERVER_KEY: SecretStr | None = None

    # --- ML Inference Service ---
    ML_INFERENCE_URL: str = Field(default="http://localhost:8001")
    ML_SERVICE_TOKEN: SecretStr = Field(
        ...,
        min_length=32,
        description=(
            "Shared secret sent as the X-ML-Service-Token header on every "
            "call to the ML inference service, which is fail-closed and "
            "rejects unauthenticated requests. Required: the API cannot do "
            "disease diagnosis or voice inference without it, so a missing "
            "value must fail at boot rather than at the first farmer's "
            "upload. Generate with `openssl rand -hex 32`."
        ),
    )

    # --- Observability ---
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = Field(default="krishisetu-api")

    # --- Phase F: Security Hardening ---
    ENCRYPTION_KEY: SecretStr | None = Field(
        default=None,
        description="Base64-encoded 32-byte AES key for field-level encryption",
    )
    ENCRYPTION_KEY_PREVIOUS: list[SecretStr] = Field(
        default_factory=list,
        description="Previous encryption keys (for rotation)",
    )

    # CSRF protection (double-submit cookie)
    CSRF_SECRET: SecretStr | None = Field(
        default=None,
        min_length=32,
        description="Secret used to sign CSRF tokens (min 32 chars)",
    )
    CSRF_COOKIE_SECURE: bool = Field(
        default=True,
        description="Set CSRF cookies with Secure flag (HTTPS only)",
    )

    # Content Security Policy
    CSP_DIRECTIVES: str | None = Field(
        default=None,
        description="Content-Security-Policy directives (default: strict API policy)",
    )
    CSP_REPORT_ONLY: bool = Field(
        default=False,
        description="Emit CSP as Report-Only (for staged rollout)",
    )

    # Request body size limit (bytes). Default 15 MB.
    MAX_REQUEST_BODY_BYTES: int = Field(
        default=15 * 1024 * 1024,
        ge=1024,
        le=100 * 1024 * 1024,
        description="Maximum request body size in bytes",
    )

    # DPDP compliance settings
    DPDP_DATA_RETENTION_DAYS: int = Field(
        default=2555,
        description="Default data retention period in days for inactive accounts",
    )
    DPDP_GRIEVANCE_OFFICER_EMAIL: str | None = Field(
        default=None,
        description="Email of the DPDP Grievance Officer",
    )
    DPDP_GRIEVANCE_RESOLUTION_DAYS: int = Field(
        default=30,
        description="SLA for grievance resolution (DPDP mandates 30 days)",
    )

    # Antivirus scan endpoint (optional, for file uploads)
    AV_SCAN_URL: str | None = Field(
        default=None,
        description="ClamAV / AV service URL for async file scanning",
    )

    @field_validator("ENCRYPTION_KEY_PREVIOUS", mode="before")
    @classmethod
    def parse_encryption_keys_previous(cls, v: object) -> list[SecretStr]:
        """Accept ENCRYPTION_KEY_PREVIOUS as JSON array or comma-separated list."""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            v = v.strip().strip("[]")
            if not v:
                return []
            items = [item.strip().strip('"').strip("'") for item in v.split(",")]
            return [SecretStr(item) for item in items if item]
        if isinstance(v, list):
            return [SecretStr(item) if not isinstance(item, SecretStr) else item for item in v]
        raise TypeError(f"ENCRYPTION_KEY_PREVIOUS must be str or list, got {type(v)}")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        """Accept CORS_ORIGINS as JSON array string or comma-separated list."""
        if isinstance(v, str):
            v = v.strip().strip("[]")
            if not v:
                return []
            return [origin.strip().strip('"').strip("'") for origin in v.split(",")]
        if isinstance(v, list):
            return v
        raise TypeError(f"CORS_ORIGINS must be str or list, got {type(v)}")

    @model_validator(mode="after")
    def enforce_production_hardening(self) -> Settings:
        """Refuse to boot with a development-grade config in production.

        Each of these is a real exposure if it reaches production, and each
        is invisible at runtime until it is exploited — so fail fast at import
        time rather than warn in a log nobody reads.
        """
        if self.ENV != "production":
            return self

        problems: list[str] = []
        if self.DEBUG:
            problems.append("DEBUG must be False")
        if "*" in self.CORS_ORIGINS:
            problems.append("CORS_ORIGINS must not contain '*'")
        if self.CSRF_SECRET is None:
            problems.append("CSRF_SECRET must be set")
        if self.ENCRYPTION_KEY is None:
            problems.append("ENCRYPTION_KEY must be set")
        if not self.CSRF_COOKIE_SECURE:
            problems.append("CSRF_COOKIE_SECURE must be True")

        if problems:
            raise ValueError(
                "Insecure configuration for ENV=production: " + "; ".join(problems)
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.ENV == "development"

    @property
    def google_oauth_enabled(self) -> bool:
        """Whether Google OAuth is configured and usable."""
        return bool(self.GOOGLE_OAUTH_CLIENT_ID and self.GOOGLE_OAUTH_CLIENT_SECRET)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()  # type: ignore[call-arg]


def settings() -> Settings:
    """Get the application settings (cached)."""
    return get_settings()