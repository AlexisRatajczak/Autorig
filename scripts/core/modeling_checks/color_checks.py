"""Vertex color and display color checks."""
from ..utilities import geo_utilities
from .base import BaseCheck

CATEGORY = "Color"


class ColorSets(BaseCheck):
    id = "color_sets"
    label = "Vertex color sets"
    category = CATEGORY
    DESCRIPTION = "Le mesh contient des color sets (vertex colors). Fix : supprime les color sets."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        if self.settings["color"].get("allow_color_sets"):
            return []
        return [m for m in self.meshes(scope) if geo_utilities.color_sets(m)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.delete_color_sets(self.existing_items())


class DisplayColor(BaseCheck):
    id = "color_display"
    label = "Display / wireframe color"
    category = CATEGORY
    DESCRIPTION = ("Drawing override ou couleur de wireframe réglé à la main "
                   "(les display layers sont ignorés). Fix : remet l'affichage par défaut.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        nodes = []
        for transform in self.transforms(scope):
            nodes.append(transform)
            nodes.extend(geo_utilities.shapes_of(transform))
        return [node for node in nodes if geo_utilities.has_display_color(node)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.reset_display_color(self.existing_items())


class OutlinerColor(BaseCheck):
    id = "color_outliner"
    label = "Outliner color"
    category = CATEGORY
    DESCRIPTION = "Couleur personnalisée dans l'outliner. Fix : désactive la couleur."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return [node for node in self.transforms(scope) if geo_utilities.has_outliner_color(node)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.reset_outliner_color(self.existing_items())


CHECKS = [ColorSets, DisplayColor, OutlinerColor]
