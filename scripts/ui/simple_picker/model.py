# -*- coding: utf-8 -*-
"""Modèle de données du picker.

Aucune dépendance à Maya ni à Qt : ces classes ne font que décrire
un picker et se (dé)sérialiser en dictionnaire JSON.
"""
import base64
import copy
import uuid
from dataclasses import dataclass, field, asdict, fields

DATA_VERSION = 1

SHAPES = ["rect", "rounded", "circle", "ellipse", "diamond", "triangle", "hexagon", "star"]
BORDER_STYLES = ["solid", "dash", "dot", "none"]


def new_id():
    return uuid.uuid4().hex[:10]


class Serializable(object):
    """Mixin : to_dict / from_dict tolérant aux clés inconnues ou manquantes."""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        names = {f.name for f in fields(cls)}
        return cls(**{k: copy.deepcopy(v) for k, v in (data or {}).items() if k in names})


@dataclass
class ButtonData(Serializable):
    """Un bouton du picker. x / y = centre du bouton dans la scène."""
    id: str = field(default_factory=new_id)
    label: str = ""
    controls: list = field(default_factory=list)  # noms SANS namespace
    shape: str = "rounded"
    x: float = 0.0
    y: float = 0.0
    width: float = 30.0
    height: float = 30.0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    color: str = "#ff4a90d9"        # #AARRGGBB
    text_color: str = "#ffffffff"
    border_color: str = "#ff1a1a1a"
    border_width: float = 1.5
    border_style: str = "solid"
    corner_radius: float = 6.0
    font_size: int = 10

    def apply(self, values):
        """Applique un dictionnaire de valeurs (ex : un preset)."""
        for key, value in (values or {}).items():
            if key != "id" and hasattr(self, key):
                setattr(self, key, copy.deepcopy(value))

    def clone(self):
        other = ButtonData.from_dict(self.to_dict())
        other.id = new_id()
        return other


@dataclass
class BackgroundData(Serializable):
    """Image de fond, embarquée en base64 pour que le picker soit autonome."""
    image: str = ""
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0
    opacity: float = 1.0

    @property
    def has_image(self):
        return bool(self.image)

    def set_from_file(self, path):
        with open(path, "rb") as handle:
            self.image = base64.b64encode(handle.read()).decode("ascii")

    def image_bytes(self):
        return base64.b64decode(self.image) if self.image else b""


@dataclass
class PickerData(object):
    name: str = "Picker"
    namespace: str = ""
    background: BackgroundData = field(default_factory=BackgroundData)
    buttons: list = field(default_factory=list)

    def to_dict(self):
        return {
            "version": DATA_VERSION,
            "name": self.name,
            "namespace": self.namespace,
            "background": self.background.to_dict(),
            "buttons": [b.to_dict() for b in self.buttons],
        }

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            name=data.get("name", "Picker"),
            namespace=data.get("namespace", ""),
            background=BackgroundData.from_dict(data.get("background")),
            buttons=[ButtonData.from_dict(b) for b in data.get("buttons", [])],
        )

    def get_button(self, button_id):
        for button in self.buttons:
            if button.id == button_id:
                return button
        return None

    def remove_button(self, button_id):
        self.buttons = [b for b in self.buttons if b.id != button_id]
