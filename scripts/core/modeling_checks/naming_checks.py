# ====================================================================================================================
# NAMING CHECKS
# ====================================================================================================================
#
#   _invalid(nodes, rule)                   - nodes breaking a naming rule
#   _rename_to_rule(nodes, settings, key)   - rename nodes to follow a rule
#   GroupNames, GeometryNames, CurveNames, ShapeNames, DuplicateNames, EmptyGroups
#
# ====================================================================================================================
"""Naming and hierarchy checks."""
from collections import Counter

from maya import cmds

from ..utilities import geo_utilities, naming_utilities
from .base import BaseCheck

CATEGORY = "Naming"


def _invalid(nodes, rule):
    return [node for node in nodes if not naming_utilities.is_valid(geo_utilities.leaf(node), rule)]


def _rename_to_rule(nodes, settings, key):
    rule = settings["naming"][key]
    strip = settings["naming"].get("strip_suffixes", [])
    geo_utilities.rename_many(nodes, lambda node: naming_utilities.suggest(geo_utilities.leaf(node), rule, strip))


class GroupNames(BaseCheck):
    id = "naming_group"
    label = "Group names"
    category = CATEGORY
    DESCRIPTION = ("Les groupes (transforms sans shape) doivent respecter le préfixe, le suffixe "
                   "et le pattern de naming.group. Fix : renomme avec le bon suffixe.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return _invalid(geo_utilities.groups(scope, self.settings), self.settings["naming"]["group"])

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        _rename_to_rule(self.existing_items(), self.settings, "group")


class GeometryNames(BaseCheck):
    id = "naming_geo"
    label = "Geometry names"
    category = CATEGORY
    DESCRIPTION = ("Les transforms de mesh doivent respecter naming.geo. "
                   "Fix : renomme avec le bon suffixe.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        nodes = geo_utilities.shape_transforms(scope, self.settings, "mesh")
        return _invalid(nodes, self.settings["naming"]["geo"])

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        _rename_to_rule(self.existing_items(), self.settings, "geo")


class CurveNames(BaseCheck):
    id = "naming_curve"
    label = "Curve names"
    category = CATEGORY
    DESCRIPTION = ("Les transforms de curve doivent respecter naming.curve. "
                   "Fix : renomme avec le bon suffixe.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        nodes = geo_utilities.shape_transforms(scope, self.settings, "nurbsCurve")
        return _invalid(nodes, self.settings["naming"]["curve"])

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        _rename_to_rule(self.existing_items(), self.settings, "curve")


class ShapeNames(BaseCheck):
    id = "naming_shape"
    label = "Shape names"
    category = CATEGORY
    DESCRIPTION = ("Chaque shape doit porter le nom de son transform suivi de 'Shape' "
                   "(naming.shape.template). Fix : renomme la shape.")

    def description(self):
        return self.DESCRIPTION

    def _expected(self, shape):
        rule = self.settings["naming"]["shape"]
        types = set(rule.get("shape_types", ["mesh", "nurbsCurve"]))
        parent = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
        siblings = [s for s in geo_utilities.shapes_of(parent) if cmds.nodeType(s) in types]
        index = siblings.index(shape) if shape in siblings else 0
        return naming_utilities.expected_shape_name(geo_utilities.leaf(parent), index, rule)

    def check(self, scope):
        types = set(self.settings["naming"]["shape"].get("shape_types", ["mesh", "nurbsCurve"]))
        result = []
        for transform in self.transforms(scope):
            for shape in geo_utilities.shapes_of(transform):
                if cmds.nodeType(shape) in types and geo_utilities.leaf(shape) != self._expected(shape):
                    result.append(shape)
        return result

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.rename_many(self.existing_items(), self._expected)


class DuplicateNames(BaseCheck):
    id = "duplicate_names"
    label = "Duplicate names"
    category = CATEGORY
    DESCRIPTION = ("Plusieurs transforms portent le même nom court dans la scène. "
                   "Pas de fix automatique : à renommer à la main.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        nodes = self.transforms(scope)
        counts = Counter(geo_utilities.short(node) for node in nodes)
        return [node for node in nodes if counts[geo_utilities.short(node)] > 1]

    def select(self):
        return geo_utilities.select_items(self.items)


class EmptyGroups(BaseCheck):
    id = "empty_groups"
    label = "Empty groups"
    category = CATEGORY
    DESCRIPTION = "Groupes sans aucun enfant. Fix : supprime ces groupes."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        groups = geo_utilities.groups(scope, self.settings)
        return [group for group in groups if not cmds.listRelatives(group, children=True)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        for node in self.items:
            if cmds.objExists(node):
                geo_utilities.safe(cmds.delete, node)


CHECKS = [GroupNames, GeometryNames, CurveNames, ShapeNames, DuplicateNames, EmptyGroups]
