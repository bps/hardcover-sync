"""Tests for Hardcover authentication helpers."""

import base64
import json
from urllib.parse import parse_qs, urlparse

from hardcover_sync.auth import PAT_CREATION_URL, PAT_SCOPES, is_legacy_jwt, normalize_token


def jwt_with_header(header):
    encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    return f"{encoded}.payload.signature"


def test_pat_creation_url_preselects_every_required_scope():
    parsed = urlparse(PAT_CREATION_URL)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://hardcover.app/account/api/keys/new"
    )
    assert parse_qs(parsed.query) == {"scope": [" ".join(PAT_SCOPES)]}


def test_normalize_token_strips_whitespace_and_bearer_prefix():
    assert normalize_token("  BeArEr token-value\n") == "token-value"


def test_legacy_jwt_detection_accepts_unpadded_jwt_header():
    token = jwt_with_header({"alg": "HS256", "typ": "JWT"})

    assert is_legacy_jwt(f" Bearer {token} ") is True


def test_legacy_jwt_detection_rejects_pats_and_jwt_lookalikes():
    assert is_legacy_jwt("hc_pat_abc") is False
    assert is_legacy_jwt("a.b.c") is False
    assert is_legacy_jwt(jwt_with_header({"typ": "JWT"})) is False
    assert is_legacy_jwt("") is False
    assert is_legacy_jwt(None) is False  # type: ignore[arg-type]
