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


# ==========================================================
# SIMPLE IK BUILDER
# ==========================================================
#
# IK simple sur la chaîne de joints du module : un ctrl root sur le
# premier joint (pilote la base de la chaîne), un ctrl IK à la position
# du dernier joint (pilote l'ikHandle + l'orientation du dernier
# joint), et un ctrl pole vector (si la chaîne compte au moins 3
# joints) qui pilote le coude/genou de l'ikHandle.
#
# Les trois ctrls partagent toujours le même parent (voir
# parent_ik_controls). En mode 'No Ctrl', ils sont remplacés par des
# joints dédiés portant directement la shape ({..}_rootCtrl_jnt,
# {..}_ikCtrl_jnt et {..}_pole_jnt), parentés comme la racine du module
# (joint du guide parent, sinon JNT_grp).
#

class Builder(BaseBuilder):

    IK_CONTROL_SHAPE = "cube"
    IK_CONTROL_COLOR_TYPE = "IK Main"

    POLE_CONTROL_SHAPE = "diamond"
    POLE_CONTROL_COLOR_TYPE = "IK Secondary"

    ROOT_CONTROL_SHAPE = "square"
    ROOT_CONTROL_COLOR_TYPE = "IK Main"

    # Suffixes des joints-ctrls créés en mode 'No Ctrl'.
    ROOT_CONTROL_JOINT_SUFFIX = "rootCtrl_jnt"
    IK_CONTROL_JOINT_SUFFIX = "ikCtrl_jnt"
    POLE_CONTROL_JOINT_SUFFIX = "pole_jnt"

    # Distance du ctrl pole vector par rapport au joint du milieu,
    # proportionnelle à la longueur de la chaîne (root -> end).
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
        Un ctrl root sur le premier joint (controls[0] : reparenté au
        ctrl du module parent par MainBuild.parent_ctrls_module), un ctrl
        IK à la position du dernier joint, et un ctrl pole vector si la
        chaîne a de quoi former un coude/genou.
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
        Ctrl root, positionné/orienté sur le premier guide de la chaîne
        (joint-ctrl en mode 'No Ctrl', voir create_control_joint). Il
        pilote le premier joint (voir connect_setup) : sa rotation reste
        libre pour l'ikHandle, qui tourne la chaîne par-dessus.
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
        Ctrl IK '{side}_{baseName}_{index}_{suffix}', positionné sur le
        dernier joint de 'joints' (self.joints par défaut) et orienté
        comme lui (sinon aligné au monde), sous CTRL_grp - joint-ctrl en
        mode 'No Ctrl' (voir create_control_joint).

        joints         : chaîne IK (ex: limb -> self.ik_joints).
        match_rotation : matcher l'orientation du joint (sinon monde).
        adjust_shape   : appliquer shapeTranslate/Rotate/Scale du module.
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
        Ctrl pole vector '{side}_{baseName}_{index}_{suffix}', positionné
        devant le joint du milieu de 'joints' (self.joints par défaut),
        sous CTRL_grp (aucun ctrl si la chaîne a moins de 3 joints, ou si
        l'option 'Rotate Plane Solver' est désactivée : un ikSCsolver
        n'a pas de pole vector).
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

        # Orientation : monde (défaut) ou celle du joint du milieu.
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
        Mode 'No Ctrl' : joint dédié '{side}_{baseName}_{index}_{suffix}'
        qui porte directement la shape du ctrl (Control.transfer_to_joint).
        Matché sur 'guide' (position + rotation), ou placé à 'position'
        (monde) aligné au monde si fournie. Son transform est baké dans
        son offsetParentMatrix (Joint.freeze_transform), puis il est
        parenté comme la racine du module (MainBuild.parent_module_root :
        joint du guide parent, sinon JNT_grp) - jamais sous la chaîne IK
        qu'il pilote.
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

            # Orientation de 'rotation_from' (sinon alignée au monde).
            if rotation_from and cmds.objExists(rotation_from):
                cmds.matchTransform(joint.name, rotation_from, rotation=True)

        joint.freeze_transform()

        # Shape construite sur un transform temporaire puis transférée
        # (relative) : ses CV sont déjà dans l'espace local du joint.
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

        """
        Projette 'mid' sur la droite start->end, puis place le pole
        vector devant 'mid' dans la direction opposée à cette
        projection, à une distance proportionnelle à POLE_DISTANCE.
        """

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

        """
        Couleur configurée sur le rig_data (ou son défaut projet) pour
        le side du module et le rôle donné (ex: 'IK Main').
        """

        return self.main.get_color(self.data.get("side"), color_type)

    # ======================================================
    # SETUP
    # ======================================================

    def rotate_plane_solver(self):

        """
        Option 'Rotate Plane Solver' du module (attributes.json) : ikRPsolver
        + pole vector, sinon ikSCsolver sans pole. Activée par défaut (y
        compris pour un module construit avant l'ajout de l'option).
        """

        value = self.data.get("rotatePlaneSolver")

        return True if value is None else bool(value)

    def ik_ctrl_world(self):
        """Option 'IK Ctrl Orientation' = World : ctrl IK aligné au monde (sinon orienté comme le dernier joint)."""

        return self.data.get("ikCtrlOrient") == "World"

    def pole_ctrl_joint(self):
        """Option 'Pole Ctrl Orientation' = Joint : ctrl pole orienté comme le joint du milieu (sinon monde)."""

        return self.data.get("poleCtrlOrient") == "Joint"

    def use_stretch(self):
        """Option 'Stretch' du module (attributes.json) : stretch + lock de coude (stretch_ik)."""

        return bool(self.data.get("stretchIk", 0))

    def create_setup(self, joints=None):

        """
        Crée l'ikHandle sur 'joints' (self.joints par défaut ; ex: limb ->
        self.ik_joints), sous MISC_grp et caché (ikRPsolver si l'option
        'Rotate Plane Solver' est active, ikSCsolver sinon).
        """

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
        Connecte, sur 'joints' (self.joints par défaut) : le ctrl root au
        premier joint, le ctrl IK à l'ikHandle et à l'orientation du
        dernier joint, et le ctrl pole vector au coude/genou de
        l'ikHandle.
        """

        joints = self.joints if joints is None else joints

        if self.root_control and joints:
            cnstrMtx_utilities.ParentCnstrMtx(joints[0].name, self.root_control, dcmpMtx=False)

        if not self.ik_handle:
            return

        if self.ik_control:

            # RP : position seule - la rotation de l'ikHandle ferait tourner
            # le plan de la chaîne avec le ctrl IK (le pole seul doit le
            # définir). SC (sans pole) : sa rotation oriente la chaîne, elle
            # suit le ctrl (maintain offset : pas de saut au build).
            if self.rotate_plane_solver():
                cnstrMtx_utilities.PointCnstrMtx(self.ik_handle, self.ik_control, dcmpMtx=False)
            else:
                cnstrMtx_utilities.ParentCnstrMtx(self.ik_handle, self.ik_control, mo=True, dcmpMtx=False)

            # Orientation du dernier joint : son propre réseau, indépendant de l'ikHandle.
            self.orient_end_joint(joints[-1].name, mo=self.ik_ctrl_world())

        if self.pole_control and self.rotate_plane_solver():
            cnstrMtx_utilities.PoleVectorCnstr(self.ik_handle, self.pole_control)
            self.add_pole_flip(self.ik_handle, self.pole_control)

        # Après orient_end_joint (il écrit l'offsetParentMatrix du dernier joint).
        if self.use_stretch():
            self.stretch_ik(joints)

    def orient_end_joint(self, end_joint=None, mo=False):

        """
        Oriente le dernier joint sur le ctrl IK, sans maintain offset, en
        matrices uniquement (pas de decomposeMatrix) :

            rotation    = pickMatrix(ik_ctrl.worldMatrix, rotation seule)
            position    = pickMatrix(translation de repos * parent.worldMatrix,
                          translation seule) : bout de l'os, stretch compris
            offsetParentMatrix = rotation * position * parent.worldInverseMatrix

        La matrice monde du joint vaut donc exactement rotation * position,
        quel que soit le scale (stretch / squash) de son parent : le
        parentInverseMatrix annule aussi ce scale. inverseScale est
        déconnecté (il le compenserait une seconde fois).

        Pas de cycle : les connexions du joint vers l'ikEffector (translate,
        offsetParentMatrix...) sont figées à leur valeur actuelle
        (freeze_effector_inputs) : l'effecteur reste au bout de l'os dans
        l'espace du joint parent, stretch compris.

        end_joint : joint à orienter (dernier de self.joints par défaut).
        mo        : maintain offset de rotation (ctrl IK aligné au monde) :
                    rotation = offset * rotation du ctrl, offset = écart
                    joint / ctrl au build (le joint garde son orientation).

        Retourne les nodes créés.
        """

        end_joint = end_joint or self.joints[-1].name

        rest_translate = cmds.getAttr(f"{end_joint}.offsetParentMatrix")[12:15]

        # Matrices lues sur le joint PARENT (et non parentMatrix /
        # parentInverseMatrix du joint) : le réseau ne repart jamais du
        # joint qu'il pilote -> pas de cycle (l'évaluation se fait par node).
        parent = cmds.listRelatives(end_joint, parent=True, fullPath=True)[0]

        def pick(name, matrix_plug, translate, rotate):
            node = cmds.createNode("pickMatrix", name=f"{end_joint}_{name}")
            cmds.connectAttr(matrix_plug, f"{node}.inputMatrix", force=True)
            cmds.setAttr(f"{node}.useTranslate", translate)
            cmds.setAttr(f"{node}.useRotate", rotate)
            cmds.setAttr(f"{node}.useScale", 0)
            cmds.setAttr(f"{node}.useShear", 0)
            return node

        # Rotation monde du ctrl IK.
        rotation = pick("orient_rot_pm", f"{self.ik_control}.worldMatrix[0]", 0, 1)
        rotation_plug = f"{rotation}.outputMatrix"

        # Maintain offset : écart de rotation joint / ctrl au build.
        if mo:

            joint_rotation = om.MTransformationMatrix(om.MMatrix(cmds.getAttr(f"{end_joint}.worldMatrix[0]"))).asRotateMatrix()
            ctrl_rotation = om.MTransformationMatrix(om.MMatrix(cmds.getAttr(f"{self.ik_control}.worldMatrix[0]"))).asRotateMatrix()

            offset = cmds.createNode("holdMatrix", name=f"{end_joint}_orient_offset_hm")
            cmds.setAttr(f"{offset}.inMatrix", list(joint_rotation * ctrl_rotation.inverse()), type="matrix")

            offset_rotation = cmds.createNode("multMatrix", name=f"{end_joint}_orient_offset_mm")
            cmds.connectAttr(f"{offset}.outMatrix", f"{offset_rotation}.matrixIn[0]", force=True)
            cmds.connectAttr(rotation_plug, f"{offset_rotation}.matrixIn[1]", force=True)

            rotation_plug = f"{offset_rotation}.matrixSum"

        # Position monde du bout de l'os : translation de repos dans
        # l'espace (scalé) du parent.
        rest = cmds.createNode("composeMatrix", name=f"{end_joint}_orient_rest_cm")

        cmds.setAttr(f"{rest}.inputTranslate", *rest_translate)

        tip = cmds.createNode("multMatrix", name=f"{end_joint}_orient_tip_mm")
        cmds.connectAttr(f"{rest}.outputMatrix", f"{tip}.matrixIn[0]", force=True)
        cmds.connectAttr(f"{parent}.worldMatrix[0]", f"{tip}.matrixIn[1]", force=True)

        position = pick("orient_pos_pm", f"{tip}.matrixSum", 1, 0)

        # offsetParentMatrix = monde voulu * parentInverseMatrix.
        mult = cmds.createNode("multMatrix", name=f"{end_joint}_orient_mm")
        cmds.connectAttr(rotation_plug, f"{mult}.matrixIn[0]", force=True)
        cmds.connectAttr(f"{position}.outputMatrix", f"{mult}.matrixIn[1]", force=True)
        cmds.connectAttr(f"{parent}.worldInverseMatrix[0]", f"{mult}.matrixIn[2]", force=True)

        # Canaux locaux neutres : seule l'offsetParentMatrix place le joint.
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
        Déconnecte les attributs de 'joint' qui alimentent un ikEffector
        (l'ikHandle les connecte à sa création) en gardant leur valeur
        actuelle sur l'effecteur : piloter ensuite le joint ne repasse
        plus par l'effecteur (pas de cycle avec l'IK).
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
        Attribut enum 'poleFlip' (Positive / Negative) sur le ctrl pole :
        Negative inverse le poleVector de l'ikHandle (multiplyDivide * -1
        entre la contrainte et ikHandle.poleVector) - le plan de la chaîne
        passe de l'autre côté. Retourne le multiplyDivide, ou None si le
        poleVector n'est pas connecté.
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
        Stretch + lock + squash sur une chaîne IK d'au moins 2 joints :

            stretch : distance root -> ctrl IK au-delà de la longueur de la
                      chaîne -> facteur distance / longueur (1 en dessous),
                      limité à 'stretchLimit' (ctrl IK), appliqué à tous les
                      os, dosé par 'stretch' (0..1, ctrl IK) ;
            lock    : (si ctrl pole) le joint du milieu (joints[n // 2],
                      comme create_pole_control) est amené sur le pole : os
                      du haut * dist(root, pole) / longueur du haut, os du
                      bas * dist(pole, ik) / longueur du bas, dosé par
                      'lock' (0..1, ctrl pole) ;
            squash  : facteur ^ -squash sur les deux autres axes,
                      'squash' (0..1, ctrl IK) : 0 = pas de scale,
                      0.5 = volume conservé, 1 = inverse du stretch.

        Le facteur pilote le scale du joint qui porte chaque os sur l'axe de
        l'aimVector (stretch : la translation de l'enfant s'allonge avec
        lui), le squash ses deux autres axes ; le dernier joint reçoit le
        squash du dernier os. La rotation de repos des enfants passe dans
        leur jointOrient, leur inverseScale est connecté : pas de
        cisaillement. À appeler après connect_setup (orient_end_joint pilote
        l'offsetParentMatrix du dernier joint).

        joints       : chaîne IK (self.joints par défaut ; ex: limb -> self.ik_joints).
        root         : node ou plug de matrice de départ des distances (par
                       défaut la position du premier joint, sans son scale).
        pole_control : ctrl pole (None = self.pole_control) ; False = pas de lock.
        ik_control   : ctrl IK (self.ik_control par défaut) : cible des distances.
        pivot        : index du joint amené sur le pole par le lock (None =
                       joints[n // 2], comme create_pole_control).
        host         : porteur des attributs stretch / stretchLimit / squash
                       (ik_control par défaut) : partagé par plusieurs IK
                       (ex: legQuadruped).

        Mémorise self.ik_stretch_segments : [(position de départ, position
        de fin, plug du facteur de stretch, plug du squash)] par os, à la
        pose de build (utilisé par ribbon.connect_follicle_scale).

        Retourne les nodes créés, ou {} si la chaîne a moins de 2 joints
        ou s'il n'y a pas de ctrl IK.
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
            # Node -> son worldMatrix ; un plug de matrice est gardé tel quel.
            return item if "." in item else f"{item}.worldMatrix[0]"

        def distance(name, start, end):
            db = node("distanceBetween", name)
            cmds.connectAttr(world(start), f"{db}.inMatrix1")
            cmds.connectAttr(world(end), f"{db}.inMatrix2")
            return f"{db}.distance"

        # Départ des distances : 'root', sinon la position du premier joint
        # sans rien lire SUR ce joint (son scale est piloté par le stretch :
        # le relire ferait un cycle, l'évaluation se fait par node) :
        # offsetParentMatrix (sa source si elle est connectée, sinon sa
        # valeur) * worldMatrix de son parent. Ses canaux sont figés
        # (Joint.freeze_transform) : son translate vaut 0.
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

        # Os = joints enfants (joints[1:]), longueur au repos = translation
        # de leur offsetParentMatrix.
        bones = [joint.name for joint in joints[1:]]
        lengths = [om.MVector(cmds.getAttr(f"{bone}.offsetParentMatrix")[12:15]).length() for bone in bones]

        # Longueurs à l'échelle du rig : * scale monde du joint root
        # (ScaleCnstrMtx, get_chain_scale) - pas de stretch quand le rig est scalé.
        chain_scale = self.get_chain_scale(joints, prefix)

        def scaled(name, length):
            return float_math(name, 2, chain_scale, length)

        chain_length = scaled("chain_length_fm", sum(lengths))

        # Stretch : distance / longueur au-delà de la longueur, limité.
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

        # Squash : exposant -squash, réglé sur le ctrl IK.
        self.add_stretch_attribute(host, "squash", 0.5, maximum=1.0)

        squash_power = float_math("squash_power_fm", 2, f"{host}.squash", -1.0)

        # Lock : os du haut (jusqu'au joint du milieu) et du bas, vers le pole.
        pivot = len(joints) // 2 if pivot is None else int(pivot)

        if pole_control and 0 < pivot < len(joints) - 1:

            self.add_stretch_attribute(pole_control, "lock", 0.0, maximum=1.0)

            upper, lower = slice(0, pivot), slice(pivot, len(bones))

            lock_up = float_math("lock_up_fm", 3, distance("lock_up_db", root, pole_control), scaled("lock_up_length_fm", sum(lengths[upper])))
            lock_down = float_math("lock_down_fm", 3, distance("lock_down_db", pole_control, ik_control), scaled("lock_down_length_fm", sum(lengths[lower])))

            up = blend("up_bta", stretch, lock_up, f"{pole_control}.lock")
            down = blend("down_bta", stretch, lock_down, f"{pole_control}.lock")

            factors = [up] * pivot + [down] * (len(bones) - pivot)

        # Axe de l'os : composante dominante de l'aimVector du module.
        aim_vector = self.get_vector_attribute("aimVector", default=(1.0, 0.0, 0.0))
        aim = max(range(3), key=lambda k: abs(aim_vector[k]))

        squash = None

        self.ik_stretch_segments = []

        for i, (parent, bone, factor) in enumerate(zip(joints[:-1], bones, factors), start=1):

            # L'enfant ne doit pas hériter du scale non uniforme du parent
            # (cisaillement) : rotation de repos de son offsetParentMatrix ->
            # jointOrient (offsetParentMatrix = translation de repos seule),
            # et parent.scale -> inverseScale. Dernier joint : son
            # offsetParentMatrix (orient_end_joint) annule déjà le scale du
            # parent.
            if not cmds.listConnections(f"{bone}.offsetParentMatrix", source=True, destination=False):

                self.move_rest_rotation_to_joint_orient(bone)

                if not cmds.listConnections(f"{bone}.inverseScale", source=True, destination=False):
                    cmds.connectAttr(f"{parent.name}.scale", f"{bone}.inverseScale", force=True)

            # Stretch : scale du joint qui porte l'os sur l'axe de l'aimVector
            # (la translation de l'enfant, dans l'espace du parent, s'allonge
            # avec lui). Squash : facteur ^ -squash sur les deux autres axes.
            squash = float_math(f"{i:02d}_squash_fm", 6, factor, squash_power)

            for k, axis in enumerate("XYZ"):
                cmds.connectAttr(factor if k == aim else squash, f"{parent.name}.scale{axis}", force=True)

            self.ik_stretch_segments.append((
                cmds.xform(parent.name, query=True, worldSpace=True, translation=True),
                cmds.xform(bone, query=True, worldSpace=True, translation=True),
                factor,
                squash
            ))

        # Dernier joint : il ne porte pas d'os, mais garde l'épaisseur du
        # dernier os (squash sur ses deux axes perpendiculaires à l'os, pas
        # de stretch : il n'a pas d'enfant à éloigner).
        if squash:
            for k, axis in enumerate("XYZ"):
                if k != aim:
                    cmds.connectAttr(squash, f"{joints[-1].name}.scale{axis}", force=True)

        return nodes

    def prepare_ik_chain(self, joints):

        """
        Chaîne IK classique avant la création de l'ikHandle : la rotation de
        repos de chaque joint (sauf le premier, piloté par son ctrl / son
        root) passe de l'offsetParentMatrix au jointOrient
        (move_rest_rotation_to_joint_orient, pose inchangée). Les joints
        figés (Joint.freeze_transform) portent leur pliage dans
        l'offsetParentMatrix : le solver RP, qui se repère sur jointOrient /
        rotate, pouvait résoudre la chaîne du côté opposé au pole.
        """

        for joint in joints[1:]:

            name = getattr(joint, "name", joint)

            if not cmds.listConnections(f"{name}.offsetParentMatrix", source=True, destination=False):
                self.move_rest_rotation_to_joint_orient(name)

    @staticmethod
    def move_rest_rotation_to_joint_orient(joint):

        """
        Rotation de l'offsetParentMatrix de 'joint' déplacée dans son
        jointOrient : offsetParentMatrix = translation seule, pose monde
        inchangée (rotate est appliqué avant jointOrient, comme avant
        l'offsetParentMatrix). Sans effet si elle n'a pas de rotation.
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
        Plug du scale monde (X) du joint root de la chaîne : root joint du
        module (self.root_joint, ex: limb), sinon le parent du premier
        joint - jamais le premier joint lui-même (son scale est piloté par
        le stretch : cycle). Lu par une ScaleCnstrMtx sur un groupe caché
        '{prefix}_stretchScale_grp' sous MISC_grp. 1.0 sans root.
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
        """Attribut float keyable 'attr' sur 'control' (bornes optionnelles), s'il n'existe pas."""

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
        Place les ctrls IK et pole vector sous le même parent que le
        ctrl de référence (ctrl root, sinon ctrl IK).
        MainBuild.parent_ctrls_module ne reparente que controls[0] vers
        le ctrl du module parent : les autres, restés sous CTRL_grp, le
        rejoignent ici. Position monde préservée ; sans offset group,
        l'offsetParentMatrix est re-baké pour le nouveau parent (canaux
        propres). En mode 'No Ctrl', les joints-ctrls ont déjà le même
        parent (voir create_control_joint) : rien à faire.
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
        """Offset group du ctrl s'il existe, sinon le ctrl lui-même."""

        offset = self.main.get_offset_group(control)

        return offset if offset and cmds.objExists(offset) else control

    def create_space_switches(self):

        """
        Space switch du ctrl root (spaceSwitchTargets, comme le ctrl
        racine du Builder de base), du ctrl IK (ikSpaceSwitchTargets) et
        du ctrl pole vector (poleSpaceSwitchTargets).
        Appelé après MainBuild.parent_ctrls_module : on y regroupe d'abord
        le pole sous le parent final du ctrl IK (parent_ik_controls),
        pour que l'espace "Local" de chaque switch soit le bon.
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
