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


# ==========================================================
# LEG QUADRUPED BUILDER
# ==========================================================
#
# Limb à 4 joints : hanche (0) -> genou (1) -> jarret (2) -> pied (3).
# Tout est hérité de limb (FK, switch IK/FK, root, ruban), sauf l'IK,
# reconstruit en deux ikHandles selon l'attribut 'quadrupedIkMethod' :
#
#   SC_RP : SC 0 -> 1 piloté par le ctrl genou (knee_ctrl), puis
#           RP 1 -> 3 piloté par le ctrl IK, pole devant le jarret ;
#   RP_RP : RP 0 -> 2 piloté par le ctrl jarret (hock_ctrl), pole devant
#           le genou, puis RP 1 -> 3 piloté par le ctrl IK, sans pole vector
#           (un seul pole, sur le premier RP) ;
#   RP_SC : RP 0 -> 2 piloté par le ctrl jarret (hock_ctrl), pole devant
#           le genou, puis SC 2 -> 3 piloté par le ctrl IK.
#
# L'ikHandle du ctrl secondaire vise une cible qui glisse vers la ligne
# hanche -> pied quand la jambe approche de son extension (attribut
# 'straightenStart' du ctrl IK) : la jambe se tend droite et le stretch
# l'allonge sans la replier (drive_secondary_handle).
#
# Le ctrl secondaire (genou / jarret) et le pole sont sous le root ctrl
# et suivent le ctrl IK en translation par des space blends (attributs
# '<nom>Blend' du ctrl IK, 0.5 par défaut). Le dernier joint prend
# l'orientation du ctrl IK (simpleIk.orient_end_joint).
#
# Stretch (option 'stretchIk') : simpleIk.stretch_ik sur TOUTE la jambe
# (hanche -> ctrl IK, longueur des 3 os), comme un simple IK : la jambe
# s'étire dès qu'elle est entièrement tendue, quel que soit le ctrl
# secondaire. Attributs stretch / stretchLimit / squash sur le ctrl IK,
# lock du joint qui a le pole ('lock_joint') sur le pole.
#

IkBuilder = limb_builder.IkBuilder


