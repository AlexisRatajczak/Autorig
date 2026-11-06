# ====================================================================================================================
# FOOT BUILDER
# ====================================================================================================================
#
#   Reverse foot (ankle -> ball -> [phalanges] -> tip) driven by pivots and their ROTATION LIMITS (no condition node):
#   each pivot gets the whole roll value and only keeps its own range (heel: back roll, ball: 0 -> ballAngle,
#   each phalanx: the next phalanxAngle range...). Any phalanx count: loops over the roll joints.
#
#   JOINTS (3 chains, same placement, one joint per guide: ankle, ball, phalanges..., tip)
#       main  {side}_{name}_{i}_jnt    - self.joints, skin, joints[0] parented by MainBuild (on the leg ankle joint
#                                        when the foot guide is under it); receives the switch: each joint (but the
#                                        tip) blends its FK joint (0) / IK joint (1)
#       IK    {side}_{name}_{i}_ik_jnt - self.ik_joints, reverse foot + roll (each on its reverse ctrl)
#       FK    {side}_{name}_{i}_fk_jnt - self.fk_joints, FK ctrls
#       IK / FK roots under the main root parent
#   CONTROLS
#       foot ctrl                   - attached leg: its IK ctrl ({leg}_ik_ctrl / {leg}_ctrl), no ctrl created;
#                                     else '{prefix}_ctrl' on the ankle (controls[0])
#       roll ctrl  {prefix}_roll_ctrl - under the foot ctrl, behind the heel, translate only (Y locked):
#                                     translateZ -> foot roll, translateX -> bank (* rollFactor degrees / unit);
#                                     holds rollFactor, ballAngle, ballMult, tiptoeMult (+ phalanxAngle)
#       pivot ctrls                 - '{prefix}_{pivot}_ctrl' on every pivot but the ankle ('pivotControls'), each
#                                     under its pivot, parent of the next pivots: free rotation added to the roll
#                                     (translate / scale locked)
#       reverse ctrls               - '{side}_{name}_{i}_ik_ctrl', one per segment (every joint but the tip), under
#                                     the pivot space carrying it (get_segment_space): drive the IK chain
#       FK ctrls                    - '{side}_{name}_{i}_fk_ctrl', chained, one per FK joint (simpleFk); root under
#                                     the foot ctrl (alone) or the leg last FK ctrl {leg}_fk_ctrl (attached)
#       switch                      - 'ikFk' (0 = FK, 1 = IK): the leg one when attached (else on the leg IK ctrl),
#                                     on the foot ctrl alone; drives the main chain blend (+ FK / IK visibility)
#   PIVOTS ({prefix}_{name}_piv, oriented on the foot: Z forward on the ground, Y up, X side)
#       heel / tiptoe / bankL / bankR on their pivot guides {module}_*_PIVOT (Guides.PIVOT_GUIDES), roll pivots
#       on their joints (ball, phalanx01...)
#       ankle > heel > tiptoe > bankR > bankL > phalanxN > ... > phalanx01 > ball
#           heel       rotateX = roll                                  limit max 0
#           tiptoe     rotateX = (roll - start_tip) * tiptoeMult        limit min 0
#           bankR / L  rotateZ = bank                                  limit on its edge side
#           phalanx p  rotateX = roll - start_p                        limit 0 -> phalanxAngle
#           ball       rotateX = roll * ballMult                       limit 0 -> ballAngle (plug)
#       segment j (joints[j]) : reverse ctrl in the roll pivot of joints[j + 1] (last segment: bankL); ball space
#                               also holds '{prefix}_ankle_target' (leg ikHandle)
#   LEG ('attachToLeg', root guide under a guide of an IK module: simpleIk / limb / arm / legBiped)
#       the leg IK ctrl is the foot ctrl, the leg ikHandle follows the ankle target (its constraint to the IK ctrl
#       replaced), the leg stretch / lock distances read it; THEN the foot switch (leg IK/FK plug).
#
#   Builder
#       DATA        get_float, prefix, get_leg, get_leg_prefix, get_foot_frame, get_roll_names, get_segment_space,
#                   get_pivot_position
#       JOINTS      build_joints
#       CONTROLS    create_controls, get_foot_control, get_module_root_control
#       SETUP       create_setup, create_pivots, use_pivot_controls, create_pivot_control, create_roll_control,
#                   create_ik_controls, parent_chain_root, create_ik_chain, create_fk_chain, get_fk_root_parent,
#                   get_control_node, parent_control_node,
#                   create_attributes, connect_pivots
#       LEG         create_space_switches, attach_leg, connect_foot_switch, connect_foot_joints,
#                   connect_switch_visibility
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from ..simpleBase.builder import Builder as BaseBuilder
from ..simpleIk.builder import Builder as SimpleIkBuilder
from ..simpleFk.builder import Builder as FkBuilder
from ....utilities import joint_utilities
from ....utilities import ctrl_utilities
from ....utilities import cnstr_utilities
from ....utilities import transform_utilities
from ....utilities import switchSpace_utilities
from ....utilities import attribute_utilities

