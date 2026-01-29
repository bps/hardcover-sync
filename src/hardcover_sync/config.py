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

    This is a stub that will be expanded in Phase 6 with full UI:
    - API token input and validation
    - Column mapping dropdowns
    - Status value mappings
    - Conflict resolution settings
    """

    def __init__(self):
        """Initialize the configuration widget."""
        # Import Qt here to avoid issues when running outside Calibre
        try:
            from qt.core import QLabel, QLineEdit, QVBoxLayout, QWidget
        except ImportError:
            from PyQt5.Qt import QLabel, QLineEdit, QVBoxLayout, QWidget

        self.widget = QWidget()
        self.layout = QVBoxLayout(self.widget)

        # API Token input
        self.layout.addWidget(QLabel("API Token:"))
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Paste your API token from hardcover.app/account/api")
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setText(prefs.get("api_token", ""))
        self.layout.addWidget(self.token_input)

        # Username display
        username = prefs.get("username", "")
        if username:
            self.layout.addWidget(QLabel(f"Logged in as: @{username}"))
        else:
            self.layout.addWidget(QLabel("Not logged in - enter API token above"))

        # Placeholder for more settings
        self.layout.addWidget(QLabel(""))
        self.layout.addWidget(QLabel("Additional settings will be available in a future update."))

        self.layout.addStretch()

    def __getattr__(self, name):
        """Delegate attribute access to the internal widget."""
        return getattr(self.widget, name)

    def save_settings(self):
        """Save the current settings."""
        token = self.token_input.text().strip()
        if token != prefs.get("api_token", ""):
            prefs["api_token"] = token
            # Clear cached user info when token changes
            prefs["username"] = ""
            prefs["user_id"] = None
            # TODO: Validate token and fetch user info

    def validate_token(self, token):
        """
        Validate the API token by making a test request.

        This will be implemented in Phase 3 when the API client is ready.

        Args:
            token: The API token to validate.

        Returns:
            tuple: (is_valid, username, user_id) or (False, None, None) if invalid.
        """
        # TODO: Implement with API client
        return False, None, None
