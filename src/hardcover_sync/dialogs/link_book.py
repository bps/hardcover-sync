"""
Link Book dialog for Hardcover Sync plugin.

This dialog allows users to search for and link Calibre books
to Hardcover books. Supports cycling through multiple selected books.
"""

from __future__ import annotations

from dataclasses import dataclass

from qt.core import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    Qt,
    QVBoxLayout,
)

from ..api import HardcoverAPI
from ..config import get_plugin_prefs
from ..matcher import MatchResult, search_for_calibre_book, set_hardcover_id
from ..models import Book


@dataclass
class PendingLink:
    """A link that has been chosen but not yet committed to the database."""

    calibre_book_id: int
    hardcover_book_id: int
    edition_id: int | None
    auto: bool


class LinkBookDialog(QDialog):
    """
    Dialog for linking Calibre books to Hardcover.

    Supports single or multiple books. When multiple books are provided,
    the user cycles through each one. Books with a single 100% confidence
    match are auto-linked and skipped.

    All links are staged as pending and only committed to the database
    when the user finishes (accept). Cancelling discards all pending links.
    """

    def __init__(
        self,
        parent,
        db,
        books: list[tuple[int, str, list[str]]],
    ):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            db: Calibre database API.
            books: List of (book_id, title, authors) tuples to link.
        """
        super().__init__(parent)
        self.db = db
        self.books = books
        self.current_index = 0
        self.selected_book: Book | None = None
        self.results: list[MatchResult] = []
        self.pending_links: list[PendingLink] = []
        self.skipped_count = 0

        self.setWindowTitle("Link to Hardcover")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self._setup_ui()
        # Defer initial search until the event loop is running so that
        # accept() from auto-link actually closes the dialog.
        QTimer.singleShot(0, self._load_current_book)

    @property
    def linked_count(self) -> int:
        return len(self.pending_links)

    @property
    def auto_linked_count(self) -> int:
        return sum(1 for link in self.pending_links if link.auto)

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Progress label (e.g. "Book 1 of 5")
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #666;")
        layout.addWidget(self.progress_label)

        # Book info
        self.info_label = QLabel("")
        layout.addWidget(self.info_label)

        # Search row
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter title, author, or ISBN...")
        self.search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_input, 1)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._on_search)
        search_layout.addWidget(self.search_button)

        layout.addLayout(search_layout)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Title", "Author", "Year", "Match"])
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_table.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.results_table)

        # Status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Button box
        button_layout = QHBoxLayout()

        self.skip_button = QPushButton("Skip")
        self.skip_button.setToolTip("Skip this book without linking")
        self.skip_button.clicked.connect(self._on_skip)
        button_layout.addWidget(self.skip_button)

        button_layout.addStretch()

        self.link_button = QPushButton("Link")
        self.link_button.setEnabled(False)
        self.link_button.setDefault(True)
        self.link_button.clicked.connect(self._on_link)
        button_layout.addWidget(self.link_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    @property
    def _is_multi(self) -> bool:
        return len(self.books) > 1

    @property
    def _current_book(self) -> tuple[int, str, list[str]]:
        return self.books[self.current_index]

    def _get_api(self) -> HardcoverAPI | None:
        """Get an API instance with the configured token."""
        prefs = get_plugin_prefs()
        token = prefs.get("api_token", "")
        if not token:
            self.status_label.setText("Error: No API token configured")
            return None
        return HardcoverAPI(token=token)

    def _load_current_book(self):
        """Load and search for the current book in the queue."""
        book_id, title, authors = self._current_book

        # Update progress
        if self._is_multi:
            self.progress_label.setText(
                f"Book {self.current_index + 1} of {len(self.books)}"
                f"  ({self.linked_count} linked, {self.skipped_count} skipped)"
            )
            self.progress_label.setVisible(True)
        else:
            self.progress_label.setVisible(False)

        # Update book info
        if authors:
            self.info_label.setText(f"<b>Calibre Book:</b> {title} by {', '.join(authors)}")
        else:
            self.info_label.setText(f"<b>Calibre Book:</b> {title}")

        # Pre-fill search
        self.search_input.setText(title)

        # Reset state
        self.selected_book = None
        self.link_button.setEnabled(False)
        self.results_table.setRowCount(0)
        self.results = []

        # Update button text
        self._update_button_text()

        # Search
        self._initial_search()

    def _update_button_text(self):
        """Update button labels based on position in the queue."""
        is_last = self.current_index >= len(self.books) - 1

        if self._is_multi and not is_last:
            self.link_button.setText("Link && Next")
            self.skip_button.setText("Skip")
            self.skip_button.setVisible(True)
        else:
            self.link_button.setText("Link")
            self.skip_button.setVisible(self._is_multi)

    def _initial_search(self):
        """Perform initial search for the current book."""
        api = self._get_api()
        if not api:
            return

        book_id = self._current_book[0]

        self.status_label.setText("Searching...")
        self._update_ui()

        try:
            self.results = search_for_calibre_book(api, self.db, book_id)
            self._populate_results()

            # Auto-link: single result with 100% confidence
            auto_link = get_plugin_prefs().get("auto_link_exact_match", True)
            if auto_link and len(self.results) == 1 and self.results[0].confidence >= 1.0:
                self._stage_auto_link(self.results[0])
                return

            if self.results:
                self.status_label.setText(f"Found {len(self.results)} result(s)")
            else:
                self.status_label.setText("No results found. Try a different search.")
        except Exception as e:
            self.status_label.setText(f"Search error: {e}")

    def _stage_auto_link(self, result: MatchResult):
        """Stage an auto-link for a perfect match and advance."""
        book_id = self._current_book[0]
        book = result.book
        if not book:
            return

        edition_id = book.editions[0].id if book.editions else None
        self.pending_links.append(
            PendingLink(
                calibre_book_id=book_id,
                hardcover_book_id=book.id,
                edition_id=edition_id,
                auto=True,
            )
        )

        if self._advance():
            return

        # Last book - finish
        self._finish()

    def _on_search(self):
        """Handle search button click."""
        query = self.search_input.text().strip()
        if not query:
            return

        api = self._get_api()
        if not api:
            return

        self.status_label.setText("Searching...")
        self.search_button.setEnabled(False)
        self._update_ui()

        try:
            books = api.search_books(query)
            self.results = [
                MatchResult(
                    book=book,
                    match_type="search",
                    confidence=0.5,  # Manual search has neutral confidence
                    message=f"{book.title}",
                )
                for book in books
            ]
            self._populate_results()

            if self.results:
                self.status_label.setText(f"Found {len(self.results)} result(s)")
            else:
                self.status_label.setText("No results found. Try a different search.")
        except Exception as e:
            self.status_label.setText(f"Search error: {e}")
        finally:
            self.search_button.setEnabled(True)

    def _populate_results(self):
        """Populate the results table."""
        self.results_table.setRowCount(len(self.results))

        for row, result in enumerate(self.results):
            book = result.book
            if not book:
                continue

            # Title
            title_item = QTableWidgetItem(book.title)
            title_item.setData(Qt.ItemDataRole.UserRole, row)  # Store index
            self.results_table.setItem(row, 0, title_item)

            # Author
            authors = ""
            if book.authors:
                authors = ", ".join(a.name for a in book.authors[:2])
                if len(book.authors) > 2:
                    authors += " et al."
            self.results_table.setItem(row, 1, QTableWidgetItem(authors))

            # Year
            year = ""
            if book.release_date:
                year = book.release_date[:4]
            self.results_table.setItem(row, 2, QTableWidgetItem(year))

            # Match confidence
            confidence = f"{int(result.confidence * 100)}%"
            match_item = QTableWidgetItem(confidence)
            self.results_table.setItem(row, 3, match_item)

        # Auto-select first row if results exist
        if self.results:
            self.results_table.selectRow(0)

    def _on_selection_changed(self):
        """Handle selection change in results table."""
        rows = self.results_table.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            if 0 <= row < len(self.results):
                self.selected_book = self.results[row].book
                self.link_button.setEnabled(True)
                return

        self.selected_book = None
        self.link_button.setEnabled(False)

    def _on_double_click(self, item):
        """Handle double-click on a result row."""
        row = item.row()
        if 0 <= row < len(self.results):
            self.selected_book = self.results[row].book
            self._on_link()

    def _on_link(self):
        """Stage a link for the current book and advance or finish."""
        if not self.selected_book:
            return

        book_id = self._current_book[0]
        edition_id = self.selected_book.editions[0].id if self.selected_book.editions else None
        self.pending_links.append(
            PendingLink(
                calibre_book_id=book_id,
                hardcover_book_id=self.selected_book.id,
                edition_id=edition_id,
                auto=False,
            )
        )

        if self._advance():
            return

        # Last book - finish
        self._finish()

    def _on_skip(self):
        """Skip the current book and advance or finish."""
        self.skipped_count += 1

        if self._advance():
            return

        # Last book - finish
        self._finish()

    def _finish(self):
        """Commit all pending links and accept the dialog."""
        for link in self.pending_links:
            set_hardcover_id(self.db, link.calibre_book_id, link.hardcover_book_id, link.edition_id)
        self.accept()

    def _advance(self) -> bool:
        """Advance to the next book. Returns True if there are more books."""
        if self.current_index < len(self.books) - 1:
            self.current_index += 1
            self._load_current_book()
            return True
        return False

    def _update_ui(self):
        """Force UI update."""
        QApplication.processEvents()

    def get_selected_book(self) -> Book | None:
        """Get the selected Hardcover book (for single-book mode compatibility)."""
        return self.selected_book

    def get_selected_edition_id(self) -> int | None:
        """Get the edition ID for the selected book."""
        if self.selected_book and self.selected_book.editions:
            return self.selected_book.editions[0].id
        return None
