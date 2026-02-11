"""
Sync from Hardcover dialog.

This dialog fetches the user's Hardcover library and syncs data to Calibre.
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
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    Qt,
)

from ..api import HardcoverAPI
from ..config import READING_STATUSES, get_column_mappings, get_unmapped_columns
from ..models import UserBook
from ..sync import (
    NewBookAction,
    SyncChange,
    coerce_value_for_column,
    convert_rating_to_calibre,
    find_new_books,
    find_sync_from_changes,
)
from .base import HardcoverDialogBase


class SyncFromHardcoverDialog(HardcoverDialogBase):
    """
    Dialog for syncing data from Hardcover to Calibre.

    Shows a preview of changes and allows the user to select which to apply.
    """

    def __init__(self, parent: Any, plugin_action: Any, book_ids: list[int] | None = None) -> None:
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            plugin_action: The plugin's InterfaceAction (provides access to GUI/database).
            book_ids: Optional list of selected Calibre book IDs. If provided and not
                all books are selected, only these books will be synced.
        """
        super().__init__(parent, plugin_action, book_ids or [])
        self.changes: list[SyncChange] = []
        self.new_books: list[NewBookAction] = []
        self.hardcover_books: list[UserBook] = []

        # Determine sync scope: if a subset of books is selected, scope to those
        all_book_ids = self.db.all_book_ids()
        if book_ids and len(book_ids) < len(all_book_ids):
            self.scoped_book_ids: list[int] | None = book_ids
        else:
            self.scoped_book_ids = None

        self.setWindowTitle("Sync from Hardcover")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self._setup_ui()
        # Show diagnostic info immediately
        self._update_diagnostics()

    def _setup_ui(self) -> None:
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
        if self.scoped_book_ids is not None:
            self.fetch_button = QPushButton("Fetch Selected")
        else:
            self.fetch_button = QPushButton("Fetch Library")
        self.fetch_button.clicked.connect(self._on_fetch)
        fetch_layout.addWidget(self.fetch_button)

        # Checkbox to create new books
        self.create_books_checkbox = QCheckBox("Add books not in Calibre")
        self.create_books_checkbox.setToolTip(
            "Create new Calibre entries for Hardcover books that aren't in your library yet.\n"
            "When checked, a full library fetch is performed to discover unlinked books."
        )
        self.create_books_checkbox.setChecked(False)
        self.create_books_checkbox.stateChanged.connect(self._on_add_books_toggled)
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

    def _update_diagnostics(self) -> None:
        """Update the diagnostics panel with current status."""
        # Count linked books in scope
        linked_count = 0

        if self.scoped_book_ids is not None:
            scope_ids = self.scoped_book_ids
        else:
            scope_ids = list(self.db.all_book_ids())

        total_count = len(scope_ids)

        for book_id in scope_ids:
            identifiers = self.db.field_for("identifiers", book_id) or {}
            if identifiers.get("hardcover"):
                linked_count += 1

        # Scope label
        want_new_books = self.create_books_checkbox.isChecked()
        if self.scoped_book_ids is not None and not want_new_books:
            scope_text = f"<b>Scope:</b> {total_count} selected book(s)"
        else:
            all_count = len(list(self.db.all_book_ids()))
            scope_text = f"<b>Scope:</b> All books in library ({all_count})"

        if linked_count == 0:
            self.info_status_label.setText(
                f"{scope_text}, "
                f"<span style='color: red;'><b>0 linked to Hardcover</b></span><br>"
                "<i>Use 'Link to Hardcover...' to connect books first.</i>"
            )
        else:
            self.info_status_label.setText(
                f"{scope_text}, <b>{linked_count} linked to Hardcover</b>"
            )

        # Column mapping and warnings (delegate to base class)
        self._update_column_diagnostics(linked_count)

        # Update status message
        if not self.prefs.get("api_token"):
            self.status_label.setText(
                "No API token configured. Go to plugin settings to add your token."
            )
            self.fetch_button.setEnabled(False)
        elif linked_count == 0:
            if self.scoped_book_ids is not None:
                self.status_label.setText(
                    "No selected books are linked to Hardcover. "
                    "Use 'Link to Hardcover...' to connect books first."
                )
            else:
                self.status_label.setText(
                    "No books are linked to Hardcover. Check 'Add books not in Calibre' "
                    "to import from your Hardcover library, or link existing books first."
                )
            self.fetch_button.setEnabled(True)  # Still allow fetching for new books
        else:
            if self.scoped_book_ids is not None:
                self.status_label.setText(
                    f"Click 'Fetch Selected' to sync {linked_count} linked book(s) from Hardcover."
                )
            else:
                self.status_label.setText("Click 'Fetch Library' to load your Hardcover books.")
            self.fetch_button.setEnabled(True)

    def _on_add_books_toggled(self) -> None:
        """Update scope display and fetch button when the add-books checkbox changes."""
        if self.scoped_book_ids is not None:
            if self.create_books_checkbox.isChecked():
                self.fetch_button.setText("Fetch Library")
            else:
                self.fetch_button.setText("Fetch Selected")
        self._update_diagnostics()

    def _on_fetch(self) -> None:
        """Fetch the user's Hardcover library."""
        api = self._get_api()
        if not api:
            return

        self.fetch_button.setEnabled(False)
        is_scoped = self.scoped_book_ids is not None
        want_new_books = self.create_books_checkbox.isChecked()
        if is_scoped and not want_new_books:
            self.status_label.setText("Fetching selected books from Hardcover...")
        else:
            self.status_label.setText("Fetching your Hardcover library...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        QApplication.processEvents()

        try:
            # Build the map of linked books for the current scope
            hc_to_calibre = self._build_hardcover_to_calibre_map()

            if want_new_books:
                # Need a full library fetch to discover unlinked books
                self.hardcover_books = self._fetch_all_books(api)
                # Build the full map so we correctly identify which books are new
                full_hc_to_calibre = self._build_hardcover_to_calibre_map(full=True)
            elif is_scoped and hc_to_calibre:
                # Targeted fetch: only request the specific books by slug
                hc_slugs = list(hc_to_calibre.keys())
                self.hardcover_books = self._fetch_books_by_slugs(api, hc_slugs)
                full_hc_to_calibre = hc_to_calibre
            else:
                # Full library fetch
                self.hardcover_books = self._fetch_all_books(api)
                full_hc_to_calibre = hc_to_calibre

            total = len(self.hardcover_books)
            linked_count = sum(
                1
                for hb in self.hardcover_books
                if (hb.book.slug if hb.book else None) in hc_to_calibre
            )
            unlinked_count = total - linked_count

            self.status_label.setText(
                f"Found {total} books in Hardcover library, "
                f"{linked_count} linked to Calibre. Analyzing changes..."
            )
            QApplication.processEvents()

            # Find changes for linked books
            self.changes = self._find_changes(hc_to_calibre)

            # Find new books to create (if checkbox is checked)
            self.new_books = []
            if want_new_books:
                self.new_books = self._find_new_books(full_hc_to_calibre)

            self._populate_changes_tree()

            # Update UI
            self.progress_bar.setVisible(False)
            has_items = len(self.changes) > 0 or len(self.new_books) > 0
            self.expand_all_button.setEnabled(has_items)
            self.collapse_all_button.setEnabled(has_items)
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(has_items)
            self._update_summary()

            # Detailed status message
            if not self.changes and not self.new_books:
                if linked_count == 0:
                    self.status_label.setText(
                        f"Found {total} books in Hardcover library, "
                        "but none are linked to Calibre books. "
                        "Use 'Link to Hardcover...' to connect them."
                    )
                else:
                    # Check if columns are mapped
                    unmapped = get_unmapped_columns(self.prefs)
                    if len(unmapped) == 6:  # All unmapped
                        self.status_label.setText(
                            f"Found {total} Hardcover books, "
                            f"{linked_count} linked. <b>No columns are mapped!</b> "
                            "Go to plugin settings to map Calibre columns "
                            "to Hardcover fields."
                        )
                    else:
                        self.status_label.setText(
                            f"All {linked_count} linked books are in sync "
                            "with Hardcover. No changes needed."
                        )
            else:
                parts = []
                if self.changes:
                    parts.append(f"{len(self.changes)} change(s)")
                if self.new_books:
                    parts.append(f"{len(self.new_books)} new book(s) to add")
                status = f"Found {', '.join(parts)} across {linked_count} linked books."
                if unlinked_count > 0 and not self.create_books_checkbox.isChecked():
                    status += (
                        f" ({unlinked_count} Hardcover book(s) not linked"
                        " - check 'Add books' to include)"
                    )
                self.status_label.setText(status)

        except Exception as e:
            self.status_label.setText(f"Error fetching library: {e}")
            self.progress_bar.setVisible(False)
        finally:
            self.fetch_button.setEnabled(True)

    def _fetch_all_books(self, api: HardcoverAPI) -> list[UserBook]:
        """Fetch all books from the user's Hardcover library.

        Deduplicates by book_id, keeping the most recently updated entry
        (the API returns results ordered by updated_at desc).
        """
        all_books: list[UserBook] = []
        seen_book_ids: set[int] = set()
        offset = 0
        limit = 100

        while True:
            batch = api.get_user_books(limit=limit, offset=offset)
            for ub in batch:
                if ub.book_id not in seen_book_ids:
                    seen_book_ids.add(ub.book_id)
                    all_books.append(ub)

            if len(batch) < limit:
                break

            offset += limit
            QApplication.processEvents()

        return all_books

    def _fetch_books_by_slugs(self, api: HardcoverAPI, slugs: list[str]) -> list[UserBook]:
        """Fetch specific books from the user's Hardcover library by slugs."""
        return api.get_user_books_by_slugs(slugs)

    def _find_changes(self, hc_to_calibre: dict[str, int] | None = None) -> list[SyncChange]:
        """Find all changes between Hardcover and Calibre."""
        if hc_to_calibre is None:
            hc_to_calibre = self._build_hardcover_to_calibre_map()

        return find_sync_from_changes(
            hardcover_books=self.hardcover_books,
            hc_to_calibre=hc_to_calibre,
            get_calibre_value=self._get_calibre_value,
            get_calibre_title=lambda book_id: self.db.field_for("title", book_id) or "Unknown",
            prefs=self.prefs,
            get_column_metadata=self._get_custom_column_metadata,
        )

    def _find_new_books(self, hc_to_calibre: dict[str, int]) -> list[NewBookAction]:
        """Find Hardcover books that aren't in Calibre yet."""
        sync_statuses = self.prefs.get("sync_statuses", [])
        new_books = find_new_books(
            hardcover_books=self.hardcover_books,
            hc_to_calibre=hc_to_calibre,
            sync_statuses=sync_statuses if sync_statuses else None,
        )
        # Sort by title
        new_books.sort(key=lambda x: x.title.lower())
        return new_books

    def _build_hardcover_to_calibre_map(self, full: bool = False) -> dict[str, int]:
        """Build a map from Hardcover slug to Calibre book ID.

        When scoped to selected books, only those books are included unless
        ``full=True`` is passed, which always covers the entire library.
        The full variant is used for new-book discovery.
        """
        hc_to_calibre = {}

        if full or self.scoped_book_ids is None:
            book_ids = list(self.db.all_book_ids())
        else:
            book_ids = self.scoped_book_ids

        for book_id in book_ids:
            identifiers = self.db.field_for("identifiers", book_id) or {}
            hc_id = identifiers.get("hardcover")
            if hc_id:
                hc_to_calibre[hc_id] = book_id

        return hc_to_calibre

    def _populate_changes_tree(self) -> None:
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

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:  # type: ignore[reportInvalidTypeForm]
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

    def _set_children_checked(self, item: QTreeWidgetItem, checked: bool) -> None:  # type: ignore[reportInvalidTypeForm]
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

    def _update_parent_check_state(self, parent: QTreeWidgetItem) -> None:  # type: ignore[reportInvalidTypeForm]
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

    def _sync_parent_check_states(self) -> None:
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

    def _update_summary(self) -> None:
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

    def _on_apply(self) -> None:
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

        try:
            self._set_column_value(change.calibre_id, column, change.api_value)
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

        # Set identifiers - link to Hardcover (prefer slug, fall back to numeric ID)
        mi.set_identifiers(
            {"hardcover": new_book.hardcover_slug or str(new_book.hardcover_book_id)}
        )

        # Set ISBN if available
        if new_book.isbn:
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
            from ..matcher import set_hardcover_slug

            set_hardcover_slug(
                self.db, book_id, new_book.hardcover_slug or str(new_book.hardcover_book_id)
            )

            # Apply all Hardcover user data to the new book
            self._apply_user_book_data(book_id, new_book.user_book)

        return book_id

    def _apply_user_book_data(self, book_id: int, user_book: UserBook) -> None:
        """
        Apply Hardcover user book data to a Calibre book.

        This sets status, rating, progress, dates, and review based on
        the user's Hardcover data and column mappings.
        """
        from datetime import datetime

        # Get column mappings
        col = get_column_mappings(self.prefs)
        status_col = col.get("status", "")
        rating_col = col.get("rating", "")
        progress_col = col.get("progress", "")
        date_started_col = col.get("date_started", "")
        date_read_col = col.get("date_read", "")
        review_col = col.get("review", "")

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
            col_info = self._get_custom_column_metadata(rating_col)
            rating_value_str, _ = convert_rating_to_calibre(user_book.rating, rating_col, col_info)
            # Convert string back to appropriate type for Calibre
            if rating_col == "rating" or (col_info and col_info.get("datatype") == "rating"):
                rating_value = int(rating_value_str)
            else:
                rating_value = float(rating_value_str)
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

    def _set_column_value(self, book_id: int, column: str, value: Any) -> None:
        """Set a column value with appropriate type conversion."""
        if column == "rating":
            self.db.set_field("rating", {book_id: int(value) if value else None})
        elif column.startswith("#"):
            col_info = self._get_custom_column_metadata(column)
            if col_info:
                datatype = col_info.get("datatype", "text")
                value = coerce_value_for_column(value, datatype)
            self.db.set_field(column, {book_id: value})
        else:
            self.db.set_field(column, {book_id: value})

    def _get_column_for_field(self, field: str) -> str | None:
        """Get the Calibre column name for a sync field."""
        col = get_column_mappings(self.prefs).get(field)
        return col or None