from importlib import reload

reload(joint_utilities)
reload(ctrl_utilities)
reload(cnstr_utilities)
reload(transform_utilities)
reload(switchSpace_utilities)
reload(attribute_utilities)


class Builder(BaseBuilder):

    CONTROL_SHAPE = "cube"
    CONTROL_COLOR_TYPE = "IK Main"

    # Joint labels: ankle Other (the leg ankle is the 'Foot'), ball 'Toe', phalanges / tip Other.
    JOINT_TYPES = (None, "Toe")

    # Fixed pivots, parent first: (name, parent). The roll pivots (ball, phalanges) follow under bankL (get_roll_names).
    PIVOTS = (
        ("ankle", None),
        ("heel", "ankle"),
        ("tiptoe", "heel"),
        ("bankR", "tiptoe"),
        ("bankL", "bankR"),
    )

    # Pivot -> its pivot guide (data node message, Guides.PIVOT_GUIDES).
    PIVOT_GUIDES = {"heel": "heelGuide", "tiptoe": "tiptoeGuide", "bankL": "bankLGuide", "bankR": "bankRGuide"}

    # Pivot ctrls ('pivotControls'): pivot -> (shape, size factor of pivotCtrlSize); roll pivots: ROLL_PIVOT_CONTROL.
    PIVOT_CONTROLS = {
        "heel": ("sphere", 0.6),
        "tiptoe": ("sphere", 0.6),
        "bankL": ("diamond", 0.5),
        "bankR": ("diamond", 0.5),
    }
    ROLL_PIVOT_CONTROL = ("circle", 1.0)
    PIVOT_CONTROL_COLOR_TYPE = "IK Secondary"

    ROLL_CONTROL_SHAPE = "square"

    IK_CONTROL_COLOR_TYPE = "IK Secondary"
    FK_CONTROL_COLOR_TYPE = "FK Main"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.foot_control = None
        self.roll_control = None
        self.pivots = {}

        # Pivot ctrls, and the node each pivot's children go under (its ctrl, else the pivot).
        self.pivot_controls = {}
        self.pivot_spaces = {}

        # Reverse foot ctrls (IK side), one per foot segment (every joint but the tip).
        self.ik_controls = []

        # IK chain ({..}_ik_jnt, driven by the reverse ctrls), FK chain ({..}_fk_jnt) and its chained ctrls ({..}_fk_ctrl).
        self.ik_joints = []
        self.fk_joints = []
        self.fk_controls = []

        # IK/FK switch plug (0 = FK, 1 = IK): the leg one when attached, else the foot one.
        self.switch_plug = None

        self.ankle_target = None

        # Builder of the attached leg (get_leg), or None.
        self.leg = None

    # ======================================================
    # DATA
    # ======================================================

    def get_float(self, key, default):
        """Float / int module attribute, or 'default'."""

        try:
            return float(self.data.get(key))
        except (TypeError, ValueError):
            return default

    @property
    def prefix(self):
        """{side}_{baseName}_{index:02d}, from the root guide."""

        base_name, side, index = self.main.get_guide_naming(self.get_root_guide())

        return f"{side}_{base_name}_{index:02d}"

    def get_leg(self):

        """
        Builder of the leg the foot is attached to ('attachToLeg', on by default): the
        module owning the parent guide, if it is an IK module (simpleIk / limb: it has
        ik_control / ik_handle, filled during its passes). None otherwise. Read on the
        builder, not in the scene: the leg nodes may not be built yet.
        """

        value = self.data.get("attachToLeg")

        if value is not None and not value:
            return None

        parent = self.data.get("parent")
        parent = parent[0] if isinstance(parent, (list, tuple)) and parent else parent

        if not parent:
            return None

        parent = parent.split("|")[-1]

        for builder in self.main.builders.values():

            if builder is self or not (hasattr(builder, "ik_control") and hasattr(builder, "ik_handle")):
                continue

            guides = [guide.split("|")[-1] for guide in (builder.data.get("guides") or {})]

            if parent in guides:
                return builder

        return None

    def get_leg_end_joint(self):
        """Last joint of the attached leg IK chain (limb ik_joints, else simpleIk joints), or None."""

        if not self.leg:
            return None

        chain = getattr(self.leg, "ik_joints", None) or getattr(self.leg, "joints", None) or []

        name = getattr(chain[-1], "name", chain[-1]) if chain else None

        return name if name and cmds.objExists(name) else None

    def get_leg_prefix(self):
        """'{side}_{baseName}_{index:02d}' of the leg end guide (its stretch / lock node names), or None."""

        guides = list((self.leg.data.get("guides") or {}).keys()) if self.leg else []

        if not guides:
            return None

        base_name, side, index = self.main.get_guide_naming(guides[-1])

        return f"{side}_{base_name}_{index:02d}"

    def get_foot_frame(self):

        """
        Foot axes (MVectors): Z forward (ankle -> tip on the ground plane), Y world up,
        X = Y ^ Z (side). Forward falls back on world Z.
        """

        ankle, tip = [om.MVector(cmds.xform(joint.name, query=True, worldSpace=True, translation=True)) for joint in (self.joints[0], self.joints[-1])]

        forward = tip - ankle
        forward.y = 0.0

        forward = forward.normal() if forward.length() > 1e-6 else om.MVector(0, 0, 1)
        up = om.MVector(0, 1, 0)

        return (up ^ forward).normal(), up, forward

    def get_roll_names(self):

        """
        Roll pivot names, one per roll joint (joints[1:-1]: ball, then each phalanx),
        ball first: 'ball', 'phalanx01', 'phalanx02'...
        """

        count = max(0, len(self.joints) - 2)

        return ["ball"] + [f"phalanx{index:02d}" for index in range(1, count)] if count else []

    def get_segment_space(self, index):

        """
        Pivot space carrying the foot segment of joints[index] (index < tip): the roll
        pivot on the NEXT joint (segment j turns with the rolls past it: roll index j),
        bankL for the last segment (only tiptoe / banks / heel past it).
        """

        rolls = self.get_roll_names()

        return self.pivot_spaces[rolls[index]] if index < len(rolls) else self.pivot_spaces["bankL"]

    def get_pivot_position(self, pivot, default):
        """World position of the pivot guide of 'pivot' (PIVOT_GUIDES), else 'default' (MVector) with a warning."""

        guide = self.get_message(self.PIVOT_GUIDES[pivot])

        if guide:
            return om.MVector(cmds.xform(guide, query=True, worldSpace=True, translation=True))

        cmds.warning(f"Foot '{self.prefix}' : guide de pivot '{pivot}' introuvable, position par défaut.")

        return default

    # ======================================================
    # JOINTS
    # ======================================================

    def build_joints(self, suffix="jnt"):

        """
        3 chains, same placement:

            main '{..}_{suffix}' : self.joints, skin, receives the switch (FK / IK blend);
            IK   '{..}_ik_jnt'   : self.ik_joints, reverse foot + roll (create_ik_chain);
            FK   '{..}_fk_jnt'   : self.fk_joints, FK ctrls (create_fk_chain).

        The IK / FK chains are out of self.joints: their roots are parented in the setup
        pass, once MainBuild has parented the main root.
        """

        super().build_joints(suffix=suffix)

        self.ik_joints = self.create_joints(suffix="ik_jnt")
        self.fk_joints = self.create_joints(suffix="fk_jnt")

        return self.joints

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        Attached leg: no ctrl (the leg IK ctrl is the foot ctrl). Else '{prefix}_ctrl'
        on the ankle, oriented on the foot (controls[0]). The roll, pivot and FK ctrls
        need the pivots: create_setup.
        """

        if len(self.joints) < 3:
            cmds.warning(f"Foot '{self.prefix}' : 3 guides nécessaires (cheville, ball, pointe).")
            return []

        self.leg = self.get_leg()

        # Attached: the leg IK ctrl, read in create_setup (every ctrl exists by then).
        if self.leg:
            return []

        x_axis, y_axis, z_axis = self.get_foot_frame()
        ankle = cmds.xform(self.joints[0].name, query=True, worldSpace=True, translation=True)

        control = ctrl_utilities.Control(
            f"{self.prefix}_ctrl",
            shape=self.data.get("footShape") or self.CONTROL_SHAPE,
            size=self.get_float("footSize", 1.0),
            color=self.get_control_color()
        )
        control.create()

        self.adjust_control_shape(control)

        cmds.xform(control.name, worldSpace=True, matrix=transform_utilities.build_matrix(x_axis, y_axis, z_axis, ankle))

        control.create_offset(parent=self.get_controls_group(), use_group=self.offset_group())

        self.foot_control = control.name

        return [self.foot_control]

    def get_foot_control(self):
        """Foot ctrl: attached leg IK ctrl, else own ctrl (create_controls). None if missing."""

        if self.leg:
            self.foot_control = getattr(self.leg, "ik_control", None)

        return self.foot_control if self.foot_control and cmds.objExists(self.foot_control) else None

    def get_module_root_control(self):
        """Alone: the foot ctrl. Attached: None, the foot ctrls stay under the leg IK ctrl."""

        return None if self.leg else self.foot_control

    # ======================================================
    # SETUP
    # ======================================================

    def create_setup(self):

        """
        Pivots (+ pivot ctrls) under the foot ctrl, roll ctrl, reverse ctrls on the
        pivots, FK chain + ctrls (create_fk_chain), ankle target, attribute network.
        Alone: own 'ikFk' switch on the foot ctrl, bind joints blended FK / IK
        (attached: attach_leg, AFTER the leg ikHandle is reattached). Returns the setup nodes.
        """

        if len(self.joints) < 3:
            return []

        if not self.get_foot_control():
            cmds.warning(f"Foot '{self.prefix}' : pas de ctrl de pied (ctrl IK de la jambe introuvable), pied ignoré.")
            return []

        self.create_pivots()
        self.create_roll_control()
        self.create_ik_controls()
        self.create_ik_chain()
        self.create_fk_chain()

        # Module ctrls (sets), after the foot ctrl (controls[0] stays the foot ctrl when alone).
        self.controls.extend([self.roll_control] + list(self.pivot_controls.values()) + self.ik_controls + self.fk_controls)

        # Ankle target on the ball space, on the leg IK end (else the foot ankle). Attached: it becomes
        # the leg IK target BEFORE the connect pass: the leg ikHandle constraint, stretch / lock distances,
        # quadruped straighten activation and secondary / pole blends are all built on it.
        self.ankle_target = cmds.group(empty=True, name=f"{self.prefix}_ankle_target", parent=self.pivot_spaces["ball"])

        leg_end = self.get_leg_end_joint()
        position_node = leg_end if leg_end else self.joints[0].name

        cmds.xform(self.ankle_target, worldSpace=True, translation=cmds.xform(position_node, query=True, worldSpace=True, translation=True))

        if self.leg and hasattr(self.leg, "get_ik_target"):
            self.leg.ik_target = self.ankle_target

        if not self.leg:
            # Switch on the foot ctrl (always visible), not on the roll ctrl (hidden in FK).
            host = self.get_attributes_host(default=self.foot_control)

            self.switch_plug = self.add_switch_attribute(host)

            self.connect_foot_joints(self.switch_plug)
            self.connect_switch_visibility(self.switch_plug)

        self.connect_pivots(self.create_attributes())

        return [self.ankle_target]

    def create_pivots(self):

        """
        Pivot locators '{prefix}_{name}_piv' (root under the foot ctrl, locator shapes
        hidden), oriented on the foot frame (rotations / limits on its axes):

            ankle                         : ankle joint
            heel / tiptoe / bankL / bankR : their pivot guides (heelGuide...), else
                                            the ankle / tip / ball joint
            ball, phalanx01...            : one roll pivot per roll joint (loop over
                                            get_roll_names), chained in reverse under
                                            bankL: last phalanx > ... > ball

        With 'pivotControls', a ctrl under each pivot but the ankle
        (create_pivot_control), parent of the next pivots: the roll drives the
        pivot (limits), the ctrl adds its free rotation on top.
        """

        x_axis, y_axis, z_axis = self.get_foot_frame()

        joint_positions = [om.MVector(cmds.xform(joint.name, query=True, worldSpace=True, translation=True)) for joint in self.joints]

        ankle, ball, tip = joint_positions[0], joint_positions[1], joint_positions[-1]

        positions = {
            "ankle": ankle,
            "heel": self.get_pivot_position("heel", ankle),
            "tiptoe": self.get_pivot_position("tiptoe", tip),
            "bankR": self.get_pivot_position("bankR", ball),
            "bankL": self.get_pivot_position("bankL", ball),
        }

        # Roll pivots on their joints, chained in reverse: last phalanx under bankL ... ball innermost.
        rolls = self.get_roll_names()
        layout = list(self.PIVOTS)

        for index in reversed(range(len(rolls))):

            positions[rolls[index]] = joint_positions[index + 1]
            layout.append((rolls[index], rolls[index + 1] if index + 1 < len(rolls) else "bankL"))

        self.pivots = {}
        self.pivot_controls = {}
        self.pivot_spaces = {}

        use_controls = self.use_pivot_controls()

        for name, parent in layout:

            pivot = transform_utilities.create_pivot(
                f"{self.prefix}_{name}_piv",
                transform_utilities.build_matrix(x_axis, y_axis, z_axis, positions[name]),
                parent=self.pivot_spaces[parent] if parent else self.foot_control
            )

            # Locator shape hidden only: the ctrls under it stay visible.
            for shape in cmds.listRelatives(pivot, shapes=True, fullPath=True) or []:
                cmds.setAttr(f"{shape}.visibility", 0)

            self.pivots[name] = pivot
            self.pivot_spaces[name] = pivot

            if use_controls and (name in self.PIVOT_CONTROLS or name in rolls):
                self.pivot_controls[name] = self.create_pivot_control(name, pivot)
                self.pivot_spaces[name] = self.pivot_controls[name]

        return self.pivots

    def use_pivot_controls(self):
        """'Pivot Controls' option (on by default): a ctrl on the heel, tiptoe, bank and roll (ball, phalanges) pivots."""

        value = self.data.get("pivotControls")

        return True if value is None else bool(value)

    def create_pivot_control(self, name, pivot):

        """
        Ctrl '{prefix}_{name}_ctrl' (PIVOT_CONTROLS shape, pivotCtrlSize) matched on
        'pivot', under it, offset baked in its offsetParentMatrix. Rotation only:
        translate / scale locked. Returns its name.
        """

        shape, factor = self.PIVOT_CONTROLS.get(name, self.ROLL_PIVOT_CONTROL)

        control = ctrl_utilities.Control(
            f"{self.prefix}_{name}_ctrl",
            shape=shape,
            size=self.get_float("pivotCtrlSize", 1.0) * factor,
            color=self.main.get_color(self.data.get("side"), self.PIVOT_CONTROL_COLOR_TYPE)
        )
        control.create()

        cmds.matchTransform(control.name, pivot, position=True, rotation=True)

        control.create_offset(parent=pivot, use_group=False)

        for attr in ("translate", "scale"):
            for axis in "XYZ":
                cmds.setAttr(f"{control.name}.{attr}{axis}", lock=True, keyable=False, channelBox=False)

        return control.name

    def create_roll_control(self):

        """
        Roll ctrl '{prefix}_roll_ctrl' under the foot ctrl (outside the pivots: no
        cycle), behind the heel pivot by rollCtrlOffset, oriented on the foot. Only
        translateX (bank) / translateZ (roll) free. Returns its name.
        """

        x_axis, y_axis, z_axis = self.get_foot_frame()

        heel = om.MVector(cmds.xform(self.pivots["heel"], query=True, worldSpace=True, translation=True))
        position = heel - z_axis * self.get_float("rollCtrlOffset", 2.0)

        control = ctrl_utilities.Control(
            f"{self.prefix}_roll_ctrl",
            shape=self.ROLL_CONTROL_SHAPE,
            size=self.get_float("pivotCtrlSize", 1.0) * 0.5,
            color=self.main.get_color(self.data.get("side"), self.PIVOT_CONTROL_COLOR_TYPE)
        )
        control.create()

        cmds.xform(control.name, worldSpace=True, matrix=transform_utilities.build_matrix(x_axis, y_axis, z_axis, position))

        control.create_offset(parent=self.foot_control, use_group=False)

        for attr, axes in (("translate", "Y"), ("rotate", "XYZ"), ("scale", "XYZ")):
            for axis in axes:
                cmds.setAttr(f"{control.name}.{attr}{axis}", lock=True, keyable=False, channelBox=False)

        self.roll_control = control.name

        return self.roll_control

    def create_ik_controls(self):

        """
        Reverse foot level on the pivots: one ctrl '{side}_{name}_{i}_ik_ctrl' per foot segment
        (every joint but the tip, loop), matched on its joint, under the pivot space
        carrying it (get_segment_space: ankle -> ball roll, ball -> phalanx01 roll...,
        last -> bankL), offset baked. The joints follow them (connect_foot_joints).
        Returns the ctrls.
        """

        self.ik_controls = []

        for index, joint in enumerate(self.joints[:-1]):

            base_name, side, guide_index = self.main.get_guide_naming(joint.guide)

            control = ctrl_utilities.Control(
                f"{side}_{base_name}_{guide_index:02d}_ik_ctrl",
                shape="circle",
                size=self.get_float("fkCtrlSize", 1.0),
                color=self.main.get_color(self.data.get("side"), self.IK_CONTROL_COLOR_TYPE)
            )
            control.create()

            cmds.matchTransform(control.name, joint.name, position=True, rotation=True)

            control.create_offset(parent=self.get_segment_space(index), use_group=self.offset_group())

            self.ik_controls.append(control.name)

        return self.ik_controls

    def parent_chain_root(self, chain):
        """Root of 'chain' (IK / FK) under the main root parent (leg ankle when attached), world pose kept."""

        parent = cmds.listRelatives(self.joints[0].name, parent=True, fullPath=True)

        if chain and parent:
            joint_utilities.parent_joint(chain[0], parent[0])

    def create_ik_chain(self):

        """
        IK chain: root under the main root parent, each joint (but the tip, it follows
        its parent) parent constrained to its reverse foot ctrl (constrain, no offset:
        matched at build). Carries the reverse foot and the roll. Returns the IK joints.
        """

        if len(self.ik_joints) != len(self.joints):
            self.ik_joints = []
            return []

        self.parent_chain_root(self.ik_joints)

        for joint, control in zip(self.ik_joints[:-1], self.ik_controls):
            self.constrain("parent", joint.name, control, mo=False, dcmpMtx=False)

        return self.ik_joints

    def create_fk_chain(self):

        """
        FK chain, built once every ctrl exists (setup pass):

            joints : FK root under the bind root parent (leg ankle when attached),
                     world pose kept (joint_utilities.parent_joint);
            ctrls  : one chained '{..}_fk_ctrl' per FK joint (simpleFk.create_fk_controls),
                     each driving its FK joint;
            root   : alone, under the foot ctrl; attached, under the leg last FK ctrl
                     ('{leg}_fk_ctrl': the foot continues the leg FK chain and its
                     visibility), else under the leg IK ctrl parent. Plain parent,
                     world pose kept: no constraint offset.

        Returns the FK ctrls.
        """

        self.fk_controls = []

        if len(self.fk_joints) != len(self.joints):
            return []

        self.parent_chain_root(self.fk_joints)

        self.fk_controls = FkBuilder.create_fk_controls(
            self,
            self.fk_joints,
            suffix="fk_ctrl",
            shape="circle",
            size=self.get_float("fkCtrlSize", 1.0),
            color=self.main.get_color(self.data.get("side"), self.FK_CONTROL_COLOR_TYPE),
            adjust_shape=False
        )

        if not self.fk_controls:
            return []

        target = self.get_fk_root_parent()

        if target:
            self.parent_control_node(self.fk_controls[0], target)

        return self.fk_controls

    def get_fk_root_parent(self):

        """
        Parent of the FK root ctrl: alone, the foot ctrl; attached, the leg last FK ctrl
        '{leg}_fk_ctrl' (limb), else the DAG parent of the leg IK ctrl (CTRL_grp, leg root
        ctrl...). None if nothing fits.
        """

        if not self.leg:
            return self.foot_control

        leg_prefix = self.get_leg_prefix()
        leg_fk = f"{leg_prefix}_fk_ctrl" if leg_prefix else None

        if leg_fk and cmds.objExists(leg_fk):
            return leg_fk

        node = self.get_control_node(self.foot_control)
        parent = cmds.listRelatives(node, parent=True, fullPath=True)

        return parent[0] if parent else None

    def get_control_node(self, control):
        """Offset group of a ctrl if it exists, else the ctrl."""

        offset = self.main.get_offset_group(control)

        return offset if offset and cmds.objExists(offset) else control

    def parent_control_node(self, control, parent):
        """Put the ctrl (its offset group if any) under 'parent', world pose kept, offsetParentMatrix re-baked."""

        node = self.get_control_node(control)

        if node != control:
            cmds.parent(node, parent)
            return

        world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)

        cmds.parent(node, parent, relative=True)
        cmds.xform(node, worldSpace=True, matrix=world_matrix)

        ctrl_utilities.Control(node).transfer_offset_parent_matrix()

    def create_attributes(self):

        """
        FOOT ROLL section on the attributes host (roll ctrl by default): rollFactor (degrees
        per translate unit), ballAngle (ball roll limit), ballMult, tiptoeMult (+ phalanxAngle
        with phalanges). Returns the host.
        """

        host = self.get_attributes_host(default=self.roll_control)

        attributes = [
            {"name": "rollFactor", "default": self.get_float("rollFactor", 10.0), "minimum": 0.0},
            {"name": "ballAngle", "default": self.get_float("ballAngle", 30.0), "minimum": 0.0},
            {"name": "ballMult", "default": 1.0, "minimum": 0.0},
            {"name": "tiptoeMult", "default": 1.0, "minimum": 0.0},
        ]

        # One roll range per phalanx (none without phalanx).
        if len(self.get_roll_names()) > 1:
            attributes.append({"name": "phalanxAngle", "default": self.get_float("phalanxAngle", 20.0), "minimum": 0.0})

        attribute_utilities.add_attributes(host, "FOOT ROLL", attributes)

        return host

    def connect_pivots(self, host):

        """
        Roll ctrl translate -> pivot rotations; each pivot keeps its range through its
        rotation limits (transform_utilities.set_rotation_limit), no condition node:

            roll = translateZ * rollFactor     bank = translateX * -rollFactor

            heel        rotateX = roll                         max 0 (ctrl back: heel)
            ball        rotateX = roll * ballMult              0 -> ballAngle
            phalanx p   rotateX = roll - start_p               0 -> phalanxAngle
                        start_p = ballAngle + (p - 1) * phalanxAngle (loop: each
                        phalanx rolls after the previous one)
            tiptoe      rotateX = (roll - start_tip) * tiptoeMult   min 0 (last)
                        start_tip = ballAngle + phalanx count * phalanxAngle
            bank        rotateZ = bank on both bank pivots, each limited to the
                        rotation lifting the opposite edge: the foot rolls onto the
                        edge the ctrl moves to

        Returns the created nodes.
        """

        nodes = []

        def float_math(name, operation, a, b):
            fm = cmds.createNode("floatMath", name=f"{self.prefix}_{name}_fm")
            cmds.setAttr(f"{fm}.operation", operation)
            for attr, value in (("floatA", a), ("floatB", b)):
                if isinstance(value, str):
                    cmds.connectAttr(value, f"{fm}.{attr}")
                else:
                    cmds.setAttr(f"{fm}.{attr}", value)
            nodes.append(fm)
            return f"{fm}.outFloat"

        pivots = self.pivots
        limit = transform_utilities.set_rotation_limit

        roll = float_math("roll", 2, f"{self.roll_control}.translateZ", f"{host}.rollFactor")

        # Roll: heel back, ball then tiptoe forward.
        cmds.connectAttr(roll, f"{pivots['heel']}.rotateX")
        limit(pivots["heel"], "X", maximum=0.0)

        cmds.connectAttr(float_math("ballRoll", 2, roll, f"{host}.ballMult"), f"{pivots['ball']}.rotateX")
        limit(pivots["ball"], "X", minimum=0.0, maximum=f"{host}.ballAngle")

        # Phalanges: each takes over when the previous range is used up.
        start = f"{host}.ballAngle"

        for name in self.get_roll_names()[1:]:

            cmds.connectAttr(float_math(f"{name}Roll", 1, roll, start), f"{pivots[name]}.rotateX")
            limit(pivots[name], "X", minimum=0.0, maximum=f"{host}.phalanxAngle")

            start = float_math(f"{name}End", 0, start, f"{host}.phalanxAngle")

        tiptoe = float_math("tiptoeRoll", 1, roll, start)
        cmds.connectAttr(float_math("tiptoeRollMult", 2, tiptoe, f"{host}.tiptoeMult"), f"{pivots['tiptoe']}.rotateX")
        limit(pivots["tiptoe"], "X", minimum=0.0)

        # Bank: rotateZ < 0 lifts the -X edge (roll onto +X, where the ctrl goes), a pivot on the
        # +X edge keeps the negative side, the -X one the positive side.
        bank_factor = float_math("bankFactor", 2, f"{host}.rollFactor", -1.0)
        bank = float_math("bank", 2, f"{self.roll_control}.translateX", bank_factor)

        x_axis = self.get_foot_frame()[0]
        center = om.MVector(cmds.xform(pivots["ball"], query=True, worldSpace=True, translation=True))

        for name in ("bankR", "bankL"):

            cmds.connectAttr(bank, f"{pivots[name]}.rotateZ")

            edge = (om.MVector(cmds.xform(pivots[name], query=True, worldSpace=True, translation=True)) - center) * x_axis

            if edge < 0:
                limit(pivots[name], "Z", minimum=0.0)
            else:
                limit(pivots[name], "Z", maximum=0.0)

        return nodes

    # ======================================================
    # LEG
    # ======================================================

    def create_space_switches(self):

        """
        Alone: base space switch on the foot ctrl. Attached: none (the leg IK ctrl has
        its own), then the leg attachment (every leg setup is built by now).
        """

        if not self.leg:
            super().create_space_switches()

        elif self.ankle_target:
            self.attach_leg()

    def attach_leg(self):

        """
        Attached leg (every leg node exists by now):

            leg IK target : the ankle target was handed to the leg in create_setup
                            (ik_target): its ikHandle(s), stretch / lock distances,
                            quadruped straighten and blends are already built on it,
                            nothing to rewire;
            fallback      : (leg without ik_target) ikHandle constraint replaced by the
                            ankle target, '{leg}_stretch_db' / '{leg}_lock_down_db'
                            redirected to it;
            foot switch   : LAST (the leg connections above never depend on it): the leg
                            IK/FK plug (limb ik_fk_plug), else an own 'ikFk' on the leg
                            IK ctrl; connect_foot_joints, visibility only when the FK
                            root is not under the leg FK ctrl (its visibility covers it).
        """

        ik_handle = getattr(self.leg, "ik_handle", None)
        ik_control = self.foot_control

        if getattr(self.leg, "ik_target", None) == self.ankle_target:
            self.connect_foot_switch()
            return

        if not ik_handle or not cmds.objExists(ik_handle):
            cmds.warning(f"Foot '{self.prefix}' : ikHandle de la jambe introuvable, jambe non attachée.")
            self.connect_foot_switch()
            return

        position = cmds.xform(ik_handle, query=True, worldSpace=True, translation=True)

        cmds.xform(self.ankle_target, worldSpace=True, translation=position)

        cnstr_utilities.remove_constraints(ik_handle)
        cmds.xform(ik_handle, worldSpace=True, translation=position)

        self.constrain("point", ik_handle, self.ankle_target, mo=False, dcmpMtx=False)

        leg_prefix = self.get_leg_prefix()

        for name in ("stretch_db", "lock_down_db"):

            distance = f"{leg_prefix}_{name}"

            if not leg_prefix or not cmds.objExists(distance):
                continue

            source = cmds.listConnections(f"{distance}.inMatrix2", source=True, destination=False) or []

            if source and source[0] == ik_control:
                cmds.connectAttr(f"{self.ankle_target}.worldMatrix[0]", f"{distance}.inMatrix2", force=True)

        self.connect_foot_switch()

    def connect_foot_switch(self):

        """
        Attached foot switch: the leg IK/FK plug (limb ik_fk_plug), else an own 'ikFk'
        on the leg IK ctrl; bind joints blended FK / IK (connect_foot_joints); FK / IK
        visibility only if the FK root is not under the leg FK ctrl.
        """

        self.switch_plug = getattr(self.leg, "ik_fk_plug", None)

        if not self.switch_plug or not cmds.objExists(self.switch_plug):
            self.switch_plug = self.add_switch_attribute(self.foot_control)

        self.connect_foot_joints(self.switch_plug)

        leg_prefix = self.get_leg_prefix()

        if not (leg_prefix and self.get_fk_root_parent() == f"{leg_prefix}_fk_ctrl"):
            self.connect_switch_visibility(self.switch_plug)

    @staticmethod
    def add_switch_attribute(host):
        """IK FK section on 'host': 'ikFk' (0 = FK, 1 = IK, default IK). Returns its plug."""

        return attribute_utilities.add_attributes(host, "IK FK", [
            {"name": "ikFk", "default": 1.0, "minimum": 0.0, "maximum": 1.0},
        ])["ikFk"]

    def connect_foot_joints(self, switch=None):

        """
        Main chain: each joint (but the tip, it follows its parent) blends between its
        FK joint ("FK", switch 0) and its IK joint ("IK", switch 1): blend SpaceSwitch
        into its offsetParentMatrix, maintain offset (identity: the 3 chains are
        matched at build). No switch or no FK chain: parent constraint on the IK joint.
        """

        fk_joints = self.fk_joints if len(self.fk_joints) == len(self.joints) else []

        for index, (joint, ik_joint) in enumerate(zip(self.joints[:-1], self.ik_joints)):

            joint = joint.name

            if not switch or not cmds.objExists(switch) or not fk_joints:
                self.constrain("parent", joint, ik_joint.name, mo=False, dcmpMtx=False)
                continue

            host, attr = switch.split(".", 1)

            switchSpace_utilities.SpaceSwitch(
                target=joint,
                spaces=[("FK", fk_joints[index].name), ("IK", ik_joint.name)],
                default=cmds.getAttr(switch),
                attr_name=attr,
                attr_host=host,
                mo=True,
                blend=True
            )

    def connect_switch_visibility(self, switch):

        """
        Ctrl visibility from 'switch': FK root ctrl while < 1, reverse foot (pivots and
        their ctrls, roll ctrl) while > 0 (both during a blend). Locked / connected
        visibility skipped.
        """

        def condition(name, operation, value):
            node = cmds.createNode("condition", name=f"{self.prefix}_{name}_cond")
            cmds.setAttr(f"{node}.operation", operation)
            cmds.setAttr(f"{node}.secondTerm", value)
            cmds.setAttr(f"{node}.colorIfTrueR", 1)
            cmds.setAttr(f"{node}.colorIfFalseR", 0)
            cmds.connectAttr(switch, f"{node}.firstTerm")
            return f"{node}.outColorR"

        fk_visibility = condition("fkVis", 4, 1.0)  # less than
        ik_visibility = condition("ikVis", 2, 0.0)  # greater than

        targets = [(self.get_control_node(self.fk_controls[0]), fk_visibility)] if self.fk_controls else []
        targets += [(node, ik_visibility) for node in (self.pivots.get("ankle"), self.roll_control) if node]

        for node, plug in targets:

            attr = f"{node}.visibility"

            if cmds.getAttr(attr, lock=True) or cmds.listConnections(attr, source=True, destination=False):
                continue

            cmds.connectAttr(plug, attr, force=True)
