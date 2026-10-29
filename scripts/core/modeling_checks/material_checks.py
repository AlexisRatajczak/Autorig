"""Material assignment checks."""
from maya import cmds

from ..utilities import geo_utilities
from .base import BaseCheck

CATEGORY = "Material"


class NoMaterial(BaseCheck):
    id = "mat_missing"
    label = "No material"
    category = CATEGORY
    DESCRIPTION = ("Mesh sans aucun matériau assigné. "
                   "Fix : assigne material.default_shading_group.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return [m for m in self.meshes(scope) if not geo_utilities.shading_groups(m)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        geo_utilities.assign(self.existing_items(), self.settings["material"]["default_shading_group"])


class DefaultMaterialPolicy(BaseCheck):
    id = "mat_policy"
    label = "Default material policy"
    category = CATEGORY
    DESCRIPTION = ("Règle material.default_material_policy : 'required' = seul le matériau par "
                   "défaut est accepté, 'forbidden' = il est interdit, 'any' = pas de contrôle. "
                   "Fix (mode 'required') : réassigne le matériau par défaut.")

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        config = self.settings["material"]
        group, policy = config["default_shading_group"], config["default_material_policy"]
        return [m for m in self.meshes(scope) if geo_utilities.breaks_policy(m, group, policy)]

    def select(self):
        return geo_utilities.select_items(self.items)

    def fix(self):
        config = self.settings["material"]
        if config["default_material_policy"] != "required":
            cmds.warning("modeling_checker: no automatic fix unless the policy is 'required'")
            return
        geo_utilities.assign(self.existing_items(), config["default_shading_group"])


class PerFaceAssignment(BaseCheck):
    id = "mat_per_face"
    label = "Per-face assignment"
    category = CATEGORY
    DESCRIPTION = "Matériaux assignés par face au lieu de l'objet entier. Pas de fix automatique."

    def description(self):
        return self.DESCRIPTION

    def check(self, scope):
        return [m for m in self.meshes(scope) if geo_utilities.has_per_face_assignment(m)]

    def select(self):
        return geo_utilities.select_items(self.items)


CHECKS = [NoMaterial, DefaultMaterialPolicy, PerFaceAssignment]
