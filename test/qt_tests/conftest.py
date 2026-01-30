"""
Pytest configuration for Qt widget tests.

This conftest sets up the Qt shim for testing dialog widgets with real Qt
bindings via pytest-qt. It does NOT mock Qt modules like the main conftest.

These tests require a display (they won't run in headless CI without Xvfb).
"""

import os
import sys
from pathlib import Path

import pytest


# Check for display before running Qt tests
@pytest.fixture(scope="session", autouse=True)
def check_display():
    """Skip all Qt tests if no display is available."""
    if sys.platform == "linux" and not os.environ.get("DISPLAY"):
        pytest.skip("No display available - Qt tests require a display")


# Install Qt shim before any tests run
@pytest.fixture(scope="session", autouse=True)
def setup_qt_environment():
    """Set up the Qt environment before any tests."""
    # Add test directory to path so we can import qt_shim
    test_path = Path(__file__).parent.parent
    if str(test_path) not in sys.path:
        sys.path.insert(0, str(test_path))

    # Add src to path
    src_path = Path(__file__).parent.parent.parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    # Install the Qt shim
    from qt_shim import install_qt_shim

    install_qt_shim()

    # Mock only non-Qt calibre modules
    from unittest.mock import MagicMock

    calibre_mock = MagicMock()
    sys.modules["calibre"] = calibre_mock
    sys.modules["calibre.customize"] = calibre_mock
    sys.modules["calibre.gui2"] = calibre_mock
    sys.modules["calibre.gui2.actions"] = calibre_mock
    sys.modules["calibre.utils.config"] = calibre_mock
    sys.modules["calibre.ebooks.metadata.book.base"] = calibre_mock

    yield

    # Cleanup
    from qt_shim import uninstall_qt_shim

    uninstall_qt_shim()
