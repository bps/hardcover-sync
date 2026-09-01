"""Contract smoke tests for Calibre and Qt-facing adapters."""

from types import SimpleNamespace
import sys
from unittest.mock import Mock, call, patch

from hardcover_sync.action import offer_pat_migration, update_calibre_status
from hardcover_sync.config import ConfigWidget, READING_STATUSES
from hardcover_sync.matcher import set_hardcover_slug
from hardcover_sync.services import OperationGuard


class FakeValueWidget:
    def __init__(self, value):
        self.value = value

    def text(self):
        return self.value

    def isChecked(self):
        return self.value

    def get_selected_column(self):
        return self.value

    def setChecked(self, value):
        self.value = value


class FakeCalibreDB:
    def __init__(self, identifiers=None) -> None:
        self.identifiers = identifiers or {}
        self.writes = []

    def field_for(self, field, book_id):
        assert field == "identifiers"
        return dict(self.identifiers)

    def set_field(self, field, values):
        self.writes.append((field, values))


def test_set_hardcover_slug_preserves_other_identifiers():
    db = FakeCalibreDB({"isbn": "9780123456789", "asin": "B000TEST"})

    set_hardcover_slug(db, 7, "test-book", edition_id=9, hardcover_book_id=8)

    assert db.writes == [
        (
            "identifiers",
            {
                7: {
                    "isbn": "9780123456789",
                    "asin": "B000TEST",
                    "hardcover": "test-book",
                    "hardcover-book": "8",
                    "hardcover-edition": "9",
                }
            },
        )
    ]


def test_toolbar_status_write_uses_configured_mapping():
    db = FakeCalibreDB()

    update_calibre_status(
        db,
        7,
        3,
        {"status_column": "#status", "status_mappings": {"3": "Finished"}},
    )

    assert db.writes == [("#status", {7: "Finished"})]


def test_configuration_save_writes_mapping_and_option_contract():
    stored_prefs = {"api_token": "token"}
    widget = SimpleNamespace(
        token_input=FakeValueWidget("token"),
        _allow_unvalidated_token="",
        _normalize_token=lambda value: value.strip(),
        status_combo=FakeValueWidget("#status"),
        rating_combo=FakeValueWidget("rating"),
        progress_combo=FakeValueWidget("#progress"),
        progress_percent_combo=FakeValueWidget("#progress_pct"),
        date_started_combo=FakeValueWidget("#started"),
        date_read_combo=FakeValueWidget("#finished"),
        is_read_combo=FakeValueWidget("#read"),
        review_combo=FakeValueWidget("#review"),
        status_mapping_inputs={3: FakeValueWidget("Finished")},
        auto_link_checkbox=FakeValueWidget(True),
        sync_rating_checkbox=FakeValueWidget(True),
        sync_progress_checkbox=FakeValueWidget(False),
        sync_dates_checkbox=FakeValueWidget(True),
        sync_review_checkbox=FakeValueWidget(False),
        status_filter_checkboxes={
            status_id: FakeValueWidget(status_id in {1, 2, 3}) for status_id in READING_STATUSES
        },
        lab_update_progress_checkbox=FakeValueWidget(False),
        lab_lists_checkbox=FakeValueWidget(True),
    )

    with patch("hardcover_sync.config.prefs", stored_prefs):
        ConfigWidget.save_settings(widget)

    assert stored_prefs["status_column"] == "#status"
    assert stored_prefs["progress_percent_column"] == "#progress_pct"
    assert stored_prefs["status_mappings"] == {"3": "Finished"}
    assert stored_prefs["sync_progress"] is False
    assert stored_prefs["sync_review"] is False
    assert stored_prefs["sync_statuses"] == [1, 2, 3]
    assert stored_prefs["enable_lab_lists"] is True


def test_token_format_warning_hides_after_pasting_pat():
    widget = SimpleNamespace(migration_label=Mock())

    ConfigWidget._update_token_format_warning(widget, "eyJhbGciOiJIUzI1NiJ9.payload.signature")
    ConfigWidget._update_token_format_warning(widget, "hc_pat_replacement")

    assert widget.migration_label.setVisible.call_args_list == [
        call(True),
        call(False),
    ]


def test_configuration_validation_reports_missing_permissions():
    widget = SimpleNamespace()
    user = SimpleNamespace(username="reader", id=7)

    with patch("hardcover_sync.api.HardcoverAPI") as api_class:
        api_class.return_value.validate_token_permissions.return_value = (
            False,
            user,
            ("write:reviews", "write:lists"),
        )
        result = ConfigWidget._validate_token(widget, "hc_pat_test")

    assert result == (
        False,
        None,
        "Missing required permissions: write:reviews, write:lists",
    )


def test_configuration_validate_rejects_changed_invalid_token():
    widget = SimpleNamespace(
        token_input=FakeValueWidget("hc_pat_incomplete"),
        widget=object(),
        _normalize_token=lambda value: value,
        _validate_token=lambda _token: (False, None, "Missing required permissions: write:lists"),
    )

    with (
        patch("hardcover_sync.config.prefs", {"api_token": "old-token"}),
        patch("calibre.gui2.error_dialog"),
    ):
        assert ConfigWidget.validate(widget) is False


def test_configuration_allows_explicit_save_after_transient_validation_failure():
    widget = SimpleNamespace(
        token_input=FakeValueWidget("hc_pat_unverified"),
        widget=object(),
        _allow_unvalidated_token="",
        _normalize_token=lambda value: value,
        _validate_token=lambda _token: (False, None, "HardcoverAPIError: service unavailable"),
    )
    gui2 = SimpleNamespace(question_dialog=Mock(return_value=True))

    with (
        patch("hardcover_sync.config.prefs", {"api_token": "old-token"}),
        patch.dict(sys.modules, {"calibre.gui2": gui2}),
    ):
        assert ConfigWidget.validate(widget) is True

    assert widget._allow_unvalidated_token == "hc_pat_unverified"  # noqa: S105


def test_legacy_jwt_migration_prompt_is_shown_only_once():
    stored_prefs = {
        "api_token": "eyJhbGciOiJIUzI1NiJ9.payload.signature",
        "pat_migration_prompt_shown": False,
    }
    show_configuration = Mock()
    gui2 = SimpleNamespace(question_dialog=Mock(return_value=True), open_url=Mock())

    with (
        patch("hardcover_sync.action.get_plugin_prefs", return_value=stored_prefs),
        patch.dict(sys.modules, {"calibre.gui2": gui2}),
    ):
        offer_pat_migration(object(), show_configuration)
        offer_pat_migration(object(), show_configuration)

    assert stored_prefs["pat_migration_prompt_shown"] is True
    gui2.question_dialog.assert_called_once()
    gui2.open_url.assert_called_once()
    show_configuration.assert_called_once()


def test_status_filter_cannot_leave_every_status_unchecked():
    changed = FakeValueWidget(False)
    widget = SimpleNamespace(
        status_filter_checkboxes={
            1: changed,
            2: FakeValueWidget(False),
        }
    )

    ConfigWidget._ensure_status_filter_not_empty(widget, changed)

    assert changed.isChecked() is True


def test_operation_guard_prevents_reentry_until_finished():
    guard = OperationGuard()

    assert guard.start() is True
    assert guard.start() is False
    guard.finish()
    assert guard.start() is True
