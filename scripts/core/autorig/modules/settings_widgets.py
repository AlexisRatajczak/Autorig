# ====================================================================================================================
# SETTINGS WIDGETS
# ====================================================================================================================
#
#   Qt widgets, one per attribute type, used by SettingsWidget (modules/base/ui_settings.py) to build a
#   module's settings UI from its attributes.json. Shared interface: 'changed(object)' signal,
#   set_value(value), get_value().
#
#   ATTRIBUTE WIDGETS       StringAttributeWidget, BoolAttributeWidget, IntAttributeWidget, FloatAttributeWidget,
#                           EnumAttributeWidget, VectorAttributeWidget, MessageListAttributeWidget,
#                           MessageAttributeWidget, MatrixAttributeWidget
#                           resolve_accepted_node(node, accept) - node to connect for an 'accept' rule, or None
#   COLLAPSIBLE SECTION     CollapsibleSection - foldout (add_row, add_widget, clear, set_collapsed)
#
# ====================================================================================================================

from PySide6 import QtWidgets, QtCore

import maya.cmds as cmds


# ==========================================================
# ATTRIBUTE WIDGETS
# ==========================================================

class StringAttributeWidget(QtWidgets.QLineEdit):

    changed = QtCore.Signal(object)

    def __init__(self, value=None, parent=None):
        super().__init__(parent)

        self.set_value(value)
        self.editingFinished.connect(self._emit_changed)

    def _emit_changed(self):
        self.changed.emit(self.get_value())

    def set_value(self, value):
        self.setText("" if value is None else str(value))

    def get_value(self):
        return self.text()


class BoolAttributeWidget(QtWidgets.QCheckBox):

    changed = QtCore.Signal(object)

    def __init__(self, value=None, parent=None):
        super().__init__(parent)

        self.set_value(value)
        self.stateChanged.connect(lambda _: self.changed.emit(self.get_value()))

    def set_value(self, value):
        self.setChecked(bool(value))

    def get_value(self):
        return self.isChecked()


class IntAttributeWidget(QtWidgets.QSpinBox):

    changed = QtCore.Signal(object)

    def __init__(self, value=None, parent=None):
        super().__init__(parent)

        self.setRange(-2147483648, 2147483647)
        self.set_value(value)
        self.valueChanged.connect(lambda _: self.changed.emit(self.get_value()))

    def set_value(self, value):
        self.setValue(int(value or 0))

    def get_value(self):
        return self.value()


class FloatAttributeWidget(QtWidgets.QDoubleSpinBox):

    changed = QtCore.Signal(object)

    def __init__(self, value=None, parent=None):
        super().__init__(parent)

        self.setRange(-999999.0, 999999.0)
        self.setDecimals(4)
        self.set_value(value)
        self.valueChanged.connect(lambda _: self.changed.emit(self.get_value()))

    def set_value(self, value):
        self.setValue(float(value or 0.0))

    def get_value(self):
        return self.value()


class EnumAttributeWidget(QtWidgets.QComboBox):

    changed = QtCore.Signal(object)

    def __init__(self, enum_names=None, value=None, parent=None):
        super().__init__(parent)

        for index, name in enumerate(enum_names or []):
            self.addItem(name, index)

        self.set_value(value)
        self.currentIndexChanged.connect(lambda _: self.changed.emit(self.get_value()))

    def set_value(self, value):
        self.setCurrentIndex(int(value or 0))

    def get_value(self):
        return self.currentIndex()


