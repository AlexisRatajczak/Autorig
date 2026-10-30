# ====================================================================================================================
# IK SPINE BUILDER
# ====================================================================================================================
#
#   Spline IK spine (ikSplineSolver) driven by a main + sub ctrl per guide.
#
#   JOINTS (under the root joint {side}_{name}_{idx}_root_jnt, joints[0])
#       guide  {..}_jnt               - self.guide_joints: one per guide, flat under the root, driven by its sub
#                                       ctrl, skins its curve CV
#       spine  {prefix}_{i}_spine_jnt - self.spine_joints: spineJointCount chained joints along the curve,
#                                       driven by the spline IK (skin joints)
#   CONTROLS (one pair per guide)
#       main   {..}_ctrl              - chained to the previous main (controls[0] reparented by MainBuild)
#       sub    {..}_sub_ctrl          - under its main, drives the guide joint (ParentCnstrMtx)
#   SETUP
#       {prefix}_spine_crv: one CV per guide, each skinned 100% to its guide joint; spline ikHandle on the
#       spine joints; advanced twist (Object Rotation Up Start / End) between the first and last sub ctrl.
#
#   Builder
#       DATA        get_float, get_string, prefix, get_role_color, get_guide_positions
#       JOINTS      build_joints, create_spine_joints
#       CONTROLS    create_controls, create_spine_control
#       SETUP       create_setup, connect_setup
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from ..base.builder import Builder as BaseBuilder
from ....utilities import joint_utilities
from ....utilities import ctrl_utilities
from ....utilities import curve_utilities
from ....utilities import skinCluster_utilities

from importlib import reload

reload(joint_utilities)
reload(ctrl_utilities)
reload(curve_utilities)
reload(skinCluster_utilities)


# Module axis (aimVector / upVector) -> spline ikHandle enums.
FORWARD_AXIS = {(1, 0, 0): 0, (-1, 0, 0): 1, (0, 1, 0): 2, (0, -1, 0): 3, (0, 0, 1): 4, (0, 0, -1): 5}
UP_AXIS = {(0, 1, 0): 0, (0, -1, 0): 1, (0, 0, 1): 3, (0, 0, -1): 4, (1, 0, 0): 6, (-1, 0, 0): 7}


