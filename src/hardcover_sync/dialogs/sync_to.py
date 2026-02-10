"""
Sync to Hardcover dialog.

This dialog syncs data from Calibre to Hardcover for selected books.
"""

from __future__ import annotations

from typing import Any

# Qt imports - only available in Calibre's runtime environment
from qt.core import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
)

from ..api import HardcoverAPI
from ..config import (
    STATUS_IDS,
    get_unmapped_columns,
)
from ..models import UserBook
from ..sync import (
    SyncToChange,
    SyncToResult,
    find_sync_to_changes,
)
from .base import HardcoverDialogBase


class SyncToHardcoverDialog(HardcoverDialogBase):
    """
    Dialog for syncing data from Calibre to Hardcover.

    Shows a preview of changes and allows the user to select which to apply.
    """

    def __init__(self, parent: Any, plugin_action: Any, book_ids: list[int]) -> None:
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            plugin_action: The plugin's InterfaceAction.
            book_ids: List of Calibre book IDs to sync.
        """
        super().__init__(parent, plugin_action, book_ids)
        self.changes: list[SyncToChange] = []
        self.hardcover_data: dict[int, UserBook] = {}  # hardcover_book_id -> UserBook

        self.setWindowTitle("Sync to Hardcover")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self._setup_ui()
        # Show diagnostics first, then analyze
        self._update_diagnostics()
        self._analyze_books()

    def _setup_ui(self) -> None:
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

    def _update_diagnostics(self) -> None:
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
            self.info_status_label.setText(
                f"<b>Selection:</b> {len(self.book_ids)} book(s) selected, "
                f"<span style='color: red;'><b>none are linked to Hardcover</b></span><br>"
                "<i>Use 'Link to Hardcover...' to connect books first.</i>"
            )
        elif unlinked_count > 0:
            self.info_status_label.setText(
                f"<b>Selection:</b> {len(self.book_ids)} book(s) selected, "
                f"<b>{linked_count} linked</b>, {unlinked_count} will be skipped<br>"
                f"<i>Unlinked: {', '.join(unlinked_titles)}</i>"
            )
        else:
            self.info_status_label.setText(
                f"<b>Selection:</b> {len(self.book_ids)} book(s) selected, all linked to Hardcover"
            )

        # Column mapping and warnings (delegate to base class)
        self._update_column_diagnostics(linked_count, exclude_columns={"is_read_column"})

    def _analyze_books(self) -> None:
        """Analyze the selected books and find changes."""
        api = self._get_api()
        if not api:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self.book_ids))
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        from ..matcher import resolve_hardcover_book

        def on_progress(i: int) -> None:
            self.progress_bar.setValue(i)
            QApplication.processEvents()

        result: SyncToResult = find_sync_to_changes(
            book_ids=self.book_ids,
            get_identifiers=lambda bid: self.db.field_for("identifiers", bid) or {},
            get_calibre_value=self._get_calibre_value,
            get_calibre_title=lambda bid: self.db.field_for("title", bid) or "Unknown",
            resolve_book=lambda slug: resolve_hardcover_book(api, slug),
            get_user_book=api.get_user_book,
            prefs=self.prefs,
            get_column_metadata=self._get_custom_column_metadata,
            on_progress=on_progress,
        )

        self.changes = result.changes
        self.hardcover_data = result.hardcover_data

        self.progress_bar.setVisible(False)
        self._populate_changes_table()

        # Build detailed status message
        if result.linked_count == 0:
            self.status_label.setText(
                "No selected books are linked to Hardcover. "
                "Use 'Link to Hardcover...' to connect books first."
            )
        elif not self.changes:
            unmapped = get_unmapped_columns(self.prefs)
            if len(unmapped) == 6:  # All unmapped
                self.status_label.setText(
                    f"Analyzed {result.linked_count} linked book(s). "
                    "<b>No columns are mapped!</b> "
                    "Go to plugin settings to map Calibre columns to Hardcover fields."
                )
            else:
                self.status_label.setText(
                    f"Analyzed {result.linked_count} linked book(s). "
                    "No changes needed - Hardcover already matches Calibre data."
                )
        else:
            parts = [
                f"Found {len(self.changes)} change(s) from {result.books_with_changes} book(s)"
            ]
            if result.not_linked_count > 0:
                parts.append(f"{result.not_linked_count} skipped (not linked)")
            if result.api_errors > 0:
                parts.append(f"{result.api_errors} API error(s)")
            self.status_label.setText(". ".join(parts) + ".")

        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(len(self.changes) > 0)
        self._update_summary()

    def _populate_changes_table(self) -> None:
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
            self.changes_table.setItem(row, 4, new_item)

    def _on_checkbox_changed(self, row: int, state: int) -> None:
        """Handle checkbox state change."""
        if 0 <= row < len(self.changes):
            self.changes[row].apply = state == Qt.CheckState.Checked.value
            self._update_summary()

    def _on_select_all_changed(self, state: int) -> None:
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

    def _update_summary(self) -> None:
        """Update the summary label."""
        selected = sum(1 for c in self.changes if c.apply)
        total = len(self.changes)
        self.summary_label.setText(f"<b>{selected}</b> of {total} changes selected to sync.")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(selected > 0)

    def _on_apply(self) -> None:
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
        # Separate user_book data from read data
        # User book: status, rating, review
        # Read: progress_pages, started_at, finished_at
        user_book_data: dict = {}
        read_data: dict = {}
        status_mappings = self.prefs.get("status_mappings", {})
        calibre_to_hc_status = {v: int(k) for k, v in status_mappings.items()}

        for change in changes:
            if change.field == "status" and change.new_value:
                status_id = calibre_to_hc_status.get(change.new_value)
                if status_id is None:
                    status_id = STATUS_IDS.get(change.new_value)
                if status_id:
                    user_book_data["status_id"] = status_id
            elif change.field == "rating":
                user_book_data["rating"] = float(change.api_value) if change.api_value else None
            elif change.field == "progress":
                read_data["progress_pages"] = int(change.api_value) if change.api_value else None
            elif change.field == "progress_percent":
                # api_value is already 0.0-1.0 decimal
                read_data["progress"] = float(change.api_value) if change.api_value else None
            elif change.field == "date_started":
                read_data["started_at"] = change.api_value
            elif change.field == "date_read":
                read_data["finished_at"] = change.api_value
            elif change.field == "review":
                user_book_data["review"] = change.api_value

        if not user_book_data and not read_data:
            return False, "No valid update data"

        try:
            created_user_book = None

            # Either update existing or add new user_book
            if user_book_id:
                # Update existing user_book with non-read data
                if user_book_data:
                    api.update_user_book(user_book_id, **user_book_data)
            else:
                # Need to add book to library first
                status_id = user_book_data.pop("status_id", 1)  # Default to "Want to Read"
                created_user_book = api.add_book_to_library(
                    book_id=hc_book_id,
                    status_id=status_id,
                    **user_book_data,
                )
                user_book_id = created_user_book.id

            # Handle read data (progress, dates) via user_book_reads API
            if read_data and user_book_id:
                # Get the existing user book to check for latest read
                hc_user_book = self.hardcover_data.get(hc_book_id)
                if hc_user_book and hc_user_book.latest_read:
                    # Update existing read
                    api.update_user_book_read(hc_user_book.latest_read.id, **read_data)
                else:
                    # Create new read
                    api.insert_user_book_read(user_book_id, **read_data)

            return True, None

        except Exception as e:
            return False, str(e)
