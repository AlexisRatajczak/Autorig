from PySide6 import QtWidgets, QtCore

from importlib import reload

from . import guides_panel, settings_panel, import_export_panel

reload(guides_panel)
reload(settings_panel)
reload(import_export_panel)

from .guides_panel import GuidesPanel
from .settings_panel import SettingsPanel
from .import_export_panel import ImportExportPanel


# ==========================================================
# SLIDING PANEL
# ==========================================================

class SlidingPanel(QtWidgets.QFrame):

    PANEL_WIDTH = 320

    def __init__(self, parent=None):
        """Initialize the sliding panel and its pages."""
        super().__init__(parent)

        self.opened = False

        self.setMinimumWidth(0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )

        self.build_widgets()
        self.build_layout()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the sliding panel."""

        self.content = QtWidgets.QWidget()
        self.stack = QtWidgets.QStackedWidget()

        self.opacity_effect = QtWidgets.QGraphicsOpacityEffect(self.content)
        self.content.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.pages = {
            "Settings": SettingsPanel(),
            "Modules": GuidesPanel(),
            "Import/Export": ImportExportPanel(),
        }

    def build_layout(self):
        """Build the sliding panel layout."""

        layout = QtWidgets.QVBoxLayout(self)

        content_layout = QtWidgets.QVBoxLayout(self.content)
        content_layout.addWidget(self.stack)
        layout.addWidget(self.content)

        for widget in self.pages.values():
            self.stack.addWidget(widget)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def set_page(self, name):
        """Set the currently displayed panel page."""
        if name in self.pages:
            self.stack.setCurrentWidget(self.pages[name])

    def expand(self):
        """Mark the sliding panel as opened."""
        self.opened = True

    def collapse(self):
        """Mark the sliding panel as closed."""
        self.opened = False

    def toggle(self):
        """Toggle the sliding panel between opened and closed states."""
        if self.opened:
            self.collapse()
        else:
            self.expand()
