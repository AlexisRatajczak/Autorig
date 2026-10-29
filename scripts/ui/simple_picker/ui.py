# -*- coding: utf-8 -*-
"""Interface (widgets uniquement). Aucune logique : tout passe par des signaux
que le PickerController (logic.py) connecte."""
from .qt import QtCore, QtGui, QtWidgets, QAction, Qt, exec_menu
from .graphics import PickerView
from .model import SHAPES, BORDER_STYLES
from .presets import BUTTON_PRESETS, BORDER_PRESETS

ANIM_HINT = ("Anim : clic = sélectionner | Shift = ajouter/basculer | glisser = rectangle | "
             "molette = zoom | clic milieu / Alt+clic = pan | F = recentrer")
EDIT_HINT = ("Édition : glisser = déplacer | clic droit = menu | Suppr = effacer | "
             "Ctrl+D = dupliquer | flèches = décaler (Shift x10) | F = recentrer")


class ColorButton(QtWidgets.QPushButton):
    colorChanged = QtCore.Signal(str)

    def __init__(self, color="#ffffffff", parent=None):
        super(ColorButton, self).__init__(parent)
        self._color = color
        self.setFixedHeight(22)
        self.clicked.connect(self._pick)
        self.set_color(color)

    def color(self):
        return self._color

    def set_color(self, color):
        self._color = color
        c = QtGui.QColor(color)
        self.setStyleSheet("background-color: rgba({},{},{},{}); border: 1px solid #111;".format(
            c.red(), c.green(), c.blue(), c.alpha()))

    def _pick(self):
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self._color), self, "Couleur",
                                                QtWidgets.QColorDialog.ShowAlphaChannel)
        if color.isValid():
            self.set_color(color.name(QtGui.QColor.HexArgb))
            self.colorChanged.emit(self._color)


def _spin(minimum, maximum, step=1.0, decimals=1):
    spin = QtWidgets.QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setKeyboardTracking(False)
    return spin


