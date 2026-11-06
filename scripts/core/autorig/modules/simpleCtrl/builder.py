# ====================================================================================================================
# BASIC CTRL BUILDER
# ====================================================================================================================
#
#   Root class of every module builder, driven by MainBuild from the PreBuild data dict. On its own (BasicCtrl
#   module): a single ctrl '{side}_{baseName}_{index}_ctrl' on the root guide, no joint. 'offsetGroup': offset group
#   above it (else offset baked in its offsetParentMatrix). Parented by MainBuild under its parent guide ctrl; space
#   switch only if spaceSwitchTargets holds guides. The base Builder (base/builder.py) inherits it and adds the
#   joints, the guide chain ctrls and the constraints.
#
#   Builder
#       DATA            get_rig_group, get_geo_group, get_joints_group, get_controls_group, get_misc_group,
#                       get_setup_group, parent_to_setup, prefix,
#                       get_root_guide, get_int, get_float, get_message, get_vector_attribute
#       BUILD           build
#       JOINTS          build_joints (none), get_skin_joints
#       CONTROLS        build_controls, create_controls, create_control, get_control_color,
#                       shape_ctrl, adjust_control_shape, get_shape_scale, offset_group, no_ctrl
#       SPACE SWITCH    get_module_root_control, create_space_switches, create_space_switch, create_space_group,
#                       create_world_space_switch, resolve_space_target
#                       (module space switches split: spaceTranslate / spaceRotate / spaceScale on the ctrl)
#       SETUP           build_setup, create_setup, connect_setup
#
# ====================================================================================================================

import maya.cmds as cmds

from ....utilities import ctrl_utilities
from ....utilities import switchSpace_utilities

from importlib import reload

