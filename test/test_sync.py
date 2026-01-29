"""
Tests for the sync functionality.

These tests verify the sync logic without requiring Qt or Calibre.
"""


# =============================================================================
# Test SyncChange dataclass (sync from Hardcover)
# =============================================================================


class TestSyncChange:
    """Tests for the SyncChange dataclass."""

    def test_create_sync_change(self):
        """Test creating a SyncChange instance."""
        from hardcover_sync.dialogs.sync_from import SyncChange

        change = SyncChange(
            calibre_id=123,
            calibre_title="Test Book",
            hardcover_book_id=456,
            field="status",
            old_value="Want to Read",
            new_value="Read",
        )

        assert change.calibre_id == 123
        assert change.calibre_title == "Test Book"
        assert change.hardcover_book_id == 456
        assert change.field == "status"
        assert change.old_value == "Want to Read"
        assert change.new_value == "Read"
        assert change.apply is True  # Default

    def test_sync_change_apply_default(self):
        """Test that apply defaults to True."""
        from hardcover_sync.dialogs.sync_from import SyncChange

        change = SyncChange(
            calibre_id=1,
            calibre_title="Book",
            hardcover_book_id=2,
            field="rating",
            old_value="3",
            new_value="5",
        )

        assert change.apply is True

    def test_sync_change_apply_false(self):
        """Test creating with apply=False."""
        from hardcover_sync.dialogs.sync_from import SyncChange

        change = SyncChange(
            calibre_id=1,
            calibre_title="Book",
            hardcover_book_id=2,
            field="rating",
            old_value="3",
            new_value="5",
            apply=False,
        )

        assert change.apply is False

    def test_display_field_mapping(self):
        """Test the display_field property."""
        from hardcover_sync.dialogs.sync_from import SyncChange

        test_cases = [
            ("status", "Reading Status"),
            ("rating", "Rating"),
            ("progress", "Progress"),
            ("date_started", "Date Started"),
            ("date_read", "Date Read"),
            ("review", "Review"),
            ("unknown", "unknown"),  # Fallback to raw field name
        ]

        for field, expected_display in test_cases:
            change = SyncChange(
                calibre_id=1,
                calibre_title="Book",
                hardcover_book_id=2,
                field=field,
                old_value="old",
                new_value="new",
            )
            assert change.display_field == expected_display, f"Failed for field: {field}"

    def test_sync_change_with_none_values(self):
        """Test creating SyncChange with None values."""
        from hardcover_sync.dialogs.sync_from import SyncChange

        change = SyncChange(
            calibre_id=1,
            calibre_title="Book",
            hardcover_book_id=2,
            field="date_started",
            old_value=None,
            new_value="2024-01-15",
        )

        assert change.old_value is None
        assert change.new_value == "2024-01-15"


# =============================================================================
# Test SyncToChange dataclass (sync to Hardcover)
# =============================================================================


class TestSyncToChange:
    """Tests for the SyncToChange dataclass."""

    def test_create_sync_to_change(self):
        """Test creating a SyncToChange instance."""
        from hardcover_sync.dialogs.sync_to import SyncToChange

        change = SyncToChange(
            calibre_id=123,
            calibre_title="Test Book",
            hardcover_book_id=456,
            user_book_id=789,
            field="status",
            old_value="Want to Read",
            new_value="Read",
        )

        assert change.calibre_id == 123
        assert change.calibre_title == "Test Book"
        assert change.hardcover_book_id == 456
        assert change.user_book_id == 789
        assert change.field == "status"
        assert change.old_value == "Want to Read"
        assert change.new_value == "Read"
        assert change.apply is True

    def test_sync_to_change_no_user_book(self):
        """Test SyncToChange when book not yet in Hardcover library."""
        from hardcover_sync.dialogs.sync_to import SyncToChange

        change = SyncToChange(
            calibre_id=1,
            calibre_title="New Book",
            hardcover_book_id=100,
            user_book_id=None,  # Not in library yet
            field="status",
            old_value="(not in library)",
            new_value="Want to Read",
        )

        assert change.user_book_id is None

    def test_sync_to_change_display_field(self):
        """Test the display_field property for SyncToChange."""
        from hardcover_sync.dialogs.sync_to import SyncToChange

        test_cases = [
            ("status", "Reading Status"),
            ("rating", "Rating"),
            ("progress", "Progress"),
            ("date_started", "Date Started"),
            ("date_read", "Date Read"),
            ("review", "Review"),
        ]

        for field, expected_display in test_cases:
            change = SyncToChange(
                calibre_id=1,
                calibre_title="Book",
                hardcover_book_id=2,
                user_book_id=3,
                field=field,
                old_value="old",
                new_value="new",
            )
            assert change.display_field == expected_display


# =============================================================================
# Test sync field constants
# =============================================================================


class TestSyncFields:
    """Tests for sync-related constants and mappings."""

    def test_reading_statuses_used_in_sync(self):
        """Test that READING_STATUSES is available for sync."""
        from hardcover_sync.config import READING_STATUSES

        # Sync uses these statuses
        assert 1 in READING_STATUSES  # Want to Read
        assert 2 in READING_STATUSES  # Currently Reading
        assert 3 in READING_STATUSES  # Read
        assert 4 in READING_STATUSES  # Paused
        assert 5 in READING_STATUSES  # DNF
        assert 6 in READING_STATUSES  # Ignored

    def test_status_ids_reverse_mapping(self):
        """Test that STATUS_IDS provides reverse lookup."""
        from hardcover_sync.config import READING_STATUSES, STATUS_IDS

        for status_id, status_name in READING_STATUSES.items():
            assert STATUS_IDS[status_name] == status_id

    def test_sync_prefs_exist(self):
        """Test that sync-related preferences exist."""
        from hardcover_sync.config import DEFAULT_PREFS

        # Column mappings used by sync
        assert "status_column" in DEFAULT_PREFS
        assert "rating_column" in DEFAULT_PREFS
        assert "progress_column" in DEFAULT_PREFS
        assert "date_started_column" in DEFAULT_PREFS
        assert "date_read_column" in DEFAULT_PREFS
        assert "review_column" in DEFAULT_PREFS

        # Sync toggles
        assert "sync_rating" in DEFAULT_PREFS
        assert "sync_progress" in DEFAULT_PREFS
        assert "sync_dates" in DEFAULT_PREFS
        assert "sync_review" in DEFAULT_PREFS

        # Status mappings
        assert "status_mappings" in DEFAULT_PREFS