class VectorAttributeWidget(QtWidgets.QWidget):

    changed = QtCore.Signal(object)

    def __init__(self, value=None, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.spin_x = QtWidgets.QDoubleSpinBox()
        self.spin_y = QtWidgets.QDoubleSpinBox()
        self.spin_z = QtWidgets.QDoubleSpinBox()

        for spin in (self.spin_x, self.spin_y, self.spin_z):
            spin.setRange(-999999, 999999)
            spin.setDecimals(0)
            spin.setFixedWidth(60)
            layout.addWidget(spin)

        self.set_value(value)

        for spin in (self.spin_x, self.spin_y, self.spin_z):
            spin.valueChanged.connect(lambda _: self.changed.emit(self.get_value()))

    def set_value(self, value):
        x, y, z = self._normalize(value)

        for spin, component in zip((self.spin_x, self.spin_y, self.spin_z), (x, y, z)):
            spin.blockSignals(True)
            spin.setValue(component)
            spin.blockSignals(False)

    def get_value(self):
        return (self.spin_x.value(), self.spin_y.value(), self.spin_z.value())

    @staticmethod
    def _normalize(value):
        if isinstance(value, list) and value:
            value = value[0]

        if isinstance(value, (tuple, list)) and len(value) == 3:
            return tuple(value)

        return (0.0, 0.0, 0.0)


def resolve_accepted_node(node, accept):

    """
    Node to connect for 'node' given 'accept' (schema key), or None with a warning:

    - None       : any node, as is.
    - "guide"    : a guide (name containing '_GUIDE').
    - shape type : a transform with a shape of that type (ex: "nurbsSurface"),
                   or the shape itself (its transform is returned).
    """

    if not accept:
        return node

    short_name = node.split("|")[-1]

    if accept == "guide":

        if "_GUIDE" not in short_name:
            cmds.warning(f"'{node}' is not a guide.")
            return None

        return node

    if cmds.nodeType(node) == accept:
        parents = cmds.listRelatives(node, parent=True) or []
        return parents[0] if parents else node

    if cmds.listRelatives(node, shapes=True, noIntermediate=True, type=accept):
        return node

    cmds.warning(f"'{node}' is not a {accept}.")

    return None


class MessageListAttributeWidget(QtWidgets.QWidget):
    """
    Multi message attribute (ex: spaceSwitchTargets): list of connected nodes,
    with buttons to add the Maya selection and remove the selected entries.

    accept : accepted nodes (see resolve_accepted_node), None = any.
    """

    changed = QtCore.Signal(object)

    def __init__(self, value=None, parent=None, accept=None):
        super().__init__(parent)

        self.accept = accept

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setFixedHeight(90)
        layout.addWidget(self.list_widget)

        buttons_layout = QtWidgets.QHBoxLayout()

        self.add_button = QtWidgets.QPushButton("+ Add Item")
        self.remove_button = QtWidgets.QPushButton("- Remove")

        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.remove_button)

        layout.addLayout(buttons_layout)

        self.set_value(value)

        self.add_button.clicked.connect(self.add_selected)
        self.remove_button.clicked.connect(self.remove_selected)

    def set_value(self, value):
        self.list_widget.clear()

        items = value if isinstance(value, list) else ([value] if value else [])

        for item in items:
            if item:
                self.list_widget.addItem(str(item))

    def get_value(self):
        return [
            self.list_widget.item(index).text()
            for index in range(self.list_widget.count())
        ]

    def add_selected(self):
        """Add the currently selected Maya object(s) to the list."""

        selection = cmds.ls(selection=True) or []

        if not selection:
            cmds.warning("Nothing selected.")
            return

        existing = self.get_value()

        for node in selection:

            node = resolve_accepted_node(node, self.accept)

            if node and node not in existing:
                self.list_widget.addItem(node)
                existing.append(node)

        self.changed.emit(self.get_value())

    def remove_selected(self):
        """Remove the selected list entries."""

        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

        self.changed.emit(self.get_value())


class MessageAttributeWidget(QtWidgets.QWidget):
    """
    Single message attribute (ex: attributesHost): one connected node, with
    buttons to set it from the Maya selection and to clear it.

    accept : accepted nodes (see resolve_accepted_node), "guide" by default.
    """

    changed = QtCore.Signal(object)

    def __init__(self, value=None, parent=None, accept="guide"):
        super().__init__(parent)

        self.accept = accept

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.line_edit = QtWidgets.QLineEdit()
        self.line_edit.setReadOnly(True)
        self.line_edit.setPlaceholderText("Default")
        layout.addWidget(self.line_edit)

        self.set_button = QtWidgets.QPushButton("Set")
        self.clear_button = QtWidgets.QPushButton("Clear")

        layout.addWidget(self.set_button)
        layout.addWidget(self.clear_button)

        self.set_value(value)

        self.set_button.clicked.connect(self.set_selected)
        self.clear_button.clicked.connect(self.clear)

    def set_value(self, value):
        if isinstance(value, list):
            value = value[0] if value else None

        self.line_edit.setText(str(value) if value else "")

    def get_value(self):
        return self.line_edit.text() or None

    def set_selected(self):
        """Set the value from the single selected node (see accept)."""

        selection = cmds.ls(selection=True) or []

        if len(selection) != 1:
            cmds.warning(f"Select exactly one {self.accept or 'node'}.")
            return

        node = resolve_accepted_node(selection[0], self.accept)

        if not node:
            return

        self.line_edit.setText(node)
        self.changed.emit(self.get_value())

    def clear(self):
        self.line_edit.setText("")
        self.changed.emit(None)


