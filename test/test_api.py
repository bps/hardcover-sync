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
    UserBook,
    UserBookRead,
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
                        "review_raw": "Great book!",
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
                        "user_book_reads": [
                            {
                                "id": 100,
                                "started_at": "2024-01-01",
                                "finished_at": "2024-01-15",
                                "progress_pages": 300,
                                "edition_id": 456,
                            }
                        ],
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
        # Verify reads are parsed
        assert books[0].reads is not None
        assert len(books[0].reads) == 1
        assert books[0].latest_started_at == "2024-01-01"
        assert books[0].latest_finished_at == "2024-01-15"


class TestAddBookToLibrary:
    """Tests for the add_book_to_library method."""

    def test_add_book(self, api, mock_client):
        """Test adding a book to library."""
        mock_client.return_value.execute.return_value = {
            "insert_user_book": {
                "id": 1001,
                "user_book": {
                    "id": 1001,
                    "book_id": 789,
                    "status_id": 1,
                    "rating": None,
                    "updated_at": "2024-01-01T00:00:00",
                },
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
                "id": 1001,
                "user_book": {
                    "id": 1001,
                    "book_id": 789,
                    "status_id": 3,
                    "rating": 5,
                    "updated_at": "2024-01-15T00:00:00",
                },
            }
        }

        user_book = api.update_user_book(user_book_id=1001, status_id=3, rating=5)

        assert user_book.status_id == 3
        assert user_book.rating == 5

    def test_update_no_data(self, api, mock_client):
        """Test update when no data returned."""
        mock_client.return_value.execute.return_value = {
            "update_user_book": {"id": None, "user_book": None}
        }

        with pytest.raises(HardcoverAPIError):
            api.update_user_book(user_book_id=1001, status_id=3)


class TestRemoveBookFromLibrary:
    """Tests for the remove_book_from_library method."""

    def test_remove_book(self, api, mock_client):
        """Test removing a book from library."""
        mock_client.return_value.execute.return_value = {"delete_user_book": {"id": 1001}}

        result = api.remove_book_from_library(user_book_id=1001)

        assert result is True

    def test_remove_book_not_found(self, api, mock_client):
        """Test removing a book that doesn't exist."""
        mock_client.return_value.execute.return_value = {"delete_user_book": {"id": None}}

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
        assert log[0]["variables"]["object"]["book_id"] == 123
        assert log[0]["variables"]["object"]["status_id"] == 1

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
        assert log[0]["variables"]["object"]["status_id"] == 3

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


# =============================================================================
# UserBookRead Tests
# =============================================================================


class TestUserBookRead:
    """Tests for the UserBookRead dataclass."""

    def test_create_user_book_read(self):
        """Test creating a UserBookRead instance."""
        read = UserBookRead(
            id=100,
            started_at="2024-01-15",
            finished_at="2024-01-30",
            progress_pages=250,
            edition_id=456,
        )

        assert read.id == 100
        assert read.started_at == "2024-01-15"
        assert read.finished_at == "2024-01-30"
        assert read.progress_pages == 250
        assert read.edition_id == 456

    def test_user_book_read_with_none_values(self):
        """Test UserBookRead with missing/None values."""
        read = UserBookRead(id=100)

        assert read.id == 100
        assert read.started_at is None
        assert read.finished_at is None
        assert read.progress_pages is None
        assert read.edition_id is None


