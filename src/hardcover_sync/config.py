"""
Configuration management for Hardcover Sync plugin.

This module provides:
- READING_STATUSES: Mapping of Hardcover status IDs to labels
- get_plugin_prefs(): Get the plugin's JSONConfig preferences
- ConfigWidget: QWidget for plugin configuration dialog
"""

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
    # Column mappings (None means not mapped)
    "status_column": None,
    "rating_column": None,
    "progress_column": None,
    "date_started_column": None,
    "date_read_column": None,
    "review_column": None,
    "lists_column": None,  # Or use tags
    "use_tags_for_lists": False,
    # Status value mappings (custom column value -> Hardcover status ID)
    "status_mappings": {},
    # Sync behavior
    "conflict_resolution": "ask",  # ask, hardcover, calibre, newest
    "sync_rating": True,
    "sync_progress": True,
    "sync_dates": True,
    "sync_review": True,
    "sync_lists": True,
    # Menu display options
    "display_status_menu": True,
    "display_progress_menu": True,
    "display_sync_menu": True,
    "display_lists_menu": True,
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


class ConfigWidget:
    """
    Configuration widget for the plugin settings dialog.

    Provides:
    - API token input with validation button
    - User status display
    - Placeholder for additional settings (Phase 6)
    """

    def __init__(self):
        """Initialize the configuration widget."""
        # Import Qt here to avoid issues when running outside Calibre
        try:
            from qt.core import (
                QGroupBox,
                QHBoxLayout,
                QLabel,
                QLineEdit,
                QPushButton,
                QVBoxLayout,
                QWidget,
            )
        except ImportError:
            from PyQt5.Qt import (
                QGroupBox,
                QHBoxLayout,
                QLabel,
                QLineEdit,
                QPushButton,
                QVBoxLayout,
                QWidget,
            )

        self.widget = QWidget()
        self.main_layout = QVBoxLayout(self.widget)

        # Authentication group
        auth_group = QGroupBox("Hardcover Account")
        auth_layout = QVBoxLayout(auth_group)

        # API Token input row
        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("API Token:"))
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Paste your API token from hardcover.app/account/api")
        self.token_input.setEchoMode(QLineEdit.Password)
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

        self.main_layout.addWidget(auth_group)

        # Placeholder for more settings
        settings_group = QGroupBox("Sync Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.addWidget(
            QLabel("Column mappings and sync options will be available in a future update.")
        )
        self.main_layout.addWidget(settings_group)

        self.main_layout.addStretch()

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
        token = self.token_input.text().strip()
        if not token:
            self.status_label.setText("<b>Status:</b> Please enter an API token")
            self.status_label.setStyleSheet("color: orange;")
            return

        # Disable button during validation
        self.validate_button.setEnabled(False)
        self.validate_button.setText("Validating...")
        self.status_label.setText("<b>Status:</b> Validating token...")
        self.status_label.setStyleSheet("color: blue;")

        # Force UI update
        try:
            from qt.core import QApplication
        except ImportError:
            from PyQt5.Qt import QApplication
        QApplication.processEvents()

        # Validate the token
        is_valid, user = self._validate_token(token)

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
            self.status_label.setText("<b>Status:</b> Invalid token")
            self.status_label.setStyleSheet("color: red;")

    def _validate_token(self, token):
        """
        Validate the API token by making a test request.

        Args:
            token: The API token to validate.

        Returns:
            tuple: (is_valid, User) or (False, None) if invalid.
        """
        try:
            from .api import HardcoverAPI
        except ImportError:
            # Handle case where api module isn't available
            return False, None

        try:
            api = HardcoverAPI(token=token, timeout=15)
            return api.validate_token()
        except Exception:
            return False, None

    def save_settings(self):
        """Save the current settings."""
        token = self.token_input.text().strip()
        current_token = prefs.get("api_token", "")

        if token != current_token:
            if token:
                # Token changed - validate and save
                is_valid, user = self._validate_token(token)
                if is_valid and user:
                    prefs["api_token"] = token
                    prefs["username"] = user.username
                    prefs["user_id"] = user.id
                else:
                    # Still save the token but clear user info
                    prefs["api_token"] = token
                    prefs["username"] = ""
                    prefs["user_id"] = None
            else:
                # Token cleared
                prefs["api_token"] = ""
                prefs["username"] = ""
                prefs["user_id"] = None
