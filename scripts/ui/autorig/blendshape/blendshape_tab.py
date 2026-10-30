from PySide6 import QtWidgets, QtCore

from . import mesh_panel, blendshape_panel
from ..rig import log_panel
from ....core import log

from importlib import reload

reload(mesh_panel)
reload(blendshape_panel)
reload(log_panel)
reload(log)


class BlendshapeTab(QtWidgets.QWidget):

    def __init__(self, parent=None):
        """Initialize the Blendshape tab (mesh panel + blendshape panel + log)."""
        super().__init__(parent)

        self.build_widgets()
        self.build_layout()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the Blendshape tab."""

        self.mesh_panel = mesh_panel.MeshPanel()
        self.blendshape_panel = blendshape_panel.BlendshapePanel()

        self.log_panel = log_panel.LogPanel()
        log.register(self.log_panel.write)

    def build_layout(self):
        """Build the Blendshape tab layout."""

        self.top_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.top_splitter.addWidget(self.mesh_panel)
        self.top_splitter.addWidget(self.blendshape_panel)
        self.top_splitter.setSizes([250, 750])

        self.vertical_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.vertical_splitter.addWidget(self.top_splitter)
        self.vertical_splitter.addWidget(self.log_panel)
        self.vertical_splitter.setSizes([650, 150])

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.vertical_splitter)

        self.mesh_panel.meshSelected.connect(self.blendshape_panel.set_mesh)
        self.blendshape_panel.meshPanelRefreshRequested.connect(self.mesh_panel.refresh)
