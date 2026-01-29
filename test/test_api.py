"""
Tests for the Hardcover API client.

These tests use mocked responses to avoid actual API calls.
"""

from unittest.mock import patch

import pytest

from hardcover_sync.api import (
    AuthenticationError,
    HardcoverAPI,
    HardcoverAPIError,
    RateLimitError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_client():
    """Create a mock GraphQL client."""
    with patch("hardcover_sync.api.Client") as mock:
        yield mock


@pytest.fixture
def api(mock_client):
    """Create an API instance with a mocked client."""
    return HardcoverAPI(token="test-token")  # noqa: S106


# =============================================================================
# User Tests
# =============================================================================


class TestGetMe:
    """Tests for the get_me method."""

    def test_get_me_success(self, api, mock_client):
        """Test successful user fetch."""
        mock_client.return_value.execute.return_value = {
            "me": {
                "id": 123,
                "username": "testuser",
                "name": "Test User",
                "books_count": 42,
            }
        }

        user = api.get_me()

        assert user.id == 123
        assert user.username == "testuser"
        assert user.name == "Test User"
        assert user.books_count == 42

    def test_get_me_invalid_token(self, api, mock_client):
        """Test authentication error on invalid token."""
        from gql.transport.exceptions import TransportQueryError

        mock_client.return_value.execute.side_effect = TransportQueryError(
            "unauthorized: invalid token"
        )

        with pytest.raises(AuthenticationError):
            api.get_me()

    def test_get_me_no_data(self, api, mock_client):
        """Test error when no user data returned."""
        mock_client.return_value.execute.return_value = {"me": None}

        with pytest.raises(AuthenticationError):
            api.get_me()


class TestValidateToken:
    """Tests for the validate_token method."""

    def test_validate_token_valid(self, api, mock_client):
        """Test valid token validation."""
        mock_client.return_value.execute.return_value = {
            "me": {"id": 123, "username": "testuser", "name": None, "books_count": 0}
        }

        is_valid, user = api.validate_token()

        assert is_valid is True
        assert user is not None
        assert user.username == "testuser"

    def test_validate_token_invalid(self, api, mock_client):
        """Test invalid token validation."""
        from gql.transport.exceptions import TransportQueryError

        mock_client.return_value.execute.side_effect = TransportQueryError("unauthorized")

        is_valid, user = api.validate_token()

        assert is_valid is False
        assert user is None


# =============================================================================
# Book Lookup Tests
# =============================================================================


class TestFindBookByISBN:
    """Tests for the find_book_by_isbn method."""

    def test_find_by_isbn13(self, api, mock_client):
        """Test finding a book by ISBN-13."""
        mock_client.return_value.execute.return_value = {
            "editions": [
                {
                    "id": 456,
                    "isbn_13": "9780316769174",
                    "isbn_10": "0316769177",
                    "title": "The Catcher in the Rye",
                    "book": {
                        "id": 789,
                        "title": "The Catcher in the Rye",
                        "slug": "the-catcher-in-the-rye",
                        "contributions": [{"author": {"id": 111, "name": "J.D. Salinger"}}],
                    },
                }
            ]
        }

        book = api.find_book_by_isbn("9780316769174")

        assert book is not None
        assert book.id == 789
        assert book.title == "The Catcher in the Rye"
        assert len(book.authors) == 1
        assert book.authors[0].name == "J.D. Salinger"

    def test_find_by_isbn10(self, api, mock_client):
        """Test finding a book by ISBN-10."""
        mock_client.return_value.execute.return_value = {
            "editions": [
                {
                    "id": 456,
                    "isbn_13": "9780316769174",
                    "isbn_10": "0316769177",
                    "title": "The Catcher in the Rye",
                    "book": {
                        "id": 789,
                        "title": "The Catcher in the Rye",
                        "slug": "the-catcher-in-the-rye",
                        "contributions": [{"author": {"id": 111, "name": "J.D. Salinger"}}],
                    },
                }
            ]
        }

        book = api.find_book_by_isbn("0316769177")

        assert book is not None
        assert book.id == 789

    def test_find_by_isbn_not_found(self, api, mock_client):
        """Test when ISBN is not found."""
        mock_client.return_value.execute.return_value = {"editions": []}

        book = api.find_book_by_isbn("9780000000000")

        assert book is None

    def test_find_by_isbn_with_dashes(self, api, mock_client):
        """Test that dashes are stripped from ISBN."""
        mock_client.return_value.execute.return_value = {
            "editions": [
                {
                    "id": 456,
                    "isbn_13": "9780316769174",
                    "isbn_10": None,
                    "title": "Test",
                    "book": {
                        "id": 789,
                        "title": "Test",
                        "slug": "test",
                        "contributions": [],
                    },
                }
            ]
        }

        book = api.find_book_by_isbn("978-0-316-76917-4")

        assert book is not None
        assert book.id == 789


class TestSearchBooks:
    """Tests for the search_books method."""

    def test_search_books(self, api, mock_client):
        """Test book search."""
        mock_client.return_value.execute.return_value = {
            "search": {
                "results": {
                    "hits": [
                        {
                            "document": {
                                "id": 1,
                                "title": "The Great Gatsby",
                                "slug": "the-great-gatsby",
                                "release_year": 1925,
                                "author_names": ["F. Scott Fitzgerald"],
                                "isbns": ["9780743273565"],
                            }
                        },
                        {
                            "document": {
                                "id": 2,
                                "title": "Gatsby's Girl",
                                "slug": "gatsbys-girl",
                                "release_year": 2010,
                                "author_names": ["Someone Else"],
                                "isbns": [],
                            }
                        },
                    ]
                }
            }
        }

        books = api.search_books("Gatsby")

        assert len(books) == 2
        assert books[0].title == "The Great Gatsby"
        assert books[0].authors[0].name == "F. Scott Fitzgerald"
        assert len(books[0].editions) == 1

    def test_search_books_empty(self, api, mock_client):
        """Test search with no results."""
        mock_client.return_value.execute.return_value = {"search": {"results": {"hits": []}}}

        books = api.search_books("xyznonexistent")

        assert books == []


# =============================================================================
# User Library Tests
# =============================================================================


class TestGetUserBooks:
    """Tests for the get_user_books method."""

    def test_get_user_books(self, api, mock_client):
        """Test fetching user's library."""
        # First call is for get_me (to get user_id)
        mock_client.return_value.execute.side_effect = [
            {
                "me": {
                    "id": 123,
                    "username": "testuser",
                    "name": None,
                    "books_count": 0,
                }
            },
            {
                "user_books": [
                    {
                        "id": 1001,
                        "book_id": 789,
                        "edition_id": 456,
                        "status_id": 3,
                        "rating": 4.5,
                        "review": "Great book!",
                        "created_at": "2024-01-01T00:00:00",
                        "updated_at": "2024-01-15T00:00:00",
                        "book": {
                            "id": 789,
                            "title": "Test Book",
                            "slug": "test-book",
                            "contributions": [{"author": {"id": 111, "name": "Test Author"}}],
                        },
                        "edition": {
                            "id": 456,
                            "isbn_13": "9780000000000",
                            "isbn_10": None,
                            "title": "Test Edition",
                            "pages": 300,
                        },
                    }
                ]
            },
        ]

        books = api.get_user_books()

        assert len(books) == 1
        assert books[0].id == 1001
        assert books[0].book_id == 789
        assert books[0].status_id == 3
        assert books[0].rating == 4.5
        assert books[0].book.title == "Test Book"
        assert books[0].edition.isbn_13 == "9780000000000"


class TestAddBookToLibrary:
    """Tests for the add_book_to_library method."""

    def test_add_book(self, api, mock_client):
        """Test adding a book to library."""
        mock_client.return_value.execute.return_value = {
            "insert_user_book": {
                "id": 1001,
                "book_id": 789,
                "status_id": 1,
                "rating": None,
                "updated_at": "2024-01-01T00:00:00",
            }
        }

        user_book = api.add_book_to_library(book_id=789, status_id=1)

        assert user_book.id == 1001
        assert user_book.book_id == 789
        assert user_book.status_id == 1


class TestUpdateUserBook:
    """Tests for the update_user_book method."""

    def test_update_status(self, api, mock_client):
        """Test updating book status."""
        mock_client.return_value.execute.return_value = {
            "update_user_book": {
                "returning": [
                    {
                        "id": 1001,
                        "book_id": 789,
                        "status_id": 3,
                        "rating": 5,
                        "updated_at": "2024-01-15T00:00:00",
                    }
                ]
            }
        }

        user_book = api.update_user_book(user_book_id=1001, status_id=3, rating=5)

        assert user_book.status_id == 3
        assert user_book.rating == 5

    def test_update_no_data(self, api, mock_client):
        """Test update when no data returned."""
        mock_client.return_value.execute.return_value = {"update_user_book": {"returning": []}}

        with pytest.raises(HardcoverAPIError):
            api.update_user_book(user_book_id=1001, status_id=3)


class TestRemoveBookFromLibrary:
    """Tests for the remove_book_from_library method."""

    def test_remove_book(self, api, mock_client):
        """Test removing a book from library."""
        mock_client.return_value.execute.return_value = {"delete_user_book": {"affected_rows": 1}}

        result = api.remove_book_from_library(user_book_id=1001)

        assert result is True

    def test_remove_book_not_found(self, api, mock_client):
        """Test removing a book that doesn't exist."""
        mock_client.return_value.execute.return_value = {"delete_user_book": {"affected_rows": 0}}

        result = api.remove_book_from_library(user_book_id=9999)

        assert result is False


# =============================================================================
# List Tests
# =============================================================================


class TestGetUserLists:
    """Tests for the get_user_lists method."""

    def test_get_lists(self, api, mock_client):
        """Test fetching user's lists."""
        mock_client.return_value.execute.side_effect = [
            {
                "me": {
                    "id": 123,
                    "username": "testuser",
                    "name": None,
                    "books_count": 0,
                }
            },
            {
                "lists": [
                    {
                        "id": 1,
                        "name": "Favorites",
                        "slug": "favorites",
                        "description": "My favorite books",
                        "books_count": 10,
                        "created_at": "2024-01-01",
                        "updated_at": "2024-01-01",
                    },
                    {
                        "id": 2,
                        "name": "To Read",
                        "slug": "to-read",
                        "description": None,
                        "books_count": 5,
                        "created_at": "2024-01-01",
                        "updated_at": "2024-01-01",
                    },
                ]
            },
        ]

        lists = api.get_user_lists()

        assert len(lists) == 2
        assert lists[0].name == "Favorites"
        assert lists[0].books_count == 10


class TestAddBookToList:
    """Tests for the add_book_to_list method."""

    def test_add_to_list(self, api, mock_client):
        """Test adding a book to a list."""
        mock_client.return_value.execute.return_value = {
            "insert_list_book": {"id": 500, "list_id": 1, "book_id": 789}
        }

        list_book_id = api.add_book_to_list(list_id=1, book_id=789)

        assert list_book_id == 500


class TestRemoveBookFromList:
    """Tests for the remove_book_from_list method."""

    def test_remove_from_list(self, api, mock_client):
        """Test removing a book from a list."""
        mock_client.return_value.execute.return_value = {"delete_list_book": {"affected_rows": 1}}

        result = api.remove_book_from_list(list_book_id=500)

        assert result is True


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for API error handling."""

    def test_rate_limit_error(self, api, mock_client):
        """Test rate limit error handling."""
        from gql.transport.exceptions import TransportQueryError

        mock_client.return_value.execute.side_effect = TransportQueryError("rate limit exceeded")

        with pytest.raises(RateLimitError):
            api.get_me()

    def test_generic_error(self, api, mock_client):
        """Test generic error handling."""
        mock_client.return_value.execute.side_effect = Exception("Network error")

        with pytest.raises(HardcoverAPIError):
            api.get_me()


# =============================================================================
# Dry-Run Mode Tests
# =============================================================================


class TestDryRunMode:
    """Tests for dry-run mode functionality."""

    @pytest.fixture
    def dry_run_api(self, mock_client):
        """Create an API instance in dry-run mode."""
        return HardcoverAPI(token="test-token", dry_run=True)  # noqa: S106

    def test_dry_run_add_book_to_library(self, dry_run_api, mock_client):
        """Test that add_book_to_library is logged but not executed in dry-run mode."""
        # Should NOT call the actual API
        user_book = dry_run_api.add_book_to_library(book_id=123, status_id=1)

        # Verify mock was NOT called
        mock_client.return_value.execute.assert_not_called()

        # Verify the returned object has placeholder data
        assert user_book.id == -1
        assert user_book.book_id == 123
        assert user_book.status_id == 1

        # Verify the operation was logged
        log = dry_run_api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "add_book_to_library"
        assert log[0]["variables"]["book_id"] == 123
        assert log[0]["variables"]["status_id"] == 1

    def test_dry_run_update_user_book(self, dry_run_api, mock_client):
        """Test that update_user_book is logged but not executed in dry-run mode."""
        user_book = dry_run_api.update_user_book(user_book_id=456, status_id=3, rating=5.0)

        mock_client.return_value.execute.assert_not_called()

        assert user_book.id == 456
        assert user_book.status_id == 3
        assert user_book.rating == 5.0

        log = dry_run_api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "update_user_book"
        assert log[0]["variables"]["id"] == 456
        assert log[0]["variables"]["status_id"] == 3

    def test_dry_run_remove_book_from_library(self, dry_run_api, mock_client):
        """Test that remove_book_from_library is logged but not executed in dry-run mode."""
        result = dry_run_api.remove_book_from_library(user_book_id=789)

        mock_client.return_value.execute.assert_not_called()

        # Returns True (simulated success)
        assert result is True

        log = dry_run_api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "remove_book_from_library"
        assert log[0]["variables"]["id"] == 789

    def test_dry_run_add_book_to_list(self, dry_run_api, mock_client):
        """Test that add_book_to_list is logged but not executed in dry-run mode."""
        list_book_id = dry_run_api.add_book_to_list(list_id=10, book_id=20)

        mock_client.return_value.execute.assert_not_called()

        assert list_book_id == -1

        log = dry_run_api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "add_book_to_list"
        assert log[0]["variables"]["list_id"] == 10
        assert log[0]["variables"]["book_id"] == 20

    def test_dry_run_remove_book_from_list(self, dry_run_api, mock_client):
        """Test that remove_book_from_list is logged but not executed in dry-run mode."""
        result = dry_run_api.remove_book_from_list(list_book_id=555)

        mock_client.return_value.execute.assert_not_called()

        assert result is True

        log = dry_run_api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "remove_book_from_list"
        assert log[0]["variables"]["list_book_id"] == 555

    def test_dry_run_queries_still_execute(self, dry_run_api, mock_client):
        """Test that read-only queries still execute in dry-run mode."""
        mock_client.return_value.execute.return_value = {
            "me": {"id": 123, "username": "testuser", "name": None, "books_count": 0}
        }

        user = dry_run_api.get_me()

        # Query WAS executed
        mock_client.return_value.execute.assert_called_once()
        assert user.username == "testuser"

        # No dry-run log for queries
        assert dry_run_api.get_dry_run_log() == []

    def test_dry_run_log_multiple_operations(self, dry_run_api, mock_client):
        """Test that multiple operations are logged in sequence."""
        dry_run_api.add_book_to_library(book_id=1, status_id=1)
        dry_run_api.update_user_book(user_book_id=100, status_id=2)
        dry_run_api.remove_book_from_library(user_book_id=100)

        log = dry_run_api.get_dry_run_log()
        assert len(log) == 3
        assert log[0]["operation"] == "add_book_to_library"
        assert log[1]["operation"] == "update_user_book"
        assert log[2]["operation"] == "remove_book_from_library"

    def test_clear_dry_run_log(self, dry_run_api, mock_client):
        """Test that the dry-run log can be cleared."""
        dry_run_api.add_book_to_library(book_id=1, status_id=1)
        assert len(dry_run_api.get_dry_run_log()) == 1

        dry_run_api.clear_dry_run_log()
        assert len(dry_run_api.get_dry_run_log()) == 0

    def test_dry_run_log_is_copy(self, dry_run_api, mock_client):
        """Test that get_dry_run_log returns a copy, not the original list."""
        dry_run_api.add_book_to_library(book_id=1, status_id=1)

        log1 = dry_run_api.get_dry_run_log()
        log1.clear()  # Modify the returned list

        # Original should still have the entry
        assert len(dry_run_api.get_dry_run_log()) == 1
