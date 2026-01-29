"""
Configuration management for Hardcover Sync plugin.

This module provides:
- READING_STATUSES: Mapping of Hardcover status IDs to labels
- get_plugin_prefs(): Get the plugin's JSONConfig preferences
- ConfigWidget: QWidget for plugin configuration dialog
"""

# Calibre imports - only available in Calibre's runtime environment
from calibre.utils.config import JSONConfig

# Hardcover reading status mapping
READING_STATUSES = {
    1: "Want to Read",
    2: "Currently Reading",
    3: "Read",
    4: "Paused",
    5: "Did Not Finish",
    6: "Ignored",
}

# Reverse mapping for convenience
STATUS_IDS = {v: k for k, v in READING_STATUSES.items()}

# Default preferences
DEFAULT_PREFS = {
    # Authentication
    "api_token": "",
    "username": "",
    "user_id": None,
    # Column mappings (None or empty string means not mapped)
    "status_column": "",
    "rating_column": "",
    "progress_column": "",
    "date_started_column": "",
    "date_read_column": "",
    "review_column": "",
    "lists_column": "",
    "use_tags_for_lists": True,
    # Status value mappings (Hardcover status ID -> Calibre column value)
    # e.g., {1: "Want to Read", 2: "Currently Reading", ...}
    "status_mappings": {},
    # Reading statuses to include when syncing from Hardcover
    # Empty list means all statuses; otherwise list of status IDs to include
    "sync_statuses": [],  # Default: sync all statuses
    # Sync behavior
    "conflict_resolution": "ask",  # ask, hardcover, calibre, newest
    "sync_rating": True,
    "sync_progress": True,
    "sync_dates": True,
    "sync_review": True,
    "sync_lists": True,
}

# Plugin configuration storage
prefs = JSONConfig("plugins/Hardcover Sync")
prefs.defaults = DEFAULT_PREFS


def get_plugin_prefs():
    """
    Get the plugin preferences.

    Returns:
        JSONConfig: The plugin's preferences object.
    """
    return prefs


class CustomColumnComboBox:
    """
    A combo box for selecting custom columns.

    Wraps QComboBox and provides methods to populate with custom columns
    and retrieve the selected column's lookup name.
    """

    def __init__(self, parent, custom_columns=None, selected_column="", initial_items=None):
        """
        Initialize the combo box.

        Args:
            parent: Parent widget.
            custom_columns: Dict of custom columns {lookup_name: column_info}.
            selected_column: Currently selected column lookup name.
            initial_items: List or dict of initial items (e.g., [""] for "Not mapped").
        """
        from qt.core import QComboBox

        self.combo = QComboBox(parent)
        self.column_names = []

        if custom_columns is None:
            custom_columns = {}
        if initial_items is None:
            initial_items = [""]

        self.populate_combo(custom_columns, selected_column, initial_items)

    def populate_combo(self, custom_columns, selected_column="", initial_items=None):
        """
        Populate the combo box with columns.

        Args:
            custom_columns: Dict of {lookup_name: column_info}.
            selected_column: Column to select.
            initial_items: Initial items (list of strings or dict).
        """
        self.combo.clear()
        self.column_names = []
        selected_idx = 0

        if initial_items is None:
            initial_items = [""]

        # Add initial items
        if isinstance(initial_items, dict):
            for key in sorted(initial_items.keys()):
                self.column_names.append(key)
                display_name = initial_items[key]
                self.combo.addItem(display_name)
                if key == selected_column:
                    selected_idx = len(self.column_names) - 1
        else:
            for item in initial_items:
                self.column_names.append(item)
                display_name = "(Not mapped)" if item == "" else item
                self.combo.addItem(display_name)
                if item == selected_column:
                    selected_idx = len(self.column_names) - 1

        # Add custom columns sorted by lookup name
        for key in sorted(custom_columns.keys()):
            self.column_names.append(key)
            col_info = custom_columns[key]
            display_name = col_info.get("name", key)
            # Show lookup name and display name: "#status (Reading Status)"
            self.combo.addItem(f"{key} ({display_name})")
            if key == selected_column:
                selected_idx = len(self.column_names) - 1

        self.combo.setCurrentIndex(selected_idx)

    def get_selected_column(self):
        """Get the lookup name of the selected column (or empty string if not mapped)."""
        idx = self.combo.currentIndex()
        if 0 <= idx < len(self.column_names):
            return self.column_names[idx]
        return ""

    def setMinimumWidth(self, width):
        """Set minimum width of the combo box."""
        self.combo.setMinimumWidth(width)

    def widget(self):
        """Get the underlying QComboBox widget."""
        return self.combo