# --------------------------------------------------------------------------- #
class PropertyPanel(QtWidgets.QWidget):
    propertyChanged = QtCore.Signal(str, object)
    controlsAction = QtCore.Signal(str)        # set | add | remove | clear | select
    presetApplied = QtCore.Signal(str, str)    # "button"/"border", nom
    createWithPreset = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(PropertyPanel, self).__init__(parent)
        self._updating = False
        self._fields = {}
        layout = QtWidgets.QVBoxLayout(self)
        self.info_label = QtWidgets.QLabel()
        layout.addWidget(self.info_label)
        layout.addWidget(self._build_presets())
        self.edit_box = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(self.edit_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self._build_controls())
        box.addWidget(self._build_transform())
        box.addWidget(self._build_style())
        layout.addWidget(self.edit_box)
        layout.addStretch()
        self.set_buttons([])

    # -- construction -----------------------------------------------------------
    def _register(self, key, widget):
        self._fields[key] = widget
        if isinstance(widget, QtWidgets.QLineEdit):
            widget.textChanged.connect(lambda v, k=key: self._emit(k, v))
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.currentTextChanged.connect(lambda v, k=key: self._emit(k, v))
        elif isinstance(widget, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
            widget.valueChanged.connect(lambda v, k=key: self._emit(k, v))
        elif isinstance(widget, ColorButton):
            widget.colorChanged.connect(lambda v, k=key: self._emit(k, v))
        return widget

    def _build_presets(self):
        group = QtWidgets.QGroupBox("Presets")
        grid = QtWidgets.QGridLayout(group)
        self.button_preset = QtWidgets.QComboBox()
        self.button_preset.addItems(list(BUTTON_PRESETS))
        apply_btn = QtWidgets.QPushButton("Appliquer")
        create_btn = QtWidgets.QPushButton("Créer")
        apply_btn.clicked.connect(lambda: self.presetApplied.emit("button", self.button_preset.currentText()))
        create_btn.clicked.connect(lambda: self.createWithPreset.emit(self.button_preset.currentText()))
        self.border_preset = QtWidgets.QComboBox()
        self.border_preset.addItems(list(BORDER_PRESETS))
        border_btn = QtWidgets.QPushButton("Appliquer")
        border_btn.clicked.connect(lambda: self.presetApplied.emit("border", self.border_preset.currentText()))
        grid.addWidget(QtWidgets.QLabel("Bouton"), 0, 0)
        grid.addWidget(self.button_preset, 0, 1)
        grid.addWidget(apply_btn, 0, 2)
        grid.addWidget(create_btn, 0, 3)
        grid.addWidget(QtWidgets.QLabel("Bordure"), 1, 0)
        grid.addWidget(self.border_preset, 1, 1)
        grid.addWidget(border_btn, 1, 2)
        grid.setColumnStretch(1, 1)
        return group

    def _build_controls(self):
        group = QtWidgets.QGroupBox("Contrôles Maya")
        layout = QtWidgets.QVBoxLayout(group)
        form = QtWidgets.QFormLayout()
        form.addRow("Label", self._register("label", QtWidgets.QLineEdit()))
        layout.addLayout(form)
        self.controls_list = QtWidgets.QListWidget()
        self.controls_list.setMaximumHeight(90)
        layout.addWidget(self.controls_list)
        row = QtWidgets.QHBoxLayout()
        for text, action in (("Assigner sél.", "set"), ("Ajouter", "add"), ("Retirer", "remove"),
                             ("Vider", "clear"), ("Sélect.", "select")):
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(lambda _=False, a=action: self.controlsAction.emit(a))
            row.addWidget(btn)
        layout.addLayout(row)
        return group

    def _build_transform(self):
        group = QtWidgets.QGroupBox("Transform")
        form = QtWidgets.QFormLayout(group)
        form.addRow("Forme", self._register("shape", self._combo(SHAPES)))
        form.addRow("X", self._register("x", _spin(-100000, 100000)))
        form.addRow("Y", self._register("y", _spin(-100000, 100000)))
        form.addRow("Largeur", self._register("width", _spin(1, 4000)))
        form.addRow("Hauteur", self._register("height", _spin(1, 4000)))
        rot = self._register("rotation", _spin(-360, 360, 5))
        rot.setWrapping(True)
        form.addRow("Rotation", rot)
        form.addRow("Scale X", self._register("scale_x", _spin(-20, 20, 0.05, 2)))
        form.addRow("Scale Y", self._register("scale_y", _spin(-20, 20, 0.05, 2)))
        return group

    def _build_style(self):
        group = QtWidgets.QGroupBox("Style")
        form = QtWidgets.QFormLayout(group)
        form.addRow("Couleur", self._register("color", ColorButton()))
        form.addRow("Texte", self._register("text_color", ColorButton()))
        form.addRow("Taille texte", self._register("font_size", QtWidgets.QSpinBox()))
        self._fields["font_size"].setRange(4, 72)
        form.addRow("Bordure", self._register("border_color", ColorButton()))
        form.addRow("Épaisseur", self._register("border_width", _spin(0, 30, 0.5)))
        form.addRow("Style bordure", self._register("border_style", self._combo(BORDER_STYLES)))
        form.addRow("Arrondi", self._register("corner_radius", _spin(0, 500)))
        return group

    @staticmethod
    def _combo(items):
        combo = QtWidgets.QComboBox()
        combo.addItems(items)
        return combo

    # -- API -------------------------------------------------------------------
    def _emit(self, key, value):
        if not self._updating:
            self.propertyChanged.emit(key, value)

    def _set_widget(self, widget, value):
        if isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(value)
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentIndex(max(0, widget.findText(value)))
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, ColorButton):
            widget.set_color(value)

    def set_buttons(self, datas):
        count = len(datas)
        self.edit_box.setEnabled(count > 0)
        self.info_label.setText({0: "Aucun bouton sélectionné", 1: "1 bouton sélectionné"}.get(
            count, "{} boutons sélectionnés (édition groupée)".format(count)))
        self.controls_list.clear()
        if not count:
            return
        first = datas[0]
        self._updating = True
        try:
            for key, widget in self._fields.items():
                self._set_widget(widget, getattr(first, key))
            self.controls_list.addItems(first.controls)
        finally:
            self._updating = False

    def update_position(self, x, y):
        self._updating = True
        try:
            self._fields["x"].setValue(x)
            self._fields["y"].setValue(y)
        finally:
            self._updating = False


