"""
Tests for the sync module.

This tests the extracted business logic for syncing between Hardcover and Calibre.
"""

from hardcover_sync.api import Author, Book, Edition, UserBook
from hardcover_sync.sync import (
    NewBookAction,
    SyncChange,
    SyncToChange,
    convert_rating_from_calibre,
    convert_rating_to_calibre,
    extract_date,
    find_new_books,
    find_sync_from_changes,
    format_rating_as_stars,
    get_status_from_calibre,
    get_status_from_hardcover,
)


class TestSyncChange:
    """Tests for the SyncChange dataclass."""

    def test_create_sync_change(self):
        """Test creating a SyncChange."""
        change = SyncChange(
            calibre_id=1,
            calibre_title="Test Book",
            hardcover_book_id=100,
            field="status",
            old_value="Want to Read",
            new_value="Currently Reading",
        )
        assert change.calibre_id == 1
        assert change.field == "status"
        assert change.apply is True

    def test_sync_change_apply_default(self):
        """Test that apply defaults to True."""
        change = SyncChange(
            calibre_id=1,
            calibre_title="Test",
            hardcover_book_id=100,
            field="rating",
            old_value="3",
            new_value="5",
        )
        assert change.apply is True

    def test_sync_change_apply_false(self):
        """Test setting apply to False."""
        change = SyncChange(
            calibre_id=1,
            calibre_title="Test",
            hardcover_book_id=100,
            field="rating",
            old_value="3",
            new_value="5",
            apply=False,
        )
        assert change.apply is False

    def test_display_field_mapping(self):
        """Test display_field property."""
        fields = ["status", "rating", "progress", "date_started", "date_read", "review"]
        expected = [
            "Reading Status",
            "Rating",
            "Progress",
            "Date Started",
            "Date Read",
            "Review",
        ]
        for field, expected_display in zip(fields, expected, strict=True):
            change = SyncChange(
                calibre_id=1,
                calibre_title="Test",
                hardcover_book_id=100,
                field=field,
                old_value="old",
                new_value="new",
            )
            assert change.display_field == expected_display

    def test_sync_change_with_none_values(self):
        """Test creating SyncChange with None values."""
        change = SyncChange(
            calibre_id=1,
            calibre_title="Test",
            hardcover_book_id=100,
            field="rating",
            old_value=None,
            new_value=None,
        )
        assert change.old_value is None
        assert change.new_value is None

    def test_api_value_uses_raw_value(self):
        """Test that api_value returns raw_value when set."""
        change = SyncChange(
            calibre_id=1,
            calibre_title="Test",
            hardcover_book_id=100,
            field="rating",
            old_value="★★★☆☆",
            new_value="★★★★★",
            raw_value="10",
        )
        assert change.api_value == "10"

    def test_api_value_uses_new_value_when_no_raw(self):
        """Test that api_value returns new_value when raw_value is None."""
        change = SyncChange(
            calibre_id=1,
            calibre_title="Test",
            hardcover_book_id=100,
            field="status",
            old_value="Want to Read",
            new_value="Currently Reading",
        )
        assert change.api_value == "Currently Reading"


class TestSyncToChange:
    """Tests for the SyncToChange dataclass."""

    def test_create_sync_to_change(self):
        """Test creating a SyncToChange."""
        change = SyncToChange(
            calibre_id=1,
            calibre_title="Test Book",
            hardcover_book_id=100,
            user_book_id=200,
            field="status",
            old_value="Want to Read",
            new_value="Currently Reading",
        )
        assert change.user_book_id == 200
        assert change.field == "status"

    def test_sync_to_change_no_user_book(self):
        """Test SyncToChange when book not in Hardcover library."""
        change = SyncToChange(
            calibre_id=1,
            calibre_title="Test",
            hardcover_book_id=100,
            user_book_id=None,
            field="status",
            old_value=None,
            new_value="Currently Reading",
        )
        assert change.user_book_id is None

    def test_sync_to_change_display_field(self):
        """Test display_field property."""
        change = SyncToChange(
            calibre_id=1,
            calibre_title="Test",
            hardcover_book_id=100,
            user_book_id=200,
            field="rating",
            old_value="3",
            new_value="5",
        )
        assert change.display_field == "Rating"


