# ====================================================================================================================
# SPINE BUILDER
# ====================================================================================================================
#
#   Spline IK spine (ikSplineSolver) driven by a main + sub ctrl per guide.
#
#   JOINTS (under the root joint {side}_{name}_{idx}_root_jnt, joints[0])
#       driver {..}_drv_jnt           - self.guide_joints: one per guide, flat under the root, driven by its sub
#                                       ctrl, skins its curve CV
#       spine  {prefix}_{i}_spine_jnt - self.spine_joints: spineJointCount chained joints along the curve,
#                                       driven by the spline IK (skin joints)
#       attach {..}_jnt               - self.attach_joints: one per guide, flat under the root, stuck to the
#                                       spine bone at the guide (no scale): child modules parent on them
#   CONTROLS (one pair per guide)
#       main   {..}_ctrl              - chained to the previous main (controls[0] reparented by MainBuild)
#       sub    {..}_sub_ctrl          - under its main, drives the driver joint (ParentCnstrMtx)
#       attach {..}_attach_grp        - under its main, stuck to the attach joint: parent of the child module
#                                       root ctrls (MainBuild)
#   SETUP
#       {prefix}_spine_crv: one CV per guide, each skinned 100% to its driver joint. Twist ('twistMethod'):
#           Advanced Twist : spline ikHandle on the spine joints, advanced twist (Object Rotation Up Start / End)
#                            between the first and last sub ctrl;
#           Up Curve       : {prefix}_spineUp_crv (guide points moved along the driver joints upVector, skinned
#                            to them), one {prefix}_{i}_spineUp_loc per spine joint attached on it; each spine
#                            joint rides the spine curve, aims at the next one, up toward its locator.
#       Stretch (curve length / rest length) and squash on the spine joints, 'stretch' / 'squash' on the
#       attributes host.
#
#   Builder
#       DATA        get_float, get_string, prefix, get_role_color, get_guide_positions, get_aim_axis
#       JOINTS      build_joints, get_skin_joints, create_spine_joints, create_attach_joints
#       CONTROLS    create_controls, create_spine_control
#       SETUP       create_setup, create_driven_curve, prepare_spine_chain, connect_setup, connect_advanced_twist,
#                   get_spine_scale, create_stretch, get_attach_driver, connect_attach_joints, create_attach_groups
#       UP CURVE    use_up_curve_twist, create_up_curve_twist
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from ..simpleBase.builder import Builder as BaseBuilder
from ..simpleIk.builder import Builder as SimpleIkBuilder
from ....utilities import joint_utilities
from ....utilities import ctrl_utilities
from ....utilities import curve_utilities
from ....utilities import skinCluster_utilities
from ....utilities import cnstrMtx_utilities
from ....utilities import attribute_utilities

from importlib import reload

