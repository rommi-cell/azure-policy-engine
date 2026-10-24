"""Password hashing for the demo login (standard library only)."""

import hashlib
import hmac
import secrets

ITERATIONS = 200_000


def hash_password(password, salt=None):
    """Return 'salt$hash' using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored):
    """Check a password against a stored 'salt$hash' value in constant time."""
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)