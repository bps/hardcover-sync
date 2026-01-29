"""
Sync to Hardcover dialog.

This dialog syncs data from Calibre to Hardcover for selected books.
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
)

from ..api import HardcoverAPI, UserBook
from ..config import READING_STATUSES, STATUS_IDS, get_plugin_prefs


@dataclass
class SyncToChange:
    """Represents a change to be synced from Calibre to Hardcover."""

    calibre_id: int
    calibre_title: str
    hardcover_book_id: int
    user_book_id: int | None  # None if not in Hardcover library yet
    field: str  # status, rating, progress, date_started, date_read, review
    old_value: str | None  # Current Hardcover value
    new_value: str | None  # New value from Calibre
    apply: bool = True

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
        self.setMinimumHeight(500)

        self._setup_ui()
        self._analyze_books()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            f"This will sync {len(self.book_ids)} selected book(s) from Calibre to Hardcover. "
            "Only books with a Hardcover link will be synced."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Analyzing books...")
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

    def _get_api(self) -> HardcoverAPI | None:
        """Get an API instance."""
        token = self.prefs.get("api_token", "")
        if not token:
            self.status_label.setText("Error: No API token configured.")
            return None
        return HardcoverAPI(token=token)

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
                hc_user_book = None

            user_book_id = hc_user_book.id if hc_user_book else None

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

            # Compare rating
            if rating_col:
                calibre_rating = self._get_calibre_value(book_id, rating_col)
                if calibre_rating is not None:
                    # Convert Calibre rating to Hardcover scale (0-5)
                    if rating_col == "rating":
                        # Built-in rating is 0-10
                        hc_new_rating = calibre_rating / 2 if calibre_rating else None
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
                                old_value=str(hc_current_rating)
                                if hc_current_rating is not None
                                else "(empty)",
                                new_value=str(hc_new_rating),
                            )
                        )

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

        self.progress_bar.setVisible(False)
        self._populate_changes_table()

        if not_linked_count > 0:
            self.status_label.setText(
                f"Found {len(self.changes)} change(s) from {linked_count} linked book(s). "
                f"({not_linked_count} book(s) not linked to Hardcover)"
            )
        else:
            self.status_label.setText(
                f"Found {len(self.changes)} change(s) from {linked_count} book(s)."
            )

        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(len(self.changes) > 0)
        self._update_summary()

    def _get_calibre_value(self, book_id: int, column: str):
        """Get a value from a Calibre column."""
        if not column:
            return None
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

            # Hardcover value (current)
            self.changes_table.setItem(row, 3, QTableWidgetItem(change.old_value or ""))

            # Calibre value (new)
            new_item = QTableWidgetItem(change.new_value or "")
            new_item.setForeground(Qt.darkGreen)
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
        errors = 0

        # Group changes by book for efficient API calls
        changes_by_book = {}
        for change in changes_to_apply:
            key = (change.hardcover_book_id, change.user_book_id)
            if key not in changes_by_book:
                changes_by_book[key] = []
            changes_by_book[key].append(change)

        i = 0
        for (hc_book_id, user_book_id), book_changes in changes_by_book.items():
            try:
                self._apply_book_changes(api, hc_book_id, user_book_id, book_changes)
                applied += len(book_changes)
            except Exception as e:
                errors += len(book_changes)
                print(f"Error syncing book {hc_book_id}: {e}")

            i += len(book_changes)
            self.progress_bar.setValue(i)
            QApplication.processEvents()

        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Synced {applied} changes. {errors} errors.")

        self.accept()

    def _apply_book_changes(
        self,
        api: HardcoverAPI,
        hc_book_id: int,
        user_book_id: int | None,
        changes: list[SyncToChange],
    ):
        """Apply all changes for a single book."""
        # Build the update data
        update_data = {}
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
                update_data["rating"] = float(change.new_value) if change.new_value else None
            elif change.field == "progress":
                update_data["progress_pages"] = int(change.new_value) if change.new_value else None
            elif change.field == "date_started":
                update_data["started_at"] = change.new_value
            elif change.field == "date_read":
                update_data["finished_at"] = change.new_value
            elif change.field == "review":
                update_data["review"] = change.new_value

        if not update_data:
            return

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
