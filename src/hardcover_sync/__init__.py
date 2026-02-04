"""
Hardcover Sync - A Calibre plugin for syncing with Hardcover.app

This plugin allows bidirectional synchronization of reading status,
ratings, progress, and lists between Calibre and Hardcover.app.
"""

import sys
from pathlib import Path

# Add plugin directory to sys.path FIRST for bundled dependencies (gql, graphql-core)
# This must happen before any other imports to avoid conflicts with system packages
_plugin_dir = Path(__file__).parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))

# Remove any pre-loaded graphql/gql modules so our bundled versions are used
# This is necessary because Calibre or its environment may have older versions
_modules_to_remove = [
    key
    for key in sys.modules
    if key == "graphql" or key.startswith("graphql.") or key == "gql" or key.startswith("gql.")
]
for mod in _modules_to_remove:
    del sys.modules[mod]

# Calibre imports - only available in Calibre's runtime environment
from calibre.customize import InterfaceActionBase  # noqa: E402

try:
    from ._version import __version__, __version_tuple__  # noqa: E402
except ImportError:
    __version__ = "0.0.0.dev0"
    __version_tuple__ = (0, 0, 0, "dev0")


class HardcoverSyncPlugin(InterfaceActionBase):
    """
    The main plugin class that Calibre uses to load the plugin.
    """

    name = "Hardcover Sync"
    description = "Sync reading status, ratings, and progress with Hardcover.app"
    author = "Brian Smyth"
    version = __version_tuple__[:3] if len(__version_tuple__) >= 3 else (0, 0, 0)
    minimum_calibre_version = (6, 0, 0)

    # The actual plugin is in action.py
    actual_plugin = "calibre_plugins.hardcover_sync.action:HardcoverSyncAction"

    def is_customizable(self):
        """This plugin has a configuration dialog."""
        return True

    def config_widget(self):
        """Return the configuration widget."""
        from .config import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget):
        """Save the settings from the configuration widget."""
        config_widget.save_settings()

    def do_user_config(self, parent=None, plugin_action=None):
        """
        This method shows a configuration dialog for this plugin.
        It returns True if the user clicks OK, False otherwise.

        Args:
            parent: Parent widget for the dialog.
            plugin_action: The InterfaceAction instance (provides access to GUI/database).
        """
        from qt.core import QDialog, QDialogButtonBox, QVBoxLayout

        from .config import ConfigWidget

        config_widget = ConfigWidget(plugin_action=plugin_action)

        dialog = QDialog(parent)
        dialog.setWindowTitle(f"Configure {self.name}")
        dialog.resize(500, 600)
        layout = QVBoxLayout(dialog)
        layout.addWidget(config_widget.widget)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            config_widget.save_settings()
            return True
        return False
