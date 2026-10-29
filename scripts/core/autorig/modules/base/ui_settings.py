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


# ==========================================================
# BASE MODULE - UI SETTINGS WIDGET
# ==========================================================
#
# SettingsWidget : widget qui contient TOUT le layout du panneau de
# settings d'un module (label, zone scroll, form d'attributs, bouton
# "+ Add Guide") et le construit à partir du schéma du module
# (attributes.json, résolu automatiquement à côté du ui_settings.py
# concret).
#
# Chaque module a son propre ui_settings.py avec une classe
# SettingsWidget(BaseSettingsWidget). Par défaut elle ne surcharge rien
# (UI générée depuis le schéma). Pour une UI custom, surcharger :
#
#   - build_ui()            : layout complet
#   - build_attributes()    : lignes / sections d'attributs
#   - create_attribute_widget(attr, spec) / create_widget(...)
#   - post_build()          : ajouts après la construction standard
#
# GuideSettingsPanel (scripts/ui/autorig) est juste l'hôte : il résout
# la bonne classe SettingsWidget selon le moduleType du guide
# sélectionné, l'instancie et l'embarque.
#

MODULE_DIR = Path(__file__).resolve().parent


class SettingsWidget(QtWidgets.QWidget):

    # Émis quand un attribut a changé. Argument : le data node courant
    # (son nom, qui peut avoir changé suite à un rename).
    attr_changed = QtCore.Signal(object)

    def __init__(self, node=None, parent=None):
        super().__init__(parent)

        self.node = node
        self.node_cls = None
        self.widgets = {}
        self.sections = {}
        self._updating = False

        # Schéma UI (attributes.json fusionné), chargé une fois pour la
        # classe concrète, et dérivés.
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
        """
        Dossier du module de la classe CONCRÈTE (là où vit son
        ui_settings.py et son attributes.json). Permet à une sous-classe
        de charger son propre schéma sans rien redéclarer.
        """
        try:
            return Path(inspect.getfile(type(self))).resolve().parent
        except TypeError:
            return MODULE_DIR

    def load_schema(self):
        """Schéma UI fusionné du module (ou {} si pas de attributes.json)."""
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
        """Hook appelé après build_ui()/set_style(). Vide par défaut."""
        pass

    # ------------------------------------------------------
    # NODE
    # ------------------------------------------------------

    def set_node(self, node):
        """Set the current data node and rebuild its attribute widgets."""

        if node and node == self.node and self.widgets:
            # Même node déjà affiché (ex: ré-appelé en ricochet après une
            # simple édition d'attribut) : rien de structurel n'a changé,
            # un refresh des valeurs suffit - ne pas détruire/recréer les
            # widgets d'attribut pendant qu'ils traitent encore l'édition
            # qui a déclenché ce ricochet.
            self.refresh()
            return

        # Détruire (clear_attributes) puis recréer (build_attributes) tous
        # les widgets d'attribut repeint la zone en 2 temps (vide, puis
        # remplie) : sous updates activés, ça peut se voir comme un flash.
        # setUpdatesEnabled(False) fige l'affichage le temps de l'opération
        # complète, un seul repaint final une fois tout reconstruit.
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
        Crée un dépliant (CollapsibleSection) pour ranger des settings et
        l'ajoute au panneau (dans le form, ou dans 'parent' si fourni :
        une autre section, pour imbriquer).

        - key   : identifiant de récupération (self.sections[key], défaut = title).
        - label : texte du header (défaut = title).

        Retourne la section. On y range ensuite des lignes via
        section.add_row(label, widget) / section.add_widget(widget).

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
        Pré-crée les dépliants déclarés dans schema['sections'], dans
        l'ordre ('order'), avec leur état 'collapsed'. Les attributs
        portant "section": "<clé>" y sont ensuite rangés par
        create_attribute_widget. Override pour un layout de sections
        custom.
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

        # Dépliants d'abord (ordre déclaré), puis les attributs qui s'y
        # rangent via leur clé "section".
        self.build_sections()

        for attr, spec in ui_schema.ordered_attributes(self._schema):

            if not self.is_visible(spec):
                continue

            self.create_attribute_widget(attr, spec)

    def is_visible(self, spec):

        """
        Evaluate an attribute's optional 'visible_when' condition : un
        dict (une condition), ou une liste de dicts (toutes doivent être
        vraies).
        """

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

        # Rangement : si le schéma déclare "section" pour cet attribut, on
        # le pose dans le dépliant correspondant (créé à la volée), sinon
        # directement dans le form.
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
        """
        Une section est fermée par défaut si le bloc 'sections' le déclare,
        ou si un de ses attributs porte 'section_collapsed'.
        """
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

        # A 'visible_when' attribute may depend on the one we just changed :
        # rebuild to re-evaluate visibilities (schema stays cached).
        #
        # Différé (QTimer.singleShot(0, ...)) plutôt qu'immédiat : on est
        # encore dans le signal 'changed' du widget qu'on vient d'éditer,
        # et clear_attributes() le détruit (deleteLater) ; le détruire de
        # façon synchrone pendant qu'il traite encore son propre signal
        # provoque un flash visuel (mini-fenêtre) le temps que Qt/Maya
        # recomposent l'affichage. On laisse l'event loop terminer le
        # traitement courant avant de reconstruire.
        if self._has_conditional and not self._updating:
            QtCore.QTimer.singleShot(0, lambda node=self.node: self._rebuild_attributes(node))

        self.attr_changed.emit(self.node)

    def _rebuild_attributes(self, expected_node):
        """Reconstruit les widgets d'attribut (visible_when). Voir set_attribute()."""

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
        Reconnect a multi message attribute (ex: spaceSwitchTargets) from
        the widget's list. N'ÉMET PAS attr_changed : ajouter / retirer une
        cible ne renomme rien et ne doit pas provoquer une reconstruction
        du panneau (le widget reflète déjà l'état édité).
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
        """
        Reconnecte un attribut message simple (ex: attributesHost) sur
        'target' (ou le vide si None). Comme set_message_list_attribute,
        n'émet pas attr_changed.
        """

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
