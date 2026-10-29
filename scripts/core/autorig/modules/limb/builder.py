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


# ==========================================================
# LIMB BUILDER
# ==========================================================
#
# Membre à 3 joints (épaule/hanche -> coude/genou -> poignet/cheville)
# avec switch IK/FK.
#
# JOINTS (Builder.create_joints, une fois par chaîne)
#   root  {side}_{name}_{i}_root_jnt -> self.root_joint (sur le 1er joint)
#   bind  {side}_{name}_{i}_jnt      -> self.bind_joints
#   FK    {side}_{name}_{i}_fk_jnt   -> self.fk_joints
#   IK    {side}_{name}_{i}_ik_jnt   -> self.ik_joints
#   Les 3 chaînes sont parentées sous le root joint. self.joints =
#   [root] + bind (vue par MainBuild) : le root joint est parenté au
#   joint du guide parent du module (sinon JNT_grp) via
#   MainBuild.parent_module_root.
#
# Les étapes FK et IK sont héritées de simpleFk / simpleIk, appliquées
# chacune à sa propre chaîne (fk_joints / ik_joints).
#
# CONTROLS
#   Root   : root_ctrl sur le root joint, qui le pilote. controls[0] :
#            reparenté au ctrl du module parent par MainBuild. Tous les
#            autres ctrls du limb sont rangés dessous.
#   FK     : simpleFk.create_fk_controls sur la chaîne FK (fk_ctrl).
#   IK     : simpleIk.create_ik_control / create_pole_control sur la
#            chaîne IK (ik_ctrl + pole_ctrl).
#   Switch : ctrl porteur de l'attribut 'ikFk' (switch_ctrl), qui suit
#            le dernier joint bind.
#   'No Ctrl' : la shape du root ctrl est posée sur le root joint, et
#            les joints-ctrls IK / pole sont parentés sous lui.
#
# SETUP
#   simpleIk.create_setup / connect_setup sur la chaîne IK : ikHandle
#   (ikRPsolver) sous MISC_grp, piloté par le ctrl IK + pole. Le FK n'a
#   pas de setup (ctrls déjà connectés à leurs joints).
#   Chaque joint bind suit son joint FK ou IK via un SpaceSwitch
#   (switchSpace_utilities) piloté par 'ikFk', qui gère aussi la
#   visibilité des ctrls FK / IK.
#
# RIBBON (option 'useRibbon', étapes héritées du module ribbon)
#   Ruban construit à travers les guides du limb, skinné à ses joints
#   bind (main nurb), avec bindJointCount sk joints sur follicules et
#   jusqu'à 2 niveaux de ctrls (levelCount). Joints sous le root joint,
#   ctrls de niveau sous le root ctrl, setup dans {prefix}_setup_grp.
#   Les méthodes du ruban sont appelées explicitement
#   (ribbonBuilder.xxx(self)) : plusieurs parents du limb ont des
#   méthodes du même nom (create_setup, connect_setup, ...).
#
# Paramètres : sections "FK", "IK", "IK/FK Switch" et "Ribbon" de
# attributes.json.
#

IkBuilder = simpleIk_builder.Builder
FkBuilder = simpleFk_builder.Builder
ribbonBuilder = ribbon_builder.Builder