# --------------------------------------------------------------------------- #
class BackgroundPanel(QtWidgets.QWidget):
    importRequested = QtCore.Signal()
    clearRequested = QtCore.Signal()
    valueChanged = QtCore.Signal(str, float)

    def __init__(self, parent=None):
        super(BackgroundPanel, self).__init__(parent)
        self._updating = False
        layout = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        import_btn = QtWidgets.QPushButton("Importer une image...")
        clear_btn = QtWidgets.QPushButton("Retirer")
        import_btn.clicked.connect(self.importRequested.emit)
        clear_btn.clicked.connect(self.clearRequested.emit)
        row.addWidget(import_btn)
        row.addWidget(clear_btn)
        layout.addLayout(row)

        form = QtWidgets.QFormLayout()
        self.opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.scale = _spin(0.01, 50, 0.05, 2)
        self.pos_x = _spin(-100000, 100000)
        self.pos_y = _spin(-100000, 100000)
        form.addRow("Opacité", self.opacity)
        form.addRow("Échelle", self.scale)
        form.addRow("X", self.pos_x)
        form.addRow("Y", self.pos_y)
        layout.addLayout(form)
        layout.addStretch()

        self.opacity.valueChanged.connect(lambda v: self._emit("opacity", v / 100.0))
        self.scale.valueChanged.connect(lambda v: self._emit("scale", v))
        self.pos_x.valueChanged.connect(lambda v: self._emit("x", v))
        self.pos_y.valueChanged.connect(lambda v: self._emit("y", v))

    def _emit(self, key, value):
        if not self._updating:
            self.valueChanged.emit(key, float(value))

    def set_background(self, background):
        self._updating = True
        try:
            self.opacity.setValue(int(round(background.opacity * 100)))
            self.scale.setValue(background.scale)
            self.pos_x.setValue(background.x)
            self.pos_y.setValue(background.y)
        finally:
            self._updating = False