class TestUserBookWithReads:
    """Tests for UserBook with user_book_reads (multiple reads support)."""

    def test_user_book_with_no_reads(self):
        """Test UserBook with no reads array."""
        user_book = UserBook(id=1001, book_id=789)

        assert user_book.reads is None
        assert user_book.latest_read is None
        assert user_book.first_read is None
        assert user_book.latest_started_at is None
        assert user_book.latest_finished_at is None
        assert user_book.current_progress_pages is None
        assert user_book.read_count == 0

    def test_user_book_with_empty_reads(self):
        """Test UserBook with empty reads array."""
        user_book = UserBook(id=1001, book_id=789, reads=[])

        assert user_book.reads == []
        assert user_book.latest_read is None
        assert user_book.first_read is None
        assert user_book.latest_started_at is None
        assert user_book.latest_finished_at is None
        assert user_book.current_progress_pages is None
        assert user_book.read_count == 0

    def test_user_book_with_single_read(self):
        """Test UserBook with a single read."""
        read = UserBookRead(
            id=100,
            started_at="2024-01-15",
            finished_at="2024-01-30",
            progress_pages=300,
        )
        user_book = UserBook(id=1001, book_id=789, reads=[read])

        assert user_book.read_count == 1
        assert user_book.latest_read == read
        assert user_book.first_read == read
        assert user_book.latest_started_at == "2024-01-15"
        assert user_book.latest_finished_at == "2024-01-30"
        assert user_book.first_started_at == "2024-01-15"
        assert user_book.first_finished_at == "2024-01-30"
        assert user_book.current_progress_pages == 300

    def test_user_book_with_multiple_reads(self):
        """Test UserBook with multiple reads (re-reads)."""
        # Reads are ordered by started_at desc, so latest is first
        read_2024 = UserBookRead(
            id=200,
            started_at="2024-06-01",
            finished_at="2024-06-15",
            progress_pages=300,
        )
        read_2023 = UserBookRead(
            id=100,
            started_at="2023-01-01",
            finished_at="2023-01-20",
            progress_pages=300,
        )
        user_book = UserBook(id=1001, book_id=789, reads=[read_2024, read_2023])

        assert user_book.read_count == 2

        # Latest read (first in list)
        assert user_book.latest_read == read_2024
        assert user_book.latest_started_at == "2024-06-01"
        assert user_book.latest_finished_at == "2024-06-15"

        # First read (last in list)
        assert user_book.first_read == read_2023
        assert user_book.first_started_at == "2023-01-01"
        assert user_book.first_finished_at == "2023-01-20"

    def test_user_book_with_in_progress_read(self):
        """Test UserBook with a read that's in progress (no finished_at)."""
        read = UserBookRead(
            id=100,
            started_at="2024-01-15",
            finished_at=None,  # Still reading
            progress_pages=150,
        )
        user_book = UserBook(id=1001, book_id=789, reads=[read])

        assert user_book.latest_started_at == "2024-01-15"
        assert user_book.latest_finished_at is None
        assert user_book.current_progress_pages == 150

    def test_user_book_with_mixed_complete_incomplete_reads(self):
        """Test UserBook with mix of complete and in-progress reads."""
        # Latest read is in progress
        current_read = UserBookRead(
            id=200,
            started_at="2024-06-01",
            finished_at=None,
            progress_pages=50,
        )
        # Previous read was completed
        previous_read = UserBookRead(
            id=100,
            started_at="2023-01-01",
            finished_at="2023-01-20",
            progress_pages=300,
        )
        user_book = UserBook(id=1001, book_id=789, reads=[current_read, previous_read])

        # Latest read properties
        assert user_book.latest_started_at == "2024-06-01"
        assert user_book.latest_finished_at is None  # Current read not finished
        assert user_book.current_progress_pages == 50

        # First read properties
        assert user_book.first_finished_at == "2023-01-20"

    def test_deprecated_fields_are_none(self):
        """Test that deprecated fields (progress, started_at, finished_at) default to None."""
        user_book = UserBook(
            id=1001,
            book_id=789,
            reads=[
                UserBookRead(
                    id=100,
                    started_at="2024-01-15",
                    finished_at="2024-01-30",
                    progress_pages=300,
                )
            ],
        )

        # These deprecated fields should be None even when reads exist
        # (they're kept for backward compat but not populated from API)
        assert user_book.progress is None
        assert user_book.progress_pages is None
        assert user_book.started_at is None
        assert user_book.finished_at is None


