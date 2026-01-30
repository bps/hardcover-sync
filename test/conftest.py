"""
Pytest configuration for Hardcover Sync tests.

This conftest sets up mocks for calibre modules before any test imports,
allowing us to test the plugin code without having Calibre installed.

For Qt widget tests using pytest-qt, see test/qt_tests/ which has its own
conftest that sets up real Qt bindings instead of mocks.

NOTE: pytest-qt is disabled by default via pyproject.toml (-p no:qt).
Use `just test-qt` to run Qt widget tests with pytest-qt enabled.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock


def _is_qt_test():
    """Check if we're running Qt widget tests."""
    # Check for qt_tests in command line args
    for arg in sys.argv:
        if "qt_tests" in arg:
            return True
    return False


# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


# Only mock modules for non-Qt tests
# Qt tests use real PyQt6 bindings via the qt_shim
if not _is_qt_test():
    # Mock calibre modules before any imports
    calibre_mock = MagicMock()
    sys.modules["calibre"] = calibre_mock
    sys.modules["calibre.customize"] = calibre_mock
    sys.modules["calibre.gui2"] = calibre_mock
    sys.modules["calibre.gui2.actions"] = calibre_mock
    sys.modules["calibre.utils.config"] = calibre_mock

    # Mock Qt modules (Calibre's qt.core abstraction)
    qt_mock = MagicMock()
    sys.modules["qt"] = qt_mock
    sys.modules["qt.core"] = qt_mock
