# ====================================================================================================================
# MESH CHECKS
# ====================================================================================================================
#
#   Ngons, NonManifold, LaminaFaces, ZeroAreaFaces, ZeroLengthEdges, History, UnfrozenTransforms,
#   LockedNormals
#
# ====================================================================================================================
"""Mesh topology, history and transform checks."""
from..utilities import geo_utilities
from .base import BaseCheck

CATEGORY = "Mesh"


class Ngons(BaseCheck):
    id = "mesh_ngons"
    label = "N-gons"
    category = CATEGORY
    DESCRIPTION = ("Faces avec plus de côtés que mesh.max_face_sides (4 par défaut). "
                   "Fix : triangule ces faces.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return self.mesh_components(scope, geo_utilities.ngons, self.settings["mesh"]["max_face_sides"])

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.triangulate_faces(self.existing_items())


class NonManifold(BaseCheck):
    id = "mesh_non_manifold"
    label = "Non-manifold"
    category = CATEGORY
    DESCRIPTION = ("Edges ou vertices non-manifold (edge partagé par plus de deux faces, "
                   "faces reliées par un seul vertex...). Pas de fix automatique.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return self.mesh_components(scope, geo_utilities.non_manifold)

    def select(self):
        return geo_utilities.select_items(self.items)


class LaminaFaces(BaseCheck):
    id = "mesh_lamina"
    label = "Lamina faces"
    category = CATEGORY
    DESCRIPTION = "Faces superposées qui partagent tous leurs edges. Fix : supprime ces faces."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return self.mesh_components(scope, geo_utilities.lamina_faces)

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.delete_components(self.existing_items())


class ZeroAreaFaces(BaseCheck):
    id = "mesh_zero_area"
    label = "Zero area faces"
    category = CATEGORY
    DESCRIPTION = ("Faces dont l'aire est nulle (sous mesh.zero_area_tolerance). "
                   "Pas de fix automatique.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        tolerance = self.settings["mesh"]["zero_area_tolerance"]
        return self.mesh_components(scope, geo_utilities.zero_area_faces, tolerance)

    def select(self):
        return geo_utilities.select_items(self.items)


class ZeroLengthEdges(BaseCheck):
    id = "mesh_zero_length"
    label = "Zero length edges"
    category = CATEGORY
    DESCRIPTION = ("Edges de longueur nulle (sous mesh.zero_length_tolerance). "
                   "Fix : collapse ces edges.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        tolerance = self.settings["mesh"]["zero_length_tolerance"]
        return self.mesh_components(scope, geo_utilities.zero_length_edges, tolerance)

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.collapse_edges(self.existing_items())


class History(BaseCheck):
    id = "mesh_history"
    label = "Construction history"
    category = CATEGORY
    DESCRIPTION = "Le mesh a encore de l'historique de construction. Fix : supprime l'historique."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        ignore = set(self.settings["mesh"].get("history_ignore_types", []))
        return [m for m in self.meshes(scope) if geo_utilities.has_history(m, ignore)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.delete_history(self.existing_items())


class UnfrozenTransforms(BaseCheck):
    id = "mesh_unfrozen"
    label = "Unfrozen transforms"
    category = CATEGORY
    DESCRIPTION = ("Le transform du mesh a des valeurs de translate / rotate / scale. "
                   "Fix : freeze transformations.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        tolerance = self.settings["mesh"]["transform_tolerance"]
        nodes = geo_utilities.shape_transforms(scope, self.settings, "mesh")
        return [node for node in nodes if geo_utilities.is_unfrozen(node, tolerance)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.freeze_transforms(self.existing_items())


class LockedNormals(BaseCheck):
    id = "mesh_locked_normals"
    label = "Locked normals"
    category = CATEGORY
    DESCRIPTION = "Le mesh a des normales lockées. Fix : unlock des normales."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return [m for m in self.meshes(scope) if geo_utilities.has_locked_normals(m)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.unlock_normals(self.existing_items())


CHECKS = [Ngons, NonManifold, LaminaFaces, ZeroAreaFaces, ZeroLengthEdges,
          History, UnfrozenTransforms, LockedNormals]