# MRO : Limb -> IkBuilder -> FkBuilder -> ribbonBuilder -> BaseBuilder
# (la classe de base doit venir après ses sous-classes).
class Builder(IkBuilder, FkBuilder, ribbonBuilder):

    # Le ruban du limb a au plus 2 niveaux.
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

        # Pas self.root_control (simpleIk) : il contraindrait la racine
        # de la chaîne IK et regrouperait l'IK à côté de lui, pas dessous.
        self.limb_root_control = None
        self.switch_control = None
        self.ik_fk_switches = []
        self.ik_fk_plug = None

        # Utilisé par SimpleIkBuilder.get_pole_vector_position.
        self.POLE_DISTANCE = self.get_float("poleDistance", 1.0)

    # ======================================================
    # DATA HELPERS
    # ======================================================

    def get_float(self, key, default):
        """Attribut float/int du module ('key'), ou 'default' si absent/invalide."""

        try:
            return float(self.data.get(key))
        except (TypeError, ValueError):
            return default

    def get_string(self, key, default):
        """Attribut enum (lu en string par PreBuild) du module, ou 'default'."""

        value = self.data.get(key)

        return value if isinstance(value, str) and value else default

    def use_ribbon(self):
        """Option 'Use Ribbon' du module (attributes.json) : ajouter un ruban au limb."""

        return bool(self.data.get("useRibbon"))

    # ======================================================
    # BUILD
    # ======================================================

    def build(self):

        """
        Construit le module seul (MainBuild appelle directement
        build_joints / build_controls / build_setup / connect_setup en
        passes séparées, sur tous les modules).
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

        """
        Chaîne bind, chaînes FK et IK identiques, puis root joint sur le
        premier joint, qui reçoit les 3 chaînes. self.joints = [root] +
        bind : MainBuild parente joints[0] (le root) et range le tout
        dans les sets.
        """

        self.bind_joints = self.create_joints(suffix=suffix)
        self.bind_joints.extend(self.create_module_joints())

        self.fk_chain()
        self.ik_chain()

        # Base : le ruban (dans le MRO avant Base) a son propre create_root_joint.
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
        Étape joints du ruban (module ribbon) : main nurb à travers les
        guides du limb + nurbs des niveaux (create_nurb), follicules
        (create_follicules), sk joints sur les follicules et drivers des
        niveaux, sous le root joint du limb. Retourne les joints créés.
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
        """Chaîne FK ({side}_{baseName}_{index}_fk_jnt), construite depuis les guides."""

        self.fk_joints = self.create_joints(suffix="fk_jnt")

        return self.fk_joints

    def ik_chain(self):
        """Chaîne IK ({side}_{baseName}_{index}_ik_jnt), construite depuis les guides."""

        self.ik_joints = self.create_joints(suffix="ik_jnt")

        return self.ik_joints

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        Root ctrl en premier (controls[0], reparenté au ctrl du module
        parent par MainBuild.parent_ctrls_module), puis FK, IK, pole
        vector et switch, tous rangés sous le root ctrl.
        """

        if not self.bind_joints or not self.fk_joints or not self.ik_joints:
            return []

        root_control = self.create_limb_root_control()

        fk_controls = list(self.create_fk_step())
        ik_control, pole_control = self.create_ik_step()

        # Le switch est contraint dès sa création (ParentCnstrMtx, qui fige
        # l'espace de son parent) : il est donc créé directement sous le
        # root, les autres y sont reparentés.
        switch_control = self.create_switch_control(parent=root_control)

        for control in (fk_controls[:1] + [ik_control, pole_control]):
            self.parent_under_root(control)

        controls = [root_control] + fk_controls

        for control in (ik_control, pole_control, switch_control):
            if control:
                controls.append(control)

        # Ruban : ctrls des niveaux sous le root ctrl du limb.
        if self.use_ribbon() and self.level_drivers:
            controls.extend(ribbonBuilder.create_level_controls(self, parent=root_control))

        return controls

    # --------------------------------------------------
    # ROOT
    # --------------------------------------------------

    def create_limb_root_control(self):

        """
        Root ctrl '{side}_{baseName}_{index}_root_ctrl' matché sur le root
        joint, sous CTRL_grp, et connecté à lui (Builder.connect_control).
        En mode 'No Ctrl', la shape est posée sur le root joint lui-même
        (Builder.create_joint_shape), qui devient le node animable.
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
        Range 'control' sous le root ctrl, position monde préservée :
        - joint-ctrl ('No Ctrl') : sous le root joint, via parent_joint
          (les ctrls FK, posés sur la chaîne FK, y sont déjà) ;
        - offset group dédié : simple reparent ;
        - sinon : reparent "relatif", monde restauré, offsetParentMatrix
          re-baké pour le nouveau parent (canaux propres).
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
        """Ctrls FK chaînés sur la chaîne FK (simpleFk.create_fk_controls)."""

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
        Ctrl IK sur le dernier joint IK, orienté comme lui ('Joint') ou
        aligné au monde ('World') selon ikCtrlOrient, puis pole vector
        devant le joint IK du milieu (simpleIk.create_ik_control /
        create_pole_control). Pas de ctrl root : la racine du limb est le
        ctrl FK racine.
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
        Ctrl qui porte l'attribut de switch IK/FK : sur le dernier joint
        bind (shape décalée de switchShapeOffset), sous 'parent' (sinon
        CTRL_grp), qui le suit (ParentCnstrMtx, maintain offset). Canaux
        verrouillés : il ne sert qu'à porter l'attribut.
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
        """Nom '{side}_{baseName}_{index}_{suffix}' d'un ctrl construit sur 'joint' (Joint)."""

        base_name, side, index = self.main.get_guide_naming(joint.guide)

        return f"{side}_{base_name}_{index:02d}_{suffix}"

    # ======================================================
    # SETUP
    # ======================================================

    def create_setup(self):

        """
        IK : ikHandle sur la chaîne IK (simpleIk.create_setup). FK : setup
        du simpleFk (aucun node, ctrls déjà connectés). Retourne la liste
        des nodes de setup (vue par MainBuild).
        """

        setups = self.create_ik_setup() + FkBuilder.create_setup(self)

        # Ruban : sk joints -> follicules, ctrls de niveau accrochés à la
        # surface du dessous (ribbon.create_setup).
        if self.use_ribbon() and self.nurb:
            setups.extend(ribbonBuilder.create_setup(self))

        return setups

    def connect_setup(self):

        """
        IK : ctrl IK -> ikHandle + orientation du dernier joint IK
        (maintain offset : le ctrl peut être aligné au monde), pole
        vector -> ikHandle (simpleIk.connect_setup). FK : rien à
        connecter (simpleFk). Puis switch IK/FK de la chaîne bind, et
        enfin skin du ruban (main nurb -> joints bind du limb, niveaux ->
        leurs drivers, ribbon.connect_setup).
        """

        self.connect_ik_setup()
        FkBuilder.connect_setup(self)

        self.create_ik_fk_switch()

        if self.use_ribbon() and self.nurb:
            ribbonBuilder.connect_setup(self)

    def create_ik_setup(self):
        """ikHandle(s) de la chaîne IK (simpleIk.create_setup). Surchargé par legQuadruped."""

        return IkBuilder.create_setup(self, self.ik_joints)

    def connect_ik_setup(self):
        """Ctrl IK, pole, orientation du dernier joint et stretch (simpleIk.connect_setup)."""

        IkBuilder.connect_setup(self, self.ik_joints)

    # ======================================================
    # IK / FK SWITCH
    # ======================================================

    def create_ik_fk_switch(self, attr_name=None, default=None):

        """
        Pour chaque joint bind, un SpaceSwitch (switchSpace_utilities, en
        mode blend) entre son joint FK et son joint IK, qui pilote son
        offsetParentMatrix (support de son bake, voir
        Joint.freeze_transform). Tous partagent le même attribut float
        0 (FK) -> 1 (IK) sur l'hôte des attributs du module
        (attributesHost, sinon le ctrl de switch). Pas de maintain
        offset : les 3 chaînes sont construites identiques, le joint bind
        colle exactement à sa chaîne active.

        attr_name : nom de l'attribut de switch (SWITCH_ATTR par défaut).
        default   : 0 = FK, 1 = IK (par défaut : ikFkDefault du module).
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

        """
        Visibilité des ctrls selon l'attribut de switch (float 0..1) :
        ctrls FK visibles tant qu'il est < 1, ctrls IK + pole tant qu'il
        est > 0 (les deux pendant un blend).
        """

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

        """
        Connecte 'plug' à la visibilité de l'offset group du ctrl s'il
        existe, sinon du ctrl lui-même (ignoré si verrouillée ou déjà
        connectée).
        """

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

        """
        Space switches de la racine FK (spaceSwitchTargets), du ctrl IK
        (ikSpaceSwitchTargets) et du pole vector (poleSpaceSwitchTargets).
        """

        if self.fk_controls:
            self.create_space_switch(self.fk_controls[0])

        super().create_space_switches()
