"""
Tests for the configuration module.

These tests verify the configuration defaults and helper functions
without requiring Qt or Calibre.
"""


# =============================================================================
# Test READING_STATUSES and STATUS_IDS
# =============================================================================


class TestReadingStatuses:
    """Tests for reading status constants."""

    def test_reading_statuses_contains_all_ids(self):
        """Test that all 6 Hardcover statuses are defined."""
        from hardcover_sync.config import READING_STATUSES

        assert len(READING_STATUSES) == 6
        assert 1 in READING_STATUSES
        assert 2 in READING_STATUSES
        assert 3 in READING_STATUSES
        assert 4 in READING_STATUSES
        assert 5 in READING_STATUSES
        assert 6 in READING_STATUSES

    def test_reading_statuses_values(self):
        """Test that status names are correct."""
        from hardcover_sync.config import READING_STATUSES

        assert READING_STATUSES[1] == "Want to Read"
        assert READING_STATUSES[2] == "Currently Reading"
        assert READING_STATUSES[3] == "Read"
        assert READING_STATUSES[4] == "Paused"
        assert READING_STATUSES[5] == "Did Not Finish"
        assert READING_STATUSES[6] == "Ignored"

    def test_status_ids_reverse_mapping(self):
        """Test that STATUS_IDS is the reverse of READING_STATUSES."""
        from hardcover_sync.config import READING_STATUSES, STATUS_IDS

        for status_id, status_name in READING_STATUSES.items():
            assert STATUS_IDS[status_name] == status_id


class TestStatusMappingConflicts:
    """Tests for ambiguous status mapping detection."""

    def test_no_conflicts_with_defaults(self):
        from hardcover_sync.config import get_status_mapping_conflicts

        assert get_status_mapping_conflicts({}) == {}

    def test_duplicate_custom_value(self):
        from hardcover_sync.config import get_status_mapping_conflicts

        assert get_status_mapping_conflicts({"1": "Done", "3": "Done"}) == {"Done": [1, 3]}

    def test_custom_value_colliding_with_default(self):
        from hardcover_sync.config import get_status_mapping_conflicts

        assert get_status_mapping_conflicts({"1": "Read"}) == {"Read": [1, 3]}


# =============================================================================
# Test DEFAULT_PREFS
# =============================================================================


class TestDefaultPrefs:
    """Tests for default preferences."""

    def test_default_prefs_has_auth_fields(self):
        """Test that auth fields have defaults."""
        from hardcover_sync.config import DEFAULT_PREFS

        assert "api_token" in DEFAULT_PREFS
        assert "username" in DEFAULT_PREFS
        assert "user_id" in DEFAULT_PREFS
        assert DEFAULT_PREFS["api_token"] == ""
        assert DEFAULT_PREFS["username"] == ""
        assert DEFAULT_PREFS["user_id"] is None

    def test_default_prefs_has_column_mappings(self):
        """Test that column mapping fields have defaults."""
        from hardcover_sync.config import DEFAULT_PREFS

        column_keys = [
            "status_column",
            "rating_column",
            "progress_column",
            "date_started_column",
            "date_read_column",
            "review_column",
        ]
        for key in column_keys:
            assert key in DEFAULT_PREFS
            assert DEFAULT_PREFS[key] == ""

    def test_default_prefs_has_sync_options(self):
        """Test that sync option fields have defaults."""
        from hardcover_sync.config import DEFAULT_PREFS

        sync_keys = [
            "sync_rating",
            "sync_progress",
            "sync_dates",
            "sync_review",
        ]
        for key in sync_keys:
            assert key in DEFAULT_PREFS
            assert DEFAULT_PREFS[key] is True  # All enabled by default

    def test_default_prefs_status_mappings(self):
        """Test that status_mappings defaults to empty dict."""
        from hardcover_sync.config import DEFAULT_PREFS

        assert "status_mappings" in DEFAULT_PREFS
        assert DEFAULT_PREFS["status_mappings"] == {}

    def test_default_prefs_lab_features(self):
        """Test that Lab feature flags have defaults."""
        from hardcover_sync.config import DEFAULT_PREFS

        assert "enable_lab_update_progress" in DEFAULT_PREFS
        assert DEFAULT_PREFS["enable_lab_update_progress"] is False
        assert "enable_lab_lists" in DEFAULT_PREFS
        assert DEFAULT_PREFS["enable_lab_lists"] is False


