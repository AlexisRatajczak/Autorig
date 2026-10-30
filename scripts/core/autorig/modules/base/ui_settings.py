# ====================================================================================================================
# BASE - UI SETTINGS
# ====================================================================================================================
#
#   SettingsWidget - whole settings panel of a module (label, scroll area, attribute form, "+ Add Guide"),
#   built from the module schema (attributes.json next to the concrete ui_settings.py). Each module has its own
#   SettingsWidget(BaseSettingsWidget); override build_ui / build_attributes / create_attribute_widget /
#   create_widget / post_build for a custom UI. GuideSettingsPanel (scripts/ui/autorig) only hosts it.
#
#       SCHEMA          schema_dir, load_schema
#       UI              build_ui, set_style, post_build
#       NODE            set_node, clear_attributes, add_section, build_sections, update_add_guide_button
#       ATTRIBUTES      build_attributes, is_visible, is_message_list, is_message, create_attribute_widget,
#                       _section_collapsed_default, create_widget
#       WRITE BACK      set_attribute, _rebuild_attributes, set_message_list_attribute, set_message_attribute,
#                       refresh
#       GUIDES          add_guide
#       HELPERS         get_nice_name
#
# ====================================================================================================================

import inspect
from pathlib import Path
from importlib import reload

from PySide6 import QtWidgets, QtCore

import maya.cmds as cmds

from .. import registry
from .. import ui_schema
from .. import settings_widgets
from .... import log

reload(ui_schema)
reload(settings_widgets)
reload(registry)


MODULE_DIR = Path(__file__).resolve().parent


