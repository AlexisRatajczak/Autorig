# -*- coding: utf-8 -*-
"""Éléments graphiques du picker (QGraphicsView / items).

Ne contient aucune logique métier : les items lisent leur ButtonData et
la vue émet des signaux que le contrôleur interprète.
"""
import math

from .qt import QtCore, QtGui, QtWidgets, Qt

GItem = QtWidgets.QGraphicsItem


def qcolor(value, fallback="#ff808080"):
    color = QtGui.QColor(value or fallback)
    return color if color.isValid() else QtGui.QColor(fallback)


class ShapeFactory(object):
    """Construit le QPainterPath d'une forme, centré sur (0, 0)."""

    @staticmethod
    def _poly(points):
        path = QtGui.QPainterPath()
        path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))
        path.closeSubpath()
        return path

    @classmethod
    def build(cls, shape, w, h, radius=0.0):
        w, h = max(w, 1.0), max(h, 1.0)
        rect = QtCore.QRectF(-w / 2, -h / 2, w, h)
        path = QtGui.QPainterPath()
        if shape == "rect":
            path.addRect(rect)
        elif shape == "ellipse":
            path.addEllipse(rect)
        elif shape == "circle":
            d = min(w, h)
            path.addEllipse(QtCore.QRectF(-d / 2, -d / 2, d, d))
        elif shape == "diamond":
            path = cls._poly([(0, -h / 2), (w / 2, 0), (0, h / 2), (-w / 2, 0)])
        elif shape == "triangle":
            path = cls._poly([(0, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)])
        elif shape == "hexagon":
            path = cls._poly([(-w / 2, 0), (-w / 4, -h / 2), (w / 4, -h / 2),
                              (w / 2, 0), (w / 4, h / 2), (-w / 4, h / 2)])
        elif shape == "star":
            pts = []
            for i in range(10):
                ratio = 1.0 if i % 2 == 0 else 0.45
                angle = math.radians(-90 + i * 36)
                pts.append((math.cos(angle) * w / 2 * ratio, math.sin(angle) * h / 2 * ratio))
            path = cls._poly(pts)
        else:  # rounded
            r = min(radius, w / 2, h / 2)
            path.addRoundedRect(rect, r, r)
        return path


