"""Resolve which insurer an insurer-role user is allowed to act for.

Claims belong to an insurance product, and every product names its insurer
(`insurance_products.insurer_name`). Without a binding between the reviewing
user and that insurer, any insurer account can review any claim on the
platform — so this module resolves the reviewer's insurer and callers use it
to scope both claim listing and claim review.

TODO(migration): there is no `identity.users.insurer_org` column (nor an
`insurance.insurer_users` table), so the binding cannot be read from the
database yet. Until that migration exists, the mapping is read from the
KRISHISETU_INSURER_ORGS environment variable:

    KRISHISETU_INSURER_ORGS="<user_id>=<insurer_name>;<user_id>=<insurer_name>"

The resolution fails closed: an insurer account with no mapping cannot review
or list any claim. Admins are unrestricted.
"""

from __future__ import annotations

import os

from krishisetu.core.exceptions import AuthorizationError
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.models import User, UserRole

logger = get_logger(__name__)

_ENV_VAR = "KRISHISETU_INSURER_ORGS"


def _load_mapping() -> dict[str, str]:
    """Parse the user_id → insurer_name mapping from the environment."""
    raw = os.environ.get(_ENV_VAR, "")
    mapping: dict[str, str] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        user_id, _, insurer_name = entry.partition("=")
        user_id = user_id.strip().lower()
        insurer_name = insurer_name.strip()
        if user_id and insurer_name:
            mapping[user_id] = insurer_name
    return mapping


def resolve_insurer_name(user: User) -> str | None:
    """Return the insurer this user may act for, or None if unrestricted.

    Admins are unrestricted (None). Every other caller must have an explicit
    mapping; otherwise AuthorizationError is raised.
    """
    if user.role == UserRole.ADMIN:
        return None

    insurer_name = _load_mapping().get(str(user.id).lower())
    if not insurer_name:
        logger.warning(
            "insurance.insurer_not_bound",
            user_id=str(user.id),
            role=user.role.value,
        )
        raise AuthorizationError(
            "This account is not bound to an insurer. Claim review is "
            "restricted to accounts with an assigned insurer."
        )

    return insurer_name
