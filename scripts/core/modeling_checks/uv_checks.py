# ====================================================================================================================
# UV CHECKS
# ====================================================================================================================
#
#   MissingUVs, ExtraUVSets, UVSetName, UVsOutOfRange, UVsCrossingTiles, FlippedUVs, OverlappingUVs
#
# ====================================================================================================================
"""UV checks."""
from ..utilities import geo_utilities
from .base import BaseCheck

CATEGORY = "UV"


class MissingUVs(BaseCheck):
    id = "uv_missing"
    label = "Missing UVs"
    category = CATEGORY
    DESCRIPTION = "Mesh sans aucun UV, ou faces sans UV. Pas de fix automatique."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return self.mesh_components(scope, geo_utilities.missing_uvs)

    def select(self):
        return geo_utilities.select_items(self.items)


class ExtraUVSets(BaseCheck):
    id = "uv_sets"
    label = "Extra UV sets"
    category = CATEGORY
    DESCRIPTION = "Le mesh a plus de UV sets que uv.max_uv_sets. Fix : supprime les UV sets en trop."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        maximum = self.settings["uv"]["max_uv_sets"]
        return [m for m in self.meshes(scope) if len(geo_utilities.uv_sets(m)) > maximum]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.delete_extra_sets(self.existing_items(), self.settings["uv"]["max_uv_sets"])


class UVSetName(BaseCheck):
    id = "uv_set_name"
    label = "UV set name"
    category = CATEGORY
    DESCRIPTION = ("Le premier UV set doit s'appeler comme uv.default_uv_set (map1). "
                   "Fix : renomme le UV set.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        name = self.settings["uv"]["default_uv_set"]
        result = []
        for mesh in self.meshes(scope):
            sets = geo_utilities.uv_sets(mesh)
            if sets and sets[0] != name:
                result.append(mesh)
        return result

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.rename_first_set(self.existing_items(), self.settings["uv"]["default_uv_set"])


class UVsOutOfRange(BaseCheck):
    id = "uv_range"
    label = "UVs out of range"
    category = CATEGORY
    DESCRIPTION = ("UVs en coordonnées négatives, ou hors de l'espace 0-1 si uv.allow_udim est "
                   "false. Pas de fix automatique.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        config = self.settings["uv"]
        return self.mesh_components(scope, geo_utilities.out_of_range, config["allow_udim"], config["udim_max_u"])

    def select(self):
        return geo_utilities.select_items(self.items)


class UVsCrossingTiles(BaseCheck):
    id = "uv_cross_border"
    label = "UVs crossing tiles"
    category = CATEGORY
    DESCRIPTION = ("Faces dont les UVs sont à cheval sur plusieurs tiles UV / UDIM. "
                   "Pas de fix automatique.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return self.mesh_components(scope, geo_utilities.crossing_borders)

    def select(self):
        return geo_utilities.select_items(self.items)


class FlippedUVs(BaseCheck):
    id = "uv_flipped"
    label = "Flipped UVs"
    category = CATEGORY
    DESCRIPTION = "Faces dont les UVs sont retournés (sens inversé). Pas de fix automatique."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return self.mesh_components(scope, geo_utilities.flipped)

    def select(self):
        return geo_utilities.select_items(self.items)


class OverlappingUVs(BaseCheck):
    id = "uv_overlap"
    label = "Overlapping UVs"
    category = CATEGORY
    DESCRIPTION = "Faces qui se chevauchent dans l'espace UV. Pas de fix automatique."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return self.mesh_components(scope, geo_utilities.overlapping)

    def select(self):
        return geo_utilities.select_items(self.items)


CHECKS = [MissingUVs, ExtraUVSets, UVSetName, UVsOutOfRange, UVsCrossingTiles,
          FlippedUVs, OverlappingUVs]
