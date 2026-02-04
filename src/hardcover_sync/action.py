"""
Main InterfaceAction for the Hardcover Sync plugin.

This module defines the toolbar button and menu structure.
"""

from functools import partial

# Calibre imports - only available in Calibre's runtime environment
from calibre.gui2.actions import InterfaceAction
from qt.core import QMenu, QToolButton

from .config import MENU_STATUSES, READING_STATUSES, get_plugin_prefs


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
    popup_type = QToolButton.ToolButtonPopupMode.InstantPopup
    action_type = "current"
    dont_add_to_toolbar = False

    def genesis(self):
        """
        Setup the plugin. Called once when Calibre starts.
        """
        # Set the icon for this plugin
        # get_icons is injected by Calibre at runtime
        icon = get_icons("images/hardcover_sync.png", "Hardcover Sync")  # type: ignore[name-defined]
        self.qaction.setIcon(icon)

        # Track if menu needs rebuilding
        self._menu_needs_rebuild = True

        # Create the menu - we'll populate it in initialization_complete
        # or when aboutToShow fires
        self.menu = QMenu(self.gui)
        self.qaction.setMenu(self.menu)

        # Connect aboutToShow to rebuild menu - ensures it's always fresh
        self.menu.aboutToShow.connect(self._on_menu_about_to_show)

    def initialization_complete(self):
        """Called after GUI is fully initialized."""
        # Build the menu now that GUI is ready
        self._menu_needs_rebuild = True
        self.rebuild_menu()

    def _on_menu_about_to_show(self):
        """Called when menu is about to be shown."""
        if self._menu_needs_rebuild:
            self.rebuild_menu()

    def mark_menu_for_rebuild(self):
        """Mark the menu to be rebuilt on next show."""
        self._menu_needs_rebuild = True

    def library_changed(self, db):
        """Called when the library is changed."""
        # Invalidate any caches and mark menu for rebuild
        self._menu_needs_rebuild = True

    def rebuild_menu(self):
        """Rebuild the plugin menu."""
        self._menu_needs_rebuild = False
        self.menu.clear()
        prefs = get_plugin_prefs()

        # Check if API token is configured
        token = prefs.get("api_token", "")
        if not token:
            # Show a minimal menu prompting configuration
            self.menu.addAction("Configure Hardcover API token...").triggered.connect(
                self.show_configuration
            )
            self.menu.addSeparator()
            self.menu.addAction("Help").triggered.connect(self.show_help)
            return

        # Set Status submenu
        if prefs.get("display_status_menu", True):
            status_menu = self.menu.addMenu("Set Status")
            for status_id, status_name in MENU_STATUSES.items():
                action = status_menu.addAction(status_name)
                action.triggered.connect(partial(self.set_reading_status, status_id))
            status_menu.addSeparator()
            remove_action = status_menu.addAction("Remove from Hardcover")
            remove_action.triggered.connect(self.remove_from_hardcover)

        # Update Progress (Lab feature)
        if prefs.get("enable_lab_update_progress", False):
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

        # Lists submenu (Lab feature)
        if prefs.get("enable_lab_lists", False):
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

    def _get_api(self):
        """Get an API instance with the configured token."""
        from .api import HardcoverAPI
        from .config import get_plugin_prefs

        prefs = get_plugin_prefs()
        token = prefs.get("api_token", "")
        if not token:
            from calibre.gui2 import error_dialog

            error_dialog(
                self.gui,
                "Not Configured",
                "Please configure your Hardcover API token first.",
                show=True,
            )
            return None
        return HardcoverAPI(token=token)

    def _update_calibre_status(self, db, book_id: int, status_id: int):
        """Update the Calibre status column if configured."""
        from .config import get_plugin_prefs

        prefs = get_plugin_prefs()
        status_column = prefs.get("status_column")

        if not status_column:
            return  # No column mapped

        status_name = READING_STATUSES.get(status_id, "Unknown")

        try:
            # Get the column label without the # prefix
            col_name = status_column.lstrip("#")
            db.set_field(f"#{col_name}", {book_id: status_name})
        except Exception:  # noqa: S110
            pass  # Column update is best-effort, don't interrupt user flow

    def set_reading_status(self, status_id):
        """Set the reading status for selected books on Hardcover."""
        from calibre.gui2 import error_dialog, info_dialog

        from .matcher import get_hardcover_id

        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        api = self._get_api()
        if not api:
            return

        db = self.gui.current_db.new_api
        status_name = READING_STATUSES.get(status_id, "Unknown")

        success_count = 0
        not_linked = []
        errors = []

        for book_id in book_ids:
            hc_id = get_hardcover_id(db, book_id)
            title = db.field_for("title", book_id) or "Unknown"

            if not hc_id:
                not_linked.append(title)
                continue

            try:
                # Check if book is already in user's library
                user_book = api.get_user_book(hc_id)

                if user_book:
                    # Update existing
                    api.update_user_book(user_book.id, status_id=status_id)
                else:
                    # Add to library with this status
                    api.add_book_to_library(book_id=hc_id, status_id=status_id)

                # Update Calibre column if mapped
                self._update_calibre_status(db, book_id, status_id)
                success_count += 1

            except Exception as e:
                errors.append(f"{title}: {e}")

        # Show results
        if success_count > 0:
            msg = f"Set {success_count} book(s) to '{status_name}'."
            if not_linked:
                msg += f"\n\n{len(not_linked)} book(s) not linked to Hardcover."
            if errors:
                msg += f"\n\n{len(errors)} error(s) occurred."
            info_dialog(self.gui, "Status Updated", msg, show=True)
        elif not_linked:
            error_dialog(
                self.gui,
                "Not Linked",
                "None of the selected books are linked to Hardcover.\n"
                "Use 'Link to Hardcover' first.",
                show=True,
            )
        elif errors:
            error_dialog(
                self.gui,
                "Error",
                f"Failed to update status:\n{errors[0]}",
                show=True,
            )

    def remove_from_hardcover(self):
        """Remove selected books from Hardcover library."""
        from calibre.gui2 import error_dialog, info_dialog, question_dialog

        from .matcher import get_hardcover_id

        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        api = self._get_api()
        if not api:
            return

        db = self.gui.current_db.new_api

        # Find books that are linked and in library
        to_remove = []
        for book_id in book_ids:
            hc_id = get_hardcover_id(db, book_id)
            if hc_id:
                user_book = api.get_user_book(hc_id)
                if user_book:
                    title = db.field_for("title", book_id) or "Unknown"
                    to_remove.append((book_id, user_book.id, title))

        if not to_remove:
            error_dialog(
                self.gui,
                "Not in Library",
                "None of the selected books are in your Hardcover library.",
                show=True,
            )
            return

        # Confirm
        if len(to_remove) == 1:
            msg = f"Remove '{to_remove[0][2]}' from your Hardcover library?"
        else:
            msg = f"Remove {len(to_remove)} books from your Hardcover library?"

        if not question_dialog(self.gui, "Confirm Removal", msg):
            return

        # Remove books
        success = 0
        for _, user_book_id, _ in to_remove:
            try:
                api.remove_book_from_library(user_book_id)
                success += 1
            except Exception:  # noqa: S110
                pass  # Continue removing other books even if one fails

        info_dialog(
            self.gui,
            "Removed",
            f"Removed {success} book(s) from your Hardcover library.",
            show=True,
        )

    def update_progress(self):
        """Update reading progress for selected book."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        from .dialogs.update_progress import UpdateProgressDialog

        dialog = UpdateProgressDialog(self.gui, self, book_ids)
        dialog.exec_()

    def sync_from_hardcover(self):
        """Sync data from Hardcover to Calibre."""
        from .dialogs.sync_from import SyncFromHardcoverDialog

        dialog = SyncFromHardcoverDialog(self.gui, self)
        dialog.exec_()

    def sync_to_hardcover(self):
        """Sync data from Calibre to Hardcover."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        from .dialogs.sync_to import SyncToHardcoverDialog

        dialog = SyncToHardcoverDialog(self.gui, self, book_ids)
        dialog.exec_()

    def add_to_list(self):
        """Add selected books to a Hardcover list."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        from .dialogs.add_to_list import AddToListDialog

        dialog = AddToListDialog(self.gui, self, book_ids)
        dialog.exec_()

    def remove_from_list(self):
        """Remove selected books from a Hardcover list."""
        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        from .dialogs.remove_from_list import RemoveFromListDialog

        dialog = RemoveFromListDialog(self.gui, self, book_ids)
        dialog.exec_()

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
        from calibre.gui2 import info_dialog

        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        # Only link one book at a time
        book_id = book_ids[0]
        db = self.gui.current_db.new_api

        # Get book info
        title = db.field_for("title", book_id) or "Unknown"
        authors = db.field_for("authors", book_id) or []

        # Show the link dialog
        from .dialogs.link_book import LinkBookDialog

        dialog = LinkBookDialog(self.gui, db, book_id, title, authors)
        if dialog.exec_() == dialog.Accepted:
            selected_book = dialog.get_selected_book()
            if selected_book:
                # Store the Hardcover ID
                from .matcher import set_hardcover_id

                edition_id = dialog.get_selected_edition_id()
                set_hardcover_id(db, book_id, selected_book.id, edition_id)

                info_dialog(
                    self.gui,
                    "Book Linked",
                    f"'{title}' has been linked to '{selected_book.title}' on Hardcover.",
                    show=True,
                )

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
        from calibre.gui2 import error_dialog, info_dialog, question_dialog

        book_ids = self.get_selected_book_ids()
        if not book_ids:
            return self._show_no_selection_error()

        db = self.gui.current_db.new_api

        # Check how many are actually linked
        linked_ids = []
        for bid in book_ids:
            identifiers = db.field_for("identifiers", bid) or {}
            if "hardcover" in identifiers:
                linked_ids.append(bid)

        if not linked_ids:
            error_dialog(
                self.gui,
                "No Links Found",
                "None of the selected books are linked to Hardcover.",
                show=True,
            )
            return

        # Confirm removal
        if len(linked_ids) == 1:
            title = db.field_for("title", linked_ids[0])
            msg = f"Remove Hardcover link from '{title}'?"
        else:
            msg = f"Remove Hardcover links from {len(linked_ids)} books?"

        if not question_dialog(self.gui, "Confirm Removal", msg):
            return

        # Remove links
        from .matcher import remove_hardcover_id

        for bid in linked_ids:
            remove_hardcover_id(db, bid)

        info_dialog(
            self.gui,
            "Links Removed",
            f"Removed Hardcover links from {len(linked_ids)} book(s).",
            show=True,
        )

    def show_configuration(self):
        """Show the plugin configuration dialog."""
        if self.interface_action_base_plugin.do_user_config(self.gui, plugin_action=self):  # type: ignore[union-attr]
            # User clicked OK - mark menu for rebuild in case token was added/changed
            self.mark_menu_for_rebuild()

    def show_help(self):
        """Show help documentation."""
        from calibre.gui2 import open_url
        from qt.core import QUrl

        open_url(QUrl("https://github.com/bps/hardcover-sync"))

    def _show_no_selection_error(self):
        """Show error when no books are selected."""
        from calibre.gui2 import error_dialog

        error_dialog(
            self.gui,
            "No Books Selected",
            "Please select one or more books first.",
            show=True,
        )