class TestNewBookAction:
    """Tests for NewBookAction dataclass."""

    def test_create_new_book_action(self):
        """Test creating a NewBookAction."""
        user_book = UserBook(id=1, book_id=100, status_id=1)
        action = NewBookAction(
            hardcover_book_id=100,
            title="Test Book",
            authors=["Author One", "Author Two"],
            user_book=user_book,
            isbn="9780123456789",
        )
        assert action.title == "Test Book"
        assert action.apply is True

    def test_author_string(self):
        """Test author_string property."""
        user_book = UserBook(id=1, book_id=100, status_id=1)
        action = NewBookAction(
            hardcover_book_id=100,
            title="Test",
            authors=["Author One", "Author Two"],
            user_book=user_book,
        )
        assert action.author_string == "Author One, Author Two"

    def test_author_string_empty(self):
        """Test author_string with no authors."""
        user_book = UserBook(id=1, book_id=100, status_id=1)
        action = NewBookAction(
            hardcover_book_id=100,
            title="Test",
            authors=[],
            user_book=user_book,
        )
        assert action.author_string == "Unknown"


class TestFormatRatingAsStars:
    """Tests for format_rating_as_stars function."""

    def test_full_stars(self):
        """Test formatting full stars."""
        assert format_rating_as_stars(5.0) == "★★★★★"
        assert format_rating_as_stars(4.0) == "★★★★☆"
        assert format_rating_as_stars(3.0) == "★★★☆☆"
        assert format_rating_as_stars(2.0) == "★★☆☆☆"
        assert format_rating_as_stars(1.0) == "★☆☆☆☆"

    def test_half_stars(self):
        """Test formatting half stars."""
        assert format_rating_as_stars(4.5) == "★★★★½"
        assert format_rating_as_stars(3.5) == "★★★½☆"
        assert format_rating_as_stars(0.5) == "½☆☆☆☆"

    def test_zero_rating(self):
        """Test zero rating."""
        assert format_rating_as_stars(0.0) == "☆☆☆☆☆"

    def test_none_rating(self):
        """Test None rating."""
        assert format_rating_as_stars(None) == "(no rating)"


class TestConvertRatingToCalibre:
    """Tests for convert_rating_to_calibre function."""

    def test_builtin_rating_column(self):
        """Test conversion for built-in rating column."""
        raw, display = convert_rating_to_calibre(5.0, "rating")
        assert raw == "10"
        assert display == 5.0

        raw, display = convert_rating_to_calibre(3.5, "rating")
        assert raw == "7"
        assert display == 3.5

    def test_custom_rating_column(self):
        """Test conversion for custom rating column."""
        col_meta = {"datatype": "rating"}
        raw, display = convert_rating_to_calibre(4.0, "#myrating", col_meta)
        assert raw == "8"
        assert display == 4.0

    def test_custom_non_rating_column(self):
        """Test conversion for custom non-rating column."""
        col_meta = {"datatype": "int"}
        raw, display = convert_rating_to_calibre(4.0, "#mycolumn", col_meta)
        assert raw == "4.0"
        assert display == 4.0

    def test_custom_column_no_metadata(self):
        """Test custom column without metadata."""
        raw, display = convert_rating_to_calibre(4.0, "#mycolumn", None)
        assert raw == "4.0"

    def test_other_column(self):
        """Test other column types."""
        raw, display = convert_rating_to_calibre(4.0, "some_field")
        assert raw == "4.0"


