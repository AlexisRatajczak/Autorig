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


# ==========================================================
# IK SPINE BUILDER
# ==========================================================
#
# Colonne en spline IK (ikSplineSolver) pilotée par un ctrl + sub ctrl
# par guide.
#
# JOINTS (sous le root joint {side}_{name}_{idx}_root_jnt, joints[0])
#   guide  {..}_jnt               -> self.guide_joints : un par guide, à plat
#                                    sous le root, piloté par son sub ctrl,
#                                    skinne son CV de la courbe
#   spine  {prefix}_{i}_spine_jnt -> self.spine_joints : spineJointCount
#                                    joints répartis le long de la courbe,
#                                    chaînés, pilotés par la spline IK
#                                    (joints de skin)
#
# CONTROLS (un couple par guide)
#   main {..}_ctrl     : chaîné au main du guide précédent (controls[0] =
#                        main du premier guide, reparenté par MainBuild)
#   sub  {..}_sub_ctrl : sous son main, pilote le joint du guide
#                        (ParentCnstrMtx)
#
# SETUP
#   courbe {prefix}_spine_crv : un CV par guide (degré 3 max), chaque CV
#   skinné à 100% au joint de son guide ; ikHandle spline sur les joints de
#   spine ; twist avancé (Object Rotation Up Start/End) entre le premier et
#   le dernier sub ctrl.
#
# Outils génériques : curve_utilities (courbe, points le long),
# skinCluster_utilities (skin des CVs), joint_utilities (create_chain,
# parent_joint), Builder de base (create_root_joint).
#

# Axe (aimVector / upVector du module) -> enums de l'ikHandle spline.
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
        """Attribut float / int du module, ou 'default'."""

        try:
            return float(self.data.get(key))
        except (TypeError, ValueError):
            return default

    def get_string(self, key, default):
        """Attribut enum (lu en string par PreBuild) du module, ou 'default'."""

        value = self.data.get(key)

        return value if isinstance(value, str) and value else default

    @property
    def prefix(self):
        """{side}_{baseName}_{index:02d}, d'après le root guide."""

        base_name, side, index = self.main.get_guide_naming(list(self.data["guides"])[0])

        return f"{side}_{base_name}_{index:02d}"

    def get_role_color(self, role):
        """Couleur du rig_data (ou défaut projet) pour le side du module et 'role'."""

        return self.main.get_color(self.data.get("side"), role)

    def get_guide_positions(self):
        """Positions monde des joints des guides."""

        return [cmds.xform(joint.name, query=True, worldSpace=True, translation=True) for joint in self.guide_joints]

    # ======================================================
    # JOINTS
    # ======================================================

    def build_joints(self, suffix="jnt"):

        """
        Joints des guides (à plat sous le root joint), root joint, puis
        spineJointCount joints de spine le long de la courbe des guides.
        self.joints = [root] + joints des guides + joints de spine.
        """

        self.guide_joints = self.create_joints(suffix=suffix)

        if len(self.guide_joints) < 2:
            cmds.warning(f"IkSpine '{self.prefix}' : au moins 2 guides sont nécessaires.")

        self.create_root_joint(self.guide_joints[0])

        # À plat : chaque joint de guide est piloté par son sub ctrl.
        for joint in self.guide_joints:
            joint_utilities.parent_joint(joint, self.root_joint.name)

        self.spine_joints = self.create_spine_joints()

        self.joints = [self.root_joint] + self.guide_joints + self.spine_joints

        return self.joints

    def create_spine_joints(self):

        """
        spineJointCount joints '{prefix}_{i:02d}_spine_jnt' (min 2) répartis à
        distance égale le long de la courbe des guides
        (curve_utilities.get_points_along_points), chaînés sous le root
        joint (joint_utilities.create_chain) : aimVector vers le joint
        suivant, up selon le joint de guide le plus proche.
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
        Pour chaque guide : un main ctrl '{..}_ctrl' chaîné au main du guide
        précédent, et un sub ctrl '{..}_sub_ctrl' sous lui, qui pilote le
        joint du guide (connect_control). Retourne mains puis subs
        (controls[0] = premier main).
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
        Ctrl 'name' matché (position + orientation) sur 'match', décalage de
        shape du module (shapeTranslate / Rotate / Scale), sous 'parent'
        (CTRL_grp par défaut). Retourne son nom.
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
        Courbe '{prefix}_spine_crv' (un CV par guide) sous MISC_grp, cachée,
        skinnée à 100% aux joints des guides (skinCluster_utilities), et ikHandle
        spline sur les joints de spine. Retourne les nodes de setup.
        """

        if len(self.guide_joints) < 2 or len(self.spine_joints) < 2:
            return []

        misc = self.get_misc_group()

        curve = curve_utilities.create_curve(self.get_guide_positions(), name=f"{self.prefix}_spine_crv")

        if misc:
            curve = cmds.parent(curve, misc)[0]

        # Déformée par son skin seulement.
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
        Twist avancé de la spline IK (Object Rotation Up Start/End) : le
        début suit le premier sub ctrl, la fin le dernier. Axes d'après
        aimVector / upVector du module.
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

        # Up dans l'espace des sub ctrls (orientés comme les joints des guides).
        cmds.setAttr(f"{handle}.dWorldUpVector", *up_vector)
        cmds.setAttr(f"{handle}.dWorldUpVectorEnd", *up_vector)

        cmds.connectAttr(f"{self.sub_controls[0]}.worldMatrix[0]", f"{handle}.dWorldUpMatrix", force=True)
        cmds.connectAttr(f"{self.sub_controls[-1]}.worldMatrix[0]", f"{handle}.dWorldUpMatrixEnd", force=True)
