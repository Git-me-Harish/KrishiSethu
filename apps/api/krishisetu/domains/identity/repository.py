"""Database access layer for the identity domain.

The repository pattern centralizes all database queries for a domain in one
place. Benefits:
- Business logic in services/ doesn't depend directly on SQLAlchemy
- Easier to swap implementations (e.g., add caching layer)
- Easier to test (mock the repository interface)
- Single source of truth for query patterns

All methods are async and accept a session (transaction scope is managed by
the FastAPI dependency `get_db`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.security import hash_password
from krishisetu.domains.identity.models import RefreshToken, User, UserRole


# ---------------------------------------------------------------------------
# User queries
# ---------------------------------------------------------------------------


async def get_user_by_id(db: AsyncSession, user_id: UUID | str) -> User | None:
    """Fetch a user by primary key."""
    result = await db.execute(
        select(User).where(User.id == UUID(str(user_id)) if isinstance(user_id, str) else user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    """Fetch a user by phone number (10-digit normalized)."""
    result = await db.execute(select(User).where(User.phone == phone))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Fetch a user by email address."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_google_sub(db: AsyncSession, google_sub: str) -> User | None:
    """Fetch a user by Google's immutable subject identifier."""
    result = await db.execute(select(User).where(User.google_sub == google_sub))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    phone: str,
    full_name: str,
    role: UserRole = UserRole.FARMER,
    email: str | None = None,
    password: str | None = None,
    preferred_language: str = "en",
    phone_verified: bool = True,  # If creating via OTP flow, phone is verified
) -> User:
    """Create a new user.

    If a password is provided, it is hashed before storage. If not, the user
    is OTP-only (password_hash is NULL).
    """
    user = User(
        phone=phone,
        full_name=full_name,
        role=role,
        email=email,
        phone_verified=phone_verified,
        preferred_language=preferred_language,
        password_hash=hash_password(password) if password else None,
    )
    db.add(user)
    await db.flush()  # Populate user.id without committing
    await db.refresh(user)
    return user


# Fields that may be written through update_user. Anything not listed here —
# notably password_hash, phone, and the login-lockout counters — must be
# changed through its own dedicated function, so a caller that forwards
# request data as **kwargs can never mass-assign it.
_UPDATABLE_USER_FIELDS = frozenset({
    "full_name",
    "email",
    "email_verified",
    "phone_verified",
    "preferred_language",
    "aadhaar_hash",
    "aadhaar_verified",
    "google_sub",
    # Privileged — only reachable from the admin-guarded /admin/users route.
    "role",
    "is_active",
})


async def update_user(
    db: AsyncSession,
    user_id: UUID,
    **fields: object,
) -> User | None:
    """Update allowlisted fields on a user.

    Only the fields provided in kwargs are updated, and only if they appear in
    `_UPDATABLE_USER_FIELDS`. Returns the updated user, or None if the user
    does not exist.

    Raises ValueError if a caller passes a field that is not updatable — a
    loud failure is preferable to silently dropping the write.
    """
    if not fields:
        return await get_user_by_id(db, user_id)

    rejected = sorted(set(fields) - _UPDATABLE_USER_FIELDS)
    if rejected:
        raise ValueError(
            f"Fields not updatable via update_user: {', '.join(rejected)}"
        )

    await db.execute(
        update(User).where(User.id == user_id).values(**fields)
    )
    await db.flush()
    return await get_user_by_id(db, user_id)


async def update_last_login(db: AsyncSession, user_id: UUID) -> None:
    """Update the last_login_at timestamp to now."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(last_login_at=datetime.now(timezone.utc))
    )
    await db.flush()


async def increment_failed_login(db: AsyncSession, user_id: UUID) -> int:
    """Increment failed_login_count, return the new count."""
    user = await get_user_by_id(db, user_id)
    if not user:
        return 0
    new_count = user.failed_login_count + 1
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(failed_login_count=new_count)
    )
    await db.flush()
    return new_count


async def reset_failed_login(db: AsyncSession, user_id: UUID) -> None:
    """Reset failed_login_count to 0 and clear locked_until."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(failed_login_count=0, locked_until=None)
    )
    await db.flush()


async def lock_account(
    db: AsyncSession, user_id: UUID, lock_duration_minutes: int = 15
) -> None:
    """Lock an account for the specified duration."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            locked_until=datetime.now(timezone.utc)
            + timedelta(minutes=lock_duration_minutes)
        )
    )
    await db.flush()


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> tuple[list[User], int]:
    """List users with pagination and optional filters.

    Returns a tuple of (users, total_count).
    """
    query = select(User)
    count_query = select(func.count(User.id))

    if role is not None:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    # Get total count
    total = (await db.execute(count_query)).scalar_one()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    users = list((await db.execute(query)).scalars().all())

    return users, total


# ---------------------------------------------------------------------------
# Refresh token queries
# ---------------------------------------------------------------------------


async def create_refresh_token(
    db: AsyncSession,
    *,
    user_id: UUID,
    token_hash: str,
    jti: str,
    expires_at: datetime,
    device_info: str | None = None,
    ip_address: str | None = None,
) -> RefreshToken:
    """Persist a new refresh token."""
    token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        jti=jti,
        expires_at=expires_at,
        device_info=device_info,
        ip_address=ip_address,
    )
    db.add(token)
    await db.flush()
    await db.refresh(token)
    return token


async def get_refresh_token_by_jti(
    db: AsyncSession, jti: str
) -> RefreshToken | None:
    """Fetch a refresh token by its JWT ID (jti)."""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.jti == jti)
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(
    db: AsyncSession,
    jti: str,
    reason: str = "logout",
) -> bool:
    """Mark a refresh token as revoked.

    Returns True if a token was found and revoked, False if not found or
    already revoked.
    """
    token = await get_refresh_token_by_jti(db, jti)
    if not token or token.is_revoked:
        return False

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti)
        .values(revoked_at=datetime.now(timezone.utc), revoked_reason=reason)
    )
    await db.flush()
    return True


async def revoke_all_user_tokens(
    db: AsyncSession,
    user_id: UUID,
    reason: str = "session_invalidation",
) -> int:
    """Revoke all active refresh tokens for a user.

    Used when:
    - User changes password
    - User changes phone number
    - Admin forces logout
    - Suspected token theft detected

    Returns the number of tokens revoked.
    """
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(
            revoked_at=datetime.now(timezone.utc),
            revoked_reason=reason,
        )
        .returning(RefreshToken.id)
    )
    rows = result.fetchall()
    await db.flush()
    return len(rows)


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """Delete expired refresh tokens older than 30 days.

    Called by a periodic Celery task. Returns the number of deleted rows.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        RefreshToken.__table__.delete().where(RefreshToken.expires_at < cutoff)
    )
    await db.flush()
    return result.rowcount or 0