class TestConvertRatingFromCalibre:
    """Tests for convert_rating_from_calibre function."""

    def test_builtin_rating_column(self):
        """Test conversion from built-in rating column."""
        assert convert_rating_from_calibre(10, "rating") == 5.0
        assert convert_rating_from_calibre(6, "rating") == 3.0

    def test_custom_rating_column(self):
        """Test conversion from custom rating column."""
        col_meta = {"datatype": "rating"}
        assert convert_rating_from_calibre(8, "#myrating", col_meta) == 4.0

    def test_custom_non_rating_column(self):
        """Test conversion from custom non-rating column."""
        col_meta = {"datatype": "int"}
        assert convert_rating_from_calibre(4, "#mycolumn", col_meta) == 4.0

    def test_none_rating(self):
        """Test conversion of None rating."""
        assert convert_rating_from_calibre(None, "rating") is None

    def test_invalid_rating(self):
        """Test conversion of invalid rating."""
        assert convert_rating_from_calibre("invalid", "rating") is None


class TestGetStatusFromHardcover:
    """Tests for get_status_from_hardcover function."""

    def test_mapped_status(self):
        """Test getting mapped status."""
        mappings = {"3": "Finished"}
        assert get_status_from_hardcover(3, mappings) == "Finished"

    def test_default_status(self):
        """Test getting default status when no mapping."""
        assert get_status_from_hardcover(1, {}) == "Want to Read"
        assert get_status_from_hardcover(2, {}) == "Currently Reading"
        assert get_status_from_hardcover(3, {}) == "Read"

    def test_unknown_status(self):
        """Test unknown status ID."""
        assert get_status_from_hardcover(99, {}) is None


class TestGetStatusFromCalibre:
    """Tests for get_status_from_calibre function."""

    def test_mapped_status(self):
        """Test getting mapped status."""
        mappings = {"3": "Finished"}
        assert get_status_from_calibre("Finished", mappings) == 3

    def test_default_status(self):
        """Test getting default status when no mapping."""
        assert get_status_from_calibre("Want to Read", {}) == 1
        assert get_status_from_calibre("Currently Reading", {}) == 2
        assert get_status_from_calibre("Read", {}) == 3

    def test_unknown_status(self):
        """Test unknown status value."""
        assert get_status_from_calibre("Unknown Status", {}) is None


class TestExtractDate:
    """Tests for extract_date function."""

    def test_iso_date(self):
        """Test extracting ISO date."""
        assert extract_date("2024-01-15") == "2024-01-15"

    def test_iso_datetime(self):
        """Test extracting date from ISO datetime."""
        assert extract_date("2024-01-15T10:30:00") == "2024-01-15"

    def test_space_datetime(self):
        """Test extracting date from space-separated datetime."""
        assert extract_date("2024-01-15 10:30:00") == "2024-01-15"

    def test_none(self):
        """Test None input."""
        assert extract_date(None) is None

    def test_empty_string(self):
        """Test empty string input."""
        assert extract_date("") is None


