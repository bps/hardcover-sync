"""
Add to list dialog.

This dialog allows the user to add selected books to a Hardcover list.
"""

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
from ..models import List as HardcoverList


class AddToListDialog(HardcoverDialogBase):
    """
    Dialog for adding books to a Hardcover list.

    Shows the user's lists and allows selecting one to add books to.
    """

    def __init__(self, parent, plugin_action, book_ids: list[int]):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            plugin_action: The plugin's InterfaceAction.
            book_ids: List of Calibre book IDs to add to list.
        """
        super().__init__(parent, plugin_action, book_ids)
        self.lists: list[HardcoverList] = []

        # Get book info (resolve slugs via API)
        api = self._get_api()
        self.book_info = self._get_book_info(api)

        self.setWindowTitle("Add to Hardcover List")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

        self._setup_ui()
        self._load_lists()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Check if any books are linked
        if not self.book_info:
            self._setup_not_linked_ui(layout)
            return

        # Show which book(s) will be added
        if len(self.book_info) == 1:
            book_label = QLabel(f"Add <b>{self.book_info[0]['title']}</b> to list:")
        else:
            book_label = QLabel(f"Add <b>{len(self.book_info)} books</b> to list:")
        layout.addWidget(book_label)

        # Lists widget
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # Status label
        self.status_label = QLabel("Loading your lists...")
        layout.addWidget(self.status_label)

        # Button box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_apply)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Add to List")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self.button_box)

        # Enable OK button when selection changes
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)

    def _load_lists(self):
        """Load the user's lists from Hardcover."""
        if not self.book_info:
            return

        api = self._get_api()
        if not api:
            return

        try:
            self.lists = api.get_user_lists()
            self._populate_list_widget()

            if self.lists:
                self.status_label.setText(f"Select a list ({len(self.lists)} available).")
            else:
                self.status_label.setText(
                    "You don't have any lists on Hardcover.\nCreate a list on hardcover.app first."
                )
        except Exception as e:
            self.status_label.setText(f"Error loading lists: {e}")

    def _populate_list_widget(self):
        """Populate the list widget with user's lists."""
        self.list_widget.clear()

        for lst in self.lists:
            item = QListWidgetItem(f"{lst.name} ({lst.books_count} books)")
            item.setData(Qt.ItemDataRole.UserRole, lst.id)
            self.list_widget.addItem(item)

    def _on_selection_changed(self):
        """Handle list selection change."""
        has_selection = len(self.list_widget.selectedItems()) > 0
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(has_selection)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on a list item."""
        self._on_apply()

    def _on_apply(self):
        """Add books to the selected list."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return

        list_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        list_name = selected_items[0].text().split(" (")[0]

        api = self._get_api()
        if not api:
            return

        self.button_box.setEnabled(False)
        self.status_label.setText("Adding books to list...")
        QApplication.processEvents()

        success = 0
        errors = []
        already_in_list = 0

        for book in self.book_info:
            try:
                # Check if book is already in the list
                book_lists = api.get_book_lists(book["hardcover_id"])
                if any(lst.id == list_id for lst in book_lists):
                    already_in_list += 1
                    continue

                # Add to list
                api.add_book_to_list(list_id, book["hardcover_id"])
                success += 1

            except Exception as e:
                errors.append(f"{book['title']}: {e}")

        self.button_box.setEnabled(True)

        # Build result message
        msg_parts = []
        if success > 0:
            msg_parts.append(f"Added {success} book(s) to '{list_name}'.")
        if already_in_list > 0:
            msg_parts.append(f"{already_in_list} already in list.")
        if errors:
            msg_parts.append(f"{len(errors)} error(s).")

        self.status_label.setText(" ".join(msg_parts) if msg_parts else "Done.")

        if success > 0 or already_in_list > 0:
            self.accept()