class SettingsWidget(QtWidgets.QWidget):

    # Emitted when an attribute changed, with the current data node (may be renamed).
    attr_changed = QtCore.Signal(object)

    def __init__(self, node=None, parent=None):
        super().__init__(parent)

        self.node = node
        self.node_cls = None
        self.widgets = {}
        self.sections = {}
        self._updating = False

        # Merged UI schema, loaded once for the concrete class.
        self._schema = self.load_schema()
        self._has_conditional = any(
            "visible_when" in spec
            for spec in self._schema.get("attributes", {}).values()
        )

        self.build_ui()
        self.set_style()
        self.post_build()

        if self.node:
            self.set_node(self.node)
        else:
            self.update_add_guide_button()

    # ------------------------------------------------------
    # SCHEMA
    # ------------------------------------------------------

    def schema_dir(self):
        """Module folder of the CONCRETE class (its ui_settings.py and attributes.json)."""
        try:
            return Path(inspect.getfile(type(self))).resolve().parent
        except TypeError:
            return MODULE_DIR

    def load_schema(self):
        """Merged UI schema of the module ({} without attributes.json)."""
        return ui_schema.load_ui_settings(self.schema_dir()) or {}

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_ui(self):
        """Build the full settings layout. Override for a custom layout."""

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(8)

        # Node name
        self.node_label = QtWidgets.QLabel("No node selected")
        self.node_label.setStyleSheet("QLabel { font-weight: bold; padding: 6px; }")
        self.main_layout.addWidget(self.node_label)

        # Scroll area
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.main_layout.addWidget(self.scroll)

        # Container + form
        self.container = QtWidgets.QWidget()
        self.attributes_layout = QtWidgets.QFormLayout(self.container)
        self.attributes_layout.setContentsMargins(4, 4, 4, 4)
        self.attributes_layout.setSpacing(8)
        self.scroll.setWidget(self.container)

        # Add Guide button (outside the scroll area)
        self.add_guide_button = QtWidgets.QPushButton("+ Add Guide")
        self.main_layout.addWidget(self.add_guide_button)
        self.add_guide_button.clicked.connect(self.add_guide)

    def set_style(self):
        """Apply the visual style. Override to restyle."""
        self.setStyleSheet("""
            QToolButton {
                font-weight: bold;
                padding: 6px;
                text-align: left;
            }

            QFrame {
                border: 1px solid #444;
                border-radius: 5px;
            }

            QPushButton {
                padding: 6px;
            }

            QLineEdit,
            QSpinBox,
            QDoubleSpinBox,
            QComboBox {
                padding: 4px;
            }

            QCheckBox {
                padding: 4px;
            }
        """)

    def post_build(self):
        """Hook called after build_ui() / set_style(). Empty by default."""
        pass

    # ------------------------------------------------------
    # NODE
    # ------------------------------------------------------

    def set_node(self, node):
        """Set the current data node and rebuild its attribute widgets."""

        if node and node == self.node and self.widgets:
            # Same node already shown (ex: called back after an edit): refresh the
            # values only, never destroy the widgets still handling that edit.
            self.refresh()
            return

        # Updates off during the rebuild: one final repaint, no flash.
        self.setUpdatesEnabled(False)

        try:
            self.node = node
            self.node_cls = None

            self.clear_attributes()

            if not node:
                self.node_label.setText("No node selected")
                self.update_add_guide_button()
                return

            if not cmds.objExists(node):
                self.node_label.setText("Node does not exist")
                self.node = None
                self.update_add_guide_button()
                return

            self.node_label.setText(node)
            self.node_cls = registry.load_guide(node)

            self.build_attributes()
            self.update_add_guide_button()
        finally:
            self.setUpdatesEnabled(True)

    def clear_attributes(self):
        """Remove every attribute widget (and section) from the form."""

        self.widgets.clear()
        self.sections.clear()

        while self.attributes_layout.count():
            item = self.attributes_layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()

    def add_section(self, title, key=None, collapsed=False, parent=None, label=None):
        """
        Add a foldout (CollapsibleSection) to the form, or to 'parent' (another
        section, to nest). Returns it; fill it with add_row / add_widget.

        key   : self.sections key (default: title).
        label : header text (default: title).

            general = self.add_section("General")
            general.add_row("Name", name_widget)

            orient = self.add_section("Orientation", collapsed=True)
            orient.add_row("Aim Vector", aim_widget)
        """

        section = settings_widgets.CollapsibleSection(label or title, collapsed=collapsed)

        if parent is not None:
            parent.add_widget(section)
        else:
            self.attributes_layout.addRow(section)

        self.sections[key or title] = section

        return section

    def build_sections(self):
        """
        Create the foldouts of schema['sections'] in 'order', with their
        'collapsed' state; create_attribute_widget fills them. Override for
        a custom section layout.
        """

        for title, spec in ui_schema.ordered_sections(self._schema):

            if title in self.sections:
                continue

            self.add_section(
                title,
                collapsed=bool(spec.get("collapsed")),
                label=spec.get("label"),
            )

    def update_add_guide_button(self):
        """Enable/disable the Add Guide button from the module's guide limit."""

        if not self.node_cls:
            self.add_guide_button.setEnabled(False)
            return

        reached_max = self.node_cls.has_reached_max_guides()
        self.add_guide_button.setEnabled(not reached_max)

        if reached_max:
            self.add_guide_button.setToolTip(
                f"Maximum guides reached ({self.node_cls.MAX_GUIDES})."
            )
        else:
            self.add_guide_button.setToolTip("")

    # ------------------------------------------------------
    # ATTRIBUTES (schema-driven)
    # ------------------------------------------------------

    def build_attributes(self):
        """
        Build one widget per schema-declared attribute (strict mode : an
        attribute not in attributes.json is never shown). Override to add
        custom rows / sections.
        """

        if not self.node:
            return

        # Foldouts first (declared order), then the attributes.
        self.build_sections()

        for attr, spec in ui_schema.ordered_attributes(self._schema):

            if not self.is_visible(spec):
                continue

            self.create_attribute_widget(attr, spec)

    def is_visible(self, spec):

        """Evaluate the optional 'visible_when': one condition dict, or a list (all must be true)."""

        condition = spec.get("visible_when")

        if not condition or not self.node:
            return True

        if isinstance(condition, (list, tuple)):
            return all(self.is_visible({"visible_when": item}) for item in condition)

        attr = condition.get("attr")

        if not attr or not cmds.objExists(f"{self.node}.{attr}"):
            return True

        try:
            current = cmds.getAttr(f"{self.node}.{attr}")
        except Exception:
            return True

        if "equals" in condition:
            return current == condition["equals"]

        if "in" in condition:
            return current in condition["in"]

        if "min" in condition or "max" in condition:
            try:
                current = float(current)
            except (TypeError, ValueError):
                return True

            if "min" in condition and current < condition["min"]:
                return False

            if "max" in condition and current > condition["max"]:
                return False

            return True

        return bool(current)

    def is_message_list(self, attr):
        """True if the attribute is declared as 'message_list' in the schema."""
        spec = self._schema.get("attributes", {}).get(attr, {})
        return spec.get("widget") == "message_list"

    def is_message(self, attr):
        """True if the attribute is declared as 'message' (single) in the schema."""
        spec = self._schema.get("attributes", {}).get(attr, {})
        return spec.get("widget") == "message"

    def create_attribute_widget(self, attr, spec):
        """Create + add one row for a schema-declared attribute."""

        plug = f"{self.node}.{attr}"

        # The attribute must exist on the node (a schema can declare an
        # attribute that a given subclass module does not add).
        if not cmds.objExists(plug):
            return

        widget_type = spec.get("widget")

        if not widget_type:
            return

        if widget_type == "message_list":
            value = cmds.listConnections(plug, source=True, destination=False) or []

            widget = settings_widgets.MessageListAttributeWidget(value, accept=spec.get("accept"))
            widget.changed.connect(
                lambda value, a=attr: self.set_message_list_attribute(a, value)
            )

        elif widget_type == "message":
            value = cmds.listConnections(plug, source=True, destination=False) or []

            widget = settings_widgets.MessageAttributeWidget(value, accept=spec.get("accept", "guide"))
            widget.changed.connect(
                lambda value, a=attr: self.set_message_attribute(a, value)
            )

        else:

            try:
                value = cmds.getAttr(f"{self.node}.{attr}")
            except Exception:
                value = None

            widget = self.create_widget(attr, widget_type, value, spec)

            if widget is None:
                return

        label = spec.get("label") or self.get_nice_name(attr)

        if spec.get("tooltip"):
            widget.setToolTip(spec["tooltip"])

        locked = bool(spec.get("readonly"))

        if not locked:
            try:
                locked = cmds.getAttr(f"{self.node}.{attr}", lock=True)
            except Exception:
                locked = False

        widget.setEnabled(not locked)

        self.widgets[attr] = widget

        # In its "section" foldout (created on the fly), else in the form.
        section_title = spec.get("section")

        if section_title:
            section = self.sections.get(section_title) or self.add_section(
                section_title,
                collapsed=self._section_collapsed_default(section_title),
            )
            section.add_row(label, widget)
        else:
            self.attributes_layout.addRow(label, widget)

    def _section_collapsed_default(self, section_title):
        """A section starts closed if 'sections' says so, or one of its attributes has 'section_collapsed'."""
        section_spec = self._schema.get("sections", {}).get(section_title, {})

        if section_spec.get("collapsed"):
            return True

        return any(
            spec.get("section") == section_title and spec.get("section_collapsed")
            for spec in self._schema.get("attributes", {}).values()
        )

    def create_widget(self, attr, widget_type, value, spec=None):
        """Create an attribute widget from a schema 'widget' type + options."""

        spec = spec or {}

        if widget_type == "string":
            widget = settings_widgets.StringAttributeWidget(value)

        elif widget_type == "bool":
            widget = settings_widgets.BoolAttributeWidget(value)

        elif widget_type == "int":
            widget = settings_widgets.IntAttributeWidget(value)

            if "min" in spec or "max" in spec:
                widget.setRange(
                    int(spec.get("min", -2147483648)),
                    int(spec.get("max", 2147483647))
                )

            if "step" in spec:
                widget.setSingleStep(int(spec["step"]))

        elif widget_type == "float":
            widget = settings_widgets.FloatAttributeWidget(value)

            if "decimals" in spec:
                widget.setDecimals(int(spec["decimals"]))

            if "min" in spec or "max" in spec:
                widget.setRange(
                    float(spec.get("min", -999999.0)),
                    float(spec.get("max", 999999.0))
                )

            if "step" in spec:
                widget.setSingleStep(float(spec["step"]))

        elif widget_type == "enum":
            enum_raw = cmds.attributeQuery(attr, node=self.node, listEnum=True) or [""]
            enum_values = spec.get("enum") or [
                name.split("=")[0]
                for name in enum_raw[0].split(":")
                if name
            ]
            widget = settings_widgets.EnumAttributeWidget(enum_values, value)

        elif widget_type == "vector":
            widget = settings_widgets.VectorAttributeWidget(value)

        elif widget_type == "matrix":
            widget = settings_widgets.MatrixAttributeWidget(value)

        else:
            return None

        widget.changed.connect(
            lambda value, a=attr: self.set_attribute(a, value)
        )

        return widget

    # ------------------------------------------------------
    # WRITE BACK
    # ------------------------------------------------------

    def set_attribute(self, attr, value):
        """Set an attribute through Guides.set_attribute (handles renaming)."""

        if self._updating or not self.node:
            return

        if not self.node_cls:
            self.node_cls = registry.load_guide(self.node)

        if not self.node_cls:
            return

        try:
            self.node_cls.set_attribute(attr, value)
        except Exception as error:
            log.error(f"Could not set {self.node}.{attr}: {error}")
            return

        # The node may have been renamed
        self.node = self.node_cls.data_node
        self.node_label.setText(self.node)

        # A 'visible_when' attribute may depend on this one: rebuild to
        # re-evaluate visibilities. Deferred: we are still inside the edited
        # widget's signal, destroying it now flashes the panel.
        if self._has_conditional and not self._updating:
            QtCore.QTimer.singleShot(0, lambda node=self.node: self._rebuild_attributes(node))

        self.attr_changed.emit(self.node)

    def _rebuild_attributes(self, expected_node):
        """Rebuild the attribute widgets (visible_when). See set_attribute()."""

        if self._updating or self.node != expected_node:
            return

        self._updating = True

        try:
            self.clear_attributes()
            self.build_attributes()
        finally:
            self._updating = False

    def set_message_list_attribute(self, attr, targets):
        """
        Reconnect a multi message attribute (ex: spaceSwitchTargets) from the
        widget list. Does NOT emit attr_changed: nothing is renamed, no rebuild.
        """

        if self._updating or not self.node:
            return

        plug = f"{self.node}.{attr}"

        if not cmds.objExists(plug):
            return

        for index in cmds.getAttr(plug, multiIndices=True) or []:

            element_plug = f"{plug}[{index}]"

            sources = cmds.listConnections(
                element_plug, source=True, destination=False, plugs=True
            ) or []

            for source in sources:
                cmds.disconnectAttr(source, element_plug)

        for index, target in enumerate(targets):

            if cmds.objExists(target) and cmds.objExists(f"{target}.message"):
                cmds.connectAttr(f"{target}.message", f"{plug}[{index}]", force=True)
                log.info(f"Connected '{target}' to {plug}[{index}]")
            else:
                log.error(f"Could not connect '{target}' to {plug}[{index}].")

    def set_message_attribute(self, attr, target):
        """Reconnect a single message attribute (ex: attributesHost) to 'target' (None clears it). No attr_changed."""

        if self._updating or not self.node:
            return

        plug = f"{self.node}.{attr}"

        if not cmds.objExists(plug):
            return

        cmds.setAttr(plug, lock=False)

        for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
            cmds.disconnectAttr(source, plug)

        if not target:
            log.info(f"Cleared {plug}")
            return

        if cmds.objExists(target) and cmds.objExists(f"{target}.message"):
            cmds.connectAttr(f"{target}.message", plug, force=True)
            log.info(f"Connected '{target}' to {plug}")
        else:
            log.error(f"Could not connect '{target}' to {plug}.")

    def refresh(self):
        """Refresh existing widgets from the current node values."""

        if not self.node:
            return

        if not cmds.objExists(self.node):
            self.set_node(None)
            return

        self._updating = True

        try:
            for attr, widget in self.widgets.items():

                plug = f"{self.node}.{attr}"

                if not cmds.objExists(plug):
                    continue

                if self.is_message_list(attr) or self.is_message(attr):
                    value = cmds.listConnections(plug, source=True, destination=False) or []
                else:
                    try:
                        value = cmds.getAttr(f"{self.node}.{attr}")
                    except Exception:
                        continue

                widget.set_value(value)

        finally:
            self._updating = False

    # ------------------------------------------------------
    # GUIDES
    # ------------------------------------------------------

    def add_guide(self):
        """Add a guide to the current module (delegates to Guides.add_guide)."""

        if not self.node or not cmds.objExists(self.node):
            log.warning("No guide module selected.")
            return

        self.node_cls = registry.load_guide(self.node)

        if not self.node_cls:
            log.warning("No guide module selected.")
            return

        new_guide = self.node_cls.add_guide()

        if new_guide:
            cmds.select(new_guide, replace=True)

        self.update_add_guide_button()

    # ------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------

    def get_nice_name(self, attr):
        """Fallback display name for an attribute (DCC nice name, else attr)."""
        try:
            nice_name = cmds.attributeQuery(attr, node=self.node, niceName=True)
            if nice_name:
                return nice_name
        except Exception:
            pass

        return attr
