from PySide6 import QtWidgets, QtCore, QtGui

from ....core import log
from ....core.utilities import blendshape_utilities
from ....core.blendshape import blendshape_workflow

from importlib import reload

reload(log)
reload(blendshape_utilities)
reload(blendshape_workflow)


ROLE_TYPE = QtCore.Qt.UserRole
ROLE_NODE = QtCore.Qt.UserRole + 1
ROLE_NAME = QtCore.Qt.UserRole + 2
ROLE_VALUE = QtCore.Qt.UserRole + 3


class TargetTree(QtWidgets.QTreeWidget):

    itemDropped = QtCore.Signal(QtWidgets.QTreeWidgetItem, object)

    def __init__(self, parent=None):
        """Initialize the tree with internal drag/drop routed to a signal."""
        super().__init__(parent)

        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def dropEvent(self, event):
        """Emit 'itemDropped' instead of letting Qt move the item itself."""

        dragged_item = self.currentItem()

        try:
            drop_point = event.position().toPoint()
        except AttributeError:
            drop_point = event.pos()

        target_item = self.itemAt(drop_point)

        event.accept()

        if dragged_item is not None:
            self.itemDropped.emit(dragged_item, target_item)


class BlendshapePanel(QtWidgets.QWidget):

    NODE_BACKGROUND_COLOR = "#1a1a1a"
    WEIGHT_SLIDER_SCALE = 1000
    INBETWEEN_RANGE = (-10.0, 10.0)

    # Emitted whenever the scene's mesh list may have changed (blendShape
    # created/deleted, target mesh created/deleted, ...) - the tab forwards
    # this to the mesh panel's refresh(), since that panel isn't owned here.
    meshPanelRefreshRequested = QtCore.Signal()

    def __init__(self, parent=None):
        """Initialize the blendshape panel (shape/group tools + target tree)."""
        super().__init__(parent)

        self.mesh = None
        self.blendshape_node = None

        self.build_widgets()
        self.build_layout()
        self.set_style()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the blendshape panel."""

        self.mesh_label = QtWidgets.QLabel("No mesh selected")
        self.mesh_label.setAlignment(QtCore.Qt.AlignCenter)

        self.create_blendshape_button = QtWidgets.QPushButton("+ Create Blendshape")

        self.create_group_button = QtWidgets.QPushButton("Group")
        self.create_shape_button = QtWidgets.QPushButton("Create Shape")
        self.import_template_button = QtWidgets.QPushButton("Import Template")

        self.target_tree = TargetTree()
        self.target_tree.setHeaderHidden(True)
        self.target_tree.setColumnCount(3)
        self.target_tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.target_tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        self.refresh_button = QtWidgets.QPushButton("Refresh")

        self.set_tools_enabled(False)
        self.create_group_button.setEnabled(False)

    def build_layout(self):
        """Build the blendshape panel layout."""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self.mesh_label)
        layout.addWidget(self.create_blendshape_button)

        tools_layout = QtWidgets.QHBoxLayout()
        tools_layout.setSpacing(6)
        tools_layout.addWidget(self.create_group_button)
        tools_layout.addWidget(self.create_shape_button)
        tools_layout.addWidget(self.import_template_button)

        layout.addLayout(tools_layout)
        layout.addWidget(self.target_tree)
        layout.addWidget(self.refresh_button)

        self.create_blendshape_button.clicked.connect(self.create_blendshape)
        self.create_group_button.clicked.connect(self.create_group)
        self.create_shape_button.clicked.connect(self.create_shape)
        self.import_template_button.clicked.connect(self.import_template)
        self.refresh_button.clicked.connect(self.refresh_tree)

        self.target_tree.currentItemChanged.connect(self.on_tree_selection_changed)
        self.target_tree.itemSelectionChanged.connect(self.on_tree_selection_items_changed)
        self.target_tree.itemClicked.connect(self.on_tree_item_clicked)
        self.target_tree.itemChanged.connect(self.on_tree_item_renamed)
        self.target_tree.itemDropped.connect(self.on_tree_item_dropped)
        self.target_tree.customContextMenuRequested.connect(self.show_tree_context_menu)

    def set_style(self):
        """Apply the visual style to the blendshape panel."""
        self.setStyleSheet("""
            QPushButton {
                padding: 6px;
            }

            QLineEdit {
                padding: 4px;
            }
        """)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def set_mesh(self, full_path):
        """Track 'full_path' as the current mesh and refresh its blendshape tree."""

        self.mesh = full_path
        self.mesh_label.setText(full_path.split("|")[-1])
        self.blendshape_node = None

        self.refresh_tree()

    def on_tree_selection_changed(self, current, previous):
        """Track which blendShape node the current tree selection belongs to."""

        self.blendshape_node = current.data(0, ROLE_NODE) if current else None

        self.set_tools_enabled(bool(self.blendshape_node))

    def on_tree_item_clicked(self, item, column):
        """Select an inbetween's (or the main target's) mesh, if it still exists."""

        if item.data(0, ROLE_TYPE) != "inbetween":
            return

        blendshape_workflow.select_inbetween(
            item.data(0, ROLE_NODE), item.data(0, ROLE_NAME), item.data(0, ROLE_VALUE)
        )

    def set_tools_enabled(self, enabled):
        """Enable/disable the shape/template tools."""

        self.create_shape_button.setEnabled(enabled)
        self.import_template_button.setEnabled(enabled)

    def on_tree_selection_items_changed(self):
        """Enable "Group" when the selection resolves to one or more shapes/groups."""

        self.create_group_button.setEnabled(bool(self.resolve_groupable_items()))

    def resolve_groupable_items(self):
        """
        Return the unique shape/group items to act on for the current tree
        selection - a selected value/inbetween row resolves to its parent
        shape. Returns [] if the selection contains anything else (a node),
        since only shapes and groups can be (re)grouped.
        """

        resolved = []
        seen_ids = set()

        for item in self.target_tree.selectedItems():

            item_type = item.data(0, ROLE_TYPE)

            if item_type == "inbetween":
                item = item.parent()
                item_type = item.data(0, ROLE_TYPE) if item else None

            if item_type not in ("target", "group"):
                return []

            if id(item) not in seen_ids:
                seen_ids.add(id(item))
                resolved.append(item)

        return resolved

    def _group_item_path(self, item):
        """Full nested group prefix (e.g. 'outer___inner') for a group tree item."""

        segments = []

        while item is not None and item.data(0, ROLE_TYPE) == "group":
            segments.append(item.data(0, ROLE_NAME))
            item = item.parent()

        return blendshape_workflow.GROUP_SEPARATOR.join(reversed(segments))

    def current_group_prefix(self):
        """
        Return the full nested group prefix (e.g. 'outer___inner') for the
        group containing the tree's current item - itself if it's a group,
        or its containing group if it's a shape/value - else None.
        """

        item = self.target_tree.currentItem()

        if not item:
            return None

        item_type = item.data(0, ROLE_TYPE)

        if item_type == "target":
            item = item.parent()
        elif item_type == "inbetween":
            item = item.parent()
            item = item.parent() if item else None

        if item is None or item.data(0, ROLE_TYPE) != "group":
            return None

        return self._group_item_path(item)

    def show_tree_context_menu(self, pos):
        """Show a context menu (Rename/Delete, mesh tools, + inbetween tools) for the item under the cursor."""

        item = self.target_tree.itemAt(pos)

        if not item:
            return

        item_type = item.data(0, ROLE_TYPE)
        is_main_inbetween = item_type == "inbetween" and item.data(0, ROLE_VALUE) == 1.0
        has_mesh_tools = item_type in ("target", "inbetween")

        menu = QtWidgets.QMenu(self)

        add_inbetween_action = menu.addAction("Add Inbetween...") if item_type == "target" else None

        create_mesh_action = None
        assign_mesh_action = None

        if has_mesh_tools:

            if add_inbetween_action is not None:
                menu.addSeparator()

            create_mesh_action = menu.addAction("Create Mesh")
            assign_mesh_action = menu.addAction("Assign Selected Mesh")

        rename_action = None
        set_value_action = None
        delete_action = None

        if is_main_inbetween:
            action_label = menu.addAction("Main target (value 1.0)")
            action_label.setEnabled(False)
        else:

            menu.addSeparator()

            rename_action = menu.addAction("Rename")

            if item_type == "inbetween":
                set_value_action = menu.addAction("Set Value...")

            delete_action = menu.addAction("Delete")

        action = menu.exec_(self.target_tree.viewport().mapToGlobal(pos))

        if action is None:
            return

        if action == add_inbetween_action:
            self.prompt_add_inbetween(item)
        elif action == create_mesh_action:
            self.create_tree_item_mesh(item)
        elif action == assign_mesh_action:
            self.assign_tree_item_mesh(item)
        elif action == rename_action:
            self.target_tree.editItem(item, 1 if item_type == "inbetween" else 0)
        elif action == set_value_action:
            self.prompt_set_inbetween_value(item)
        elif action == delete_action:
            self.delete_tree_item(item)

    def _resolve_item_target_value(self, item):
        """Return (node, alias, value) for a 'target' (value 1.0) or 'inbetween' tree item, else None."""

        item_type = item.data(0, ROLE_TYPE)

        if item_type == "target":
            return item.data(0, ROLE_NODE), item.data(0, ROLE_NAME), 1.0

        if item_type == "inbetween":
            return item.data(0, ROLE_NODE), item.data(0, ROLE_NAME), item.data(0, ROLE_VALUE)

        return None

    def _current_display(self, item):
        """Return an item's current name (target/group/node) or custom inbetween name."""

        item_type = item.data(0, ROLE_TYPE)

        if item_type == "target":
            return blendshape_workflow.split_target_group(item.data(0, ROLE_NAME))[1]

        if item_type == "inbetween":

            value = item.data(0, ROLE_VALUE)

            if value == 1.0:
                return item.text(1)

            return blendshape_workflow.get_inbetween_name(
                item.data(0, ROLE_NODE), item.data(0, ROLE_NAME), value
            ) or ""

        return item.data(0, ROLE_NAME)

    def _resolve_drop_destination(self, target_item):
        """
        Return the full nested group path an item was dropped onto (None
        for the root - dropped on the node itself or empty space). A drop
        on a shape/value row resolves to that row's own containing group.
        """

        if target_item is None:
            return None

        item_type = target_item.data(0, ROLE_TYPE)

        if item_type == "group":
            return self._group_item_path(target_item)

        if item_type in ("target", "inbetween"):

            parent_item = target_item.parent()

            if item_type == "inbetween" and parent_item is not None:
                parent_item = parent_item.parent()

            if parent_item is not None and parent_item.data(0, ROLE_TYPE) == "group":
                return self._group_item_path(parent_item)

        return None

    def refresh_tree(self):
        """Rebuild the whole node -> group -> target tree from the scene."""

        self.target_tree.blockSignals(True)

        try:

            self.target_tree.clear()

            if not self.mesh:
                return

            node_font = self.target_tree.font()
            node_font.setBold(True)

            if node_font.pointSize() > 0:
                node_font.setPointSize(node_font.pointSize() + 4)
            elif node_font.pixelSize() > 0:
                node_font.setPixelSize(node_font.pixelSize() + 6)
            else:
                node_font.setPointSize(14)

            node_background = QtGui.QBrush(QtGui.QColor(self.NODE_BACKGROUND_COLOR))

            for node in blendshape_utilities.get_blendshape_nodes(self.mesh):

                node_item = QtWidgets.QTreeWidgetItem([node])
                node_item.setFont(0, node_font)
                node_item.setFont(1, node_font)
                node_item.setBackground(0, node_background)
                node_item.setBackground(1, node_background)
                node_item.setFlags(
                    (node_item.flags() | QtCore.Qt.ItemIsEditable) & ~QtCore.Qt.ItemIsDragEnabled
                )
                node_item.setData(0, ROLE_TYPE, "node")
                node_item.setData(0, ROLE_NODE, node)
                node_item.setData(0, ROLE_NAME, node)

                self.target_tree.addTopLevelItem(node_item)
                self.target_tree.setItemWidget(node_item, 2, self._make_envelope_widget(node))

                self.build_node_targets(node_item, node)

            self.target_tree.expandAll()
            self.target_tree.resizeColumnToContents(0)
            self.target_tree.resizeColumnToContents(1)

        finally:
            self.target_tree.blockSignals(False)

    def build_node_targets(self, node_item, node):
        """Populate 'node_item' with its (possibly nested) groups and shapes."""

        aliases = blendshape_utilities.list_targets(node)

        self._build_group_level(node_item, node, [(alias, alias) for alias in aliases])

    def _build_group_level(self, parent_item, node, entries):
        """Recursively split 'entries' into nested group items and leaf shapes."""

        grouped = {}
        leaves = []

        for full_alias, tail in entries:

            group_name, rest = blendshape_workflow.split_target_group(tail)

            if group_name:
                grouped.setdefault(group_name, []).append((full_alias, rest))
            else:
                leaves.append((full_alias, tail))

        for group_name in sorted(grouped):

            group_item = self._make_group_item(node, group_name)
            parent_item.addChild(group_item)

            self._build_group_level(group_item, node, grouped[group_name])

        for full_alias, short_name in sorted(leaves, key=lambda entry: entry[1]):

            item = self._make_target_item(node, full_alias, short_name)
            parent_item.addChild(item)

            self.target_tree.setItemWidget(item, 2, self._make_target_weight_widget(node, full_alias))

    def _make_group_item(self, node, group_name):
        """Build a QTreeWidgetItem for a group."""

        item = QtWidgets.QTreeWidgetItem([group_name])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        item.setData(0, ROLE_TYPE, "group")
        item.setData(0, ROLE_NODE, node)
        item.setData(0, ROLE_NAME, group_name)

        return item

    def _make_target_item(self, node, alias, display_name):
        """Build a QTreeWidgetItem for a target ('alias' is the raw name, with any group prefix)."""

        item = QtWidgets.QTreeWidgetItem([display_name])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        item.setData(0, ROLE_TYPE, "target")
        item.setData(0, ROLE_NODE, node)
        item.setData(0, ROLE_NAME, alias)

        for entry in blendshape_workflow.list_inbetweens(node, alias):
            item.addChild(
                self._make_inbetween_item(node, alias, entry["value"], entry["name"], display_name)
            )

        return item

    def _make_inbetween_item(self, node, alias, value, name, target_display_name):
        """
        Build a QTreeWidgetItem for one of a target's inbetween values - two
        columns, like a table : the value (col 0, always shown) and its name
        (col 1) - for value 1.0 (the target itself), that name is the
        target's own display name ; for others, it's the custom name if set.
        """

        display_value = f"{value:g}"
        display_name = target_display_name if value == 1.0 else (name or "")

        item = QtWidgets.QTreeWidgetItem([display_value, display_name])
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsDragEnabled)
        item.setData(0, ROLE_TYPE, "inbetween")
        item.setData(0, ROLE_NODE, node)
        item.setData(0, ROLE_NAME, alias)
        item.setData(0, ROLE_VALUE, value)

        if value == 1.0:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            item.setFont(1, font)
        else:
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)

        return item

    def _make_envelope_widget(self, node):
        """Slider + spinbox (col 2) bound live to a blendShape node's overall '.envelope'."""

        current = blendshape_utilities.get_envelope(node)

        return self._build_weight_controls(
            current if current is not None else 1.0,
            0.0, 1.0,
            on_change=lambda value: blendshape_utilities.set_envelope(node, value),
        )

    def _make_target_weight_widget(self, node, alias):
        """Slider + spinbox (col 2) bound live to a target's own weight (its aliased attribute)."""

        current = blendshape_utilities.get_target_weight(node, alias)

        return self._build_weight_controls(
            current if current is not None else 0.0,
            0.0, 1.0,
            on_change=lambda value: blendshape_utilities.set_target_weight(node, alias, value),
        )

    def _build_weight_controls(self, value, minimum, maximum, on_change):
        """
        Build a slider + spinbox pair kept in sync with each other and with
        the scene (via 'on_change' at every change). The slider's integer
        range is scaled by WEIGHT_SLIDER_SCALE for sub-1.0 precision and
        clamped to [minimum, maximum] ; the spinbox allows typing values
        outside that range (e.g. an overdriven/negative weight) without
        extending the slider itself - it just clamps at whichever end.
        """

        container = QtWidgets.QWidget()

        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setMinimum(int(minimum * self.WEIGHT_SLIDER_SCALE))
        slider.setMaximum(int(maximum * self.WEIGHT_SLIDER_SCALE))

        spinbox = QtWidgets.QDoubleSpinBox()
        spinbox.setDecimals(3)
        spinbox.setRange(-10.0, 10.0)
        spinbox.setSingleStep(0.01)
        spinbox.setFixedWidth(76)
        spinbox.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        layout.addWidget(slider, 1)
        layout.addWidget(spinbox)

        slider.setValue(int(round(max(minimum, min(maximum, value)) * self.WEIGHT_SLIDER_SCALE)))
        spinbox.setValue(value)

        guard = {"active": False}

        def apply(new_value):

            if guard["active"]:
                return

            guard["active"] = True

            try:
                clamped = max(minimum, min(maximum, new_value))
                slider.setValue(int(round(clamped * self.WEIGHT_SLIDER_SCALE)))
                spinbox.setValue(new_value)
            finally:
                guard["active"] = False

            on_change(new_value)

        slider.valueChanged.connect(lambda raw: apply(raw / self.WEIGHT_SLIDER_SCALE))
        spinbox.valueChanged.connect(apply)

        return container

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def create_group(self):
        """
        Prompt for a group name and move every selected shape into it - or,
        for a selected group, move that whole group (and everything nested
        under it) so it becomes a child of the new group instead. A
        selected value/inbetween row is treated as its parent shape. Only
        enabled when the selection resolves to one or more shapes/groups -
        see on_tree_selection_items_changed.
        """

        items = self.resolve_groupable_items()

        if not items:
            return

        name, ok = QtWidgets.QInputDialog.getText(self, "Group", "Group name:")

        if not ok or not name.strip():
            return

        group_name = name.strip()

        for item in items:

            node = item.data(0, ROLE_NODE)
            item_type = item.data(0, ROLE_TYPE)

            if item_type == "target":
                self._move_target(node, item.data(0, ROLE_NAME), group_name)
            else:
                self._move_group(node, self._group_item_path(item), group_name)

        self.refresh_tree()

    def _move_target(self, node, alias, new_parent_path):
        """
        Move a shape so 'new_parent_path' becomes its (sole) group context
        ('' or None to move it to the root), replacing any group it was
        previously in - its leaf name is preserved.
        """

        leaf_name = alias.split(blendshape_workflow.GROUP_SEPARATOR)[-1]
        new_alias = (
            f"{new_parent_path}{blendshape_workflow.GROUP_SEPARATOR}{leaf_name}"
            if new_parent_path else leaf_name
        )

        if new_alias != alias:
            blendshape_workflow.rename_target(node, alias, new_alias)

    def _move_group(self, node, old_path, new_parent_path):
        """
        Move the group at 'old_path' (and every shape nested under it, at
        any depth) so its parent becomes 'new_parent_path' ('' or None to
        move it to the root) - its own leaf name is preserved.
        """

        leaf_name = old_path.split(blendshape_workflow.GROUP_SEPARATOR)[-1]
        new_path = (
            f"{new_parent_path}{blendshape_workflow.GROUP_SEPARATOR}{leaf_name}"
            if new_parent_path else leaf_name
        )

        if new_path == old_path:
            return

        old_prefix = f"{old_path}{blendshape_workflow.GROUP_SEPARATOR}"
        new_prefix = f"{new_path}{blendshape_workflow.GROUP_SEPARATOR}"

        for alias in blendshape_utilities.list_targets(node):

            if alias.startswith(old_prefix):
                blendshape_workflow.rename_target(node, alias, f"{new_prefix}{alias[len(old_prefix):]}")

    def create_blendshape(self):
        """Create a blendShape node on the currently selected mesh."""

        mesh = blendshape_utilities.get_selected_mesh()

        if not mesh:
            log.warning("Select a mesh first.")
            return

        self.set_mesh(mesh)

        if blendshape_utilities.create_blendshape(mesh):
            self.refresh_tree()
            self.meshPanelRefreshRequested.emit()

    def create_shape(self):
        """
        Prompt for a name and add a new target (weight 0) to the blendShape.
        If a group (or a target inside one) is currently selected in the
        tree, the new target's alias is prefixed with that group's name.
        """

        if not self.blendshape_node or not self.mesh:
            return

        name, ok = QtWidgets.QInputDialog.getText(self, "Create Shape", "Target name:")

        if not ok or not name.strip():
            return

        short_name = name.strip()
        group_prefix = self.current_group_prefix()

        target_name = (
            f"{group_prefix}{blendshape_workflow.GROUP_SEPARATOR}{short_name}"
            if group_prefix else short_name
        )

        blendshape_workflow.create_target(self.mesh, self.blendshape_node, target_name)

        self.refresh_tree()

    def import_template(self):
        """Pick a JSON template and bulk-create its groups and shapes."""

        if not self.blendshape_node or not self.mesh:
            return

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import Template",
            str(blendshape_workflow.TEMPLATES_DIR),
            "JSON Files (*.json)",
        )

        if not path:
            return

        blendshape_workflow.import_template(self.mesh, self.blendshape_node, path)

        self.refresh_tree()

    def _group_transform_for_alias(self, node, alias):
        """Return the DAG group transform a shape's mesh should be organized under, from its alias."""

        group_path, _, _ = alias.rpartition(blendshape_workflow.GROUP_SEPARATOR)

        if group_path:
            return blendshape_workflow.get_group_transform_name(node, group_path)

        return blendshape_workflow.get_targets_root_name(node)

    def create_tree_item_mesh(self, item):
        """Materialize (on demand) the mesh currently baked for a shape/value's delta."""

        resolved = self._resolve_item_target_value(item)

        if not resolved or not self.mesh:
            return

        node, alias, value = resolved

        if blendshape_workflow.select_inbetween(node, alias, value):
            log.warning("Mesh already exists - selected it instead of recreating it.")
            return

        organize_under = self._group_transform_for_alias(node, alias)

        if blendshape_workflow.create_target_mesh(
            self.mesh, node, alias, value=value, organize_under=organize_under
        ):
            self.refresh_tree()

    def assign_tree_item_mesh(self, item):
        """Bake the currently selected scene mesh's shape as a shape/value's delta."""

        resolved = self._resolve_item_target_value(item)

        if not resolved:
            return

        node, alias, value = resolved
        mesh = blendshape_utilities.get_selected_mesh()

        if not mesh:
            log.warning("Select a mesh in the scene first.")
            return

        if blendshape_workflow.assign_mesh_to_target(self.mesh, node, alias, value, mesh):
            self.refresh_tree()

    def prompt_add_inbetween(self, target_item):
        """Prompt for a value, then an optional name (e.g. 'up'/'down'), and add an inbetween."""

        node = target_item.data(0, ROLE_NODE)
        alias = target_item.data(0, ROLE_NAME)

        value, ok = QtWidgets.QInputDialog.getDouble(
            self, "Add Inbetween", "Value (any, except 1):",
            0.5, *self.INBETWEEN_RANGE, 3,
        )

        if not ok:
            return

        if value == 1.0:
            log.warning("Value 1.0 is reserved for the target itself.")
            return

        name, ok = QtWidgets.QInputDialog.getText(
            self, "Add Inbetween", "Name (optional, e.g. up/down):"
        )
        name = name.strip() if ok else ""

        blendshape_workflow.add_inbetween(self.mesh, node, alias, value, name=name or None)

        self.refresh_tree()

    def prompt_set_inbetween_value(self, item):
        """Prompt for a new value and move an existing inbetween to it."""

        node = item.data(0, ROLE_NODE)
        alias = item.data(0, ROLE_NAME)
        old_value = item.data(0, ROLE_VALUE)

        new_value, ok = QtWidgets.QInputDialog.getDouble(
            self, "Set Value", "New value (any, except 1):",
            old_value, *self.INBETWEEN_RANGE, 3,
        )

        if not ok or new_value == old_value:
            return

        if new_value == 1.0:
            log.warning("Value 1.0 is reserved for the target itself.")
            return

        blendshape_workflow.set_inbetween_value(self.mesh, node, alias, old_value, new_value)

        self.refresh_tree()

    def delete_tree_item(self, item):
        """Delete a node/group/target/inbetween item from the scene, after confirmation."""

        item_type = item.data(0, ROLE_TYPE)
        node = item.data(0, ROLE_NODE)
        name = item.data(0, ROLE_NAME)

        if item_type == "inbetween" and item.data(0, ROLE_VALUE) == 1.0:
            return

        if item_type == "inbetween":
            custom_name = self._current_display(item)
            label = f"{name} @ {item.text(0)}" + (f" ({custom_name})" if custom_name else "")
        else:
            label = name

        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete",
            f"Delete '{label}' ?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )

        if confirm != QtWidgets.QMessageBox.Yes:
            return

        if item_type == "node":
            blendshape_utilities.delete_blendshape_node(node)
        elif item_type == "group":
            blendshape_workflow.delete_target_group(node, name)
        elif item_type == "target":
            blendshape_utilities.delete_target(node, name)
        elif item_type == "inbetween":
            blendshape_workflow.delete_inbetween(node, name, item.data(0, ROLE_VALUE))

        self.refresh_tree()
        self.meshPanelRefreshRequested.emit()

    def on_tree_item_renamed(self, item, column):
        """
        Commit an inline (double-click) edit. Node/group/target are edited
        via column 0 (their name). An inbetween (!= 1.0) is only editable
        via column 1 (its custom name, e.g. 'up'/'down') - column 0 always
        reflects the real value and is reverted if somehow edited ; use
        "Set Value..." to actually move it.
        """

        item_type = item.data(0, ROLE_TYPE)
        node = item.data(0, ROLE_NODE)
        old_name = item.data(0, ROLE_NAME)

        editable_column = 1 if item_type == "inbetween" else 0

        if column != editable_column:
            self.refresh_tree()
            return

        new_text = item.text(column).strip()
        old_display = self._current_display(item)

        if new_text == old_display:
            return

        parent_item = item.parent()
        parent_group_path = (
            self._group_item_path(parent_item)
            if parent_item and parent_item.data(0, ROLE_TYPE) == "group"
            else None
        )

        if item_type == "node":
            blendshape_utilities.rename_blendshape_node(old_name, new_text)

        elif item_type == "group":

            old_path = self._group_item_path(item)
            new_path = (
                f"{parent_group_path}{blendshape_workflow.GROUP_SEPARATOR}{new_text}"
                if parent_group_path else new_text
            )

            blendshape_workflow.rename_target_group(node, old_path, new_path)

        elif item_type == "target":

            if not new_text:
                self.refresh_tree()
                return

            new_alias = (
                f"{parent_group_path}{blendshape_workflow.GROUP_SEPARATOR}{new_text}"
                if parent_group_path else new_text
            )

            blendshape_workflow.rename_target(node, old_name, new_alias)

        elif item_type == "inbetween":

            value = item.data(0, ROLE_VALUE)

            if value != 1.0:
                blendshape_workflow.set_inbetween_name(node, old_name, value, new_text or None)

        self.refresh_tree()

    def on_tree_item_dropped(self, dragged_item, target_item):
        """
        Move a dragged shape or group into another group, out to the root
        (dropped on the node or empty space), or no-op on an invalid drop -
        including dropping a group onto itself or one of its own
        descendants. Only shapes and groups are draggable (see
        _make_*_item, ItemIsDragEnabled stripped elsewhere).
        """

        dragged_type = dragged_item.data(0, ROLE_TYPE)

        if dragged_type not in ("target", "group"):
            return

        node = dragged_item.data(0, ROLE_NODE)

        if target_item is not None and target_item.data(0, ROLE_NODE) != node:
            log.warning("Cannot move a shape to a different blendShape node.")
            return

        destination = self._resolve_drop_destination(target_item)

        if dragged_type == "target":

            self._move_target(node, dragged_item.data(0, ROLE_NAME), destination)

        else:

            group_path = self._group_item_path(dragged_item)

            if destination is not None and (
                destination == group_path
                or destination.startswith(f"{group_path}{blendshape_workflow.GROUP_SEPARATOR}")
            ):
                log.warning("Cannot move a group into itself or one of its own subgroups.")
                return

            self._move_group(node, group_path, destination)

        self.refresh_tree()
