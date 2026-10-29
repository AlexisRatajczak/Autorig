from PySide6 import QtWidgets, QtCore
from pathlib import Path
import importlib
from importlib import reload
import ast

import maya.cmds as cmds

from ....core.autorig.build import mainbuild, postbuild
from ....core.autorig.build import prebuild
from ....core.autorig.modules import registry
from ....core import log

reload(mainbuild)
reload(prebuild)
reload(postbuild)
reload(registry)


# ==========================================================
# MODULE ITEM WIDGET
# ==========================================================

class ModuleItemWidget(QtWidgets.QFrame):

    create_clicked = QtCore.Signal(dict)

    def __init__(self, module_data, parent=None):
        """Initialize the module item with its module data."""

        super().__init__(parent)

        self.module_data = module_data
        self.module_name = module_data["module_name"]

        self.build_widgets()
        self.build_layout()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the module item."""

        self.name_label = QtWidgets.QLabel(self.module_name)
        self.create_button = QtWidgets.QPushButton("Create")

    def build_layout(self):
        """Build the module item layout."""

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(self.name_label)
        layout.addStretch()
        layout.addWidget(self.create_button)

        self.create_button.clicked.connect(lambda: self.create_clicked.emit(self.module_data))


# ==========================================================
# GUIDES PANEL
# ==========================================================

class GuidesPanel(QtWidgets.QFrame):

    MODULES_DIR = registry.MODULES_DIR

    create_clicked = QtCore.Signal(dict)
    create_data_node = QtCore.Signal(object)

    def __init__(self, parent=None):
        """Initialize the guides panel and load available modules."""

        super().__init__(parent)

        self.modules = []

        self.setObjectName("GuidesPanel")

        self.build_widgets()
        self.build_layout()
        self.populate_modules()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the guides panel."""

        self.title = QtWidgets.QLabel("GUIDES")
        self.title.setAlignment(QtCore.Qt.AlignCenter)

        self.name_field = QtWidgets.QLineEdit()
        self.name_field.setPlaceholderText("Search Guides...")

        self.module_list = QtWidgets.QListWidget()

    def build_layout(self):
        """Build the guides panel layout."""

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.name_field)
        layout.addWidget(self.module_list)

        self.name_field.textChanged.connect(self.filter_modules)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def refresh_modules(self):
        """Refresh the module list."""

        self.module_list.clear()

        for module in self.modules:

            item = QtWidgets.QListWidgetItem()
            widget = ModuleItemWidget(module)

            item.setSizeHint(widget.sizeHint())

            self.module_list.addItem(item)
            self.module_list.setItemWidget(item, widget)

            widget.create_clicked.connect(self.create_clicked.emit)

    def filter_modules(self, text):
        """Filter visible modules according to the search text."""

        text = text.lower()

        for index in range(self.module_list.count()):

            item = self.module_list.item(index)
            widget = self.module_list.itemWidget(item)

            item.setHidden(text not in widget.module_name.lower())

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def populate_modules(self):
        """Scan module folders and find their Guides class."""

        self.modules.clear()

        modules_path = Path(self.MODULES_DIR)

        if not modules_path.exists():
            print(f"Modules directory does not exist: {modules_path}")
            return

        for module_dir in modules_path.iterdir():

            if not module_dir.is_dir():
                continue

            if module_dir.name == "__pycache__":
                continue

            guides_file = module_dir / "guides.py"

            if not guides_file.exists():
                continue

            try:

                with open(guides_file, "r", encoding="utf-8") as file:
                    tree = ast.parse(file.read())

                settings = {}
                module_name = module_dir.name
                guides_class = None

                for node in tree.body:

                    if not isinstance(node, ast.ClassDef):
                        continue

                    if node.name != "Guides":
                        continue

                    guides_class = node.name

                    for class_node in node.body:

                        if not isinstance(class_node, ast.Assign):
                            continue

                        for target in class_node.targets:

                            if isinstance(target, ast.Name) and target.id == "MODULE_NAME":

                                module_name = ast.literal_eval(class_node.value)

                for node in tree.body:

                    if not isinstance(node, ast.Assign):
                        continue

                    for target in node.targets:

                        if isinstance(target, ast.Name) and target.id == "SETTINGS":

                            settings = ast.literal_eval(node.value)

                if guides_class:

                    self.modules.append({
                        "module": module_dir.name,
                        "module_name": module_name,
                        "filepath": str(guides_file),
                        "file": f"guides.py",
                        "class": guides_class,
                        "settings": settings
                    })

            except Exception as e:

                print(f"Error loading module '{module_dir.name}': {e}")

        self.modules.sort(key=lambda module: module["module_name"].lower())

        self.refresh_modules()

    def create_module(self, module, rig_data):
        """Import, instantiate, create and connect a guide module."""

        if not rig_data:
            log.error(
                f"Cannot create module '{module['module_name']}' : no rig data "
                "selected/created. Create or select a rig first."
            )
            return

        rig_data_node = f"{rig_data}_RIG_DATA"

        if not cmds.objExists(rig_data_node):
            log.error(
                f"Cannot create module '{module['module_name']}' : rig data node "
                f"'{rig_data_node}' does not exist in the scene."
            )
            return

        log.info(f"Creating module '{module['module_name']}' on rig data '{rig_data}'...")

        module_path = f"scripts.core.autorig.modules.{module['module']}.guides"

        python_module = importlib.import_module(module_path)
        reload(python_module)

        cls = getattr(python_module, module["class"])

        instance = cls("name")

        instance.create()

        instance.connect_rig_data(rig_data)

        print("=" * 50)
        print("MODULE NAME :", module["module_name"])
        print("MODULE      :", module["module"])
        print("FILE        :", module["file"])
        print("CLASS       :", module["class"])
        print("SETTINGS    :", module["settings"])
        print("RIG DATA    :", rig_data)
        print("=" * 50)

        log.success(f"Module '{module['module_name']}' created and connected to '{rig_data}'.")

        self.create_data_node.emit(instance.data_node)
