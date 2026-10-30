from PySide6 import QtWidgets, QtCore

import maya.cmds as cmds

from ....core.autorig.modules import registry
from ....core.autorig.modules.base import ui_settings

from importlib import reload
reload(registry)
reload(ui_settings)


# ==========================================================
# GUIDE SETTINGS PANEL (HOST)
# ==========================================================

class GuideSettingsPanel(QtWidgets.QWidget):

    attr_changed = QtCore.Signal(object)

    def __init__(self, node=None, parent=None):
        """
        Initialize the guide settings panel - it doesn't build any guide UI
        itself : for the selected guide, it resolves the module's
        SettingsWidget class (core/modules/<name>/ui_settings.py) from its
        moduleType and embeds it, so each module can fully customize its
        own settings UI by overriding its SettingsWidget.

        Tracks the current widget's class and moduleType (not just the
        widget) because get_settings_widget_class() reloads its module on
        every call, so the class object's identity changes even for an
        unchanged moduleType - comparing by 'is' would rebuild the widget
        on every single selection.
        """
        super().__init__(parent)

        self.node = None

        self._widget = None
        self._widget_class = None
        self._module_type = None

        self.build_widgets()
        self.build_layout()

        if node:
            self.set_node(node)
        else:
            self._show_placeholder()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):

        self.placeholder = QtWidgets.QLabel("No node selected")
        self.placeholder.setAlignment(QtCore.Qt.AlignCenter)
        self.placeholder.setStyleSheet("QLabel { padding: 12px; color: #888; }")

    def build_layout(self):

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.addWidget(self.placeholder)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def _show_placeholder(self):

        self._clear_widget()

        self.placeholder.setVisible(True)

    def _clear_widget(self):

        if self._widget is not None:
            self.main_layout.removeWidget(self._widget)
            self._widget.deleteLater()
            self._widget = None
            self._widget_class = None
            self._module_type = None

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def set_node(self, node):
        """
        Resolve the guide's module SettingsWidget and embed it - if 'node'
        is already the one currently shown, just refreshes it in place
        (no rebuild, to avoid a visual flash in the middle of the attribute
        edit that likely triggered this call) ; any real swap/rebuild
        freezes UI updates for its whole duration, to avoid an intermediate
        repaint (empty widget, then filled).
        """

        if node and node == self.node and self._widget is not None:
            self._widget.refresh()
            return

        self.setUpdatesEnabled(False)

        try:
            self.node = node

            if not node or not cmds.objExists(node):
                self.node = None
                self._show_placeholder()
                return

            module_type = self._resolve_module_type(node)

            if module_type != self._module_type or self._widget is None:

                widget_class = (
                    registry.get_settings_widget_class(module_type)
                    or ui_settings.SettingsWidget
                )

                self._clear_widget()

                self._widget = widget_class(parent=self)
                self._widget_class = widget_class
                self._module_type = module_type
                self._widget.attr_changed.connect(self.attr_changed)

                self.placeholder.setVisible(False)
                self.main_layout.addWidget(self._widget)

            self._widget.set_node(node)
        finally:
            self.setUpdatesEnabled(True)

    def _resolve_module_type(self, node):

        if cmds.objExists(f"{node}.moduleType"):
            try:
                return cmds.getAttr(f"{node}.moduleType", asString=True)
            except Exception:
                pass

        instance = registry.load_guide(node)

        return getattr(instance, "MODULE_NAME", None)

    def refresh(self):
        if self._widget is not None:
            self._widget.refresh()