reload(ctrl_utilities)
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

        # Module setup group in MISC (get_setup_group).
        self.setup_group = None

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

    def get_setup_group(self):

        """
        Module setup group '{side}_{baseName}_{index:02d}_setup_grp' (root guide
        naming) under MISC_grp, holding the module setup nodes (ikHandles, curves,
        locators...). Created on first call; MISC_grp without root guide.
        """

        group = getattr(self, "setup_group", None)

        if group and cmds.objExists(group):
            return group

        misc = self.get_misc_group()
        root_guide = self.get_root_guide()

        if not root_guide:
            return misc

        base_name, side, index = self.main.get_guide_naming(root_guide)

        group = cmds.group(empty=True, name=f"{side}_{base_name}_{index:02d}_setup_grp")

        if misc:
            group = cmds.parent(group, misc)[0]

        self.setup_group = group

        return group

    def parent_to_setup(self, node, group=None):

        """Put 'node' in 'group' (module setup group by default) if not already there. Returns its name."""

        group = group or self.get_setup_group()

        if not group or not cmds.objExists(group):
            return node

        current_parent = cmds.listRelatives(node, parent=True, fullPath=True) or []

        if current_parent and current_parent[0] == cmds.ls(group, long=True)[0]:
            return node

        return cmds.parent(node, group)[0]

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

    def get_vector_attribute(self, key, default):

        """Vector (double3) module attribute (ex: 'aimVector'), or 'default'."""

        value = self.data.get(key)

        if isinstance(value, list) and value:
            value = value[0]

        if isinstance(value, (tuple, list)) and len(value) == 3:
            return tuple(value)

        return default

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
        """No joint: ctrl only (base Builder builds the guide chain)."""

        self.joints = []

        return self.joints

    def get_skin_joints(self):

        """
        Joints to bind the skin on (MainBuild 'JNT_bindskin' set): the module main chain
        (self.joints) by default. Override: ribbon sk joints, spine chain...
        """

        return list(self.joints)

    # ======================================================
    # CONTROLS
    # ======================================================

    def build_controls(self):

        self.controls = self.create_controls()

        return self.controls

    def create_controls(self):

        """One ctrl matched on the root guide, under CTRL_grp (MainBuild parents it later). Returns [ctrl]."""

        guide = self.get_root_guide()

        if not guide or not cmds.objExists(guide):
            return []

        base_name, side, index = self.main.get_guide_naming(guide)

        return [self.create_control(guide, base_name, side, index)]

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

        """Apply the module shape offset (shapeTranslate / Rotate, uniform shapeScale) to the ctrl CVs only."""

        translate = self.get_vector_attribute("shapeTranslate", default=(0.0, 0.0, 0.0))
        rotate = self.get_vector_attribute("shapeRotate", default=(0.0, 0.0, 0.0))
        scale = self.get_shape_scale()

        if (
            tuple(translate) == (0.0, 0.0, 0.0)
            and tuple(rotate) == (0.0, 0.0, 0.0)
            and tuple(scale) == (1.0, 1.0, 1.0)
        ):
            return

        control.transform_shape(translate=translate, rotate=rotate, scale=scale)

    def get_shape_scale(self):

        """
        'shapeScale' as a uniform (s, s, s). Old guides with a double3 shapeScale
        (before Update Guides) are still read as a vector.
        """

        value = self.data.get("shapeScale", 1.0)

        if isinstance(value, (list, tuple)):
            return self.get_vector_attribute("shapeScale", default=(1.0, 1.0, 1.0))

        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 1.0

        return (value, value, value)

    def offset_group(self):
        """'Offset Group' option: offset group above the ctrl instead of the offsetParentMatrix."""
        return bool(self.data.get("offsetGroup"))

    def no_ctrl(self):
        """'No Ctrl' option (base modules): shape directly on the joint. Never set on a BasicCtrl."""
        return bool(self.data.get("noCtrl"))

    # ======================================================
    # SPACE SWITCH
    # ======================================================

    def get_module_root_control(self):
        """Ctrl MainBuild parents under the parent guide ctrl (controls[0]), or None to leave the module ctrls in place."""

        return self.controls[0] if self.controls else None

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
            parent=current_parent,
            split=True
        )

    def create_space_group(self, control):

        """
        Space group '{..}_space_grp' inserted above 'control' (its offset group if any),
        under the same parent, matched on it, inheritsTransform OFF: its world placement
        comes only from its offsetParentMatrix (create_world_space_switch). The ctrl node
        goes under it, world pose kept, offsetParentMatrix re-baked. Returns the group.
        """

        offset = self.main.get_offset_group(control)
        node = offset if offset and cmds.objExists(offset) else control

        base = control[: -len("_ctrl")] if control.endswith("_ctrl") else control

        group = cmds.group(empty=True, name=f"{base}_space_grp")

        parent = cmds.listRelatives(node, parent=True, fullPath=True)

        if parent:
            group = cmds.parent(group, parent[0])[0]

        # Inherits off first: the world matrix set next is its own transform.
        cmds.setAttr(f"{group}.inheritsTransform", 0)
        cmds.xform(group, worldSpace=True, matrix=cmds.xform(node, query=True, worldSpace=True, matrix=True))

        world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)

        cmds.parent(node, group, relative=True)
        cmds.xform(node, worldSpace=True, matrix=world_matrix)

        ctrl_utilities.Control(node).transfer_offset_parent_matrix()

        return group

    def create_world_space_switch(self, control, targets_attr, attr_name="space"):

        """
        Space switch through a space group (create_space_group, inheritsTransform off)
        above 'control': its offsetParentMatrix in world space, spaces always "Local"
        (the group DAG parent) and "World" (rig top group), then data[targets_attr]
        (guides resolved to joints). Enums '{attr_name}Translate' / 'Rotate' / 'Scale' on the ctrl (split), maintain offset
        (no pop). 'No Ctrl' mode: create_space_switch. Returns the SpaceSwitch.
        """

        if not control or not cmds.objExists(control):
            return None

        if self.no_ctrl():
            return self.create_space_switch(control, attr_name=attr_name, targets_attr=targets_attr)

        group = self.create_space_group(control)

        local = (cmds.listRelatives(group, parent=True, fullPath=True) or [None])[0]
        world = self.get_rig_group("rig")

        spaces = []
        drivers = set()

        for name, driver in (("Local", local), ("World", world)):

            if driver and driver not in drivers:
                spaces.append((name, driver))
                drivers.add(driver)

        targets = self.data.get(targets_attr) or []

        for target in targets:

            driver = self.resolve_space_target(target)

            if not driver or driver in drivers:
                continue

            spaces.append((driver.split("|")[-1], driver))
            drivers.add(driver)

        if len(spaces) < 2:
            return None

        return switchSpace_utilities.SpaceSwitch(
            target=group,
            spaces=spaces,
            default=0,
            attr_name=attr_name,
            attr_host=control,
            mo=True,
            world=True,
            split=True
        )

    def resolve_space_target(self, target):

        """
        Build driver of a space switch target: the joint built from a guide (else its
        ctrl, ex: a BasicCtrl module without joint), or the node itself if it is not a
        guide (ex: a world group).
        """

        if not target or not cmds.objExists(target):
            return None

        short_name = target.split("|")[-1]

        if "_GUIDE" not in short_name:
            return target

        base_name, side, index = self.main.get_guide_naming(target)
        prefix = f"{side}_{base_name}_{index:02d}"

        for suffix in ("jnt", "ctrl"):

            candidate = f"{prefix}_{suffix}"

            if cmds.objExists(candidate):
                return candidate

        cmds.warning(f"Space switch target '{target}' has no built joint ('{prefix}_jnt').")

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
