"""
Sync to Hardcover dialog.

This dialog syncs data from Calibre to Hardcover for selected books.
"""

from dataclasses import dataclass

# Qt imports - only available in Calibre's runtime environment
from qt.core import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
)

from ..api import HardcoverAPI, UserBook
from ..config import READING_STATUSES, STATUS_IDS, get_plugin_prefs


def format_rating_as_stars(rating: float | None) -> str:
    """
    Format a rating (0-5 scale) as star characters.

    Args:
        rating: Rating value from 0-5, or None.

    Returns:
        String like "★★★★½" or "(empty)" if None.
    """
    if rating is None:
        return "(empty)"

    full_stars = int(rating)
    half_star = (rating - full_stars) >= 0.5

    result = "★" * full_stars
    if half_star:
        result += "½"

    # Pad with empty stars for visual consistency
    empty_stars = 5 - full_stars - (1 if half_star else 0)
    result += "☆" * empty_stars

    return result or "☆☆☆☆☆"  # Show empty stars for 0 rating


@dataclass
class SyncToChange:
    """Represents a change to be synced from Calibre to Hardcover."""

    calibre_id: int
    calibre_title: str
    hardcover_book_id: int
    user_book_id: int | None  # None if not in Hardcover library yet
    field: str  # status, rating, progress, date_started, date_read, review
    old_value: str | None  # Current Hardcover value (for display)
    new_value: str | None  # New value from Calibre (for display)
    raw_value: str | None = None  # Raw value for API (if different from display)
    apply: bool = True

    @property
    def api_value(self) -> str | None:
        """Get the value to send to the API."""
        return self.raw_value if self.raw_value is not None else self.new_value

    @property
    def display_field(self) -> str:
        """Get a display-friendly field name."""
        return {
            "status": "Reading Status",
            "rating": "Rating",
            "progress": "Progress",
            "date_started": "Date Started",
            "date_read": "Date Read",
            "review": "Review",
        }.get(self.field, self.field)


