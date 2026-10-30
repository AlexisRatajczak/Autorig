# ====================================================================================================================
# BASE BUILDER
# ====================================================================================================================
#
#   Default module build (joints, ctrls, setup) from the PreBuild data dict, driven by MainBuild. Module builders
#   (arm, legBiped, simpleIk, ikSpine, ...) inherit it and override only what they need (create_module_joints,
#   create_setup, connect_setup, ...).
#
#   Builder
#       DATA            get_rig_group, get_geo_group, get_joints_group, get_controls_group, get_misc_group, prefix,
#                       get_root_guide, get_int, get_float, get_message, level_count, get_chain_guides,
#                       get_chain_positions, get_chain_joints
#       BUILD           build
#       JOINTS          build_joints, create_joints, create_module_joints, create_root_joint, duplicate_joints,
#                       get_vector_attribute, get_joint_orientation, get_chain_plane_normal, orient_joint
#       CONTROLS        build_controls, create_controls, create_joint_shape, create_control, get_control_color,
#                       shape_ctrl, adjust_control_shape, simple_connection, offset_group, no_ctrl,
#                       get_attributes_host, connect_control, connect_control_direct
#       SPACE SWITCH    create_space_switches, create_space_switch, resolve_space_target
#       SETUP           build_setup, create_setup, connect_setup
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from ....utilities import joint_utilities
from ....utilities import ctrl_utilities
from ....utilities import cnstrMtx_utilities
from ....utilities import switchSpace_utilities

from importlib import reload

reload(joint_utilities)
reload(ctrl_utilities)
reload(cnstrMtx_utilities)
reload(switchSpace_utilities)


