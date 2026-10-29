# -*- coding: utf-8 -*-
"""Utilitaires Maya : tout ce qui touche à maya.cmds / OpenMaya vit ici.

Ni l'UI ni la logique UI n'importent maya directement : elles passent
par ces classes.
"""
import json
import os
import re
import tempfile
from contextlib import contextmanager

from maya import cmds
import maya.OpenMayaUI as omui1
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui

from .qt import QtWidgets, wrapInstance


def maya_main_window():
    ptr = omui1.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


@contextmanager
def undo_chunk(name="animPicker"):
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def _hex_color(rgb, alpha=255):
    r, g, b = [max(0, min(255, int(round(c * 255)))) for c in rgb[:3]]
    return "#{:02x}{:02x}{:02x}{:02x}".format(alpha, r, g, b)


# --------------------------------------------------------------------------- #
class NamespaceUtils(object):

    @staticmethod
    def short_name(node):
        return node.split("|")[-1]

    @classmethod
    def get_namespace(cls, node):
        return cls.short_name(node).rpartition(":")[0]

    @classmethod
    def strip(cls, node):
        return cls.short_name(node).rpartition(":")[2]

    @staticmethod
    def add(name, namespace):
        namespace = (namespace or "").strip(":")
        return "{}:{}".format(namespace, name) if namespace else name

    @staticmethod
    def list_namespaces():
        try:
            spaces = cmds.namespaceInfo(":", listOnlyNamespaces=True, recurse=True) or []
        except RuntimeError:
            return []
        return sorted(ns for ns in spaces if ns not in ("UI", "shared"))


# --------------------------------------------------------------------------- #
class SelectionUtils(object):

    @staticmethod
    def get_selection(long=False):
        return cmds.ls(selection=True, long=long) or []

    @staticmethod
    def existing(nodes):
        """Filtre les noms qui existent (ls ignore silencieusement les autres)."""
        return cmds.ls(list(nodes)) or [] if nodes else []

    @classmethod
    def select(cls, nodes, mode="replace"):
        """mode : replace | add | remove | toggle"""
        nodes = cls.existing(nodes)
        if mode == "replace":
            if nodes:
                cmds.select(nodes, replace=True)
            else:
                cmds.select(clear=True)
        elif nodes:
            flag = {"add": "add", "remove": "deselect", "toggle": "toggle"}[mode]
            cmds.select(nodes, **{flag: True})

    @staticmethod
    def exists(node):
        return cmds.objExists(node)


class SelectionWatcher(object):
    """Callback OpenMaya sur le changement de sélection."""

    def __init__(self, callback):
        self._callback = callback
        self._id = None

    def start(self):
        if self._id is None:
            self._id = om.MEventMessage.addEventCallback("SelectionChanged", self._on_event)

    def stop(self):
        if self._id is not None:
            try:
                om.MMessage.removeCallback(self._id)
            except RuntimeError:
                pass
            self._id = None

    def _on_event(self, *_):
        try:
            self._callback()
        except Exception as exc:  # ne jamais casser Maya depuis un callback
            om.MGlobal.displayWarning("AnimPicker : {}".format(exc))


# --------------------------------------------------------------------------- #
class RigAnalyzer(object):
    """Trouve les contrôleurs (transforms portant des nurbsCurve) d'un rig."""

    @staticmethod
    def curve_shapes(transform):
        shapes = cmds.listRelatives(transform, shapes=True, type="nurbsCurve",
                                    fullPath=True, noIntermediate=True) or []
        return shapes

    @classmethod
    def find_controls(cls, roots):
        controls, seen = [], set()
        for root in roots:
            shapes = cmds.listRelatives(root, allDescendents=True, type="nurbsCurve",
                                        fullPath=True, noIntermediate=True) or []
            if cmds.nodeType(root) == "nurbsCurve":
                shapes.append(cmds.ls(root, long=True)[0])
            for shape in shapes:
                parent = (cmds.listRelatives(shape, parent=True, fullPath=True) or [None])[0]
                if parent and parent not in seen:
                    seen.add(parent)
                    controls.append(parent)
        # ordre hiérarchie -> ordre de création conservé (listRelatives renvoie en ordre inverse)
        controls.reverse()
        return controls

    @classmethod
    def get_color(cls, transform):
        """Couleur d'override du contrôle (shape d'abord, puis transform)."""
        for node in cls.curve_shapes(transform) + [transform]:
            if not cmds.attributeQuery("overrideEnabled", node=node, exists=True):
                continue
            if not cmds.getAttr(node + ".overrideEnabled"):
                continue
            if cmds.attributeQuery("overrideRGBColors", node=node, exists=True) and \
                    cmds.getAttr(node + ".overrideRGBColors"):
                return _hex_color(cmds.getAttr(node + ".overrideColorRGB")[0])
            index = cmds.getAttr(node + ".overrideColor")
            if index > 0:
                return _hex_color(cmds.colorIndex(index, query=True))
        return None