class Builder(BaseBuilder):

    CONTROL_SHAPE = "circle"
    CONTROL_COLOR_TYPE = "IK Main"

    SUB_CONTROL_SHAPE = "circle"
    SUB_CONTROL_COLOR_TYPE = "IK Secondary"
    SUB_CONTROL_SUFFIX = "sub_ctrl"

    SPINE_JOINT_SUFFIX = "spine_jnt"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.guide_joints = []
        self.spine_joints = []

        self.main_controls = []
        self.sub_controls = []

        self.curve = None
        self.ik_handle = None
        self.skin_cluster = None

    # ======================================================
    # DATA
    # ======================================================

    def get_float(self, key, default):
        """Float / int module attribute, or 'default'."""

        try:
            return float(self.data.get(key))
        except (TypeError, ValueError):
            return default

    def get_string(self, key, default):
        """Enum module attribute (string, read by PreBuild), or 'default'."""

        value = self.data.get(key)

        return value if isinstance(value, str) and value else default

    @property
    def prefix(self):
        """{side}_{baseName}_{index:02d}, from the root guide."""

        base_name, side, index = self.main.get_guide_naming(list(self.data["guides"])[0])

        return f"{side}_{base_name}_{index:02d}"

    def get_role_color(self, role):
        """Rig data color (or project default) for the module side and 'role'."""

        return self.main.get_color(self.data.get("side"), role)

    def get_guide_positions(self):
        """World positions of the guide joints."""

        return [cmds.xform(joint.name, query=True, worldSpace=True, translation=True) for joint in self.guide_joints]

    # ======================================================
    # JOINTS
    # ======================================================

    def build_joints(self, suffix="jnt"):

        """
        Guide joints (flat under the root joint), root joint, then
        spineJointCount spine joints along the guide curve.
        self.joints = [root] + guide joints + spine joints.
        """

        self.guide_joints = self.create_joints(suffix=suffix)

        if len(self.guide_joints) < 2:
            cmds.warning(f"IkSpine '{self.prefix}' : au moins 2 guides sont nécessaires.")

        self.create_root_joint(self.guide_joints[0])

        # Flat: each guide joint is driven by its sub ctrl.
        for joint in self.guide_joints:
            joint_utilities.parent_joint(joint, self.root_joint.name)

        self.spine_joints = self.create_spine_joints()

        self.joints = [self.root_joint] + self.guide_joints + self.spine_joints

        return self.joints

    def create_spine_joints(self):

        """
        spineJointCount (min 2) joints '{prefix}_{i:02d}_spine_jnt' evenly spaced
        along the guide curve, chained under the root joint: aimVector to the
        next joint, up from the closest guide joint.
        """

        count = max(2, int(self.get_float("spineJointCount", 8)))

        guide_positions = self.get_guide_positions()

        positions = curve_utilities.get_points_along_points(guide_positions, count)

        up_objects = [
            self.guide_joints[
                min(range(len(guide_positions)), key=lambda g: (om.MVector(guide_positions[g]) - om.MVector(position)).length())
            ].name
            for position in positions
        ]

        return joint_utilities.create_chain(
            positions,
            [f"{self.prefix}_{i:02d}_{self.SPINE_JOINT_SUFFIX}" for i in range(count)],
            parent=self.root_joint.name,
            aim_vector=self.get_vector_attribute("aimVector", default=(1, 0, 0)),
            up_vector=self.get_vector_attribute("upVector", default=(0, 0, 1)),
            up_objects=up_objects
        )

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        Per guide: a main ctrl '{..}_ctrl' chained to the previous main, and a
        sub ctrl '{..}_sub_ctrl' under it driving the guide joint.
        Returns mains then subs (controls[0] = first main).
        """

        self.main_controls = []
        self.sub_controls = []

        main_shape = self.get_string("mainShape", self.CONTROL_SHAPE)
        main_size = self.get_float("mainSize", 1.5)
        sub_shape = self.get_string("subShape", self.SUB_CONTROL_SHAPE)
        sub_size = self.get_float("subSize", 1.0)

        main_color = self.get_role_color(self.CONTROL_COLOR_TYPE)
        sub_color = self.get_role_color(self.SUB_CONTROL_COLOR_TYPE)

        parent = None

        for joint in self.guide_joints:

            base_name, side, index = self.main.get_guide_naming(joint.guide)
            name = f"{side}_{base_name}_{index:02d}"

            main_control = self.create_spine_control(f"{name}_ctrl", joint.name, main_shape, main_size, main_color, parent)
            sub_control = self.create_spine_control(f"{name}_{self.SUB_CONTROL_SUFFIX}", joint.name, sub_shape, sub_size, sub_color, main_control)

            self.connect_control(sub_control, joint.name)

            self.main_controls.append(main_control)
            self.sub_controls.append(sub_control)

            parent = main_control

        return self.main_controls + self.sub_controls

    def create_spine_control(self, name, match, shape, size, color, parent=None):

        """
        Ctrl 'name' matched on 'match', with the module shape offset,
        under 'parent' (CTRL_grp by default). Returns its name.
        """

        control = ctrl_utilities.Control(name, shape=shape, size=size, color=color)
        control.create()

        self.adjust_control_shape(control)

        cmds.matchTransform(control.name, match, position=True, rotation=True)

        control.create_offset(parent=parent or self.get_controls_group(), use_group=self.offset_group())

        return control.name

    # ======================================================
    # SETUP
    # ======================================================

    def create_setup(self):

        """
        Hidden curve '{prefix}_spine_crv' (one CV per guide) under MISC_grp,
        skinned 100% to the guide joints, and spline ikHandle on the spine
        joints. Returns the setup nodes.
        """

        if len(self.guide_joints) < 2 or len(self.spine_joints) < 2:
            return []

        misc = self.get_misc_group()

        curve = curve_utilities.create_curve(self.get_guide_positions(), name=f"{self.prefix}_spine_crv")

        if misc:
            curve = cmds.parent(curve, misc)[0]

        # Deformed by its skin only.
        cmds.setAttr(f"{curve}.inheritsTransform", 0)
        cmds.setAttr(f"{curve}.visibility", 0)

        self.curve = curve
        self.skin_cluster = skinCluster_utilities.skin_cvs_to_joints(curve, self.guide_joints, name=f"{self.prefix}_spine_skin")

        ik_handle, effector = cmds.ikHandle(
            startJoint=self.spine_joints[0].name,
            endEffector=self.spine_joints[-1].name,
            solver="ikSplineSolver",
            curve=curve,
            createCurve=False,
            parentCurve=False,
            name=f"{self.prefix}_splineIkHandle"
        )[:2]

        cmds.rename(effector, f"{self.prefix}_splineIkHandle_effector")

        if misc:
            ik_handle = cmds.parent(ik_handle, misc)[0]

        cmds.setAttr(f"{ik_handle}.visibility", 0)

        self.ik_handle = ik_handle

        return [self.curve, self.ik_handle]

    def connect_setup(self):

        """
        Spline IK advanced twist (Object Rotation Up Start / End): start follows
        the first sub ctrl, end the last one. Axes from aimVector / upVector.
        """

        if not self.ik_handle or not self.sub_controls:
            return

        aim_vector = tuple(int(round(v)) for v in self.get_vector_attribute("aimVector", default=(1, 0, 0)))
        up_vector = tuple(int(round(v)) for v in self.get_vector_attribute("upVector", default=(0, 0, 1)))

        handle = self.ik_handle

        cmds.setAttr(f"{handle}.dTwistControlEnable", 1)
        cmds.setAttr(f"{handle}.dWorldUpType", 4)
        cmds.setAttr(f"{handle}.dForwardAxis", FORWARD_AXIS.get(aim_vector, 0))
        cmds.setAttr(f"{handle}.dWorldUpAxis", UP_AXIS.get(up_vector, 0))

        # Up in sub ctrl space (oriented like the guide joints).
        cmds.setAttr(f"{handle}.dWorldUpVector", *up_vector)
        cmds.setAttr(f"{handle}.dWorldUpVectorEnd", *up_vector)

        cmds.connectAttr(f"{self.sub_controls[0]}.worldMatrix[0]", f"{handle}.dWorldUpMatrix", force=True)
        cmds.connectAttr(f"{self.sub_controls[-1]}.worldMatrix[0]", f"{handle}.dWorldUpMatrixEnd", force=True)
