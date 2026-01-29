"""
Hardcover Sync - A Calibre plugin for syncing with Hardcover.app

This plugin allows bidirectional synchronization of reading status,
ratings, progress, and lists between Calibre and Hardcover.app.
"""

from calibre.customize import InterfaceActionBase

try:
    from ._version import __version__, __version_tuple__
except ImportError:
    __version__ = "0.0.0.dev0"
    __version_tuple__ = (0, 0, 0, "dev0")


class HardcoverSyncPlugin(InterfaceActionBase):
    """
    The main plugin class that Calibre uses to load the plugin.
    """

    name = "Hardcover Sync"
    description = "Sync reading status, ratings, and progress with Hardcover.app"
    author = "Brian Ryall"
    version = __version_tuple__[:3] if len(__version_tuple__) >= 3 else (0, 0, 0)
    minimum_calibre_version = (5, 0, 0)

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

    def do_user_config(self, parent=None):
        """
        This method shows a configuration dialog for this plugin.
        It returns True if the user clicks OK, False otherwise.
        """
        from calibre.gui2 import error_dialog
        from qt.core import QDialog, QDialogButtonBox, QVBoxLayout

        from .config import ConfigWidget

        config_widget = ConfigWidget()

        dialog = QDialog(parent)
        dialog.setWindowTitle(f"Configure {self.name}")
        layout = QVBoxLayout(dialog)
        layout.addWidget(config_widget)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec_() == QDialog.Accepted:
            config_widget.save_settings()
            return True
        return False
