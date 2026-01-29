"""
Main InterfaceAction for the Hardcover Sync plugin.

This module defines the toolbar button and menu structure.
"""

from functools import partial

from calibre.gui2.actions import InterfaceAction

from .config import READING_STATUSES, get_plugin_prefs


class HardcoverSyncAction(InterfaceAction):
    """
    The main action class for Hardcover Sync.
    Provides the toolbar button and menu.
    """

    name = "Hardcover Sync"
    action_spec = (
        "Hardcover",  # Text for toolbar button
        None,  # Icon (will be set in genesis)
        "Sync with Hardcover.app",  # Tooltip
        None,  # Keyboard shortcut
    )
    popup_type = QToolButton.InstantPopup
    action_type = "current"
    dont_add_to_toolbar = False

    def genesis(self):
        """
        Setup the plugin. Called once when Calibre starts.
        """
        # Set the icon for this plugin
        icon = get_icons("images/hardcover_sync.png", "Hardcover Sync")
        self.qaction.setIcon(icon)

        # Build the menu
        self.menu = self.qaction.menu()
        self.rebuild_menu()

        # Connect to library change signal
        self.gui.library_view.model().library_changed.connect(self.library_changed)

    def library_changed(self, db):
        """Called when the library is changed."""
        # Invalidate any caches
        pass

    def rebuild_menu(self):
        """Rebuild the plugin menu."""
        self.menu.clear()
        prefs = get_plugin_prefs()

        # Set Status submenu
        if prefs.get("display_status_menu", True):
            status_menu = self.menu.addMenu("Set Status")
            for status_id, status_name in READING_STATUSES.items():
                action = status_menu.addAction(status_name)
                action.triggered.connect(partial(self.set_reading_status, status_id))
            status_menu.addSeparator()
            remove_action = status_menu.addAction("Remove from Hardcover")
            remove_action.triggered.connect(self.remove_from_hardcover)

        # Update Progress
        if prefs.get("display_progress_menu", True):
            self.menu.addAction("Update Reading Progress...").triggered.connect(
                self.update_progress
            )

        self.menu.addSeparator()

        # Sync actions
        if prefs.get("display_sync_menu", True):
            self.menu.addAction("Sync from Hardcover...").triggered.connect(
                self.sync_from_hardcover
            )
            self.menu.addAction("Sync to Hardcover...").triggered.connect(self.sync_to_hardcover)

        self.menu.addSeparator()

        # Lists submenu
        if prefs.get("display_lists_menu", True):
            lists_menu = self.menu.addMenu("Lists")
            lists_menu.addAction("Add to List...").triggered.connect(self.add_to_list)
            lists_menu.addAction("Remove from List...").triggered.connect(self.remove_from_list)
            lists_menu.addSeparator()
            lists_menu.addAction("View Lists on Hardcover").triggered.connect(
                self.view_lists_on_hardcover
            )

        self.menu.addSeparator()

        # Link/view actions
        self.menu.addAction("Link to Hardcover...").triggered.connect(self.link_to_hardcover)
        self.menu.addAction("View on Hardcover").triggered.connect(self.view_on_hardcover)
        self.menu.addAction("Remove Hardcover Link").triggered.connect(self.remove_hardcover_link)

        self.menu.addSeparator()

        # Configuration
        self.menu.addAction("Customize plugin...").triggered.connect(self.show_configuration)
        self.menu.addAction("Help").triggered.connect(self.show_help)

    def get_selected_books(self):
        """Get the currently selected books in the library view."""
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            return []
        return [row.row() for row in rows]

    def get_selected_book_ids(self):
        """Get the calibre book IDs for selected books."""
        rows = self.get_selected_books()
        if not rows:
            return []
        return [self.gui.library_view.model().id(row) for row in rows]

    # -------------------------------------------------------------------------
    # Action handlers (stubs for now)
    # -------------------------------------------------------------------------

    def set_reading_status(self, status_id):
        """Set the reading status for selected books."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()
        # TODO: Implement
        print(f"Set status {status_id} for books: {book_ids}")

    def remove_from_hardcover(self):
        """Remove selected books from Hardcover library."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()
        # TODO: Implement
        print(f"Remove from Hardcover: {book_ids}")

    def update_progress(self):
        """Update reading progress for selected book."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()
        # TODO: Implement - show dialog
        print(f"Update progress for: {book_ids}")

    def sync_from_hardcover(self):
        """Sync data from Hardcover to Calibre."""
        # TODO: Implement - show dialog
        print("Sync from Hardcover")

    def sync_to_hardcover(self):
        """Sync data from Calibre to Hardcover."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()
        # TODO: Implement - show dialog
        print(f"Sync to Hardcover: {book_ids}")

    def add_to_list(self):
        """Add selected books to a Hardcover list."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()
        # TODO: Implement - show dialog
        print(f"Add to list: {book_ids}")

    def remove_from_list(self):
        """Remove selected books from a Hardcover list."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()
        # TODO: Implement - show dialog
        print(f"Remove from list: {book_ids}")

    def view_lists_on_hardcover(self):
        """Open Hardcover lists page in browser."""
        from calibre.gui2 import open_url
        from qt.core import QUrl

        prefs = get_plugin_prefs()
        username = prefs.get("username", "")
        if username:
            url = f"https://hardcover.app/@{username}/lists"
        else:
            url = "https://hardcover.app"
        open_url(QUrl(url))

    def link_to_hardcover(self):
        """Link selected book to a Hardcover book."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()
        # TODO: Implement - show search dialog
        print(f"Link to Hardcover: {book_ids}")

    def view_on_hardcover(self):
        """Open selected book on Hardcover in browser."""
        from calibre.gui2 import open_url
        from qt.core import QUrl

        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        # Get the Hardcover ID from the first selected book
        db = self.gui.current_db.new_api
        book_id = book_ids[0]
        identifiers = db.field_for("identifiers", book_id)
        hardcover_id = identifiers.get("hardcover")

        if not hardcover_id:
            from calibre.gui2 import error_dialog

            error_dialog(
                self.gui,
                "Not Linked",
                "This book is not linked to Hardcover. Use 'Link to Hardcover' first.",
                show=True,
            )
            return

        url = f"https://hardcover.app/books/{hardcover_id}"
        open_url(QUrl(url))

    def remove_hardcover_link(self):
        """Remove Hardcover identifier from selected books."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()
        # TODO: Implement
        print(f"Remove Hardcover link: {book_ids}")

    def show_configuration(self):
        """Show the plugin configuration dialog."""
        self.interface_action_base_plugin.do_user_config(self.gui)

    def show_help(self):
        """Show help documentation."""
        from calibre.gui2 import open_url
        from qt.core import QUrl

        # TODO: Update with actual documentation URL
        open_url(QUrl("https://github.com/brianryall/hardcover-sync"))

    def _show_no_selection_error(self):
        """Show error when no books are selected."""
        from calibre.gui2 import error_dialog

        error_dialog(
            self.gui,
            "No Books Selected",
            "Please select one or more books first.",
            show=True,
        )


# Import Qt widgets (needed for popup_type)
try:
    from qt.core import QToolButton
except ImportError:
    from PyQt5.Qt import QToolButton
