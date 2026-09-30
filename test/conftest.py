"""
Pytest configuration for Hardcover Sync tests.

This conftest sets up mocks for calibre modules before any test imports,
allowing us to test the plugin code without having Calibre installed.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class FakeInterfaceActionBase:
    """Keep plugin subclasses real so their entry points can be tested."""

    def __init__(self, plugin_path=None):
        self.actual_plugin_ = None


# Mock calibre modules before any imports
calibre_mock = MagicMock()
calibre_mock.InterfaceActionBase = FakeInterfaceActionBase
sys.modules["calibre"] = calibre_mock
sys.modules["calibre.customize"] = calibre_mock
sys.modules["calibre.gui2"] = calibre_mock
sys.modules["calibre.gui2.actions"] = calibre_mock
sys.modules["calibre.utils.config"] = calibre_mock

# Mock Qt modules (Calibre's qt.core abstraction)
qt_mock = MagicMock()
sys.modules["qt"] = qt_mock
sys.modules["qt.core"] = qt_mock
