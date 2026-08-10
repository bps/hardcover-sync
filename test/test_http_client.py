"""Tests for the standard-library Hardcover HTTP client."""

import io
import json
from urllib.error import HTTPError
from unittest.mock import patch

import pytest

from hardcover_sync.api import (
    API_URL,
    GraphQLResponseError,
    HardcoverHTTPClient,
    _NoRedirectHandler,
)


def make_client():
    """Create a client with an isolated mock URL opener."""
    with patch("hardcover_sync.api.build_opener") as build_opener:
        client = HardcoverHTTPClient("test-token", timeout=12)  # noqa: S106
    return client, build_opener.return_value


def json_response(payload):
    """Create a context-manageable byte response."""
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def http_error(status, body):
    """Create an HTTP error with a readable response body."""
    return HTTPError(API_URL, status, "error", {}, io.BytesIO(body))


class TestHardcoverHTTPClient:
    def test_execute_posts_graphql_request(self):
        client, opener = make_client()
        opener.open.return_value = json_response({"data": {"me": {"id": 1}}})

        result = client.execute("query Me { me { id } }", {"limit": 10})

        assert result == {"me": {"id": 1}}
        request = opener.open.call_args.args[0]
        assert request.full_url == API_URL
        assert request.get_method() == "POST"
        assert request.get_header("Authorization") == "Bearer test-token"
        assert request.get_header("Content-type") == "application/json"
        assert request.get_header("Accept") == "application/json"
        assert request.get_header("User-agent") == "hardcover-sync-calibre-plugin"
        assert json.loads(request.data) == {
            "query": "query Me { me { id } }",
            "variables": {"limit": 10},
        }
        assert opener.open.call_args.kwargs == {"timeout": 12}

    def test_execute_omits_variables_when_not_provided(self):
        client, opener = make_client()
        opener.open.return_value = json_response({"data": {"me": None}})

        client.execute("query Me { me { id } }")

        request = opener.open.call_args.args[0]
        assert json.loads(request.data) == {"query": "query Me { me { id } }"}

    def test_execute_raises_graphql_error(self):
        client, opener = make_client()
        opener.open.return_value = json_response(
            {"errors": [{"message": "first error"}, {"message": "second error"}]}
        )

        with pytest.raises(GraphQLResponseError, match="first error; second error"):
            client.execute("query Broken { broken }")

    def test_execute_preserves_http_status_on_graphql_error(self):
        client, opener = make_client()
        opener.open.side_effect = http_error(
            429,
            json.dumps({"errors": [{"message": "slow down"}]}).encode("utf-8"),
        )

        with pytest.raises(GraphQLResponseError, match="slow down") as exc_info:
            client.execute("query Me { me { id } }")

        assert exc_info.value.status == 429

    def test_execute_refuses_redirect_with_json_body(self):
        client, opener = make_client()
        error = http_error(302, json.dumps({"data": {"me": {"id": 1}}}).encode("utf-8"))
        opener.open.side_effect = error

        with pytest.raises(HTTPError) as exc_info:
            client.execute("query Me { me { id } }")

        assert exc_info.value is error

    def test_execute_preserves_status_when_http_error_has_no_graphql_errors(self):
        client, opener = make_client()
        opener.open.side_effect = http_error(
            401,
            json.dumps({"message": "Unauthorized"}).encode("utf-8"),
        )

        with pytest.raises(GraphQLResponseError) as exc_info:
            client.execute("query Me { me { id } }")

        assert exc_info.value.status == 401

    def test_execute_reraises_http_error_with_non_json_body(self):
        client, opener = make_client()
        error = http_error(401, b"Unauthorized")
        opener.open.side_effect = error

        with pytest.raises(HTTPError) as exc_info:
            client.execute("query Me { me { id } }")

        assert exc_info.value is error

    def test_execute_rejects_invalid_json(self):
        client, opener = make_client()
        opener.open.return_value = io.BytesIO(b"not json")

        with pytest.raises(GraphQLResponseError, match="valid JSON"):
            client.execute("query Me { me { id } }")

    @pytest.mark.parametrize("payload", [[], {}, {"data": None}])
    def test_execute_rejects_invalid_graphql_response(self, payload):
        client, opener = make_client()
        opener.open.return_value = json_response(payload)

        with pytest.raises(GraphQLResponseError, match="GraphQL response"):
            client.execute("query Me { me { id } }")

    def test_error_messages_are_truncated(self):
        error = GraphQLResponseError("x" * 1000)

        assert len(str(error)) == 500


class TestNoRedirectHandler:
    def test_redirects_are_refused(self):
        handler = _NoRedirectHandler()

        assert handler.redirect_request(None, None, 302, "Found", {}, "https://example.com") is None
