"""Resolve the district/state an agri officer is allowed to operate in.

Officer endpoints (plot verification, scheme application review, disease
report review) are meant to be district-scoped, but the district was taken
from a query parameter — i.e. chosen by the caller — which makes every
officer endpoint nationwide in practice.

TODO(migration): `identity.users` has no `assigned_district` / `assigned_state`
column and there is no `identity.officer_assignments` table, so the officer's
jurisdiction cannot be read from the database. Adding those columns (plus a
backfill for existing officer accounts) is the proper fix. Until then the
assignment is read from the KRISHISETU_OFFICER_JURISDICTIONS environment
variable:

    KRISHISETU_OFFICER_JURISDICTIONS="<user_id>=<state>:<district>;<user_id>=..."

Resolution fails closed: an officer account with no assignment cannot list or
mutate anything. Admins are unrestricted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from krishisetu.core.exceptions import AuthorizationError
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.models import User, UserRole

logger = get_logger(__name__)

_ENV_VAR = "KRISHISETU_OFFICER_JURISDICTIONS"


@dataclass(frozen=True)
class OfficerJurisdiction:
    """The single district (within a state) an officer is assigned to."""

    state: str
    district: str

    def covers(self, state: str | None, district: str | None) -> bool:
        """Whether a record in (state, district) falls inside this jurisdiction."""
        if not district or district.strip().lower() != self.district.lower():
            return False
        if not state or state.strip().lower() != self.state.lower():
            return False
        return True


def _load_mapping() -> dict[str, OfficerJurisdiction]:
    """Parse the user_id → jurisdiction mapping from the environment."""
    raw = os.environ.get(_ENV_VAR, "")
    mapping: dict[str, OfficerJurisdiction] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        user_id, _, scope = entry.partition("=")
        state, _, district = scope.partition(":")
        user_id = user_id.strip().lower()
        state = state.strip()
        district = district.strip()
        if user_id and state and district:
            mapping[user_id] = OfficerJurisdiction(state=state, district=district)
    return mapping


def resolve_officer_jurisdiction(user: User) -> OfficerJurisdiction | None:
    """Return the officer's jurisdiction, or None if unrestricted (admin).

    Raises AuthorizationError for any non-admin account without an explicit
    assignment — officer endpoints must never default to nationwide access.
    """
    if user.role == UserRole.ADMIN:
        return None

    jurisdiction = _load_mapping().get(str(user.id).lower())
    if jurisdiction is None:
        logger.warning(
            "officer.jurisdiction_not_assigned",
            user_id=str(user.id),
            role=user.role.value,
        )
        raise AuthorizationError(
            "This account has no assigned district. Officer endpoints are "
            "restricted to an officer's own district."
        )

    return jurisdiction


def require_within_jurisdiction(
    jurisdiction: OfficerJurisdiction | None,
    *,
    state: str | None,
    district: str | None,
) -> None:
    """Raise AuthorizationError if a record is outside the officer's district."""
    if jurisdiction is None:
        return
    if not jurisdiction.covers(state, district):
        raise AuthorizationError(
            "This record is outside your assigned district."
        )