# --------------------------------------------------------------------------- #
class PickerWindow(QtWidgets.QMainWindow):
    OBJECT_NAME = "SimpleAnimPickerWindow"
    closed = QtCore.Signal()

    def __init__(self, parent=None):
        super(PickerWindow, self).__init__(parent)
        self.setObjectName(self.OBJECT_NAME)
        self.setWindowTitle("Simple Anim Picker")
        self.setWindowFlags(Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1000, 700)

        self.scene = QtWidgets.QGraphicsScene(self)
        self.view = PickerView(self.scene)
        self.properties = PropertyPanel()
        self.background_panel = BackgroundPanel()
        self.actions = {}

        self._build_actions()
        self._build_toolbars()
        self._build_central()
        self.set_edit_mode_ui(False)

    # -- construction -----------------------------------------------------------
    def _build_actions(self):
        specs = [
            ("new", "Nouveau", "Ctrl+N"), ("open", "Ouvrir .json", "Ctrl+O"),
            ("save", "Enregistrer .json", "Ctrl+S"), ("save_as", "Enregistrer sous...", "Ctrl+Shift+S"),
            ("scene_save", "Sauver dans la scène", None), ("scene_load", "Charger", None),
            ("scene_delete", "Supprimer", None), ("edit", "Mode édition", "Ctrl+E"),
            ("autogen", "Auto-générer depuis le rig", None), ("frame", "Recentrer (F)", None),
        ]
        for key, text, shortcut in specs:
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QtGui.QKeySequence(shortcut))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.actions[key] = action
            self.addAction(action)
        self.actions["edit"].setCheckable(True)
        self.actions["autogen"].setToolTip(
            "Sélectionne le groupe racine du rig : capture du viewport actif\n"
            "+ un bouton par contrôleur (nurbsCurve), placé à sa position écran.")

    def _build_toolbars(self):
        main = self.addToolBar("Fichier")
        main.setMovable(False)
        for key in ("new", "open", "save", "save_as"):
            main.addAction(self.actions[key])
        main.addSeparator()
        main.addAction(self.actions["edit"])
        main.addAction(self.actions["autogen"])
        main.addAction(self.actions["frame"])

        self.addToolBarBreak()
        bar = self.addToolBar("Scène")
        bar.setMovable(False)
        bar.addWidget(QtWidgets.QLabel(" Nom : "))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setMaximumWidth(160)
        bar.addWidget(self.name_edit)
        bar.addWidget(QtWidgets.QLabel("  Namespace : "))
        self.namespace_combo = QtWidgets.QComboBox()
        self.namespace_combo.setEditable(True)
        self.namespace_combo.setMinimumWidth(120)
        bar.addWidget(self.namespace_combo)
        self.ns_refresh_btn = QtWidgets.QToolButton()
        self.ns_refresh_btn.setText("↻")
        bar.addWidget(self.ns_refresh_btn)
        bar.addSeparator()
        bar.addWidget(QtWidgets.QLabel(" Pickers de la scène : "))
        self.scene_combo = QtWidgets.QComboBox()
        self.scene_combo.setMinimumWidth(180)
        bar.addWidget(self.scene_combo)
        self.scene_refresh_btn = QtWidgets.QToolButton()
        self.scene_refresh_btn.setText("↻")
        bar.addWidget(self.scene_refresh_btn)
        for key in ("scene_load", "scene_save", "scene_delete"):
            bar.addAction(self.actions[key])

    def _build_central(self):
        self.side_tabs = QtWidgets.QTabWidget()
        for widget, title in ((self.properties, "Bouton"), (self.background_panel, "Fond")):
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            self.side_tabs.addTab(scroll, title)
        self.side_tabs.setMinimumWidth(320)

        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.addWidget(self.view)
        splitter.addWidget(self.side_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        self.setCentralWidget(splitter)

    # -- état UI -----------------------------------------------------------------
    def set_edit_mode_ui(self, enabled):
        self.side_tabs.setVisible(enabled)
        self.actions["edit"].blockSignals(True)
        self.actions["edit"].setChecked(enabled)
        self.actions["edit"].blockSignals(False)
        self.statusBar().showMessage(EDIT_HINT if enabled else ANIM_HINT)

    def set_title(self, text):
        self.setWindowTitle("Simple Anim Picker - " + text)

    def set_picker_name(self, name):
        self.name_edit.blockSignals(True)
        self.name_edit.setText(name)
        self.name_edit.blockSignals(False)

    def set_namespaces(self, namespaces, current=""):
        self.namespace_combo.blockSignals(True)
        self.namespace_combo.clear()
        self.namespace_combo.addItems([""] + list(namespaces))
        self.namespace_combo.setEditText(current)
        self.namespace_combo.blockSignals(False)

    def set_namespace(self, namespace):
        self.namespace_combo.blockSignals(True)
        self.namespace_combo.setEditText(namespace)
        self.namespace_combo.blockSignals(False)

    def set_scene_pickers(self, entries, current=None):
        self.scene_combo.clear()
        for node, name in entries:
            self.scene_combo.addItem("{}  ({})".format(name, node), node)
        if current:
            index = self.scene_combo.findData(current)
            if index >= 0:
                self.scene_combo.setCurrentIndex(index)

    def current_scene_picker(self):
        return self.scene_combo.currentData()

    def show_status(self, text, timeout=4000):
        self.statusBar().showMessage(text, timeout)

    # -- dialogues ---------------------------------------------------------------
    def ask_open_path(self):
        return QtWidgets.QFileDialog.getOpenFileName(self, "Ouvrir un picker", "", "Picker (*.json)")[0]

    def ask_save_path(self, name):
        return QtWidgets.QFileDialog.getSaveFileName(self, "Enregistrer le picker", name + ".json",
                                                     "Picker (*.json)")[0]

    def ask_image_path(self):
        return QtWidgets.QFileDialog.getOpenFileName(self, "Image de fond", "",
                                                     "Images (*.png *.jpg *.jpeg *.bmp *.tif)")[0]

    def confirm(self, title, text):
        answer = QtWidgets.QMessageBox.question(self, title, text)
        return answer == QtWidgets.QMessageBox.Yes

    def warn(self, text):
        QtWidgets.QMessageBox.warning(self, "Anim Picker", text)

    def exec_context_menu(self, global_pos, entries):
        """entries : liste de (label, callable) | (label, [sous-entrées]) | None (séparateur)."""
        menu = QtWidgets.QMenu(self)
        self._fill_menu(menu, entries)
        exec_menu(menu, global_pos)

    def _fill_menu(self, menu, entries):
        for entry in entries:
            if entry is None:
                menu.addSeparator()
                continue
            label, target = entry
            if isinstance(target, list):
                self._fill_menu(menu.addMenu(label), target)
            else:
                action = menu.addAction(label)
                action.triggered.connect(lambda _=False, cb=target: cb())

    def closeEvent(self, event):
        self.closed.emit()
        super(PickerWindow, self).closeEvent(event)
