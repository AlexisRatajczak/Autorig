from PySide6 import QtWidgets, QtCore
from datetime import datetime
import json

import maya.cmds as cmds

from ....core.autorig.rigData import init_rigData
from ....core.autorig.modules import update_guides
from ....core import log
from .. import color_picker
from importlib import reload

reload(init_rigData)
reload(update_guides)
reload(color_picker)


# ==========================================================
# COLLAPSIBLE BOX
# ==========================================================

class CollapsibleBox(QtWidgets.QWidget):

    def __init__(self, title, parent=None):
        """Initialize the collapsible box with its title."""
        super().__init__(parent)

        self.toggle_button = QtWidgets.QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(QtCore.Qt.RightArrow)

        self.content = QtWidgets.QFrame()
        self.content.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.content.setVisible(False)

        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 8, 8, 8)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content)

        self.toggle_button.clicked.connect(self.toggle)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def toggle(self):
        """Toggle the visibility of the collapsible content."""
        visible = self.toggle_button.isChecked()

        self.content.setVisible(visible)
        self.toggle_button.setArrowType(
            QtCore.Qt.DownArrow if visible else QtCore.Qt.RightArrow
        )

    def add_widget(self, widget):
        """Add a widget to the collapsible content."""
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        """Add a layout to the collapsible content."""
        self.content_layout.addLayout(layout)


# ==========================================================
# SETTINGS PANEL
# ==========================================================