# =============================================================================
# Test get_plugin_prefs
# =============================================================================


class TestGetPluginPrefs:
    """Tests for the get_plugin_prefs function."""

    def test_get_plugin_prefs_returns_prefs(self):
        """Test that get_plugin_prefs returns the prefs object."""
        from hardcover_sync.config import get_plugin_prefs, prefs

        result = get_plugin_prefs()
        assert result is prefs

    def test_prefs_has_defaults(self):
        """Test that prefs object has defaults set."""
        from hardcover_sync.config import DEFAULT_PREFS, prefs

        assert prefs.defaults == DEFAULT_PREFS


# =============================================================================
# Test SYNCABLE_COLUMNS and get_unmapped_columns
# =============================================================================


class TestSyncableColumns:
    """Tests for syncable column constants and utilities."""

    def test_syncable_columns_defined(self):
        """Test that SYNCABLE_COLUMNS is defined with expected entries."""
        from hardcover_sync.config import SYNCABLE_COLUMNS

        assert len(SYNCABLE_COLUMNS) == 8
        pref_keys = [col[0] for col in SYNCABLE_COLUMNS]
        assert "status_column" in pref_keys
        assert "rating_column" in pref_keys
        assert "progress_column" in pref_keys
        assert "progress_percent_column" in pref_keys
        assert "date_started_column" in pref_keys
        assert "date_read_column" in pref_keys
        assert "is_read_column" in pref_keys
        assert "review_column" in pref_keys

    def test_get_unmapped_columns_all_unmapped(self):
        """Test get_unmapped_columns when no columns are mapped."""
        from hardcover_sync.config import get_unmapped_columns

        # Empty prefs means all unmapped
        prefs = {}
        unmapped = get_unmapped_columns(prefs)
        assert len(unmapped) == 8
        assert "Status" in unmapped
        assert "Rating" in unmapped

    def test_get_unmapped_columns_some_mapped(self):
        """Test get_unmapped_columns when some columns are mapped."""
        from hardcover_sync.config import get_unmapped_columns

        prefs = {"status_column": "#hc_status", "rating_column": "rating"}
        unmapped = get_unmapped_columns(prefs)
        assert len(unmapped) == 6
        assert "Status" not in unmapped
        assert "Rating" not in unmapped
        assert "Progress (pages)" in unmapped
        assert "Progress (%)" in unmapped

    def test_get_unmapped_columns_all_mapped(self):
        """Test get_unmapped_columns when all columns are mapped."""
        from hardcover_sync.config import get_unmapped_columns

        prefs = {
            "status_column": "#hc_status",
            "rating_column": "rating",
            "progress_column": "#progress",
            "progress_percent_column": "#progress_percent",
            "date_started_column": "#started",
            "date_read_column": "#read",
            "is_read_column": "#is_read",
            "review_column": "#review",
        }
        unmapped = get_unmapped_columns(prefs)
        assert len(unmapped) == 0

    def test_progress_percent_only_counts_as_mapped(self):
        """A percentage-only configuration is recognized as a column mapping."""
        from hardcover_sync.config import get_column_mappings, get_unmapped_columns

        prefs = {"progress_percent_column": "#progress_percent"}

        assert get_column_mappings(prefs) == {"progress_percent": "#progress_percent"}
        assert "Progress (%)" not in get_unmapped_columns(prefs)


class TestProgressColumnOptions:
    """Tests for page and percentage column compatibility."""

    def test_integer_columns_are_available_for_percentage_progress(self):
        """Integer percentages are offered without changing page column options."""
        from unittest.mock import Mock

        from hardcover_sync.config import ConfigWidget

        plugin_action = Mock()
        plugin_action.gui.library_view.model().custom_columns = {
            "#integer": {"datatype": "int", "name": "Integer"},
            "#float": {"datatype": "float", "name": "Float"},
        }

        widget = ConfigWidget(plugin_action=plugin_action)

        assert widget.progress_combo.column_names == ["", "#integer"]
        assert widget.progress_percent_combo.column_names == ["", "#float", "#integer"]
