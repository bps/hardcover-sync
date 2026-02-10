"""
Remove from list dialog.

This dialog allows the user to remove selected books from a Hardcover list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qt.core import (
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QApplication,
    Qt,
)

from .base import HardcoverDialogBase


@dataclass
class ListBookInfo:
    """Information about a book's membership in a list."""

    list_id: int
    list_name: str
    list_book_id: int  # The ID needed to remove the book from the list


class RemoveFromListDialog(HardcoverDialogBase):
    """
    Dialog for removing books from a Hardcover list.

    Shows which lists contain the selected book(s) and allows removing them.
    """

    def __init__(self, parent: Any, plugin_action: Any, book_ids: list[int]) -> None:
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            plugin_action: The plugin's InterfaceAction.
            book_ids: List of Calibre book IDs to remove from lists.
        """
        super().__init__(parent, plugin_action, book_ids)
        self.list_memberships: dict[int, list[ListBookInfo]] = {}  # list_id -> list of memberships

        # Get book info (resolve slugs via API)
        api = self._get_api()
        self.book_info = self._get_book_info(api)

        self.setWindowTitle("Remove from Hardcover List")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

        self._setup_ui()
        self._load_list_memberships()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Check if any books are linked
        if not self.book_info:
            self._setup_not_linked_ui(layout)
            return

        # Show which book(s) will be processed
        if len(self.book_info) == 1:
            book_label = QLabel(f"Remove <b>{self.book_info[0]['title']}</b> from list:")
        else:
            book_label = QLabel(f"Remove <b>{len(self.book_info)} books</b> from list:")
        layout.addWidget(book_label)

        # Lists widget
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # Status label
        self.status_label = QLabel("Loading list memberships...")
        layout.addWidget(self.status_label)

        # Button box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_apply)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Remove from Selected")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self.button_box)

        # Enable OK button when selection changes
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)

    def _load_list_memberships(self) -> None:
        """Load which lists contain the selected books."""
        if not self.book_info:
            return

        api = self._get_api()
        if not api:
            return

        self.status_label.setText("Loading list memberships...")
        QApplication.processEvents()

        try:
            # For each book, find which lists contain it
            for book in self.book_info:
                memberships = api.get_book_list_memberships(book["hardcover_id"])

                for membership in memberships:
                    list_id = membership.list_id
                    if list_id not in self.list_memberships:
                        self.list_memberships[list_id] = []
                    self.list_memberships[list_id].append(
                        ListBookInfo(
                            list_id=list_id,
                            list_name=membership.list_name,
                            list_book_id=membership.list_book_id,
                        )
                    )

            self._populate_list_widget()

            if self.list_memberships:
                self.status_label.setText(
                    f"Found in {len(self.list_memberships)} list(s). Select lists to remove from."
                )
            else:
                self.status_label.setText("These books are not in any of your lists.")

        except Exception as e:
            self.status_label.setText(f"Error: {e}")

    def _populate_list_widget(self) -> None:
        """Populate the list widget with lists containing the books."""
        self.list_widget.clear()

        for list_id, memberships in self.list_memberships.items():
            list_name = memberships[0].list_name
            book_count = len(memberships)
            if len(self.book_info) == 1:
                item = QListWidgetItem(list_name)
            else:
                item = QListWidgetItem(f"{list_name} ({book_count} selected book(s))")
            item.setData(Qt.ItemDataRole.UserRole, list_id)
            self.list_widget.addItem(item)

    def _on_selection_changed(self) -> None:
        """Handle list selection change."""
        has_selection = len(self.list_widget.selectedItems()) > 0
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(has_selection)

    def _on_item_double_clicked(self, item: Any) -> None:
        """Handle double-click on a list item."""
        self._on_apply()

    def _on_apply(self) -> None:
        """Remove books from the selected lists."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return

        selected_list_ids = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]

        api = self._get_api()
        if not api:
            return

        self.button_box.setEnabled(False)
        self.status_label.setText("Removing from lists...")
        QApplication.processEvents()

        success = 0
        errors = []

        for list_id in selected_list_ids:
            memberships = self.list_memberships.get(list_id, [])
            for membership in memberships:
                try:
                    api.remove_book_from_list(membership.list_book_id)
                    success += 1
                except Exception as e:
                    errors.append(str(e))

        self.button_box.setEnabled(True)

        if success > 0:
            self.status_label.setText(f"Removed {success} book(s) from lists.")
            self.accept()
        else:
            self.status_label.setText(f"Error: {errors[0]}" if errors else "Unknown error.")