class TestGetUserBooksWithReads:
    """Tests for get_user_books with user_book_reads parsing."""

    def test_get_user_books_with_reads(self, api, mock_client):
        """Test that user_book_reads are correctly parsed."""
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
                        "review_raw": "Great book!",
                        "created_at": "2024-01-01T00:00:00",
                        "updated_at": "2024-01-15T00:00:00",
                        "book": {
                            "id": 789,
                            "title": "Test Book",
                            "slug": "test-book",
                            "contributions": [],
                        },
                        "edition": {
                            "id": 456,
                            "isbn_13": "9780000000000",
                            "isbn_10": None,
                            "title": "Test Edition",
                            "pages": 300,
                        },
                        "user_book_reads": [
                            {
                                "id": 100,
                                "started_at": "2024-01-10",
                                "finished_at": "2024-01-15",
                                "progress_pages": 300,
                                "edition_id": 456,
                            }
                        ],
                    }
                ]
            },
        ]

        books = api.get_user_books()

        assert len(books) == 1
        user_book = books[0]

        # Reads should be parsed
        assert user_book.reads is not None
        assert len(user_book.reads) == 1
        assert user_book.reads[0].id == 100
        assert user_book.reads[0].started_at == "2024-01-10"
        assert user_book.reads[0].finished_at == "2024-01-15"
        assert user_book.reads[0].progress_pages == 300

        # Convenience properties should work
        assert user_book.latest_started_at == "2024-01-10"
        assert user_book.latest_finished_at == "2024-01-15"
        assert user_book.current_progress_pages == 300

    def test_get_user_books_with_multiple_reads(self, api, mock_client):
        """Test parsing multiple reads for a book."""
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
                        "rating": 5.0,
                        "review_raw": None,
                        "created_at": "2023-01-01T00:00:00",
                        "updated_at": "2024-06-20T00:00:00",
                        "book": {
                            "id": 789,
                            "title": "Favorite Book",
                            "slug": "favorite-book",
                            "contributions": [],
                        },
                        "edition": None,
                        # Multiple reads ordered by started_at desc
                        "user_book_reads": [
                            {
                                "id": 200,
                                "started_at": "2024-06-01",
                                "finished_at": "2024-06-15",
                                "progress_pages": 300,
                                "edition_id": None,
                            },
                            {
                                "id": 100,
                                "started_at": "2023-01-01",
                                "finished_at": "2023-01-20",
                                "progress_pages": 300,
                                "edition_id": 456,
                            },
                        ],
                    }
                ]
            },
        ]

        books = api.get_user_books()

        user_book = books[0]
        assert user_book.read_count == 2

        # Latest read (re-read in 2024)
        assert user_book.latest_started_at == "2024-06-01"
        assert user_book.latest_finished_at == "2024-06-15"

        # First read (original read in 2023)
        assert user_book.first_started_at == "2023-01-01"
        assert user_book.first_finished_at == "2023-01-20"

    def test_get_user_books_with_no_reads(self, api, mock_client):
        """Test parsing user_books when no reads exist."""
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
                        "status_id": 1,  # Want to Read - no reads yet
                        "rating": None,
                        "review_raw": None,
                        "created_at": "2024-01-01T00:00:00",
                        "updated_at": "2024-01-01T00:00:00",
                        "book": {
                            "id": 789,
                            "title": "TBR Book",
                            "slug": "tbr-book",
                            "contributions": [],
                        },
                        "edition": None,
                        "user_book_reads": [],  # Empty array
                    }
                ]
            },
        ]

        books = api.get_user_books()

        user_book = books[0]
        assert user_book.reads == []
        assert user_book.read_count == 0
        assert user_book.latest_started_at is None
        assert user_book.latest_finished_at is None
        assert user_book.current_progress_pages is None

    def test_get_user_books_without_reads_field(self, api, mock_client):
        """Test parsing user_books when user_book_reads field is missing entirely."""
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
                        "rating": 4.0,
                        "review_raw": None,
                        "created_at": "2024-01-01T00:00:00",
                        "updated_at": "2024-01-15T00:00:00",
                        "book": {
                            "id": 789,
                            "title": "Old Book",
                            "slug": "old-book",
                            "contributions": [],
                        },
                        "edition": None,
                        # No user_book_reads field at all
                    }
                ]
            },
        ]

        books = api.get_user_books()

        user_book = books[0]
        # Should handle missing field gracefully
        assert user_book.reads == []
        assert user_book.read_count == 0
        assert user_book.latest_started_at is None


class TestGetUserBookWithReads:
    """Tests for get_user_book (single book) with reads parsing."""

    def test_get_user_book_with_reads(self, api, mock_client):
        """Test that single user_book query parses reads."""
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
                        "status_id": 2,
                        "rating": None,
                        "review_raw": None,
                        "created_at": "2024-01-01T00:00:00",
                        "updated_at": "2024-01-10T00:00:00",
                        "user_book_reads": [
                            {
                                "id": 100,
                                "started_at": "2024-01-05",
                                "finished_at": None,  # Currently reading
                                "progress_pages": 75,
                                "edition_id": 456,
                            }
                        ],
                    }
                ]
            },
        ]

        user_book = api.get_user_book(book_id=789)

        assert user_book is not None
        assert user_book.reads is not None
        assert len(user_book.reads) == 1
        assert user_book.latest_started_at == "2024-01-05"
        assert user_book.latest_finished_at is None
        assert user_book.current_progress_pages == 75


# =============================================================================
# User Book Read CRUD Tests
# =============================================================================


