"""Token creation and hashing.

Nothing sensitive is ever stored in plaintext:

* dashboard sessions  -> 32 random bytes, stored as a SHA-256 digest
* extension tokens    -> prefixed random bytes, stored as a SHA-256 digest
* pairing codes       -> 8 human-typable chars from an unambiguous alphabet,
                          stored as an HMAC-SHA256 digest keyed by SECRET_KEY

SHA-256 is correct here (not argon2) because these are high-entropy machine
generated secrets, not user-chosen passwords: there is nothing to brute-force.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string
import uuid

from app.core.config import settings

# No 0/O, 1/I/L, 2/Z, 5/S: people read these off a screen and type them by hand.
PAIRING_ALPHABET = "ACDEFGHJKMNPQRTUVWXY34679"
PAIRING_CODE_LENGTH = 8
EXTENSION_TOKEN_PREFIX = "aa_ext_"

_PAIRING_CLEANUP = re.compile(r"[\s\-_]+")


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_extension_token() -> str:
    return EXTENSION_TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_secret(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


def new_pairing_code() -> str:
    return "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def normalise_pairing_code(code: str) -> str:
    return _PAIRING_CLEANUP.sub("", code.strip()).upper()


def hash_pairing_code(code: str) -> bytes:
    normalised = normalise_pairing_code(code)
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        normalised.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def sign_payload(payload: str) -> str:
    """HMAC signature for short-lived file URLs."""
    return hmac.new(
        settings.secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def signatures_match(expected: str, provided: str) -> bool:
    return hmac.compare_digest(expected, provided)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def is_valid_pairing_code(code: str) -> bool:
    normalised = normalise_pairing_code(code)
    return len(normalised) == PAIRING_CODE_LENGTH and all(
        char in PAIRING_ALPHABET for char in normalised
    )


# Kept for callers that want a human-readable install label.
def short_id() -> str:
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
