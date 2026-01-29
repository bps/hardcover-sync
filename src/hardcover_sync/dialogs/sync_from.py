"""
Sync from Hardcover dialog.

This dialog fetches the user's Hardcover library and syncs data to Calibre.
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
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
)

from ..api import HardcoverAPI, UserBook
from ..config import READING_STATUSES, get_plugin_prefs


@dataclass
class SyncChange:
    """Represents a change to be synced from Hardcover to Calibre."""

    calibre_id: int
    calibre_title: str
    hardcover_book_id: int
    field: str  # status, rating, progress, date_started, date_read, review
    old_value: str | None
    new_value: str | None
    apply: bool = True  # Whether to apply this change

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


class SyncFromHardcoverDialog(QDialog):
    """
    Dialog for syncing data from Hardcover to Calibre.

    Shows a preview of changes and allows the user to select which to apply.
    """

    def __init__(self, parent, plugin_action):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            plugin_action: The plugin's InterfaceAction (provides access to GUI/database).
        """
        super().__init__(parent)
        self.plugin_action = plugin_action
        self.gui = plugin_action.gui
        self.db = self.gui.current_db.new_api
        self.prefs = get_plugin_prefs()
        self.changes: list[SyncChange] = []
        self.hardcover_books: list[UserBook] = []

        self.setWindowTitle("Sync from Hardcover")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self._setup_ui()
        # Show diagnostic info immediately
        self._update_diagnostics()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "Sync your reading data from Hardcover to Calibre. "
            "Books must be linked via the 'hardcover' identifier to be synced."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Diagnostics panel
        self._setup_diagnostics_panel(layout)

        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Fetch button
        fetch_layout = QHBoxLayout()
        self.fetch_button = QPushButton("Fetch Library")
        self.fetch_button.clicked.connect(self._on_fetch)
        fetch_layout.addWidget(self.fetch_button)
        fetch_layout.addStretch()

        # Select all/none
        self.select_all_checkbox = QCheckBox("Select All")
        self.select_all_checkbox.setChecked(True)
        self.select_all_checkbox.stateChanged.connect(self._on_select_all_changed)
        self.select_all_checkbox.setEnabled(False)
        fetch_layout.addWidget(self.select_all_checkbox)

        layout.addLayout(fetch_layout)

        # Changes table
        self.changes_table = QTableWidget()
        self.changes_table.setColumnCount(6)
        self.changes_table.setHorizontalHeaderLabels(
            ["Apply", "Book", "Field", "Current Value", "New Value", ""]
        )
        self.changes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.changes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.changes_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.changes_table.setColumnHidden(5, True)  # Hidden column for data
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
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Apply Changes")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self.button_box)

    def _setup_diagnostics_panel(self, layout):
        """Setup the diagnostics info panel."""
        # Frame for diagnostics
        diag_frame = QFrame()
        diag_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        diag_layout = QVBoxLayout(diag_frame)
        diag_layout.setContentsMargins(8, 8, 8, 8)

        # Library status
        self.library_status_label = QLabel()
        self.library_status_label.setWordWrap(True)
        diag_layout.addWidget(self.library_status_label)

        # Column mapping status
        self.column_status_label = QLabel()
        self.column_status_label.setWordWrap(True)
        diag_layout.addWidget(self.column_status_label)

        # Warnings
        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #b35900;")  # Orange/warning color
        diag_layout.addWidget(self.warnings_label)

        layout.addWidget(diag_frame)

    def _update_diagnostics(self):
        """Update the diagnostics panel with current status."""
        # Count linked books
        linked_count = 0
        total_count = len(self.db.all_book_ids())

        for book_id in self.db.all_book_ids():
            identifiers = self.db.field_for("identifiers", book_id) or {}
            if identifiers.get("hardcover"):
                linked_count += 1

        if linked_count == 0:
            self.library_status_label.setText(
                f"<b>Library:</b> {total_count} books in Calibre, "
                f"<span style='color: red;'><b>0 linked to Hardcover</b></span><br>"
                "<i>Use 'Link to Hardcover...' to connect books first.</i>"
            )
        else:
            self.library_status_label.setText(
                f"<b>Library:</b> {total_count} books in Calibre, "
                f"<b>{linked_count} linked to Hardcover</b>"
            )

        # Column mapping status - all fields are now supported via user_book_reads
        mappings = []
        unmapped = []

        # All syncable fields
        supported_columns = [
            ("status_column", "Status"),
            ("rating_column", "Rating"),
            ("review_column", "Review"),
            ("progress_column", "Progress"),
            ("date_started_column", "Date Started"),
            ("date_read_column", "Date Read"),
        ]

        for pref_key, display_name in supported_columns:
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
            warnings.append("No books are linked to Hardcover - nothing can be synced.")
        if unmapped:
            warnings.append(f"Unmapped fields will be skipped: {', '.join(unmapped)}")
        if not self.prefs.get("api_token"):
            warnings.append("No API token configured!")

        if warnings:
            self.warnings_label.setText("⚠ " + " | ".join(warnings))
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

        # Update status message
        if linked_count == 0:
            self.status_label.setText(
                "No books are linked to Hardcover. Link books first using "
                "'Link to Hardcover...' before syncing."
            )
            self.fetch_button.setEnabled(False)
        elif not self.prefs.get("api_token"):
            self.status_label.setText(
                "No API token configured. Go to plugin settings to add your token."
            )
            self.fetch_button.setEnabled(False)
        else:
            self.status_label.setText("Click 'Fetch Library' to load your Hardcover books.")
            self.fetch_button.setEnabled(True)

    def _get_api(self) -> HardcoverAPI | None:
        """Get an API instance with the configured token."""
        token = self.prefs.get("api_token", "")
        if not token:
            self.status_label.setText(
                "Error: No API token configured. Please configure the plugin first."
            )
            return None
        return HardcoverAPI(token=token)

    def _on_fetch(self):
        """Fetch the user's Hardcover library."""
        api = self._get_api()
        if not api:
            return

        self.fetch_button.setEnabled(False)
        self.status_label.setText("Fetching your Hardcover library...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        QApplication.processEvents()

        try:
            # Fetch all books from Hardcover
            self.hardcover_books = self._fetch_all_books(api)

            # Build the map first so we can report on it
            hc_to_calibre = self._build_hardcover_to_calibre_map()
            matched_count = sum(1 for hb in self.hardcover_books if hb.book_id in hc_to_calibre)

            self.status_label.setText(
                f"Fetched {len(self.hardcover_books)} books from Hardcover. "
                f"{matched_count} match linked Calibre books. Analyzing changes..."
            )
            QApplication.processEvents()

            # Find changes
            self.changes = self._find_changes(hc_to_calibre)
            self._populate_changes_table()

            # Update UI
            self.progress_bar.setVisible(False)
            self.select_all_checkbox.setEnabled(True)
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
                len(self.changes) > 0
            )
            self._update_summary()

            # Detailed status message
            if not self.changes:
                if matched_count == 0:
                    self.status_label.setText(
                        f"Fetched {len(self.hardcover_books)} books from Hardcover, "
                        "but none match your linked Calibre books. "
                        "Make sure books are linked using 'Link to Hardcover...'."
                    )
                else:
                    # Check if columns are mapped
                    unmapped = self._get_unmapped_columns()
                    if len(unmapped) == 6:  # All unmapped
                        self.status_label.setText(
                            f"Fetched {len(self.hardcover_books)} books, "
                            f"{matched_count} matched. <b>No columns are mapped!</b> "
                            "Go to plugin settings to map Calibre columns to Hardcover fields."
                        )
                    else:
                        self.status_label.setText(
                            f"Fetched {len(self.hardcover_books)} books, "
                            f"{matched_count} matched. No changes needed - "
                            "Calibre is already in sync with Hardcover."
                        )
            else:
                self.status_label.setText(
                    f"Found {len(self.changes)} change(s) from {matched_count} matched books "
                    f"(out of {len(self.hardcover_books)} in your Hardcover library)."
                )

        except Exception as e:
            self.status_label.setText(f"Error fetching library: {e}")
            self.progress_bar.setVisible(False)
        finally:
            self.fetch_button.setEnabled(True)

    def _get_unmapped_columns(self) -> list[str]:
        """Get list of unmapped column names."""
        unmapped = []
        # All syncable fields
        columns = [
            ("status_column", "Status"),
            ("rating_column", "Rating"),
            ("review_column", "Review"),
            ("progress_column", "Progress"),
            ("date_started_column", "Date Started"),
            ("date_read_column", "Date Read"),
        ]
        for pref_key, display_name in columns:
            if not self.prefs.get(pref_key, ""):
                unmapped.append(display_name)
        return unmapped

    def _fetch_all_books(self, api: HardcoverAPI) -> list[UserBook]:
        """Fetch all books from the user's Hardcover library."""
        all_books = []
        offset = 0
        limit = 100

        while True:
            batch = api.get_user_books(limit=limit, offset=offset)
            all_books.extend(batch)

            if len(batch) < limit:
                break

            offset += limit
            QApplication.processEvents()

        return all_books

    def _find_changes(self, hc_to_calibre: dict[int, int] | None = None) -> list[SyncChange]:
        """Find all changes between Hardcover and Calibre."""
        changes = []

        # Get column mappings
        status_col = self.prefs.get("status_column", "")
        rating_col = self.prefs.get("rating_column", "")
        progress_col = self.prefs.get("progress_column", "")
        date_started_col = self.prefs.get("date_started_column", "")
        date_read_col = self.prefs.get("date_read_column", "")
        review_col = self.prefs.get("review_column", "")

        # Get sync options
        sync_rating = self.prefs.get("sync_rating", True)
        sync_progress = self.prefs.get("sync_progress", True)
        sync_dates = self.prefs.get("sync_dates", True)
        sync_review = self.prefs.get("sync_review", True)

        # Get status mappings (Hardcover ID -> Calibre value)
        status_mappings = self.prefs.get("status_mappings", {})

        # Build a map of Hardcover book ID -> Calibre book ID
        if hc_to_calibre is None:
            hc_to_calibre = self._build_hardcover_to_calibre_map()

        for hc_book in self.hardcover_books:
            calibre_id = hc_to_calibre.get(hc_book.book_id)
            if not calibre_id:
                continue  # Not linked to Calibre

            calibre_title = self.db.field_for("title", calibre_id) or "Unknown"

            # Check status
            if status_col and hc_book.status_id:
                hc_status_value = status_mappings.get(
                    str(hc_book.status_id), READING_STATUSES.get(hc_book.status_id, "")
                )
                if hc_status_value:
                    current = self._get_calibre_value(calibre_id, status_col)
                    if current != hc_status_value:
                        changes.append(
                            SyncChange(
                                calibre_id=calibre_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book.book_id,
                                field="status",
                                old_value=current or "(empty)",
                                new_value=hc_status_value,
                            )
                        )

            # Check rating
            if sync_rating and rating_col and hc_book.rating is not None:
                current = self._get_calibre_value(calibre_id, rating_col)
                new_rating = str(hc_book.rating)
                # Convert to Calibre rating scale if using built-in rating
                if rating_col == "rating":
                    # Built-in rating is 0-10 (displayed as stars)
                    new_rating = str(int(hc_book.rating * 2))
                if str(current) != new_rating:
                    changes.append(
                        SyncChange(
                            calibre_id=calibre_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book.book_id,
                            field="rating",
                            old_value=str(current) if current else "(empty)",
                            new_value=new_rating,
                        )
                    )

            # Check progress (from latest read)
            current_progress = hc_book.current_progress_pages
            if sync_progress and progress_col and current_progress is not None:
                current = self._get_calibre_value(calibre_id, progress_col)
                new_progress = str(current_progress)
                if str(current) != new_progress:
                    changes.append(
                        SyncChange(
                            calibre_id=calibre_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book.book_id,
                            field="progress",
                            old_value=str(current) if current else "(empty)",
                            new_value=new_progress,
                        )
                    )

            # Check date started (from latest read)
            latest_started = hc_book.latest_started_at
            if sync_dates and date_started_col and latest_started:
                current = self._get_calibre_value(calibre_id, date_started_col)
                current_str = str(current)[:10] if current else ""
                new_date = latest_started[:10]  # YYYY-MM-DD
                if current_str != new_date:
                    changes.append(
                        SyncChange(
                            calibre_id=calibre_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book.book_id,
                            field="date_started",
                            old_value=current_str or "(empty)",
                            new_value=new_date,
                        )
                    )

            # Check date read (from latest read)
            latest_finished = hc_book.latest_finished_at
            if sync_dates and date_read_col and latest_finished:
                current = self._get_calibre_value(calibre_id, date_read_col)
                current_str = str(current)[:10] if current else ""
                new_date = latest_finished[:10]
                if current_str != new_date:
                    changes.append(
                        SyncChange(
                            calibre_id=calibre_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book.book_id,
                            field="date_read",
                            old_value=current_str or "(empty)",
                            new_value=new_date,
                        )
                    )

            # Check review
            if sync_review and review_col and hc_book.review:
                current = self._get_calibre_value(calibre_id, review_col)
                if current != hc_book.review:
                    changes.append(
                        SyncChange(
                            calibre_id=calibre_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book.book_id,
                            field="review",
                            old_value=(current[:50] + "...")
                            if current and len(current) > 50
                            else (current or "(empty)"),
                            new_value=(hc_book.review[:50] + "...")
                            if len(hc_book.review) > 50
                            else hc_book.review,
                        )
                    )

        return changes

    def _build_hardcover_to_calibre_map(self) -> dict[int, int]:
        """Build a map from Hardcover book ID to Calibre book ID."""
        hc_to_calibre = {}

        # Get all book IDs in library
        all_book_ids = self.db.all_book_ids()

        for book_id in all_book_ids:
            identifiers = self.db.field_for("identifiers", book_id) or {}
            hc_id = identifiers.get("hardcover")
            if hc_id:
                try:
                    hc_to_calibre[int(hc_id)] = book_id
                except (ValueError, TypeError):
                    pass

        return hc_to_calibre

    def _get_calibre_value(self, book_id: int, column: str):
        """Get a value from a Calibre column."""
        if not column:
            return None

        if column == "rating":
            return self.db.field_for("rating", book_id)

        if column.startswith("#"):
            # Custom column
            return self.db.field_for(column, book_id)

        return self.db.field_for(column, book_id)

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

            # Current value
            self.changes_table.setItem(row, 3, QTableWidgetItem(change.old_value or ""))

            # New value
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
        self.summary_label.setText(f"<b>{selected}</b> of {total} changes selected to apply.")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(selected > 0)

    def _on_apply(self):
        """Apply the selected changes."""
        changes_to_apply = [c for c in self.changes if c.apply]
        if not changes_to_apply:
            self.reject()
            return

        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(False)
        self.status_label.setText("Applying changes...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(changes_to_apply))
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        applied = 0
        skipped = 0
        errors = []

        for i, change in enumerate(changes_to_apply):
            try:
                success, error_msg = self._apply_change(change)
                if success:
                    applied += 1
                else:
                    skipped += 1
                    if error_msg:
                        errors.append(f"{change.calibre_title}: {error_msg}")
            except Exception as e:
                errors.append(f"{change.calibre_title}: {e}")

            self.progress_bar.setValue(i + 1)
            QApplication.processEvents()

        self.progress_bar.setVisible(False)

        # Build result message
        result_parts = []
        if applied > 0:
            result_parts.append(f"Applied {applied} change(s)")
        if skipped > 0:
            result_parts.append(f"Skipped {skipped}")
        if errors:
            result_parts.append(f"{len(errors)} error(s)")

        result_msg = ". ".join(result_parts) + "."

        if errors:
            # Show first few errors
            error_preview = "; ".join(errors[:3])
            if len(errors) > 3:
                error_preview += f" (+{len(errors) - 3} more)"
            result_msg += f"\nErrors: {error_preview}"

        self.status_label.setText(result_msg)

        if applied > 0:
            # Refresh the library view
            self.gui.library_view.model().refresh()

        # Show summary dialog before closing
        from calibre.gui2 import info_dialog

        if errors:
            info_dialog(
                self,
                "Sync Complete (with errors)",
                f"Applied {applied} change(s), skipped {skipped}, {len(errors)} error(s).\n\n"
                f"Errors:\n" + "\n".join(errors[:10]),
                show=True,
            )
        elif applied > 0:
            info_dialog(
                self,
                "Sync Complete",
                f"Successfully applied {applied} change(s) to your Calibre library.",
                show=True,
            )
        else:
            info_dialog(
                self,
                "No Changes Applied",
                "No changes were applied. This may be because columns are not mapped "
                "in the plugin settings.",
                show=True,
            )

        self.accept()

    def _apply_change(self, change: SyncChange) -> tuple[bool, str | None]:
        """
        Apply a single change to Calibre.

        Returns:
            Tuple of (success, error_message).
        """
        column = self._get_column_for_field(change.field)
        if not column:
            return False, f"No column mapped for {change.display_field}"

        value = change.new_value

        try:
            # Handle different column types
            if column == "rating":
                # Built-in rating
                self.db.set_field("rating", {change.calibre_id: int(value) if value else None})
            elif column.startswith("#"):
                # Custom column - need to determine type
                col_info = self._get_custom_column_metadata(column)
                if not col_info:
                    return False, f"Column {column} not found"

                datatype = col_info.get("datatype")
                if datatype == "int":
                    value = int(value) if value else None
                elif datatype == "float":
                    value = float(value) if value else None
                elif datatype == "datetime":
                    # Parse date string
                    from datetime import datetime

                    if value:
                        value = datetime.fromisoformat(value)
                    else:
                        value = None
                elif datatype == "rating":
                    value = int(float(value) * 2) if value else None

                self.db.set_field(column, {change.calibre_id: value})
            else:
                self.db.set_field(column, {change.calibre_id: value})

            return True, None

        except Exception as e:
            return False, str(e)

    def _get_custom_column_metadata(self, column: str) -> dict | None:
        """Get metadata for a custom column."""
        try:
            custom_columns = self.gui.library_view.model().custom_columns
            return custom_columns.get(column)
        except (AttributeError, Exception):
            return None

    def _get_column_for_field(self, field: str) -> str | None:
        """Get the Calibre column name for a sync field."""
        mapping = {
            "status": self.prefs.get("status_column", ""),
            "rating": self.prefs.get("rating_column", ""),
            "progress": self.prefs.get("progress_column", ""),
            "date_started": self.prefs.get("date_started_column", ""),
            "date_read": self.prefs.get("date_read_column", ""),
            "review": self.prefs.get("review_column", ""),
        }
        return mapping.get(field)