class TestInsertUserBookRead:
    """Tests for the insert_user_book_read method."""

    def test_insert_user_book_read(self, api, mock_client):
        """Test inserting a new reading session."""
        mock_client.return_value.execute.return_value = {
            "insert_user_book_read": {
                "id": 200,
                "user_book_read": {
                    "id": 200,
                    "started_at": "2024-06-01",
                    "finished_at": None,
                    "paused_at": None,
                    "progress": 0.25,
                    "progress_pages": 75,
                    "edition_id": 456,
                },
            }
        }

        read = api.insert_user_book_read(
            user_book_id=1001,
            started_at="2024-06-01",
            progress_pages=75,
            progress=0.25,
            edition_id=456,
        )

        assert read.id == 200
        assert read.started_at == "2024-06-01"
        assert read.progress_pages == 75
        assert read.progress == 0.25
        assert read.edition_id == 456

    def test_dry_run_insert_user_book_read(self, mock_client):
        """Test that insert_user_book_read is logged in dry-run mode."""
        api = HardcoverAPI(token="test-token", dry_run=True)  # noqa: S106

        read = api.insert_user_book_read(
            user_book_id=1001,
            started_at="2024-06-01",
            progress_pages=100,
        )

        mock_client.return_value.execute.assert_not_called()
        assert read.id == -1
        assert read.progress_pages == 100

        log = api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "insert_user_book_read"


class TestUpdateUserBookRead:
    """Tests for the update_user_book_read method."""

    def test_update_user_book_read(self, api, mock_client):
        """Test updating a reading session."""
        mock_client.return_value.execute.return_value = {
            "update_user_book_read": {
                "id": 200,
                "user_book_read": {
                    "id": 200,
                    "started_at": "2024-06-01",
                    "finished_at": "2024-06-15",
                    "paused_at": None,
                    "progress": 1.0,
                    "progress_pages": 300,
                    "edition_id": 456,
                },
            }
        }

        read = api.update_user_book_read(
            read_id=200,
            finished_at="2024-06-15",
            progress=1.0,
            progress_pages=300,
        )

        assert read.id == 200
        assert read.finished_at == "2024-06-15"
        assert read.progress == 1.0
        assert read.progress_pages == 300

    def test_update_user_book_read_no_data(self, api, mock_client):
        """Test update when no data returned."""
        mock_client.return_value.execute.return_value = {
            "update_user_book_read": {"id": None, "user_book_read": None}
        }

        with pytest.raises(HardcoverAPIError):
            api.update_user_book_read(read_id=200, progress_pages=100)

    def test_dry_run_update_user_book_read(self, mock_client):
        """Test that update_user_book_read is logged in dry-run mode."""
        api = HardcoverAPI(token="test-token", dry_run=True)  # noqa: S106

        read = api.update_user_book_read(read_id=200, progress_pages=150)

        mock_client.return_value.execute.assert_not_called()
        assert read.id == 200
        assert read.progress_pages == 150

        log = api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "update_user_book_read"


class TestDeleteUserBookRead:
    """Tests for the delete_user_book_read method."""

    def test_delete_user_book_read(self, api, mock_client):
        """Test deleting a reading session."""
        mock_client.return_value.execute.return_value = {"delete_user_book_read": {"id": 200}}

        result = api.delete_user_book_read(read_id=200)

        assert result is True

    def test_delete_user_book_read_not_found(self, api, mock_client):
        """Test deleting a reading session that doesn't exist."""
        mock_client.return_value.execute.return_value = {"delete_user_book_read": {"id": None}}

        result = api.delete_user_book_read(read_id=9999)

        assert result is False

    def test_dry_run_delete_user_book_read(self, mock_client):
        """Test that delete_user_book_read is logged in dry-run mode."""
        api = HardcoverAPI(token="test-token", dry_run=True)  # noqa: S106

        result = api.delete_user_book_read(read_id=200)

        mock_client.return_value.execute.assert_not_called()
        assert result is True

        log = api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "delete_user_book_read"


# =============================================================================
# Book Lookup Tests (Additional)
# =============================================================================


