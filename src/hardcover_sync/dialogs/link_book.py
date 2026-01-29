"""
Link Book dialog for Hardcover Sync plugin.

This dialog allows users to search for and link a Calibre book
to a Hardcover book.
"""

from qt.core import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    Qt,
    QVBoxLayout,
)

from ..api import Book, HardcoverAPI
from ..config import get_plugin_prefs
from ..matcher import MatchResult, search_for_calibre_book


class LinkBookDialog(QDialog):
    """
    Dialog for linking a Calibre book to Hardcover.

    Shows search results and allows the user to select the correct match.
    """

    def __init__(self, parent, db, book_id: int, book_title: str, book_authors: list[str]):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            db: Calibre database API.
            book_id: The Calibre book ID.
            book_title: The book title from Calibre.
            book_authors: The book authors from Calibre.
        """
        super().__init__(parent)
        self.db = db
        self.book_id = book_id
        self.book_title = book_title
        self.book_authors = book_authors
        self.selected_book: Book | None = None
        self.results: list[MatchResult] = []

        self.setWindowTitle("Link to Hardcover")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self._setup_ui()
        self._initial_search()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Book info
        info_label = QLabel(f"<b>Calibre Book:</b> {self.book_title}")
        if self.book_authors:
            info_label.setText(
                f"<b>Calibre Book:</b> {self.book_title} by {', '.join(self.book_authors)}"
            )
        layout.addWidget(info_label)

        # Search row
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter title, author, or ISBN...")
        self.search_input.setText(self.book_title)
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
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Link")
        layout.addWidget(self.button_box)

    def _get_api(self) -> HardcoverAPI | None:
        """Get an API instance with the configured token."""
        prefs = get_plugin_prefs()
        token = prefs.get("api_token", "")
        if not token:
            self.status_label.setText("Error: No API token configured")
            return None
        return HardcoverAPI(token=token)

    def _initial_search(self):
        """Perform initial search for the book."""
        api = self._get_api()
        if not api:
            return

        self.status_label.setText("Searching...")
        self._update_ui()

        try:
            self.results = search_for_calibre_book(api, self.db, self.book_id)
            self._populate_results()

            if self.results:
                self.status_label.setText(f"Found {len(self.results)} result(s)")
            else:
                self.status_label.setText("No results found. Try a different search.")
        except Exception as e:
            self.status_label.setText(f"Search error: {e}")

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
                self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
                return

        self.selected_book = None
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def _on_double_click(self, item):
        """Handle double-click on a result row."""
        row = item.row()
        if 0 <= row < len(self.results):
            self.selected_book = self.results[row].book
            self.accept()

    def _update_ui(self):
        """Force UI update."""
        QApplication.processEvents()

    def get_selected_book(self) -> Book | None:
        """Get the selected Hardcover book."""
        return self.selected_book

    def get_selected_edition_id(self) -> int | None:
        """Get the edition ID for the selected book."""
        if self.selected_book and self.selected_book.editions:
            return self.selected_book.editions[0].id
        return None
