"""Authentication helpers for Hardcover personal access tokens."""

import base64
import json
from urllib.parse import urlencode

PAT_SCOPES = (
    "read:catalog",
    "read:library",
    "read:lists",
    "read:me:content",
    "write:library",
    "write:reviews",
    "write:lists",
)

PAT_CREATION_URL = "https://hardcover.app/account/api/keys/new?" + urlencode(
    {"scope": " ".join(PAT_SCOPES)}
)


def normalize_token(token: str) -> str:
    """Strip whitespace and an optional Bearer prefix from a token."""
    if not isinstance(token, str):
        return ""
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def is_legacy_jwt(token: str) -> bool:
    """Return whether a token has the structure of a legacy JWT credential."""
    token = normalize_token(token)
    if token.startswith("hc_pat_"):
        return False

    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        return False

    try:
        header = parts[0] + "=" * (-len(parts[0]) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(header).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(decoded, dict) and isinstance(decoded.get("alg"), str)