class TestGetBookById:
    """Tests for the get_book_by_id method."""

    def test_get_book_by_id(self, api, mock_client):
        """Test getting a book by ID."""
        mock_client.return_value.execute.return_value = {
            "books": [
                {
                    "id": 789,
                    "title": "The Great Gatsby",
                    "slug": "the-great-gatsby",
                    "release_date": "1925-04-10",
                    "contributions": [{"author": {"id": 111, "name": "F. Scott Fitzgerald"}}],
                    "editions": [
                        {
                            "id": 456,
                            "isbn_13": "9780743273565",
                            "isbn_10": "0743273567",
                            "title": "The Great Gatsby (Scribner)",
                            "pages": 180,
                        }
                    ],
                }
            ]
        }

        book = api.get_book_by_id(789)

        assert book is not None
        assert book.id == 789
        assert book.title == "The Great Gatsby"
        assert book.release_date == "1925-04-10"
        assert len(book.authors) == 1
        assert book.authors[0].name == "F. Scott Fitzgerald"
        assert len(book.editions) == 1
        assert book.editions[0].isbn_13 == "9780743273565"

    def test_get_book_by_id_not_found(self, api, mock_client):
        """Test getting a book that doesn't exist."""
        mock_client.return_value.execute.return_value = {"books": []}

        book = api.get_book_by_id(99999)

        assert book is None


class TestGetBookLists:
    """Tests for the get_book_lists method."""

    def test_get_book_lists(self, api, mock_client):
        """Test getting lists that contain a book."""
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
                "list_books": [
                    {
                        "id": 1,
                        "list": {
                            "id": 10,
                            "name": "Favorites",
                            "slug": "favorites",
                        },
                    },
                    {
                        "id": 2,
                        "list": {
                            "id": 20,
                            "name": "Classics",
                            "slug": "classics",
                        },
                    },
                ]
            },
        ]

        lists = api.get_book_lists(book_id=789)

        assert len(lists) == 2
        assert lists[0].id == 10
        assert lists[0].name == "Favorites"
        assert lists[1].id == 20
        assert lists[1].name == "Classics"

    def test_get_book_lists_empty(self, api, mock_client):
        """Test getting lists for a book not in any lists."""
        mock_client.return_value.execute.side_effect = [
            {
                "me": {
                    "id": 123,
                    "username": "testuser",
                    "name": None,
                    "books_count": 0,
                }
            },
            {"list_books": []},
        ]

        lists = api.get_book_lists(book_id=789)

        assert lists == []


# =============================================================================
# Search Books Edge Cases
# =============================================================================


class TestSearchBooksEdgeCases:
    """Tests for search_books edge cases."""

    def test_search_books_legacy_list_format(self, api, mock_client):
        """Test search with legacy list format results."""
        mock_client.return_value.execute.return_value = {
            "search": {
                "results": [
                    {
                        "id": 1,
                        "title": "Test Book",
                        "slug": "test-book",
                        "release_year": 2020,
                        "author_names": ["Test Author"],
                        "isbns": [],
                    }
                ]
            }
        }

        books = api.search_books("Test")

        assert len(books) == 1
        assert books[0].title == "Test Book"

    def test_search_books_null_results(self, api, mock_client):
        """Test search with null items in results."""
        mock_client.return_value.execute.return_value = {
            "search": {
                "results": {
                    "hits": [
                        {"document": None},
                        {
                            "document": {
                                "id": 1,
                                "title": "Valid Book",
                                "slug": "valid-book",
                                "author_names": [],
                                "isbns": [],
                            }
                        },
                    ]
                }
            }
        }

        books = api.search_books("Test")

        assert len(books) == 1
        assert books[0].title == "Valid Book"

    def test_search_books_isbn_10_parsing(self, api, mock_client):
        """Test search with ISBN-10 in results."""
        mock_client.return_value.execute.return_value = {
            "search": {
                "results": {
                    "hits": [
                        {
                            "document": {
                                "id": 1,
                                "title": "Test Book",
                                "slug": "test-book",
                                "author_names": [],
                                "isbns": ["0316769177"],  # ISBN-10
                            }
                        }
                    ]
                }
            }
        }

        books = api.search_books("Test")

        assert len(books) == 1
        assert len(books[0].editions) == 1
        assert books[0].editions[0].isbn_10 == "0316769177"

    def test_search_books_no_release_year(self, api, mock_client):
        """Test search with missing release_year."""
        mock_client.return_value.execute.return_value = {
            "search": {
                "results": {
                    "hits": [
                        {
                            "document": {
                                "id": 1,
                                "title": "Test Book",
                                "slug": "test-book",
                                "author_names": [],
                                "isbns": [],
                                "release_year": None,
                            }
                        }
                    ]
                }
            }
        }

        books = api.search_books("Test")

        assert len(books) == 1
        assert books[0].release_date is None
