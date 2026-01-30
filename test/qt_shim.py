"""
Qt shim module for testing with pytest-qt.

This module provides a `qt.core` compatible interface that wraps PyQt6,
allowing the plugin dialogs to be tested with real Qt widgets outside
of Calibre's runtime environment.
"""

import sys
from types import ModuleType

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Create a module that forwards qt.core imports to PyQt6
qt_core_shim = ModuleType("qt.core")

# Add all classes to the shim module
qt_core_shim.Qt = Qt  # type: ignore[attr-defined]
qt_core_shim.QUrl = QUrl  # type: ignore[attr-defined]
qt_core_shim.QAbstractItemView = QAbstractItemView  # type: ignore[attr-defined]
qt_core_shim.QApplication = QApplication  # type: ignore[attr-defined]
qt_core_shim.QCheckBox = QCheckBox  # type: ignore[attr-defined]
qt_core_shim.QComboBox = QComboBox  # type: ignore[attr-defined]
qt_core_shim.QDialog = QDialog  # type: ignore[attr-defined]
qt_core_shim.QDialogButtonBox = QDialogButtonBox  # type: ignore[attr-defined]
qt_core_shim.QFormLayout = QFormLayout  # type: ignore[attr-defined]
qt_core_shim.QFrame = QFrame  # type: ignore[attr-defined]
qt_core_shim.QGroupBox = QGroupBox  # type: ignore[attr-defined]
qt_core_shim.QHBoxLayout = QHBoxLayout  # type: ignore[attr-defined]
qt_core_shim.QHeaderView = QHeaderView  # type: ignore[attr-defined]
qt_core_shim.QLabel = QLabel  # type: ignore[attr-defined]
qt_core_shim.QLineEdit = QLineEdit  # type: ignore[attr-defined]
qt_core_shim.QListWidget = QListWidget  # type: ignore[attr-defined]
qt_core_shim.QListWidgetItem = QListWidgetItem  # type: ignore[attr-defined]
qt_core_shim.QMenu = QMenu  # type: ignore[attr-defined]
qt_core_shim.QProgressBar = QProgressBar  # type: ignore[attr-defined]
qt_core_shim.QPushButton = QPushButton  # type: ignore[attr-defined]
qt_core_shim.QSpinBox = QSpinBox  # type: ignore[attr-defined]
qt_core_shim.QTableWidget = QTableWidget  # type: ignore[attr-defined]
qt_core_shim.QTableWidgetItem = QTableWidgetItem  # type: ignore[attr-defined]
qt_core_shim.QToolButton = QToolButton  # type: ignore[attr-defined]
qt_core_shim.QTreeWidget = QTreeWidget  # type: ignore[attr-defined]
qt_core_shim.QTreeWidgetItem = QTreeWidgetItem  # type: ignore[attr-defined]
qt_core_shim.QVBoxLayout = QVBoxLayout  # type: ignore[attr-defined]
qt_core_shim.QWidget = QWidget  # type: ignore[attr-defined]

# Also create the parent qt module
qt_shim = ModuleType("qt")
qt_shim.core = qt_core_shim  # type: ignore[attr-defined]


def install_qt_shim():
    """Install the Qt shim into sys.modules."""
    sys.modules["qt"] = qt_shim
    sys.modules["qt.core"] = qt_core_shim


def uninstall_qt_shim():
    """Remove the Qt shim from sys.modules."""
    sys.modules.pop("qt", None)
    sys.modules.pop("qt.core", None)
