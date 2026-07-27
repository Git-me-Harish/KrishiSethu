"""Role-Based Access Control (RBAC) permission matrix.

Defines which permission strings are granted to each role. Permissions are
granular strings (e.g., "plot:create", "disease:report:submit") used by the
`require_permissions` FastAPI dependency to enforce authorization.

To add a new permission:
1. Add it to the appropriate role's set below
2. Use it in a route:
   `@router.get("/", dependencies=[Depends(require_permissions("plot:read:own"))])`

Permissions are version-controlled in code (not in database) so changes go
through code review. This preserves auditability — every permission change
is a Git commit with reviewer sign-off.

Naming convention: `<resource>:<action>[:<scope>]`
- resource: noun (plot, disease, scheme, order, user)
- action: verb (create, read, update, delete, list, submit, review, approve)
- scope: optional (own, district, all) — defaults to "own" for read/update

Examples:
- "plot:create"        — create plots (only own, always)
- "plot:read:own"      — read own plots
- "plot:read:district" — read plots in officer's district
- "plot:read:all"      — read any plot (admin only)
- "scheme:review"      — review scheme applications
"""

from __future__ import annotations

from krishisetu.domains.identity.models import UserRole

# ---------------------------------------------------------------------------
# Permission definitions
# ---------------------------------------------------------------------------

# Each permission is a string constant — using constants avoids typos.
# Import these in route files rather than typing the string.

# Identity & profile
PERM_USER_READ_OWN = "user:read:own"
PERM_USER_UPDATE_OWN = "user:update:own"
PERM_USER_READ_ALL = "user:read:all"
PERM_USER_UPDATE_ROLE = "user:update:role"
PERM_USER_DEACTIVATE = "user:deactivate"

# Plots & land records (Phase 2)
PERM_PLOT_CREATE = "plot:create"
PERM_PLOT_READ_OWN = "plot:read:own"
PERM_PLOT_READ_DISTRICT = "plot:read:district"
PERM_PLOT_READ_ALL = "plot:read:all"
PERM_PLOT_UPDATE_OWN = "plot:update:own"
PERM_PLOT_VERIFY = "plot:verify"

# Crop disease identification (Phase 1+)
PERM_DISEASE_REPORT_SUBMIT = "disease:report:submit"
PERM_DISEASE_REPORT_READ_OWN = "disease:report:read:own"
PERM_DISEASE_REPORT_READ_DISTRICT = "disease:report:read:district"
PERM_DISEASE_REPORT_REVIEW = "disease:report:review"

# Soil & weather (Phase 2)
PERM_SOIL_TEST_READ_OWN = "soil:test:read:own"
PERM_SOIL_TEST_ADD = "soil:test:add"
PERM_WEATHER_READ = "weather:read"

# NDVI (Phase 2)
PERM_NDVI_READ_OWN = "ndvi:read:own"
PERM_NDVI_READ_DISTRICT = "ndvi:read:district"
PERM_NDVI_REFRESH = "ndvi:refresh"

# Insurance (Phase 3)
PERM_INSURANCE_APPLY = "insurance:apply"
PERM_INSURANCE_READ_OWN = "insurance:read:own"
PERM_INSURANCE_CLAIM_FILE = "insurance:claim:file"
PERM_INSURANCE_CLAIM_REVIEW = "insurance:claim:review"

# Marketplace (Phase 3)
PERM_MARKETPLACE_BROWSE = "marketplace:browse"
PERM_MARKETPLACE_ORDER = "marketplace:order"
PERM_MARKETPLACE_READ_OWN_ORDERS = "marketplace:order:read:own"
PERM_SUPPLIER_CATALOG_MANAGE = "supplier:catalog:manage"
PERM_SUPPLIER_ORDER_FULFILL = "supplier:order:fulfill"

# Govt schemes (Phase 4)
PERM_SCHEME_BROWSE = "scheme:browse"
PERM_SCHEME_APPLY = "scheme:apply"
PERM_SCHEME_APPLICATION_REVIEW = "scheme:application:review"

# Voice & notifications
PERM_VOICE_QUERY = "voice:query"
PERM_NOTIFICATION_READ_OWN = "notification:read:own"

# Consent & privacy (DPDP Act 2023)
PERM_CONSENT_MANAGE_OWN = "consent:manage:own"
PERM_CONSENT_READ_ALL = "consent:read:all"
PERM_PRIVACY_DSR_FILE = "privacy:dsr:file"
PERM_PRIVACY_DSR_REVIEW = "privacy:dsr:review"
PERM_PRIVACY_GRIEVANCE_FILE = "privacy:grievance:file"
PERM_PRIVACY_GRIEVANCE_REVIEW = "privacy:grievance:review"

# Admin
PERM_ADMIN_DASHBOARD = "admin:dashboard"
PERM_ADMIN_USER_MANAGE = "admin:user:manage"
PERM_ADMIN_CONTENT_MODERATE = "admin:content:moderate"
PERM_ADMIN_AUDIT_LOG_READ = "admin:audit:read"
PERM_ADMIN_ML_MANAGE = "admin:ml:manage"


