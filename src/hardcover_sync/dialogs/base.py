"""
Base dialog class for Hardcover Sync plugin.

This module provides a common base class for all Hardcover dialogs,
consolidating shared functionality like API access and book info retrieval.
"""

from __future__ import annotations

from typing import Any

from qt.core import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
)

from ..api import HardcoverAPI
from ..config import SYNCABLE_COLUMNS, get_plugin_prefs
from ..matcher import get_hardcover_slug, resolve_hardcover_book


class HardcoverDialogBase(QDialog):
    """
    Base class for Hardcover dialogs.

    Provides common functionality for dialogs that operate on selected books.
    """

    def __init__(self, parent: Any, plugin_action: Any, book_ids: list[int]) -> None:
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

    def _get_calibre_value(self, book_id: int, column: str) -> Any:
        """Get a value from a Calibre column."""
        if not column:
            return None
        return self.db.field_for(column, book_id)

    def _get_custom_column_metadata(self, column: str) -> dict | None:
        """Get metadata for a custom column."""
        try:
            custom_columns = self.gui.library_view.model().custom_columns
            return custom_columns.get(column)
        except (AttributeError, Exception):
            return None

    def _setup_diagnostics_panel(self, layout: Any) -> None:
        """Setup the diagnostics info panel.

        Creates a framed panel with three labels:
        - info_status_label: For scope/selection info
        - column_status_label: For column mapping status
        - warnings_label: For warning messages (orange text)
        """
        diag_frame = QFrame()
        diag_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        diag_layout = QVBoxLayout(diag_frame)
        diag_layout.setContentsMargins(8, 8, 8, 8)

        self.info_status_label = QLabel()
        self.info_status_label.setWordWrap(True)
        diag_layout.addWidget(self.info_status_label)

        self.column_status_label = QLabel()
        self.column_status_label.setWordWrap(True)
        diag_layout.addWidget(self.column_status_label)

        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #b35900;")
        diag_layout.addWidget(self.warnings_label)

        layout.addWidget(diag_frame)

    def _update_column_diagnostics(
        self,
        linked_count: int,
        *,
        exclude_columns: set[str] | None = None,
    ) -> None:
        """Update the column mapping and warnings labels in the diagnostics panel.

        This builds the "Mapped columns" text and warning messages shared by
        both sync dialogs.

        Args:
            linked_count: Number of linked books (used for warnings).
            exclude_columns: Optional set of pref_keys to exclude from the
                column mapping display (e.g. {"is_read_column"}).
        """
        mappings = []
        unmapped = []
        exclude = exclude_columns or set()

        for pref_key, display_name in SYNCABLE_COLUMNS:
            if pref_key in exclude:
                continue
            col = self.prefs.get(pref_key, "")
            if col:
                mappings.append(f"{display_name} → {col}")
            else:
                unmapped.append(display_name)

        if mappings:
            self.column_status_label.setText(f"<b>Mapped columns:</b> {', '.join(mappings)}")
        else:
            self.column_status_label.setText(
                "<b>Mapped columns:</b> <span style='color: red;'>None</span>"
            )

        # Warnings
        warnings: list[str] = []
        if linked_count == 0:
            warnings.append("No selected books are linked to Hardcover.")
        if unmapped:
            warnings.append(f"Unmapped fields won't sync: {', '.join(unmapped)}")
        if not self.prefs.get("api_token"):
            warnings.append("No API token configured!")

        if warnings:
            self.warnings_label.setText("\u26a0 " + " | ".join(warnings))
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

    def _get_book_info(self, api: HardcoverAPI | None = None) -> list[dict]:
        """
        Get info about books that are linked to Hardcover.

        Args:
            api: Optional HardcoverAPI instance for resolving slug-based identifiers
                 to integer book IDs. When provided, slugs are resolved via API lookup.
                 When not provided, only legacy numeric identifiers are resolved.

        Returns:
            List of dicts with calibre_id, hardcover_id (int), hardcover_slug, and title.
        """
        books = []
        for book_id in self.book_ids:
            hc_slug = get_hardcover_slug(self.db, book_id)
            if hc_slug:
                title = self.db.field_for("title", book_id) or "Unknown"
                # Resolve slug to integer book ID for API calls
                hc_int_id = None
                try:
                    hc_int_id = int(hc_slug)
                except (ValueError, TypeError):
                    # Slug-based identifier: resolve via API if available
                    if api:
                        book = resolve_hardcover_book(api, hc_slug)
                        if book:
                            hc_int_id = book.id
                if hc_int_id is not None:
                    books.append(
                        {
                            "calibre_id": book_id,
                            "hardcover_id": hc_int_id,
                            "hardcover_slug": hc_slug,
                            "title": title,
                        }
                    )
        return books

    def _setup_not_linked_ui(self, layout: Any) -> None:
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
