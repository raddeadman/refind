"""Password hashing and JWT helpers.

Owner: Habib (auth). Only auth_service may call hash_password() for
passwordHash; item_service uses hash_secret() for verification answers.
"""

import re
import string
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from .config import get_settings

BCRYPT_ROUNDS = 12  # the $jsonSchema validator requires $2b$12$


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


_PUNCTUATION = re.compile(f"[{re.escape(string.punctuation)}]")
_SPACES = re.compile(r"\s+")


def normalise_answer(answer: str) -> str:
    """Lower-case, trim, drop punctuation and repeated spaces (§5.2)."""
    answer = _PUNCTUATION.sub("", answer.lower())
    return _SPACES.sub(" ", answer).strip()


def hash_secret(answer: str) -> str:
    return hash_password(normalise_answer(answer))


def verify_secret(answer: str, answer_hash: str) -> bool:
    return verify_password(normalise_answer(answer), answer_hash)


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError if the token is invalid or expired."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
