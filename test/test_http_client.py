"""Tests for the standard-library Hardcover HTTP client."""

import io
import json
from urllib.error import HTTPError
from unittest.mock import call, patch

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


def http_error(status, body, headers=None):
    """Create an HTTP error with a readable response body."""
    return HTTPError(API_URL, status, "error", headers or {}, io.BytesIO(body))


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

    @patch("hardcover_sync.api.time.sleep")
    def test_execute_retries_http_rate_limit(self, sleep):
        client, opener = make_client()
        opener.open.side_effect = [
            http_error(429, b"rate limited", {"Retry-After": "3"}),
            json_response({"data": {"me": {"id": 1}}}),
        ]

        result = client.execute("query Me { me { id } }")

        assert result == {"me": {"id": 1}}
        assert opener.open.call_count == 2
        assert sleep.call_args_list == [call(3.0)]
        first_request, second_request = [args.args[0] for args in opener.open.call_args_list]
        assert first_request is not second_request
        assert first_request.data == second_request.data
        assert first_request.get_header("Authorization") == second_request.get_header(
            "Authorization"
        )

    @patch("hardcover_sync.api.time.sleep")
    def test_execute_preserves_http_status_after_rate_limit_retries(self, sleep):
        client, opener = make_client()
        error_body = json.dumps(
            {"error": "Too Many Requests", "message": "Try again in 1 seconds."}
        ).encode("utf-8")
        opener.open.side_effect = [http_error(429, error_body) for _ in range(3)]

        with pytest.raises(GraphQLResponseError, match="Try again in 1 seconds") as exc_info:
            client.execute("query Me { me { id } }")

        assert exc_info.value.status == 429
        assert opener.open.call_count == 3
        assert sleep.call_args_list == [call(1.0), call(2.0)]

    @pytest.mark.parametrize(
        ("retry_after", "expected"),
        [(None, 2.0), ("not-a-delay", 2.0), ("nan", 2.0), ("0", 1.0), ("30", 10.0)],
    )
    def test_retry_delay_is_bounded(self, retry_after, expected):
        headers = {"Retry-After": retry_after} if retry_after is not None else None
        error = http_error(429, b"rate limited", headers)

        assert HardcoverHTTPClient._retry_delay(error, retry_number=1) == expected

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

        with pytest.raises(GraphQLResponseError, match="Unauthorized") as exc_info:
            client.execute("query Me { me { id } }")

        assert exc_info.value.status == 401
        assert opener.open.call_count == 1

    def test_execute_rejects_data_from_http_error(self):
        client, opener = make_client()
        opener.open.side_effect = http_error(
            500,
            json.dumps({"data": {"me": {"id": 1}}}).encode("utf-8"),
        )

        with pytest.raises(GraphQLResponseError, match="HTTP 500") as exc_info:
            client.execute("query Me { me { id } }")

        assert exc_info.value.status == 500
        assert opener.open.call_count == 1

    def test_execute_reraises_http_error_with_non_json_body(self):
        client, opener = make_client()
        error = http_error(401, b"Unauthorized")
        opener.open.side_effect = error

        with pytest.raises(HTTPError) as exc_info:
            client.execute("query Me { me { id } }")

        assert exc_info.value is error
        assert opener.open.call_count == 1

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
