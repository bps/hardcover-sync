"""
Proof-of-concept tests for pytest-qt integration.

These tests verify that pytest-qt works with our Qt shim and can test
dialog widgets. This file should be run separately from other tests
since it requires a real Qt environment.

Run with: uv run pytest test/qt_tests/ -v
"""

from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout


class SimpleTestDialog(QDialog):
    """A simple dialog for testing pytest-qt integration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Test Dialog")

        layout = QVBoxLayout(self)

        self.label = QLabel("Initial text")
        layout.addWidget(self.label)

        self.button = QPushButton("Click me")
        self.button.clicked.connect(self._on_click)
        layout.addWidget(self.button)

        self.click_count = 0

    def _on_click(self):
        self.click_count += 1
        self.label.setText(f"Clicked {self.click_count} time(s)")


class TestPyTestQtIntegration:
    """Verify pytest-qt works with our setup."""

    def test_qtbot_fixture_works(self, qtbot):
        """Test that the qtbot fixture is available."""
        assert qtbot is not None

    def test_create_simple_dialog(self, qtbot):
        """Test creating a simple dialog widget."""
        dialog = SimpleTestDialog()
        qtbot.addWidget(dialog)

        assert dialog.label.text() == "Initial text"
        assert dialog.click_count == 0

    def test_button_click_simulation(self, qtbot):
        """Test simulating a button click."""
        dialog = SimpleTestDialog()
        qtbot.addWidget(dialog)

        # Simulate button click
        dialog.button.click()

        assert dialog.click_count == 1
        assert dialog.label.text() == "Clicked 1 time(s)"

    def test_multiple_clicks(self, qtbot):
        """Test multiple button clicks."""
        dialog = SimpleTestDialog()
        qtbot.addWidget(dialog)

        for _ in range(3):
            dialog.button.click()

        assert dialog.click_count == 3
        assert dialog.label.text() == "Clicked 3 time(s)"


class TestQtShimWorks:
    """Verify the qt.core shim works correctly."""

    def test_qt_core_import(self):
        """Test that qt.core imports work."""
        from qt.core import QDialog, QLabel, QPushButton, Qt

        assert QDialog is not None
        assert QLabel is not None
        assert QPushButton is not None
        assert Qt is not None

    def test_qt_constants(self):
        """Test that Qt constants are accessible."""
        from qt.core import Qt

        # Test some common Qt constants
        assert hasattr(Qt, "ItemFlag")
        assert hasattr(Qt, "CheckState")
