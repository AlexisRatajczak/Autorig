from PySide6 import QtWidgets, QtCore

from importlib import reload

import maya.cmds as cmds

from ....core.autorig.build import mainbuild, postbuild
from ....core.autorig.build import prebuild
from ....core.autorig.modules import registry
reload(mainbuild)
reload(postbuild)
reload(prebuild)
reload(registry)


class MainPanel(QtWidgets.QFrame):

    guideSelected = QtCore.Signal(object)
    rigDataChanged = QtCore.Signal(object)

    CONTEXT_MENU_ACTIONS = {
        "Select Root": "context_select_root",
        "Rename...": "context_rename",
        "Duplicate": "context_duplicate",
        "Create Mirror": "context_mirror",
        "Delete": "context_delete",
    }

    MULTI_CONTEXT_MENU_ACTIONS = {
        "Select Roots": "context_select_roots_multi",
        "Duplicate": "context_duplicate_multi",
        "Create Mirror": "context_mirror_multi",
        "Delete": "context_delete_multi",
    }

    def __init__(self, parent=None):
        """Initialize the main panel and refresh its content."""
        super().__init__(parent)

        self.data_rig = None
        self.settings = QtCore.QSettings("AlexisTools", "AutoRig")

        self.build_widgets()
        self.build_layout()
        self.refresh()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the main panel."""

        self.rig_combo = QtWidgets.QComboBox()
        self.rig_combo.setFixedHeight(32)

        combo_font = self.rig_combo.font()
        combo_font.setPointSize(10)
        self.rig_combo.setFont(combo_font)

        self.build_button = QtWidgets.QPushButton("Build")
        self.build_button.setFixedSize(120, 32)

        button_font = self.build_button.font()
        button_font.setPointSize(10)
        self.build_button.setFont(button_font)

        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.setFixedSize(80, 32)
        self.refresh_button.setFont(button_font)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        self.select_from_scene_button = QtWidgets.QPushButton("Select From Scene")
        self.select_from_scene_button.setFixedHeight(32)
        self.select_from_scene_button.setFont(button_font)

    def build_layout(self):
        """Build the main panel layout."""

        rig_layout = QtWidgets.QHBoxLayout()
        rig_layout.setContentsMargins(0, 0, 0, 0)
        rig_layout.setSpacing(4)

        rig_layout.addWidget(self.refresh_button)
        rig_layout.addWidget(self.rig_combo)
        rig_layout.addWidget(self.build_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(rig_layout)
        layout.addWidget(self.tree)
        layout.addWidget(self.select_from_scene_button)

        self.rig_combo.currentIndexChanged.connect(self.rig_changed)
        self.build_button.clicked.connect(self.build_rig)
        self.refresh_button.clicked.connect(self.refresh_outliner)
        self.tree.itemSelectionChanged.connect(self.select_in_maya)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.select_from_scene_button.clicked.connect(self.select_from_scene)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def rig_changed(self):
        """Update the selected rig data and refresh the outliner."""
        self.data_rig = self.rig_combo.currentData()

        self.settings.setValue("lastRigData", self.data_rig)

        self.refresh_outliner()

        self.rigDataChanged.emit(self.data_rig)

        print("Data Rig :", self.data_rig)

    def refresh(self):
        """Refresh the rig combo box and guide outliner."""
        self.refresh_combo()
        self.refresh_outliner()

    def refresh_combo(self):
        """Refresh the rig data combo box from Maya network nodes."""
        self.rig_combo.blockSignals(True)

        self.rig_combo.clear()
        self.rig_combo.addItem("All Guides", None)

        rigs = sorted(cmds.ls("*_RIG_DATA", type="network") or [])

        for rig in rigs:
            self.rig_combo.addItem(rig, rig)

        last_rig = self.settings.value("lastRigData")
        index = self.rig_combo.findData(last_rig) if last_rig else -1

        if index != -1:
            self.rig_combo.setCurrentIndex(index)

        self.rig_combo.blockSignals(False)

        self.data_rig = self.rig_combo.currentData()

    def refresh_outliner(self):
        """Refresh the guide hierarchy displayed in the outliner."""

        self.tree.setUpdatesEnabled(False)

        try:
            self.tree.clear()

            rig = self.data_rig

            if rig is None:
                guides = sorted(cmds.ls("*_GUIDE_DATA", type="network") or [])
            else:
                guides = cmds.listConnections(
                    f"{rig}.rigData",
                    source=True,
                    destination=False
                ) or []
                guides.sort()

            self.list_guides_data = guides

            items = {}

            for guide in guides:
                item = QtWidgets.QTreeWidgetItem([guide])
                item.setData(0, QtCore.Qt.UserRole, guide)
                items[guide] = item

            for guide in guides:
                parent = cmds.listConnections(
                    f"{guide}.parent",
                    source=True,
                    destination=False
                ) or []

                if parent and parent[0] in items:
                    items[parent[0]].addChild(items[guide])
                else:
                    self.tree.addTopLevelItem(items[guide])

            self.tree.expandAll()
        finally:
            self.tree.setUpdatesEnabled(True)

    def select_rig_data(self, rig_data):
        """Select a rig data node in the rig combo box."""
        index = self.rig_combo.findData(f"{rig_data}_RIG_DATA")

        if index == -1:
            return False

        self.rig_combo.setCurrentIndex(index)
        return True

    def select_guide(self, guide_name):
        """Select and reveal a guide in the outliner by its name."""

        if not guide_name:
            return False

        def find_item(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                data = item.data(0, QtCore.Qt.UserRole)

                if data == guide_name:
                    return item

                result = find_item(item)

                if result:
                    return result

            return None

        target = None

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, QtCore.Qt.UserRole) == guide_name:
                target = item
                break

            target = find_item(item)

            if target:
                break

        if not target:
            return False

        self.tree.setCurrentItem(target)
        self.tree.scrollToItem(
            target,
            QtWidgets.QAbstractItemView.PositionAtCenter
        )

        return True

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def build_rig(self):
        """Build the currently selected rig."""

        rig_data = self.rig_combo.currentData()

        if not rig_data:
            print("Aucun RIG_DATA sélectionné.")
            return

        prebuild_rig = prebuild.PreBuild(rig_data)
        print(prebuild_rig.hierarchy_data)
        mainbuild_rig = mainbuild.MainBuild(prebuild_rig.hierarchy_data)
        postbuild_rig = postbuild.PostBuild(rig_data)

        print("Build Rig :", rig_data)

    def select_in_maya(self):
        """Select the guide root(s) in Maya. Settings only shown for a single selection."""

        items = self.tree.selectedItems()

        if not items:
            return

        if len(items) == 1:

            data = items[0].data(0, QtCore.Qt.UserRole)

            self.guideSelected.emit(data)

            root = cmds.listConnections(f"{data}.rootGuide", source=True, destination=False) or []

            if root:
                cmds.select(root[0], replace=True)
            else:
                cmds.select(data, replace=True)

            return

        targets = []

        for item in items:

            data = item.data(0, QtCore.Qt.UserRole)

            if not data:
                continue

            root = cmds.listConnections(f"{data}.rootGuide", source=True, destination=False) or []
            targets.append(root[0] if root else data)

        if targets:
            cmds.select(targets, replace=True)

        self.guideSelected.emit(None)

    def select_from_scene(self):
        """Select in the tree the guide_data connected to the current Maya selection."""

        selection = cmds.ls(selection=True) or []

        if not selection:
            cmds.warning("Nothing selected in the scene.")
            return

        data_node = registry.get_base_guides_class().get_data_node(selection[0])

        if not data_node:
            cmds.warning(f"'{selection[0]}' is not connected to a guide module.")
            return

        if not self.select_guide(data_node):
            cmds.warning(f"'{data_node}' is not listed in the outliner (check the rig filter).")

    # ------------------------------------------------------
    # CONTEXT MENU
    # ------------------------------------------------------

    def show_context_menu(self, position):
        """Build and show the right-click menu for the selected tree item(s)."""

        items = self.tree.selectedItems()

        if not items:
            item = self.tree.itemAt(position)

            if not item:
                return

            items = [item]

        menu = QtWidgets.QMenu(self.tree)

        if len(items) > 1:

            for label, method_name in self.MULTI_CONTEXT_MENU_ACTIONS.items():

                method = getattr(self, method_name, None)

                if not method:
                    continue

                action = menu.addAction(label)
                action.triggered.connect(
                    lambda checked=False, its=items, m=method: m(its)
                )

        else:

            item = items[0]

            for label, method_name in self.CONTEXT_MENU_ACTIONS.items():

                method = getattr(self, method_name, None)

                if not method:
                    continue

                action = menu.addAction(label)
                action.triggered.connect(
                    lambda checked=False, i=item, m=method: m(i)
                )

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def context_select_root(self, item):
        """Select the module's root guide in the Maya scene."""

        data = item.data(0, QtCore.Qt.UserRole)

        registry.get_base_guides_class().select_root_node(data)

    def context_rename(self, item):
        """Prompt for a new baseName and rename the module accordingly."""

        data = item.data(0, QtCore.Qt.UserRole)

        if not data or not cmds.objExists(data):
            return

        current_name = cmds.getAttr(f"{data}.baseName")

        new_name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename Module",
            "Base Name:",
            text=current_name
        )

        if not ok or not new_name:
            return

        instance = registry.load_guide(data)

        if not instance:
            return

        instance.rename(new_name)

        self.refresh_outliner()
        self.select_guide(instance.data_node)

    def context_duplicate(self, item):
        """Duplicate the module (guides.Guides.duplicate)."""

        data = item.data(0, QtCore.Qt.UserRole)

        if not data or not cmds.objExists(data):
            return

        instance = registry.load_guide(data)

        if not instance:
            return

        duplicated = instance.duplicate()

        if not duplicated:
            return

        self.refresh_outliner()
        self.select_guide(duplicated.data_node)

    def context_mirror(self, item):
        """Create a mirrored duplicate of the module (guides.Guides.create_mirror)."""

        data = item.data(0, QtCore.Qt.UserRole)

        if not data or not cmds.objExists(data):
            return

        instance = registry.load_guide(data)

        if not instance:
            return

        side_map = {"Left": "Right", "Right": "Left"}
        replace_side = side_map.get(instance.side)

        if not replace_side:
            cmds.warning("Only Left/Right modules can be mirrored.")
            return

        mirrored = instance.create_mirror(replace_side=replace_side)

        if not mirrored:
            return

        self.refresh_outliner()
        self.select_guide(mirrored.data_node)

    def context_delete(self, item):
        """Delete the module (root guide + data node) after confirmation."""

        data = item.data(0, QtCore.Qt.UserRole)

        if not data or not cmds.objExists(data):
            return

        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete Module",
            f"Delete '{data}' and its guides?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if confirm != QtWidgets.QMessageBox.Yes:
            return

        instance = registry.load_guide(data)

        if instance:
            instance.delete()

        self.refresh_outliner()

    # ------------------------------------------------------
    # CONTEXT MENU (MULTI-SELECTION)
    # ------------------------------------------------------

    def context_select_roots_multi(self, items):
        """Select the root guides of every given tree item in the Maya scene."""

        roots = []

        for item in items:

            data = item.data(0, QtCore.Qt.UserRole)
            root = registry.get_base_guides_class().get_root_node(data)

            if root:
                roots.append(root)

        if roots:
            cmds.select(roots, replace=True)

    def context_duplicate_multi(self, items):
        """Duplicate every selected module, then refresh once."""

        duplicated_nodes = []

        for item in items:

            data = item.data(0, QtCore.Qt.UserRole)

            if not data or not cmds.objExists(data):
                continue

            instance = registry.load_guide(data)

            if not instance:
                continue

            duplicated = instance.duplicate()

            if duplicated:
                duplicated_nodes.append(duplicated.data_node)

        self.refresh_outliner()

        if duplicated_nodes:
            self.select_guide(duplicated_nodes[-1])

    def context_mirror_multi(self, items):
        """Create a mirror of every selected Left/Right module, then refresh once."""

        side_map = {"Left": "Right", "Right": "Left"}
        mirrored_nodes = []

        for item in items:

            data = item.data(0, QtCore.Qt.UserRole)

            if not data or not cmds.objExists(data):
                continue

            instance = registry.load_guide(data)

            if not instance:
                continue

            replace_side = side_map.get(instance.side)

            if not replace_side:
                continue

            mirrored = instance.create_mirror(replace_side=replace_side)

            if mirrored:
                mirrored_nodes.append(mirrored.data_node)

        self.refresh_outliner()

        if mirrored_nodes:
            self.select_guide(mirrored_nodes[-1])

    def context_delete_multi(self, items):
        """Delete every selected module after a single confirmation."""

        data_nodes = [item.data(0, QtCore.Qt.UserRole) for item in items]
        data_nodes = [data for data in data_nodes if data and cmds.objExists(data)]

        if not data_nodes:
            return

        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete Modules",
            f"Delete {len(data_nodes)} module(s) and their guides?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if confirm != QtWidgets.QMessageBox.Yes:
            return

        for data_node in data_nodes:

            instance = registry.load_guide(data_node)

            if instance:
                instance.delete()

        self.refresh_outliner()
