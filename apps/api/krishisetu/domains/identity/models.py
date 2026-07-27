"""SQLAlchemy ORM models for the identity domain.

The User model is the central identity record. It stores authentication-related
fields (phone, password hash, role, active status, login attempt tracking)
and links to role-specific profile tables (farmer_profiles, supplier_profiles,
etc., added in subsequent sprints).

The model maps to the `identity.users` table created by Alembic migration
0001 (see alembic/versions/2026_07_19_0530_0001_initial_schema.py).

Security notes:
- `password_hash` is nullable because farmers can use OTP-only auth
- `aadhaar_hash` is nullable because Aadhaar verification is optional (Phase 1+)
- `failed_login_count` and `locked_until` implement account lockout
- The `phone` field stores the 10-digit normalized form (no country code)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Boolean, func
from krishisetu.core.types import make_enum_type
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from krishisetu.core.database import Base


class UserRole(str, Enum):
    """User roles in the platform.

    The order matters for hierarchy checks (admin > insurer > agri_officer >
    supplier > farmer), though explicit permission checks are used rather
    than hierarchy comparisons.
    """

    FARMER = "farmer"
    AGRI_OFFICER = "agri_officer"
    SUPPLIER = "supplier"
    INSURER = "insurer"
    ADMIN = "admin"


class User(Base):
    """Application user — central identity record.

    Maps to: identity.users
    """

    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    # --- Identity ---
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    phone: Mapped[str] = mapped_column(
        String(15),
        unique=True,
        nullable=False,
        index=True,
        comment="10-digit Indian mobile number, no country code",
    )
    phone_verified: Mapped[bool] = mapped_column(
        Boolean,
        server_default=func.text("false"),
        nullable=False,
        default=False,
    )
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        server_default=func.text("false"),
        nullable=False,
        default=False,
    )

    # --- Federated identity ---
    google_sub: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True,
        comment=(
            "Google's immutable subject identifier. Matched BEFORE email on "
            "OAuth login — email alone is user-settable and was hijackable."
        ),
    )

    # --- Aadhaar (encrypted / hashed only — never raw) ---
    aadhaar_hash: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        nullable=True,
        comment=(
            "Peppered PBKDF2 hash of the Aadhaar number, prefixed with its "
            "scheme version ('v2$...'). Legacy rows hold a bare SHA-256 digest."
        ),
    )
    aadhaar_verified: Mapped[bool] = mapped_column(
        Boolean,
        server_default=func.text("false"),
        nullable=False,
        default=False,
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        make_enum_type(UserRole)(20),
        nullable=False,
        default=UserRole.FARMER,
        server_default="farmer",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=func.text("true"),
        nullable=False,
        default=True,
    )
    preferred_language: Mapped[str] = mapped_column(
        String(5),
        server_default=func.text("'en'"),
        nullable=False,
        default="en",
    )

    # --- Authentication ---
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Bcrypt hash. NULL for OTP-only authentication.",
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        server_default=func.text("0"),
        nullable=False,
        default=0,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --- Timestamps (updated_by trigger, see migration 0001) ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # --- Convenience properties ---

    @property
    def is_locked(self) -> bool:
        """Whether the account is currently locked due to failed login attempts."""
        if self.locked_until is None:
            return False
        # Compare with current UTC time
        from datetime import datetime, timezone

        return datetime.now(timezone.utc) < self.locked_until

    @property
    def is_otp_only(self) -> bool:
        """Whether this user uses OTP-only authentication (no password)."""
        return self.password_hash is None

    @property
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        return self.full_name

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone} role={self.role} active={self.is_active}>"


class RefreshToken(Base):
    """Refresh token record for rotation and revocation.

    Stored in the identity.refresh_tokens table. Each refresh token use:
    1. Verifies the token exists and is not revoked
    2. Issues a new refresh token (rotation)
    3. Revokes the old token
    4. Stores the new token hash

    If a revoked token is presented, the entire session family is revoked
    (suspected token theft).
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "identity"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Owning user — FK added in next migration",
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hash of the JWT refresh token",
    )
    jti: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="JWT ID from the token's jti claim",
    )
    device_info: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="User-Agent string of the device that issued the token",
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="NULL if active; set when token is revoked (logout, rotation, or session invalidation)",
    )
    revoked_reason: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="logout, rotation, session_invalidation, suspected_theft",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked and not self.is_expired

    def __repr__(self) -> str:
        return (
            f"<RefreshToken id={self.id} user_id={self.user_id} "
            f"revoked={self.is_revoked} expired={self.is_expired}>"
        )
