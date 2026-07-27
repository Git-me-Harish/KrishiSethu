"""ML inference service configuration.

Loaded from environment variables with validation. Sensitive values
(S3 credentials) use SecretStr.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ML inference service settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENV: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Server
    ML_HOST: str = "0.0.0.0"
    ML_PORT: int = 8001

    # Service-to-service auth — shared secret the main API must present on
    # every inference request (header: X-ML-Service-Token). Required: the
    # service refuses to start without it, so it can never run unauthenticated.
    ML_SERVICE_TOKEN: SecretStr

    # Object Storage
    S3_ENDPOINT: str
    S3_ACCESS_KEY: SecretStr
    S3_SECRET_KEY: SecretStr
    S3_BUCKET_NAME: str = "krishisetu-models"
    S3_REGION: str = "ap-south-1"

    # Model paths
    DISEASE_CLASSIFIER_MODEL_PATH: str
    DISEASE_CLASSIFIER_MODEL_VERSION: str = "v0.1.0"

    # Model labels — comma-separated list of class names in training order
    DISEASE_CLASSIFIER_LABELS: list[str] = Field(
        default_factory=lambda: ["healthy"],
        description="Comma-separated list of class labels",
    )

    # Inference
    MODEL_WARMUP_ON_START: bool = True
    MAX_IMAGE_SIZE_MB: int = 10
    INFERENCE_TIMEOUT_SECONDS: int = 30

    # No CORS settings: this service is internal (apps/api only) and does not
    # run CORS middleware, so there is no origin allowlist to configure.

    @field_validator("DISEASE_CLASSIFIER_LABELS", mode="before")
    @classmethod
    def parse_labels(cls, v: object) -> list[str]:
        """Parse comma-separated labels string into a list."""
        if isinstance(v, str):
            return [label.strip() for label in v.split(",") if label.strip()]
        if isinstance(v, list):
            return v
        raise TypeError(f"Labels must be str or list, got {type(v)}")

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.ENV == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings() -> Settings:
    return get_settings()
