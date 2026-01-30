"""
Update reading progress dialog.

This dialog allows the user to update reading progress for selected books.
"""

from qt.core import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QApplication,
)

from ..api import HardcoverAPI
from ..config import get_plugin_prefs
from ..matcher import get_hardcover_id


class UpdateProgressDialog(QDialog):
    """
    Dialog for updating reading progress on Hardcover.

    Allows entering current page number for the selected book.
    """

    def __init__(self, parent, plugin_action, book_ids: list[int]):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            plugin_action: The plugin's InterfaceAction.
            book_ids: List of Calibre book IDs to update.
        """
        super().__init__(parent)
        self.plugin_action = plugin_action
        self.gui = plugin_action.gui
        self.db = self.gui.current_db.new_api
        self.prefs = get_plugin_prefs()
        self.book_ids = book_ids

        # Get book info
        self.book_info = self._get_book_info()

        self.setWindowTitle("Update Reading Progress")
        self.setMinimumWidth(400)

        self._setup_ui()

    def _get_book_info(self) -> list[dict]:
        """Get info about books to update."""
        books = []
        for book_id in self.book_ids:
            hc_id = get_hardcover_id(self.db, book_id)
            if hc_id:
                title = self.db.field_for("title", book_id) or "Unknown"
                books.append(
                    {
                        "calibre_id": book_id,
                        "hardcover_id": hc_id,
                        "title": title,
                    }
                )
        return books

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Check if any books are linked
        if not self.book_info:
            label = QLabel(
                "None of the selected books are linked to Hardcover.\n"
                "Use 'Link to Hardcover' first."
            )
            layout.addWidget(label)

            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            button_box.rejected.connect(self.reject)
            layout.addWidget(button_box)
            return

        # Show which book(s) will be updated
        if len(self.book_info) == 1:
            book_label = QLabel(f"<b>{self.book_info[0]['title']}</b>")
        else:
            book_label = QLabel(f"<b>{len(self.book_info)} books</b> will be updated.")
        layout.addWidget(book_label)

        # Current page input
        page_layout = QHBoxLayout()
        page_label = QLabel("Current page:")
        page_layout.addWidget(page_label)

        self.page_spinbox = QSpinBox()
        self.page_spinbox.setRange(0, 10000)
        self.page_spinbox.setValue(0)
        self.page_spinbox.setMinimumWidth(100)
        page_layout.addWidget(self.page_spinbox)

        page_layout.addStretch()
        layout.addLayout(page_layout)

        # Info text
        info_label = QLabel(
            "<i>This will set reading progress on Hardcover.<br>Set to 0 to clear progress.</i>"
        )
        layout.addWidget(info_label)

        layout.addStretch()

        # Status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Button box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_apply)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Update Progress")
        layout.addWidget(self.button_box)

        # Pre-populate with current progress if single book
        if len(self.book_info) == 1:
            self._load_current_progress()

    def _get_api(self) -> HardcoverAPI | None:
        """Get an API instance with the configured token."""
        token = self.prefs.get("api_token", "")
        if not token:
            self.status_label.setText("Error: No API token configured.")
            return None
        return HardcoverAPI(token=token)

    def _load_current_progress(self):
        """Load current progress from Hardcover for single book."""
        api = self._get_api()
        if not api:
            return

        try:
            hc_id = self.book_info[0]["hardcover_id"]
            user_book = api.get_user_book(hc_id)
            if user_book and user_book.progress_pages:
                self.page_spinbox.setValue(user_book.progress_pages)
        except Exception:  # noqa: S110
            pass  # Non-critical: just show default values if we can't load current progress

    def _on_apply(self):
        """Apply the progress update."""
        api = self._get_api()
        if not api:
            return

        page_num = self.page_spinbox.value()

        self.button_box.setEnabled(False)
        self.status_label.setText("Updating progress...")
        QApplication.processEvents()

        success = 0
        errors = []

        for book in self.book_info:
            try:
                # Get the user_book to update
                user_book = api.get_user_book(book["hardcover_id"])

                if user_book:
                    # Update existing entry
                    api.update_user_book(
                        user_book.id,
                        progress_pages=page_num if page_num > 0 else None,
                    )
                else:
                    # Add to library with "Currently Reading" status
                    api.add_book_to_library(
                        book_id=book["hardcover_id"],
                        status_id=2,  # Currently Reading
                        progress_pages=page_num if page_num > 0 else None,
                    )

                # Update Calibre column if configured
                progress_col = self.prefs.get("progress_column")
                if progress_col:
                    self._update_calibre_progress(book["calibre_id"], progress_col, page_num)

                success += 1

            except Exception as e:
                errors.append(f"{book['title']}: {e}")

        self.button_box.setEnabled(True)

        if errors:
            from calibre.gui2 import error_dialog

            error_dialog(
                self,
                "Update Progress Error",
                f"Failed to update {len(errors)} book(s):",
                det_msg="\n".join(errors),
                show=True,
            )

        if success > 0:
            self.status_label.setText(f"Updated {success} book(s).")
            # Refresh library view
            self.gui.library_view.model().refresh()
            self.accept()
        else:
            self.status_label.setText("No books were updated.")

    def _update_calibre_progress(self, book_id: int, column: str, page_num: int):
        """Update the progress column in Calibre."""
        try:
            if column.startswith("#"):
                self.db.set_field(column, {book_id: page_num if page_num > 0 else None})
        except Exception:  # noqa: S110
            pass  # Column update is best-effort, don't interrupt user flow
