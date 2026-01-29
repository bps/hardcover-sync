"""
Integration tests for the Hardcover API client.

These tests run against the REAL Hardcover API using read-only operations.
They are skipped unless the HARDCOVER_API_TOKEN environment variable is set.

Usage:
    # Set your API token and run tests
    export HARDCOVER_API_TOKEN="your-token-here"
    python -m pytest test/test_integration.py -v

    # Or run with token inline
    HARDCOVER_API_TOKEN="your-token" python -m pytest test/test_integration.py -v

IMPORTANT: These tests only perform READ operations. They will NOT modify
your Hardcover library. All write operations use dry-run mode.
"""

import os

import pytest

from hardcover_sync.api import (
    Book,
    HardcoverAPI,
    User,
)

# Skip all tests in this module if no token is provided
HARDCOVER_TOKEN = os.environ.get("HARDCOVER_API_TOKEN")
pytestmark = pytest.mark.skipif(
    not HARDCOVER_TOKEN,
    reason="HARDCOVER_API_TOKEN environment variable not set",
)


@pytest.fixture(scope="module")
def api():
    """Create a real API client for integration tests."""
    return HardcoverAPI(token=HARDCOVER_TOKEN)


@pytest.fixture(scope="module")
def dry_run_api():
    """Create a dry-run API client for testing mutations safely."""
    return HardcoverAPI(token=HARDCOVER_TOKEN, dry_run=True)


@pytest.fixture(scope="module")
def current_user(api):
    """Get the current user (cached for the module)."""
    return api.get_me()


# =============================================================================
# Authentication Tests
# =============================================================================


class TestAuthentication:
    """Tests for API authentication."""

    def test_get_me_returns_user(self, api):
        """Test that we can fetch the authenticated user."""
        user = api.get_me()

        assert isinstance(user, User)
        assert user.id > 0
        assert user.username
        print(f"\n  Authenticated as: @{user.username} (ID: {user.id})")
        print(f"  Books in library: {user.books_count}")

    def test_validate_token_succeeds(self, api):
        """Test that token validation works."""
        is_valid, user = api.validate_token()

        assert is_valid is True
        assert user is not None

    def test_invalid_token_fails(self):
        """Test that an invalid token is rejected."""
        bad_api = HardcoverAPI(token="invalid-token-12345")  # noqa: S106

        is_valid, user = bad_api.validate_token()

        assert is_valid is False
        assert user is None


# =============================================================================
# Book Search Tests
# =============================================================================


class TestBookSearch:
    """Tests for book search functionality."""

    def test_search_books_returns_results(self, api):
        """Test that searching for a popular book returns results."""
        books = api.search_books("The Great Gatsby")

        assert len(books) > 0
        assert isinstance(books[0], Book)

        # Should find the actual book
        titles = [b.title.lower() for b in books]
        assert any("gatsby" in t for t in titles)

        print(f"\n  Found {len(books)} results for 'The Great Gatsby'")
        for book in books[:3]:
            authors = ", ".join(a.name for a in (book.authors or []))
            print(f"    - {book.title} by {authors}")

    def test_search_books_empty_query(self, api):
        """Test searching with a nonsense query."""
        books = api.search_books("xyznonexistentbook12345")

        # Should return empty list, not error
        assert isinstance(books, list)
        assert len(books) == 0

    def test_find_book_by_isbn13(self, api):
        """Test finding a book by ISBN-13."""
        # The Great Gatsby - a well-known ISBN
        book = api.find_book_by_isbn("9780743273565")

        if book:
            print(f"\n  Found: {book.title} (ID: {book.id})")
            assert "gatsby" in book.title.lower()
        else:
            # ISBN might not be in their database
            pytest.skip("ISBN not found in Hardcover database")

    def test_find_book_by_isbn_with_dashes(self, api):
        """Test that ISBN with dashes is handled correctly."""
        book = api.find_book_by_isbn("978-0-7432-7356-5")

        # Should work the same as without dashes
        if book:
            assert book.id > 0


# =============================================================================
# User Library Tests (Read-Only)
# =============================================================================