# --------------------------------------------------------------------------- #
class PickerButtonItem(QtWidgets.QGraphicsObject):
    moved = QtCore.Signal(str)
    snap_size = 0  # > 0 : magnétisme sur grille en mode édition

    def __init__(self, data, parent=None):
        super(PickerButtonItem, self).__init__(parent)
        self.data = data
        self._edit_mode = False
        self._hovered = False
        self._path = QtGui.QPainterPath()
        self.setAcceptHoverEvents(True)
        self.setFlag(GItem.ItemIsSelectable, True)
        self.setFlag(GItem.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.PointingHandCursor)
        self.sync_from_data()

    # -- état ---------------------------------------------------------------
    def set_edit_mode(self, enabled):
        self._edit_mode = enabled
        self.setFlag(GItem.ItemIsMovable, enabled)
        self.setCursor(Qt.SizeAllCursor if enabled else Qt.PointingHandCursor)
        self.update()

    def sync_from_data(self):
        d = self.data
        self.prepareGeometryChange()
        self._path = ShapeFactory.build(d.shape, d.width, d.height, d.corner_radius)
        self.setPos(d.x, d.y)
        self.setRotation(d.rotation)
        sx = d.scale_x if abs(d.scale_x) > 1e-3 else 1e-3
        sy = d.scale_y if abs(d.scale_y) > 1e-3 else 1e-3
        self.setTransform(QtGui.QTransform.fromScale(sx, sy))
        self.setToolTip("\n".join(d.controls) if d.controls else "(aucun contrôle)")
        self.update()

    # -- géométrie ------------------------------------------------------------
    def boundingRect(self):
        m = max(self.data.border_width, 2.0) + 4.0
        return self._path.boundingRect().adjusted(-m, -m, m, m)

    def shape(self):
        return self._path

    def itemChange(self, change, value):
        if change == GItem.ItemPositionChange and self._edit_mode and self.snap_size > 0:
            s = float(self.snap_size)
            return QtCore.QPointF(round(value.x() / s) * s, round(value.y() / s) * s)
        if change == GItem.ItemPositionHasChanged:
            pos = self.pos()
            self.data.x, self.data.y = pos.x(), pos.y()
            self.moved.emit(self.data.id)
        return super(PickerButtonItem, self).itemChange(change, value)

    # -- dessin ---------------------------------------------------------------
    def _border_pen(self):
        d = self.data
        if d.border_style == "none" or d.border_width <= 0:
            return QtGui.QPen(Qt.NoPen)
        pen = QtGui.QPen(qcolor(d.border_color), d.border_width)
        pen.setStyle({"dash": Qt.DashLine, "dot": Qt.DotLine}.get(d.border_style, Qt.SolidLine))
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def paint(self, painter, option, widget=None):
        d = self.data
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        selected = self.isSelected()

        fill = qcolor(d.color)
        if selected and not self._edit_mode:
            fill = fill.lighter(165)
        elif self._hovered:
            fill = fill.lighter(125)
        painter.setBrush(fill)
        painter.setPen(self._border_pen())
        painter.drawPath(self._path)

        if selected:
            pen = QtGui.QPen(QtGui.QColor("#ffa500") if self._edit_mode else QtGui.QColor("#ffffff"), 2)
            pen.setCosmetic(True)
            painter.setBrush(Qt.NoBrush)
            if self._edit_mode:
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.drawRect(self._path.boundingRect().adjusted(-3, -3, 3, 3))
            else:
                painter.setPen(pen)
                painter.drawPath(self._path)

        if d.label:
            font = painter.font()
            font.setPixelSize(max(4, int(d.font_size)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(qcolor(d.text_color))
            painter.drawText(self._path.boundingRect(), Qt.AlignCenter, d.label)

        if self._edit_mode and not d.controls:  # repère : bouton sans contrôle assigné
            r = self._path.boundingRect()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QtGui.QColor("#ff3030"))
            painter.drawEllipse(QtCore.QPointF(r.right(), r.top()), 3, 3)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super(PickerButtonItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super(PickerButtonItem, self).hoverLeaveEvent(event)


# --------------------------------------------------------------------------- #
class BackgroundItem(QtWidgets.QGraphicsPixmapItem):

    def __init__(self):
        super(BackgroundItem, self).__init__()
        self._cached = None
        self.setZValue(-1000)
        self.setTransformationMode(Qt.SmoothTransformation)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setFlag(GItem.ItemIsSelectable, False)

    def set_data(self, background):
        if background.image != self._cached:
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(QtCore.QByteArray(background.image_bytes()))
            self.setPixmap(pixmap)
            self._cached = background.image
        self.setPos(background.x, background.y)
        self.setScale(background.scale)
        self.setOpacity(background.opacity)
        return not self.pixmap().isNull()


# --------------------------------------------------------------------------- #
class PickerView(QtWidgets.QGraphicsView):
    """Vue navigable : molette = zoom, clic milieu / Alt+clic gauche = pan, F = recentrer."""

    selectionFinished = QtCore.Signal(bool)          # additive ?
    deleteRequested = QtCore.Signal()
    duplicateRequested = QtCore.Signal()
    nudgeRequested = QtCore.Signal(float, float)
    contextMenuRequested = QtCore.Signal(object, object)  # QPoint global, QPointF scène

    MIN_ZOOM, MAX_ZOOM = 0.05, 30.0
    GRID = 20

    def __init__(self, scene, parent=None):
        super(PickerView, self).__init__(scene, parent)
        self.show_grid = False
        self._panning = False
        self._pan_last = QtCore.QPoint()
        self._additive = False

        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSceneRect(-50000, -50000, 100000, 100000)  # navigation libre
        self.setBackgroundBrush(QtGui.QColor(42, 42, 42))
        self.setFocusPolicy(Qt.StrongFocus)
        self.centerOn(0, 0)

    # -- helpers ----------------------------------------------------------------
    @staticmethod
    def _pos(event):
        return event.position().toPoint() if hasattr(event, "position") else event.pos()

    @staticmethod
    def _remap(event):
        """Shift (convention Maya) -> Ctrl (convention Qt) pour ajouter/basculer."""
        if not (event.modifiers() & Qt.ShiftModifier):
            return event
        mods = Qt.ControlModifier
        if hasattr(event, "position"):
            return QtGui.QMouseEvent(event.type(), event.position(), event.globalPosition(),
                                     event.button(), event.buttons(), mods)
        return QtGui.QMouseEvent(event.type(), event.localPos(), event.windowPos(), event.screenPos(),
                                 event.button(), event.buttons(), mods)

    def zoom(self):
        return self.transform().m11()

    def frame(self):
        items = [i for i in self.scene().items() if i.isVisible()]
        if not items:
            self.resetTransform()
            self.centerOn(0, 0)
            return
        rect = QtCore.QRectF()
        for item in items:
            rect = rect.united(item.sceneBoundingRect())
        margin = max(rect.width(), rect.height()) * 0.08 + 10
        rect.adjust(-margin, -margin, margin, margin)
        self.fitInView(rect, Qt.KeepAspectRatio)
        z = self.zoom()
        if z > self.MAX_ZOOM:
            self.scale(self.MAX_ZOOM / z, self.MAX_ZOOM / z)

    # -- événements -------------------------------------------------------------
    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if self.MIN_ZOOM < self.zoom() * factor < self.MAX_ZOOM:
            self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or \
                (event.button() == Qt.LeftButton and event.modifiers() & Qt.AltModifier):
            self._panning = True
            self._pan_last = self._pos(event)
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self._additive = bool(event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier))
        super(PickerView, self).mousePressEvent(self._remap(event))

    def mouseMoveEvent(self, event):
        if self._panning:
            pos = self._pos(event)
            delta = pos - self._pan_last
            self._pan_last = pos
            hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
            hbar.setValue(hbar.value() - delta.x())
            vbar.setValue(vbar.value() - delta.y())
            event.accept()
            return
        super(PickerView, self).mouseMoveEvent(self._remap(event))

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super(PickerView, self).mouseReleaseEvent(self._remap(event))
        if event.button() == Qt.LeftButton:
            self.selectionFinished.emit(self._additive)

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers()
        if key in (Qt.Key_F, Qt.Key_A) and not (mods & Qt.ControlModifier):
            self.frame()
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.deleteRequested.emit()
        elif key == Qt.Key_D and mods & Qt.ControlModifier:
            self.duplicateRequested.emit()
        elif key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 10.0 if mods & Qt.ShiftModifier else 1.0
            dx = {Qt.Key_Left: -step, Qt.Key_Right: step}.get(key, 0.0)
            dy = {Qt.Key_Up: -step, Qt.Key_Down: step}.get(key, 0.0)
            self.nudgeRequested.emit(dx, dy)
        else:
            super(PickerView, self).keyPressEvent(event)
            return
        event.accept()

    def contextMenuEvent(self, event):
        self.contextMenuRequested.emit(event.globalPos(), self.mapToScene(event.pos()))

    def enterEvent(self, event):
        self.setFocus()  # pour que F fonctionne dès que la souris survole le picker
        super(PickerView, self).enterEvent(event)

    def drawBackground(self, painter, rect):
        super(PickerView, self).drawBackground(painter, rect)
        if not self.show_grid or self.zoom() < 0.3:
            return
        step = self.GRID
        left = int(math.floor(rect.left() / step)) * step
        top = int(math.floor(rect.top() / step)) * step
        lines = []
        x = left
        while x < rect.right():
            lines.append(QtCore.QLineF(x, rect.top(), x, rect.bottom()))
            x += step
        y = top
        while y < rect.bottom():
            lines.append(QtCore.QLineF(rect.left(), y, rect.right(), y))
            y += step
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 16))
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLines(lines)
        pen.setColor(QtGui.QColor(255, 255, 255, 45))
        painter.setPen(pen)
        painter.drawLine(QtCore.QLineF(0, rect.top(), 0, rect.bottom()))
        painter.drawLine(QtCore.QLineF(rect.left(), 0, rect.right(), 0))