# --------------------------------------------------------------------------- #
class ViewportCapture(object):
    """Capture du viewport actif + projection des contrôleurs en pixels."""

    EDITOR_FLAGS = ("nurbsCurves", "grid", "hud", "manipulators", "selectionHiliteDisplay")

    @staticmethod
    def get_model_panel():
        try:
            editor = cmds.playblast(activeEditor=True)
            panel = editor.split("|")[-1]
            if cmds.getPanel(typeOf=panel) == "modelPanel":
                return panel
        except RuntimeError:
            pass
        for panel in cmds.getPanel(visiblePanels=True) or []:
            if cmds.getPanel(typeOf=panel) == "modelPanel":
                return panel
        raise RuntimeError("Aucun viewport (modelPanel) visible.")

    @staticmethod
    def _project(view, point, port_h, sx, sy):
        res = view.worldToView(om.MPoint(point[0], point[1], point[2]))
        # Viewport : origine en bas à gauche -> image : origine en haut à gauche
        return res[0] * sx, (port_h - res[1]) * sy

    @classmethod
    def capture_rig(cls, roots, frame=True, hide_curves=True, fit_factor=0.85):
        """Retourne (chemin_png, (largeur, hauteur), [infos contrôleurs])."""
        panel = cls.get_model_panel()
        controls = RigAnalyzer.find_controls(roots)
        if not controls:
            raise RuntimeError("Aucun contrôleur (nurbsCurve) trouvé sous la sélection.")

        camera = cmds.modelPanel(panel, query=True, camera=True)
        previous_sel = cmds.ls(selection=True, long=True) or []
        state = {flag: cmds.modelEditor(panel, query=True, **{flag: True}) for flag in cls.EDITOR_FLAGS}
        path = os.path.join(tempfile.gettempdir(), "animPicker_capture.png")
        results = []
        try:
            if frame:
                cmds.select(roots, replace=True)
                cmds.viewFit(camera, fitFactor=fit_factor)
            cmds.select(clear=True)

            edits = {flag: False for flag in cls.EDITOR_FLAGS}
            if not hide_curves:
                edits.pop("nurbsCurves")
            cmds.modelEditor(panel, edit=True, **edits)

            view = omui.M3dView.getM3dViewFromModelPanel(panel)
            view.refresh(False, True)
            image = om.MImage()
            view.readColorBuffer(image, True)
            image.writeToFile(path, "png")

            img_w, img_h = image.getSize()
            port_w, port_h = view.portWidth(), view.portHeight()
            sx, sy = img_w / float(port_w), img_h / float(port_h)  # gestion HiDPI

            for ctrl in controls:
                shapes = RigAnalyzer.curve_shapes(ctrl)
                if not shapes:
                    continue
                bb = cmds.exactWorldBoundingBox(shapes)
                corners = [(x, y, z) for x in (bb[0], bb[3]) for y in (bb[1], bb[4]) for z in (bb[2], bb[5])]
                pts = [cls._project(view, c, port_h, sx, sy) for c in corners]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                center = cls._project(view, ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2),
                                      port_h, sx, sy)
                results.append({
                    "name": ctrl,
                    "x": center[0], "y": center[1],
                    "w": max(xs) - min(xs), "h": max(ys) - min(ys),
                    "color": RigAnalyzer.get_color(ctrl),
                })
        finally:
            cmds.modelEditor(panel, edit=True, **state)
            if previous_sel:
                cmds.select(previous_sel, replace=True)
            else:
                cmds.select(clear=True)
        return path, (img_w, img_h), results


# --------------------------------------------------------------------------- #
class SceneStorage(object):
    """Stockage du picker dans un node network de la scène Maya."""

    TAG_ATTR = "animPickerNode"
    NAME_ATTR = "pickerName"
    DATA_ATTR = "pickerData"

    @staticmethod
    def _safe(name):
        safe = re.sub(r"[^A-Za-z0-9_]", "_", name or "") or "picker"
        return "_" + safe if safe[0].isdigit() else safe

    @classmethod
    def list_pickers(cls):
        result = []
        for node in cmds.ls(type="network") or []:
            if cmds.attributeQuery(cls.TAG_ATTR, node=node, exists=True):
                name = cmds.getAttr("{}.{}".format(node, cls.NAME_ATTR)) or node
                result.append((node, name))
        return result

    @classmethod
    def save(cls, data_dict, name, node=None):
        payload = json.dumps(data_dict)
        with undo_chunk("Save anim picker"):
            if not node or not cmds.objExists(node):
                node = cmds.createNode("network", name=cls._safe(name) + "_animPicker_NET", skipSelect=True)
                cmds.addAttr(node, longName=cls.TAG_ATTR, attributeType="bool", defaultValue=True)
                cmds.addAttr(node, longName=cls.NAME_ATTR, dataType="string")
                cmds.addAttr(node, longName=cls.DATA_ATTR, dataType="string")
            cmds.setAttr("{}.{}".format(node, cls.NAME_ATTR), name, type="string")
            cmds.setAttr("{}.{}".format(node, cls.DATA_ATTR), payload, type="string")
        return node

    @classmethod
    def load(cls, node):
        if not cmds.objExists(node):
            raise RuntimeError("Le node '{}' n'existe plus.".format(node))
        return json.loads(cmds.getAttr("{}.{}".format(node, cls.DATA_ATTR)) or "{}")

    @staticmethod
    def delete(node):
        if cmds.objExists(node):
            cmds.delete(node)


class JsonStorage(object):

    @staticmethod
    def save(path, data_dict):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data_dict, handle, indent=2, ensure_ascii=False)

    @staticmethod
    def load(path):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
