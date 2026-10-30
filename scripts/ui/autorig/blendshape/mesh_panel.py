from PySide6 import QtWidgets, QtCore, QtGui

import maya.cmds as cmds

from ....core.utilities import blendshape_utilities
from ....core.blendshape import blendshape_workflow

from importlib import reload

reload(blendshape_utilities)
reload(blendshape_workflow)


class MeshPanel(QtWidgets.QFrame):

    meshSelected = QtCore.Signal(str)

    BLENDSHAPE_COLOR = "#5fd68a"
    PLAIN_COLOR = "#c8c8c8"

    def __init__(self, parent=None):
        """Initialize the mesh panel and build its interface."""
        super().__init__(parent)

        self.setObjectName("MeshPanel")
        self.build_widgets()
        self.build_layout()
        self.refresh()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the mesh panel."""

        self.title = QtWidgets.QLabel("MESHES")

        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.setFixedHeight(22)

        self.search_field = QtWidgets.QLineEdit()
        self.search_field.setPlaceholderText("Search meshes...")

        self.mesh_list = QtWidgets.QListWidget()

    def build_layout(self):
        """Build the mesh panel layout."""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.refresh_button)

        layout.addLayout(header)
        layout.addWidget(self.search_field)
        layout.addWidget(self.mesh_list)

        self.search_field.textChanged.connect(self.filter_meshes)
        self.refresh_button.clicked.connect(self.refresh)
        self.mesh_list.itemClicked.connect(self.on_item_clicked)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def refresh(self):
        """Re-scan the scene's meshes and rebuild the list."""

        self.mesh_list.clear()

        meshes = self.list_meshes()

        meshes.sort(
            key=lambda mesh: (not mesh["has_blendshape"], mesh["short_name"].lower())
        )

        for mesh in meshes:

            has_blendshape = mesh["has_blendshape"]
            label = f"◆ {mesh['short_name']}" if has_blendshape else mesh["short_name"]

            item = QtWidgets.QListWidgetItem(label)

            item.setData(QtCore.Qt.UserRole, mesh["full_path"])

            color = self.BLENDSHAPE_COLOR if has_blendshape else self.PLAIN_COLOR
            item.setForeground(QtGui.QBrush(QtGui.QColor(color)))

            if has_blendshape:
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.mesh_list.addItem(item)

    def filter_meshes(self, text):
        """Filter visible meshes according to the search text (matched on the short name)."""

        text = text.strip().lower()

        for index in range(self.mesh_list.count()):

            item = self.mesh_list.item(index)
            full_path = item.data(QtCore.Qt.UserRole) or ""
            short_name = full_path.split("|")[-1]

            item.setHidden(text not in short_name.lower())

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def list_meshes(self):
        """
        Return [{'full_path', 'short_name', 'has_blendshape'}, ...] for every
        "real" mesh transform in the scene - target/shape duplicates (see
        blendshape_workflow.TARGET_MESH_SUFFIX) are excluded, they're not
        meshes to build a rig on.
        """

        transforms = set()

        for shape in cmds.ls(type="mesh", noIntermediate=True, long=True) or []:

            parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []

            if parents and not blendshape_workflow.is_target_mesh(parents[0]):
                transforms.add(parents[0])

        meshes = []

        for transform in transforms:

            has_blendshape = blendshape_utilities.has_blendshape(transform)

            meshes.append({
                "full_path": transform,
                "short_name": transform.split("|")[-1],
                "has_blendshape": has_blendshape,
            })

        return meshes

    def on_item_clicked(self, item):
        """Select the clicked mesh in the Maya scene (via its full path)."""

        full_path = item.data(QtCore.Qt.UserRole)

        if full_path and cmds.objExists(full_path):
            cmds.select(full_path, replace=True)
            self.meshSelected.emit(full_path)
