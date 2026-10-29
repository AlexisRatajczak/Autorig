import json
import os

from PySide6 import QtWidgets, QtCore

import maya.cmds as cmds

from ....core import serialize

from importlib import reload
reload(serialize)


# ==========================================================
# IMPORT / EXPORT PANEL
# ==========================================================

class ImportExportPanel(QtWidgets.QWidget):

    rigImported = QtCore.Signal()

    MODE_FULL = "full"
    MODE_RIG_DATA = "rig_data"
    MODE_MODULES = "modules"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.import_data = None
        self.import_path = None

        self.build_widgets()
        self.build_layout()
        self.create_connections()
        self.set_style()

        self.refresh_rig_combo()
        self.update_mode_ui()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_rig_combo()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):

        self.rig_combo = QtWidgets.QComboBox()
        self.export_button = QtWidgets.QPushButton("Export Rig...")

        self.file_field = QtWidgets.QLineEdit()
        self.file_field.setReadOnly(True)
        self.file_field.setPlaceholderText("No .json loaded")

        self.browse_button = QtWidgets.QPushButton("Browse...")
        self.browse_button.setFixedWidth(80)

        self.info_label = QtWidgets.QLabel("")
        self.info_label.setWordWrap(True)

        self.mode_full = QtWidgets.QRadioButton("Full rig (rig data + modules)")
        self.mode_rig_data = QtWidgets.QRadioButton("Rig data only")
        self.mode_modules = QtWidgets.QRadioButton("Selected modules (+ children)")
        self.mode_full.setChecked(True)

        self.mode_group = QtWidgets.QButtonGroup(self)
        self.mode_group.addButton(self.mode_full)
        self.mode_group.addButton(self.mode_rig_data)
        self.mode_group.addButton(self.mode_modules)

        self.module_list = QtWidgets.QListWidget()
        self.module_list.setFixedHeight(140)

        self.import_button = QtWidgets.QPushButton("Import")

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

        export_layout.addWidget(self._title("EXPORT"))
        export_layout.addWidget(self.rig_combo)
        export_layout.addWidget(self.export_button)

        layout.addWidget(export_box)

        import_box = QtWidgets.QFrame()
        import_box.setFrameShape(QtWidgets.QFrame.StyledPanel)
        import_layout = QtWidgets.QVBoxLayout(import_box)

        import_layout.addWidget(self._title("IMPORT"))

        file_row = QtWidgets.QHBoxLayout()
        file_row.addWidget(self.file_field)
        file_row.addWidget(self.browse_button)
        import_layout.addLayout(file_row)

        import_layout.addWidget(self.info_label)

        for button in (self.mode_full, self.mode_rig_data, self.mode_modules):
            import_layout.addWidget(button)

        import_layout.addWidget(self.module_list)
        import_layout.addWidget(self.import_button)
        import_layout.addWidget(self.report_label)

        layout.addWidget(import_box)
        layout.addStretch()

    def _title(self, text):
        label = QtWidgets.QLabel(text)
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setStyleSheet("font-weight: bold;")
        return label

    def set_style(self):
        """Local tweaks only - card/button/field look comes from the global theme."""
        self.setStyleSheet("")

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def create_connections(self):

        self.export_button.clicked.connect(self.export_rig)
        self.browse_button.clicked.connect(self.browse_json)
        self.import_button.clicked.connect(self.import_rig)

        for button in (self.mode_full, self.mode_rig_data, self.mode_modules):
            button.toggled.connect(self.update_mode_ui)

    def current_mode(self):

        if self.mode_rig_data.isChecked():
            return self.MODE_RIG_DATA

        if self.mode_modules.isChecked():
            return self.MODE_MODULES

        return self.MODE_FULL

    def update_mode_ui(self, *_):

        self.module_list.setVisible(self.current_mode() == self.MODE_MODULES)

    def populate_module_list(self, modules):

        self.module_list.clear()

        for module in modules:

            label = f"{module.get('node')}   [{module.get('module_type')}]"

            item = QtWidgets.QListWidgetItem(label)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Unchecked)
            item.setData(QtCore.Qt.UserRole, module.get("node"))

            self.module_list.addItem(item)

    def checked_modules(self):

        nodes = []

        for row in range(self.module_list.count()):

            item = self.module_list.item(row)

            if item.checkState() == QtCore.Qt.Checked:
                nodes.append(item.data(QtCore.Qt.UserRole))

        return nodes

    def show_report(self, report):

        lines = [f"Rig data: {report.get('rig_data')}"]
        lines.append(f"Created: {len(report.get('created', []))}")

        skipped = report.get("skipped", [])

        if skipped:
            lines.append(
                "Skipped: " + ", ".join(
                    f"{s['old']} ({s['module_type']})" for s in skipped
                )
            )

        for warning in report.get("warnings", []):
            lines.append(f"! {warning}")

        self.report_label.setText("\n".join(lines))

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def refresh_rig_combo(self):

        self.rig_combo.clear()

        for node in sorted(cmds.ls("*_RIG_DATA", type="network") or []):
            self.rig_combo.addItem(node, node)

    def export_rig(self):

        node = self.rig_combo.currentData()

        if not node or not cmds.objExists(node):
            cmds.warning("Select a rig data to export.")
            return

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Rig", f"{node}.json", "JSON (*.json)"
        )

        if not path:
            return

        try:
            data = serialize.export_rig(node, path)
        except Exception as error:
            cmds.warning(f"Export failed: {error}")
            return

        self.report_label.setText(
            f"Exported '{node}' ({len(data.get('modules', []))} modules) -> {os.path.basename(path)}"
        )

    def browse_json(self):

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Rig", "", "JSON (*.json)"
        )

        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as file:
                self.import_data = json.load(file)
        except Exception as error:
            cmds.warning(f"Could not read '{path}': {error}")
            self.import_data = None
            return

        self.import_path = path
        self.file_field.setText(path)

        rig_name = (self.import_data.get("rig_data") or {}).get("rig_name", "?")
        modules = self.import_data.get("modules") or []

        self.info_label.setText(
            f"Rig: {rig_name}    Modules: {len(modules)}"
        )

        self.populate_module_list(modules)
        self.report_label.setText("")

    def import_rig(self):

        if not self.import_data:
            cmds.warning("Load a .json first.")
            return

        mode = self.current_mode()

        try:

            if mode == self.MODE_RIG_DATA:
                report = serialize.rebuild_rig_data_only(self.import_data)

            elif mode == self.MODE_MODULES:

                nodes = self.checked_modules()

                if not nodes:
                    cmds.warning("Check at least one module.")
                    return

                report = serialize.rebuild_modules(self.import_data, nodes)

            else:
                report = serialize.rebuild_rig(self.import_data)

        except Exception as error:
            cmds.warning(f"Import failed: {error}")
            return

        self.show_report(report)
        self.rigImported.emit()