# Description des méthodes :
#   secondary : (index du joint, nom) du ctrl secondaire.
#   handles   : (début, fin, solver, ctrl pilote, pole) - "secondary",
#               "ik" ; pole "pole" (self.pole_control) ou None.
#   lock_joint : index du joint amené sur le pole par le lock du stretch
#                (milieu de l'ikHandle qui a le pole).
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

    # Extension (distance hanche -> pied / longueur de la jambe) à partir de
    # laquelle la cible du ctrl secondaire glisse vers la ligne hanche -> pied.
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
        """Description (METHODS) de la méthode choisie par 'quadrupedIkMethod'."""

        name = self.get_string("quadrupedIkMethod", DEFAULT_METHOD)

        return METHODS.get(name, METHODS[DEFAULT_METHOD])

    def get_rig_node(self, key):
        """Node désigné dans METHODS : "secondary", "ik", "pole" (None sinon)."""

        return {
            "secondary": self.secondary_control,
            "ik": self.ik_control,
            "pole": self.pole_control,
        }.get(key)

    def get_secondary_name(self):
        """Nom du ctrl secondaire de la méthode ("knee" / "hock")."""

        return self.get_method()["secondary"][1]

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):
        """Ctrls du limb, puis ctrl secondaire, rangé sous le root ctrl."""

        controls = super().create_controls()

        if self.secondary_control:
            self.parent_under_root(self.secondary_control)
            controls.append(self.secondary_control)

        return controls

    def create_ik_step(self):

        """
        Ctrl IK sur le dernier joint IK (pied), pole de l'ikHandle de la
        méthode qui en a un, et ctrl secondaire (genou ou jarret).
        Retourne (ctrl IK, pole) comme limb.
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
        """Pole vector devant le joint du milieu de 'joints' (simpleIk.create_pole_control)."""

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
        Ctrl secondaire '{side}_{baseName}_{index}_{knee|hock}_ctrl' sur son
        joint IK (position + orientation), sous CTRL_grp (rangé sous le
        root ctrl par create_controls). En mode 'No Ctrl' : joint-ctrl
        (simpleIk.create_control_joint).
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
        Les deux ikHandles de la méthode, sous MISC_grp et cachés (RP
        remplacé par SC si 'Rotate Plane Solver' est désactivé).
        Retourne les ikHandles.
        """

        if len(self.ik_joints) != 4:
            return []

        self.ik_handles = []

        # Pliage de repos dans les jointOrient avant les ikHandles (voir
        # simpleIk.prepare_ik_chain).
        IkBuilder.prepare_ik_chain(self, self.ik_joints)

        for start, end, solver, _, _ in self.get_method()["handles"]:

            if solver == "ikRPsolver" and not self.rotate_plane_solver():
                solver = "ikSCsolver"

            suffix = "rpIkHandle" if solver == "ikRPsolver" else "scIkHandle"

            self.ik_handles.append(
                self.create_ik_handle(self.ik_joints[start], self.ik_joints[end], solver, suffix)
            )

        # simpleIk / limb ne connaissent qu'un ikHandle : le dernier (pied).
        self.ik_handle = self.ik_handles[-1]

        return list(self.ik_handles)

    def create_ik_handle(self, start_joint, end_joint, solver, suffix):

        """
        ikHandle '{side}_{baseName}_{index}_{suffix}' de 'start_joint' à
        'end_joint' (Joint), sous MISC_grp et caché.
        """

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
        Chaque ikHandle suit son ctrl pilote en position seulement (+ son
        pole s'il est RP) - celui du ctrl secondaire via
        drive_secondary_handle -, dernier joint orienté sur le ctrl IK, puis
        stretch si l'option est active.
        """

        if len(self.ik_handles) != len(self.get_method()["handles"]):
            return

        for ik_handle, (_, _, _, driver, pole) in zip(self.ik_handles, self.get_method()["handles"]):

            driver_node = self.get_rig_node(driver)
            pole_node = self.get_rig_node(pole)

            solver = cmds.nodeType(cmds.listConnections(f"{ik_handle}.ikSolver")[0])
            has_pole = bool(pole_node) and solver == "ikRPsolver"

            # Position seule (pointConstraint) : la rotation de l'ikHandle
            # reste celle de sa création. Un SC oriente la chaîne d'après la
            # rotation de son ikHandle : la lui faire suivre ferait rouler
            # les joints.
            if driver == "secondary" and driver_node and self.ik_control:
                self.drive_secondary_handle(ik_handle)

            elif driver_node:
                cnstrMtx_utilities.PointCnstrMtx(ik_handle, driver_node, dcmpMtx=False)

            if has_pole:
                cnstrMtx_utilities.PoleVectorCnstr(ik_handle, pole_node)
                IkBuilder.add_pole_flip(self, ik_handle, pole_node)

        if self.ik_control:
            IkBuilder.orient_end_joint(self, self.ik_joints[-1].name, mo=self.ik_ctrl_world())

        # Après orient_end_joint (il écrit l'offsetParentMatrix du dernier joint).
        if self.use_stretch():
            self.stretch_quadruped()

    def get_hip_matrix(self, prefix):

        """
        Matrice monde (plug) de la hanche (premier joint IK) sans lire ce
        joint (son scale est piloté par le stretch : cycle) : son
        offsetParentMatrix (source si connecté, sinon valeur) * worldMatrix
        de son parent.
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
        L'ikHandle du ctrl secondaire vise une cible (dans son offsetParentMatrix,
        translation seule) entre :

            ctrl secondaire          : jambe pliée ;
            point de la ligne        : hanche + (pied - hanche) * longueur
              hanche -> pied           jusqu'au joint secondaire / longueur
                                       totale - sa place sur la jambe tendue,
                                       stretch compris ;

        mélange w = (extension - straightenStart) / (1 - straightenStart),
        clampé 0..1, extension = distance hanche -> ctrl IK / longueur de la
        jambe. À extension 1 et au-delà la cible est sur la ligne : la jambe
        est droite et le stretch l'allonge sans la replier.
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

        # Extension de la jambe.
        distance = cmds.createNode("distanceBetween", name=f"{prefix}_extension_db")
        cmds.connectAttr(hip, f"{distance}.point1")
        cmds.connectAttr(foot, f"{distance}.point2")

        # Longueur de la jambe à l'échelle du rig (simpleIk.get_chain_scale).
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

        # w = (extension - start) / (1 - start), clampé 0..1.
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

        # Point de la ligne hanche -> pied.
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

        # Cible = ctrl secondaire -> point de la ligne (w).
        target = cmds.createNode("blendColors", name=f"{prefix}_target_bc")
        cmds.connectAttr(f"{line}.output3D", f"{target}.color1")
        cmds.connectAttr(secondary, f"{target}.color2")
        cmds.connectAttr(f"{clamp}.outputR", f"{target}.blender")

        # Monde -> espace du parent de l'ikHandle, dans son offsetParentMatrix.
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
        Stretch de toute la jambe (simpleIk.stretch_ik sur les 4 joints IK) :
        distance hanche -> ctrl IK sur la longueur des 3 os, appliquée à
        tous les os dès que la jambe est entièrement tendue - pas segment
        par segment vers le ctrl secondaire, qui ne suit le pied qu'en
        partie (blend) et ne se tendrait jamais en même temps. Lock du joint
        'lock_joint' de la méthode sur le pole. Attributs sur le ctrl IK.
        Retourne les nodes créés.
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
        """Visibilité du limb, plus le ctrl secondaire avec les ctrls IK."""

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
        Space switches du limb (racine FK, ctrl IK, pole), puis space
        blends du ctrl secondaire et du pole vers le ctrl IK. Après
        MainBuild.parent_ctrls_module : l'espace local de chaque blend est
        le parent final du ctrl.
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
        Space blend en translation de 'control' entre son parent (espace
        local, 0) et le ctrl IK (1), piloté par 'attr' (float 0..1) sur le
        ctrl IK : SpaceSwitch en mode blend sur l'offset du ctrl (maintain
        offset : pas de saut au build), rotation / scale / shear gardés
        dans l'espace local.

        Ignoré si l'offset du ctrl est déjà piloté (ex: space switch du
        pole via poleSpaceSwitchTargets).

        Retourne le SpaceSwitch, ou None.
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

        # Translation seule depuis le ctrl IK.
        blend_matrix = switch.nodes.get("blendMatrix")

        for flag in ("useRotate", "useScale", "useShear"):
            plug = f"{blend_matrix}.target[0].{flag}"
            if blend_matrix and cmds.objExists(plug):
                cmds.setAttr(plug, 0)

        return switch
