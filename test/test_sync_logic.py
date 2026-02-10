"""
Tests for the sync module.

This tests the extracted business logic for syncing between Hardcover and Calibre.
"""

from hardcover_sync.models import Author, Book, Edition, UserBook
from hardcover_sync.sync import (
    NewBookAction,
    SyncChange,
    SyncToChange,
    SyncToResult,
    coerce_value_for_column,
    convert_rating_from_calibre,
    convert_rating_to_calibre,
    extract_date,
    find_new_books,
    find_sync_from_changes,
    find_sync_to_changes,
    format_rating_as_stars,
    get_status_from_calibre,
    get_status_from_hardcover,
    truncate_for_display,
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
        fields = [
            "status",
            "rating",
            "progress",
            "progress_percent",
            "date_started",
            "date_read",
            "review",
        ]
        expected = [
            "Reading Status",
            "Rating",
            "Progress (pages)",
            "Progress (%)",
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
        slug: str = "test-book",
    ) -> UserBook:
        """Helper to create a UserBook for testing."""
        return UserBook(
            id=1,
            book_id=book_id,
            status_id=status_id,
            rating=rating,
            review=review,
            book=Book(id=book_id, title="Test Book", slug=slug),
        )

    def test_status_change(self):
        """Test detecting status changes."""
        hc_books = [self.create_user_book(100, status_id=3)]
        hc_to_calibre = {"test-book": 1}

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
        hc_to_calibre = {"test-book": 1}

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
        hc_to_calibre = {"test-book": 1}

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
        hc_to_calibre = {"test-book": 1}

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
        hc_to_calibre = {"test-book": 1}  # Already linked

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

    def test_isbn_from_edition(self):
        """Test getting ISBN from user's specific edition."""
        book = Book(
            id=100,
            title="Test Book",
            slug="test-book",
            editions=[Edition(id=2, isbn_13="9781111111111")],  # Book edition
        )
        # User's specific edition with its own ISBN
        edition = Edition(id=1, isbn_13="9780123456789")
        hc_book = UserBook(
            id=1,
            book_id=100,
            status_id=1,
            book=book,
            edition=edition,
        )
        hc_to_calibre = {}

        new_books = find_new_books([hc_book], hc_to_calibre)

        assert len(new_books) == 1
        # Should use the user's edition ISBN, not the book's edition ISBN
        assert new_books[0].isbn == "9780123456789"

    def test_isbn_from_edition_isbn10(self):
        """Test getting ISBN-10 from user's edition when no ISBN-13."""
        book = Book(id=100, title="Test Book", slug="test-book")
        edition = Edition(id=1, isbn_10="0123456789")  # Only ISBN-10
        hc_book = UserBook(
            id=1,
            book_id=100,
            status_id=1,
            book=book,
            edition=edition,
        )
        hc_to_calibre = {}

        new_books = find_new_books([hc_book], hc_to_calibre)

        assert len(new_books) == 1
        assert new_books[0].isbn == "0123456789"

    def test_isbn_fallback_to_book_editions(self):
        """Test falling back to book editions when user edition has no ISBN."""
        book = Book(
            id=100,
            title="Test Book",
            slug="test-book",
            editions=[
                Edition(id=2, isbn_13="9781111111111"),
            ],
        )
        # User's edition has no ISBN
        edition = Edition(id=1, isbn_13=None, isbn_10=None)
        hc_book = UserBook(
            id=1,
            book_id=100,
            status_id=1,
            book=book,
            edition=edition,
        )
        hc_to_calibre = {}

        new_books = find_new_books([hc_book], hc_to_calibre)

        assert len(new_books) == 1
        # Should fall back to book edition ISBN
        assert new_books[0].isbn == "9781111111111"

    def test_isbn_fallback_to_book_editions_isbn10(self):
        """Test falling back to book edition ISBN-10."""
        book = Book(
            id=100,
            title="Test Book",
            slug="test-book",
            editions=[
                Edition(id=2, isbn_10="0987654321"),  # Only ISBN-10 available
            ],
        )
        hc_book = UserBook(
            id=1,
            book_id=100,
            status_id=1,
            book=book,
            edition=None,  # No user edition
        )
        hc_to_calibre = {}

        new_books = find_new_books([hc_book], hc_to_calibre)

        assert len(new_books) == 1
        assert new_books[0].isbn == "0987654321"


class TestFindSyncFromChangesProgress:
    """Tests for progress sync in find_sync_from_changes."""

    def create_user_book_with_reads(
        self,
        book_id: int,
        progress_pages: int = None,
        progress: float = None,
        started_at: str = None,
        finished_at: str = None,
        slug: str = "test-book",
    ) -> UserBook:
        """Helper to create a UserBook with reads for testing."""
        from hardcover_sync.models import UserBookRead

        reads = []
        if progress_pages is not None or progress is not None or started_at or finished_at:
            reads.append(
                UserBookRead(
                    id=1,
                    progress_pages=progress_pages,
                    progress=progress,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )

        return UserBook(
            id=1,
            book_id=book_id,
            status_id=2,  # Currently reading
            reads=reads if reads else None,
            book=Book(id=book_id, title="Test Book", slug=slug),
        )

    def test_progress_pages_change(self):
        """Test detecting progress pages changes."""
        hc_books = [self.create_user_book_with_reads(100, progress_pages=150)]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            if col == "progress_col":
                return "100"  # Current value differs from 150
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "progress_column": "progress_col",
            "sync_progress": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "progress"
        assert changes[0].old_value == "100"
        assert changes[0].new_value == "150"

    def test_progress_percent_change(self):
        """Test detecting progress percent changes."""
        hc_books = [self.create_user_book_with_reads(100, progress=0.75)]  # 75%
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            if col == "progress_pct_col":
                return 50.0  # Current is 50%, should change to 75%
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "progress_percent_column": "progress_pct_col",
            "sync_progress": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "progress_percent"
        assert "50.0%" in changes[0].old_value
        assert "75.0%" in changes[0].new_value

    def test_progress_percent_empty_to_value(self):
        """Test progress percent change from empty to value."""
        hc_books = [self.create_user_book_with_reads(100, progress=0.25)]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            return None  # No current value

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "progress_percent_column": "progress_pct_col",
            "sync_progress": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "progress_percent"
        assert changes[0].old_value == "(empty)"
        assert "25.0%" in changes[0].new_value


class TestFindSyncFromChangesDates:
    """Tests for date sync in find_sync_from_changes."""

    def create_user_book_with_reads(
        self,
        book_id: int,
        started_at: str = None,
        finished_at: str = None,
        slug: str = "test-book",
    ) -> UserBook:
        """Helper to create a UserBook with reads for testing."""
        from hardcover_sync.models import UserBookRead

        reads = []
        if started_at or finished_at:
            reads.append(
                UserBookRead(
                    id=1,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )

        return UserBook(
            id=1,
            book_id=book_id,
            status_id=3,
            reads=reads if reads else None,
            book=Book(id=book_id, title="Test Book", slug=slug),
        )

    def test_date_started_change(self):
        """Test detecting date started changes."""
        hc_books = [self.create_user_book_with_reads(100, started_at="2024-03-15T10:00:00")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            if col == "date_started_col":
                return "2024-01-01"  # Different date
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "date_started_column": "date_started_col",
            "sync_dates": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "date_started"
        assert changes[0].old_value == "2024-01-01"
        assert changes[0].new_value == "2024-03-15"

    def test_date_read_change(self):
        """Test detecting date read changes."""
        hc_books = [self.create_user_book_with_reads(100, finished_at="2024-06-20")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            if col == "date_read_col":
                return "2024-05-01"  # Different date
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "date_read_column": "date_read_col",
            "sync_dates": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "date_read"
        assert changes[0].old_value == "2024-05-01"
        assert changes[0].new_value == "2024-06-20"

    def test_date_started_empty_to_value(self):
        """Test date started change from empty to value."""
        hc_books = [self.create_user_book_with_reads(100, started_at="2024-03-15")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            return None  # No current value

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "date_started_column": "date_started_col",
            "sync_dates": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "date_started"
        assert changes[0].old_value == "(empty)"
        assert changes[0].new_value == "2024-03-15"

    def test_date_read_empty_to_value(self):
        """Test date read change from empty to value."""
        hc_books = [self.create_user_book_with_reads(100, finished_at="2024-06-20")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "date_read_column": "date_read_col",
            "sync_dates": True,
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        assert len(changes) == 1
        assert changes[0].field == "date_read"
        assert changes[0].old_value == "(empty)"
        assert changes[0].new_value == "2024-06-20"


class TestFindSyncFromChangesIsRead:
    """Tests for is_read boolean sync in find_sync_from_changes."""

    def create_user_book_with_reads(
        self,
        book_id: int,
        status_id: int = 3,
        started_at: str = None,
        finished_at: str = None,
        slug: str = "test-book",
    ) -> UserBook:
        """Helper to create a UserBook with reads for testing."""
        from hardcover_sync.models import UserBookRead

        reads = []
        if started_at or finished_at:
            reads.append(
                UserBookRead(
                    id=1,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )

        return UserBook(
            id=1,
            book_id=book_id,
            status_id=status_id,
            reads=reads if reads else None,
            book=Book(id=book_id, title="Test Book", slug=slug),
        )

    def test_is_read_true_when_status_is_read(self):
        """Test is_read becomes True when book status is 'Read' (status_id=3)."""
        hc_books = [self.create_user_book_with_reads(100, status_id=3)]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            if col == "is_read_col":
                return False  # Currently not marked as read
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "is_read_column": "is_read_col",
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        # Find the is_read change
        is_read_changes = [c for c in changes if c.field == "is_read"]
        assert len(is_read_changes) == 1
        assert is_read_changes[0].old_value == "No"
        assert is_read_changes[0].new_value == "Yes"

    def test_is_read_false_when_status_is_not_read(self):
        """Test is_read becomes False when book status is not 'Read'."""
        # Book with status "Currently Reading" (status_id=2)
        hc_books = [self.create_user_book_with_reads(100, status_id=2, started_at="2024-03-15")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            if col == "is_read_col":
                return True  # Currently marked as read (incorrectly)
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "is_read_column": "is_read_col",
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        is_read_changes = [c for c in changes if c.field == "is_read"]
        assert len(is_read_changes) == 1
        assert is_read_changes[0].old_value == "Yes"
        assert is_read_changes[0].new_value == "No"

    def test_is_read_no_change_when_already_correct(self):
        """Test no change when is_read already matches status."""
        hc_books = [self.create_user_book_with_reads(100, status_id=3, finished_at="2024-06-20")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            if col == "is_read_col":
                return True  # Already correctly marked as read
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "is_read_column": "is_read_col",
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        is_read_changes = [c for c in changes if c.field == "is_read"]
        assert len(is_read_changes) == 0

    def test_is_read_change_from_none_to_true(self):
        """Test is_read change when column is None (unset) and book status is Read."""
        hc_books = [self.create_user_book_with_reads(100, status_id=3, finished_at="2024-06-20")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            return None  # No current value

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "is_read_column": "is_read_col",
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        is_read_changes = [c for c in changes if c.field == "is_read"]
        assert len(is_read_changes) == 1
        assert is_read_changes[0].old_value == "No"
        assert is_read_changes[0].new_value == "Yes"

    def test_is_read_not_synced_when_column_not_configured(self):
        """Test is_read is not synced when column is not configured."""
        hc_books = [self.create_user_book_with_reads(100, status_id=3, finished_at="2024-06-20")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "is_read_column": "",  # Not configured
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        is_read_changes = [c for c in changes if c.field == "is_read"]
        assert len(is_read_changes) == 0

    def test_is_read_synced_even_when_sync_dates_disabled(self):
        """Test is_read is synced regardless of sync_dates setting (it's status-based, not date-based)."""
        hc_books = [self.create_user_book_with_reads(100, status_id=3, finished_at="2024-06-20")]
        hc_to_calibre = {"test-book": 1}

        def get_value(calibre_id, col):
            if col == "is_read_col":
                return False
            return None

        def get_title(calibre_id):
            return "Test Book"

        prefs = {
            "status_column": "",
            "is_read_column": "is_read_col",
            "sync_dates": False,  # Disabled, but is_read should still sync
        }

        changes = find_sync_from_changes(hc_books, hc_to_calibre, get_value, get_title, prefs)

        is_read_changes = [c for c in changes if c.field == "is_read"]
        assert len(is_read_changes) == 1
        assert is_read_changes[0].new_value == "Yes"


class TestConvertRatingFromCalibreOtherColumn:
    """Test rating conversion for non-standard column names."""

    def test_other_column_type(self):
        """Test rating conversion for columns that aren't built-in or custom."""
        # This covers line 181 - the else branch for non-standard column names
        result = convert_rating_from_calibre(4.0, "my_custom_field")
        assert result == 4.0


class TestCoerceValueForColumn:
    """Tests for coerce_value_for_column function."""

    # --- None / empty handling ---

    def test_none_returns_none(self):
        """None input returns None for any datatype."""
        assert coerce_value_for_column(None, "bool") is None
        assert coerce_value_for_column(None, "int") is None
        assert coerce_value_for_column(None, "float") is None
        assert coerce_value_for_column(None, "datetime") is None
        assert coerce_value_for_column(None, "rating") is None
        assert coerce_value_for_column(None, "text") is None

    def test_empty_string_returns_none(self):
        """Empty string returns None for any datatype."""
        assert coerce_value_for_column("", "bool") is None
        assert coerce_value_for_column("", "int") is None
        assert coerce_value_for_column("", "float") is None
        assert coerce_value_for_column("", "datetime") is None
        assert coerce_value_for_column("", "rating") is None
        assert coerce_value_for_column("", "text") is None

    # --- Bool coercion ---

    def test_bool_yes_string(self):
        """String 'Yes' coerces to True."""
        assert coerce_value_for_column("Yes", "bool") is True

    def test_bool_no_string(self):
        """String 'No' coerces to False."""
        assert coerce_value_for_column("No", "bool") is False

    def test_bool_true_string(self):
        """String 'true' coerces to True."""
        assert coerce_value_for_column("true", "bool") is True

    def test_bool_false_string(self):
        """String 'false' coerces to False."""
        assert coerce_value_for_column("false", "bool") is False

    def test_bool_one_string(self):
        """String '1' coerces to True."""
        assert coerce_value_for_column("1", "bool") is True

    def test_bool_zero_string(self):
        """String '0' coerces to False."""
        assert coerce_value_for_column("0", "bool") is False

    def test_bool_case_insensitive(self):
        """Bool coercion is case-insensitive."""
        assert coerce_value_for_column("YES", "bool") is True
        assert coerce_value_for_column("True", "bool") is True
        assert coerce_value_for_column("TRUE", "bool") is True

    def test_bool_true_passthrough(self):
        """Actual True bool passes through unchanged."""
        assert coerce_value_for_column(True, "bool") is True

    def test_bool_false_passthrough(self):
        """Actual False bool passes through unchanged."""
        assert coerce_value_for_column(False, "bool") is False

    # --- Int coercion ---

    def test_int_string(self):
        """String '42' coerces to int 42."""
        assert coerce_value_for_column("42", "int") == 42

    def test_int_zero_string(self):
        """String '0' coerces to int 0."""
        assert coerce_value_for_column("0", "int") == 0

    # --- Float coercion ---

    def test_float_string(self):
        """String '3.14' coerces to float."""
        assert coerce_value_for_column("3.14", "float") == 3.14

    def test_float_integer_string(self):
        """String '5' coerces to float 5.0."""
        assert coerce_value_for_column("5", "float") == 5.0

    # --- Datetime coercion ---

    def test_datetime_iso_string(self):
        """ISO date string coerces to datetime."""
        from datetime import datetime

        result = coerce_value_for_column("2024-06-20", "datetime")
        assert result == datetime(2024, 6, 20)

    def test_datetime_iso_with_time(self):
        """ISO datetime string with time coerces correctly."""
        from datetime import datetime

        result = coerce_value_for_column("2024-06-20T14:30:00", "datetime")
        assert result == datetime(2024, 6, 20, 14, 30, 0)

    # --- Rating coercion ---

    def test_rating_string(self):
        """String '8' coerces to int 8."""
        assert coerce_value_for_column("8", "rating") == 8

    def test_rating_float_string(self):
        """String '7.5' coerces to int 7 (truncated, not rounded)."""
        assert coerce_value_for_column("7.5", "rating") == 7

    # --- Text passthrough ---

    def test_text_passthrough(self):
        """Text values pass through unchanged."""
        assert coerce_value_for_column("hello world", "text") == "hello world"

    def test_comments_passthrough(self):
        """Comments values pass through unchanged."""
        assert coerce_value_for_column("<p>review</p>", "comments") == "<p>review</p>"

    def test_unknown_datatype_passthrough(self):
        """Unknown datatype passes through unchanged."""
        assert coerce_value_for_column("something", "enumeration") == "something"

    # --- Bool coercion for non-string, non-bool ---

    def test_bool_int_truthy(self):
        """Integer 1 coerces to True via bool()."""
        assert coerce_value_for_column(1, "bool") is True

    def test_bool_int_falsy(self):
        """Integer 0 coerces to False via bool()."""
        assert coerce_value_for_column(0, "bool") is False

    def test_bool_nonempty_list(self):
        """Non-empty list coerces to True via bool()."""
        assert coerce_value_for_column([1], "bool") is True

    def test_bool_empty_list(self):
        """Empty list coerces to False via bool()."""
        assert coerce_value_for_column([], "bool") is False


class TestTruncateForDisplay:
    """Tests for truncate_for_display function."""

    def test_none_returns_empty_placeholder(self):
        """None text returns the empty placeholder."""
        assert truncate_for_display(None) == "(empty)"

    def test_empty_string_returns_empty_placeholder(self):
        """Empty string returns the empty placeholder."""
        assert truncate_for_display("") == "(empty)"

    def test_short_text_unchanged(self):
        """Text shorter than max_length is returned unchanged."""
        assert truncate_for_display("Hello world") == "Hello world"

    def test_text_at_max_length(self):
        """Text exactly at max_length is returned unchanged."""
        text = "x" * 50
        assert truncate_for_display(text) == text

    def test_text_over_max_length_truncated(self):
        """Text longer than max_length is truncated with ellipsis."""
        text = "x" * 60
        result = truncate_for_display(text)
        assert result == "x" * 50 + "..."
        assert len(result) == 53

    def test_custom_max_length(self):
        """Custom max_length works."""
        assert truncate_for_display("Hello world", max_length=5) == "Hello..."

    def test_custom_empty_placeholder(self):
        """Custom empty placeholder works."""
        assert truncate_for_display(None, empty="N/A") == "N/A"
        assert truncate_for_display("", empty="--") == "--"


class TestSyncToResult:
    """Tests for SyncToResult dataclass."""

    def test_default_values(self):
        """Test that SyncToResult initializes with correct defaults."""
        result = SyncToResult()
        assert result.changes == []
        assert result.hardcover_data == {}
        assert result.linked_count == 0
        assert result.not_linked_count == 0
        assert result.api_errors == 0
        assert result.books_with_changes == 0

    def test_mutable_defaults_are_independent(self):
        """Test that mutable defaults are independent between instances."""
        r1 = SyncToResult()
        r2 = SyncToResult()
        r1.changes.append("test")
        assert len(r2.changes) == 0

    def test_accumulation(self):
        """Test accumulating stats."""
        result = SyncToResult()
        result.linked_count += 3
        result.not_linked_count += 2
        result.api_errors += 1
        result.books_with_changes += 2
        assert result.linked_count == 3
        assert result.not_linked_count == 2
        assert result.api_errors == 1
        assert result.books_with_changes == 2


class TestFindSyncToChanges:
    """Tests for find_sync_to_changes function."""

    def _make_user_book(
        self,
        book_id: int = 100,
        status_id: int = 3,
        rating: float = None,
        review: str = None,
        progress_pages: int = None,
        progress: float = None,
        started_at: str = None,
        finished_at: str = None,
    ) -> UserBook:
        """Helper to create a UserBook with optional reads."""
        from hardcover_sync.models import UserBookRead

        reads = []
        if progress_pages is not None or progress is not None or started_at or finished_at:
            reads.append(
                UserBookRead(
                    id=1,
                    progress_pages=progress_pages,
                    progress=progress,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )

        return UserBook(
            id=1,
            book_id=book_id,
            status_id=status_id,
            rating=rating,
            review=review,
            reads=reads if reads else None,
            book=Book(id=book_id, title="Test Book", slug="test-book"),
        )

    def _make_book(self, book_id: int = 100) -> Book:
        """Helper to create a simple Book."""
        return Book(id=book_id, title="Test Book", slug="test-book")

    def _call(
        self,
        book_ids=None,
        identifiers=None,
        calibre_values=None,
        calibre_titles=None,
        resolved_books=None,
        user_books=None,
        prefs=None,
        column_metadata=None,
        on_progress=None,
    ):
        """Helper to call find_sync_to_changes with sensible defaults."""
        if book_ids is None:
            book_ids = [1]
        if identifiers is None:
            identifiers = {1: {"hardcover": "100"}}
        if calibre_values is None:
            calibre_values = {}
        if calibre_titles is None:
            calibre_titles = {1: "Test Book"}
        if resolved_books is None:
            resolved_books = {"100": self._make_book()}
        if user_books is None:
            user_books = {}
        if prefs is None:
            prefs = {"status_column": "", "status_mappings": {}}

        def get_identifiers(bid):
            return identifiers.get(bid, {})

        def get_calibre_value(bid, col):
            return calibre_values.get((bid, col))

        def get_calibre_title(bid):
            return calibre_titles.get(bid, "Unknown")

        def resolve_book(slug_or_id):
            return resolved_books.get(slug_or_id)

        def get_user_book(hc_book_id):
            return user_books.get(hc_book_id)

        def get_column_metadata_fn(col):
            if column_metadata:
                return column_metadata.get(col)
            return None

        return find_sync_to_changes(
            book_ids=book_ids,
            get_identifiers=get_identifiers,
            get_calibre_value=get_calibre_value,
            get_calibre_title=get_calibre_title,
            resolve_book=resolve_book,
            get_user_book=get_user_book,
            prefs=prefs,
            get_column_metadata=get_column_metadata_fn,
            on_progress=on_progress,
        )

    # --- Book linking tests ---

    def test_not_linked_book_skipped(self):
        """Books without hardcover identifier are skipped."""
        result = self._call(
            book_ids=[1],
            identifiers={1: {}},  # no hardcover key
        )
        assert result.not_linked_count == 1
        assert result.linked_count == 0
        assert len(result.changes) == 0

    def test_unresolved_book_skipped(self):
        """Books that can't be resolved on Hardcover are skipped."""
        result = self._call(
            book_ids=[1],
            identifiers={1: {"hardcover": "999"}},
            resolved_books={},  # nothing resolves
        )
        assert result.not_linked_count == 1
        assert result.linked_count == 0

    def test_linked_book_counted(self):
        """Linked books increment linked_count."""
        result = self._call(
            user_books={100: self._make_user_book()},
        )
        assert result.linked_count == 1
        assert result.not_linked_count == 0

    # --- Status change tests ---

    def test_status_change_detected(self):
        """Detects status difference between Calibre and Hardcover."""
        hc_user_book = self._make_user_book(status_id=1)  # Want to Read on HC
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): "Currently Reading"},
            user_books={100: hc_user_book},
        )
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 1
        assert status_changes[0].new_value == "Currently Reading"
        assert status_changes[0].old_value == "Want to Read"

    def test_status_no_change_when_equal(self):
        """No change when Calibre status matches Hardcover."""
        hc_user_book = self._make_user_book(status_id=3)  # Read
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): "Read"},
            user_books={100: hc_user_book},
        )
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 0

    def test_status_empty_calibre_value_skipped(self):
        """No status change when Calibre column is empty."""
        hc_user_book = self._make_user_book(status_id=3)
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): None},
            user_books={100: hc_user_book},
        )
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 0

    def test_status_with_custom_mapping(self):
        """Status change uses custom status mappings."""
        hc_user_book = self._make_user_book(status_id=1)  # Want to Read on HC
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {"3": "Finished"},
            },
            calibre_values={(1, "#status"): "Finished"},  # maps to status_id 3
            user_books={100: hc_user_book},
        )
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 1
        assert status_changes[0].new_value == "Finished"

    def test_status_not_in_library_old_value(self):
        """When no user_book on HC, old_value shows '(not in library)'."""
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): "Currently Reading"},
            user_books={},  # no user_book
        )
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 1
        assert status_changes[0].old_value == "(not in library)"

    # --- Rating change tests ---

    def test_rating_change_detected(self):
        """Detects rating difference."""
        hc_user_book = self._make_user_book(rating=3.0)
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "rating_column": "rating",
            },
            calibre_values={(1, "rating"): 10},  # 10/10 = 5.0 on HC scale
            user_books={100: hc_user_book},
        )
        rating_changes = [c for c in result.changes if c.field == "rating"]
        assert len(rating_changes) == 1
        assert rating_changes[0].api_value == 5.0

    def test_rating_no_change_when_equal(self):
        """No change when ratings match."""
        hc_user_book = self._make_user_book(rating=5.0)
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "rating_column": "rating",
            },
            calibre_values={(1, "rating"): 10},  # 10/10 = 5.0
            user_books={100: hc_user_book},
        )
        rating_changes = [c for c in result.changes if c.field == "rating"]
        assert len(rating_changes) == 0

    def test_rating_none_calibre_skipped(self):
        """No rating change when Calibre value is None."""
        hc_user_book = self._make_user_book(rating=4.0)
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "rating_column": "rating",
            },
            calibre_values={(1, "rating"): None},
            user_books={100: hc_user_book},
        )
        rating_changes = [c for c in result.changes if c.field == "rating"]
        assert len(rating_changes) == 0

    def test_rating_no_user_book_shows_none(self):
        """Rating when no HC user_book uses None as current."""
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "rating_column": "rating",
            },
            calibre_values={(1, "rating"): 8},  # 4.0 on HC scale
            user_books={},
        )
        rating_changes = [c for c in result.changes if c.field == "rating"]
        assert len(rating_changes) == 1
        assert rating_changes[0].api_value == 4.0

    # --- Progress (pages) tests ---

    def test_progress_pages_change_detected(self):
        """Detects progress pages difference."""
        hc_user_book = self._make_user_book(progress_pages=100)
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "progress_column": "#pages",
            },
            calibre_values={(1, "#pages"): 200},
            user_books={100: hc_user_book},
        )
        progress_changes = [c for c in result.changes if c.field == "progress"]
        assert len(progress_changes) == 1
        assert progress_changes[0].new_value == "200"
        assert progress_changes[0].old_value == "100"

    def test_progress_pages_no_change(self):
        """No change when progress pages match."""
        hc_user_book = self._make_user_book(progress_pages=150)
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "progress_column": "#pages",
            },
            calibre_values={(1, "#pages"): 150},
            user_books={100: hc_user_book},
        )
        progress_changes = [c for c in result.changes if c.field == "progress"]
        assert len(progress_changes) == 0

    def test_progress_pages_empty_old_value(self):
        """Old value shows '(empty)' when no HC progress."""
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "progress_column": "#pages",
            },
            calibre_values={(1, "#pages"): 50},
            user_books={},
        )
        progress_changes = [c for c in result.changes if c.field == "progress"]
        assert len(progress_changes) == 1
        assert progress_changes[0].old_value == "(empty)"

    # --- Progress percent tests ---

    def test_progress_percent_change_detected(self):
        """Detects progress percent difference."""
        hc_user_book = self._make_user_book(progress=0.50)  # 50%
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "progress_percent_column": "#pct",
            },
            calibre_values={(1, "#pct"): 75.0},
            user_books={100: hc_user_book},
        )
        pct_changes = [c for c in result.changes if c.field == "progress_percent"]
        assert len(pct_changes) == 1
        assert "75.0%" in pct_changes[0].new_value
        assert pct_changes[0].api_value == 0.75  # converted to 0-1 for API

    def test_progress_percent_no_change_when_equal(self):
        """No change when progress percent matches (after rounding)."""
        hc_user_book = self._make_user_book(progress=0.50)  # 50%
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "progress_percent_column": "#pct",
            },
            calibre_values={(1, "#pct"): 50.0},
            user_books={100: hc_user_book},
        )
        pct_changes = [c for c in result.changes if c.field == "progress_percent"]
        assert len(pct_changes) == 0

    def test_progress_percent_empty_old_value(self):
        """Old value shows '(empty)' when no HC progress percent."""
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "progress_percent_column": "#pct",
            },
            calibre_values={(1, "#pct"): 25.0},
            user_books={},
        )
        pct_changes = [c for c in result.changes if c.field == "progress_percent"]
        assert len(pct_changes) == 1
        assert pct_changes[0].old_value == "(empty)"

    # --- Date started tests ---

    def test_date_started_change_detected(self):
        """Detects date started difference."""
        hc_user_book = self._make_user_book(started_at="2024-01-15T10:00:00")
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "date_started_column": "#started",
            },
            calibre_values={(1, "#started"): "2024-06-01"},
            user_books={100: hc_user_book},
        )
        date_changes = [c for c in result.changes if c.field == "date_started"]
        assert len(date_changes) == 1
        assert date_changes[0].new_value == "2024-06-01"
        assert date_changes[0].old_value == "2024-01-15"

    def test_date_started_empty_old_value(self):
        """Old value shows '(empty)' when no HC start date."""
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "date_started_column": "#started",
            },
            calibre_values={(1, "#started"): "2024-03-01"},
            user_books={},
        )
        date_changes = [c for c in result.changes if c.field == "date_started"]
        assert len(date_changes) == 1
        assert date_changes[0].old_value == "(empty)"

    def test_date_started_no_change_when_equal(self):
        """No change when dates match."""
        hc_user_book = self._make_user_book(started_at="2024-03-15")
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "date_started_column": "#started",
            },
            calibre_values={(1, "#started"): "2024-03-15"},
            user_books={100: hc_user_book},
        )
        date_changes = [c for c in result.changes if c.field == "date_started"]
        assert len(date_changes) == 0

    # --- Date read tests ---

    def test_date_read_change_detected(self):
        """Detects date read difference."""
        hc_user_book = self._make_user_book(finished_at="2024-06-20")
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "date_read_column": "#finished",
            },
            calibre_values={(1, "#finished"): "2024-05-01"},
            user_books={100: hc_user_book},
        )
        date_changes = [c for c in result.changes if c.field == "date_read"]
        assert len(date_changes) == 1
        assert date_changes[0].new_value == "2024-05-01"
        assert date_changes[0].old_value == "2024-06-20"

    def test_date_read_empty_old_value(self):
        """Old value shows '(empty)' when no HC finish date."""
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "date_read_column": "#finished",
            },
            calibre_values={(1, "#finished"): "2024-06-20"},
            user_books={},
        )
        date_changes = [c for c in result.changes if c.field == "date_read"]
        assert len(date_changes) == 1
        assert date_changes[0].old_value == "(empty)"

    # --- Review tests ---

    def test_review_change_detected(self):
        """Detects review difference."""
        hc_user_book = self._make_user_book(review="Old review")
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "review_column": "#review",
            },
            calibre_values={(1, "#review"): "New review"},
            user_books={100: hc_user_book},
        )
        review_changes = [c for c in result.changes if c.field == "review"]
        assert len(review_changes) == 1

    def test_review_no_change_when_equal(self):
        """No change when reviews match."""
        hc_user_book = self._make_user_book(review="Same review")
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "review_column": "#review",
            },
            calibre_values={(1, "#review"): "Same review"},
            user_books={100: hc_user_book},
        )
        review_changes = [c for c in result.changes if c.field == "review"]
        assert len(review_changes) == 0

    def test_review_empty_calibre_skipped(self):
        """No review change when Calibre has no review."""
        hc_user_book = self._make_user_book(review="HC review")
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "review_column": "#review",
            },
            calibre_values={(1, "#review"): None},
            user_books={100: hc_user_book},
        )
        review_changes = [c for c in result.changes if c.field == "review"]
        assert len(review_changes) == 0

    # --- Multiple books and fields ---

    def test_multiple_books(self):
        """Process multiple books correctly."""
        hc_book_a = self._make_user_book(book_id=100, status_id=1)
        hc_book_b = self._make_user_book(book_id=200, status_id=2)

        result = self._call(
            book_ids=[1, 2],
            identifiers={
                1: {"hardcover": "100"},
                2: {"hardcover": "200"},
            },
            resolved_books={
                "100": Book(id=100, title="Book A", slug="book-a"),
                "200": Book(id=200, title="Book B", slug="book-b"),
            },
            calibre_titles={1: "Book A", 2: "Book B"},
            calibre_values={
                (1, "#status"): "Read",
                (2, "#status"): "Read",
            },
            user_books={100: hc_book_a, 200: hc_book_b},
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
        )
        assert result.linked_count == 2
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 2

    def test_books_with_changes_count(self):
        """books_with_changes counts unique books, not total changes."""
        hc_user_book = self._make_user_book(status_id=1, rating=2.0)
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
                "rating_column": "rating",
            },
            calibre_values={
                (1, "#status"): "Read",
                (1, "rating"): 10,  # 5.0 != 2.0
            },
            user_books={100: hc_user_book},
        )
        assert result.books_with_changes == 1
        assert len(result.changes) == 2

    def test_no_changes_no_book_count(self):
        """books_with_changes is 0 when no changes detected."""
        hc_user_book = self._make_user_book(status_id=3)
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): "Read"},
            user_books={100: hc_user_book},
        )
        assert result.books_with_changes == 0
        assert len(result.changes) == 0

    def test_api_error_during_user_book_fetch(self):
        """API errors during get_user_book are counted."""

        def failing_get_user_book(hc_book_id):
            raise RuntimeError("API timeout")

        result = find_sync_to_changes(
            book_ids=[1],
            get_identifiers=lambda bid: {"hardcover": "100"},
            get_calibre_value=lambda bid, col: None,
            get_calibre_title=lambda bid: "Test",
            resolve_book=lambda s: self._make_book(),
            get_user_book=failing_get_user_book,
            prefs={"status_column": "", "status_mappings": {}},
        )
        assert result.api_errors == 1
        assert result.linked_count == 1

    def test_on_progress_callback(self):
        """on_progress callback is called for each book."""
        progress_calls = []
        self._call(
            book_ids=[1, 2, 3],
            identifiers={
                1: {"hardcover": "100"},
                2: {},
                3: {"hardcover": "300"},
            },
            resolved_books={
                "100": self._make_book(100),
                "300": Book(id=300, title="Book C", slug="book-c"),
            },
            on_progress=lambda i: progress_calls.append(i),
        )
        assert progress_calls == [1, 2, 3]

    def test_hardcover_data_stored(self):
        """User book data is stored in result.hardcover_data."""
        hc_user_book = self._make_user_book()
        result = self._call(
            user_books={100: hc_user_book},
        )
        assert 100 in result.hardcover_data
        assert result.hardcover_data[100] == hc_user_book

    def test_status_column_not_configured_skips_status(self):
        """When status_column is empty, status comparison is skipped."""
        hc_user_book = self._make_user_book(status_id=1)
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): "Read"},
            user_books={100: hc_user_book},
        )
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 0

    def test_status_direct_match_fallback(self):
        """Status uses STATUS_IDS direct match when custom mapping fails."""
        hc_user_book = self._make_user_book(status_id=1)  # Want to Read
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},  # no custom mappings
            },
            # "Read" maps to status_id 3 via STATUS_IDS
            calibre_values={(1, "#status"): "Read"},
            user_books={100: hc_user_book},
        )
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 1

    def test_unmapped_calibre_status_skipped(self):
        """Status with unknown Calibre value that doesn't map is skipped."""
        hc_user_book = self._make_user_book(status_id=3)
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): "Totally Unknown Status"},
            user_books={100: hc_user_book},
        )
        # The Calibre value "Totally Unknown Status" doesn't map to any HC status
        # so no status change is produced
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 0

    def test_rating_column_with_custom_metadata(self):
        """Rating uses column metadata for conversion."""
        hc_user_book = self._make_user_book(rating=3.0)
        result = self._call(
            prefs={
                "status_column": "",
                "status_mappings": {},
                "rating_column": "#myrating",
            },
            calibre_values={(1, "#myrating"): 8},  # custom rating column
            user_books={100: hc_user_book},
            column_metadata={"#myrating": {"datatype": "rating"}},
        )
        rating_changes = [c for c in result.changes if c.field == "rating"]
        assert len(rating_changes) == 1
        assert rating_changes[0].api_value == 4.0  # 8/2 = 4.0

    def test_sync_to_change_has_user_book_id(self):
        """SyncToChange includes the user_book_id from HC."""
        hc_user_book = self._make_user_book(status_id=1)
        hc_user_book.id = 42
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): "Read"},
            user_books={100: hc_user_book},
        )
        assert len(result.changes) >= 1
        assert result.changes[0].user_book_id == 42

    def test_no_user_book_yields_none_user_book_id(self):
        """SyncToChange has user_book_id=None when book not in HC library."""
        result = self._call(
            prefs={
                "status_column": "#status",
                "status_mappings": {},
            },
            calibre_values={(1, "#status"): "Read"},
            user_books={},  # no user book on HC
        )
        status_changes = [c for c in result.changes if c.field == "status"]
        assert len(status_changes) == 1
        assert status_changes[0].user_book_id is None