class Builder():

    # Default color role of the module ctrls (RigData.COLORS), ex: "IK Main" for an IK module.
    CONTROL_COLOR_TYPE = "FK Main"

    # Default ctrl shape (shapesCtrl_config.json).
    CONTROL_SHAPE = "circle"

    def __init__(self, module, data, main):

        self.module = module
        self.data = data
        self.main = main

        self.joints = []
        self.controls = []
        self.setups = []

    # ======================================================
    # DATA
    # ======================================================

    def get_rig_group(self, key):
        """Rig group 'key' of main.groups ("geo", "joints", "controls", "misc"), or None."""

        group = self.main.groups.get(key)

        return group if group and cmds.objExists(group) else None

    def get_geo_group(self):
        """Rig GEO group, or None."""

        return self.get_rig_group("geo")

    def get_joints_group(self):
        """Rig JNT group, or None."""

        return self.get_rig_group("joints")

    def get_controls_group(self):
        """Rig CTRL group, or None."""

        return self.get_rig_group("controls")

    def get_misc_group(self):
        """Rig MISC group, or None."""

        return self.get_rig_group("misc")

    @property
    def prefix(self):
        """{side}_{baseName}_{index:02d} (module guide naming)."""
        return f"{self.side}_{self.base_name}_{self.module_index:02d}"

    def get_root_guide(self):
        """Module root guide (first of data['guides'])."""

        guides = list((self.data.get("guides") or {}).keys())

        return guides[0] if guides else None

    def get_int(self, key, default):
        """Int module attribute, or 'default'."""

        try:
            return int(self.data.get(key))
        except (TypeError, ValueError):
            return default

    def get_float(self, key, default):
        """Float module attribute, or 'default'."""

        try:
            return float(self.data.get(key))
        except (TypeError, ValueError):
            return default

    def get_message(self, key):
        """First node connected to a single message attribute, or None."""

        value = self.data.get(key)

        if isinstance(value, (list, tuple)):
            value = value[0] if value else None

        return value if value and cmds.objExists(value) else None

    @property
    def level_count(self):
        return max(0, min(self.MAX_LEVELS, self.get_int("levelCount", 1)))

    def get_chain_guides(self):

        """Guides of the ribbon chain: ribbonJointGuides (in order), else the module guides if 2 or more."""

        guides = [guide for guide in (self.data.get("ribbonJointGuides") or []) if cmds.objExists(guide)]

        if len(guides) >= 2:
            return guides

        module_guides = [guide for guide in (self.data.get("guides") or {}) if cmds.objExists(guide)]

        return module_guides if len(module_guides) >= 2 else guides

    def get_chain_positions(self):
        """World positions of the chain guides."""

        return [cmds.xform(guide, query=True, worldSpace=True, translation=True) for guide in self.get_chain_guides()]

    def get_chain_joints(self):
        """Joints built from the chain guides (missing ones skipped)."""

        joints = []

        for guide in self.get_chain_guides():

            joint = self.resolve_space_target(guide)

            if joint and cmds.objExists(joint):
                joints.append(joint)

        return joints


    # ======================================================
    # BUILD
    # ======================================================

    def build(self):

        """
        Build the whole module: joints, ctrls, setup, connect. MainBuild runs these
        steps as separate passes; modules override create_joints /
        create_module_joints / create_controls / create_setup / connect_setup.
        """

        self.build_joints()
        self.build_controls()
        self.build_setup()
        self.connect_setup()

        return self

    # ======================================================
    # JOINTS
    # ======================================================

    def build_joints(self, suffix="jnt"):

        self.joints = self.create_joints(suffix=suffix)
        self.joints.extend(self.create_module_joints())

        return self.joints

    def create_joints(self, suffix="jnt"):

        """
        Module joint chain from its guides. Each joint transform is baked into its
        offsetParentMatrix (Joint.freeze_transform): clean channels.
        """

        joints = []

        guides = list(self.data["guides"].keys())

        aim_vector = self.get_vector_attribute("aimVector", default=(1, 0, 0))
        up_vector = self.get_vector_attribute("upVector", default=(0, 0, 1))

        # jointOrientation:
        #   Chain Plane : up on the chain plane normal (same bend axis, IK plane);
        #                 straight chain / 2 guides: up = Y axis of each guide;
        #   Guide Up    : up = Y axis of each guide;
        #   Guides      : exact orientation of each guide (no aim).
        orientation = self.get_joint_orientation()

        plane_normal = self.get_chain_plane_normal(guides) if orientation == "Chain Plane" else None

        parent = None

        for index, guide in enumerate(guides):

            next_guide = guides[index + 1] if index + 1 < len(guides) else None

            joint_data = {
                "baseName": self.data["baseName"],
                "side": self.data["side"],
                "parent": parent,
                "index": index,
                "guide": guide
            }

            joint = joint_utilities.Joint(joint_data, suffix=suffix)

            joint.create_joint()
            joint.match_transform(matchRot=orientation == "Guides")

            base_name, side, guide_index = self.main.get_guide_naming(guide)
            joint.rename(baseName=base_name, side=side, index=guide_index)

            if orientation != "Guides":

                self.orient_joint(
                    joint.name,
                    guide,
                    next_guide,
                    aim_vector=aim_vector,
                    up_vector=up_vector,
                    world_up=plane_normal
                )

                # Last joint: parent orientation.
                if next_guide is None:
                    cmds.setAttr(f"{joint.name}.jointOrient", 0, 0, 0)

            joint.freeze_transform()

            joints.append(joint)

            parent = joint.name

        return joints

    def create_module_joints(self):
        """Override to add extra joints (ex: pole, twist)."""
        return []

    def create_root_joint(self, reference=None, suffix="root_jnt"):

        """
        Module root joint '{side}_{baseName}_{index}_{suffix}' matched on 'reference'
        (first module joint by default), baked. The module chains go under it; it
        becomes joints[0]. Stored in self.root_joint and returned.
        """

        reference = reference or self.joints[0]

        base_name, side, index = self.main.get_guide_naming(reference.guide)

        joint = joint_utilities.Joint(
            {"baseName": base_name, "side": side, "index": index, "guide": reference.guide},
            suffix=suffix
        )
        joint.create_joint()
        joint.match_transform(reference.name, matchPos=True, matchRot=True)
        joint.freeze_transform()

        self.root_joint = joint

        return joint

    def duplicate_joints(self, replace_name={"_jnt": "_fk_jnt"}):

        """
        Duplicate the module chain from self.joints[0] (Joint.duplicate_chain).
        'replace_name' {old: new} renames each copy. Returns the Joints, root first.
        """

        if not self.joints:
            return []

        root = self.joints[0]
        root = root.name if isinstance(root, joint_utilities.Joint) else root

        if not root or not cmds.objExists(root):
            return []

        return joint_utilities.Joint.duplicate_chain(root, replace_name=replace_name)

    def get_vector_attribute(self, key, default):

        """Vector (double3) module attribute (ex: 'aimVector'), or 'default'."""

        value = self.data.get(key)

        if isinstance(value, list) and value:
            value = value[0]

        if isinstance(value, (tuple, list)) and len(value) == 3:
            return tuple(value)

        return default

    JOINT_ORIENTATIONS = ("Chain Plane", "Guide Up", "Guides")

    def get_joint_orientation(self):
        """Joint orientation mode (jointOrientation), 'Chain Plane' by default."""

        value = self.data.get("jointOrientation")

        return value if value in self.JOINT_ORIENTATIONS else self.JOINT_ORIENTATIONS[0]

    def get_chain_plane_normal(self, guides, tolerance=1e-3):

        """
        Normalized world normal of the guide chain plane: (middle - first) ^
        (last - middle). None with fewer than 3 guides or a straight chain.
        """

        guides = [guide for guide in guides if cmds.objExists(guide)]

        if len(guides) < 3:
            return None

        first, middle, last = (
            om.MVector(cmds.xform(guide, query=True, worldSpace=True, translation=True))
            for guide in (guides[0], guides[len(guides) // 2], guides[-1])
        )

        upper = middle - first
        lower = last - middle

        normal = upper ^ lower

        if normal.length() < tolerance * upper.length() * lower.length():
            return None

        normal.normalize()

        return (normal.x, normal.y, normal.z)

    def orient_joint(self, joint, guide, target, aim_vector=(1, 0, 0), up_vector=(0, 0, 1), world_up=None):

        """
        Aim the joint at 'target' (temporary aim constraint). Up: 'world_up' (ex:
        chain plane normal) if given, else the guide Y axis. Without target the
        joint keeps its parent orientation.
        """

        if not target or not cmds.objExists(target) or not cmds.objExists(joint):
            return

        if world_up:
            up_kwargs = {"worldUpType": "vector", "worldUpVector": tuple(world_up)}
        else:
            up_kwargs = {"worldUpType": "objectrotation", "worldUpVector": (0, 1, 0), "worldUpObject": guide}

        aim = cmds.aimConstraint(
            target,
            joint,
            aimVector=aim_vector,
            upVector=up_vector,
            name=f"{joint}_AIM_temp",
            **up_kwargs
        )

        cmds.delete(aim)

    # ======================================================
    # CONTROLS
    # ======================================================

    def build_controls(self):

        self.controls = self.create_controls()

        return self.controls

    def create_controls(self):

        """
        Default: one ctrl per guide, chained to the previous one and connected to
        its joint. 'noCtrl': the shape goes on the joint itself. The root space
        switch comes later (create_space_switches).
        """

        controls = []

        guides = list(self.data.get("guides", {}).keys())

        parent = None
        no_ctrl = self.no_ctrl()

        for guide in guides:

            if not cmds.objExists(guide):
                continue

            base_name, side, index = self.main.get_guide_naming(guide)
            joint = f"{side}_{base_name}_{index:02d}_jnt"

            if not cmds.objExists(joint):
                continue

            if no_ctrl:
                control = self.create_joint_shape(guide, base_name, side, index, joint)
            else:
                control = self.create_control(guide, base_name, side, index, parent=parent)
                self.connect_control(control, joint)

            controls.append(control)

            parent = control

        return controls

    def create_joint_shape(self, guide, base_name, side, index, joint, shape=None, size=1.0, color=None):

        """
        'No Ctrl' mode: build the ctrl shape (same shape / color / offset as
        create_control) on a temporary transform matched on the guide, then move it
        onto the joint, which becomes the animated node.
        """

        if shape is None:
            shape = self.shape_ctrl() or self.CONTROL_SHAPE

        if color is None:
            color = self.get_control_color()

        temp_name = f"{side}_{base_name}_{index:02d}_ctrlShape_TEMP"

        control = ctrl_utilities.Control(temp_name, shape=shape, size=size, color=color)
        control.create()

        self.adjust_control_shape(control)

        cmds.matchTransform(control.name, guide, position=True, rotation=True)

        control.transfer_to_joint(joint)

        return joint

    def create_control(self, guide, base_name, side, index, shape=None, size=1.0, color=None, parent=None):

        """
        Ctrl matched on the guide, offset under 'parent' (previous ctrl) or CTRL_grp.
        Defaults: CONTROL_SHAPE and the rig data color of the module side / role.
        """

        ctrl_name = f"{side}_{base_name}_{index:02d}_ctrl"

        if shape is None:
            shape = self.shape_ctrl() or self.CONTROL_SHAPE

        if color is None:
            color = self.get_control_color()

        control = ctrl_utilities.Control(ctrl_name, shape=shape, size=size, color=color)
        control.create()

        self.adjust_control_shape(control)

        cmds.matchTransform(control.name, guide, position=True, rotation=True)

        target_parent = parent if parent and cmds.objExists(parent) else self.main.groups.get("controls")

        # Offset group if 'Offset Group' is on, else baked into the ctrl offsetParentMatrix.
        control.create_offset(parent=target_parent, use_group=self.offset_group())

        return control.name

    def get_control_color(self):

        """Default ctrl color: rig data color (or project default) of the module side and CONTROL_COLOR_TYPE."""

        return self.main.get_color(self.data.get("side"), self.CONTROL_COLOR_TYPE)

    def shape_ctrl(self):

        """Ctrl shape asked by 'shapeCtrl', or None for 'Default'."""

        value = self.data.get("shapeCtrl")

        if not value or value == "Default":
            return None

        return value

    def adjust_control_shape(self, control):

        """Apply the module shape offset (shapeTranslate / Rotate / Scale) to the ctrl CVs only."""

        translate = self.get_vector_attribute("shapeTranslate", default=(0.0, 0.0, 0.0))
        rotate = self.get_vector_attribute("shapeRotate", default=(0.0, 0.0, 0.0))
        scale = self.get_vector_attribute("shapeScale", default=(1.0, 1.0, 1.0))

        if (
            tuple(translate) == (0.0, 0.0, 0.0)
            and tuple(rotate) == (0.0, 0.0, 0.0)
            and tuple(scale) == (1.0, 1.0, 1.0)
        ):
            return

        control.transform_shape(translate=translate, rotate=rotate, scale=scale)

    def simple_connection(self):
        """'Simple Connection' option."""
        return bool(self.data.get("simpleConnection"))

    def offset_group(self):
        """'Offset Group' option: offset group above the ctrl instead of the offsetParentMatrix."""
        return bool(self.data.get("offsetGroup"))

    def no_ctrl(self):
        """'No Ctrl' option: shape directly on the joint."""
        return bool(self.data.get("noCtrl"))

    def get_attributes_host(self, default=None):

        """
        Ctrl holding the module custom attributes, from 'attributesHost' (a guide,
        resolved to its ctrl, or its joint in 'No Ctrl' mode). Returns 'default'
        (the first module ctrl if not given) when unset or missing. The guide may
        belong to another module: call after every module is built.
        """

        if default is None and self.controls:
            default = self.controls[0]

        targets = self.data.get("attributesHost") or []

        if isinstance(targets, str):
            targets = [targets]

        if not targets or not cmds.objExists(targets[0]):
            return default

        guide = targets[0]

        base_name, side, index = self.main.get_guide_naming(guide)

        for suffix in ("ctrl", "jnt"):

            candidate = f"{side}_{base_name}_{index:02d}_{suffix}"

            if cmds.objExists(candidate):
                return candidate

        cmds.warning(f"Attributes host guide '{guide}' has no built ctrl.")

        return default

    def connect_control(self, control, joint):

        """Connect the ctrl to the joint: parent matrix constraint, or direct channels with 'simpleConnection'."""

        if not cmds.objExists(control) or not cmds.objExists(joint):
            return None

        if self.simple_connection():
            return self.connect_control_direct(control, joint)

        return cnstrMtx_utilities.ParentCnstrMtx(joint, control, dcmpMtx=False)

    def connect_control_direct(self, control, joint):

        """
        Simple connection: ctrl translate / rotate / scale -> joint channels (already
        zero). Lighter than a constraint, but the ctrl and joint must be aligned.
        """

        for attr in ("translate", "rotate", "scale"):
            cmds.connectAttr(f"{control}.{attr}", f"{joint}.{attr}", force=True)

        return None

    # ======================================================
    # SPACE SWITCH
    # ======================================================

    def create_space_switches(self):

        """
        Module space switches, called by MainBuild once every ctrl has its final
        parent. Default: on the root ctrl (or the joint in 'No Ctrl' mode).
        """

        if self.controls:
            self.create_space_switch(self.controls[0])

    def create_space_switch(self, control, attr_name="space", targets_attr="spaceSwitchTargets"):

        """
        Space switch on the offsetParentMatrix of 'control' (or its offset group)
        between its current parent ("Local") and data[targets_attr] (guides resolved
        to joints). Maintain offset keeps the existing bake. Nothing without targets.
        """

        targets = self.data.get(targets_attr) or []

        if not targets or not control or not cmds.objExists(control):
            return None

        offset = self.main.get_offset_group(control)
        node = offset if offset and cmds.objExists(offset) else control

        current_parent = cmds.listRelatives(node, parent=True, fullPath=True)
        current_parent = current_parent[0] if current_parent else None

        spaces = []
        drivers = set()

        if current_parent:
            spaces.append(("Local", current_parent))
            drivers.add(current_parent)

        for target in targets:

            driver = self.resolve_space_target(target)

            if not driver or driver in drivers:
                continue

            spaces.append((driver.split("|")[-1], driver))
            drivers.add(driver)

        if len(spaces) < 2:
            return None

        return switchSpace_utilities.SpaceSwitch(
            target=node,
            spaces=spaces,
            default=0,
            attr_name=attr_name,
            attr_host=control,
            parent=current_parent
        )

    def resolve_space_target(self, target):

        """
        Build driver of a space switch target: the joint built from a guide, or the
        node itself if it is not a guide (ex: a world group).
        """

        if not target or not cmds.objExists(target):
            return None

        short_name = target.split("|")[-1]

        if "_GUIDE" not in short_name:
            return target

        base_name, side, index = self.main.get_guide_naming(target)
        candidate = f"{side}_{base_name}_{index:02d}_jnt"

        if cmds.objExists(candidate):
            return candidate

        cmds.warning(f"Space switch target '{target}' has no built joint ('{candidate}').")

        return None

    # ======================================================
    # SETUP
    # ======================================================

    def build_setup(self):

        self.setups = self.create_setup()

        return self.setups

    def create_setup(self):
        """Override: constraints, IK, FK, nodes..."""
        return []

    def connect_setup(self):
        """Override: connect the setups to the joints."""
        pass
