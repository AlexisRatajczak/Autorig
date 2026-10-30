# ====================================================================================================================
# LIMB BUILDER
# ====================================================================================================================
#
#   3 joint limb (shoulder / hip -> elbow / knee -> wrist / ankle) with an IK/FK switch. FK and IK steps come
#   from simpleFk / simpleIk, each on its own chain.
#
#   JOINTS (Builder.create_joints, once per chain, all under the root joint)
#       root  {side}_{name}_{i}_root_jnt  - self.root_joint (on the 1st joint)
#       bind  {side}_{name}_{i}_jnt       - self.bind_joints
#       FK    {side}_{name}_{i}_fk_jnt    - self.fk_joints
#       IK    {side}_{name}_{i}_ik_jnt    - self.ik_joints
#       self.joints = [root] + bind (root parented by MainBuild.parent_module_root).
#   CONTROLS (all under the root ctrl)
#       Root    root_ctrl on the root joint, drives it (controls[0], reparented by MainBuild)
#       FK      simpleFk.create_fk_controls on the FK chain (fk_ctrl)
#       IK      simpleIk.create_ik_control / create_pole_control on the IK chain (ik_ctrl + pole_ctrl)
#       Switch  switch_ctrl holding 'ikFk', follows the last bind joint
#       'No Ctrl': root shape on the root joint, IK / pole joint ctrls under it.
#   SETUP
#       simpleIk setup on the IK chain (ikHandle under MISC_grp). Each bind joint follows its FK or IK joint
#       through a blend SpaceSwitch driven by 'ikFk', which also drives the FK / IK ctrl visibility.
#   RIBBON ('useRibbon', ribbon module steps)
#       Ribbon through the limb guides, skinned to the bind joints, bindJointCount sk joints on follicles and up
#       to 2 ctrl levels. Ribbon methods are called explicitly (ribbonBuilder.xxx(self)): several limb parents
#       share method names.
#
#   Builder
#       DATA HELPERS    get_float, get_string, use_ribbon
#       BUILD           build
#       JOINTS          build_joints, build_ribbon_joints, fk_chain, ik_chain
#       CONTROLS        create_controls, create_limb_root_control, parent_under_root, create_fk_step,
#                       create_ik_step, create_switch_control, control_name_for
#       SETUP           create_setup, connect_setup, create_ik_setup, connect_ik_setup
#       IK / FK SWITCH  create_ik_fk_switch, connect_ik_fk_visibility, connect_visibility
#       SPACE SWITCH    create_space_switches
#
# ====================================================================================================================

import maya.cmds as cmds

from ..base.builder import Builder as BaseBuilder
from ..simpleIk import builder as simpleIk_builder
from ..simpleFk import builder as simpleFk_builder
from ..ribbon import builder as ribbon_builder
from ....utilities import joint_utilities
from ....utilities import ctrl_utilities
from ....utilities import cnstrMtx_utilities
from ....utilities import switchSpace_utilities

from importlib import reload

reload(simpleIk_builder)
reload(simpleFk_builder)
reload(ribbon_builder)
reload(joint_utilities)
reload(ctrl_utilities)
reload(cnstrMtx_utilities)
reload(switchSpace_utilities)


IkBuilder = simpleIk_builder.Builder
FkBuilder = simpleFk_builder.Builder
ribbonBuilder = ribbon_builder.Builder


