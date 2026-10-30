# ====================================================================================================================
# MAIN BUILD
# ====================================================================================================================
#
#   MainBuild(data)
#       build()                 - run every build step
#       RIG NAME                get_rig_name
#       GROUPS                  create_groups, get_or_create_group
#       SETS                    create_sets, get_or_create_set, add_to_set
#       LAYERS                  create_layers, create_layer
#       BUILDERS                create_builders, get_first_joint_name, get_builder
#       COLORS                  get_color
#       MODULES                 build_modules
#       JOINTS                  parent_joint_modules, parent_module_root, get_guide_naming
#       CONTROLS                parent_ctrls_module, parent_module_root_control, get_offset_group
#       SPACE SWITCH            create_space_switches
#       MISC                    parent_misc_module
#       CLEAN                   cleanup_temp
#       CUSTOM                  custom
#
# ====================================================================================================================

from abc import ABC, abstractmethod

import maya.cmds as cmds

from ..modules import registry
from ..rigData import init_rigData
from ...utilities import ctrl_utilities
from importlib import reload

reload(registry)
reload(init_rigData)
reload(ctrl_utilities)


class MainBuild():

    def __init__(self, data):

        self.rig_data = data.get("rig_data")
        self.data = data.get("modules", {})

        self.groups = {}
        self.sets = {}
        self.layers = {}

        self.builders = {}

        self.joints = []
        self.controls = []
        self.setups = []

        self.build()

    # ======================================================
    # BUILD
    # ======================================================

    def build(self):

        self.create_groups()
        self.create_sets()
        self.create_layers()
        self.create_builders()
        self.build_modules()
        self.parent_ctrls_module()
        self.create_space_switches()
        self.parent_misc_module()
        self.cleanup_temp()
        self.custom()

    # ======================================================
    # RIG NAME
    # ======================================================

    def get_rig_name(self):

        if self.rig_data and cmds.objExists(self.rig_data) and cmds.attributeQuery("rigName", node=self.rig_data, exists=True):
            return cmds.getAttr(f"{self.rig_data}.rigName") or self.rig_data

        return self.rig_data or "RIG"

    # ======================================================
    # GROUPS
    # ======================================================

    def create_groups(self):

        self.groups["rig"] = self.get_or_create_group(f"{self.get_rig_name()}_RIG")
        self.groups["geo"] = self.get_or_create_group("GEO_grp", parent=self.groups["rig"])
        self.groups["joints"] = self.get_or_create_group("JNT_grp", parent=self.groups["rig"])
        self.groups["controls"] = self.get_or_create_group("CTRL_grp", parent=self.groups["rig"])
        self.groups["misc"] = self.get_or_create_group("MISC_grp", parent=self.groups["rig"])

    def get_or_create_group(self, name, parent=None):

        """Existing group 'name', else a new empty group (under 'parent' if given)."""

        if cmds.objExists(name):
            return name

        if parent:
            return cmds.group(empty=True, name=name, parent=parent)

        return cmds.group(empty=True, name=name)

    # ======================================================
    # SETS
    # ======================================================

    def create_sets(self):

        self.sets["joints"] = self.get_or_create_set("JNT_set")
        self.sets["controls"] = self.get_or_create_set("CTRL_set")
        self.sets["setup"] = self.get_or_create_set("SETUP_set")

        self.sets["rig"] = self.get_or_create_set(
            f"{self.get_rig_name()}_set",
            members=[self.sets["joints"], self.sets["controls"], self.sets["setup"]]
        )

    def get_or_create_set(self, name, members=None):

        """Existing set 'name', else a new set (with 'members' if given)."""

        if cmds.objExists(name):
            return name

        if members:
            return cmds.sets(members, name=name)

        return cmds.sets(name=name, em=True)

    def add_to_set(self, node, set_name):

        if cmds.objExists(node):
            cmds.sets(node, add=set_name)

    # ======================================================
    # LAYERS
    # ======================================================

    def create_layers(self):

        self.layers["geo"] = self.create_layer("GEO_layer", [self.groups["geo"]])
        self.layers["joints"] = self.create_layer("JNT_layer", [self.groups["joints"]])
        self.layers["controls"] = self.create_layer("CTRL_layer", [self.groups["controls"]])

    def create_layer(self, name, members=None):

        """Existing display layer 'name', else a new one (with 'members' if given)."""

        if cmds.objExists(name):
            return name

        layer = cmds.createDisplayLayer(name=name, empty=True)

        if members:
            cmds.editDisplayLayerMembers(layer, members, noRecurse=True)

        return layer

    # ======================================================
    # BUILDERS
    # ======================================================

    def create_builders(self):

        """
        One Builder per module (from its moduleType, through the registry),
        reused by every build pass so each keeps its own state.
        """

        self.builders = {}

        for module, data in self.data.items():

            # Already built (its first joint exists): no builder, skipped by every pass.
            first_joint = self.get_first_joint_name(data)

            if first_joint and cmds.objExists(first_joint):
                cmds.warning(f"'{module}' déjà construit ('{first_joint}' existe) : module ignoré.")
                continue

            self.builders[module] = self.get_builder(module, data)

    def get_first_joint_name(self, data):

        """First joint name of a module ({side}_{baseName}_{index:02d}_jnt) from its first guide, or None."""

        guides = list((data or {}).get("guides") or [])

        if not guides:
            return None

        base_name, side, index = self.get_guide_naming(guides[0])

        return f"{side}_{base_name}_{index:02d}_jnt"

    def get_builder(self, module, data):

        """Builder of the module's moduleType (base Builder as fallback)."""

        builder_class = (
            registry.get_builder_class(data.get("moduleType"))
            or registry.get_base_builder_class()
        )

        return builder_class(module, data, self)

    # ======================================================
    # COLORS
    # ======================================================

    def get_color(self, side, color_type):

        """
        RGB (0-1) color set on the rig data for this side / type (ex: 'Left', 'FK Main').
        Falls back on the project default (config/colorCtrl_config.json).
        """

        attribute = init_rigData.RigData.color_name(side, color_type)

        if (
            self.rig_data
            and cmds.objExists(self.rig_data)
            and cmds.attributeQuery(attribute, node=self.rig_data, exists=True)
        ):

            rgb = cmds.getAttr(f"{self.rig_data}.{attribute}")

            if isinstance(rgb, list) and rgb:
                rgb = rgb[0]

            if rgb:
                return tuple(rgb)

        return tuple(
            init_rigData.DEFAULT_COLORS.get(side, {}).get(color_type, (1.0, 1.0, 1.0))
        )

    # ======================================================
    # MODULES
    # ======================================================

    def build_modules(self):

        """
        Build every module in separate passes (joints, ctrls, setup, connect)
        so the module order does not matter. parent_joint_modules() runs
        between joints and ctrls: every joint has its final DAG parent before
        its constraint is built.
        """

        for module, builder in self.builders.items():
            builder.build_joints()

        self.parent_joint_modules()

        for module, builder in self.builders.items():
            builder.build_controls()

        for module, builder in self.builders.items():
            builder.build_setup()

        for module, builder in self.builders.items():
            builder.connect_setup()

            self.joints.extend(builder.joints)
            self.controls.extend(builder.controls)
            self.setups.extend(builder.setups)

            for joint in builder.joints:
                self.add_to_set(joint.name, self.sets["joints"])

            for control in builder.controls:
                self.add_to_set(control, self.sets["controls"])

            for setup in builder.setups:
                self.add_to_set(setup, self.sets["setup"])

    # ======================================================
    # JOINTS
    # ======================================================

    def parent_joint_modules(self):

        """Parent the first joint of each module, once every joint exists."""

        for module, builder in self.builders.items():

            if not builder.joints:
                continue

            module_parent = self.data.get(module, {}).get("parent")

            self.parent_module_root(builder.joints[0], module_parent)

    def parent_module_root(self, joint, module_parent):

        """
        Parent the first joint of a module under the joint of its parent
        guide, else under JNT_grp.

        Static joint (offsetParentMatrix baked, not connected): world matrix
        kept through a relative parent, then the offsetParentMatrix is
        re-baked. Driven joint (ParentCnstrMtx): plain cmds.parent.
        """

        target = None

        if module_parent and cmds.objExists(module_parent):

            base_name, side, index = self.get_guide_naming(module_parent)
            candidate = f"{side}_{base_name}_{index:02d}_jnt"

            if cmds.objExists(candidate):
                target = candidate

        if not target:
            target = self.groups.get("joints")

        if not target or not cmds.objExists(target) or not cmds.objExists(joint.name):
            return

        current_parent = cmds.listRelatives(joint.name, parent=True, fullPath=True) or []
        target_path = cmds.ls(target, long=True)[0]

        if current_parent and current_parent[0] == target_path:
            return

        if cmds.listConnections(f"{joint.name}.offsetParentMatrix", source=True, destination=False):
            cmds.parent(joint.name, target)
            return

        world_matrix = cmds.xform(joint.name, query=True, matrix=True, worldSpace=True)

        cmds.parent(joint.name, target, relative=True)
        cmds.xform(joint.name, worldSpace=True, matrix=world_matrix)

        joint.freeze_transform()

    def get_guide_naming(self, guide):

        """(baseName, side, index) from a guide name (ex: L_Brow_00_GUIDE, L_Brow_00_GUIDE_ROOT)."""

        short_name = guide.split("|")[-1]
        base = short_name.split("_GUIDE")[0]
        parts = base.split("_")

        side = parts[0]
        index = int(parts[-1])
        base_name = "_".join(parts[1:-1])

        return base_name, side, index

    # ======================================================
    # CONTROLS
    # ======================================================

    def parent_ctrls_module(self):

        """Parent the first ctrl of each module, once every ctrl exists."""

        for module, builder in self.builders.items():

            if not builder.controls:
                continue

            module_parent = self.data.get(module, {}).get("parent")

            self.parent_module_root_control(builder.controls[0], module_parent)

    def parent_module_root_control(self, control, module_parent):

        """
        Parent the first ctrl of a module under the ctrl of its parent guide,
        else under CTRL_grp.

        Offset group if one exists, else the ctrl itself: relative parent,
        world matrix restored, offsetParentMatrix re-baked. Skipped in
        'No Ctrl' mode ('control' is then a joint, parented by parent_module_root).
        """

        if not control or not cmds.objExists(control) or not control.endswith("_ctrl"):
            return

        offset = self.get_offset_group(control)
        node = offset if offset and cmds.objExists(offset) else control

        target = None

        if module_parent and cmds.objExists(module_parent):

            base_name, side, index = self.get_guide_naming(module_parent)
            candidate = f"{side}_{base_name}_{index:02d}_ctrl"

            if cmds.objExists(candidate):
                target = candidate

        if not target:
            target = self.groups.get("controls")

        if not target or not cmds.objExists(target):
            return

        current_parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        target_path = cmds.ls(target, long=True)[0]

        if current_parent and current_parent[0] == target_path:
            return

        if node == offset:
            cmds.parent(node, target)
            return

        world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)

        cmds.parent(node, target, relative=True)
        cmds.xform(node, worldSpace=True, matrix=world_matrix)

        ctrl_utilities.Control(node).transfer_offset_parent_matrix()

    def get_offset_group(self, control):

        """Offset group name of a ctrl (..._ctrl -> ..._offset)."""

        if control and control.endswith("_ctrl"):
            return control[: -len("_ctrl")] + "_offset"

        return None

    # ======================================================
    # SPACE SWITCH
    # ======================================================

    def create_space_switches(self):

        """Space switches of every builder, once every ctrl has its final parent."""

        for builder in self.builders.values():
            builder.create_space_switches()

    # ======================================================
    # MISC
    # ======================================================

    def parent_misc_module(self):

        """Safety net: parent under MISC_grp every setup node still at the scene root."""

        misc_group = self.groups.get("misc")

        if not misc_group or not cmds.objExists(misc_group):
            return

        for setup in self.setups:

            if not setup or not cmds.objExists(setup):
                continue

            current_parent = cmds.listRelatives(setup, parent=True) or []

            if not current_parent:
                cmds.parent(setup, misc_group)

    # ======================================================
    # CLEAN
    # ======================================================

    def cleanup_temp(self):

        """Delete every temporary node (*_temp)."""

        temp_nodes = cmds.ls("*_temp")

        if temp_nodes:
            cmds.delete(temp_nodes)

    # ======================================================
    # CUSTOM
    # ======================================================

    @abstractmethod
    def custom(self):
        pass