class TestFindSyncFromChanges:
    """Tests for find_sync_from_changes function."""

    def create_user_book(
        self,
        book_id: int,
        status_id: int = 3,
        rating: float = None,
        review: str = None,
    ) -> UserBook:
        """Helper to create a UserBook for testing."""
        return UserBook(
            id=1,
            book_id=book_id,
            status_id=status_id,
            rating=rating,
            review=review,
        )

    def test_status_change(self):
        """Test detecting status changes."""
        hc_books = [self.create_user_book(100, status_id=3)]
        hc_to_calibre = {100: 1}

        def get_value(calibre_id, col):
            return "Want to Read" if col == "status_col" else None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {"status_column": "status_col", "status_mappings": {}}

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "status"
        assert changes[0].old_value == "Want to Read"
        assert changes[0].new_value == "Read"

    def test_rating_change(self):
        """Test detecting rating changes."""
        hc_books = [self.create_user_book(100, rating=4.5)]
        hc_to_calibre = {100: 1}

        def get_value(calibre_id, col):
            return 6 if col == "rating" else None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "rating_column": "rating",
            "sync_rating": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "rating"
        assert "★★★★½" in changes[0].new_value

    def test_review_change(self):
        """Test detecting review changes."""
        hc_books = [self.create_user_book(100, review="Great book!")]
        hc_to_calibre = {100: 1}

        def get_value(calibre_id, col):
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "review_column": "comments",
            "sync_review": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "review"
        assert changes[0].new_value == "Great book!"

    def test_no_changes_when_synced(self):
        """Test no changes when already synced."""
        hc_books = [self.create_user_book(100, status_id=3)]
        hc_to_calibre = {100: 1}

        def get_value(calibre_id, col):
            return "Read"

        def get_title(calibre_id):
            return "Test Book"

        prefs = {"status_column": "status", "status_mappings": {}}

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 0

    def test_unlinked_book_skipped(self):
        """Test that unlinked books are skipped."""
        hc_books = [self.create_user_book(100, status_id=3)]
        hc_to_calibre = {}  # No mapping

        prefs = {"status_column": "status"}

        changes = find_sync_from_changes(
            hc_books, hc_to_calibre, lambda *a: None, lambda *a: "Test", prefs
        )

        assert len(changes) == 0


class TestFindNewBooks:
    """Tests for find_new_books function."""

    def create_user_book_with_book(
        self,
        book_id: int,
        status_id: int = 1,
        title: str = "Test Book",
        authors: list[str] = None,
        isbn: str = None,
    ) -> UserBook:
        """Helper to create a UserBook with Book metadata."""
        book_authors = (
            [Author(id=i, name=name) for i, name in enumerate(authors)] if authors else None
        )
        editions = [Edition(id=1, isbn_13=isbn)] if isbn else None
        book = Book(
            id=book_id,
            title=title,
            slug=title.lower().replace(" ", "-"),
            authors=book_authors,
            editions=editions,
        )
        return UserBook(
            id=1,
            book_id=book_id,
            status_id=status_id,
            book=book,
        )

    def test_find_new_book(self):
        """Test finding a new book."""
        hc_books = [
            self.create_user_book_with_book(
                100, title="New Book", authors=["John Doe"], isbn="9780123456789"
            )
        ]
        hc_to_calibre = {}

        new_books = find_new_books(hc_books, hc_to_calibre)

        assert len(new_books) == 1
        assert new_books[0].title == "New Book"
        assert new_books[0].authors == ["John Doe"]
        assert new_books[0].isbn == "9780123456789"

    def test_skip_linked_book(self):
        """Test that linked books are skipped."""
        hc_books = [self.create_user_book_with_book(100)]
        hc_to_calibre = {100: 1}  # Already linked

        new_books = find_new_books(hc_books, hc_to_calibre)

        assert len(new_books) == 0

    def test_skip_book_without_metadata(self):
        """Test that books without metadata are skipped."""
        hc_book = UserBook(id=1, book_id=100, status_id=1, book=None)
        hc_to_calibre = {}

        new_books = find_new_books([hc_book], hc_to_calibre)

        assert len(new_books) == 0

    def test_status_filter(self):
        """Test filtering by status."""
        hc_books = [
            self.create_user_book_with_book(100, status_id=1, title="Want to Read"),
            self.create_user_book_with_book(101, status_id=3, title="Read"),
        ]
        hc_to_calibre = {}

        # Only sync "Read" status
        new_books = find_new_books(hc_books, hc_to_calibre, sync_statuses=[3])

        assert len(new_books) == 1
        assert new_books[0].title == "Read"

    def test_empty_status_filter_includes_all(self):
        """Test that empty status filter includes all."""
        hc_books = [
            self.create_user_book_with_book(100, status_id=1),
            self.create_user_book_with_book(101, status_id=3),
        ]
        hc_to_calibre = {}

        new_books = find_new_books(hc_books, hc_to_calibre, sync_statuses=[])

        assert len(new_books) == 2