# MRO: Limb -> IkBuilder -> FkBuilder -> ribbonBuilder -> BaseBuilder (base class after its subclasses).
class Builder(IkBuilder, FkBuilder, ribbonBuilder):

    # Limb ribbon: 2 levels max.
    MAX_LEVELS = 2

    CONTROL_SHAPE = "circle"
    CONTROL_COLOR_TYPE = "FK Main"

    ROOT_JOINT_SUFFIX = "root_jnt"
    LIMB_ROOT_CONTROL_SUFFIX = "root_ctrl"
    LIMB_ROOT_CONTROL_SHAPE = "square"
    LIMB_ROOT_CONTROL_COLOR_TYPE = "FK Main"

    FK_CONTROL_SUFFIX = "fk_ctrl"
    IK_CONTROL_SUFFIX = "ik_ctrl"
    POLE_CONTROL_SUFFIX = "pole_ctrl"
    SWITCH_CONTROL_SUFFIX = "switch_ctrl"

    SWITCH_CONTROL_SHAPE = "plus"
    SWITCH_CONTROL_COLOR_TYPE = "FK Secondary"
    SWITCH_ATTR = "ikFk"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.root_joint = None
        self.bind_joints = []
        self.fk_joints = []
        self.ik_joints = []

        # Not self.root_control (simpleIk): it would constrain the IK chain root.
        self.limb_root_control = None
        self.switch_control = None
        self.ik_fk_switches = []
        self.ik_fk_plug = None

        # Used by simpleIk get_pole_vector_position.
        self.POLE_DISTANCE = self.get_float("poleDistance", 1.0)

    # ======================================================
    # DATA HELPERS
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

    def use_ribbon(self):
        """'Use Ribbon' option: add a ribbon to the limb."""

        return bool(self.data.get("useRibbon"))

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
        Bind chain, identical FK and IK chains, then the root joint on the
        first joint, parent of the 3 chains. self.joints = [root] + bind.
        """

        self.bind_joints = self.create_joints(suffix=suffix)
        self.bind_joints.extend(self.create_module_joints())

        self.fk_chain()
        self.ik_chain()

        # Base: the ribbon (before Base in the MRO) has its own create_root_joint.
        BaseBuilder.create_root_joint(self, self.bind_joints[0], suffix=self.ROOT_JOINT_SUFFIX)

        for chain in (self.bind_joints, self.fk_joints, self.ik_joints):
            if chain:
                joint_utilities.parent_joint(chain[0], self.root_joint.name)

        self.joints = [self.root_joint] + self.bind_joints

        if self.use_ribbon():
            self.joints.extend(self.build_ribbon_joints())

        return self.joints

    def build_ribbon_joints(self):

        """
        Ribbon joints step: main + level nurbs through the limb guides,
        follicles, sk joints and level drivers under the limb root joint.
        Returns the created joints.
        """

        if not ribbonBuilder.has_ribbon_input(self):
            cmds.warning(f"Limb '{self.prefix}' : pas assez de guides pour le ruban, ruban ignoré.")
            return []

        self.setup_nodes = ribbonBuilder.create_nurb(self)
        self.setup_nodes.extend(ribbonBuilder.create_follicules(self))

        self.sk_joints = ribbonBuilder.create_sk_joints(self)
        self.level_drivers = ribbonBuilder.create_level_joints(self)

        return self.sk_joints + [driver for drivers in self.level_drivers for driver in drivers]

    def fk_chain(self):
        """FK chain ({side}_{baseName}_{index}_fk_jnt) from the guides."""

        self.fk_joints = self.create_joints(suffix="fk_jnt")

        return self.fk_joints

    def ik_chain(self):
        """IK chain ({side}_{baseName}_{index}_ik_jnt) from the guides."""

        self.ik_joints = self.create_joints(suffix="ik_jnt")

        return self.ik_joints

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """Root ctrl first (controls[0]), then FK, IK, pole and switch, all under the root ctrl."""

        if not self.bind_joints or not self.fk_joints or not self.ik_joints:
            return []

        root_control = self.create_limb_root_control()

        fk_controls = list(self.create_fk_step())
        ik_control, pole_control = self.create_ik_step()

        # The switch is constrained at creation (parent space frozen): created under the root directly.
        switch_control = self.create_switch_control(parent=root_control)

        for control in (fk_controls[:1] + [ik_control, pole_control]):
            self.parent_under_root(control)

        controls = [root_control] + fk_controls

        for control in (ik_control, pole_control, switch_control):
            if control:
                controls.append(control)

        # Ribbon: level ctrls under the limb root ctrl.
        if self.use_ribbon() and self.level_drivers:
            controls.extend(ribbonBuilder.create_level_controls(self, parent=root_control))

        return controls

    # --------------------------------------------------
    # ROOT
    # --------------------------------------------------

    def create_limb_root_control(self):

        """
        Root ctrl '{side}_{baseName}_{index}_root_ctrl' matched on the root
        joint, under CTRL_grp, connected to it. 'No Ctrl' mode: shape on the
        root joint itself.
        """

        base_name, side, index = self.main.get_guide_naming(self.root_joint.guide)

        shape = self.get_string("rootShape", self.LIMB_ROOT_CONTROL_SHAPE)
        size = self.get_float("rootSize", 1.5)
        color = self.get_role_color(self.LIMB_ROOT_CONTROL_COLOR_TYPE)

        if self.no_ctrl():

            self.limb_root_control = self.create_joint_shape(
                self.root_joint.guide, base_name, side, index, self.root_joint.name,
                shape=shape, size=size, color=color
            )

            return self.limb_root_control

        control = ctrl_utilities.Control(
            f"{side}_{base_name}_{index:02d}_{self.LIMB_ROOT_CONTROL_SUFFIX}",
            shape=shape,
            size=size,
            color=color
        )
        control.create()

        cmds.matchTransform(control.name, self.root_joint.name, position=True, rotation=True)

        control.create_offset(parent=self.main.groups.get("controls"), use_group=self.offset_group())

        self.connect_control(control.name, self.root_joint.name)

        self.limb_root_control = control.name

        return self.limb_root_control

    def parent_under_root(self, control):

        """
        Put 'control' under the root ctrl, world position kept:
        - joint ctrl ('No Ctrl'): under the root joint (FK ones already are);
        - offset group: plain reparent;
        - else: relative reparent, world restored, offsetParentMatrix re-baked.
        """

        if not control or not cmds.objExists(control) or not self.limb_root_control:
            return

        if cmds.nodeType(control) == "joint":

            if control in [joint.name for joint in self.fk_joints]:
                return

            joint_utilities.parent_joint(control, self.root_joint.name)

            return

        node = self.get_control_node(control)

        current_parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        target_path = cmds.ls(self.limb_root_control, long=True)[0]

        if current_parent and current_parent[0] == target_path:
            return

        if node != control:
            cmds.parent(node, self.limb_root_control)
            return

        world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)

        cmds.parent(node, self.limb_root_control, relative=True)
        cmds.xform(node, worldSpace=True, matrix=world_matrix)

        ctrl_utilities.Control(node).transfer_offset_parent_matrix()

    # --------------------------------------------------
    # FK (simpleFk)
    # --------------------------------------------------

    def create_fk_step(self):
        """Chained FK ctrls on the FK chain (simpleFk.create_fk_controls)."""

        return FkBuilder.create_fk_controls(
            self,
            self.fk_joints,
            suffix=self.FK_CONTROL_SUFFIX,
            shape=self.get_string("fkShape", self.CONTROL_SHAPE),
            size=self.get_float("fkSize", 1.0),
            color=self.get_role_color(self.CONTROL_COLOR_TYPE)
        )

    # --------------------------------------------------
    # IK (simpleIk)
    # --------------------------------------------------

    def create_ik_step(self):

        """
        IK ctrl on the last IK joint (oriented like it or world aligned,
        ikCtrlOrient), then the pole vector in front of the middle IK joint.
        """

        ik_control = IkBuilder.create_ik_control(
            self,
            self.ik_joints,
            suffix=self.IK_CONTROL_SUFFIX,
            shape=self.get_string("ikShape", self.IK_CONTROL_SHAPE),
            size=self.get_float("ikSize", 1.0),
            match_rotation=self.get_string("ikCtrlOrient", "Joint") == "Joint",
            adjust_shape=False
        )

        pole_control = IkBuilder.create_pole_control(
            self,
            self.ik_joints,
            suffix=self.POLE_CONTROL_SUFFIX,
            shape=self.get_string("poleShape", self.POLE_CONTROL_SHAPE),
            size=self.get_float("poleSize", 1.0)
        )

        return ik_control, pole_control

    # --------------------------------------------------
    # SWITCH
    # --------------------------------------------------

    def create_switch_control(self, parent=None):

        """
        Ctrl holding the IK/FK switch attribute: on the last bind joint (shape
        offset by switchShapeOffset), under 'parent' (else CTRL_grp), follows
        it (ParentCnstrMtx). Channels locked.
        """

        end_joint = self.bind_joints[-1]

        control = ctrl_utilities.Control(
            self.control_name_for(end_joint, self.SWITCH_CONTROL_SUFFIX),
            shape=self.SWITCH_CONTROL_SHAPE,
            size=self.get_float("switchSize", 0.5),
            color=self.get_role_color(self.SWITCH_CONTROL_COLOR_TYPE)
        )
        control.create()

        offset = self.get_vector_attribute("switchShapeOffset", default=(0.0, 0.0, 0.0))

        if tuple(offset) != (0.0, 0.0, 0.0):
            control.translate_shape(offset)

        cmds.matchTransform(control.name, end_joint.name, position=True, rotation=True)

        target_parent = parent if parent and cmds.objExists(parent) else self.main.groups.get("controls")

        control.create_offset(parent=target_parent)

        cnstrMtx_utilities.ParentCnstrMtx(control.name, end_joint.name, dcmpMtx=False)

        for attr in ("translate", "rotate", "scale"):
            for axis in "XYZ":
                cmds.setAttr(f"{control.name}.{attr}{axis}", lock=True, keyable=False, channelBox=False)

        self.switch_control = control.name

        return self.switch_control

    def control_name_for(self, joint, suffix):
        """Name '{side}_{baseName}_{index}_{suffix}' of a ctrl built on 'joint' (Joint)."""

        base_name, side, index = self.main.get_guide_naming(joint.guide)

        return f"{side}_{base_name}_{index:02d}_{suffix}"

    # ======================================================
    # SETUP
    # ======================================================

    def create_setup(self):

        """IK ikHandle, FK setup (no node), ribbon setup. Returns the setup nodes."""

        setups = self.create_ik_setup() + FkBuilder.create_setup(self)

        # Ribbon: sk joints -> follicles, level ctrls on the surface below.
        if self.use_ribbon() and self.nurb:
            setups.extend(ribbonBuilder.create_setup(self))

        return setups

    def connect_setup(self):

        """
        IK connections (ikHandle, end joint orientation, pole, stretch), FK
        (nothing), IK/FK switch of the bind chain, then the ribbon skins and
        follicle scale (ribbon.connect_setup).
        """

        self.connect_ik_setup()
        FkBuilder.connect_setup(self)

        self.create_ik_fk_switch()

        if self.use_ribbon() and self.nurb:
            ribbonBuilder.connect_setup(self)

    def create_ik_setup(self):
        """IK chain ikHandle(s) (simpleIk.create_setup). Overridden by legQuadruped."""

        return IkBuilder.create_setup(self, self.ik_joints)

    def connect_ik_setup(self):
        """IK ctrl, pole, end joint orientation and stretch (simpleIk.connect_setup)."""

        IkBuilder.connect_setup(self, self.ik_joints)

    # ======================================================
    # IK / FK SWITCH
    # ======================================================

    def create_ik_fk_switch(self, attr_name=None, default=None):

        """
        Per bind joint, a blend SpaceSwitch between its FK and IK joints into
        its offsetParentMatrix. All share one 0 (FK) -> 1 (IK) float on the
        attributes host (else the switch ctrl). No maintain offset: the 3
        chains are identical.

        attr_name : switch attribute (SWITCH_ATTR by default).
        default   : 0 = FK, 1 = IK (module ikFkDefault by default).
        """

        attr_name = attr_name or self.SWITCH_ATTR

        if default is None:
            default = 1 if self.get_string("ikFkDefault", "FK") == "IK" else 0

        host = self.get_attributes_host(default=self.switch_control)

        if not host or not cmds.objExists(host):
            cmds.warning("Limb : aucun ctrl pour porter le switch IK/FK.")
            return []

        self.ik_fk_switches = []

        for bind, fk, ik in zip(self.bind_joints, self.fk_joints, self.ik_joints):

            switch = switchSpace_utilities.SpaceSwitch(
                target=bind.name,
                spaces=[("FK", fk.name), ("IK", ik.name)],
                default=default,
                attr_name=attr_name,
                attr_host=host,
                mo=False,
                blend=True
            )

            self.ik_fk_switches.append(switch)

        if self.ik_fk_switches:
            self.ik_fk_plug = f"{host}.{attr_name}"
            self.connect_ik_fk_visibility(self.ik_fk_plug)

        return self.ik_fk_switches

    def connect_ik_fk_visibility(self, switch_plug):

        """Ctrl visibility from the switch: FK while < 1, IK + pole while > 0 (both during a blend)."""

        prefix = switch_plug.split(".")[0]

        fk_condition = cmds.createNode("condition", name=f"{prefix}_{self.SWITCH_ATTR}_fkVis_cond")
        cmds.setAttr(f"{fk_condition}.operation", 4)  # less than
        cmds.setAttr(f"{fk_condition}.secondTerm", 1.0)

        ik_condition = cmds.createNode("condition", name=f"{prefix}_{self.SWITCH_ATTR}_ikVis_cond")
        cmds.setAttr(f"{ik_condition}.operation", 2)  # greater than
        cmds.setAttr(f"{ik_condition}.secondTerm", 0.0)

        for condition in (fk_condition, ik_condition):
            cmds.setAttr(f"{condition}.colorIfTrueR", 1)
            cmds.setAttr(f"{condition}.colorIfFalseR", 0)
            cmds.connectAttr(switch_plug, f"{condition}.firstTerm", force=True)

        for control in self.fk_controls:
            self.connect_visibility(control, f"{fk_condition}.outColorR")

        for control in (self.ik_control, self.pole_control):
            self.connect_visibility(control, f"{ik_condition}.outColorR")

    def connect_visibility(self, control, plug):

        """Connect 'plug' to the visibility of the ctrl offset group (else the ctrl), unless locked / connected."""

        if not control or not cmds.objExists(control):
            return

        offset = self.main.get_offset_group(control)
        node = offset if offset and cmds.objExists(offset) else control

        attr = f"{node}.visibility"

        if cmds.getAttr(attr, lock=True) or cmds.listConnections(attr, source=True, destination=False):
            return

        cmds.connectAttr(plug, attr, force=True)

    # ======================================================
    # SPACE SWITCH
    # ======================================================

    def create_space_switches(self):

        """Space switches of the FK root, IK ctrl and pole (spaceSwitchTargets / ik / pole)."""

        if self.fk_controls:
            self.create_space_switch(self.fk_controls[0])

        super().create_space_switches()
