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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    Qt,
)

from ..api import HardcoverAPI, UserBook
from ..config import READING_STATUSES, get_plugin_prefs


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
class SyncChange:
    """Represents a change to be synced from Hardcover to Calibre."""

    calibre_id: int
    calibre_title: str
    hardcover_book_id: int
    field: str  # status, rating, progress, date_started, date_read, review
    old_value: str | None  # Display value (e.g., stars for rating)
    new_value: str | None  # Display value (e.g., stars for rating)
    raw_value: str | None = None  # Raw value for applying (if different from display)
    apply: bool = True  # Whether to apply this change

    @property
    def api_value(self) -> str | None:
        """Get the value to apply to Calibre."""
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


@dataclass
class NewBookAction:
    """Represents a new book to create in Calibre from Hardcover."""

    hardcover_book_id: int
    title: str
    authors: list[str]
    user_book: UserBook
    isbn: str | None = None
    release_date: str | None = None
    apply: bool = True

    @property
    def author_string(self) -> str:
        """Get authors as a comma-separated string."""
        return ", ".join(self.authors) if self.authors else "Unknown"


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
        self.new_books: list[NewBookAction] = []
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

        # Fetch button and options
        fetch_layout = QHBoxLayout()
        self.fetch_button = QPushButton("Fetch Library")
        self.fetch_button.clicked.connect(self._on_fetch)
        fetch_layout.addWidget(self.fetch_button)

        # Checkbox to create new books
        self.create_books_checkbox = QCheckBox("Add books not in Calibre")
        self.create_books_checkbox.setToolTip(
            "Create new Calibre entries for Hardcover books that aren't in your library yet"
        )
        self.create_books_checkbox.setChecked(False)
        fetch_layout.addWidget(self.create_books_checkbox)

        fetch_layout.addStretch()

        # Expand/Collapse all buttons
        self.expand_all_button = QPushButton("Expand All")
        self.expand_all_button.clicked.connect(lambda: self.changes_tree.expandAll())
        self.expand_all_button.setEnabled(False)
        fetch_layout.addWidget(self.expand_all_button)

        self.collapse_all_button = QPushButton("Collapse All")
        self.collapse_all_button.clicked.connect(lambda: self.changes_tree.collapseAll())
        self.collapse_all_button.setEnabled(False)
        fetch_layout.addWidget(self.collapse_all_button)

        layout.addLayout(fetch_layout)

        # Changes tree (hierarchical view with books as parents, changes as children)
        self.changes_tree = QTreeWidget()
        self.changes_tree.setHeaderLabels(["Book / Field", "Current Value", "New Value"])
        self.changes_tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.changes_tree.setRootIsDecorated(True)
        self.changes_tree.setIndentation(20)
        self.changes_tree.itemChanged.connect(self._on_item_changed)

        header = self.changes_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.changes_tree)

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
        if not self.prefs.get("api_token"):
            self.status_label.setText(
                "No API token configured. Go to plugin settings to add your token."
            )
            self.fetch_button.setEnabled(False)
        elif linked_count == 0:
            self.status_label.setText(
                "No books are linked to Hardcover. Check 'Add books not in Calibre' "
                "to import from your Hardcover library, or link existing books first."
            )
            self.fetch_button.setEnabled(True)  # Still allow fetching for new books
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

            # Find changes for linked books
            self.changes = self._find_changes(hc_to_calibre)

            # Find new books to create (if checkbox is checked)
            self.new_books = []
            if self.create_books_checkbox.isChecked():
                self.new_books = self._find_new_books(hc_to_calibre)

            self._populate_changes_tree()

            # Update UI
            self.progress_bar.setVisible(False)
            has_items = len(self.changes) > 0 or len(self.new_books) > 0
            self.expand_all_button.setEnabled(has_items)
            self.collapse_all_button.setEnabled(has_items)
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(has_items)
            self._update_summary()

            # Detailed status message
            unmatched_count = len(self.hardcover_books) - matched_count
            if not self.changes and not self.new_books:
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
                parts = []
                if self.changes:
                    parts.append(f"{len(self.changes)} change(s)")
                if self.new_books:
                    parts.append(f"{len(self.new_books)} new book(s) to add")
                status = (
                    f"Found {', '.join(parts)} from {len(self.hardcover_books)} Hardcover books."
                )
                if unmatched_count > 0 and not self.create_books_checkbox.isChecked():
                    status += f" ({unmatched_count} not in Calibre - check 'Add books' to include)"
                self.status_label.setText(status)

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
                # Convert Hardcover rating (0-5) to Calibre scale
                if rating_col == "rating":
                    # Built-in rating is 0-10 (displayed as stars)
                    new_rating = str(int(hc_book.rating * 2))
                    # Convert current Calibre value to 0-5 for star display
                    current_for_stars = current / 2 if current else None
                elif rating_col.startswith("#"):
                    # Custom column - check if it's a rating type
                    col_info = self._get_custom_column_metadata(rating_col)
                    if col_info and col_info.get("datatype") == "rating":
                        # Custom rating columns also use 0-10 internally
                        new_rating = str(int(hc_book.rating * 2))
                        current_for_stars = current / 2 if current else None
                    else:
                        # Other column types (int, float) - store as 0-5
                        new_rating = str(hc_book.rating)
                        current_for_stars = float(current) if current else None
                else:
                    new_rating = str(hc_book.rating)
                    current_for_stars = float(current) if current else None

                if str(current) != new_rating:
                    changes.append(
                        SyncChange(
                            calibre_id=calibre_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book.book_id,
                            field="rating",
                            old_value=format_rating_as_stars(current_for_stars),
                            new_value=format_rating_as_stars(hc_book.rating),
                            raw_value=new_rating,
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

    def _find_new_books(self, hc_to_calibre: dict[int, int]) -> list[NewBookAction]:
        """Find Hardcover books that aren't in Calibre yet."""
        new_books = []

        for hc_book in self.hardcover_books:
            # Skip books that are already linked to Calibre
            if hc_book.book_id in hc_to_calibre:
                continue

            # Skip if no book metadata
            if not hc_book.book:
                continue

            # Extract metadata
            title = hc_book.book.title
            authors = []
            if hc_book.book.authors:
                authors = [a.name for a in hc_book.book.authors]

            # Get ISBN from edition if available
            isbn = None
            if hc_book.edition:
                isbn = hc_book.edition.isbn_13 or hc_book.edition.isbn_10

            # Get release date
            release_date = hc_book.book.release_date

            new_books.append(
                NewBookAction(
                    hardcover_book_id=hc_book.book_id,
                    title=title,
                    authors=authors,
                    user_book=hc_book,
                    isbn=isbn,
                    release_date=release_date,
                )
            )

        # Sort by title
        new_books.sort(key=lambda x: x.title.lower())
        return new_books

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

    def _populate_changes_tree(self):
        """Populate the changes tree with books as parents and changes as children."""
        self.changes_tree.clear()
        self.changes_tree.blockSignals(True)

        # Add new books section first (if any)
        if self.new_books:
            # Create a section header for new books
            new_books_header = QTreeWidgetItem()
            new_books_header.setText(0, f"New Books ({len(self.new_books)})")
            new_books_header.setFlags(new_books_header.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            new_books_header.setCheckState(0, Qt.CheckState.Checked)
            new_books_header.setData(0, Qt.ItemDataRole.UserRole, ("new_books_header", None))

            # Make header bold
            font = new_books_header.font(0)
            font.setBold(True)
            new_books_header.setFont(0, font)

            for new_book in self.new_books:
                book_item = QTreeWidgetItem(new_books_header)
                book_item.setText(0, new_book.title)
                book_item.setText(1, "(not in Calibre)")
                book_item.setText(2, new_book.author_string)
                book_item.setFlags(book_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                book_item.setCheckState(
                    0, Qt.CheckState.Checked if new_book.apply else Qt.CheckState.Unchecked
                )
                book_item.setData(0, Qt.ItemDataRole.UserRole, ("new_book", new_book))

            self.changes_tree.addTopLevelItem(new_books_header)

        # Group changes by calibre_id
        books: dict[int, list[SyncChange]] = {}
        for change in self.changes:
            if change.calibre_id not in books:
                books[change.calibre_id] = []
            books[change.calibre_id].append(change)

        # Add updates section header (if any changes)
        if books:
            updates_header = QTreeWidgetItem()
            updates_header.setText(0, f"Updates ({len(self.changes)} changes)")
            updates_header.setFlags(updates_header.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            updates_header.setCheckState(0, Qt.CheckState.Checked)
            updates_header.setData(0, Qt.ItemDataRole.UserRole, ("updates_header", None))

            font = updates_header.font(0)
            font.setBold(True)
            updates_header.setFont(0, font)

            # Sort books by title
            sorted_books = sorted(books.items(), key=lambda x: x[1][0].calibre_title.lower())

            # Create tree items for each book with changes
            for calibre_id, book_changes in sorted_books:
                book_title = book_changes[0].calibre_title
                change_count = len(book_changes)

                # Create parent item for the book
                book_item = QTreeWidgetItem(updates_header)
                book_item.setText(
                    0, f"{book_title} ({change_count} change{'s' if change_count != 1 else ''})"
                )
                book_item.setFlags(book_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                book_item.setCheckState(0, Qt.CheckState.Checked)
                book_item.setData(0, Qt.ItemDataRole.UserRole, ("book", calibre_id))

                # Make book title bold
                font = book_item.font(0)
                font.setBold(True)
                book_item.setFont(0, font)

                # Create child items for each change
                for change in book_changes:
                    change_item = QTreeWidgetItem(book_item)
                    change_item.setText(0, change.display_field)
                    change_item.setText(1, change.old_value or "(empty)")
                    change_item.setText(2, change.new_value or "(empty)")
                    change_item.setFlags(change_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    change_item.setCheckState(
                        0, Qt.CheckState.Checked if change.apply else Qt.CheckState.Unchecked
                    )
                    change_item.setData(0, Qt.ItemDataRole.UserRole, ("change", change))

            self.changes_tree.addTopLevelItem(updates_header)

        # Update parent check states to reflect children
        self._sync_parent_check_states()

        # Expand all by default
        self.changes_tree.expandAll()
        self.changes_tree.blockSignals(False)

        # Enable expand/collapse buttons
        has_items = len(self.changes) > 0 or len(self.new_books) > 0
        self.expand_all_button.setEnabled(has_items)
        self.collapse_all_button.setEnabled(has_items)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handle checkbox state changes in the tree."""
        if column != 0:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_data = data

        self.changes_tree.blockSignals(True)

        if item_type in ("new_books_header", "updates_header"):
            # Section header changed - update all children recursively
            checked = item.checkState(0) == Qt.CheckState.Checked
            self._set_children_checked(item, checked)

        elif item_type == "new_book":
            # Individual new book item changed
            new_book = item_data
            new_book.apply = item.checkState(0) == Qt.CheckState.Checked

            # Update parent header state
            parent = item.parent()
            if parent:
                self._update_parent_check_state(parent)

        elif item_type == "book":
            # Book item changed - update all child changes
            checked = item.checkState(0) == Qt.CheckState.Checked
            for i in range(item.childCount()):
                child = item.child(i)
                child.setCheckState(
                    0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )
                child_data = child.data(0, Qt.ItemDataRole.UserRole)
                if child_data and child_data[0] == "change":
                    child_data[1].apply = checked

            # Update parent header state
            parent = item.parent()
            if parent:
                self._update_parent_check_state(parent)

        elif item_type == "change":
            # Individual change item changed
            change = item_data
            change.apply = item.checkState(0) == Qt.CheckState.Checked

            # Update parent book item state
            parent = item.parent()
            if parent:
                self._update_parent_check_state(parent)
                # Also update grandparent (updates_header) if it exists
                grandparent = parent.parent()
                if grandparent:
                    self._update_parent_check_state(grandparent)

        self.changes_tree.blockSignals(False)
        self._update_summary()

    def _set_children_checked(self, item: QTreeWidgetItem, checked: bool):
        """Recursively set all children to checked/unchecked state."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            child_data = child.data(0, Qt.ItemDataRole.UserRole)
            if child_data:
                child_type, child_obj = child_data
                if child_type == "new_book":
                    child_obj.apply = checked
                elif child_type == "change":
                    child_obj.apply = checked
                elif child_type == "book":
                    # Recurse into book's children (individual changes)
                    self._set_children_checked(child, checked)

    def _update_parent_check_state(self, parent: QTreeWidgetItem):
        """Update parent checkbox based on children states."""
        checked_count = 0
        unchecked_count = 0
        total = parent.childCount()

        for i in range(total):
            state = parent.child(i).checkState(0)
            if state == Qt.CheckState.Checked:
                checked_count += 1
            elif state == Qt.CheckState.Unchecked:
                unchecked_count += 1
            # PartiallyChecked counts as neither fully checked nor unchecked

        if checked_count == total:
            parent.setCheckState(0, Qt.CheckState.Checked)
        elif unchecked_count == total:
            parent.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def _sync_parent_check_states(self):
        """Sync all parent check states to reflect their children after populating the tree."""
        for i in range(self.changes_tree.topLevelItemCount()):
            header = self.changes_tree.topLevelItem(i)
            if header is None:
                continue

            data = header.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                continue

            header_type, _ = data

            if header_type == "new_books_header":
                # Direct children are new_book items
                self._update_parent_check_state(header)

            elif header_type == "updates_header":
                # Children are book items, which have change items as children
                # First update each book item based on its changes
                for j in range(header.childCount()):
                    book_item = header.child(j)
                    if book_item is not None:
                        self._update_parent_check_state(book_item)

                # Then update the header based on book items
                self._update_parent_check_state(header)

    def _update_summary(self):
        """Update the summary label."""
        selected_changes = sum(1 for c in self.changes if c.apply)
        total_changes = len(self.changes)
        books_affected = len({c.calibre_id for c in self.changes if c.apply})

        selected_new = sum(1 for b in self.new_books if b.apply)
        total_new = len(self.new_books)

        parts = []
        if total_changes > 0:
            parts.append(
                f"<b>{selected_changes}</b> of {total_changes} changes "
                f"({books_affected} book{'s' if books_affected != 1 else ''})"
            )
        if total_new > 0:
            parts.append(f"<b>{selected_new}</b> of {total_new} new books")

        if parts:
            self.summary_label.setText(" | ".join(parts) + " selected.")
        else:
            self.summary_label.setText("No changes to apply.")

        has_selections = selected_changes > 0 or selected_new > 0
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(has_selections)

    def _on_apply(self):
        """Apply the selected changes and create new books."""
        changes_to_apply = [c for c in self.changes if c.apply]
        new_books_to_create = [b for b in self.new_books if b.apply]

        if not changes_to_apply and not new_books_to_create:
            self.reject()
            return

        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(False)
        self.status_label.setText("Applying changes...")
        self.progress_bar.setVisible(True)
        total_operations = len(changes_to_apply) + len(new_books_to_create)
        self.progress_bar.setRange(0, total_operations)
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        applied_changes = 0
        created_books = 0
        skipped = 0
        errors = []
        progress = 0

        # Create new books first
        for new_book in new_books_to_create:
            try:
                calibre_id = self._create_calibre_book(new_book)
                if calibre_id:
                    created_books += 1
                else:
                    skipped += 1
                    errors.append(f"{new_book.title}: Failed to create book")
            except Exception as e:
                errors.append(f"{new_book.title}: {e}")

            progress += 1
            self.progress_bar.setValue(progress)
            QApplication.processEvents()

        # Apply changes to existing books
        for change in changes_to_apply:
            try:
                success, error_msg = self._apply_change(change)
                if success:
                    applied_changes += 1
                else:
                    skipped += 1
                    if error_msg:
                        errors.append(f"{change.calibre_title}: {error_msg}")
            except Exception as e:
                errors.append(f"{change.calibre_title}: {e}")

            progress += 1
            self.progress_bar.setValue(progress)
            QApplication.processEvents()

        self.progress_bar.setVisible(False)

        # Build result message
        result_parts = []
        if created_books > 0:
            result_parts.append(f"Created {created_books} book(s)")
        if applied_changes > 0:
            result_parts.append(f"Applied {applied_changes} change(s)")
        if skipped > 0:
            result_parts.append(f"Skipped {skipped}")
        if errors:
            result_parts.append(f"{len(errors)} error(s)")

        result_msg = ". ".join(result_parts) + "." if result_parts else "No changes applied."

        if errors:
            # Show first few errors
            error_preview = "; ".join(errors[:3])
            if len(errors) > 3:
                error_preview += f" (+{len(errors) - 3} more)"
            result_msg += f"\nErrors: {error_preview}"

        self.status_label.setText(result_msg)

        if applied_changes > 0 or created_books > 0:
            # Refresh the library view
            self.gui.library_view.model().refresh()

        # Show summary dialog before closing
        from calibre.gui2 import info_dialog

        total_applied = applied_changes + created_books
        if errors:
            info_dialog(
                self,
                "Sync Complete (with errors)",
                f"Created {created_books} book(s), applied {applied_changes} change(s), "
                f"skipped {skipped}, {len(errors)} error(s).\n\n"
                f"Errors:\n" + "\n".join(errors[:10]),
                show=True,
            )
        elif total_applied > 0:
            msg_parts = []
            if created_books > 0:
                msg_parts.append(f"created {created_books} new book(s)")
            if applied_changes > 0:
                msg_parts.append(f"applied {applied_changes} change(s)")
            info_dialog(
                self,
                "Sync Complete",
                f"Successfully {' and '.join(msg_parts)} in your Calibre library.",
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

        value = change.api_value

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
                    # raw_value is already in 0-10 scale for rating columns
                    value = int(float(value)) if value else None

                self.db.set_field(column, {change.calibre_id: value})
            else:
                self.db.set_field(column, {change.calibre_id: value})

            return True, None

        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            return False, f"{e}\n\nTraceback:\n{tb}"

    def _create_calibre_book(self, new_book: NewBookAction) -> int | None:
        """
        Create a new book in Calibre from Hardcover data.

        Args:
            new_book: The NewBookAction containing book metadata.

        Returns:
            The new Calibre book ID, or None if creation failed.
        """
        from calibre.ebooks.metadata.book.base import Metadata

        # Create metadata object
        mi = Metadata(new_book.title)

        # Set authors
        if new_book.authors:
            mi.authors = new_book.authors
        else:
            mi.authors = ["Unknown"]

        # Set identifiers - link to Hardcover
        mi.set_identifiers({"hardcover": str(new_book.hardcover_book_id)})

        # Set ISBN if available
        if new_book.isbn:
            if len(new_book.isbn) == 13:
                mi.set_identifier("isbn", new_book.isbn)
            elif len(new_book.isbn) == 10:
                mi.set_identifier("isbn", new_book.isbn)

        # Set publication date if available
        if new_book.release_date:
            try:
                from datetime import datetime

                # Parse YYYY-MM-DD or YYYY format
                if len(new_book.release_date) >= 10:
                    pub_date = datetime.strptime(new_book.release_date[:10], "%Y-%m-%d")
                elif len(new_book.release_date) == 4:
                    pub_date = datetime.strptime(new_book.release_date, "%Y")
                else:
                    pub_date = None

                if pub_date:
                    mi.pubdate = pub_date
            except (ValueError, TypeError):
                pass  # Ignore invalid dates

        # Add the book to Calibre
        book_id = self.db.create_book_entry(mi)

        # Explicitly set the hardcover identifier (create_book_entry may not persist it)
        if book_id:
            from hardcover_sync.matcher import set_hardcover_id

            set_hardcover_id(self.db, book_id, new_book.hardcover_book_id)

            # Apply all Hardcover user data to the new book
            self._apply_user_book_data(book_id, new_book.user_book)

        return book_id

    def _apply_user_book_data(self, book_id: int, user_book: UserBook):
        """
        Apply Hardcover user book data to a Calibre book.

        This sets status, rating, progress, dates, and review based on
        the user's Hardcover data and column mappings.
        """
        from datetime import datetime

        # Get column mappings
        status_col = self.prefs.get("status_column", "")
        rating_col = self.prefs.get("rating_column", "")
        progress_col = self.prefs.get("progress_column", "")
        date_started_col = self.prefs.get("date_started_column", "")
        date_read_col = self.prefs.get("date_read_column", "")
        review_col = self.prefs.get("review_column", "")

        # Get status mappings
        status_mappings = self.prefs.get("status_mappings", {})

        # Apply status
        if status_col and user_book.status_id:
            status_value = status_mappings.get(
                str(user_book.status_id), READING_STATUSES.get(user_book.status_id, "")
            )
            if status_value:
                self._set_column_value(book_id, status_col, status_value)

        # Apply rating
        if rating_col and user_book.rating is not None:
            if rating_col == "rating":
                # Built-in rating is 0-10
                rating_value = int(user_book.rating * 2)
            elif rating_col.startswith("#"):
                col_info = self._get_custom_column_metadata(rating_col)
                if col_info and col_info.get("datatype") == "rating":
                    rating_value = int(user_book.rating * 2)
                else:
                    rating_value = user_book.rating
            else:
                rating_value = user_book.rating
            self._set_column_value(book_id, rating_col, rating_value)

        # Apply progress (from latest read)
        current_progress = user_book.current_progress_pages
        if progress_col and current_progress is not None:
            self._set_column_value(book_id, progress_col, current_progress)

        # Apply date started (from latest read)
        latest_started = user_book.latest_started_at
        if date_started_col and latest_started:
            try:
                date_value = datetime.fromisoformat(latest_started[:10])
                self._set_column_value(book_id, date_started_col, date_value)
            except (ValueError, TypeError):
                pass

        # Apply date read (from latest read)
        latest_finished = user_book.latest_finished_at
        if date_read_col and latest_finished:
            try:
                date_value = datetime.fromisoformat(latest_finished[:10])
                self._set_column_value(book_id, date_read_col, date_value)
            except (ValueError, TypeError):
                pass

        # Apply review
        if review_col and user_book.review:
            self._set_column_value(book_id, review_col, user_book.review)

    def _set_column_value(self, book_id: int, column: str, value):
        """Set a column value with appropriate type conversion."""
        if column == "rating":
            self.db.set_field("rating", {book_id: int(value) if value else None})
        elif column.startswith("#"):
            col_info = self._get_custom_column_metadata(column)
            if col_info:
                datatype = col_info.get("datatype")
                if datatype == "int":
                    value = int(value) if value else None
                elif datatype == "float":
                    value = float(value) if value else None
                elif datatype == "rating":
                    value = int(value) if value else None
                # datetime values are already datetime objects
            self.db.set_field(column, {book_id: value})
        else:
            self.db.set_field(column, {book_id: value})

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
