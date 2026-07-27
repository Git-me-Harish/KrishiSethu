"""Input sanitization utilities.

Defense-in-depth helpers that complement (but do NOT replace) parameterized
queries and Pydantic validation. These are designed to be applied at service-
layer boundaries where untrusted strings need to be normalized before being
used in:
- SQL LIKE patterns (which still go through parameterized queries, but special
  characters need escaping to prevent unintended wildcard matching)
- File name generation (prevent path traversal)
- HTML/JSON responses (prevent reflected XSS where auto-escaping is bypassed)
- Free-text fields shown in admin UIs (prevent stored XSS in admin pages)

Important: These helpers DO NOT make SQL string interpolation safe. Always
use parameterized queries (SQLAlchemy ORM / Core) for all DB access.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

# Maximum allowed input length for free-text fields (defense against
# ReDoS, payload bombs, and database bloat).
MAX_FREE_TEXT_LENGTH = 10_000
MAX_NAME_LENGTH = 200
MAX_FILENAME_LENGTH = 255


# Patterns that are almost always malicious in user-supplied text.
# These are BLOCKED entirely (raise ValueError) rather than stripped,
# because they have no legitimate use in farmer-facing inputs.
_SUSPICIOUS_PATTERNS = [
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"<\s*iframe", re.IGNORECASE),
    re.compile(r"<\s*object", re.IGNORECASE),
    re.compile(r"<\s*embed", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"vbscript:", re.IGNORECASE),
    re.compile(r"data:text/html", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # onerror=, onclick=, etc.
]

# SQL keywords commonly used in injection attacks — for detection only,
# NOT for blocking (legitimate text may contain these words).
# Used by detect_sql_injection_attempt() which logs suspicious patterns
# but does not reject input (we rely on parameterized queries).
_SQL_INJECTION_PATTERNS = [
    re.compile(r"'\s*OR\s*'?'?\s*=\s*'?'?\s*", re.IGNORECASE),
    re.compile(r"'\s*OR\s+1\s*=\s*1", re.IGNORECASE),
    re.compile(r"--\s*$", re.IGNORECASE),
    re.compile(r";\s*DROP\s+TABLE", re.IGNORECASE),
    re.compile(r";\s*DELETE\s+FROM", re.IGNORECASE),
    re.compile(r"UNION\s+SELECT\s+NULL", re.IGNORECASE),
    re.compile(r"INTO\s+OUTFILE", re.IGNORECASE),
    re.compile(r"xp_cmdshell", re.IGNORECASE),
    re.compile(r"information_schema\.", re.IGNORECASE),
]

# Path traversal patterns
_PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e%2f", re.IGNORECASE),
    re.compile(r"%2e%2e/", re.IGNORECASE),
    re.compile(r"\.\.%2f", re.IGNORECASE),
]


class InputValidationError(Exception):
    """Raised when input fails sanitization checks."""

    def __init__(self, message: str, field: str = "input") -> None:
        self.field = field
        super().__init__(message)
        self.message = message


def sanitize_free_text(
    value: str,
    *,
    max_length: int = MAX_FREE_TEXT_LENGTH,
    field_name: str = "input",
) -> str:
    """Sanitize free-text input (e.g. disease report notes, grievance text).

    - Normalizes Unicode (NFC) so visually identical strings compare equal.
    - Strips control characters except newlines and tabs.
    - Blocks <script>, <iframe>, javascript:, on*=, etc. entirely.
    - Enforces max_length (truncates with ellipsis at the boundary).
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InputValidationError(
            f"{field_name} must be a string, got {type(value).__name__}", field_name
        )

    # Unicode normalization (NFC: composed form)
    text = unicodedata.normalize("NFC", value)

    # Strip control chars except \n, \r, \t
    text = "".join(
        ch for ch in text
        if ch in "\n\r\t" or unicodedata.category(ch)[0] != "C"
    )

    # Check for suspicious patterns
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            raise InputValidationError(
                f"{field_name} contains disallowed content", field_name
            )

    # Length check
    if len(text) > max_length:
        text = text[: max_length - 1] + "\u2026"  # ellipsis

    return text.strip()