reload(joint_utilities)
reload(ctrl_utilities)
reload(curve_utilities)
reload(skinCluster_utilities)
reload(cnstrMtx_utilities)
reload(attribute_utilities)


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
    DRIVER_JOINT_SUFFIX = "drv_jnt"
    # Child ctrl space per guide (MainBuild.parent_module_root_control looks it up first).
    ATTACH_GROUP_SUFFIX = "attach_grp"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.guide_joints = []
        self.spine_joints = []
        self.attach_joints = []
        self.attach_groups = []

        self.main_controls = []
        self.sub_controls = []

        self.curve = None
        self.ik_handle = None

        # Up Curve twist (create_up_curve_twist).
        self.up_curve = None
        self.up_locators = []
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

    def get_aim_axis(self):
        """Index (0, 1, 2) of the main component of aimVector: spine bone axis."""

        aim_vector = self.get_vector_attribute("aimVector", default=(1, 0, 0))

        return max(range(3), key=lambda k: abs(aim_vector[k]))

    # ======================================================
    # JOINTS
    # ======================================================

    def build_joints(self, suffix="jnt"):

        """
        Driver joints (flat under the root joint), root joint, spineJointCount
        spine joints along the guide curve, then one attach joint '{..}_{suffix}'
        per guide (found by MainBuild to parent child modules).
        self.joints = [root] + driver joints + spine joints + attach joints.
        """

        self.guide_joints = self.create_joints(suffix=self.DRIVER_JOINT_SUFFIX)

        if len(self.guide_joints) < 2:
            cmds.warning(f"Spine '{self.prefix}' : au moins 2 guides sont nécessaires.")

        self.create_root_joint(self.guide_joints[0])

        # Flat: each guide joint is driven by its sub ctrl.
        for joint in self.guide_joints:
            joint_utilities.parent_joint(joint, self.root_joint.name)

        self.spine_joints = self.create_spine_joints()
        self.attach_joints = self.create_attach_joints(suffix=suffix)

        self.joints = [self.root_joint] + self.guide_joints + self.spine_joints + self.attach_joints

        return self.joints

    def get_skin_joints(self):
        """Skin joints: the spine chain (not the root, driver nor attach joints)."""

        return list(self.spine_joints)

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

    def create_attach_joints(self, suffix="jnt"):

        """
        One joint '{side}_{baseName}_{index:02d}_{suffix}' per guide, matched on
        its driver joint, baked flat under the root joint (driven by
        connect_attach_joints).
        """

        attach_joints = []

        for driver in self.guide_joints:

            base_name, side, index = self.main.get_guide_naming(driver.guide)

            joint = joint_utilities.Joint(
                {"baseName": base_name, "side": side, "index": index, "guide": driver.guide},
                suffix=suffix
            )
            joint.create_joint()
            joint.match_transform(driver.name, matchPos=True, matchRot=True)

            joint_utilities.parent_joint(joint, self.root_joint.name)

            attach_joints.append(joint)

        return attach_joints

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        Per guide: a main ctrl '{..}_ctrl' chained to the previous main, and a
        sub ctrl '{..}_sub_ctrl' under it driving the driver joint.
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
        Hidden curve '{prefix}_spine_crv' (one CV per guide) in the module setup group,
        skinned 100% to the driver joints, then the spline ikHandle on the spine
        joints, or the Up Curve twist ('twistMethod'). Returns the setup nodes.
        """

        if len(self.guide_joints) < 2 or len(self.spine_joints) < 2:
            return []

        up_curve_twist = self.use_up_curve_twist()

        if not up_curve_twist:
            self.prepare_spine_chain()

        self.curve, self.skin_cluster = self.create_driven_curve(self.get_guide_positions(), f"{self.prefix}_spine_crv")

        # Up Curve: no ikHandle, the joints ride the curve and aim with up locators.
        if up_curve_twist:
            return [self.curve] + self.create_up_curve_twist()

        ik_handle, effector = cmds.ikHandle(
            startJoint=self.spine_joints[0].name,
            endEffector=self.spine_joints[-1].name,
            solver="ikSplineSolver",
            curve=self.curve,
            createCurve=False,
            parentCurve=False,
            name=f"{self.prefix}_splineIkHandle"
        )[:2]

        cmds.rename(effector, f"{self.prefix}_splineIkHandle_effector")

        ik_handle = self.parent_to_setup(ik_handle)

        cmds.setAttr(f"{ik_handle}.visibility", 0)

        self.ik_handle = ik_handle

        return [self.curve, self.ik_handle]

    def create_driven_curve(self, points, name, degree=3):

        """
        Hidden curve 'name' (one CV per point, 'degree') in the module setup group,
        inheritsTransform off, each CV skinned 100% to its driver joint. Returns
        (curve, skinCluster).
        """

        curve = self.parent_to_setup(curve_utilities.create_curve(points, name=name, degree=degree))

        # Deformed by its skin only.
        cmds.setAttr(f"{curve}.inheritsTransform", 0)
        cmds.setAttr(f"{curve}.visibility", 0)

        skin = skinCluster_utilities.skin_cvs_to_joints(curve, self.guide_joints, name=f"{name}_skin")

        return curve, skin

    # --------------------------------------------------
    # UP CURVE TWIST
    # --------------------------------------------------

    def use_up_curve_twist(self):
        """'Twist Method' = 'Up Curve': twist from an up curve instead of the spline IK advanced twist."""

        return self.get_string("twistMethod", "Advanced Twist") == "Up Curve"

    def create_up_curve_twist(self):

        """
        Up Curve twist, instead of the spline ikHandle:

            up curve : '{prefix}_spineUp_crv', the guide points moved by
                       upCurveOffset along the upVector of their driver joint,
                       skinned to the driver joints (the sub ctrls twist it);
            locators : '{prefix}_{i}_spineUp_loc', one per spine joint, attached
                       on the up curve at the closest point to the joint up
                       position (curve_utilities.create_locators_on_curve);
            joints   : spine joints on the spine curve, aimed at the next one,
                       up toward their locator (joint_utilities.attach_chain_to_curve).

        Returns the setup nodes.
        """

        aim_vector = self.get_vector_attribute("aimVector", default=(1, 0, 0))
        up_vector = self.get_vector_attribute("upVector", default=(0, 0, 1))
        distance = self.get_float("upCurveOffset", 2.0)

        def up_position(node):
            position = cmds.xform(node, query=True, worldSpace=True, translation=True)
            direction = joint_utilities.get_world_vector(node, up_vector)
            return [position[k] + direction[k] * distance for k in range(3)]

        self.up_curve, _ = self.create_driven_curve(
            [up_position(joint.name) for joint in self.guide_joints],
            f"{self.prefix}_spineUp_crv"
        )

        group = self.parent_to_setup(cmds.group(empty=True, name=f"{self.prefix}_spineUp_loc_grp"))

        cmds.setAttr(f"{group}.visibility", 0)

        self.up_locators = curve_utilities.create_locators_on_curve(
            self.up_curve,
            [up_position(joint.name) for joint in self.spine_joints],
            [f"{self.prefix}_{i:02d}_spineUp_loc" for i in range(len(self.spine_joints))],
            parent=group
        )

        joint_utilities.attach_chain_to_curve(
            self.spine_joints,
            self.curve,
            self.up_locators,
            aim_vector=aim_vector,
            up_vector=up_vector
        )

        return [self.up_curve, group]

    def prepare_spine_chain(self):

        """
        Before the ikHandle: rest offset of each spine joint (the first aside)
        moved to translate / jointOrient (move_offset_to_channels: the spline IK
        reads the bone lengths), parent.scale -> inverseScale (the parent stretch /
        squash does not shear the child).
        """

        for parent, joint in zip(self.spine_joints[:-1], self.spine_joints[1:]):

            joint_utilities.move_offset_to_channels(joint)

            if not cmds.listConnections(f"{joint.name}.inverseScale", source=True, destination=False):
                cmds.connectAttr(f"{parent.name}.scale", f"{joint.name}.inverseScale", force=True)

    def connect_setup(self):

        """
        Advanced twist (spline ikHandle only), then the stretch / squash, the
        attach joints and their child ctrl spaces.
        """

        if not self.curve or not self.sub_controls:
            return

        if self.ik_handle:
            self.connect_advanced_twist()

        self.create_stretch()
        self.connect_attach_joints()
        self.create_attach_groups()

    def connect_advanced_twist(self):

        """
        Spline IK advanced twist (Object Rotation Up Start / End): start follows
        the first sub ctrl, end the last one. Axes from aimVector / upVector.
        """

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

    def get_spine_scale(self):

        """
        World scale (X) plug of the root joint, read by a ScaleCnstrMtx on a hidden
        '{prefix}_stretchScale_grp' in the module setup group. 1.0 without root.
        """

        root = getattr(self, "root_joint", None)
        root = getattr(root, "name", root)

        if not root or not cmds.objExists(root):
            return 1.0

        group = f"{self.prefix}_stretchScale_grp"

        if not cmds.objExists(group):

            group = self.parent_to_setup(cmds.group(empty=True, name=group))

            cmds.setAttr(f"{group}.visibility", 0)

            self.constrain("scale", group, root, mo=False, dcmpMtx=True)

        return f"{group}.scaleX"

    def create_stretch(self):

        """
        Stretch + squash of the spine joints:

            stretch : spine curve length / (rest length * root scale), weighted by
                      'stretch' (0..1): aim axis scale of every spine joint but
                      the last (spline IK: the child translation follows; Up Curve:
                      the joints ride the curve, the scale gives the volume);
            squash  : stretch ^ -squash on the two other axes (scale) of every
                      spine joint, 'squash' (0..1): 0 = no scale, 0.5 = volume kept.

        'stretch' / 'squash' on the attributes host (first main ctrl by default).
        Returns the created nodes.
        """

        if not self.curve or not self.main_controls:
            return {}

        host = self.get_attributes_host(default=self.main_controls[0])

        attribute_utilities.add_attributes(host, "STRETCH", [
            {"name": "stretch", "default": 1.0, "minimum": 0.0, "maximum": 1.0},
            {"name": "squash", "default": 0.5, "minimum": 0.0, "maximum": 1.0},
        ])

        nodes = {}

        def node(node_type, name):
            nodes[name] = cmds.createNode(node_type, name=f"{self.prefix}_{name}")
            return nodes[name]

        def float_math(name, operation, a, b):
            fm = node("floatMath", name)
            cmds.setAttr(f"{fm}.operation", operation)
            for attr, value in (("floatA", a), ("floatB", b)):
                if isinstance(value, str):
                    cmds.connectAttr(value, f"{fm}.{attr}")
                else:
                    cmds.setAttr(f"{fm}.{attr}", value)
            return f"{fm}.outFloat"

        # World length of the deformed spine curve (inheritsTransform off: rig scale included).
        shape = curve_utilities.get_curve_shape(self.curve)

        curve_info = node("curveInfo", "spine_ci")
        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{curve_info}.inputCurve")

        rest_length = float_math("rest_length_fm", 2, self.get_spine_scale(), cmds.getAttr(f"{curve_info}.arcLength"))
        ratio = float_math("stretch_ratio_fm", 3, f"{curve_info}.arcLength", rest_length)

        stretch = node("blendTwoAttr", "stretch_bta")
        cmds.setAttr(f"{stretch}.input[0]", 1.0)
        cmds.connectAttr(ratio, f"{stretch}.input[1]")
        cmds.connectAttr(f"{host}.stretch", f"{stretch}.attributesBlender")
        stretch = f"{stretch}.output"

        squash_power = float_math("squash_power_fm", 2, f"{host}.squash", -1.0)
        squash = float_math("squash_fm", 6, stretch, squash_power)

        aim = self.get_aim_axis()
        aim_axis = "XYZ"[aim]

        for i, joint in enumerate(self.spine_joints):

            # Squash: two other axes of every spine joint.
            for k, axis in enumerate("XYZ"):
                if k != aim:
                    cmds.connectAttr(squash, f"{joint.name}.scale{axis}", force=True)

            # Stretch: aim axis scale of every spine joint but the last (the child translation follows).
            if i < len(self.spine_joints) - 1:
                cmds.connectAttr(stretch, f"{joint.name}.scale{aim_axis}", force=True)

        return nodes

    def get_attach_driver(self, position):

        """
        Spine joint holding 'position': start joint of the closest spine bone,
        or the last joint past the end of the last bone. Returns (driver, next
        joint or None, t along the bone 0..1).
        """

        point = om.MVector(position)

        positions = [
            om.MVector(cmds.xform(joint.name, query=True, worldSpace=True, translation=True))
            for joint in self.spine_joints
        ]

        best = None

        for i, (start, end) in enumerate(zip(positions[:-1], positions[1:])):

            bone = end - start
            length = bone * bone

            t = ((point - start) * bone) / length if length > 1e-12 else 0.0
            t = min(1.0, max(0.0, t))

            distance = (point - (start + bone * t)).length()

            if best is None or distance < best[0] - 1e-6:
                best = (distance, i, t)

        _, i, t = best

        if i == len(positions) - 2 and t >= 1.0 - 1e-6:
            return self.spine_joints[-1].name, None, 0.0

        return self.spine_joints[i].name, self.spine_joints[i + 1].name, t

    def connect_attach_joints(self):

        """
        Each attach joint follows the spine bone holding it (get_attach_driver),
        offset kept, scale removed:

            offset_a * driver.worldMatrix * root.worldInverseMatrix
            translation blended (t along the bone) with
            offset_b * next joint.worldMatrix * root.worldInverseMatrix
            -> pickMatrix (no scale / shear) -> attach.offsetParentMatrix

        Rotation from the driver, position sliding with the bone stretch.
        Returns the created nodes.
        """

        root = self.root_joint.name

        nodes = {}

        def follow(joint, driver, name):
            # Build offset of 'joint' to 'driver', in root joint space.
            offset = (
                om.MMatrix(cmds.getAttr(f"{joint}.worldMatrix[0]"))
                * om.MMatrix(cmds.getAttr(f"{driver}.worldInverseMatrix[0]"))
            )

            mult = cmds.createNode("multMatrix", name=f"{joint}_{name}_mm")
            cmds.setAttr(f"{mult}.matrixIn[0]", list(offset), type="matrix")
            cmds.connectAttr(f"{driver}.worldMatrix[0]", f"{mult}.matrixIn[1]")
            cmds.connectAttr(f"{root}.worldInverseMatrix[0]", f"{mult}.matrixIn[2]")

            return mult

        for joint in self.attach_joints:

            position = cmds.xform(joint.name, query=True, worldSpace=True, translation=True)
            driver, next_joint, t = self.get_attach_driver(position)

            created = [follow(joint.name, driver, "attach")]
            output = f"{created[0]}.matrixSum"

            # Position between the bone ends: follows the stretch on translate.
            if next_joint and t > 1e-6:

                created.append(follow(joint.name, next_joint, "attachNext"))

                blend = cmds.createNode("blendMatrix", name=f"{joint.name}_attach_bm")
                cmds.connectAttr(output, f"{blend}.inputMatrix")
                cmds.connectAttr(f"{created[-1]}.matrixSum", f"{blend}.target[0].targetMatrix")
                # Translation only, weighted by t.
                cmds.setAttr(f"{blend}.target[0].weight", 1.0)
                cmds.setAttr(f"{blend}.target[0].translateWeight", t)

                for attr in ("rotateWeight", "scaleWeight", "shearWeight"):
                    cmds.setAttr(f"{blend}.target[0].{attr}", 0)

                created.append(blend)
                output = f"{blend}.outputMatrix"

            pick = cmds.createNode("pickMatrix", name=f"{joint.name}_attach_pm")
            cmds.setAttr(f"{pick}.useScale", 0)
            cmds.setAttr(f"{pick}.useShear", 0)
            cmds.connectAttr(output, f"{pick}.inputMatrix")

            cmds.connectAttr(f"{pick}.outputMatrix", f"{joint.name}.offsetParentMatrix", force=True)

            nodes[joint.name] = created + [pick]

        return nodes

    def create_attach_groups(self):

        """
        Per guide, a group '{..}_{ATTACH_GROUP_SUFFIX}' under its main ctrl, stuck
        to its attach joint (ParentCnstrMtx into its offsetParentMatrix, no offset:
        same pose at build). MainBuild parents the child module root ctrls under it
        instead of the main ctrl: same hierarchy, but they follow the spine curve
        (stretch included). Returns the groups.
        """

        self.attach_groups = []

        for joint, control in zip(self.attach_joints, self.main_controls):

            base_name, side, index = self.main.get_guide_naming(joint.guide)

            group = cmds.group(empty=True, name=f"{side}_{base_name}_{index:02d}_{self.ATTACH_GROUP_SUFFIX}", parent=control)

            self.constrain("parent", group, joint.name, mo=False, dcmpMtx=False)

            self.attach_groups.append(group)

        return self.attach_groups
