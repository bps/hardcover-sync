"""
Tests for the Hardcover API client.

These tests use mocked responses to avoid actual API calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from hardcover_sync.api import (
    AuthenticationError,
    Author,
    Book,
    Edition,
    HardcoverAPI,
    HardcoverAPIError,
    List,
    RateLimitError,
    User,
    UserBook,
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
    return HardcoverAPI(token="test-token")


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
                "image": "https://example.com/avatar.jpg",
            }
        }

        user = api.get_me()

        assert user.id == 123
        assert user.username == "testuser"
        assert user.name == "Test User"
        assert user.books_count == 42
        assert user.image == "https://example.com/avatar.jpg"

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
            "me": {"id": 123, "username": "testuser", "name": None, "books_count": 0, "image": None}
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
                "results": [
                    {
                        "id": 1,
                        "title": "The Great Gatsby",
                        "slug": "the-great-gatsby",
                        "release_date": "1925-04-10",
                        "contributions": [{"author": {"id": 1, "name": "F. Scott Fitzgerald"}}],
                        "editions": [{"id": 101, "isbn_13": "9780743273565", "isbn_10": None}],
                    },
                    {
                        "id": 2,
                        "title": "Gatsby's Girl",
                        "slug": "gatsbys-girl",
                        "release_date": "2010-01-01",
                        "contributions": [{"author": {"id": 2, "name": "Someone Else"}}],
                        "editions": [],
                    },
                ]
            }
        }

        books = api.search_books("Gatsby")

        assert len(books) == 2
        assert books[0].title == "The Great Gatsby"
        assert books[0].authors[0].name == "F. Scott Fitzgerald"
        assert len(books[0].editions) == 1

    def test_search_books_empty(self, api, mock_client):
        """Test search with no results."""
        mock_client.return_value.execute.return_value = {"search": {"results": []}}

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
                    "image": None,
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
                        "progress": None,
                        "progress_pages": 100,
                        "started_at": "2024-01-01",
                        "finished_at": "2024-01-15",
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
                    "image": None,
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
