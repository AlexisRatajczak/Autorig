# ====================================================================================================================
# SIMPLE IK BUILDER
# ====================================================================================================================
#
#   IK on the module chain: a root ctrl on the first joint (drives the chain base), an IK ctrl on the last joint
#   (drives the ikHandle + last joint orientation) and a pole ctrl (3+ joints) driving the elbow / knee.
#   The three ctrls share the same parent (parent_ik_controls). 'No Ctrl' mode: dedicated joints holding the shape
#   ({..}_rootCtrl_jnt, {..}_ikCtrl_jnt, {..}_pole_jnt), parented like the module root.
#
#   Builder
#       CONTROLS        create_controls, create_root_control, create_ik_control, create_pole_control,
#                       create_control_joint, get_pole_vector_position, get_role_color
#       SETUP           rotate_plane_solver, ik_ctrl_world, pole_ctrl_joint, use_stretch, create_setup, connect_setup,
#                       orient_end_joint, freeze_effector_inputs, add_pole_flip
#       STRETCH         stretch_ik, prepare_ik_chain, move_rest_rotation_to_joint_orient, get_chain_scale,
#                       add_stretch_attribute
#       SPACE SWITCH    parent_ik_controls, get_control_node, create_space_switches
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from ..base.builder import Builder as BaseBuilder
from ....utilities import joint_utilities
from ....utilities import ctrl_utilities
from ....utilities import cnstrMtx_utilities

from importlib import reload

reload(joint_utilities)
reload(ctrl_utilities)
reload(cnstrMtx_utilities)


