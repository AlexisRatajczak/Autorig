"""Modeling checker window (Maya 2026 / PySide6, falls back to PySide2)."""
import json
import os
import traceback
from functools import partial

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2024 and older
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance

from maya import cmds

from ...core.utilities import geo_utilities, settings_utilities

from ...core import modeling_checks

WINDOW_NAME = "modelingCheckerWindow"
MAX_LISTED = 2000

APP_NAME = "modeling_checker"
ENV_VAR = "MODELING_CHECKER_SETTINGS"
DEFAULT_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "config", "mode_settings.json"
)


def _settings_user_path():
    return settings_utilities.user_path(APP_NAME, env_var=ENV_VAR)


def _settings_defaults():
    return settings_utilities.defaults(DEFAULT_SETTINGS_PATH)


def _settings_load():
    return settings_utilities.load(DEFAULT_SETTINGS_PATH, APP_NAME, env_var=ENV_VAR)


def _settings_save(data):
    return settings_utilities.save(data, APP_NAME, env_var=ENV_VAR)

IDLE, OK, FAIL, ERROR = "idle", "ok", "fail", "error"
COLORS = {IDLE: "#777777", OK: "#5fb760", FAIL: "#d9534f", ERROR: "#e0a030"}


def maya_main_window():
    import maya.OpenMayaUI as omui

    pointer = omui.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None


class SettingsDialog(QtWidgets.QDialog):
    """Raw JSON editor for the settings file."""

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modeling Checker - Settings")
        self.resize(560, 640)
        self.data = None

        self.editor = QtWidgets.QPlainTextEdit(json.dumps(data, indent=4))
        self.editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.editor.setStyleSheet("font-family: Consolas, Menlo, monospace;")
        path_label = QtWidgets.QLabel("Saved to: {}".format(_settings_user_path()))
        path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        path_label.setWordWrap(True)

        save_button = QtWidgets.QPushButton("Save")
        reset_button = QtWidgets.QPushButton("Reset to defaults")
        cancel_button = QtWidgets.QPushButton("Cancel")
        save_button.clicked.connect(self.on_save)
        reset_button.clicked.connect(self.on_reset)
        cancel_button.clicked.connect(self.reject)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(reset_button)
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(path_label)
        layout.addWidget(self.editor)
        layout.addLayout(buttons)

    def on_save(self):
        try:
            data = json.loads(self.editor.toPlainText())
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid JSON", str(exc))
            return
        _settings_save(data)
        self.data = _settings_load()
        self.accept()

    def on_reset(self):
        self.editor.setPlainText(json.dumps(_settings_defaults(), indent=4))


class CheckRow(object):
    """Widgets of one check line."""

    def __init__(self, check):
        self.check = check
        self.items = []
        self.arrow = QtWidgets.QToolButton()
        self.arrow.setArrowType(QtCore.Qt.RightArrow)
        self.arrow.setCheckable(True)
        self.arrow.setAutoRaise(True)
        self.arrow.setFixedSize(16, 16)
        self.arrow.setToolTip("Show / hide the description")
        self.description = QtWidgets.QLabel(check.description())
        self.description.setWordWrap(True)
        self.description.setStyleSheet("color: #9a9a9a; padding: 0px 4px 6px 4px;")
        self.description.setVisible(False)
        self.arrow.toggled.connect(self.set_expanded)
        self.enabled = QtWidgets.QCheckBox()
        self.status = QtWidgets.QLabel()
        self.status.setFixedSize(12, 12)
        self.label = QtWidgets.QLabel(check.label)
        self.count = QtWidgets.QLabel("-")
        self.count.setFixedWidth(50)
        self.count.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.check_button = QtWidgets.QPushButton("Check")
        self.select_button = QtWidgets.QPushButton("Select")
        self.fix_button = QtWidgets.QPushButton("Fix")
        for button in (self.check_button, self.select_button, self.fix_button):
            button.setFixedWidth(58)
        if not check.can_fix:
            self.fix_button.setToolTip("No automatic fix for this check")
        self.set_state(IDLE)

    def set_expanded(self, expanded):
        self.arrow.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.description.setVisible(expanded)

    def set_state(self, state, items=None):
        self.items = list(items or [])
        self.status.setStyleSheet(
            "background-color: {}; border-radius: 6px;".format(COLORS[state])
        )
        self.count.setText({IDLE: "-", OK: "OK", ERROR: "error"}.get(state, str(len(self.items))))
        self.refresh_buttons()

    def refresh_buttons(self):
        active = self.enabled.isChecked()
        self.label.setEnabled(active)
        self.check_button.setEnabled(active)
        self.select_button.setEnabled(active and bool(self.items))
        self.fix_button.setEnabled(active and bool(self.items) and self.check.can_fix)


class CheckerWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or maya_main_window())
        self.setObjectName(WINDOW_NAME)
        self.setWindowTitle("Modeling Checker")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.resize(520, 820)

        self.settings = _settings_load()
        self.checks = modeling_checks.create_all(self.settings)
        self.rows = {}
        self.listed = []
        self._build()
        self._apply_settings()

    # ------------------------------------------------------------------ ui
    def _build(self):
        self.scope_combo = QtWidgets.QComboBox()
        self.scope_combo.addItem("Whole scene", geo_utilities.SCENE)
        self.scope_combo.addItem("Selection + children", geo_utilities.SELECTION)
        check_all = QtWidgets.QPushButton("Check all")
        fix_all = QtWidgets.QPushButton("Fix all")
        settings_button = QtWidgets.QPushButton("Settings...")
        check_all.clicked.connect(self.run_all)
        fix_all.clicked.connect(self.fix_all)
        settings_button.clicked.connect(self.edit_settings)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Scope"))
        top.addWidget(self.scope_combo, 1)
        top.addWidget(check_all)
        top.addWidget(fix_all)
        top.addWidget(settings_button)

        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        for category in modeling_checks.CATEGORIES:
            box = QtWidgets.QGroupBox(category)
            grid = QtWidgets.QGridLayout(box)
            grid.setColumnStretch(3, 1)
            grid.setVerticalSpacing(3)
            members = [c for c in self.checks if c.category == category]
            for line, check in enumerate(members):
                row = CheckRow(check)
                self.rows[check.id] = row
                widgets = (row.arrow, row.enabled, row.status, row.label, row.count,
                           row.check_button, row.select_button, row.fix_button)
                for column, widget in enumerate(widgets):
                    grid.addWidget(widget, line * 2, column)
                # description on its own line, under the label and the buttons
                grid.addWidget(row.description, line * 2 + 1, 3, 1, len(widgets) - 3)
                row.enabled.toggled.connect(partial(self.on_toggled, check))
                row.check_button.clicked.connect(partial(self.run_check, check))
                row.select_button.clicked.connect(partial(self.select_check, check))
                row.fix_button.clicked.connect(partial(self.fix_check, check))
            container_layout.addWidget(box)
        container_layout.addStretch()

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(container)

        self.result_label = QtWidgets.QLabel("Results")
        self.result_list = QtWidgets.QListWidget()
        self.result_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.result_list.itemSelectionChanged.connect(self.on_list_selection)
        results = QtWidgets.QWidget()
        results_layout = QtWidgets.QVBoxLayout(results)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.addWidget(self.result_label)
        results_layout.addWidget(self.result_list)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.addWidget(scroll)
        splitter.addWidget(results)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter)

    def _apply_settings(self):
        for row in self.rows.values():
            row.enabled.blockSignals(True)
            row.check.settings = self.settings
            row.check.items = []
            row.enabled.setChecked(row.check.enabled)
            row.enabled.blockSignals(False)
            row.set_state(IDLE)
        self._show_results(None)

    def _scope(self):
        return self.scope_combo.currentData()

    def _show_results(self, check):
        self.result_list.blockSignals(True)
        self.result_list.clear()
        self.listed = []
        if check is None:
            self.result_label.setText("Results")
        else:
            items = self.rows[check.id].items
            self.listed = items[:MAX_LISTED]
            self.result_list.addItems(self.listed)
            extra = len(items) - len(self.listed)
            text = "{}: {} item(s)".format(check.label, len(items))
            if extra > 0:
                text += " - first {} listed, Select takes them all".format(MAX_LISTED)
            self.result_label.setText(text)
        self.result_list.blockSignals(False)

    # ------------------------------------------------------------- actions
    def on_toggled(self, check, state):
        self.settings.setdefault("checks", {})[check.id] = bool(state)
        _settings_save(self.settings)
        check.items = []
        self.rows[check.id].set_state(IDLE)

    def run_check(self, check, *_):
        row = self.rows[check.id]
        try:
            items = check.check(self._scope())
            row.set_state(FAIL if items else OK, items)
        except Exception:
            traceback.print_exc()
            cmds.warning("modeling_checker: '{}' failed, see Script Editor".format(check.label))
            check.items = []
            row.set_state(ERROR)
        self._show_results(check)
        return row.items

    def select_check(self, check, *_):
        self._show_results(check)
        check.select()

    def fix_check(self, check, *_):
        row = self.rows[check.id]
        if not check.can_fix or not row.items:
            return
        try:
            with geo_utilities.undo_chunk("modelingChecker_" + check.id):
                check.fix()
        except Exception:
            traceback.print_exc()
            cmds.warning("modeling_checker: fix '{}' failed, see Script Editor".format(check.label))
        self.run_check(check)

    def _enabled_checks(self):
        return [c for c in self.checks if self.rows[c.id].enabled.isChecked()]

    def run_all(self):
        cmds.waitCursor(state=True)
        try:
            failed = [c for c in self._enabled_checks() if self.run_check(c)]
        finally:
            cmds.waitCursor(state=False)
        self._show_results(failed[0] if failed else None)
        if not failed:
            self.result_label.setText("Results - everything passed")

    def fix_all(self):
        cmds.waitCursor(state=True)
        try:
            for check in self._enabled_checks():
                if check.can_fix and self.run_check(check):
                    self.fix_check(check)
        finally:
            cmds.waitCursor(state=False)
        self.run_all()

    def on_list_selection(self):
        selected = [item.text() for item in self.result_list.selectedItems()]
        if selected:
            geo_utilities.select_items(selected)

    def edit_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() and dialog.data is not None:
            self.settings = dialog.data
            self._apply_settings()


_window = None


def close():
    global _window
    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except RuntimeError:
            pass
    _window = None


def show():
    global _window
    close()
    _window = CheckerWindow()
    _window.show()
    return _window
