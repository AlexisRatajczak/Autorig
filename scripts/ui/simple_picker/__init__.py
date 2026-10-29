# -*- coding: utf-8 -*-
"""Simple Anim Picker pour Maya 2026.

    import simple_picker
    simple_picker.show()

Architecture :
    model.py       -> données (ButtonData, PickerData) - pur Python
    presets.py     -> presets de boutons / bordures (charges depuis config/presets.json)
    maya_utils.py  -> utilitaires Maya (sélection, capture, network, json)
    graphics.py    -> items et vue QGraphics (UI)
    ui.py          -> fenêtre et panneaux (UI)
    logic.py       -> PickerController (logique UI)
"""
from .qt import QtWidgets

__version__ = "1.0.0"
_instance = None


def show():
    global _instance
    from .ui import PickerWindow
    from .logic import PickerController
    from .maya_utils import maya_main_window

    # ferme une éventuelle instance précédente
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == PickerWindow.OBJECT_NAME:
            widget.close()

    window = PickerWindow(parent=maya_main_window())
    window.controller = PickerController(window)  # garde une référence
    window.show()
    _instance = window
    return window


def reload_and_show():
    """Pratique en développement : recharge tous les modules puis relance."""
    import importlib
    import sys
    for short in ("qt", "model", "presets", "maya_utils", "graphics", "ui", "logic"):
        module = sys.modules.get("{}.{}".format(__name__, short))
        if module:
            importlib.reload(module)
    return show()