class Builder(BaseBuilder):

    IK_CONTROL_SHAPE = "cube"
    IK_CONTROL_COLOR_TYPE = "IK Main"

    POLE_CONTROL_SHAPE = "diamond"
    POLE_CONTROL_COLOR_TYPE = "IK Secondary"

    ROOT_CONTROL_SHAPE = "square"
    ROOT_CONTROL_COLOR_TYPE = "IK Main"

    # Joint ctrl suffixes ('No Ctrl' mode).
    ROOT_CONTROL_JOINT_SUFFIX = "rootCtrl_jnt"
    IK_CONTROL_JOINT_SUFFIX = "ikCtrl_jnt"
    POLE_CONTROL_JOINT_SUFFIX = "pole_jnt"

    # Pole distance from the middle joint, relative to the chain length (root -> end).
    POLE_DISTANCE = 1.0

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.root_control = None
        self.ik_control = None
        self.pole_control = None
        self.ik_handle = None

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        Root ctrl on the first joint (controls[0], reparented by MainBuild), IK ctrl
        on the last joint, and pole ctrl if the chain can bend.
        """

        if not self.joints:
            return []

        controls = []

        for control in (
            self.create_root_control(),
            self.create_ik_control(match_rotation=not self.ik_ctrl_world()),
            self.create_pole_control()
        ):
            if control:
                controls.append(control)

        return controls

    def create_root_control(self):

        """
        Root ctrl on the first guide (joint ctrl in 'No Ctrl' mode). Drives the
        first joint; its rotation stays free for the ikHandle.
        """

        root_joint = self.joints[0]

        if self.no_ctrl():

            self.root_control = self.create_control_joint(
                root_joint.guide,
                self.ROOT_CONTROL_JOINT_SUFFIX,
                shape=self.ROOT_CONTROL_SHAPE,
                color=self.get_role_color(self.ROOT_CONTROL_COLOR_TYPE),
                adjust_shape=True
            )

            return self.root_control

        base_name, side, index = self.main.get_guide_naming(root_joint.guide)

        self.root_control = self.create_control(
            root_joint.guide,
            base_name,
            side,
            index,
            shape=self.ROOT_CONTROL_SHAPE,
            color=self.get_role_color(self.ROOT_CONTROL_COLOR_TYPE)
        )

        return self.root_control

    def create_ik_control(
        self,
        joints=None,
        suffix="ctrl",
        shape=None,
        size=1.0,
        match_rotation=True,
        adjust_shape=True
    ):

        """
        IK ctrl '{side}_{baseName}_{index}_{suffix}' on the last joint of 'joints'
        (self.joints by default), oriented like it (else world), under CTRL_grp
        (joint ctrl in 'No Ctrl' mode).

        joints         : IK chain (ex: limb -> self.ik_joints).
        match_rotation : match the joint orientation (else world).
        adjust_shape   : apply the module shapeTranslate / Rotate / Scale.
        """

        joints = self.joints if joints is None else joints

        end_joint = joints[-1]

        shape = shape or self.IK_CONTROL_SHAPE
        color = self.get_role_color(self.IK_CONTROL_COLOR_TYPE)

        if self.no_ctrl():

            self.ik_control = self.create_control_joint(
                end_joint.guide,
                self.IK_CONTROL_JOINT_SUFFIX,
                shape=shape,
                color=color,
                size=size,
                adjust_shape=adjust_shape
            )

            return self.ik_control

        base_name, side, index = self.main.get_guide_naming(end_joint.guide)

        control = ctrl_utilities.Control(
            f"{side}_{base_name}_{index:02d}_{suffix}",
            shape=shape,
            size=size,
            color=color
        )
        control.create()

        if adjust_shape:
            self.adjust_control_shape(control)

        cmds.matchTransform(control.name, end_joint.name, position=True, rotation=bool(match_rotation))

        control.create_offset(parent=self.main.groups.get("controls"), use_group=self.offset_group())

        self.ik_control = control.name

        return self.ik_control

    def create_pole_control(self, joints=None, suffix="pole_ctrl", shape=None, size=1.0):

        """
        Pole ctrl '{side}_{baseName}_{index}_{suffix}' in front of the middle joint
        of 'joints', under CTRL_grp. None with fewer than 3 joints or without
        'Rotate Plane Solver' (an ikSCsolver has no pole).
        """

        joints = self.joints if joints is None else joints

        if len(joints) < 3 or not self.rotate_plane_solver():
            return None

        start_joint = joints[0]
        mid_joint = joints[len(joints) // 2]
        end_joint = joints[-1]

        position = self.get_pole_vector_position(
            start_joint.name,
            mid_joint.name,
            end_joint.name
        )

        shape = shape or self.POLE_CONTROL_SHAPE
        color = self.get_role_color(self.POLE_CONTROL_COLOR_TYPE)

        if self.no_ctrl():

            self.pole_control = self.create_control_joint(
                mid_joint.guide,
                self.POLE_CONTROL_JOINT_SUFFIX,
                shape=shape,
                color=color,
                size=size,
                position=position,
                rotation_from=mid_joint.name if self.pole_ctrl_joint() else None
            )

            return self.pole_control

        base_name, side, index = self.main.get_guide_naming(mid_joint.guide)

        control = ctrl_utilities.Control(
            f"{side}_{base_name}_{index:02d}_{suffix}",
            shape=shape,
            size=size,
            color=color
        )
        control.create()

        cmds.xform(control.name, ws=True, t=position)

        # Orientation: world (default) or the middle joint's.
        if self.pole_ctrl_joint():
            cmds.matchTransform(control.name, mid_joint.name, rotation=True)

        control.create_offset(parent=self.main.groups.get("controls"), use_group=self.offset_group())

        self.pole_control = control.name

        return self.pole_control

    def create_control_joint(
        self,
        guide,
        suffix,
        shape,
        color,
        size=1.0,
        position=None,
        adjust_shape=False,
        rotation_from=None
    ):

        """
        'No Ctrl' mode: joint '{side}_{baseName}_{index}_{suffix}' holding the ctrl
        shape, matched on 'guide' or placed at the world 'position'. Baked, then
        parented like the module root, never under the IK chain it drives.
        """

        base_name, side, index = self.main.get_guide_naming(guide)

        joint = joint_utilities.Joint(
            {
                "baseName": base_name,
                "side": side,
                "index": index,
                "guide": guide
            },
            suffix=suffix
        )
        joint.create_joint()

        if position is None:
            joint.match_transform(guide, matchPos=True, matchRot=True)
        else:
            cmds.xform(joint.name, worldSpace=True, translation=position)

            # Orientation of 'rotation_from' (else world aligned).
            if rotation_from and cmds.objExists(rotation_from):
                cmds.matchTransform(joint.name, rotation_from, rotation=True)

        joint.freeze_transform()

        # Shape built on a temporary transform, then moved (relative) onto the joint.
        control = ctrl_utilities.Control(
            f"{joint.name}_ctrlShape_TEMP",
            shape=shape,
            size=size,
            color=color
        )
        control.create()

        if adjust_shape:
            self.adjust_control_shape(control)

        control.transfer_to_joint(joint.name)

        self.main.parent_module_root(joint, self.data.get("parent"))

        return joint.name

    def get_pole_vector_position(self, start, mid, end):

        """Project 'mid' on start -> end, place the pole in front of 'mid' away from it, at POLE_DISTANCE * chain length."""

        start_pos = om.MVector(cmds.xform(start, q=True, ws=True, t=True))
        mid_pos = om.MVector(cmds.xform(mid, q=True, ws=True, t=True))
        end_pos = om.MVector(cmds.xform(end, q=True, ws=True, t=True))

        start_end = end_pos - start_pos
        start_mid = mid_pos - start_pos

        chain_length = start_end.length()

        if chain_length > 0.0001:
            dot = start_mid * start_end
            projection = start_pos + start_end * (dot / (chain_length ** 2))
        else:
            projection = start_pos

        direction = mid_pos - projection

        if direction.length() < 0.0001:
            direction = om.MVector(0, 0, 1)
        else:
            direction.normalize()

        distance = (chain_length or 1.0) * self.POLE_DISTANCE

        return list(mid_pos + direction * distance)

    def get_role_color(self, color_type):

        """Rig data color (or project default) of the module side and 'color_type' (ex: 'IK Main')."""

        return self.main.get_color(self.data.get("side"), color_type)

    # ======================================================
    # SETUP
    # ======================================================

    def rotate_plane_solver(self):

        """'Rotate Plane Solver' option: ikRPsolver + pole, else ikSCsolver. On by default (also for older modules)."""

        value = self.data.get("rotatePlaneSolver")

        return True if value is None else bool(value)

    def ik_ctrl_world(self):
        """'IK Ctrl Orientation' = World: IK ctrl world aligned (else oriented like the last joint)."""

        return self.data.get("ikCtrlOrient") == "World"

    def pole_ctrl_joint(self):
        """'Pole Ctrl Orientation' = Joint: pole ctrl oriented like the middle joint (else world)."""

        return self.data.get("poleCtrlOrient") == "Joint"

    def use_stretch(self):
        """'Stretch' option: stretch + elbow lock (stretch_ik)."""

        return bool(self.data.get("stretchIk", 0))

    def create_setup(self, joints=None):

        """Hidden ikHandle on 'joints' (self.joints by default) under MISC_grp: ikRPsolver, or ikSCsolver without 'Rotate Plane Solver'."""

        joints = self.joints if joints is None else joints

        if len(joints) < 2:
            return []

        start_joint = joints[0].name
        end_joint_obj = joints[-1]

        solver = "ikRPsolver" if self.rotate_plane_solver() else "ikSCsolver"

        self.prepare_ik_chain(joints)

        base_name, side, index = self.main.get_guide_naming(end_joint_obj.guide)

        ik_handle, ik_effector = cmds.ikHandle(
            startJoint=start_joint,
            endEffector=end_joint_obj.name,
            solver=solver,
            name=f"{side}_{base_name}_{index:02d}_ikHandle"
        )

        cmds.rename(ik_effector, f"{side}_{base_name}_{index:02d}_ikEffector")

        setup_parent = self.main.groups.get("misc")

        if setup_parent and cmds.objExists(setup_parent):
            ik_handle = cmds.parent(ik_handle, setup_parent)[0]

        cmds.setAttr(f"{ik_handle}.visibility", 0)

        self.ik_handle = ik_handle

        return [ik_handle]

    def connect_setup(self, joints=None):

        """
        On 'joints' (self.joints by default): root ctrl -> first joint, IK ctrl ->
        ikHandle and last joint orientation, pole -> ikHandle, then the stretch.
        """

        joints = self.joints if joints is None else joints

        if self.root_control and joints:
            cnstrMtx_utilities.ParentCnstrMtx(joints[0].name, self.root_control, dcmpMtx=False)

        if not self.ik_handle:
            return

        if self.ik_control:

            # RP: position only (the handle rotation would turn the chain plane, the pole defines it).
            # SC (no pole): its rotation orients the chain, it follows the ctrl (maintain offset).
            if self.rotate_plane_solver():
                cnstrMtx_utilities.PointCnstrMtx(self.ik_handle, self.ik_control, dcmpMtx=False)
            else:
                cnstrMtx_utilities.ParentCnstrMtx(self.ik_handle, self.ik_control, mo=True, dcmpMtx=False)

            # Last joint orientation: its own network, independent of the ikHandle.
            self.orient_end_joint(joints[-1].name, mo=self.ik_ctrl_world())

        if self.pole_control and self.rotate_plane_solver():
            cnstrMtx_utilities.PoleVectorCnstr(self.ik_handle, self.pole_control)
            self.add_pole_flip(self.ik_handle, self.pole_control)

        # After orient_end_joint (it drives the last joint offsetParentMatrix).
        if self.use_stretch():
            self.stretch_ik(joints)

    def orient_end_joint(self, end_joint=None, mo=False):

        """
        Orient the last joint on the IK ctrl in matrices only (no decomposeMatrix):

            rotation           = pickMatrix(ik_ctrl.worldMatrix, rotation only)
            position           = pickMatrix(rest translation * parent.worldMatrix,
                                 translation only): bone tip, stretch included
            offsetParentMatrix = rotation * position * parent.worldInverseMatrix

        The joint world matrix is exactly rotation * position whatever the parent
        scale (stretch / squash); inverseScale is disconnected. No cycle: the
        joint -> ikEffector inputs are frozen (freeze_effector_inputs).

        end_joint : joint to orient (last of self.joints by default).
        mo        : rotation maintain offset (world aligned IK ctrl): the joint keeps
                    its build orientation.

        Returns the created nodes.
        """

        end_joint = end_joint or self.joints[-1].name

        rest_translate = cmds.getAttr(f"{end_joint}.offsetParentMatrix")[12:15]

        # Matrices read on the PARENT joint, never on the driven joint: no cycle (node level evaluation).
        parent = cmds.listRelatives(end_joint, parent=True, fullPath=True)[0]

        def pick(name, matrix_plug, translate, rotate):
            node = cmds.createNode("pickMatrix", name=f"{end_joint}_{name}")
            cmds.connectAttr(matrix_plug, f"{node}.inputMatrix", force=True)
            cmds.setAttr(f"{node}.useTranslate", translate)
            cmds.setAttr(f"{node}.useRotate", rotate)
            cmds.setAttr(f"{node}.useScale", 0)
            cmds.setAttr(f"{node}.useShear", 0)
            return node

        # IK ctrl world rotation.
        rotation = pick("orient_rot_pm", f"{self.ik_control}.worldMatrix[0]", 0, 1)
        rotation_plug = f"{rotation}.outputMatrix"

        # Maintain offset: joint / ctrl rotation offset at build time.
        if mo:

            joint_rotation = om.MTransformationMatrix(om.MMatrix(cmds.getAttr(f"{end_joint}.worldMatrix[0]"))).asRotateMatrix()
            ctrl_rotation = om.MTransformationMatrix(om.MMatrix(cmds.getAttr(f"{self.ik_control}.worldMatrix[0]"))).asRotateMatrix()

            offset = cmds.createNode("holdMatrix", name=f"{end_joint}_orient_offset_hm")
            cmds.setAttr(f"{offset}.inMatrix", list(joint_rotation * ctrl_rotation.inverse()), type="matrix")

            offset_rotation = cmds.createNode("multMatrix", name=f"{end_joint}_orient_offset_mm")
            cmds.connectAttr(f"{offset}.outMatrix", f"{offset_rotation}.matrixIn[0]", force=True)
            cmds.connectAttr(rotation_plug, f"{offset_rotation}.matrixIn[1]", force=True)

            rotation_plug = f"{offset_rotation}.matrixSum"

        # World position of the bone tip: rest translation in the (scaled) parent space.
        rest = cmds.createNode("composeMatrix", name=f"{end_joint}_orient_rest_cm")

        cmds.setAttr(f"{rest}.inputTranslate", *rest_translate)

        tip = cmds.createNode("multMatrix", name=f"{end_joint}_orient_tip_mm")
        cmds.connectAttr(f"{rest}.outputMatrix", f"{tip}.matrixIn[0]", force=True)
        cmds.connectAttr(f"{parent}.worldMatrix[0]", f"{tip}.matrixIn[1]", force=True)

        position = pick("orient_pos_pm", f"{tip}.matrixSum", 1, 0)

        # offsetParentMatrix = wanted world * parentInverseMatrix.
        mult = cmds.createNode("multMatrix", name=f"{end_joint}_orient_mm")
        cmds.connectAttr(rotation_plug, f"{mult}.matrixIn[0]", force=True)
        cmds.connectAttr(f"{position}.outputMatrix", f"{mult}.matrixIn[1]", force=True)
        cmds.connectAttr(f"{parent}.worldInverseMatrix[0]", f"{mult}.matrixIn[2]", force=True)

        # Neutral local channels: only the offsetParentMatrix places the joint.
        cmds.setAttr(f"{end_joint}.translate", 0, 0, 0)
        cmds.setAttr(f"{end_joint}.rotate", 0, 0, 0)
        cmds.setAttr(f"{end_joint}.scale", 1, 1, 1)
        cmds.setAttr(f"{end_joint}.rotateAxis", 0, 0, 0)

        if cmds.attributeQuery("jointOrient", node=end_joint, exists=True):
            cmds.setAttr(f"{end_joint}.jointOrient", 0, 0, 0)

        for source in cmds.listConnections(f"{end_joint}.inverseScale", source=True, destination=False, plugs=True) or []:
            cmds.disconnectAttr(source, f"{end_joint}.inverseScale")

        cmds.setAttr(f"{end_joint}.inverseScale", 1, 1, 1)

        self.freeze_effector_inputs(end_joint)

        cmds.connectAttr(f"{mult}.matrixSum", f"{end_joint}.offsetParentMatrix", force=True)

        return {
            "rotation": rotation,
            "rest": rest,
            "tip": tip,
            "position": position,
            "multMatrix": mult
        }

    @staticmethod
    def freeze_effector_inputs(joint):

        """
        Disconnect the 'joint' attributes feeding an ikEffector, keeping their
        current value: driving the joint no longer goes through the effector.
        """

        connections = cmds.listConnections(joint, source=False, destination=True, plugs=True, connections=True, type="ikEffector") or []

        for source, destination in zip(connections[::2], connections[1::2]):

            value = cmds.getAttr(destination)

            cmds.disconnectAttr(source, destination)

            if isinstance(value, list) and len(value) == 16:
                cmds.setAttr(destination, value, type="matrix")
            elif isinstance(value, list) and value and isinstance(value[0], tuple):
                cmds.setAttr(destination, *value[0])
            else:
                cmds.setAttr(destination, value)

    POLE_FLIP_ATTR = "poleFlip"

    def add_pole_flip(self, ik_handle, pole_control, attr=None):

        """
        'poleFlip' enum (Positive / Negative) on the pole ctrl: Negative reverses
        the ikHandle poleVector (multiplyDivide * -1), the chain plane flips side.
        Returns the multiplyDivide, or None if poleVector is not connected.
        """

        attr = attr or self.POLE_FLIP_ATTR

        sources = cmds.listConnections(f"{ik_handle}.poleVector", source=True, destination=False, plugs=True)

        if not sources:
            cmds.warning(f"add_pole_flip : '{ik_handle}.poleVector' n'est pas connecté.")
            return None

        if not cmds.attributeQuery(attr, node=pole_control, exists=True):
            cmds.addAttr(pole_control, longName=attr, attributeType="enum", enumName="Positive:Negative", keyable=True)

        sign = cmds.createNode("condition", name=f"{ik_handle}_poleFlip_cnd")
        cmds.setAttr(f"{sign}.operation", 0)
        cmds.connectAttr(f"{pole_control}.{attr}", f"{sign}.firstTerm")
        cmds.setAttr(f"{sign}.secondTerm", 0)
        cmds.setAttr(f"{sign}.colorIfTrue", 1, 1, 1)
        cmds.setAttr(f"{sign}.colorIfFalse", -1, -1, -1)

        flip = cmds.createNode("multiplyDivide", name=f"{ik_handle}_poleFlip_md")
        cmds.connectAttr(sources[0], f"{flip}.input1")
        cmds.connectAttr(f"{sign}.outColor", f"{flip}.input2")

        cmds.connectAttr(f"{flip}.output", f"{ik_handle}.poleVector", force=True)

        return flip

    # ======================================================
    # STRETCH
    # ======================================================

    def stretch_ik(self, joints=None, root=None, pole_control=None, ik_control=None, host=None, pivot=None):

        """
        Stretch + lock + squash on an IK chain of 2+ joints:

            stretch : root -> IK ctrl distance past the chain length -> factor
                      distance / length (1 below), limited by 'stretchLimit',
                      on every bone, weighted by 'stretch' (0..1, IK ctrl);
            lock    : (with a pole) the middle joint (joints[n // 2]) goes onto the
                      pole: upper bones * dist(root, pole) / upper length, lower
                      bones * dist(pole, ik) / lower length, weighted by 'lock'
                      (0..1, pole ctrl);
            squash  : factor ^ -squash on the two other axes, 'squash' (0..1, IK
                      ctrl): 0 = no scale, 0.5 = volume kept, 1 = inverse stretch.

        The factor drives the aim axis scale of each bone's joint, the squash its
        two other axes; the last joint gets the last bone squash. Child rest
        rotations go to jointOrient, inverseScale connected: no shear. Call after
        connect_setup (orient_end_joint drives the last joint OPM).

        joints       : IK chain (self.joints by default; ex: limb -> self.ik_joints).
        root         : node or matrix plug where distances start (default: first
                       joint position, without its scale).
        pole_control : pole ctrl (None = self.pole_control); False = no lock.
        ik_control   : IK ctrl (self.ik_control by default): distance target.
        pivot        : index of the joint locked on the pole (None = joints[n // 2]).
        host         : holder of stretch / stretchLimit / squash (ik_control by
                       default), shared by several IKs (ex: legQuadruped).

        Stores self.ik_stretch_segments: [(start position, end position, stretch
        factor plug, squash plug)] per bone at build pose (ribbon.connect_follicle_scale).

        Returns the created nodes, or {} with fewer than 2 joints or no IK ctrl.
        """

        joints = self.joints if joints is None else joints

        ik_control = ik_control or self.ik_control
        host = host or ik_control

        if len(joints) < 2 or not ik_control:
            cmds.warning("stretch_ik : il faut une chaîne d'au moins 2 joints et un ctrl IK.")
            return {}

        root_joint = joints[0].name
        pole_control = self.pole_control if pole_control is None else pole_control

        base_name, side, index = self.main.get_guide_naming(joints[-1].guide)
        prefix = f"{side}_{base_name}_{index:02d}"

        nodes = {}

        def node(node_type, name):
            nodes[name] = cmds.createNode(node_type, name=f"{prefix}_{name}")
            return nodes[name]

        def world(item):
            # Node -> its worldMatrix; a matrix plug is kept as is.
            return item if "." in item else f"{item}.worldMatrix[0]"

        def distance(name, start, end):
            db = node("distanceBetween", name)
            cmds.connectAttr(world(start), f"{db}.inMatrix1")
            cmds.connectAttr(world(end), f"{db}.inMatrix2")
            return f"{db}.distance"

        # Distance start: 'root', else the first joint position without reading the joint (its scale is
        # driven by the stretch: cycle): its offsetParentMatrix (source or value) * parent worldMatrix.
        if not root:
            root_position = node("multMatrix", "root_position_mm")

            source = cmds.listConnections(f"{root_joint}.offsetParentMatrix", source=True, destination=False, plugs=True)

            if source:
                cmds.connectAttr(source[0], f"{root_position}.matrixIn[0]")
            else:
                cmds.setAttr(f"{root_position}.matrixIn[0]", cmds.getAttr(f"{root_joint}.offsetParentMatrix"), type="matrix")

            root_parent = cmds.listRelatives(root_joint, parent=True, fullPath=True)

            if root_parent:
                cmds.connectAttr(f"{root_parent[0]}.worldMatrix[0]", f"{root_position}.matrixIn[1]")

            root = f"{root_position}.matrixSum"

        def float_math(name, operation, a, b):
            fm = node("floatMath", name)
            cmds.setAttr(f"{fm}.operation", operation)
            for attr, value in (("floatA", a), ("floatB", b)):
                if isinstance(value, str):
                    cmds.connectAttr(value, f"{fm}.{attr}")
                else:
                    cmds.setAttr(f"{fm}.{attr}", value)
            return f"{fm}.outFloat"

        def blend(name, input_0, input_1, blender):
            bta = node("blendTwoAttr", name)
            for i, value in enumerate((input_0, input_1)):
                if isinstance(value, str):
                    cmds.connectAttr(value, f"{bta}.input[{i}]")
                else:
                    cmds.setAttr(f"{bta}.input[{i}]", value)
            cmds.connectAttr(blender, f"{bta}.attributesBlender")
            return f"{bta}.output"

        # Bones = child joints (joints[1:]), rest length = their offsetParentMatrix translation.
        bones = [joint.name for joint in joints[1:]]
        lengths = [om.MVector(cmds.getAttr(f"{bone}.offsetParentMatrix")[12:15]).length() for bone in bones]

        # Lengths at rig scale (* root joint world scale, get_chain_scale): no stretch when the rig is scaled.
        chain_scale = self.get_chain_scale(joints, prefix)

        def scaled(name, length):
            return float_math(name, 2, chain_scale, length)

        chain_length = scaled("chain_length_fm", sum(lengths))

        # Stretch: distance / length past the length, limited.
        self.add_stretch_attribute(host, "stretch", 1.0, maximum=1.0)
        self.add_stretch_attribute(host, "stretchLimit", 2.0, minimum=1.0, maximum=None)

        chain_distance = distance("stretch_db", root, ik_control)
        ratio = float_math("stretch_ratio_fm", 3, chain_distance, chain_length)

        condition = node("condition", "stretch_cnd")
        cmds.setAttr(f"{condition}.operation", 2)
        cmds.connectAttr(chain_distance, f"{condition}.firstTerm")
        cmds.connectAttr(chain_length, f"{condition}.secondTerm")
        cmds.connectAttr(ratio, f"{condition}.colorIfTrueR")
        cmds.setAttr(f"{condition}.colorIfFalseR", 1.0)

        limited = float_math("stretch_limit_fm", 4, f"{condition}.outColorR", f"{host}.stretchLimit")

        stretch = blend("stretch_bta", 1.0, limited, f"{host}.stretch")

        factors = [stretch] * len(bones)

        # Squash: -squash exponent, set on the IK ctrl.
        self.add_stretch_attribute(host, "squash", 0.5, maximum=1.0)

        squash_power = float_math("squash_power_fm", 2, f"{host}.squash", -1.0)

        # Lock: upper bones (to the middle joint) and lower bones, to the pole.
        pivot = len(joints) // 2 if pivot is None else int(pivot)

        if pole_control and 0 < pivot < len(joints) - 1:

            self.add_stretch_attribute(pole_control, "lock", 0.0, maximum=1.0)

            upper, lower = slice(0, pivot), slice(pivot, len(bones))

            lock_up = float_math("lock_up_fm", 3, distance("lock_up_db", root, pole_control), scaled("lock_up_length_fm", sum(lengths[upper])))
            lock_down = float_math("lock_down_fm", 3, distance("lock_down_db", pole_control, ik_control), scaled("lock_down_length_fm", sum(lengths[lower])))

            up = blend("up_bta", stretch, lock_up, f"{pole_control}.lock")
            down = blend("down_bta", stretch, lock_down, f"{pole_control}.lock")

            factors = [up] * pivot + [down] * (len(bones) - pivot)

        # Bone axis: main component of the module aimVector.
        aim_vector = self.get_vector_attribute("aimVector", default=(1.0, 0.0, 0.0))
        aim = max(range(3), key=lambda k: abs(aim_vector[k]))

        squash = None

        self.ik_stretch_segments = []

        for i, (parent, bone, factor) in enumerate(zip(joints[:-1], bones, factors), start=1):

            # No shear from the parent non uniform scale: rest rotation -> jointOrient (OPM = rest
            # translation only), parent.scale -> inverseScale. The last joint OPM (orient_end_joint)
            # already cancels the parent scale.
            if not cmds.listConnections(f"{bone}.offsetParentMatrix", source=True, destination=False):

                self.move_rest_rotation_to_joint_orient(bone)

                if not cmds.listConnections(f"{bone}.inverseScale", source=True, destination=False):
                    cmds.connectAttr(f"{parent.name}.scale", f"{bone}.inverseScale", force=True)

            # Stretch: scale of the bone's joint on the aim axis (the child translation follows).
            # Squash: factor ^ -squash on the two other axes.
            squash = float_math(f"{i:02d}_squash_fm", 6, factor, squash_power)

            for k, axis in enumerate("XYZ"):
                cmds.connectAttr(factor if k == aim else squash, f"{parent.name}.scale{axis}", force=True)

            self.ik_stretch_segments.append((
                cmds.xform(parent.name, query=True, worldSpace=True, translation=True),
                cmds.xform(bone, query=True, worldSpace=True, translation=True),
                factor,
                squash
            ))

        # Last joint: no bone, but keeps the last bone thickness (squash on its two other axes).
        if squash:
            for k, axis in enumerate("XYZ"):
                if k != aim:
                    cmds.connectAttr(squash, f"{joints[-1].name}.scale{axis}", force=True)

        return nodes

    def prepare_ik_chain(self, joints):

        """
        Classic IK chain before the ikHandle: the rest rotation of each joint (the
        first aside) moves from the offsetParentMatrix to jointOrient (same pose).
        With the bend in the OPM, the RP solver could flip the chain away from the pole.
        """

        for joint in joints[1:]:

            name = getattr(joint, "name", joint)

            if not cmds.listConnections(f"{name}.offsetParentMatrix", source=True, destination=False):
                self.move_rest_rotation_to_joint_orient(name)

    @staticmethod
    def move_rest_rotation_to_joint_orient(joint):

        """
        Move the offsetParentMatrix rotation of 'joint' into its jointOrient: OPM =
        translation only, same world pose. No effect without rotation.
        """

        matrix = om.MTransformationMatrix(om.MMatrix(cmds.getAttr(f"{joint}.offsetParentMatrix")))

        rotation = matrix.rotation()
        orient = [om.MAngle(angle).asDegrees() for angle in (rotation.x, rotation.y, rotation.z)]

        if all(abs(value) < 1e-6 for value in orient):
            return

        translation = matrix.translation(om.MSpace.kTransform)

        cmds.setAttr(f"{joint}.jointOrient", *orient)
        cmds.setAttr(
            f"{joint}.offsetParentMatrix",
            [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, translation.x, translation.y, translation.z, 1],
            type="matrix"
        )

    def get_chain_scale(self, joints, prefix):

        """
        World scale (X) plug of the chain root: module root joint (self.root_joint,
        ex: limb), else the first joint parent, never the first joint (its scale is
        driven by the stretch: cycle). Read by a ScaleCnstrMtx on a hidden
        '{prefix}_stretchScale_grp' under MISC_grp. 1.0 without root.
        """

        first = joints[0].name

        root = getattr(self, "root_joint", None)
        root = getattr(root, "name", root)

        if not root or root == first or not cmds.objExists(root):
            parent = cmds.listRelatives(first, parent=True, fullPath=True)
            root = parent[0] if parent else None

        if not root:
            return 1.0

        group = f"{prefix}_stretchScale_grp"

        if not cmds.objExists(group):

            group = cmds.group(empty=True, name=group)

            misc = self.get_misc_group()

            if misc:
                group = cmds.parent(group, misc)[0]

            cmds.setAttr(f"{group}.visibility", 0)

            cnstrMtx_utilities.ScaleCnstrMtx(group, root, mo=False, dcmpMtx=True)

        return f"{group}.scaleX"

    @staticmethod
    def add_stretch_attribute(control, attr, default, minimum=0.0, maximum=1.0):
        """Keyable float 'attr' on 'control' (optional bounds), if missing."""

        if cmds.attributeQuery(attr, node=control, exists=True):
            return

        kwargs = {"longName": attr, "attributeType": "float", "defaultValue": default, "keyable": True}

        if minimum is not None:
            kwargs["minValue"] = minimum

        if maximum is not None:
            kwargs["maxValue"] = maximum

        cmds.addAttr(control, **kwargs)

    # ======================================================
    # SPACE SWITCH
    # ======================================================

    def parent_ik_controls(self):

        """
        Put the IK and pole ctrls under the parent of the reference ctrl (root, else
        IK): MainBuild only reparents controls[0]. World position kept, OPM re-baked
        without offset group. Nothing in 'No Ctrl' mode.
        """

        reference = self.root_control or self.ik_control

        if not reference:
            return

        parent = cmds.listRelatives(self.get_control_node(reference), parent=True, fullPath=True)

        if not parent:
            return

        for control in (self.ik_control, self.pole_control):

            if not control or control == reference or not cmds.objExists(control):
                continue

            node = self.get_control_node(control)

            current_parent = cmds.listRelatives(node, parent=True, fullPath=True) or []

            if current_parent and current_parent[0] == parent[0]:
                continue

            if node != control:
                cmds.parent(node, parent[0])
                continue

            world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)

            cmds.parent(node, parent[0], relative=True)
            cmds.xform(node, worldSpace=True, matrix=world_matrix)

            ctrl_utilities.Control(node).transfer_offset_parent_matrix()

    def get_control_node(self, control):
        """Ctrl offset group if it exists, else the ctrl."""

        offset = self.main.get_offset_group(control)

        return offset if offset and cmds.objExists(offset) else control

    def create_space_switches(self):

        """
        Space switches of the root ctrl (spaceSwitchTargets), IK ctrl
        (ikSpaceSwitchTargets) and pole (poleSpaceSwitchTargets). The pole is first
        grouped under the IK ctrl final parent (parent_ik_controls).
        """

        self.parent_ik_controls()

        if self.root_control:
            self.create_space_switch(self.root_control)

        if self.ik_control:
            self.create_space_switch(
                self.ik_control,
                attr_name="space",
                targets_attr="ikSpaceSwitchTargets"
            )

        if self.pole_control:
            self.create_space_switch(
                self.pole_control,
                attr_name="space",
                targets_attr="poleSpaceSwitchTargets"
            )