class ConfigWidget:
    """
    Configuration widget for the plugin settings dialog.

    Provides:
    - API token input with validation button
    - Column mapping dropdowns
    - Status value mapping
    - Sync options
    - Conflict resolution settings
    """

    def __init__(self, plugin_action=None):
        """
        Initialize the configuration widget.

        Args:
            plugin_action: The plugin's InterfaceAction (provides access to GUI/database).
        """
        from qt.core import QTabWidget, QVBoxLayout, QWidget

        self.plugin_action = plugin_action
        self.widget = QWidget()
        self.main_layout = QVBoxLayout(self.widget)

        # Create tab widget for organized settings
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Tab 1: Account
        self._create_account_tab()

        # Tab 2: Column Mappings
        self._create_columns_tab()

        # Tab 3: Sync Options
        self._create_sync_tab()

    def _create_account_tab(self):
        """Create the Account settings tab."""
        from qt.core import (
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Authentication group
        auth_group = QGroupBox("Hardcover Account")
        auth_layout = QVBoxLayout(auth_group)

        # API Token input row
        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("API Token:"))
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Paste your API token from hardcover.app/account/api")
        self.token_input.setText(prefs.get("api_token", ""))
        token_row.addWidget(self.token_input, 1)

        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(self._on_validate_clicked)
        token_row.addWidget(self.validate_button)

        auth_layout.addLayout(token_row)

        # Status display
        self.status_label = QLabel()
        self._update_status_display()
        auth_layout.addWidget(self.status_label)

        # Link to get API token
        link_label = QLabel(
            '<a href="https://hardcover.app/account/api">Get your API token from Hardcover</a>'
        )
        link_label.setOpenExternalLinks(True)
        auth_layout.addWidget(link_label)

        layout.addWidget(auth_group)
        layout.addStretch()

        self.tabs.addTab(tab, "Account")

    def _create_columns_tab(self):
        """Create the Column Mappings tab."""
        from qt.core import (
            QFormLayout,
            QGroupBox,
            QLabel,
            QVBoxLayout,
            QWidget,
        )

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Instructions
        instructions = QLabel(
            "Map Calibre columns to Hardcover fields. "
            "Create custom columns in Calibre first, then select them here."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Column mappings group
        columns_group = QGroupBox("Column Mappings")
        columns_layout = QFormLayout(columns_group)

        # Get available columns from Calibre
        enum_columns = self._get_custom_columns(["enumeration", "text"])
        rating_columns = self._get_rating_columns()
        int_columns = self._get_custom_columns(["int", "float"])
        date_columns = self._get_custom_columns(["datetime"])
        text_columns = self._get_custom_columns(["text", "comments"])
        tags_columns = self._get_tags_columns()

        # Status column (enumeration preferred)
        self.status_combo = CustomColumnComboBox(tab, enum_columns, prefs.get("status_column", ""))
        self.status_combo.setMinimumWidth(200)
        columns_layout.addRow("Reading Status:", self.status_combo.widget())

        # Rating column
        self.rating_combo = CustomColumnComboBox(
            tab, rating_columns, prefs.get("rating_column", "")
        )
        self.rating_combo.setMinimumWidth(200)
        columns_layout.addRow("Rating:", self.rating_combo.widget())

        # Progress column (integer)
        self.progress_combo = CustomColumnComboBox(
            tab, int_columns, prefs.get("progress_column", "")
        )
        self.progress_combo.setMinimumWidth(200)
        columns_layout.addRow("Progress (pages):", self.progress_combo.widget())

        # Date started column
        self.date_started_combo = CustomColumnComboBox(
            tab, date_columns, prefs.get("date_started_column", "")
        )
        self.date_started_combo.setMinimumWidth(200)
        columns_layout.addRow("Date Started:", self.date_started_combo.widget())

        # Date read column
        self.date_read_combo = CustomColumnComboBox(
            tab, date_columns, prefs.get("date_read_column", "")
        )
        self.date_read_combo.setMinimumWidth(200)
        columns_layout.addRow("Date Read:", self.date_read_combo.widget())

        # Review column (long text)
        self.review_combo = CustomColumnComboBox(tab, text_columns, prefs.get("review_column", ""))
        self.review_combo.setMinimumWidth(200)
        columns_layout.addRow("Review:", self.review_combo.widget())

        # Lists column
        self.lists_combo = CustomColumnComboBox(
            tab,
            tags_columns,
            prefs.get("lists_column", "") if not prefs.get("use_tags_for_lists", True) else "tags",
            initial_items={"tags": "Tags (built-in)", "": "(Not mapped)"},
        )
        self.lists_combo.setMinimumWidth(200)
        columns_layout.addRow("Lists:", self.lists_combo.widget())

        layout.addWidget(columns_group)

        # Status value mapping group
        self._create_status_mapping_group(layout, tab)

        layout.addStretch()

        self.tabs.addTab(tab, "Columns")

    def _create_status_mapping_group(self, parent_layout, parent_widget):
        """Create the status value mapping section."""
        from qt.core import QFormLayout, QGroupBox, QLabel, QLineEdit

        group = QGroupBox("Status Value Mapping")
        layout = QFormLayout(group)

        instructions = QLabel(
            "Enter the values your status column uses for each Hardcover status. "
            "Leave blank to skip a status."
        )
        instructions.setWordWrap(True)
        layout.addRow(instructions)

        # Create input for each Hardcover status
        self.status_mapping_inputs = {}
        saved_mappings = prefs.get("status_mappings", {})

        for status_id, status_name in READING_STATUSES.items():
            input_field = QLineEdit()
            input_field.setPlaceholderText(status_name)
            # Load saved value (convert status_id to string for JSON compatibility)
            saved_value = saved_mappings.get(str(status_id), "")
            input_field.setText(saved_value)
            layout.addRow(f"{status_name}:", input_field)
            self.status_mapping_inputs[status_id] = input_field

        parent_layout.addWidget(group)

    def _create_sync_tab(self):
        """Create the Sync Options tab."""
        from qt.core import (
            QCheckBox,
            QComboBox,
            QFormLayout,
            QGroupBox,
            QLabel,
            QVBoxLayout,
            QWidget,
        )

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Sync options group
        sync_group = QGroupBox("Fields to Sync")
        sync_layout = QVBoxLayout(sync_group)

        self.sync_rating_checkbox = QCheckBox("Sync rating")
        self.sync_rating_checkbox.setChecked(prefs.get("sync_rating", True))
        sync_layout.addWidget(self.sync_rating_checkbox)

        self.sync_progress_checkbox = QCheckBox("Sync reading progress")
        self.sync_progress_checkbox.setChecked(prefs.get("sync_progress", True))
        sync_layout.addWidget(self.sync_progress_checkbox)

        self.sync_dates_checkbox = QCheckBox("Sync dates (started/finished)")
        self.sync_dates_checkbox.setChecked(prefs.get("sync_dates", True))
        sync_layout.addWidget(self.sync_dates_checkbox)

        self.sync_review_checkbox = QCheckBox("Sync review text")
        self.sync_review_checkbox.setChecked(prefs.get("sync_review", True))
        sync_layout.addWidget(self.sync_review_checkbox)

        self.sync_lists_checkbox = QCheckBox("Sync lists as tags")
        self.sync_lists_checkbox.setChecked(prefs.get("sync_lists", True))
        sync_layout.addWidget(self.sync_lists_checkbox)

        layout.addWidget(sync_group)

        # Reading statuses to sync group
        status_filter_group = QGroupBox("Reading Statuses to Sync")
        status_filter_layout = QVBoxLayout(status_filter_group)

        status_filter_label = QLabel(
            "Select which reading statuses to include when syncing from Hardcover. "
            "Unchecked statuses will be skipped when creating new books."
        )
        status_filter_label.setWordWrap(True)
        status_filter_layout.addWidget(status_filter_label)

        # Get currently enabled statuses (empty list means all enabled)
        enabled_statuses = prefs.get("sync_statuses", [])
        all_enabled = len(enabled_statuses) == 0

        # Create checkboxes for each reading status
        self.status_filter_checkboxes = {}
        for status_id, status_name in READING_STATUSES.items():
            checkbox = QCheckBox(status_name)
            # If list is empty, all are enabled; otherwise check if in list
            checkbox.setChecked(all_enabled or status_id in enabled_statuses)
            self.status_filter_checkboxes[status_id] = checkbox
            status_filter_layout.addWidget(checkbox)

        layout.addWidget(status_filter_group)

        # Conflict resolution group
        conflict_group = QGroupBox("Conflict Resolution")
        conflict_layout = QFormLayout(conflict_group)

        conflict_label = QLabel("When values differ between Calibre and Hardcover during sync:")
        conflict_label.setWordWrap(True)
        conflict_layout.addRow(conflict_label)

        self.conflict_combo = QComboBox()
        self.conflict_combo.addItem("Ask each time", "ask")
        self.conflict_combo.addItem("Always use Hardcover value", "hardcover")
        self.conflict_combo.addItem("Always use Calibre value", "calibre")
        self.conflict_combo.addItem("Use most recently updated", "newest")

        # Set current value
        current_resolution = prefs.get("conflict_resolution", "ask")
        for i in range(self.conflict_combo.count()):
            if self.conflict_combo.itemData(i) == current_resolution:
                self.conflict_combo.setCurrentIndex(i)
                break

        conflict_layout.addRow("Resolution strategy:", self.conflict_combo)

        layout.addWidget(conflict_group)
        layout.addStretch()

        self.tabs.addTab(tab, "Sync Options")

    def _get_custom_columns(self, column_types):
        """
        Get custom columns of specific types.

        Args:
            column_types: List of column datatypes (e.g., ['text', 'enumeration']).

        Returns:
            Dict of {lookup_name: column_info}.
        """
        if self.plugin_action is None:
            return {}

        try:
            custom_columns = self.plugin_action.gui.library_view.model().custom_columns
        except (AttributeError, Exception):
            return {}

        available = {}
        for key, column in custom_columns.items():
            if column.get("datatype") in column_types:
                available[key] = column
        return available

    def _get_rating_columns(self):
        """Get columns suitable for ratings (rating, int, float)."""
        columns = self._get_custom_columns(["rating", "int", "float"])

        # Add built-in rating column
        if self.plugin_action is not None:
            try:
                model = self.plugin_action.gui.library_view.model()
                rating_name = model.orig_headers.get("rating", "Rating")
                columns["rating"] = {"name": rating_name}
            except (AttributeError, Exception):
                columns["rating"] = {"name": "Rating"}

        return columns

    def _get_tags_columns(self):
        """Get columns suitable for tags/lists."""
        return self._get_custom_columns(["text"])

    def __getattr__(self, name):
        """Delegate attribute access to the internal widget."""
        return getattr(self.widget, name)

    def _update_status_display(self):
        """Update the status label based on current preferences."""
        username = prefs.get("username", "")
        if username:
            self.status_label.setText(f"<b>Status:</b> Connected as @{username}")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("<b>Status:</b> Not connected")
            self.status_label.setStyleSheet("color: gray;")

    def _on_validate_clicked(self):
        """Handle validate button click."""
        token = self._normalize_token(self.token_input.text())
        if not token:
            self.status_label.setText("<b>Status:</b> Please enter an API token")
            self.status_label.setStyleSheet("color: orange;")
            return

        # Update the input field to show normalized token (without Bearer prefix)
        self.token_input.setText(token)

        # Disable button during validation
        self.validate_button.setEnabled(False)
        self.validate_button.setText("Validating...")
        self.status_label.setText("<b>Status:</b> Validating token...")
        self.status_label.setStyleSheet("color: blue;")

        # Force UI update
        from qt.core import QApplication

        QApplication.processEvents()

        # Validate the token
        is_valid, user, error = self._validate_token(token)

        # Re-enable button
        self.validate_button.setEnabled(True)
        self.validate_button.setText("Validate")

        if is_valid and user:
            # Save valid credentials
            prefs["api_token"] = token
            prefs["username"] = user.username
            prefs["user_id"] = user.id
            self.status_label.setText(
                f"<b>Status:</b> Connected as @{user.username} ({user.books_count} books)"
            )
            self.status_label.setStyleSheet("color: green;")
        else:
            error_msg = error if error else "Invalid token"
            self.status_label.setText(f"<b>Status:</b> {error_msg}")
            self.status_label.setStyleSheet("color: red;")

    def _validate_token(self, token):
        """
        Validate the API token by making a test request.

        Args:
            token: The API token to validate.

        Returns:
            tuple: (is_valid, User, error_message) or (False, None, error_message) if invalid.
        """
        try:
            from .api import HardcoverAPI
        except ImportError as e:
            return False, None, f"Failed to import API: {e}"

        try:
            api = HardcoverAPI(token=token, timeout=15)
            is_valid, user = api.validate_token()
            if is_valid and user:
                return True, user, None
            return False, None, "Invalid token or authentication failed"
        except Exception as e:
            # Sanitize error message to avoid leaking the token
            error_msg = str(e)
            if token and len(token) > 10:
                error_msg = error_msg.replace(token, "[REDACTED]")
            return False, None, f"{type(e).__name__}: {error_msg}"

    def _normalize_token(self, token: str) -> str:
        """
        Normalize the API token by stripping whitespace and removing 'Bearer ' prefix.

        Args:
            token: The raw token input from the user.

        Returns:
            The normalized token without 'Bearer ' prefix.
        """
        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        return token

    def save_settings(self):
        """Save all settings from the configuration dialog."""
        # Save API token (normalize to remove Bearer prefix if present)
        token = self._normalize_token(self.token_input.text())
        current_token = prefs.get("api_token", "")

        if token != current_token:
            if token:
                # Token changed - validate and save
                is_valid, user, _error = self._validate_token(token)
                if is_valid and user:
                    prefs["api_token"] = token
                    prefs["username"] = user.username
                    prefs["user_id"] = user.id
                else:
                    prefs["api_token"] = token
                    prefs["username"] = ""
                    prefs["user_id"] = None
            else:
                prefs["api_token"] = ""
                prefs["username"] = ""
                prefs["user_id"] = None

        # Save column mappings
        prefs["status_column"] = self.status_combo.get_selected_column()
        prefs["rating_column"] = self.rating_combo.get_selected_column()
        prefs["progress_column"] = self.progress_combo.get_selected_column()
        prefs["date_started_column"] = self.date_started_combo.get_selected_column()
        prefs["date_read_column"] = self.date_read_combo.get_selected_column()
        prefs["review_column"] = self.review_combo.get_selected_column()

        # Lists column handling
        lists_selection = self.lists_combo.get_selected_column()
        if lists_selection == "tags":
            prefs["use_tags_for_lists"] = True
            prefs["lists_column"] = ""
        else:
            prefs["use_tags_for_lists"] = False
            prefs["lists_column"] = lists_selection

        # Save status mappings
        status_mappings = {}
        for status_id, input_field in self.status_mapping_inputs.items():
            value = input_field.text().strip()
            if value:
                status_mappings[str(status_id)] = value
        prefs["status_mappings"] = status_mappings

        # Save sync options
        prefs["sync_rating"] = self.sync_rating_checkbox.isChecked()
        prefs["sync_progress"] = self.sync_progress_checkbox.isChecked()
        prefs["sync_dates"] = self.sync_dates_checkbox.isChecked()
        prefs["sync_review"] = self.sync_review_checkbox.isChecked()
        prefs["sync_lists"] = self.sync_lists_checkbox.isChecked()

        # Save reading status filter
        # If all are checked, save empty list (means "all")
        # Otherwise save list of checked status IDs
        checked_statuses = [
            status_id
            for status_id, checkbox in self.status_filter_checkboxes.items()
            if checkbox.isChecked()
        ]
        if len(checked_statuses) == len(READING_STATUSES):
            prefs["sync_statuses"] = []  # All enabled
        else:
            prefs["sync_statuses"] = checked_statuses

        # Save conflict resolution
        prefs["conflict_resolution"] = self.conflict_combo.currentData()
