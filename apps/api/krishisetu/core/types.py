"""Custom SQLAlchemy type decorators for production-grade type consistency."""

from __future__ import annotations

from sqlalchemy import String, TypeDecorator


def make_enum_type(python_enum: type) -> type:
    """Factory that creates a SQLAlchemy TypeDecorator for a Python str+Enum.

    Stores the enum value as VARCHAR in the database (no native PG ENUM type
    created), but always returns the Python enum instance on read — ensuring
    ``.value`` and ``isinstance(..., Enum)`` work correctly everywhere.

    Usage::

        UserRoleType = make_enum_type(UserRole)
        role: Mapped[UserRole] = mapped_column(
            UserRoleType(20), nullable=False, ...,
        )
    """

    class _EnumType(TypeDecorator):
        impl = String

        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, python_enum):
                return value.value
            # accept raw string (e.g. from server_default or bulk insert)
            if isinstance(value, str):
                return value
            raise ValueError(
                f"Expected {python_enum.__name__} or str, got {type(value).__name__}"
            )

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            return python_enum(value)

        def copy(self, **kw):
            return _EnumType(self.impl.length)

    _EnumType.__name__ = f"{python_enum.__name__}Type"
    return _EnumType
