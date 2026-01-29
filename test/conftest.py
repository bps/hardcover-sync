"""
Pytest configuration for Hardcover Sync tests.

This conftest sets up mocks for calibre modules before any test imports,
allowing us to test the plugin code without having Calibre installed.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock calibre modules before any imports
calibre_mock = MagicMock()
sys.modules["calibre"] = calibre_mock
sys.modules["calibre.customize"] = calibre_mock
sys.modules["calibre.gui2"] = calibre_mock
sys.modules["calibre.gui2.actions"] = calibre_mock
sys.modules["calibre.utils.config"] = calibre_mock

# Mock Qt modules
qt_mock = MagicMock()
sys.modules["qt"] = qt_mock
sys.modules["qt.core"] = qt_mock
sys.modules["PyQt5"] = qt_mock
sys.modules["PyQt5.Qt"] = qt_mock

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
