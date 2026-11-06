# ====================================================================================================================
# SPINE RIBBON BUILDER
# ====================================================================================================================
#
#   FK chain (one ctrl per guide, simpleFk) with a ribbon attached (ribbon module steps).
#
#   JOINTS (all under the root joint)
#       root  {side}_{name}_{i}_root_jnt          - self.root_joint (on the 1st joint)
#       FK    {side}_{name}_{i}_jnt               - self.fk_joints, driven by the FK ctrls: child modules parent on
#                                                   them (MainBuild)
#       sk    {side}_{name}_{idx}_{i}_sk_jnt      - self.sk_joints, on the ribbon follicles (skin joints)
#       drv   {side}_{name}_{idx}_{i}_lvl{L}_drv_jnt - self.level_drivers, driven by the level ctrls
#       self.joints = [root] + FK + sk + drivers (root parented by MainBuild.parent_module_root).
#   CONTROLS
#       FK     {side}_{name}_{i}_ctrl              - simpleFk.create_fk_controls (controls[0], reparented by MainBuild)
#       level  {side}_{name}_{idx}_{i}_lvl{L}_ctrl - under the first FK ctrl, ride the surface below
#   SETUP
#       Ribbon through the guides, skinned to the FK joints, bindJointCount sk joints on follicles and up to
#       MAX_LEVELS ctrl levels. Ribbon methods are called explicitly (ribbonBuilder.xxx(self)): both parents share
#       method names.
#
#   Builder
#       DATA        get_float, get_string, get_role_color
#       BUILD       build
#       JOINTS      build_joints, get_skin_joints, build_ribbon_joints
#       CONTROLS    create_controls, create_fk_step
#       SETUP       create_setup, connect_setup
#
# ====================================================================================================================

import maya.cmds as cmds

from ..simpleBase.builder import Builder as BaseBuilder
from ..simpleFk import builder as simpleFk_builder
from ..simpleRibbon import builder as ribbon_builder
from ....utilities import joint_utilities

from importlib import reload

reload(simpleFk_builder)
reload(ribbon_builder)
reload(joint_utilities)


FkBuilder = simpleFk_builder.Builder
ribbonBuilder = ribbon_builder.Builder


# MRO: SpineRibbon -> FkBuilder -> ribbonBuilder -> BaseBuilder.
class Builder(FkBuilder, ribbonBuilder):

    MAX_LEVELS = 3

    CONTROL_SHAPE = "circle"
    CONTROL_COLOR_TYPE = "FK Main"

    ROOT_JOINT_SUFFIX = "root_jnt"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.root_joint = None
        self.fk_joints = []

    # ======================================================
    # DATA
    # ======================================================

    def get_float(self, key, default):
        """Float / int module attribute, or 'default' if missing / invalid."""

        try:
            return float(self.data.get(key))
        except (TypeError, ValueError):
            return default

    def get_string(self, key, default):
        """Enum module attribute (string, read by PreBuild), or 'default'."""

        value = self.data.get(key)

        return value if isinstance(value, str) and value else default

    def get_role_color(self, role):
        """Rig data color (or project default) for the module side and 'role'."""

        return self.main.get_color(self.data.get("side"), role)

    # ======================================================
    # BUILD
    # ======================================================

    def build(self):

        """Build this module alone (MainBuild runs each step as a separate pass over every module)."""

        self.build_joints()
        self.build_controls()
        self.build_setup()
        self.connect_setup()

        return self

    # ======================================================
    # JOINTS
    # ======================================================

    def build_joints(self, suffix="jnt"):

        """
        FK chain from the guides, root joint on its first joint (parent of the
        chain), then the ribbon joints. self.joints = [root] + FK + ribbon joints.
        """

        self.fk_joints = BaseBuilder.create_joints(self, suffix=suffix)

        if len(self.fk_joints) < 2:
            cmds.warning(f"SpineRibbon '{self.prefix}' : au moins 2 guides sont nécessaires.")

        if not self.fk_joints:
            self.joints = []
            return self.joints

        # Base: the ribbon (before Base in the MRO) has its own create_root_joint.
        BaseBuilder.create_root_joint(self, self.fk_joints[0], suffix=self.ROOT_JOINT_SUFFIX)

        joint_utilities.parent_joint(self.fk_joints[0], self.root_joint.name)

        self.joints = [self.root_joint] + self.fk_joints
        self.joints.extend(self.build_ribbon_joints())

        return self.joints

    def get_skin_joints(self):
        """Skin joints: the ribbon sk joints if the ribbon is built, else the FK chain."""

        if getattr(self, "sk_joints", None):
            return list(self.sk_joints)

        return list(self.fk_joints)

    def build_ribbon_joints(self):

        """
        Ribbon joints step: main + level nurbs through the guides, follicles,
        sk joints and level drivers under the root joint. Returns the created joints.
        """

        if not ribbonBuilder.has_ribbon_input(self):
            cmds.warning(f"SpineRibbon '{self.prefix}' : pas assez de guides pour le ruban, ruban ignoré.")
            return []

        self.setup_nodes = ribbonBuilder.create_nurb(self)
        self.setup_nodes.extend(ribbonBuilder.create_follicules(self))

        self.sk_joints = ribbonBuilder.create_sk_joints(self)
        self.level_drivers = ribbonBuilder.create_level_joints(self)

        return self.sk_joints + [driver for drivers in self.level_drivers for driver in drivers]

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        FK ctrls first (controls[0] = first FK ctrl), their sub ctrls ('subCtrl'), then the
        ribbon level ctrls under the first FK ctrl.
        """

        if not self.fk_joints:
            return []

        fk_controls = list(self.create_fk_step())

        controls = fk_controls + list(self.fk_sub_controls)

        if self.level_drivers:
            controls.extend(ribbonBuilder.create_level_controls(self, parent=fk_controls[0] if fk_controls else None))

        return controls

    def create_fk_step(self):
        """Chained FK ctrls on the FK chain (simpleFk.create_fk_controls), + sub ctrls with 'subCtrl'."""

        return FkBuilder.create_fk_controls(
            self,
            self.fk_joints,
            suffix="ctrl",
            shape=self.get_string("fkShape", self.CONTROL_SHAPE),
            size=self.get_float("fkSize", 1.5),
            color=self.get_role_color(self.CONTROL_COLOR_TYPE),
            sub=FkBuilder.use_sub_controls(self)
        )

    # ======================================================
    # SETUP
    # ======================================================

    def create_setup(self):

        """Ribbon setup: sk joints -> follicles, level ctrls on the surface below. Returns the setup nodes."""

        if not self.nurb:
            return []

        return ribbonBuilder.create_setup(self)

    def connect_setup(self):

        """Ribbon skins (main nurb -> FK joints, levels -> drivers) and follicle scale (ribbon.connect_setup)."""

        if self.nurb:
            ribbonBuilder.connect_setup(self)
