# ====================================================================================================================
# LEG QUADRUPED BUILDER
# ====================================================================================================================
#
#   4 joint limb: hip (0) -> knee (1) -> hock (2) -> foot (3). Everything comes from limb (FK, IK/FK switch,
#   root, ribbon) except the IK, rebuilt as two ikHandles from 'quadrupedIkMethod':
#
#       SC_RP : SC 0 -> 1 driven by the knee ctrl, then RP 1 -> 3 driven by the IK ctrl, pole at the hock;
#       RP_RP : RP 0 -> 2 driven by the hock ctrl, pole at the knee, then RP 1 -> 3 driven by the IK ctrl
#               (no pole: one pole only, on the first RP);
#       RP_SC : RP 0 -> 2 driven by the hock ctrl, pole at the knee, then SC 2 -> 3 driven by the IK ctrl.
#
#   The secondary ikHandle aims at a target sliding to the hip -> foot line as the leg nears full extension
#   ('straightenStart' on the IK ctrl): the leg goes straight and the stretch lengthens it without folding.
#   Secondary ctrl and pole live under the root ctrl and follow the IK ctrl through translate space blends
#   ('<name>Blend', 0.5). The last joint takes the IK ctrl orientation (simpleIk.orient_end_joint).
#   Stretch ('stretchIk'): simpleIk.stretch_ik on the WHOLE leg, lock of 'lock_joint' on the pole.
#
#   Builder
#       METHOD          get_method, get_rig_node, get_secondary_name
#       CONTROLS        create_controls, create_ik_step, create_pole, create_secondary_control
#       SETUP           create_ik_setup, create_ik_handle, connect_ik_setup, get_hip_matrix,
#                       drive_secondary_handle, stretch_quadruped
#       IK / FK SWITCH  connect_ik_fk_visibility
#       SPACE SWITCH    create_space_switches, create_ik_blend
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from ..limb import builder as limb_builder
from ....utilities import ctrl_utilities
from ....utilities import cnstrMtx_utilities
from ....utilities import switchSpace_utilities

from importlib import reload

reload(limb_builder)
reload(ctrl_utilities)
reload(cnstrMtx_utilities)
reload(switchSpace_utilities)


IkBuilder = limb_builder.IkBuilder


# IK methods:
#   secondary  : (joint index, name) of the secondary ctrl.
#   handles    : (start, end, solver, driver, pole) - driver "secondary" / "ik", pole "pole" or None.
#   lock_joint : joint brought onto the pole by the stretch lock (middle of the handle with the pole).
METHODS = {
    "SC_RP": {
        "secondary": (1, "knee"),
        "handles": (
            (0, 1, "ikSCsolver", "secondary", None),
            (1, 3, "ikRPsolver", "ik", "pole"),
        ),
        "lock_joint": 2,
    },
    "RP_RP": {
        "secondary": (2, "hock"),
        "handles": (
            (0, 2, "ikRPsolver", "secondary", "pole"),
            (1, 3, "ikRPsolver", "ik", None),
        ),
        "lock_joint": 1,
    },
    "RP_SC": {
        "secondary": (2, "hock"),
        "handles": (
            (0, 2, "ikRPsolver", "secondary", "pole"),
            (2, 3, "ikSCsolver", "ik", None),
        ),
        "lock_joint": 1,
    },
}

DEFAULT_METHOD = "RP_RP"


