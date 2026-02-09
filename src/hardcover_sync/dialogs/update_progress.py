"""
Update reading progress dialog.

This dialog allows the user to update reading progress for selected books.
"""

from qt.core import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QApplication,
)

from .base import HardcoverDialogBase


class UpdateProgressDialog(HardcoverDialogBase):
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
        super().__init__(parent, plugin_action, book_ids)

        # Get book info (resolve slugs via API)
        api = self._get_api()
        self.book_info = self._get_book_info(api)

        self.setWindowTitle("Update Reading Progress")
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Check if any books are linked
        if not self.book_info:
            self._setup_not_linked_ui(layout)
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

    def _load_current_progress(self):
        """Load current progress from Hardcover for single book."""
        api = self._get_api()
        if not api:
            return

        try:
            hc_id = self.book_info[0]["hardcover_id"]
            user_book = api.get_user_book(hc_id)
            if user_book and user_book.current_progress_pages:
                self.page_spinbox.setValue(user_book.current_progress_pages)
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
                    # Update progress via user_book_reads
                    if page_num > 0:
                        if user_book.latest_read:
                            # Update existing read entry
                            api.update_user_book_read(
                                user_book.latest_read.id,
                                progress_pages=page_num,
                            )
                        else:
                            # Create new read entry
                            api.insert_user_book_read(
                                user_book.id,
                                progress_pages=page_num,
                            )
                    elif user_book.latest_read:
                        # Clear progress by deleting the read entry
                        api.delete_user_book_read(user_book.latest_read.id)
                else:
                    # Add to library with "Currently Reading" status
                    new_user_book = api.add_book_to_library(
                        book_id=book["hardcover_id"],
                        status_id=2,  # Currently Reading
                    )
                    # Add progress via a read entry
                    if page_num > 0:
                        api.insert_user_book_read(
                            new_user_book.id,
                            progress_pages=page_num,
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
