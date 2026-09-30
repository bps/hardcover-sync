"""Regression tests for Calibre's plugin configuration entry points."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hardcover_sync import HardcoverSyncPlugin
from hardcover_sync import config


@pytest.fixture
def configuration(monkeypatch):
    """Use real configuration logic with stateful Qt inputs and a fake library."""
    columns = {
        "#status": {"datatype": "enumeration", "name": "Status"},
        "#pages": {"datatype": "int", "name": "Pages"},
        "#percent": {"datatype": "float", "name": "Percent"},
        "#started": {"datatype": "datetime", "name": "Started"},
        "#finished": {"datatype": "datetime", "name": "Finished"},
        "#read": {"datatype": "bool", "name": "Read"},
        "#review": {"datatype": "comments", "name": "Review"},
    }
    mappings = {
        "status_column": "#status",
        "rating_column": "rating",
        "progress_column": "#pages",
        "progress_percent_column": "#percent",
        "date_started_column": "#started",
        "date_read_column": "#finished",
        "is_read_column": "#read",
        "review_column": "#review",
    }
    prefs = {**config.DEFAULT_PREFS, **mappings}
    monkeypatch.setattr(config, "prefs", prefs)

    model = SimpleNamespace(custom_columns=columns, orig_headers={"rating": "Rating"})
    gui = SimpleNamespace(library_view=SimpleNamespace(model=Mock(return_value=model)))
    action = SimpleNamespace(gui=gui)
    plugin = HardcoverSyncPlugin(None)
    plugin.actual_plugin_ = action

    def make_combo(parent):
        combo = Mock()
        combo.setCurrentIndex.side_effect = lambda index: combo.currentIndex.configure_mock(
            return_value=index
        )
        return combo

    def make_line_edit():
        line_edit = Mock()
        line_edit.text.return_value = ""
        line_edit.setText.side_effect = lambda text: line_edit.text.configure_mock(
            return_value=text
        )
        return line_edit

    qt = sys.modules["qt.core"]
    monkeypatch.setattr(qt, "QComboBox", Mock(side_effect=make_combo))
    monkeypatch.setattr(qt, "QLineEdit", Mock(side_effect=make_line_edit))
    dialog = Mock()
    dialog.exec.return_value = 0
    dialog_class = Mock(return_value=dialog)
    dialog_class.DialogCode = SimpleNamespace(Accepted=1, Rejected=0)
    monkeypatch.setattr(qt, "QDialog", dialog_class)

    widgets = []
    widget_class = config.ConfigWidget

    def capture_widget(*args, **kwargs):
        widget = widget_class(*args, **kwargs)
        widgets.append(widget)
        return widget

    monkeypatch.setattr(config, "ConfigWidget", capture_widget)
    return SimpleNamespace(
        plugin=plugin,
        action=action,
        gui=gui,
        prefs=prefs,
        mappings=mappings,
        widgets=widgets,
        dialog=dialog,
    )


@pytest.mark.parametrize("entry_point", ["preferences", "toolbar", "config_widget"])
def test_configuration_entry_points_offer_library_columns(configuration, entry_point):
    """Preferences must discover the same columns as the toolbar menu."""
    ctx = configuration
    if entry_point == "preferences":
        ctx.plugin.do_user_config(ctx.gui)
    elif entry_point == "toolbar":
        # An explicitly supplied action must take precedence over the stored one.
        ctx.plugin.actual_plugin_ = SimpleNamespace(gui=None)
        ctx.plugin.do_user_config(ctx.gui, plugin_action=ctx.action)
    else:
        ctx.plugin.config_widget()

    widget = ctx.widgets[0]
    assert widget.status_combo.column_names == ["", "#status"]
    assert widget.rating_combo.column_names == ["", "#pages", "#percent", "rating"]
    assert widget.progress_combo.column_names == ["", "#pages"]
    assert widget.progress_percent_combo.column_names == ["", "#pages", "#percent"]
    for pref_key, column in ctx.mappings.items():
        combo = getattr(widget, f"{pref_key.removesuffix('_column')}_combo")
        assert column in combo.column_names
        assert combo.get_selected_column() == column


@pytest.mark.parametrize("entry_point", ["preferences", "toolbar"])
def test_configuration_save_preserves_existing_mappings(configuration, entry_point):
    """Accepting either dialog must not erase the saved column selections."""
    ctx = configuration
    ctx.dialog.exec.return_value = 1
    kwargs = {"plugin_action": ctx.action} if entry_point == "toolbar" else {}

    assert ctx.plugin.do_user_config(ctx.gui, **kwargs) is True

    assert {key: ctx.prefs[key] for key in ctx.mappings} == ctx.mappings


def test_cancel_configuration_leaves_preferences_unchanged(configuration):
    ctx = configuration
    before = dict(ctx.prefs)

    assert ctx.plugin.do_user_config(ctx.gui) is False

    assert ctx.prefs == before
