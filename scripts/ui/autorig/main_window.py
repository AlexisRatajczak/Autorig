import maya.cmds as cmds
import maya.OpenMayaUI as omui

from PySide6 import QtWidgets, QtCore
from shiboken6 import wrapInstance

from .rig import rig_tab
from .blendshape import blendshape_tab
from .skin import skin_tab
from . import theme

from importlib import reload

reload(rig_tab)
reload(blendshape_tab)
reload(skin_tab)
reload(theme)


# ==========================================================
# MAIN WINDOW
# ==========================================================

class MainWindow(QtWidgets.QWidget):

    WINDOW_NAME = "AutoRigTool"
    WINDOW_TITLE = "Auto Rig Tool"
    WORKSPACE_CONTROL = WINDOW_NAME + "WorkspaceControl"

    _instance = None

    def __init__(self, parent=None):
        """Build the Auto Rig Tool UI (tabs)."""
        super().__init__(parent)

        self.setObjectName(self.WINDOW_NAME)
        self.setWindowTitle(self.WINDOW_TITLE)

        self.build_widgets()
        self.build_layout()
        self.style()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create the tab widget and its tabs."""

        self.rig_tab = rig_tab.RigTab()
        self.blendshape_tab = blendshape_tab.BlendshapeTab()
        self.skin_tab = skin_tab.SkinTab()

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.rig_tab, "Rig")
        self.tabs.addTab(self.blendshape_tab, "Blendshape")
        self.tabs.addTab(self.skin_tab, "Skin")

    def build_layout(self):
        """Lay out the tab widget."""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    def style(self):
        """
        Apply the main window's global stylesheet (see theme.py).

        WA_StyledBackground is required for a "bare" QWidget (unlike QFrame
        or other natively-styled widgets) to actually paint its background
        via the stylesheet (#AutoRigTool in theme.STYLESHEET) instead of
        Qt/Maya's default gray.
        """

        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        self.setStyleSheet(theme.STYLESHEET)

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def save_settings(self):
        """Save the Rig tab's settings."""

        try:
            self.rig_tab.save_settings()
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    @classmethod
    def _clear_instance(cls):
        """Detruit l'instance Qt precedente si elle existe encore."""

        if cls._instance is None:
            return

        try:
            cls._instance.save_settings()
            cls._instance.setParent(None)
            cls._instance.deleteLater()
        except Exception:
            pass

        cls._instance = None

    @classmethod
    def _build_into(cls, parent_ptr):
        """Instancie l'UI et l'ajoute au widget parent (pointeur Qt)."""

        cls._clear_instance()

        cls._instance = cls()

        parent = wrapInstance(int(parent_ptr), QtWidgets.QWidget)

        layout = parent.layout()

        if layout is None:
            layout = QtWidgets.QVBoxLayout(parent)
            layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(cls._instance)

        return cls._instance

    @classmethod
    def restore(cls):
        """
        Reconstruit l'UI dans le workspaceControl courant.
        Appele par Maya via le `uiScript` (creation + restauration).
        """

        return cls._build_into(omui.MQtUtil.getCurrentParent())

    @classmethod
    def show_window(cls):
        """
        Cree (ou recree) l'unique fenetre dockable - repart toujours d'un
        workspaceControl propre (supprime l'existant s'il y en a un).

        Le `uiScript` fourni ici est execute par Maya a la creation (son
        timing variant selon la version de Maya, le filet de securite
        ci-dessous construit l'UI nous-memes si ce n'est pas deja fait)
        puis a chaque restauration (redemarrage, changement de workspace).
        """

        if cmds.workspaceControl(cls.WORKSPACE_CONTROL, query=True, exists=True):
            cmds.deleteUI(cls.WORKSPACE_CONTROL)

        cls._clear_instance()

        ui_script = (
            f"import {cls.__module__}; "
            f"{cls.__module__}.{cls.__name__}.restore()"
        )

        cmds.workspaceControl(
            cls.WORKSPACE_CONTROL,
            label=cls.WINDOW_TITLE,
            retain=False,
            floating=True,
            initialWidth=1400,
            initialHeight=800,
            uiScript=ui_script,
        )

        if cls._instance is None:
            control_ptr = omui.MQtUtil.findControl(cls.WORKSPACE_CONTROL)

            if control_ptr:
                cls._build_into(control_ptr)

        cmds.workspaceControl(cls.WORKSPACE_CONTROL, edit=True, restore=True)

        return cls._instance
