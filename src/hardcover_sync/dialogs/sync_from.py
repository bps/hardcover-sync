"""
Sync from Hardcover dialog.

This dialog fetches the user's Hardcover library and syncs data to Calibre.
"""

from dataclasses import dataclass

from qt.core import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
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
        self.setMinimumHeight(500)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "This will sync your Hardcover library data to Calibre. "
            "Only books that are already linked (via Hardcover identifier) will be synced."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Click 'Fetch Library' to load your Hardcover books.")
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
            self.status_label.setText(
                f"Fetched {len(self.hardcover_books)} books from Hardcover. Analyzing changes..."
            )
            QApplication.processEvents()

            # Find changes
            self.changes = self._find_changes()
            self._populate_changes_table()

            # Update UI
            self.progress_bar.setVisible(False)
            self.select_all_checkbox.setEnabled(True)
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(len(self.changes) > 0)
            self._update_summary()

            if not self.changes:
                self.status_label.setText(
                    f"Fetched {len(self.hardcover_books)} books. No changes to sync."
                )
            else:
                self.status_label.setText(
                    f"Found {len(self.changes)} change(s) to sync from {len(self.hardcover_books)} Hardcover books."
                )

        except Exception as e:
            self.status_label.setText(f"Error fetching library: {e}")
            self.progress_bar.setVisible(False)
        finally:
            self.fetch_button.setEnabled(True)

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

    def _find_changes(self) -> list[SyncChange]:
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

            # Check progress
            if sync_progress and progress_col and hc_book.progress_pages is not None:
                current = self._get_calibre_value(calibre_id, progress_col)
                new_progress = str(hc_book.progress_pages)
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

            # Check date started
            if sync_dates and date_started_col and hc_book.started_at:
                current = self._get_calibre_value(calibre_id, date_started_col)
                current_str = str(current)[:10] if current else ""
                new_date = hc_book.started_at[:10]  # YYYY-MM-DD
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

            # Check date read
            if sync_dates and date_read_col and hc_book.finished_at:
                current = self._get_calibre_value(calibre_id, date_read_col)
                current_str = str(current)[:10] if current else ""
                new_date = hc_book.finished_at[:10]
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
            new_item.setForeground(Qt.darkGreen)
            self.changes_table.setItem(row, 4, new_item)

    def _on_checkbox_changed(self, row: int, state: int):
        """Handle checkbox state change."""
        if 0 <= row < len(self.changes):
            self.changes[row].apply = state == Qt.Checked
            self._update_summary()

    def _on_select_all_changed(self, state: int):
        """Handle select all checkbox."""
        checked = state == Qt.Checked
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
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(selected > 0)

    def _on_apply(self):
        """Apply the selected changes."""
        changes_to_apply = [c for c in self.changes if c.apply]
        if not changes_to_apply:
            self.reject()
            return

        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
        self.button_box.button(QDialogButtonBox.Cancel).setEnabled(False)
        self.status_label.setText("Applying changes...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(changes_to_apply))
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        applied = 0
        errors = 0

        for i, change in enumerate(changes_to_apply):
            try:
                self._apply_change(change)
                applied += 1
            except Exception as e:
                errors += 1
                print(f"Error applying change: {e}")

            self.progress_bar.setValue(i + 1)
            QApplication.processEvents()

        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Applied {applied} changes. {errors} errors.")

        # Refresh the library view
        self.gui.library_view.model().refresh()

        self.accept()

    def _apply_change(self, change: SyncChange):
        """Apply a single change to Calibre."""
        column = self._get_column_for_field(change.field)
        if not column:
            return

        value = change.new_value

        # Handle different column types
        if column == "rating":
            # Built-in rating
            self.db.set_field("rating", {change.calibre_id: int(value) if value else None})
        elif column.startswith("#"):
            # Custom column - need to determine type
            col_info = self.db.custom_field_metadata(column)
            if col_info:
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
