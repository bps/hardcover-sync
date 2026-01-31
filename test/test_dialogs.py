"""
Tests for Phase 9 dialogs: Update Progress, Add to List, Remove from List.

These tests verify the dataclasses and helper functions without requiring Qt.
"""


# =============================================================================
# Test ListBookInfo dataclass (remove from list)
# =============================================================================


class TestListBookInfo:
    """Tests for the ListBookInfo dataclass."""

    def test_create_list_book_info(self):
        """Test creating a ListBookInfo instance."""
        from hardcover_sync.dialogs.remove_from_list import ListBookInfo

        info = ListBookInfo(
            list_id=123,
            list_name="My Reading List",
            list_book_id=456,
        )

        assert info.list_id == 123
        assert info.list_name == "My Reading List"
        assert info.list_book_id == 456


# =============================================================================
# Test dialog helper functions
# =============================================================================


class TestDialogHelpers:
    """Tests for dialog helper functionality."""

    def test_update_progress_dialog_imports(self):
        """Test that UpdateProgressDialog can be imported."""
        from hardcover_sync.dialogs.update_progress import UpdateProgressDialog

        assert UpdateProgressDialog is not None

    def test_add_to_list_dialog_imports(self):
        """Test that AddToListDialog can be imported."""
        from hardcover_sync.dialogs.add_to_list import AddToListDialog

        assert AddToListDialog is not None

    def test_remove_from_list_dialog_imports(self):
        """Test that RemoveFromListDialog can be imported."""
        from hardcover_sync.dialogs.remove_from_list import RemoveFromListDialog

        assert RemoveFromListDialog is not None

    def test_dialogs_package_exports(self):
        """Test that all dialogs are exported from the package."""
        from hardcover_sync.dialogs import (
            AddToListDialog,
            LinkBookDialog,
            RemoveFromListDialog,
            SyncFromHardcoverDialog,
            SyncToHardcoverDialog,
            UpdateProgressDialog,
        )

        assert AddToListDialog is not None
        assert LinkBookDialog is not None
        assert RemoveFromListDialog is not None
        assert SyncFromHardcoverDialog is not None
        assert SyncToHardcoverDialog is not None
        assert UpdateProgressDialog is not None


# =============================================================================
# Test API list methods that dialogs use
# =============================================================================


class TestAPIListMethods:
    """Tests for API list methods used by dialogs."""

    def test_list_dataclass(self):
        """Test creating a List instance."""
        from hardcover_sync.models import List

        lst = List(
            id=1,
            name="Favorites",
            slug="favorites",
            description="My favorite books",
            books_count=42,
        )

        assert lst.id == 1
        assert lst.name == "Favorites"
        assert lst.slug == "favorites"
        assert lst.description == "My favorite books"
        assert lst.books_count == 42

    def test_list_dataclass_defaults(self):
        """Test List dataclass with default values."""
        from hardcover_sync.models import List

        lst = List(id=1, name="Test List")

        assert lst.slug is None
        assert lst.description is None
        assert lst.books_count == 0

    def test_user_book_has_progress_fields(self):
        """Test that UserBook has progress-related fields."""
        from hardcover_sync.models import UserBook

        ub = UserBook(
            id=1,
            book_id=100,
            progress=0.5,
            progress_pages=150,
        )

        assert ub.progress == 0.5
        assert ub.progress_pages == 150


# =============================================================================
# Test API dry-run for list operations
# =============================================================================


class TestAPIListDryRun:
    """Tests for API dry-run mode with list operations."""

    def test_add_book_to_list_dry_run(self):
        """Test add_book_to_list in dry-run mode."""
        from hardcover_sync.api import HardcoverAPI

        api = HardcoverAPI(token="test-token", dry_run=True)  # noqa: S106

        # This should not make a real API call
        result = api.add_book_to_list(list_id=1, book_id=100)

        # Returns mock ID
        assert result == -1

        # Logged in dry-run log
        log = api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "add_book_to_list"
        assert log[0]["variables"]["list_id"] == 1
        assert log[0]["variables"]["book_id"] == 100

    def test_remove_book_from_list_dry_run(self):
        """Test remove_book_from_list in dry-run mode."""
        from hardcover_sync.api import HardcoverAPI

        api = HardcoverAPI(token="test-token", dry_run=True)  # noqa: S106

        result = api.remove_book_from_list(list_book_id=456)

        assert result is True

        log = api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "remove_book_from_list"
        assert log[0]["variables"]["list_book_id"] == 456


# =============================================================================
# Test progress update API
# =============================================================================


class TestProgressUpdateAPI:
    """Tests for progress update via API."""

    def test_update_user_book_status_dry_run(self):
        """Test updating status in dry-run mode."""
        from hardcover_sync.api import HardcoverAPI

        api = HardcoverAPI(token="test-token", dry_run=True)  # noqa: S106

        result = api.update_user_book(user_book_id=123, status_id=3)

        assert result.id == 123

        log = api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "update_user_book"
        assert log[0]["variables"]["id"] == 123
        assert log[0]["variables"]["object"]["status_id"] == 3

    def test_add_book_dry_run(self):
        """Test adding a book in dry-run mode."""
        from hardcover_sync.api import HardcoverAPI

        api = HardcoverAPI(token="test-token", dry_run=True)  # noqa: S106

        result = api.add_book_to_library(
            book_id=100,
            status_id=2,  # Currently Reading
        )

        assert result.book_id == 100

        log = api.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["operation"] == "add_book_to_library"
        assert log[0]["variables"]["object"]["book_id"] == 100
        assert log[0]["variables"]["object"]["status_id"] == 2
