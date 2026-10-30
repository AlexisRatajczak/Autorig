# -*- coding: utf-8 -*-
"""Logique UI : fait le lien entre la fenêtre (ui.py), le modèle (model.py)
et Maya (maya_utils.py)."""
from .qt import QtCore, QtWidgets, Qt
from .model import PickerData, ButtonData
from .presets import BUTTON_PRESETS, BORDER_PRESETS, guess_side_color
from .graphics import PickerButtonItem, BackgroundItem
from . import maya_utils as mu


class PickerController(QtCore.QObject):

    def __init__(self, window):
        super(PickerController, self).__init__(window)
        self.win = window
        self.scene = window.scene
        self.view = window.view
        self.data = PickerData()
        self.items = {}            # id -> PickerButtonItem
        self.bg_item = None
        self.edit_mode = False
        self.file_path = None
        self.scene_node = None
        self._last_selected = set()
        self._syncing = False
        self._watcher = mu.SelectionWatcher(self._sync_from_maya)

        self._connect()
        self.load_data(PickerData(name="Nouveau picker"))
        self.refresh_scene_pickers()
        self.refresh_namespaces()
        self._watcher.start()

    # ------------------------------------------------------------------ wiring
    def _connect(self):
        a, w = self.win.actions, self.win
        a["new"].triggered.connect(lambda: self.new_picker())
        a["open"].triggered.connect(lambda: self.open_json())
        a["save"].triggered.connect(lambda: self.save_json())
        a["save_as"].triggered.connect(lambda: self.save_json(save_as=True))
        a["scene_save"].triggered.connect(lambda: self.save_to_scene())
        a["scene_load"].triggered.connect(lambda: self.load_from_scene())
        a["scene_delete"].triggered.connect(lambda: self.delete_from_scene())
        a["edit"].toggled.connect(self.set_edit_mode)
        a["autogen"].triggered.connect(lambda: self.auto_generate())
        a["frame"].triggered.connect(lambda: self.view.frame())

        w.name_edit.textChanged.connect(self._on_name_changed)
        w.namespace_combo.currentTextChanged.connect(self._on_namespace_changed)
        w.ns_refresh_btn.clicked.connect(lambda: self.refresh_namespaces())
        w.scene_refresh_btn.clicked.connect(lambda: self.refresh_scene_pickers())
        w.closed.connect(self.cleanup)

        self.view.selectionFinished.connect(self._on_view_selection_finished)
        self.view.deleteRequested.connect(self.delete_selected)
        self.view.duplicateRequested.connect(self.duplicate_selected)
        self.view.nudgeRequested.connect(self.nudge_selected)
        self.view.contextMenuRequested.connect(self._on_context_menu)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)

        p = w.properties
        p.propertyChanged.connect(self._on_property_changed)
        p.controlsAction.connect(self._on_controls_action)
        p.presetApplied.connect(self.apply_preset)
        p.createWithPreset.connect(lambda name: self.add_button(preset=name))

        b = w.background_panel
        b.importRequested.connect(self.import_background)
        b.clearRequested.connect(self.clear_background)
        b.valueChanged.connect(self._on_background_value)

    def cleanup(self):
        self._watcher.stop()

    # ---------------------------------------------------------------- helpers
    def _selected_items(self):
        return [i for i in self.scene.selectedItems() if isinstance(i, PickerButtonItem)]

    def _resolve(self, name):
        return mu.NamespaceUtils.add(name, self.data.namespace)

    def _controls_of(self, items):
        result, seen = [], set()
        for item in items:
            for ctrl in item.data.controls:
                full = self._resolve(ctrl)
                if full not in seen:
                    seen.add(full)
                    result.append(full)
        return result

    def _update_title(self):
        source = self.file_path or self.scene_node or "non sauvegardé"
        self.win.set_title("{}  [{}]".format(self.data.name, source))

    # --------------------------------------------------------------- building
    def load_data(self, data):
        self.scene.clearSelection()
        for item in list(self.items.values()):
            self.scene.removeItem(item)
        self.items.clear()
        if self.bg_item is not None:
            self.scene.removeItem(self.bg_item)
            self.bg_item = None

        self.data = data
        self._update_background()
        for button in data.buttons:
            self._create_item(button)

        self.win.set_picker_name(data.name)
        self.win.set_namespace(data.namespace)
        self.win.background_panel.set_background(data.background)
        self.win.properties.set_buttons([])
        self._update_title()
        self._sync_from_maya()
        QtCore.QTimer.singleShot(0, self.view.frame)

    def _create_item(self, button):
        item = PickerButtonItem(button)
        item.set_edit_mode(self.edit_mode)
        item.moved.connect(self._on_item_moved)
        self.scene.addItem(item)
        self.items[button.id] = item
        return item

    def _update_background(self):
        background = self.data.background
        if not background.has_image:
            if self.bg_item is not None:
                self.scene.removeItem(self.bg_item)
                self.bg_item = None
            return
        if self.bg_item is None:
            self.bg_item = BackgroundItem()
            self.scene.addItem(self.bg_item)
        if not self.bg_item.set_data(background):
            self.win.show_status("Impossible de lire l'image de fond.")

    # ------------------------------------------------------------------ modes
    def set_edit_mode(self, enabled):
        self.edit_mode = bool(enabled)
        self.scene.clearSelection()
        for item in self.items.values():
            item.set_edit_mode(self.edit_mode)
        self.view.show_grid = self.edit_mode
        PickerButtonItem.snap_size = 0
        self.view.viewport().update()
        self.win.set_edit_mode_ui(self.edit_mode)
        self.win.properties.set_buttons([])
        if not self.edit_mode:
            self._sync_from_maya()

    # ------------------------------------------------- sélection (mode anim)
    def _on_view_selection_finished(self, additive):
        if self.edit_mode:
            return
        selected = self._selected_items()
        current = {i.data.id for i in selected}
        self._syncing = True
        try:
            if additive:
                added = [self.items[i] for i in current - self._last_selected if i in self.items]
                removed = [self.items[i] for i in self._last_selected - current if i in self.items]
                mu.SelectionUtils.select(self._controls_of(removed), "remove")
                mu.SelectionUtils.select(self._controls_of(added), "add")
            else:
                mu.SelectionUtils.select(self._controls_of(selected), "replace")
        finally:
            self._syncing = False
        self._sync_from_maya()

    def _sync_from_maya(self):
        """Surligne les boutons dont tous les contrôles existants sont sélectionnés dans Maya."""
        if self.edit_mode or self._syncing:
            return
        selection = {n.split("|")[-1] for n in mu.SelectionUtils.get_selection()}
        current = set()
        for item in self.items.values():
            controls = [c for c in self._controls_of([item]) if mu.SelectionUtils.exists(c)]
            state = bool(controls) and all(c.split("|")[-1] in selection for c in controls)
            if item.isSelected() != state:
                item.setSelected(state)
            if state:
                current.add(item.data.id)
        self._last_selected = current

    def select_all_controls(self):
        mu.SelectionUtils.select(self._controls_of(list(self.items.values())), "replace")

    # ----------------------------------------------------------- mode édition
    def _on_scene_selection_changed(self):
        if self.edit_mode:
            self.win.properties.set_buttons([i.data for i in self._selected_items()])

    def _on_item_moved(self, button_id):
        if not self.edit_mode:
            return
        selected = self._selected_items()
        if len(selected) == 1 and selected[0].data.id == button_id:
            self.win.properties.update_position(selected[0].data.x, selected[0].data.y)

    def _on_property_changed(self, key, value):
        items = self._selected_items()
        if key in ("x", "y") and len(items) > 1:
            return
        for item in items:
            setattr(item.data, key, value)
            item.sync_from_data()

    def _on_controls_action(self, action):
        items = self._selected_items()
        if not items:
            return
        if action == "select":
            mu.SelectionUtils.select(self._controls_of(items), "replace")
            return
        selection = mu.SelectionUtils.get_selection()
        if action in ("set", "add") and not selection:
            self.win.warn("Sélectionne d'abord des contrôleurs dans Maya.")
            return
        names = [mu.NamespaceUtils.strip(n) for n in selection]
        self._adopt_namespace(selection)
        for item in items:
            if action == "set":
                item.data.controls = list(names)
            elif action == "add":
                item.data.controls += [n for n in names if n not in item.data.controls]
            elif action == "remove":
                item.data.controls = [c for c in item.data.controls if c not in names]
            elif action == "clear":
                item.data.controls = []
            item.sync_from_data()
        self.win.properties.set_buttons([i.data for i in items])

    def _adopt_namespace(self, nodes):
        """Si le picker n'a pas encore de namespace, prend celui de la sélection."""
        if self.data.namespace or not nodes:
            return
        namespace = mu.NamespaceUtils.get_namespace(nodes[0])
        if namespace:
            self.data.namespace = namespace
            self.win.set_namespace(namespace)

    def apply_preset(self, kind, name):
        values = (BUTTON_PRESETS if kind == "button" else BORDER_PRESETS).get(name)
        items = self._selected_items()
        if not values or not items:
            self.win.show_status("Sélectionne au moins un bouton pour appliquer un preset.")
            return
        for item in items:
            item.data.apply(values)
            item.sync_from_data()
        self.win.properties.set_buttons([i.data for i in items])

    def add_button(self, preset=None, scene_pos=None, controls=None, select=True):
        if scene_pos is None:
            scene_pos = self.view.mapToScene(self.view.viewport().rect().center())
        button = ButtonData(x=scene_pos.x(), y=scene_pos.y(), controls=list(controls or []))
        if preset:
            button.apply(BUTTON_PRESETS.get(preset, {}))
        self.data.buttons.append(button)
        item = self._create_item(button)
        if select:
            self.scene.clearSelection()
            item.setSelected(True)
        return item

    def add_buttons_from_selection(self, scene_pos):
        selection = mu.SelectionUtils.get_selection()
        if not selection:
            self.win.warn("Sélectionne des contrôleurs dans Maya.")
            return
        self._adopt_namespace(selection)
        self.scene.clearSelection()
        for index, node in enumerate(selection):
            offset = QtCore.QPointF((index % 10) * 35, (index // 10) * 35)
            item = self.add_button(scene_pos=scene_pos + offset, select=False,
                                   controls=[mu.NamespaceUtils.strip(node)])
            item.data.color = mu.RigAnalyzer.get_color(node) or guess_side_color(node)
            item.data.shape = "circle"
            item.sync_from_data()
            item.setSelected(True)

    def delete_selected(self):
        if not self.edit_mode:
            return
        for item in self._selected_items():
            self.data.remove_button(item.data.id)
            self.items.pop(item.data.id, None)
            self.scene.removeItem(item)
        self.win.properties.set_buttons([])

    def duplicate_selected(self):
        if not self.edit_mode:
            return
        sources = self._selected_items()
        self.scene.clearSelection()
        for source in sources:
            button = source.data.clone()
            button.x += 20
            button.y += 20
            self.data.buttons.append(button)
            self._create_item(button).setSelected(True)

    def nudge_selected(self, dx, dy):
        if self.edit_mode:
            for item in self._selected_items():
                item.moveBy(dx, dy)

    def mirror_selected(self):
        """Duplique en miroir horizontal autour de x = 0 (L <-> R dans les noms)."""
        if not self.edit_mode:
            return
        swaps = (("L_", "R_"), ("_L", "_R"), ("left", "right"), ("Left", "Right"))
        sources = self._selected_items()
        self.scene.clearSelection()
        for source in sources:
            button = source.data.clone()
            button.x = -button.x
            button.rotation = -button.rotation
            controls = []
            for ctrl in button.controls:
                for a, b in swaps:
                    if a in ctrl:
                        ctrl = ctrl.replace(a, b)
                        break
                    if b in ctrl:
                        ctrl = ctrl.replace(b, a)
                        break
                controls.append(ctrl)
            button.controls = controls
            self.data.buttons.append(button)
            self._create_item(button).setSelected(True)

    def _on_context_menu(self, global_pos, scene_pos):
        if not self.edit_mode:
            self.win.exec_context_menu(global_pos, [
                ("Sélectionner tous les contrôles", self.select_all_controls),
                ("Recentrer (F)", self.view.frame),
                None,
                ("Passer en mode édition", lambda: self.win.actions["edit"].setChecked(True)),
            ])
            return
        presets = [(name, lambda n=name: self.add_button(preset=n, scene_pos=scene_pos))
                   for name in BUTTON_PRESETS]
        snap = PickerButtonItem.snap_size
        self.win.exec_context_menu(global_pos, [
            ("Nouveau bouton", lambda: self.add_button(scene_pos=scene_pos)),
            ("Nouveau bouton (preset)", presets),
            ("Un bouton par contrôle sélectionné", lambda: self.add_buttons_from_selection(scene_pos)),
            None,
            ("Dupliquer (Ctrl+D)", self.duplicate_selected),
            ("Miroir gauche/droite", self.mirror_selected),
            ("Supprimer (Suppr)", self.delete_selected),
            None,
            ("Désactiver la grille magnétique" if snap else "Activer la grille magnétique",
             self._toggle_snap),
            ("Recentrer (F)", self.view.frame),
        ])

    def _toggle_snap(self):
        PickerButtonItem.snap_size = 0 if PickerButtonItem.snap_size else self.view.GRID

    # -------------------------------------------------------------- background
    def import_background(self):
        path = self.win.ask_image_path()
        if not path:
            return
        try:
            self.data.background.set_from_file(path)
        except IOError as exc:
            self.win.warn(str(exc))
            return
        self._update_background()
        self.win.background_panel.set_background(self.data.background)
        self.view.frame()

    def clear_background(self):
        self.data.background.image = ""
        self._update_background()

    def _on_background_value(self, key, value):
        setattr(self.data.background, key, value)
        if self.bg_item is not None:
            self.bg_item.set_data(self.data.background)

    # ---------------------------------------------------------- auto-génération
    def auto_generate(self):
        selection = mu.SelectionUtils.get_selection(long=True)
        if not selection:
            self.win.warn("Sélectionne le groupe racine du rig (ou des contrôleurs), "
                          "cadré dans le viewport actif.")
            return
        if self.data.buttons and not self.win.confirm(
                "Auto-générer", "Remplacer le picker courant par un picker auto-généré ?"):
            return

        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            path, _, controls = mu.ViewportCapture.capture_rig(selection)
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.win.warn("Échec de la capture :\n{}".format(exc))
            return
        QtWidgets.QApplication.restoreOverrideCursor()

        root = selection[0]
        data = PickerData(name=mu.NamespaceUtils.strip(root),
                          namespace=mu.NamespaceUtils.get_namespace(root))
        data.background.set_from_file(path)
        for ctrl in controls:
            w = min(max(ctrl["w"], 12.0), 80.0)
            h = min(max(ctrl["h"], 12.0), 80.0)
            ratio = w / h
            data.buttons.append(ButtonData(
                controls=[mu.NamespaceUtils.strip(ctrl["name"])],
                shape="circle" if 0.75 < ratio < 1.33 else "rounded",
                x=ctrl["x"], y=ctrl["y"], width=w, height=h,
                corner_radius=min(w, h) / 2,
                color=ctrl["color"] or guess_side_color(ctrl["name"]),
            ))

        self.file_path = None
        self.scene_node = None
        self.load_data(data)
        self.win.actions["edit"].setChecked(True)
        self.win.show_status("{} boutons générés. Ajuste-les puis sauvegarde.".format(len(controls)))

    # -------------------------------------------------------------- fichiers
    def new_picker(self, confirm=True):
        if confirm and self.data.buttons and not self.win.confirm(
                "Nouveau picker", "Abandonner le picker courant ?"):
            return
        self.file_path = None
        self.scene_node = None
        self.load_data(PickerData(name="Nouveau picker"))

    def open_json(self):
        path = self.win.ask_open_path()
        if not path:
            return
        try:
            data = PickerData.from_dict(mu.JsonStorage.load(path))
        except Exception as exc:
            self.win.warn("Lecture impossible :\n{}".format(exc))
            return
        self.file_path = path
        self.scene_node = None
        self.load_data(data)

    def save_json(self, save_as=False):
        path = self.file_path
        if save_as or not path:
            path = self.win.ask_save_path(self.data.name)
            if not path:
                return
        try:
            mu.JsonStorage.save(path, self.data.to_dict())
        except Exception as exc:
            self.win.warn("Écriture impossible :\n{}".format(exc))
            return
        self.file_path = path
        self._update_title()
        self.win.show_status("Picker enregistré : " + path)

    # ----------------------------------------------------------------- scène
    def refresh_scene_pickers(self):
        self.win.set_scene_pickers(mu.SceneStorage.list_pickers(), current=self.scene_node)

    def refresh_namespaces(self):
        self.win.set_namespaces(mu.NamespaceUtils.list_namespaces(), current=self.data.namespace)

    def save_to_scene(self):
        self.scene_node = mu.SceneStorage.save(self.data.to_dict(), self.data.name, node=self.scene_node)
        self.refresh_scene_pickers()
        self._update_title()
        self.win.show_status("Picker sauvé dans le node " + self.scene_node)

    def load_from_scene(self):
        node = self.win.current_scene_picker()
        if not node:
            self.win.warn("Aucun picker dans la scène (clique sur ↻ pour rafraîchir).")
            return
        try:
            data = PickerData.from_dict(mu.SceneStorage.load(node))
        except Exception as exc:
            self.win.warn(str(exc))
            return
        self.scene_node = node
        self.file_path = None
        self.load_data(data)

    def delete_from_scene(self):
        node = self.win.current_scene_picker()
        if not node or not self.win.confirm("Supprimer", "Supprimer le node '{}' ?".format(node)):
            return
        mu.SceneStorage.delete(node)
        if node == self.scene_node:
            self.scene_node = None
            self._update_title()
        self.refresh_scene_pickers()

    # ------------------------------------------------------------- nom / ns
    def _on_name_changed(self, text):
        self.data.name = text
        self._update_title()

    def _on_namespace_changed(self, text):
        self.data.namespace = text.strip().strip(":")
        self._sync_from_maya()
