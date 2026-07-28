"""Application configuration loaded from environment variables"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict



# Known dev / placeholder values that MUST NEVER appear in production.
# If you change these, also update .gitleaks.toml and .env.example so they
# stay aligned.

_KNOWN_BAD_JWT_SECRETS = frozenset({
    "dev-only-secret-please-change-in-production-with-openssl-rand-hex-32",
    "change-me-to-a-256-bit-random-secret-please-use-openssl-rand-hex-32",
})
_KNOWN_BAD_S3_SECRETS = frozenset({
    "krishisetu_dev_password",
    "change-me",
    "changeme",
})


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

    # Environment 
    ENV: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Application environment profile",
    )
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Database 
    DATABASE_URL: PostgresDsn = Field(
        ...,
        description="PostgreSQL async connection URL (postgresql+asyncpg://...)",
    )
    DB_POOL_SIZE: int = Field(default=20, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=5, le=120)
    DB_POOL_RECYCLE: int = Field(default=1800, ge=300, le=7200)

    # Redis 
    REDIS_URL: RedisDsn = Field(..., description="Redis connection URL")

    # Security 
    JWT_SECRET: SecretStr = Field(
        ...,
        min_length=32,
        description="JWT signing secret (use `openssl rand -hex 32` to generate)",
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1, le=1440)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=365)
    PASSWORD_BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=15)

    # Object Storage 
    S3_ENDPOINT: str = Field(..., description="S3-compatible endpoint URL")
    S3_ACCESS_KEY: SecretStr = Field(...)
    S3_SECRET_KEY: SecretStr = Field(...)
    S3_BUCKET_NAME: str = Field(default="krishisetu")
    S3_REGION: str = Field(default="ap-south-1")

    # CORS 
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed CORS origins",
    )

    # Frontend
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend base URL — used for OAuth callback redirects",
    )

    # Rate Limiting
    RATE_LIMIT_DEFAULT: str = Field(default="100/minute")
    RATE_LIMIT_AUTH: str = Field(default="5/minute")
    RATE_LIMIT_ML: str = Field(default="20/minute")

    # Google OAuth
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

    IMD_API_KEY: SecretStr | None = None
    OPENWEATHERMAP_API_KEY: SecretStr | None = None
    SENTINEL_HUB_CLIENT_ID: SecretStr | None = None
    SENTINEL_HUB_CLIENT_SECRET: SecretStr | None = None
    UIDAI_API_KEY: SecretStr | None = None
    UIDAI_API_URL: HttpUrl | None = None
    MSG91_AUTH_KEY: SecretStr | None = None
    FCM_SERVER_KEY: SecretStr | None = None

    ML_INFERENCE_URL: str = Field(default="http://localhost:8001")

    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = Field(default="krishisetu-api")

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
    def validate_production_secrets(self) -> "Settings":
        """Refuse to boot in production if critical secrets are missing or placeholder.

        This is the last line of defense against a misconfigured deploy. In
        development and staging we let the app boot with dev defaults so the
        developer experience stays smooth; in production we fail fast.
        """
        if not self.is_production:
            return self

        errors: list[str] = []

        jwt_val = self.JWT_SECRET.get_secret_value()
        if jwt_val in _KNOWN_BAD_JWT_SECRETS or jwt_val.startswith("change-me"):
            errors.append(
                "JWT_SECRET is a known dev/placeholder value. Generate a real one "
                "with `openssl rand -hex 32`."
            )

        s3_val = self.S3_SECRET_KEY.get_secret_value()
        if s3_val in _KNOWN_BAD_S3_SECRETS:
            errors.append(
                "S3_SECRET_KEY is a known dev placeholder. Set a real secret for "
                "production object storage."
            )

        if not self.ENCRYPTION_KEY or not self.ENCRYPTION_KEY.get_secret_value():
            errors.append(
                "ENCRYPTION_KEY is required in production for field-level encryption "
                "of PII (bank accounts, Aadhaar hashes). Generate with: "
                'python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"'
            )

        if not self.CSRF_SECRET or not self.CSRF_SECRET.get_secret_value():
            errors.append(
                "CSRF_SECRET is required in production for double-submit CSRF "
                "protection. Generate with `openssl rand -hex 32`."
            )

        if self.GOOGLE_OAUTH_CLIENT_ID and not self.GOOGLE_OAUTH_CLIENT_SECRET:
            errors.append(
                "GOOGLE_OAUTH_CLIENT_ID is set but GOOGLE_OAUTH_CLIENT_SECRET is "
                "missing. Either set the secret or clear the client ID."
            )

        if not self.DPDP_GRIEVANCE_OFFICER_EMAIL:
            errors.append(
                "DPDP_GRIEVANCE_OFFICER_EMAIL is required in production (DPDP Act "
                "2023, Section 7)."
            )

        if errors:
            raise ValueError(
                "\n\n"
                "===============================================================\n"
                "  PRODUCTION CONFIGURATION INCOMPLETE — refusing to boot.\n"
                "===============================================================\n"
                "The following secrets are missing or placeholder-valued:\n\n"
                + "\n".join(f"  - {e}" for e in errors)
                + "\n\n"
                "Fix these in your environment / .env and restart.\n"
                "See docs/security/SECRET_ROTATION_RUNBOOK.md for guidance.\n"
                "===============================================================\n"
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
