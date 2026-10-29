# -*- coding: utf-8 -*-
"""Couche de compatibilité Qt (PySide6 pour Maya 2025+, PySide2 en secours)."""
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance, isValid
    QAction = QtGui.QAction
except ImportError:  # Maya <= 2024
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance, isValid
    QAction = QtWidgets.QAction

Qt = QtCore.Qt


def exec_menu(menu, pos):
    """QMenu.exec() / exec_() selon la version de PySide."""
    run = getattr(menu, "exec", None) or getattr(menu, "exec_")
    return run(pos)


__all__ = ["QtCore", "QtGui", "QtWidgets", "QAction", "Qt", "wrapInstance", "isValid", "exec_menu"]