class MatrixAttributeWidget(QtWidgets.QWidget):

    changed = QtCore.Signal(object)

    def __init__(self, value=None, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.spins = []

        for row in range(4):
            row_spins = []

            for column in range(4):
                spin = QtWidgets.QDoubleSpinBox()
                spin.setRange(-999999.0, 999999.0)
                spin.setDecimals(3)
                spin.setFixedWidth(45)
                layout.addWidget(spin, row, column)
                row_spins.append(spin)

            self.spins.append(row_spins)

        self.set_value(value)

        for row_spins in self.spins:
            for spin in row_spins:
                spin.valueChanged.connect(lambda _: self.changed.emit(self.get_value()))

    def set_value(self, value):
        flat = self._normalize(value)

        for row, row_spins in enumerate(self.spins):
            for column, spin in enumerate(row_spins):
                spin.blockSignals(True)
                spin.setValue(flat[row * 4 + column])
                spin.blockSignals(False)

    def get_value(self):
        flat = []

        for row_spins in self.spins:
            for spin in row_spins:
                flat.append(spin.value())

        return flat

    @staticmethod
    def _normalize(value):
        if isinstance(value, list) and value and isinstance(value[0], (list, tuple)):
            value = value[0]

        if isinstance(value, (list, tuple)) and len(value) == 16:
            return list(value)

        identity = [0.0] * 16

        for i in range(4):
            identity[i * 4 + i] = 1.0

        return identity


# ==========================================================
# COLLAPSIBLE SECTION
# ==========================================================

class CollapsibleSection(QtWidgets.QWidget):
    """
    Foldout for settings: a clickable header (arrow + title) that folds a body.
    Rows are added with add_row(label, widget) / add_widget(widget), or
    directly in body_layout (a QFormLayout).

    Example:

        section = self.add_section("Orientation", collapsed=True)
        section.add_row("Aim Vector", my_widget)
    """

    toggled = QtCore.Signal(bool)

    def __init__(self, title="", collapsed=False, parent=None):
        super().__init__(parent)

        # Header
        self.header = QtWidgets.QToolButton()
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(not collapsed)
        self.header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(
            QtCore.Qt.RightArrow if collapsed else QtCore.Qt.DownArrow
        )
        self.header.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.header.setCursor(QtCore.Qt.PointingHandCursor)
        self.header.clicked.connect(self._on_toggle)

        # Body
        self.body = QtWidgets.QWidget()
        self.body_layout = QtWidgets.QFormLayout(self.body)
        self.body_layout.setContentsMargins(14, 6, 4, 8)
        self.body_layout.setSpacing(8)
        self.body.setVisible(not collapsed)

        # Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.body)

    # --------------------------------------------------

    def _on_toggle(self, checked):
        self.body.setVisible(checked)
        self.header.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )
        self.toggled.emit(checked)

    def set_collapsed(self, collapsed):
        self.header.setChecked(not collapsed)
        self._on_toggle(not collapsed)

    def is_collapsed(self):
        return not self.header.isChecked()

    def set_title(self, title):
        self.header.setText(title)

    # --------------------------------------------------

    def add_row(self, label, widget=None):
        """Add a row (label + widget), or a full width widget."""
        if widget is None:
            self.body_layout.addRow(label)
        else:
            self.body_layout.addRow(label, widget)

    def add_widget(self, widget):
        """Add a full width widget (no label)."""
        self.body_layout.addRow(widget)

    def clear(self):
        """Empty the section body."""
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()
