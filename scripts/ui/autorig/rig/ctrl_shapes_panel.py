import json
import os

from PySide6 import QtWidgets, QtCore

import maya.cmds as cmds

from ....core import serialize

from importlib import reload
reload(serialize)


# ==========================================================
# CTRL SHAPES PANEL
# ==========================================================

class CtrlShapesPanel(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.import_data = None

        self.build_widgets()
        self.build_layout()
        self.create_connections()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):

        self.export_hint = QtWidgets.QLabel("Selected ctrls, or every ctrl if nothing is selected.")
        self.export_hint.setWordWrap(True)

        self.export_button = QtWidgets.QPushButton("Export Shapes...")

        self.file_field = QtWidgets.QLineEdit()
        self.file_field.setReadOnly(True)
        self.file_field.setPlaceholderText("No .json loaded")

        self.browse_button = QtWidgets.QPushButton("Browse...")
        self.browse_button.setFixedWidth(80)

        self.info_label = QtWidgets.QLabel("")
        self.info_label.setWordWrap(True)

        self.import_button = QtWidgets.QPushButton("Import Shapes")
        self.import_button.setEnabled(False)

        self.report_label = QtWidgets.QLabel("")
        self.report_label.setWordWrap(True)

    def build_layout(self):

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        root.addWidget(scroll)

        container = QtWidgets.QWidget()
        scroll.setWidget(container)

        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        export_box = QtWidgets.QFrame()
        export_box.setFrameShape(QtWidgets.QFrame.StyledPanel)
        export_layout = QtWidgets.QVBoxLayout(export_box)

        export_layout.addWidget(self._title("EXPORT CTRL SHAPES"))
        export_layout.addWidget(self.export_hint)
        export_layout.addWidget(self.export_button)

        layout.addWidget(export_box)

        import_box = QtWidgets.QFrame()
        import_box.setFrameShape(QtWidgets.QFrame.StyledPanel)
        import_layout = QtWidgets.QVBoxLayout(import_box)

        import_layout.addWidget(self._title("IMPORT CTRL SHAPES"))

        file_row = QtWidgets.QHBoxLayout()
        file_row.addWidget(self.file_field)
        file_row.addWidget(self.browse_button)
        import_layout.addLayout(file_row)

        import_layout.addWidget(self.info_label)
        import_layout.addWidget(self.import_button)
        import_layout.addWidget(self.report_label)

        layout.addWidget(import_box)
        layout.addStretch()

    def _title(self, text):
        label = QtWidgets.QLabel(text)
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setStyleSheet("font-weight: bold;")
        return label

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def create_connections(self):

        self.export_button.clicked.connect(self.export_shapes)
        self.browse_button.clicked.connect(self.browse_json)
        self.import_button.clicked.connect(self.import_shapes)

    def clear_import(self):
        """Forget the loaded file: Import stays disabled until a valid .json is loaded."""

        self.import_data = None
        self.file_field.clear()
        self.info_label.setText("")
        self.import_button.setEnabled(False)

    def show_import_report(self, report):
        """Result of an import: counts, then the ctrls missing from the scene and the failures."""

        lines = [
            f"Applied: {len(report['applied'])}",
            f"Missing: {len(report['missing'])}",
            f"Failed: {len(report['failed'])}",
        ]

        if report["missing"]:
            lines.append("Missing ctrls: " + ", ".join(report["missing"]))

        for ctrl, error in report["failed"]:
            lines.append(f"! {ctrl}: {error}")

        self.report_label.setText("\n".join(lines))

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def export_shapes(self):

        """Export the selected ctrls (else every ctrl), the list being read before the file dialog."""

        ctrls = serialize.list_ctrls()

        if not ctrls:
            cmds.warning("No ctrl to export.")
            return

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Ctrl Shapes", "ctrl_shapes.json", "JSON (*.json)"
        )

        if not path:
            return

        try:
            data = serialize.export_ctrl_shapes(path, controls=ctrls)
        except Exception as error:
            cmds.warning(f"Export failed: {error}")
            return

        self.report_label.setText(
            f"Exported {len(data['controls'])} ctrl(s) -> {os.path.basename(path)}"
        )

    def browse_json(self):

        """Load a ctrl shapes .json and show how many of its ctrls exist in the scene."""

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Ctrl Shapes", "", "JSON (*.json)"
        )

        if not path:
            return

        self.clear_import()
        self.report_label.setText("")

        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as error:
            cmds.warning(f"Could not read '{path}': {error}")
            return

        controls = data.get("controls") if isinstance(data, dict) else None

        if not controls:
            cmds.warning(f"'{os.path.basename(path)}' has no ctrl shapes.")
            return

        self.import_data = data
        self.file_field.setText(path)
        self.import_button.setEnabled(True)

        found = sum(1 for ctrl in controls if cmds.objExists(ctrl))

        self.info_label.setText(f"Ctrls: {len(controls)}    In scene: {found}")

    def import_shapes(self):

        """Apply the loaded shapes on every ctrl that exists in the scene."""

        if not self.import_data:
            cmds.warning("Load a .json first.")
            return

        try:
            report = serialize.import_ctrl_shapes(self.import_data)
        except Exception as error:
            cmds.warning(f"Import failed: {error}")
            return

        self.show_import_report(report)
