"""
Base dialog class for Hardcover Sync plugin.

This module provides a common base class for all Hardcover dialogs,
consolidating shared functionality like API access and book info retrieval.
"""

from qt.core import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from ..api import HardcoverAPI
from ..config import get_plugin_prefs
from ..matcher import get_hardcover_id


class HardcoverDialogBase(QDialog):
    """
    Base class for Hardcover dialogs.

    Provides common functionality for dialogs that operate on selected books.
    """

    def __init__(self, parent, plugin_action, book_ids: list[int]):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            plugin_action: The plugin's InterfaceAction.
            book_ids: List of Calibre book IDs to operate on.
        """
        super().__init__(parent)
        self.plugin_action = plugin_action
        self.gui = plugin_action.gui
        self.db = self.gui.current_db.new_api
        self.prefs = get_plugin_prefs()
        self.book_ids = book_ids

        # Status label for showing messages (set by subclasses in _setup_ui)
        self.status_label: QLabel | None = None

    def _get_api(self) -> HardcoverAPI | None:
        """Get an API instance with the configured token."""
        token = self.prefs.get("api_token", "")
        if not token:
            if self.status_label:
                self.status_label.setText("Error: No API token configured.")
            return None
        return HardcoverAPI(token=token)

    def _get_book_info(self) -> list[dict]:
        """
        Get info about books that are linked to Hardcover.

        Returns:
            List of dicts with calibre_id, hardcover_id, and title.
        """
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

    def _setup_not_linked_ui(self, layout: QVBoxLayout):
        """
        Setup UI for when no books are linked to Hardcover.

        Args:
            layout: The layout to add widgets to.
        """
        label = QLabel(
            "None of the selected books are linked to Hardcover.\nUse 'Link to Hardcover' first."
        )
        layout.addWidget(label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