class TestUserLibrary:
    """Tests for reading user library data."""

    def test_get_user_books(self, api, current_user):
        """Test fetching books from user's library."""
        books = api.get_user_books(limit=10)

        assert isinstance(books, list)
        print(f"\n  User has {current_user.books_count} total books")
        print(f"  Fetched {len(books)} books")

        if books:
            for ub in books[:3]:
                title = ub.book.title if ub.book else f"Book #{ub.book_id}"
                status_names = {
                    1: "Want to Read",
                    2: "Currently Reading",
                    3: "Read",
                    4: "Paused",
                    5: "DNF",
                    6: "Ignored",
                }
                status = status_names.get(ub.status_id, f"Status {ub.status_id}")
                print(f"    - {title} [{status}]")

    def test_get_user_book_by_id(self, api):
        """Test fetching a specific book from the library."""
        # First get a book from the library
        books = api.get_user_books(limit=1)

        if not books:
            pytest.skip("No books in user library")

        book_id = books[0].book_id
        user_book = api.get_user_book(book_id)

        assert user_book is not None
        assert user_book.book_id == book_id

    def test_get_user_book_not_in_library(self, api):
        """Test fetching a book that's not in the library."""
        # Use a very high ID that's unlikely to be in anyone's library
        user_book = api.get_user_book(book_id=999999999)

        assert user_book is None


# =============================================================================
# Book Details Tests
# =============================================================================


class TestBookDetails:
    """Tests for fetching book details."""

    def test_get_book_by_id(self, api):
        """Test fetching a book by its Hardcover ID."""
        # First search to get a valid book ID
        books = api.search_books("1984 George Orwell")

        if not books:
            pytest.skip("Could not find test book")

        book_id = books[0].id
        book = api.get_book_by_id(book_id)

        assert book is not None
        assert book.id == book_id
        print(f"\n  Fetched book: {book.title}")
        if book.editions:
            print(f"  Editions: {len(book.editions)}")

    def test_get_book_invalid_id(self, api):
        """Test fetching a book with invalid ID."""
        book = api.get_book_by_id(999999999)

        assert book is None


# =============================================================================
# List Tests (Read-Only)
# =============================================================================


class TestUserLists:
    """Tests for reading user lists."""

    def test_get_user_lists(self, api, current_user):
        """Test fetching user's lists."""
        lists = api.get_user_lists()

        assert isinstance(lists, list)
        print(f"\n  User has {len(lists)} lists")

        for lst in lists[:5]:
            print(f"    - {lst.name} ({lst.books_count} books)")


# =============================================================================
# Dry-Run Mutation Tests
# =============================================================================


class TestDryRunMutations:
    """Tests that verify mutations work correctly in dry-run mode.

    These tests use the real API for authentication but don't actually
    modify any data on Hardcover.
    """

    def test_dry_run_add_book(self, dry_run_api):
        """Test adding a book in dry-run mode."""
        # First, search for a book to get a valid ID
        books = dry_run_api.search_books("The Hobbit")
        if not books:
            pytest.skip("Could not find test book")

        book_id = books[0].id
        print(f"\n  Would add: {books[0].title} (ID: {book_id})")

        # This should NOT actually add the book
        result = dry_run_api.add_book_to_library(book_id=book_id, status_id=1)

        assert result.id == -1  # Placeholder ID
        assert result.book_id == book_id

        log = dry_run_api.get_dry_run_log()
        assert len(log) >= 1
        assert log[-1]["operation"] == "add_book_to_library"
        print(f"  Dry-run logged: {log[-1]['operation']}")

    def test_dry_run_update_book(self, dry_run_api):
        """Test updating a book in dry-run mode."""
        result = dry_run_api.update_user_book(
            user_book_id=12345,
            status_id=3,
            rating=4.5,
        )

        assert result.id == 12345
        assert result.status_id == 3

        log = dry_run_api.get_dry_run_log()
        assert any(op["operation"] == "update_user_book" for op in log)

    def test_dry_run_remove_book(self, dry_run_api):
        """Test removing a book in dry-run mode."""
        result = dry_run_api.remove_book_from_library(user_book_id=12345)

        assert result is True  # Simulated success

        log = dry_run_api.get_dry_run_log()
        assert any(op["operation"] == "remove_book_from_library" for op in log)

    def test_dry_run_log_contents(self, dry_run_api):
        """Test that dry-run log contains useful information."""
        dry_run_api.clear_dry_run_log()

        dry_run_api.add_book_to_library(book_id=100, status_id=2)

        log = dry_run_api.get_dry_run_log()
        assert len(log) == 1

        entry = log[0]
        assert "operation" in entry
        assert "variables" in entry
        assert "would_execute" in entry
        assert entry["variables"]["object"]["book_id"] == 100
        assert entry["variables"]["object"]["status_id"] == 2
        print(f"\n  Log entry: {entry}")