class Builder(limb_builder.Builder):

    SECONDARY_CONTROL_SHAPE = "sphere"
    SECONDARY_CONTROL_COLOR_TYPE = "IK Secondary"

    POLE_BLEND_ATTR = "poleBlend"

    # Extension (hip -> foot distance / leg length) where the secondary target starts sliding to the line.
    STRAIGHTEN_ATTR = "straightenStart"
    STRAIGHTEN_DEFAULT = 0.9
    BLEND_DEFAULT = 0.5

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.secondary_control = None
        self.ik_handles = []
        self.ik_blends = []

    # ======================================================
    # METHOD
    # ======================================================

    def get_method(self):
        """METHODS entry chosen by 'quadrupedIkMethod'."""

        name = self.get_string("quadrupedIkMethod", DEFAULT_METHOD)

        return METHODS.get(name, METHODS[DEFAULT_METHOD])

    def get_rig_node(self, key):
        """Node named in METHODS: "secondary", "ik", "pole" (else None)."""

        return {
            "secondary": self.secondary_control,
            "ik": self.ik_control,
            "pole": self.pole_control,
        }.get(key)

    def get_secondary_name(self):
        """Secondary ctrl name of the method ("knee" / "hock")."""

        return self.get_method()["secondary"][1]

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):
        """Limb ctrls, then the secondary ctrl under the root ctrl."""

        controls = super().create_controls()

        if self.secondary_control:
            self.parent_under_root(self.secondary_control)
            controls.append(self.secondary_control)

        return controls

    def create_ik_step(self):

        """
        IK ctrl on the foot, pole of the method handle that has one, and
        secondary ctrl (knee or hock). Returns (IK ctrl, pole) like limb.
        """

        if len(self.ik_joints) != 4:
            cmds.warning(f"legQuadruped : 4 joints attendus, {len(self.ik_joints)} trouvés.")

        ik_control = IkBuilder.create_ik_control(
            self,
            self.ik_joints,
            suffix=self.IK_CONTROL_SUFFIX,
            shape=self.get_string("ikShape", self.IK_CONTROL_SHAPE),
            size=self.get_float("ikSize", 1.0),
            match_rotation=self.get_string("ikCtrlOrient", "Joint") == "Joint",
            adjust_shape=False
        )

        self.pole_control = None

        for start, end, _, _, pole in self.get_method()["handles"]:
            if pole:
                self.pole_control = self.create_pole(self.ik_joints[start:end + 1])

        self.create_secondary_control()

        return ik_control, self.pole_control

    def create_pole(self, joints):
        """Pole vector in front of the middle joint of 'joints' (simpleIk.create_pole_control)."""

        pole = IkBuilder.create_pole_control(
            self,
            joints,
            suffix=self.POLE_CONTROL_SUFFIX,
            shape=self.get_string("poleShape", self.POLE_CONTROL_SHAPE),
            size=self.get_float("poleSize", 1.0)
        )

        return pole

    def create_secondary_control(self):

        """
        Secondary ctrl '{side}_{baseName}_{index}_{knee|hock}_ctrl' matched on its
        IK joint, under CTRL_grp ('No Ctrl' mode: joint ctrl).
        """

        joint_index, name = self.get_method()["secondary"]

        joint = self.ik_joints[joint_index]

        shape = self.get_string("secondaryShape", self.SECONDARY_CONTROL_SHAPE)
        size = self.get_float("secondarySize", 0.75)
        color = self.get_role_color(self.SECONDARY_CONTROL_COLOR_TYPE)

        if self.no_ctrl():

            self.secondary_control = IkBuilder.create_control_joint(
                self,
                joint.guide,
                f"{name}Ctrl_jnt",
                shape=shape,
                color=color,
                size=size
            )

            return self.secondary_control

        control = ctrl_utilities.Control(
            self.control_name_for(joint, f"{name}_ctrl"),
            shape=shape,
            size=size,
            color=color
        )
        control.create()

        cmds.matchTransform(control.name, joint.name, position=True, rotation=True)

        control.create_offset(parent=self.get_controls_group(), use_group=self.offset_group())

        self.secondary_control = control.name

        return self.secondary_control

    # ======================================================
    # SETUP
    # ======================================================

    def create_ik_setup(self):

        """
        The two hidden ikHandles of the method under MISC_grp (RP becomes SC
        when 'Rotate Plane Solver' is off). Returns the ikHandles.
        """

        if len(self.ik_joints) != 4:
            return []

        self.ik_handles = []

        # Rest bend into the jointOrients before the ikHandles (simpleIk.prepare_ik_chain).
        IkBuilder.prepare_ik_chain(self, self.ik_joints)

        for start, end, solver, _, _ in self.get_method()["handles"]:

            if solver == "ikRPsolver" and not self.rotate_plane_solver():
                solver = "ikSCsolver"

            suffix = "rpIkHandle" if solver == "ikRPsolver" else "scIkHandle"

            self.ik_handles.append(
                self.create_ik_handle(self.ik_joints[start], self.ik_joints[end], solver, suffix)
            )

        # simpleIk / limb know a single ikHandle: the last one (foot).
        self.ik_handle = self.ik_handles[-1]

        return list(self.ik_handles)

    def create_ik_handle(self, start_joint, end_joint, solver, suffix):

        """Hidden ikHandle '{side}_{baseName}_{index}_{suffix}' from 'start_joint' to 'end_joint', under MISC_grp."""

        base_name, side, index = self.main.get_guide_naming(end_joint.guide)

        name = f"{side}_{base_name}_{index:02d}_{suffix}"

        ik_handle, ik_effector = cmds.ikHandle(
            startJoint=start_joint.name,
            endEffector=end_joint.name,
            solver=solver,
            name=name
        )

        cmds.rename(ik_effector, f"{name}_effector")

        misc = self.get_misc_group()

        if misc:
            ik_handle = cmds.parent(ik_handle, misc)[0]

        cmds.setAttr(f"{ik_handle}.visibility", 0)

        return ik_handle

    def connect_ik_setup(self):

        """
        Each ikHandle follows its driver in position only (+ its pole if RP;
        the secondary one through drive_secondary_handle), last joint oriented
        on the IK ctrl, then the stretch if enabled.
        """

        if len(self.ik_handles) != len(self.get_method()["handles"]):
            return

        for ik_handle, (_, _, _, driver, pole) in zip(self.ik_handles, self.get_method()["handles"]):

            driver_node = self.get_rig_node(driver)
            pole_node = self.get_rig_node(pole)

            solver = cmds.nodeType(cmds.listConnections(f"{ik_handle}.ikSolver")[0])
            has_pole = bool(pole_node) and solver == "ikRPsolver"

            # Position only: an SC orients the chain from its handle rotation,
            # following the ctrl rotation would roll the joints.
            if driver == "secondary" and driver_node and self.ik_control:
                self.drive_secondary_handle(ik_handle)

            elif driver_node:
                cnstrMtx_utilities.PointCnstrMtx(ik_handle, driver_node, dcmpMtx=False)

            if has_pole:
                cnstrMtx_utilities.PoleVectorCnstr(ik_handle, pole_node)
                IkBuilder.add_pole_flip(self, ik_handle, pole_node)

        if self.ik_control:
            IkBuilder.orient_end_joint(self, self.ik_joints[-1].name, mo=self.ik_ctrl_world())

        # After orient_end_joint (it drives the last joint offsetParentMatrix).
        if self.use_stretch():
            self.stretch_quadruped()

    def get_hip_matrix(self, prefix):

        """
        Hip world matrix plug without reading the hip (its scale is driven by
        the stretch: cycle): its offsetParentMatrix (source or value) * parent worldMatrix.
        """

        hip = self.ik_joints[0].name

        mult = cmds.createNode("multMatrix", name=f"{prefix}_hip_mm")

        source = cmds.listConnections(f"{hip}.offsetParentMatrix", source=True, destination=False, plugs=True)

        if source:
            cmds.connectAttr(source[0], f"{mult}.matrixIn[0]")
        else:
            cmds.setAttr(f"{mult}.matrixIn[0]", cmds.getAttr(f"{hip}.offsetParentMatrix"), type="matrix")

        parent = cmds.listRelatives(hip, parent=True, fullPath=True)

        if parent:
            cmds.connectAttr(f"{parent[0]}.worldMatrix[0]", f"{mult}.matrixIn[1]")

        return f"{mult}.matrixSum"

    def drive_secondary_handle(self, ik_handle):

        """
        The secondary ikHandle aims at a target (its offsetParentMatrix,
        translation only) blended between:

            secondary ctrl   : bent leg;
            hip -> foot line : hip + (foot - hip) * (length to the secondary
                               joint / total length), its place on the straight leg.

        w = (extension - straightenStart) / (1 - straightenStart), clamped 0..1,
        extension = hip -> IK ctrl distance / leg length. From extension 1 the
        target is on the line: the leg is straight and stretches without folding.
        """

        prefix = ik_handle

        secondary_index = self.get_method()["secondary"][0]

        lengths = [
            om.MVector(cmds.getAttr(f"{joint.name}.offsetParentMatrix")[12:15]).length()
            for joint in self.ik_joints[1:]
        ]

        total = sum(lengths) or 1.0
        ratio = sum(lengths[:secondary_index]) / total

        IkBuilder.add_stretch_attribute(self.ik_control, self.STRAIGHTEN_ATTR, self.STRAIGHTEN_DEFAULT, minimum=0.0, maximum=0.99)

        def position(name, matrix_plug):
            node = cmds.createNode("decomposeMatrix", name=f"{prefix}_{name}_dcmp")
            cmds.connectAttr(matrix_plug, f"{node}.inputMatrix")
            return f"{node}.outputTranslate"

        hip = position("hip", self.get_hip_matrix(prefix))
        foot = position("foot", f"{self.ik_control}.worldMatrix[0]")
        secondary = position("secondary", f"{self.secondary_control}.worldMatrix[0]")

        # Leg extension.
        distance = cmds.createNode("distanceBetween", name=f"{prefix}_extension_db")
        cmds.connectAttr(hip, f"{distance}.point1")
        cmds.connectAttr(foot, f"{distance}.point2")

        # Leg length at rig scale (simpleIk.get_chain_scale).
        scaled_total = cmds.createNode("floatMath", name=f"{prefix}_extension_length_fm")
        cmds.setAttr(f"{scaled_total}.operation", 2)
        cmds.setAttr(f"{scaled_total}.floatB", total)

        chain_scale = IkBuilder.get_chain_scale(self, self.ik_joints, self.prefix)

        if isinstance(chain_scale, str):
            cmds.connectAttr(chain_scale, f"{scaled_total}.floatA")
        else:
            cmds.setAttr(f"{scaled_total}.floatA", chain_scale)

        extension = cmds.createNode("floatMath", name=f"{prefix}_extension_fm")
        cmds.setAttr(f"{extension}.operation", 3)
        cmds.connectAttr(f"{distance}.distance", f"{extension}.floatA")
        cmds.connectAttr(f"{scaled_total}.outFloat", f"{extension}.floatB")

        # w = (extension - start) / (1 - start), clamped 0..1.
        start = f"{self.ik_control}.{self.STRAIGHTEN_ATTR}"

        numerator = cmds.createNode("floatMath", name=f"{prefix}_straighten_num_fm")
        cmds.setAttr(f"{numerator}.operation", 1)
        cmds.connectAttr(f"{extension}.outFloat", f"{numerator}.floatA")
        cmds.connectAttr(start, f"{numerator}.floatB")

        denominator = cmds.createNode("floatMath", name=f"{prefix}_straighten_den_fm")
        cmds.setAttr(f"{denominator}.operation", 1)
        cmds.setAttr(f"{denominator}.floatA", 1.0)
        cmds.connectAttr(start, f"{denominator}.floatB")

        weight = cmds.createNode("floatMath", name=f"{prefix}_straighten_fm")
        cmds.setAttr(f"{weight}.operation", 3)
        cmds.connectAttr(f"{numerator}.outFloat", f"{weight}.floatA")
        cmds.connectAttr(f"{denominator}.outFloat", f"{weight}.floatB")

        clamp = cmds.createNode("clamp", name=f"{prefix}_straighten_clamp")
        cmds.connectAttr(f"{weight}.outFloat", f"{clamp}.inputR")
        cmds.setAttr(f"{clamp}.minR", 0.0)
        cmds.setAttr(f"{clamp}.maxR", 1.0)

        # Point on the hip -> foot line.
        direction = cmds.createNode("plusMinusAverage", name=f"{prefix}_line_dir_pma")
        cmds.setAttr(f"{direction}.operation", 2)
        cmds.connectAttr(foot, f"{direction}.input3D[0]")
        cmds.connectAttr(hip, f"{direction}.input3D[1]")

        scaled = cmds.createNode("multiplyDivide", name=f"{prefix}_line_md")
        cmds.connectAttr(f"{direction}.output3D", f"{scaled}.input1")
        cmds.setAttr(f"{scaled}.input2", ratio, ratio, ratio)

        line = cmds.createNode("plusMinusAverage", name=f"{prefix}_line_pma")
        cmds.connectAttr(hip, f"{line}.input3D[0]")
        cmds.connectAttr(f"{scaled}.output", f"{line}.input3D[1]")

        # Target = secondary ctrl -> line point (w).
        target = cmds.createNode("blendColors", name=f"{prefix}_target_bc")
        cmds.connectAttr(f"{line}.output3D", f"{target}.color1")
        cmds.connectAttr(secondary, f"{target}.color2")
        cmds.connectAttr(f"{clamp}.outputR", f"{target}.blender")

        # World -> ikHandle parent space, into its offsetParentMatrix.
        compose = cmds.createNode("composeMatrix", name=f"{prefix}_target_cm")
        cmds.connectAttr(f"{target}.output", f"{compose}.inputTranslate")

        local = cmds.createNode("multMatrix", name=f"{prefix}_target_mm")
        cmds.connectAttr(f"{compose}.outputMatrix", f"{local}.matrixIn[0]")

        handle_parent = cmds.listRelatives(ik_handle, parent=True, fullPath=True)

        if handle_parent:
            cmds.connectAttr(f"{handle_parent[0]}.worldInverseMatrix[0]", f"{local}.matrixIn[1]")

        cmds.setAttr(f"{ik_handle}.translate", 0, 0, 0)
        cmds.connectAttr(f"{local}.matrixSum", f"{ik_handle}.offsetParentMatrix", force=True)

        return target

    def stretch_quadruped(self):

        """
        Whole leg stretch (simpleIk.stretch_ik on the 4 IK joints): hip -> IK
        ctrl distance over the 3 bones, on every bone once the leg is straight.
        Lock of the method 'lock_joint' on the pole. Attributes on the IK ctrl.
        Returns the created nodes.
        """

        if not self.ik_control or len(self.ik_joints) != 4:
            return {}

        return IkBuilder.stretch_ik(
            self,
            self.ik_joints,
            pole_control=self.pole_control or False,
            ik_control=self.ik_control,
            host=self.ik_control,
            pivot=self.get_method()["lock_joint"]
        )

    # ======================================================
    # IK / FK SWITCH
    # ======================================================

    def connect_ik_fk_visibility(self, switch_plug):
        """Limb visibility, plus the secondary ctrl with the IK ctrls."""

        super().connect_ik_fk_visibility(switch_plug)

        condition = f"{switch_plug.split('.')[0]}_{self.SWITCH_ATTR}_ikVis_cond"

        if not cmds.objExists(condition):
            return

        self.connect_visibility(self.secondary_control, f"{condition}.outColorR")

    # ======================================================
    # SPACE SWITCH
    # ======================================================

    def create_space_switches(self):

        """
        Limb space switches, then space blends of the secondary ctrl and pole
        to the IK ctrl (after parent_ctrls_module: local space = final parent).
        """

        super().create_space_switches()

        self.ik_blends = []

        for control, attr in (
            (self.secondary_control, f"{self.get_secondary_name()}Blend"),
            (self.pole_control, self.POLE_BLEND_ATTR),
        ):
            blend = self.create_ik_blend(control, attr)

            if blend:
                self.ik_blends.append(blend)

        return self.ik_blends

    def create_ik_blend(self, control, attr, default=None):

        """
        Translate space blend of 'control' between its parent (0) and the IK
        ctrl (1), driven by 'attr' on the IK ctrl (blend SpaceSwitch, maintain
        offset); rotate / scale / shear stay local. Skipped if the ctrl offset
        is already driven. Returns the SpaceSwitch, or None.
        """

        if not control or not self.ik_control or not cmds.objExists(control):
            return None

        node = self.get_control_node(control)

        if cmds.listConnections(f"{node}.offsetParentMatrix", source=True, destination=False):
            cmds.warning(f"legQuadruped : '{node}' a déjà un space switch, blend '{attr}' ignoré.")
            return None

        parent = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]

        if not parent:
            return None

        switch = switchSpace_utilities.SpaceSwitch(
            target=node,
            spaces=[("Local", parent), ("IK", self.ik_control)],
            default=self.BLEND_DEFAULT if default is None else default,
            attr_name=attr,
            attr_host=self.ik_control,
            mo=True,
            blend=True
        )

        # Translation only from the IK ctrl.
        blend_matrix = switch.nodes.get("blendMatrix")

        for flag in ("useRotate", "useScale", "useShear"):
            plug = f"{blend_matrix}.target[0].{flag}"
            if blend_matrix and cmds.objExists(plug):
                cmds.setAttr(plug, 0)

        return switch