# ---------------------------------------------------------------------------
# Role → Permissions mapping
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.FARMER: frozenset({
        # Profile
        PERM_USER_READ_OWN,
        PERM_USER_UPDATE_OWN,
        # Plots
        PERM_PLOT_CREATE,
        PERM_PLOT_READ_OWN,
        PERM_PLOT_UPDATE_OWN,
        # Disease
        PERM_DISEASE_REPORT_SUBMIT,
        PERM_DISEASE_REPORT_READ_OWN,
        # Soil & weather
        PERM_SOIL_TEST_READ_OWN,
        PERM_SOIL_TEST_ADD,
        PERM_WEATHER_READ,
        # NDVI
        PERM_NDVI_READ_OWN,
        PERM_NDVI_REFRESH,
        # Insurance
        PERM_INSURANCE_APPLY,
        PERM_INSURANCE_READ_OWN,
        PERM_INSURANCE_CLAIM_FILE,
        # Marketplace
        PERM_MARKETPLACE_BROWSE,
        PERM_MARKETPLACE_ORDER,
        PERM_MARKETPLACE_READ_OWN_ORDERS,
        # Schemes
        PERM_SCHEME_BROWSE,
        PERM_SCHEME_APPLY,
        # Voice & notifications
        PERM_VOICE_QUERY,
        PERM_NOTIFICATION_READ_OWN,
        # Consent & privacy (DPDP)
        PERM_CONSENT_MANAGE_OWN,
        PERM_PRIVACY_DSR_FILE,
        PERM_PRIVACY_GRIEVANCE_FILE,
    }),

    UserRole.AGRI_OFFICER: frozenset({
        # Officer inherits farmer's read-on-own (their own profile, if any)
        PERM_USER_READ_OWN,
        PERM_USER_UPDATE_OWN,
        # District-scoped reads
        PERM_PLOT_READ_DISTRICT,
        PERM_PLOT_VERIFY,
        PERM_DISEASE_REPORT_READ_DISTRICT,
        PERM_DISEASE_REPORT_REVIEW,
        PERM_NDVI_READ_DISTRICT,
        PERM_SOIL_TEST_ADD,
        PERM_WEATHER_READ,
        # Scheme review
        PERM_SCHEME_BROWSE,
        PERM_SCHEME_APPLICATION_REVIEW,
        # Officer can verify plots and review scheme applications
        PERM_NOTIFICATION_READ_OWN,
        PERM_VOICE_QUERY,
        # Phase F: Officer reviews DSRs and grievances
        PERM_PRIVACY_DSR_REVIEW,
        PERM_PRIVACY_GRIEVANCE_REVIEW,
        PERM_CONSENT_MANAGE_OWN,
        PERM_PRIVACY_DSR_FILE,
        PERM_PRIVACY_GRIEVANCE_FILE,
    }),

    UserRole.SUPPLIER: frozenset({
        # Supplier manages own catalog and orders
        PERM_USER_READ_OWN,
        PERM_USER_UPDATE_OWN,
        PERM_MARKETPLACE_BROWSE,
        PERM_SUPPLIER_CATALOG_MANAGE,
        PERM_SUPPLIER_ORDER_FULFILL,
        PERM_NOTIFICATION_READ_OWN,
        PERM_VOICE_QUERY,
        # Phase F: supplier is also a data subject under DPDP
        PERM_CONSENT_MANAGE_OWN,
        PERM_PRIVACY_DSR_FILE,
        PERM_PRIVACY_GRIEVANCE_FILE,
    }),

    UserRole.INSURER: frozenset({
        # Insurer reviews claims and accesses NDVI evidence
        PERM_USER_READ_OWN,
        PERM_USER_UPDATE_OWN,
        PERM_INSURANCE_CLAIM_REVIEW,
        PERM_NDVI_READ_OWN,  # For insured plots specifically (scope enforced in service)
        PERM_NOTIFICATION_READ_OWN,
        PERM_VOICE_QUERY,
        # Phase F: insurer is also a data subject under DPDP
        PERM_CONSENT_MANAGE_OWN,
        PERM_PRIVACY_DSR_FILE,
        PERM_PRIVACY_GRIEVANCE_FILE,
    }),

    UserRole.ADMIN: frozenset({
        # Admin has all permissions
        PERM_USER_READ_OWN,
        PERM_USER_UPDATE_OWN,
        PERM_USER_READ_ALL,
        PERM_USER_UPDATE_ROLE,
        PERM_USER_DEACTIVATE,
        PERM_PLOT_READ_ALL,
        PERM_DISEASE_REPORT_REVIEW,
        PERM_NDVI_READ_DISTRICT,
        PERM_SCHEME_APPLICATION_REVIEW,
        PERM_ADMIN_DASHBOARD,
        PERM_ADMIN_USER_MANAGE,
        PERM_ADMIN_CONTENT_MODERATE,
        PERM_ADMIN_AUDIT_LOG_READ,
        PERM_ADMIN_ML_MANAGE,
        PERM_NOTIFICATION_READ_OWN,
        PERM_VOICE_QUERY,
        # Phase F: Admin — full consent & privacy oversight
        PERM_CONSENT_MANAGE_OWN,
        PERM_CONSENT_READ_ALL,
        PERM_PRIVACY_DSR_FILE,
        PERM_PRIVACY_DSR_REVIEW,
        PERM_PRIVACY_GRIEVANCE_FILE,
        PERM_PRIVACY_GRIEVANCE_REVIEW,
    }),
}


def get_role_permissions(role: UserRole) -> frozenset[str]:
    """Get the set of permission strings granted to a role."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: UserRole, permission: str) -> bool:
    """Check whether a role grants a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def has_all_permissions(role: UserRole, *permissions: str) -> bool:
    """Check whether a role grants ALL of the specified permissions."""
    role_perms = ROLE_PERMISSIONS.get(role, frozenset())
    return all(p in role_perms for p in permissions)


def has_any_permission(role: UserRole, *permissions: str) -> bool:
    """Check whether a role grants ANY of the specified permissions."""
    role_perms = ROLE_PERMISSIONS.get(role, frozenset())
    return any(p in role_perms for p in permissions)
