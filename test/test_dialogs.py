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

    def test_link_book_real_edition_id_returns_positive_id(self):
        """Test link dialog helper returns positive edition IDs."""
        from hardcover_sync.dialogs.link_book import _real_edition_id
        from hardcover_sync.models import Book, Edition

        book = Book(id=1, title="Test", editions=[Edition(id=123)])

        assert _real_edition_id(book) == 123

    def test_link_book_real_edition_id_ignores_search_placeholders(self):
        """Test link dialog helper ignores non-positive search placeholder edition IDs."""
        from hardcover_sync.dialogs.link_book import _real_edition_id
        from hardcover_sync.models import Book, Edition

        for edition_id in (-1, 0):
            book = Book(id=1, title="Test", editions=[Edition(id=edition_id)])

            assert _real_edition_id(book) is None

    def test_link_book_real_edition_id_handles_missing_editions(self):
        """Test link dialog helper handles books without editions."""
        from hardcover_sync.dialogs.link_book import _real_edition_id
        from hardcover_sync.models import Book

        book = Book(id=1, title="Test", editions=None)

        assert _real_edition_id(book) is None

    def test_link_book_recognizes_and_normalizes_isbn_queries(self):
        """Test manual search recognizes common ISBN-10 and ISBN-13 formats."""
        from hardcover_sync.dialogs.link_book import _isbn_from_query

        assert _isbn_from_query("978-0-306-40615-7") == "9780306406157"
        assert _isbn_from_query("0 8044 2957 x") == "080442957X"
        assert _isbn_from_query("The Hobbit") is None
        assert _isbn_from_query("123456789A") is None

    def test_link_book_manual_search_uses_exact_isbn_lookup(self, mocker):
        """Test ISBN queries use the API's exact ISBN lookup."""
        from hardcover_sync.dialogs.link_book import _manual_search
        from hardcover_sync.models import Book, Edition

        api = mocker.Mock()
        book = Book(
            id=1,
            title="Test",
            editions=[Edition(id=10, isbn_13="9780306406157")],
        )
        api.find_book_by_isbn.return_value = book

        results = _manual_search(api, "978-0-306-40615-7")

        api.find_book_by_isbn.assert_called_once_with("9780306406157")
        api.search_books.assert_not_called()
        assert [result.book for result in results] == [book]
        assert results[0].match_type == "isbn"
        assert results[0].confidence == 1.0

    def test_link_book_manual_search_falls_back_when_isbn_not_found(self, mocker):
        """Test an ISBN lookup miss falls back to the existing general search."""
        from hardcover_sync.dialogs.link_book import _manual_search
        from hardcover_sync.models import Book

        api = mocker.Mock()
        book = Book(id=1, title="Search Result")
        api.find_book_by_isbn.return_value = None
        api.search_books.return_value = [book]

        results = _manual_search(api, "9780000000000")

        api.search_books.assert_called_once_with("9780000000000")
        assert [result.book for result in results] == [book]
        assert results[0].match_type == "search"

    def test_link_book_formats_result_isbns(self):
        """Test the ISBN column includes unique ISBN-13 and ISBN-10 values."""
        from hardcover_sync.dialogs.link_book import _book_isbns
        from hardcover_sync.models import Book, Edition

        book = Book(
            id=1,
            title="Test",
            editions=[
                Edition(id=10, isbn_13="9780306406157", isbn_10="0306406152"),
                Edition(id=11, isbn_13="9780306406157"),
            ],
        )

        assert _book_isbns(book) == "9780306406157, 0306406152"
        assert _book_isbns(Book(id=2, title="No ISBN", editions=None)) == ""


class TestSyncToProgressPayloads:
    """Tests for converted percentage progress payloads."""

    def _change(self, field, pages, edition_id=None):
        from hardcover_sync.sync import SyncToChange

        return SyncToChange(
            calibre_id=1,
            calibre_title="Test Book",
            hardcover_book_id=100,
            user_book_id=10,
            field=field,
            old_value="10%",
            new_value="50%",
            api_value=pages,
            edition_id=edition_id,
        )

    def test_percentage_progress_sends_pages_and_edition(self):
        """Converted percentage uses only valid DatesReadInput fields."""
        from hardcover_sync.sync import build_sync_to_payloads

        _, read_data = build_sync_to_payloads(
            [self._change("progress_percent", 160, edition_id=9)], {}
        )

        assert read_data == {"progress_pages": 160, "edition_id": 9}
        assert "progress" not in read_data

    def test_page_progress_wins_defensively_during_apply(self):
        """Payload order cannot let percentage overwrite explicit page progress."""
        from hardcover_sync.sync import build_sync_to_payloads

        changes = [
            self._change("progress_percent", 160, edition_id=9),
            self._change("progress", 123, edition_id=8),
        ]

        _, read_data = build_sync_to_payloads(changes, {})

        assert read_data == {"progress_pages": 123, "edition_id": 8}


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