class SettingsPanel(QtWidgets.QWidget):

    COLORS = {
        "Left": [
            "FK Main",
            "FK Secondary",
            "IK Main",
            "IK Secondary",
            "Tweaker Main",
            "Tweaker Secondary"
        ],
        "Center": [
            "FK Main",
            "FK Secondary",
            "IK Main",
            "IK Secondary",
            "Tweaker Main",
            "Tweaker Secondary"
        ],
        "Right": [
            "FK Main",
            "FK Secondary",
            "IK Main",
            "IK Secondary",
            "Tweaker Main",
            "Tweaker Secondary"
        ]
    }

    def __init__(self, rig_data=None, parent=None):
        """Initialize the settings panel and its rig data."""
        super().__init__(parent)

        self.rig_data = rig_data
        self.color_buttons = {}

        self.build_widgets()
        self.build_layout()
        self.create_connections()
        self.set_style()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the settings panel."""

        self.title = QtWidgets.QLabel("RIG SETTINGS")
        self.title.setAlignment(QtCore.Qt.AlignCenter)

        self.rig_name = QtWidgets.QLineEdit()

        self.major_version = QtWidgets.QSpinBox()
        self.major_version.setMinimum(1)
        self.major_version.setValue(1)

        self.minor_version = QtWidgets.QSpinBox()
        self.minor_version.setMinimum(0)

        self.author = QtWidgets.QLineEdit()

        self.creation_date = QtWidgets.QLineEdit(
            datetime.now().strftime("%Y-%m-%d")
        )

        self.last_build_date = QtWidgets.QLineEdit()

        self.rig_scale = QtWidgets.QDoubleSpinBox()
        self.rig_scale.setRange(0.001, 100)
        self.rig_scale.setValue(1)

        self.control_size = QtWidgets.QDoubleSpinBox()
        self.control_size.setRange(0.001, 100)
        self.control_size.setValue(1)

        for side, colors in self.COLORS.items():
            self.color_buttons[side] = {}

            for color in colors:
                default_rgb = tuple(
                    init_rigData.DEFAULT_COLORS.get(side, {}).get(color, (1.0, 1.0, 1.0))
                )

                button = QtWidgets.QPushButton()
                button.setFixedSize(45, 25)
                button.setCursor(QtCore.Qt.PointingHandCursor)
                button.setProperty("rgb", default_rgb)

                self.color_buttons[side][color] = button
                self.set_color_button(button, default_rgb)

        self.pre_step_list = QtWidgets.QListWidget()
        self.pre_step_list.setFixedHeight(80)
        self.pre_step_add_button = QtWidgets.QPushButton("Add...")
        self.pre_step_remove_button = QtWidgets.QPushButton("Remove")

        self.post_step_list = QtWidgets.QListWidget()
        self.post_step_list.setFixedHeight(80)
        self.post_step_add_button = QtWidgets.QPushButton("Add...")
        self.post_step_remove_button = QtWidgets.QPushButton("Remove")

        self.update_guides_button = QtWidgets.QPushButton("Update Guides")
        self.update_guides_button.setToolTip(
            "Met à jour les modules de la scène d'après leur attributes.json : "
            "attributs manquants ajoutés, enums mis à jour."
        )

        self.remove_obsolete_checkbox = QtWidgets.QCheckBox("Remove obsolete attributes")
        self.remove_obsolete_checkbox.setToolTip(
            "Supprime aussi des data nodes les attributs qui ne sont plus dans le schéma."
        )

        self.create_button = QtWidgets.QPushButton("Create Rig Data")
        self.update_button = QtWidgets.QPushButton("Update")

    def build_layout(self):
        """Build the settings panel layout."""

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 10, 0, 0)
        root_layout.setSpacing(10)

        root_layout.addWidget(self.title)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        root_layout.addWidget(scroll)

        container = QtWidgets.QWidget()
        scroll.setWidget(container)

        main_layout = QtWidgets.QVBoxLayout(container)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        general_frame = QtWidgets.QFrame()
        general_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)

        general_layout = QtWidgets.QFormLayout(general_frame)
        general_layout.setSpacing(8)

        version_layout = QtWidgets.QHBoxLayout()
        version_layout.addWidget(self.major_version)
        version_layout.addWidget(QtWidgets.QLabel("."))
        version_layout.addWidget(self.minor_version)
        version_layout.addStretch()

        general_layout.addRow("Rig Name", self.rig_name)
        general_layout.addRow("Version", version_layout)
        general_layout.addRow("Author", self.author)
        general_layout.addWidget(self.separator())
        general_layout.addRow("Creation", self.creation_date)
        general_layout.addRow("Last Build", self.last_build_date)

        build = CollapsibleBox("◆ Build Settings")

        build_frame = QtWidgets.QFrame()
        build_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)

        build_layout = QtWidgets.QFormLayout(build_frame)
        build_layout.setSpacing(8)
        build_layout.addRow("Rig Scale", self.rig_scale)
        build_layout.addRow("Control Size", self.control_size)

        build.add_widget(build_frame)

        colors = CollapsibleBox("◆ Controller Colors")

        for side, buttons in self.color_buttons.items():
            side_box = CollapsibleBox(f"● {side}")

            side_frame = QtWidgets.QFrame()
            side_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)

            grid = QtWidgets.QGridLayout(side_frame)
            grid.setSpacing(8)

            rows = [
                ("FK Main", "FK Secondary"),
                ("IK Main", "IK Secondary"),
                ("Tweaker Main", "Tweaker Secondary")
            ]

            for row, pair in enumerate(rows):
                for column, name in enumerate(pair):
                    label = QtWidgets.QLabel(name)
                    button = buttons[name]

                    grid.addWidget(label, row, column * 2)
                    grid.addWidget(button, row, column * 2 + 1)

                if row == 1:
                    separator = QtWidgets.QFrame()
                    separator.setFrameShape(QtWidgets.QFrame.HLine)
                    separator.setFrameShadow(QtWidgets.QFrame.Sunken)

                    grid.addWidget(separator, row + 1, 0, 1, 4)

            side_box.add_widget(side_frame)
            colors.add_widget(side_box)

        custom_steps = CollapsibleBox("◆ Custom Steps")

        custom_steps_frame = QtWidgets.QFrame()
        custom_steps_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)

        custom_steps_layout = QtWidgets.QVBoxLayout(custom_steps_frame)
        custom_steps_layout.setSpacing(6)

        custom_steps_layout.addWidget(QtWidgets.QLabel("Pre Build"))
        custom_steps_layout.addWidget(self.pre_step_list)

        pre_step_buttons = QtWidgets.QHBoxLayout()
        pre_step_buttons.addWidget(self.pre_step_add_button)
        pre_step_buttons.addWidget(self.pre_step_remove_button)
        custom_steps_layout.addLayout(pre_step_buttons)

        custom_steps_layout.addWidget(self.separator())

        custom_steps_layout.addWidget(QtWidgets.QLabel("Post Build"))
        custom_steps_layout.addWidget(self.post_step_list)

        post_step_buttons = QtWidgets.QHBoxLayout()
        post_step_buttons.addWidget(self.post_step_add_button)
        post_step_buttons.addWidget(self.post_step_remove_button)
        custom_steps_layout.addLayout(post_step_buttons)

        custom_steps.add_widget(custom_steps_frame)

        guides = CollapsibleBox("◆ Guides")

        guides_frame = QtWidgets.QFrame()
        guides_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)

        guides_layout = QtWidgets.QVBoxLayout(guides_frame)
        guides_layout.setSpacing(6)
        guides_layout.addWidget(self.remove_obsolete_checkbox)
        guides_layout.addWidget(self.update_guides_button)

        guides.add_widget(guides_frame)

        button_frame = QtWidgets.QFrame()
        button_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)

        button_layout = QtWidgets.QHBoxLayout(button_frame)
        button_layout.setSpacing(10)
        button_layout.addWidget(self.create_button)
        button_layout.addWidget(self.update_button)

        main_layout.addWidget(general_frame)
        main_layout.addWidget(self.separator())
        main_layout.addWidget(build)
        main_layout.addWidget(self.separator())
        main_layout.addWidget(colors)
        main_layout.addWidget(self.separator())
        main_layout.addWidget(custom_steps)
        main_layout.addWidget(self.separator())
        main_layout.addWidget(guides)
        main_layout.addWidget(self.separator())
        main_layout.addWidget(button_frame)
        main_layout.addStretch()

    def create_connections(self):
        """Connect the settings panel widgets to their actions."""

        self.create_button.clicked.connect(self.create_rig_data)
        self.update_button.clicked.connect(self.update_rig_data)
        self.update_guides_button.clicked.connect(self.update_scene_guides)

        self.pre_step_add_button.clicked.connect(lambda: self.add_script_path(self.pre_step_list))
        self.pre_step_remove_button.clicked.connect(lambda: self.remove_script_path(self.pre_step_list))
        self.post_step_add_button.clicked.connect(lambda: self.add_script_path(self.post_step_list))
        self.post_step_remove_button.clicked.connect(lambda: self.remove_script_path(self.post_step_list))

        for side, buttons in self.color_buttons.items():
            for name, button in buttons.items():
                button.clicked.connect(
                    lambda checked=False, s=side, n=name: self.pick_color(s, n)
                )

    def set_style(self):
        """Apply the settings panel stylesheet."""
        self.setStyleSheet(
            """
            QToolButton {
                font-weight: bold;
                padding: 6px;
                text-align: left;
            }
            """
        )

    def separator(self):
        """Create and return a horizontal separator widget."""
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)

        return line

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def add_script_path(self, list_widget):
        """Browse for a .py script and append it to 'list_widget'."""

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Script", "", "Python Files (*.py)"
        )

        if not path:
            return

        list_widget.addItem(path)

    def remove_script_path(self, list_widget):
        """Remove the currently selected script(s) from 'list_widget'."""

        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    def script_list_paths(self, list_widget):
        """Return the list of script paths currently shown in 'list_widget'."""

        return [list_widget.item(i).text() for i in range(list_widget.count())]

    def load_script_list(self, list_widget, raw_json):
        """Populate 'list_widget' from a JSON-encoded list of script paths."""

        list_widget.clear()

        if not raw_json:
            return

        try:
            paths = json.loads(raw_json)
        except (TypeError, ValueError):
            return

        if isinstance(paths, list):
            list_widget.addItems(paths)

    def pick_color(self, side, name):
        """Open the custom color picker and update the selected color."""
        button = self.color_buttons[side][name]
        current = button.property("rgb") or (1.0, 1.0, 1.0)

        rgb = color_picker.ColorPickerDialog.getColor(initial=current, parent=self)

        if rgb is None:
            return

        button.setProperty("rgb", rgb)
        self.set_color_button(button, rgb)

    def set_color_button(self, button, rgb):
        """Update a color button appearance from an RGB value."""
        r = int(rgb[0] * 255)
        g = int(rgb[1] * 255)
        b = int(rgb[2] * 255)

        button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgb({r},{g},{b});
                border: 1px solid #222;
                border-radius: 3px;
            }}
            """
        )

    def load_data(self, rig_data):
        """Load an existing rig data node into the settings panel."""
        if not rig_data:
            return

        if not cmds.objExists(rig_data):
            log.error(f"Rig Data '{rig_data}' does not exist.")
            return

        rig_name = cmds.getAttr(f"{rig_data}.rigName")

        self.rig_data = init_rigData.RigData(rig_name)
        self.rig_data.data_node = rig_data

        self.rig_name.setText(
            self.rig_data.get_attribute("rigName") or ""
        )

        self.major_version.setValue(
            self.rig_data.get_attribute("majorVersion")
        )

        self.minor_version.setValue(
            self.rig_data.get_attribute("minorVersion")
        )

        self.author.setText(
            self.rig_data.get_attribute("author") or ""
        )

        self.creation_date.setText(
            self.rig_data.get_attribute("creationDate") or ""
        )

        self.last_build_date.setText(
            self.rig_data.get_attribute("lastBuildDate") or ""
        )

        self.rig_scale.setValue(
            self.rig_data.get_attribute("rigScale")
        )

        self.control_size.setValue(
            self.rig_data.get_attribute("controlSize")
        )

        self.load_script_list(self.pre_step_list, self.rig_data.get_attribute("preBuildScripts"))
        self.load_script_list(self.post_step_list, self.rig_data.get_attribute("postBuildScripts"))

        for side, buttons in self.color_buttons.items():
            for name, button in buttons.items():
                color_name = init_rigData.RigData.color_name(
                    side,
                    name
                )

                if not cmds.objExists(f"{rig_data}.{color_name}"):
                    continue

                rgb = self.rig_data.get_attribute(color_name)

                if not rgb:
                    continue

                if isinstance(rgb, list) and len(rgb) == 1:
                    rgb = rgb[0]

                self.set_color_button(button, rgb)
                button.setProperty("rgb", tuple(rgb))

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def create_rig_data(self):
        """Create or load the rig data node and update its attributes."""
        rig_name = self.rig_name.text().strip()

        if not rig_name:
            log.warning("Please enter a rig name.")
            return

        if cmds.objExists(f"{rig_name}_RIG_DATA"):
            log.warning(f"{rig_name}_RIG_DATA already exists.")
            self.rig_data = init_rigData.RigData(rig_name)
            self.rig_data.data_node = f"{rig_name}_RIG_DATA"

        else:
            self.rig_data = init_rigData.RigData(rig_name)
            self.rig_data.create()

        self.update_rig_data()

    def update_rig_data(self):
        """Update rig data attributes from the panel values."""
        if not self.rig_data:
            return

        values = {
            "rigName": self.rig_name.text(),
            "majorVersion": self.major_version.value(),
            "minorVersion": self.minor_version.value(),
            "author": self.author.text(),
            "creationDate": self.creation_date.text(),
            "lastBuildDate": self.last_build_date.text(),
            "rigScale": self.rig_scale.value(),
            "controlSize": self.control_size.value(),
            "preBuildScripts": json.dumps(self.script_list_paths(self.pre_step_list)),
            "postBuildScripts": json.dumps(self.script_list_paths(self.post_step_list)),
        }

        for attr, value in values.items():
            self.rig_data.set_attribute(attr, value)

        self.update_colors()

        log.success(f"Rig data '{self.rig_data.rig_name}' updated.")

    def update_scene_guides(self):
        """Met à jour les attributs des modules de la scène (update_guides)."""

        remove_obsolete = self.remove_obsolete_checkbox.isChecked()

        if remove_obsolete:

            answer = QtWidgets.QMessageBox.question(
                self,
                "Update Guides",
                "Supprimer aussi les attributs obsolètes des modules de la scène ?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )

            if answer != QtWidgets.QMessageBox.Yes:
                return

        cmds.undoInfo(openChunk=True, chunkName="Update Guides")

        try:
            update_guides.update_guides(remove_obsolete=remove_obsolete)
        finally:
            cmds.undoInfo(closeChunk=True)

    def update_colors(self):
        """Update all rig controller colors from the panel."""
        if not self.rig_data:
            return

        for side, buttons in self.color_buttons.items():
            for name, button in buttons.items():
                rgb = button.property("rgb")

                if rgb is None:
                    continue

                color_name = init_rigData.RigData.color_name(side, name)
                self.rig_data.set_attribute(color_name, rgb)