def sanitize_name(value: str, *, field_name: str = "name") -> str:
    """Sanitize a person/place/product name.

    - Allows letters (any script), spaces, hyphens, apostrophes, periods.
    - Blocks digits and special characters.
    - Max 200 chars.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).strip()
    if len(text) > MAX_NAME_LENGTH:
        raise InputValidationError(
            f"{field_name} exceeds {MAX_NAME_LENGTH} characters", field_name
        )
    # Allow letters (any script), spaces, hyphens, apostrophes, periods
    if not re.match(r"^[\w\s\-\'.]+$", text, re.UNICODE):
        raise InputValidationError(
            f"{field_name} contains invalid characters", field_name
        )
    # Block HTML-like patterns even in names
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            raise InputValidationError(
                f"{field_name} contains disallowed content", field_name
            )
    return text


def sanitize_filename(filename: str) -> str:
    """Sanitize a user-supplied filename for safe storage.

    - Blocks path traversal (../, ..\\, encoded variants).
    - Strips directory components.
    - Replaces unsafe characters with underscores.
    - Enforces 255-char limit.
    - Returns the basename only.

    The result is safe to use as part of a path ONLY when combined with a
    fixed directory prefix (never use user input to choose the directory).
    """
    if not filename:
        raise InputValidationError("Filename cannot be empty", "filename")

    # Decode any URL-encoded traversal attempts
    text = unicodedata.normalize("NFC", filename)

    # Block path traversal
    for pattern in _PATH_TRAVERSAL_PATTERNS:
        if pattern.search(text):
            raise InputValidationError("Filename contains path traversal", "filename")

    # Strip directory components (take basename only)
    text = text.replace("\\", "/").split("/")[-1]

    # Block hidden files (.env, .git, etc.) and shell-special chars
    if text.startswith(".") or text in {".", ".."}:
        raise InputValidationError("Filename cannot start with a dot", "filename")

    # Replace unsafe characters (keep alphanumerics, dash, underscore, dot, space)
    text = re.sub(r"[^\w\-. ]", "_", text, flags=re.UNICODE)

    # Collapse multiple underscores/spaces
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"\s+", " ", text)

    if len(text) > MAX_FILENAME_LENGTH:
        # Truncate while preserving extension
        if "." in text:
            stem, ext = text.rsplit(".", 1)
            max_stem = MAX_FILENAME_LENGTH - len(ext) - 1
            text = stem[:max_stem] + "." + ext
        else:
            text = text[:MAX_FILENAME_LENGTH]

    return text.strip(" ._") or "untitled"


def sanitize_sql_like(value: str) -> str:
    """Escape special characters in a SQL LIKE pattern.

    Even with parameterized queries, LIKE patterns need their own escaping
    because % and _ are wildcards. This escapes them so the user-supplied
    value is matched literally.

    Usage with SQLAlchemy:
        from krishisetu.core.input_sanitizer import sanitize_sql_like

        pattern = f"%{sanitize_sql_like(user_input)}%"
        stmt = select(User).where(User.phone.ilike(pattern))
    """
    if value is None:
        return ""
    # Escape \, %, _ (in this order)
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def detect_sql_injection_attempt(value: str) -> bool:
    """Heuristic detection of SQL injection patterns.

    Returns True if the input matches known SQLi signatures. Does NOT
    modify the input — used for logging/alerting only, since parameterized
    queries make actual injection impossible.

    Used by the SQL injection guard middleware to log suspicious requests
    for security monitoring.
    """
    if not value or not isinstance(value, str):
        return False
    return any(pattern.search(value) for pattern in _SQL_INJECTION_PATTERNS)


def sanitize_url(url: str, *, allowed_schemes: tuple[str, ...] = ("https", "http")) -> str:
    """Validate and sanitize a URL.

    - Allows only the specified schemes (default: https, http).
    - Blocks JavaScript: and data: URLs entirely.
    - Returns the URL percent-encoded if needed.
    """
    if not url:
        raise InputValidationError("URL cannot be empty", "url")
    text = url.strip()
    scheme_match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", text)
    if not scheme_match:
        raise InputValidationError("URL must have a scheme", "url")
    scheme = scheme_match.group(1).lower()
    if scheme not in allowed_schemes:
        raise InputValidationError(
            f"URL scheme '{scheme}' not allowed (allowed: {allowed_schemes})", "url"
        )
    # Re-encode to ensure no unencoded control chars
    return quote(text, safe=":/?&=#%+@,;")

__all__ = [
    "MAX_FILENAME_LENGTH",
    "MAX_FREE_TEXT_LENGTH",
    "MAX_NAME_LENGTH",
    "InputValidationError",
    "detect_sql_injection_attempt",
    "sanitize_filename",
    "sanitize_free_text",
    "sanitize_name",
    "sanitize_sql_like",
    "sanitize_url",
]