class SyncToHardcoverDialog(QDialog):
    """
    Dialog for syncing data from Calibre to Hardcover.

    Shows a preview of changes and allows the user to select which to apply.
    """

    def __init__(self, parent, plugin_action, book_ids: list[int]):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            plugin_action: The plugin's InterfaceAction.
            book_ids: List of Calibre book IDs to sync.
        """
        super().__init__(parent)
        self.plugin_action = plugin_action
        self.gui = plugin_action.gui
        self.db = self.gui.current_db.new_api
        self.prefs = get_plugin_prefs()
        self.book_ids = book_ids
        self.changes: list[SyncToChange] = []
        self.hardcover_data: dict[int, UserBook] = {}  # hardcover_book_id -> UserBook

        self.setWindowTitle("Sync to Hardcover")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self._setup_ui()
        # Show diagnostics first, then analyze
        self._update_diagnostics()
        self._analyze_books()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            f"Sync {len(self.book_ids)} selected book(s) from Calibre to Hardcover. "
            "Books must be linked via the 'hardcover' identifier."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Diagnostics panel
        self._setup_diagnostics_panel(layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Analyzing books...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Select all checkbox
        select_layout = QHBoxLayout()
        select_layout.addStretch()
        self.select_all_checkbox = QCheckBox("Select All")
        self.select_all_checkbox.setChecked(True)
        self.select_all_checkbox.stateChanged.connect(self._on_select_all_changed)
        select_layout.addWidget(self.select_all_checkbox)
        layout.addLayout(select_layout)

        # Changes table
        self.changes_table = QTableWidget()
        self.changes_table.setColumnCount(5)
        self.changes_table.setHorizontalHeaderLabels(
            ["Apply", "Book", "Field", "Hardcover Value", "Calibre Value"]
        )
        self.changes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.changes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.changes_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.changes_table)

        # Summary
        self.summary_label = QLabel("")
        layout.addWidget(self.summary_label)

        # Button box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_apply)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Sync to Hardcover")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self.button_box)

    def _setup_diagnostics_panel(self, layout):
        """Setup the diagnostics info panel."""
        diag_frame = QFrame()
        diag_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        diag_layout = QVBoxLayout(diag_frame)
        diag_layout.setContentsMargins(8, 8, 8, 8)

        # Selection status
        self.selection_status_label = QLabel()
        self.selection_status_label.setWordWrap(True)
        diag_layout.addWidget(self.selection_status_label)

        # Column mapping status
        self.column_status_label = QLabel()
        self.column_status_label.setWordWrap(True)
        diag_layout.addWidget(self.column_status_label)

        # Warnings
        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #b35900;")
        diag_layout.addWidget(self.warnings_label)

        layout.addWidget(diag_frame)

    def _update_diagnostics(self):
        """Update the diagnostics panel."""
        # Count linked vs unlinked in selection
        linked_count = 0
        unlinked_titles = []

        for book_id in self.book_ids:
            identifiers = self.db.field_for("identifiers", book_id) or {}
            if identifiers.get("hardcover"):
                linked_count += 1
            else:
                title = self.db.field_for("title", book_id) or "Unknown"
                if len(unlinked_titles) < 3:
                    unlinked_titles.append(title)
                elif len(unlinked_titles) == 3:
                    unlinked_titles.append("...")

        unlinked_count = len(self.book_ids) - linked_count

        if linked_count == 0:
            self.selection_status_label.setText(
                f"<b>Selection:</b> {len(self.book_ids)} book(s) selected, "
                f"<span style='color: red;'><b>none are linked to Hardcover</b></span><br>"
                "<i>Use 'Link to Hardcover...' to connect books first.</i>"
            )
        elif unlinked_count > 0:
            self.selection_status_label.setText(
                f"<b>Selection:</b> {len(self.book_ids)} book(s) selected, "
                f"<b>{linked_count} linked</b>, {unlinked_count} will be skipped<br>"
                f"<i>Unlinked: {', '.join(unlinked_titles)}</i>"
            )
        else:
            self.selection_status_label.setText(
                f"<b>Selection:</b> {len(self.book_ids)} book(s) selected, all linked to Hardcover"
            )

        # Column mapping status
        mappings = []
        unmapped = []

        columns = [
            ("status_column", "Status"),
            ("rating_column", "Rating"),
            ("progress_column", "Progress"),
            ("date_started_column", "Date Started"),
            ("date_read_column", "Date Read"),
            ("review_column", "Review"),
        ]

        for pref_key, display_name in columns:
            col = self.prefs.get(pref_key, "")
            if col:
                mappings.append(f"{display_name} → {col}")
            else:
                unmapped.append(display_name)

        if mappings:
            self.column_status_label.setText(f"<b>Mapped columns:</b> {', '.join(mappings)}")
        else:
            self.column_status_label.setText(
                "<b>Mapped columns:</b> <span style='color: red;'>None</span>"
            )

        # Warnings
        warnings = []
        if linked_count == 0:
            warnings.append("No selected books are linked to Hardcover.")
        if unmapped:
            warnings.append(f"Unmapped fields won't sync: {', '.join(unmapped)}")
        if not self.prefs.get("api_token"):
            warnings.append("No API token configured!")

        if warnings:
            self.warnings_label.setText("⚠ " + " | ".join(warnings))
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

    def _get_api(self) -> HardcoverAPI | None:
        """Get an API instance."""
        token = self.prefs.get("api_token", "")
        if not token:
            self.status_label.setText(
                "Error: No API token configured. Go to plugin settings to add your token."
            )
            return None
        return HardcoverAPI(token=token)

    def _get_unmapped_columns(self) -> list[str]:
        """Get list of unmapped column names."""
        unmapped = []
        columns = [
            ("status_column", "Status"),
            ("rating_column", "Rating"),
            ("progress_column", "Progress"),
            ("date_started_column", "Date Started"),
            ("date_read_column", "Date Read"),
            ("review_column", "Review"),
        ]
        for pref_key, display_name in columns:
            if not self.prefs.get(pref_key, ""):
                unmapped.append(display_name)
        return unmapped

    def _analyze_books(self):
        """Analyze the selected books and find changes."""
        api = self._get_api()
        if not api:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self.book_ids))
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        # Get column mappings
        status_col = self.prefs.get("status_column", "")
        rating_col = self.prefs.get("rating_column", "")
        progress_col = self.prefs.get("progress_column", "")
        date_started_col = self.prefs.get("date_started_column", "")
        date_read_col = self.prefs.get("date_read_column", "")
        review_col = self.prefs.get("review_column", "")

        # Get status mappings (reverse: Calibre value -> Hardcover ID)
        status_mappings = self.prefs.get("status_mappings", {})
        calibre_to_hc_status = {v: int(k) for k, v in status_mappings.items()}

        linked_count = 0
        not_linked_count = 0
        api_errors = 0
        books_with_data = 0

        for i, book_id in enumerate(self.book_ids):
            self.progress_bar.setValue(i + 1)
            QApplication.processEvents()

            # Check if book is linked to Hardcover
            identifiers = self.db.field_for("identifiers", book_id) or {}
            hc_id_str = identifiers.get("hardcover")
            if not hc_id_str:
                not_linked_count += 1
                continue

            try:
                hc_book_id = int(hc_id_str)
            except (ValueError, TypeError):
                not_linked_count += 1
                continue

            linked_count += 1
            calibre_title = self.db.field_for("title", book_id) or "Unknown"

            # Fetch current Hardcover data for this book
            try:
                hc_user_book = api.get_user_book(hc_book_id)
                self.hardcover_data[hc_book_id] = hc_user_book
            except Exception:
                api_errors += 1
                hc_user_book = None

            user_book_id = hc_user_book.id if hc_user_book else None

            # Track if this book has any Calibre data to sync
            book_has_changes = False

            # Compare status
            if status_col:
                calibre_status = self._get_calibre_value(book_id, status_col)
                if calibre_status:
                    hc_status_id = calibre_to_hc_status.get(calibre_status)
                    if hc_status_id is None:
                        # Try direct match with status name
                        hc_status_id = STATUS_IDS.get(calibre_status)

                    if hc_status_id:
                        hc_current_status = (
                            READING_STATUSES.get(hc_user_book.status_id)
                            if hc_user_book and hc_user_book.status_id
                            else None
                        )
                        if hc_current_status != calibre_status:
                            self.changes.append(
                                SyncToChange(
                                    calibre_id=book_id,
                                    calibre_title=calibre_title,
                                    hardcover_book_id=hc_book_id,
                                    user_book_id=user_book_id,
                                    field="status",
                                    old_value=hc_current_status or "(not in library)",
                                    new_value=calibre_status,
                                )
                            )
                            book_has_changes = True

            # Compare rating
            if rating_col:
                calibre_rating = self._get_calibre_value(book_id, rating_col)
                if calibre_rating is not None:
                    # Convert Calibre rating to Hardcover scale (0-5)
                    # Both built-in rating and custom rating columns use 0-10 internally
                    if rating_col == "rating":
                        # Built-in rating is 0-10
                        hc_new_rating = calibre_rating / 2 if calibre_rating else None
                    elif rating_col.startswith("#"):
                        # Custom column - check if it's a rating type
                        col_info = self._get_custom_column_metadata(rating_col)
                        if col_info and col_info.get("datatype") == "rating":
                            # Custom rating columns also use 0-10 internally
                            hc_new_rating = calibre_rating / 2 if calibre_rating else None
                        else:
                            # Other column types (int, float) - assume already 0-5
                            hc_new_rating = float(calibre_rating)
                    else:
                        hc_new_rating = float(calibre_rating)

                    hc_current_rating = hc_user_book.rating if hc_user_book else None
                    if hc_new_rating != hc_current_rating:
                        self.changes.append(
                            SyncToChange(
                                calibre_id=book_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book_id,
                                user_book_id=user_book_id,
                                field="rating",
                                old_value=format_rating_as_stars(hc_current_rating),
                                new_value=format_rating_as_stars(hc_new_rating),
                                raw_value=str(hc_new_rating),
                            )
                        )
                        book_has_changes = True

            # Compare progress
            if progress_col:
                calibre_progress = self._get_calibre_value(book_id, progress_col)
                if calibre_progress is not None:
                    hc_current_progress = hc_user_book.progress_pages if hc_user_book else None
                    if calibre_progress != hc_current_progress:
                        self.changes.append(
                            SyncToChange(
                                calibre_id=book_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book_id,
                                user_book_id=user_book_id,
                                field="progress",
                                old_value=str(hc_current_progress)
                                if hc_current_progress is not None
                                else "(empty)",
                                new_value=str(calibre_progress),
                            )
                        )
                        book_has_changes = True

            # Compare date started
            if date_started_col:
                calibre_date = self._get_calibre_value(book_id, date_started_col)
                if calibre_date:
                    calibre_date_str = str(calibre_date)[:10]
                    hc_current_date = (
                        hc_user_book.started_at[:10]
                        if hc_user_book and hc_user_book.started_at
                        else None
                    )
                    if calibre_date_str != hc_current_date:
                        self.changes.append(
                            SyncToChange(
                                calibre_id=book_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book_id,
                                user_book_id=user_book_id,
                                field="date_started",
                                old_value=hc_current_date or "(empty)",
                                new_value=calibre_date_str,
                            )
                        )
                        book_has_changes = True

            # Compare date read
            if date_read_col:
                calibre_date = self._get_calibre_value(book_id, date_read_col)
                if calibre_date:
                    calibre_date_str = str(calibre_date)[:10]
                    hc_current_date = (
                        hc_user_book.finished_at[:10]
                        if hc_user_book and hc_user_book.finished_at
                        else None
                    )
                    if calibre_date_str != hc_current_date:
                        self.changes.append(
                            SyncToChange(
                                calibre_id=book_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book_id,
                                user_book_id=user_book_id,
                                field="date_read",
                                old_value=hc_current_date or "(empty)",
                                new_value=calibre_date_str,
                            )
                        )
                        book_has_changes = True

            # Compare review
            if review_col:
                calibre_review = self._get_calibre_value(book_id, review_col)
                if calibre_review:
                    hc_current_review = hc_user_book.review if hc_user_book else None
                    if calibre_review != hc_current_review:
                        self.changes.append(
                            SyncToChange(
                                calibre_id=book_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book_id,
                                user_book_id=user_book_id,
                                field="review",
                                old_value=(hc_current_review[:50] + "...")
                                if hc_current_review and len(hc_current_review) > 50
                                else (hc_current_review or "(empty)"),
                                new_value=(calibre_review[:50] + "...")
                                if len(calibre_review) > 50
                                else calibre_review,
                            )
                        )
                        book_has_changes = True

            if book_has_changes:
                books_with_data += 1

        self.progress_bar.setVisible(False)
        self._populate_changes_table()

        # Build detailed status message
        if linked_count == 0:
            self.status_label.setText(
                "No selected books are linked to Hardcover. "
                "Use 'Link to Hardcover...' to connect books first."
            )
        elif not self.changes:
            unmapped = self._get_unmapped_columns()
            if len(unmapped) == 6:  # All unmapped
                self.status_label.setText(
                    f"Analyzed {linked_count} linked book(s). "
                    "<b>No columns are mapped!</b> "
                    "Go to plugin settings to map Calibre columns to Hardcover fields."
                )
            else:
                self.status_label.setText(
                    f"Analyzed {linked_count} linked book(s). "
                    "No changes needed - Hardcover already matches Calibre data."
                )
        else:
            parts = [f"Found {len(self.changes)} change(s) from {books_with_data} book(s)"]
            if not_linked_count > 0:
                parts.append(f"{not_linked_count} skipped (not linked)")
            if api_errors > 0:
                parts.append(f"{api_errors} API error(s)")
            self.status_label.setText(". ".join(parts) + ".")

        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(len(self.changes) > 0)
        self._update_summary()

    def _get_calibre_value(self, book_id: int, column: str):
        """Get a value from a Calibre column."""
        if not column:
            return None
        return self.db.field_for(column, book_id)

    def _get_custom_column_metadata(self, column: str) -> dict | None:
        """Get metadata for a custom column."""
        try:
            custom_columns = self.gui.library_view.model().custom_columns
            return custom_columns.get(column)
        except (AttributeError, Exception):
            return None

    def _populate_changes_table(self):
        """Populate the changes table."""
        self.changes_table.setRowCount(len(self.changes))

        for row, change in enumerate(self.changes):
            # Apply checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(change.apply)
            checkbox.stateChanged.connect(lambda state, r=row: self._on_checkbox_changed(r, state))
            self.changes_table.setCellWidget(row, 0, checkbox)

            # Book title
            self.changes_table.setItem(row, 1, QTableWidgetItem(change.calibre_title))

            # Field
            self.changes_table.setItem(row, 2, QTableWidgetItem(change.display_field))

            # Hardcover value (current)
            self.changes_table.setItem(row, 3, QTableWidgetItem(change.old_value or ""))

            # Calibre value (new)
            new_item = QTableWidgetItem(change.new_value or "")
            new_item.setForeground(Qt.GlobalColor.darkGreen)
            self.changes_table.setItem(row, 4, new_item)

    def _on_checkbox_changed(self, row: int, state: int):
        """Handle checkbox state change."""
        if 0 <= row < len(self.changes):
            self.changes[row].apply = state == Qt.CheckState.Checked.value
            self._update_summary()

    def _on_select_all_changed(self, state: int):
        """Handle select all checkbox."""
        checked = state == Qt.CheckState.Checked.value
        for row, change in enumerate(self.changes):
            change.apply = checked
            checkbox = self.changes_table.cellWidget(row, 0)
            if checkbox:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
        self._update_summary()

    def _update_summary(self):
        """Update the summary label."""
        selected = sum(1 for c in self.changes if c.apply)
        total = len(self.changes)
        self.summary_label.setText(f"<b>{selected}</b> of {total} changes selected to sync.")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(selected > 0)

    def _on_apply(self):
        """Apply the selected changes to Hardcover."""
        changes_to_apply = [c for c in self.changes if c.apply]
        if not changes_to_apply:
            self.reject()
            return

        api = self._get_api()
        if not api:
            return

        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(False)
        self.status_label.setText("Syncing to Hardcover...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(changes_to_apply))
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        applied = 0
        skipped = 0
        errors = []

        # Group changes by book for efficient API calls
        changes_by_book: dict[tuple[int, int | None], list[SyncToChange]] = {}
        for change in changes_to_apply:
            key = (change.hardcover_book_id, change.user_book_id)
            if key not in changes_by_book:
                changes_by_book[key] = []
            changes_by_book[key].append(change)

        i = 0
        for (hc_book_id, user_book_id), book_changes in changes_by_book.items():
            book_title = book_changes[0].calibre_title if book_changes else "Unknown"
            try:
                success, error_msg = self._apply_book_changes(
                    api, hc_book_id, user_book_id, book_changes
                )
                if success:
                    applied += len(book_changes)
                else:
                    skipped += len(book_changes)
                    if error_msg:
                        errors.append(f"{book_title}: {error_msg}")
            except Exception as e:
                errors.append(f"{book_title}: {e}")

            i += len(book_changes)
            self.progress_bar.setValue(i)
            QApplication.processEvents()

        self.progress_bar.setVisible(False)

        # Build result message
        result_parts = []
        if applied > 0:
            result_parts.append(f"Synced {applied} change(s)")
        if skipped > 0:
            result_parts.append(f"Skipped {skipped}")
        if errors:
            result_parts.append(f"{len(errors)} error(s)")

        result_msg = ". ".join(result_parts) + "." if result_parts else "No changes applied."

        if errors:
            error_preview = "; ".join(errors[:3])
            if len(errors) > 3:
                error_preview += f" (+{len(errors) - 3} more)"
            result_msg += f"\nErrors: {error_preview}"

        self.status_label.setText(result_msg)

        # Show summary dialog
        from calibre.gui2 import info_dialog

        if errors:
            info_dialog(
                self,
                "Sync Complete (with errors)",
                f"Synced {applied} change(s), skipped {skipped}, {len(errors)} error(s).\n\n"
                f"Errors:\n" + "\n".join(errors[:10]),
                show=True,
            )
        elif applied > 0:
            info_dialog(
                self,
                "Sync Complete",
                f"Successfully synced {applied} change(s) to Hardcover.",
                show=True,
            )
        else:
            info_dialog(
                self,
                "No Changes Synced",
                "No changes were synced. This may be because:\n"
                "- No columns are mapped in plugin settings\n"
                "- Calibre values match Hardcover values\n"
                "- Selected books are not linked to Hardcover",
                show=True,
            )

        self.accept()

    def _apply_book_changes(
        self,
        api: HardcoverAPI,
        hc_book_id: int,
        user_book_id: int | None,
        changes: list[SyncToChange],
    ) -> tuple[bool, str | None]:
        """
        Apply all changes for a single book.

        Returns:
            Tuple of (success, error_message).
        """
        # Build the update data
        update_data: dict = {}
        status_mappings = self.prefs.get("status_mappings", {})
        calibre_to_hc_status = {v: int(k) for k, v in status_mappings.items()}

        for change in changes:
            if change.field == "status":
                status_id = calibre_to_hc_status.get(change.new_value)
                if status_id is None:
                    status_id = STATUS_IDS.get(change.new_value)
                if status_id:
                    update_data["status_id"] = status_id
            elif change.field == "rating":
                update_data["rating"] = float(change.api_value) if change.api_value else None
            elif change.field == "progress":
                update_data["progress_pages"] = int(change.api_value) if change.api_value else None
            elif change.field == "date_started":
                update_data["started_at"] = change.api_value
            elif change.field == "date_read":
                update_data["finished_at"] = change.api_value
            elif change.field == "review":
                update_data["review"] = change.api_value

        if not update_data:
            return False, "No valid update data"

        try:
            # Either update existing or add new
            if user_book_id:
                # Update existing user_book
                api.update_user_book(user_book_id, **update_data)
            else:
                # Need to add book to library first
                status_id = update_data.pop("status_id", 1)  # Default to "Want to Read"
                api.add_book_to_library(
                    book_id=hc_book_id,
                    status_id=status_id,
                    **update_data,
                )
            return True, None

        except Exception as e:
            return False, str(e)
