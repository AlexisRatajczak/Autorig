# -*- coding: utf-8 -*-
"""Presets de boutons et de bordures, charges depuis config/picker_presets.json."""
import json
import os
import re

PRESETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "picker_presets.json"
)


def _load_presets():
    with open(PRESETS_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


_PRESETS = _load_presets()

SIDE_COLORS = _PRESETS["side_colors"]
BUTTON_PRESETS = _PRESETS["button_presets"]
BORDER_PRESETS = _PRESETS["border_presets"]

_LEFT = re.compile(r"(^|_)(l|lf|lft|left)(_|$)", re.IGNORECASE)
_RIGHT = re.compile(r"(^|_)(r|rt|rgt|right)(_|$)", re.IGNORECASE)


def guess_side_color(name):
    """Couleur selon la convention de nommage (L_/R_/_left...)."""
    short = name.split("|")[-1].split(":")[-1]
    if _LEFT.search(short) or "Left" in short:
        return SIDE_COLORS["left"]
    if _RIGHT.search(short) or "Right" in short:
        return SIDE_COLORS["right"]
    return SIDE_COLORS["center"]
