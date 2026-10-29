import maya.cmds as cmds
import maya.api.OpenMaya as om

from ....utilities import joint_utilities
from ....utilities import ctrl_utilities
from ....utilities import cnstrMtx_utilities
from ....utilities import switchSpace_utilities

from importlib import reload

reload(joint_utilities)
reload(ctrl_utilities)
reload(cnstrMtx_utilities)
reload(switchSpace_utilities)

# ==========================================================
# MODULE BUILDER
# ==========================================================
#
# Comportement par défaut de build d'un module (joints, ctrls, setup),
# à partir des données déjà collectées par PreBuild (dict), piloté par
# MainBuild. Les modules spécifiques (arm, legBiped, simpleIk, ikSpine,
# ...) héritent de cette classe et n'ont besoin de surcharger que les
# méthodes qui les concernent (create_module_joints, create_setup,
# connect_setup, ...).
#

class Builder():

    # Rôle de couleur (voir RigData.COLORS) utilisé par défaut pour les
    # ctrls de ce module. À surcharger dans les modules spécifiques
    # (ex: "IK Main" pour un module IK).
    CONTROL_COLOR_TYPE = "FK Main"

    # Forme (voir shapesCtrl_config.json) utilisée par défaut pour les
    # ctrls de ce module. À surcharger dans les modules spécifiques.
    CONTROL_SHAPE = "circle"

    def __init__(self, module, data, main):

        self.module = module
        self.data = data
        self.main = main

        self.joints = []
        self.controls = []
        self.setups = []

    # ======================================================
    # DATA
    # ======================================================

    def get_rig_group(self, key):
        """Groupe 'key' de main.groups ("geo", "joints", "controls", "misc"), ou None."""

        group = self.main.groups.get(key)

        return group if group and cmds.objExists(group) else None

    def get_geo_group(self):
        """Groupe GEO du rig, ou None."""

        return self.get_rig_group("geo")

    def get_joints_group(self):
        """Groupe JNT du rig, ou None."""

        return self.get_rig_group("joints")

    def get_controls_group(self):
        """Groupe CTRL du rig, ou None."""

        return self.get_rig_group("controls")

    def get_misc_group(self):
        """Groupe MISC du rig, ou None."""

        return self.get_rig_group("misc")

    @property
    def prefix(self):
        """{side}_{baseName}_{index:02d} (même nommage que les guides du module)."""
        return f"{self.side}_{self.base_name}_{self.module_index:02d}"

    def get_root_guide(self):
        """Root guide du module (premier guide de data['guides'])."""

        guides = list((self.data.get("guides") or {}).keys())

        return guides[0] if guides else None

    def get_int(self, key, default):
        """Attribut int du module, ou 'default'."""

        try:
            return int(self.data.get(key))
        except (TypeError, ValueError):
            return default

    def get_float(self, key, default):
        """Attribut float du module, ou 'default'."""

        try:
            return float(self.data.get(key))
        except (TypeError, ValueError):
            return default

    def get_message(self, key):
        """Premier node connecté à un attribut message simple, ou None."""

        value = self.data.get(key)

        if isinstance(value, (list, tuple)):
            value = value[0] if value else None

        return value if value and cmds.objExists(value) else None

    @property
    def level_count(self):
        return max(0, min(self.MAX_LEVELS, self.get_int("levelCount", 1)))

    def get_chain_guides(self):

        """
        Guides de la chaîne qui porte le ruban : ribbonJointGuides (dans
        l'ordre), sinon les guides du module s'il en a au moins 2.
        """

        guides = [guide for guide in (self.data.get("ribbonJointGuides") or []) if cmds.objExists(guide)]

        if len(guides) >= 2:
            return guides

        module_guides = [guide for guide in (self.data.get("guides") or {}) if cmds.objExists(guide)]

        return module_guides if len(module_guides) >= 2 else guides

    def get_chain_positions(self):
        """Positions monde des guides de la chaîne."""

        return [cmds.xform(guide, query=True, worldSpace=True, translation=True) for guide in self.get_chain_guides()]

    def get_chain_joints(self):
        """Joints construits à partir des guides de la chaîne (ignorés s'ils n'existent pas)."""

        joints = []

        for guide in self.get_chain_guides():

            joint = self.resolve_space_target(guide)

            if joint and cmds.objExists(joint):
                joints.append(joint)

        return joints


    # ======================================================
    # BUILD
    # ======================================================

    def build(self):

        """
        Construit entièrement ce module : joints, ctrls, setup, puis
        connecte le setup. Appelé une seule fois par
        MainBuild.build_modules() (le parentage entre modules se fait
        après, une fois tous les modules construits - voir
        MainBuild.parent_joint_modules / parent_ctrls_module /
        parent_misc_module).

        Les modules spécifiques n'ont normalement pas besoin de
        surcharger cette méthode : ils surchargent create_joints /
        create_module_joints / create_controls / create_setup /
        connect_setup, appelées ici via build_joints / build_controls /
        build_setup.
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

        self.joints = self.create_joints(suffix=suffix)
        self.joints.extend(self.create_module_joints())

        return self.joints

    def create_joints(self, suffix="jnt"):

        """
        Crée la chaîne de joints du module à partir de ses guides. Une
        fois positionné/orienté, chaque joint a son transform local
        (translate + jointOrient + rotate + scale) baké dans son
        offsetParentMatrix et remis à zéro/identité (voir
        Joint.freeze_transform, joint_utilities.py) : seul
        offsetParentMatrix porte des valeurs, les canaux restent propres
        pour l'animation/les connexions.
        """

        joints = []

        guides = list(self.data["guides"].keys())

        aim_vector = self.get_vector_attribute("aimVector", default=(1, 0, 0))
        up_vector = self.get_vector_attribute("upVector", default=(0, 0, 1))

        # Orientation des joints (attribut jointOrientation) :
        #   Chain Plane : up sur la normale du plan de la chaîne (même axe de
        #                 pliage pour tous, plan de l'IK) ; chaîne droite /
        #                 2 guides : up = axe Y de chaque guide ;
        #   Guide Up    : up = axe Y de chaque guide ;
        #   Guides      : orientation exacte de chaque guide (pas d'aim).
        orientation = self.get_joint_orientation()

        plane_normal = self.get_chain_plane_normal(guides) if orientation == "Chain Plane" else None

        parent = None

        for index, guide in enumerate(guides):

            next_guide = guides[index + 1] if index + 1 < len(guides) else None

            joint_data = {
                "baseName": self.data["baseName"],
                "side": self.data["side"],
                "parent": parent,
                "index": index,
                "guide": guide
            }

            joint = joint_utilities.Joint(joint_data, suffix=suffix)

            joint.create_joint()
            joint.match_transform(matchRot=orientation == "Guides")

            base_name, side, guide_index = self.main.get_guide_naming(guide)
            joint.rename(baseName=base_name, side=side, index=guide_index)

            if orientation != "Guides":

                self.orient_joint(
                    joint.name,
                    guide,
                    next_guide,
                    aim_vector=aim_vector,
                    up_vector=up_vector,
                    world_up=plane_normal
                )

                # Dernier joint : orientation de son parent.
                if next_guide is None:
                    cmds.setAttr(f"{joint.name}.jointOrient", 0, 0, 0)

            joint.freeze_transform()

            joints.append(joint)

            parent = joint.name

        return joints

    def create_module_joints(self):
        """
        Override par les modules spécifiques pour ajouter des joints
        supplémentaires (ex: pole vector, joints de twist...).
        """
        return []

    def create_root_joint(self, reference=None, suffix="root_jnt"):

        """
        Root joint '{side}_{baseName}_{index}_{suffix}' du module, matché
        (position + orientation) sur 'reference' (Joint, premier joint du
        module par défaut), nommé d'après son guide, transform baké
        (Joint.freeze_transform). Les chaînes du module se parentent dessous
        (joint_utilities.parent_joint) : il devient joints[0], parenté par
        MainBuild. Stocké dans self.root_joint, retourné.
        """

        reference = reference or self.joints[0]

        base_name, side, index = self.main.get_guide_naming(reference.guide)

        joint = joint_utilities.Joint(
            {"baseName": base_name, "side": side, "index": index, "guide": reference.guide},
            suffix=suffix
        )
        joint.create_joint()
        joint.match_transform(reference.name, matchPos=True, matchRot=True)
        joint.freeze_transform()

        self.root_joint = joint

        return joint

    def duplicate_joints(self, replace_name={"_jnt": "_fk_jnt"}):

        """
        Duplique la chaîne de joints du module (à partir de son joint
        racine, self.joints[0]) via Joint.duplicate_chain
        (joint_utilities.py). Ne fait rien si la chaîne n'a pas encore
        été créée (voir build_joints). Retourne la liste des Joint
        dupliqués (racine en premier).

        replace_name : dict {ancien: nouveau} appliqué au nom de chaque
                        joint dupliqué (ex: {"_jnt": "_ik_jnt"}).
        """

        if not self.joints:
            return []

        root = self.joints[0]
        root = root.name if isinstance(root, joint_utilities.Joint) else root

        if not root or not cmds.objExists(root):
            return []

        return joint_utilities.Joint.duplicate_chain(root, replace_name=replace_name)

    def get_vector_attribute(self, key, default):

        """
        Lit un attribut vecteur (double3) collecté depuis le module
        (ex: 'aimVector', 'upVector'). Retombe sur 'default' si absent.
        """

        value = self.data.get(key)

        if isinstance(value, list) and value:
            value = value[0]

        if isinstance(value, (tuple, list)) and len(value) == 3:
            return tuple(value)

        return default

    JOINT_ORIENTATIONS = ("Chain Plane", "Guide Up", "Guides")

    def get_joint_orientation(self):
        """Mode d'orientation des joints (attribut jointOrientation), 'Chain Plane' par défaut."""

        value = self.data.get("jointOrientation")

        return value if value in self.JOINT_ORIENTATIONS else self.JOINT_ORIENTATIONS[0]

    def get_chain_plane_normal(self, guides, tolerance=1e-3):

        """
        Normale (monde, normalisée) du plan de la chaîne de guides : premier
        -> guide du milieu -> dernier, (milieu - premier) ^ (dernier -
        milieu). None si moins de 3 guides ou chaîne droite (normale trop
        petite devant les longueurs).
        """

        guides = [guide for guide in guides if cmds.objExists(guide)]

        if len(guides) < 3:
            return None

        first, middle, last = (
            om.MVector(cmds.xform(guide, query=True, worldSpace=True, translation=True))
            for guide in (guides[0], guides[len(guides) // 2], guides[-1])
        )

        upper = middle - first
        lower = last - middle

        normal = upper ^ lower

        if normal.length() < tolerance * upper.length() * lower.length():
            return None

        normal.normalize()

        return (normal.x, normal.y, normal.z)

    def orient_joint(self, joint, guide, target, aim_vector=(1, 0, 0), up_vector=(0, 0, 1), world_up=None):

        """
        Oriente le joint vers 'target' via une aim constraint temporaire
        (supprimée juste après). Up : 'world_up' (vecteur monde, ex: normale
        du plan de la chaîne - get_chain_plane_normal) si fourni, sinon
        l'axe Y du guide. Sans target, le joint garde l'orientation de son
        parent (chaîne continue).
        """

        if not target or not cmds.objExists(target) or not cmds.objExists(joint):
            return

        if world_up:
            up_kwargs = {"worldUpType": "vector", "worldUpVector": tuple(world_up)}
        else:
            up_kwargs = {"worldUpType": "objectrotation", "worldUpVector": (0, 1, 0), "worldUpObject": guide}

        aim = cmds.aimConstraint(
            target,
            joint,
            aimVector=aim_vector,
            upVector=up_vector,
            name=f"{joint}_AIM_temp",
            **up_kwargs
        )

        cmds.delete(aim)

    # ======================================================
    # CONTROLS
    # ======================================================

    def build_controls(self):

        self.controls = self.create_controls()

        return self.controls

    def create_controls(self):

        """
        Comportement par défaut : un ctrl par guide, chaîné au ctrl
        précédent du même module (offset group parenté au ctrl
        précédent), et connecté au joint correspondant - ou, si 'noCtrl'
        est actif sur le module, aucun ctrl séparé : la shape est posée
        directement sur le joint (voir create_joint_shape), qui devient
        lui-même le node animable et chaîné pour la suite. Le space
        switch du ctrl racine est créé plus tard (voir
        create_space_switches), une fois tous les ctrls en place.
        """

        controls = []

        guides = list(self.data.get("guides", {}).keys())

        parent = None
        no_ctrl = self.no_ctrl()

        for guide in guides:

            if not cmds.objExists(guide):
                continue

            base_name, side, index = self.main.get_guide_naming(guide)
            joint = f"{side}_{base_name}_{index:02d}_jnt"

            if not cmds.objExists(joint):
                continue

            if no_ctrl:
                control = self.create_joint_shape(guide, base_name, side, index, joint)
            else:
                control = self.create_control(guide, base_name, side, index, parent=parent)
                self.connect_control(control, joint)

            controls.append(control)

            parent = control

        return controls

    def create_joint_shape(self, guide, base_name, side, index, joint, shape=None, size=1.0, color=None):

        """
        Mode 'No Ctrl' : construit la shape du ctrl (même forme/couleur/
        décalage que create_control) sur un transform temporaire matché
        au guide, puis la transfère directement sur le joint (voir
        Control.transfer_to_joint, ctrl_utilities.py) - plus de ctrl
        séparé, le joint (déjà à canaux propres/offsetParentMatrix baké
        depuis create_joints) devient lui-même animable.
        """

        if shape is None:
            shape = self.shape_ctrl() or self.CONTROL_SHAPE

        if color is None:
            color = self.get_control_color()

        temp_name = f"{side}_{base_name}_{index:02d}_ctrlShape_TEMP"

        control = ctrl_utilities.Control(temp_name, shape=shape, size=size, color=color)
        control.create()

        self.adjust_control_shape(control)

        cmds.matchTransform(control.name, guide, position=True, rotation=True)

        control.transfer_to_joint(joint)

        return joint

    def create_control(self, guide, base_name, side, index, shape=None, size=1.0, color=None, parent=None):

        """
        Crée un ctrl (Control) à la position/rotation du guide, avec son
        offset group parenté à 'parent' (ctrl précédent de la chaîne) si
        fourni, sinon au groupe CTRL. Sans forme/couleur explicite,
        utilise respectivement CONTROL_SHAPE et la couleur configurée
        sur le rig_data (ou son défaut) pour le side du module et son
        rôle (CONTROL_COLOR_TYPE).
        """

        ctrl_name = f"{side}_{base_name}_{index:02d}_ctrl"

        if shape is None:
            shape = self.shape_ctrl() or self.CONTROL_SHAPE

        if color is None:
            color = self.get_control_color()

        control = ctrl_utilities.Control(ctrl_name, shape=shape, size=size, color=color)
        control.create()

        self.adjust_control_shape(control)

        cmds.matchTransform(control.name, guide, position=True, rotation=True)

        target_parent = parent if parent and cmds.objExists(parent) else self.main.groups.get("controls")

        # Parenté dans tous les cas : offset group dédié si 'Offset Group'
        # est actif, sinon offset baké dans l'offsetParentMatrix du ctrl
        # (reparenté sous target_parent avant le bake, voir
        # Control.create_offset).
        control.create_offset(parent=target_parent, use_group=self.offset_group())

        return control.name

    def get_control_color(self):

        """
        Couleur par défaut des ctrls de ce module : celle configurée sur
        le rig_data (ou son défaut projet) pour le side du module et son
        rôle CONTROL_COLOR_TYPE.
        """

        return self.main.get_color(self.data.get("side"), self.CONTROL_COLOR_TYPE)

    def shape_ctrl(self):

        """
        Forme demandée pour les ctrls du module ('shapeCtrl'), ou None si
        'Default' (le module garde sa forme par défaut).
        """

        value = self.data.get("shapeCtrl")

        if not value or value == "Default":
            return None

        return value

    def adjust_control_shape(self, control):

        """
        Applique le décalage de shape du module (shapeTranslate /
        shapeRotate / shapeScale) : transforme uniquement les points de
        la shape du ctrl, pas son transform.
        """

        translate = self.get_vector_attribute("shapeTranslate", default=(0.0, 0.0, 0.0))
        rotate = self.get_vector_attribute("shapeRotate", default=(0.0, 0.0, 0.0))
        scale = self.get_vector_attribute("shapeScale", default=(1.0, 1.0, 1.0))

        if (
            tuple(translate) == (0.0, 0.0, 0.0)
            and tuple(rotate) == (0.0, 0.0, 0.0)
            and tuple(scale) == (1.0, 1.0, 1.0)
        ):
            return

        control.transform_shape(translate=translate, rotate=rotate, scale=scale)

    def simple_connection(self):
        """Option 'Simple Connection' du module (attributs.json)."""
        return bool(self.data.get("simpleConnection"))

    def offset_group(self):
        """Option 'Offset Group' du module (attributs.json) : groupe offset au-dessus du ctrl, au lieu de l'offsetParentMatrix."""
        return bool(self.data.get("offsetGroup"))

    def no_ctrl(self):
        """Option 'No Ctrl' du module (attributs.json) : shape posée directement sur le joint."""
        return bool(self.data.get("noCtrl"))

    def get_attributes_host(self, default=None):

        """
        Ctrl qui doit porter les attributs custom du module, choisi via
        'attributesHost' (attributes.json) : un seul guide, résolu vers le
        ctrl construit à partir de lui - ou vers son joint si ce guide a
        été construit en mode 'No Ctrl'. Retourne 'default' si rien n'est
        configuré (ou introuvable) ; 'default' vaut le premier ctrl du
        module s'il n'est pas fourni.

        Le guide peut appartenir à un autre module : appeler cette
        méthode une fois tous les modules construits (comme
        create_space_switches) si c'est le cas.
        """

        if default is None and self.controls:
            default = self.controls[0]

        targets = self.data.get("attributesHost") or []

        if isinstance(targets, str):
            targets = [targets]

        if not targets or not cmds.objExists(targets[0]):
            return default

        guide = targets[0]

        base_name, side, index = self.main.get_guide_naming(guide)

        for suffix in ("ctrl", "jnt"):

            candidate = f"{side}_{base_name}_{index:02d}_{suffix}"

            if cmds.objExists(candidate):
                return candidate

        cmds.warning(f"Attributes host guide '{guide}' has no built ctrl.")

        return default

    def connect_control(self, control, joint):

        """
        Connecte le ctrl au joint.

        - Par défaut : contrainte de matrix (parent), maintainOffset.
        - Si 'simpleConnection' est activé : connexion directe
          translate/rotate/scale (voir connect_control_direct).
        """

        if not cmds.objExists(control) or not cmds.objExists(joint):
            return None

        if self.simple_connection():
            return self.connect_control_direct(control, joint)

        return cnstrMtx_utilities.ParentCnstrMtx(joint, control, dcmpMtx=False)

    def connect_control_direct(self, control, joint):

        """
        Connexion simple : translate / rotate / scale du ctrl sont
        connectés directement aux canaux du joint - déjà à zéro, son
        offset ayant été baké dans son offsetParentMatrix dès sa
        création (voir create_joints, Joint.freeze_transform).

        Plus léger qu'une contrainte de matrix, mais suppose que le ctrl
        et le joint sont alignés (le ctrl pilote les canaux locaux du
        joint tels quels).
        """

        for attr in ("translate", "rotate", "scale"):
            cmds.connectAttr(f"{control}.{attr}", f"{joint}.{attr}", force=True)

        return None

    # ======================================================
    # SPACE SWITCH
    # ======================================================

    def create_space_switches(self):

        """
        Crée les space switches du module. Appelé par MainBuild une fois
        TOUS les modules construits ET reparentés entre eux (après
        parent_ctrls_module) : avant ce point, le ctrl racine n'a pas
        encore son parent DAG final (il est encore sous CTRL_grp ou le
        ctrl précédent de son propre module), donc l'espace "Local" et
        les matrices de maintien de pose calculés par SpaceSwitch
        seraient faux. Comportement par défaut : space switch sur le
        ctrl racine (premier de la chaîne) - ou, en mode 'No Ctrl', sur
        le joint lui-même (create_space_switch gère les deux).
        """

        if self.controls:
            self.create_space_switch(self.controls[0])

    def create_space_switch(self, control, attr_name="space", targets_attr="spaceSwitchTargets"):

        """
        Ajoute un space switch qui pilote directement l'offsetParentMatrix
        de 'control' (déjà le support du bake statique de create_offset -
        voir Control.transfer_offset_parent_matrix ; SpaceSwitch capture
        la pose courante par espace via son "maintain offset", donc ce
        bake existant est naturellement absorbé, pas perdu), entre son
        parent actuel ("Local") et les cibles listées dans
        data[targets_attr] (résolues en joint si ce sont des guides,
        puisque seuls des guides peuvent être ajoutés à cette liste
        depuis le panel). Ne fait rien si aucune cible n'est configurée.

        Si un offset group dédié existe encore pour 'control' (voir
        create_offset(use_group=True)), c'est lui qui est piloté à la
        place, comme avant (ses propres canaux restent libres pour
        l'animation, séparés de ceux du ctrl).
        """

        targets = self.data.get(targets_attr) or []

        if not targets or not control or not cmds.objExists(control):
            return None

        offset = self.main.get_offset_group(control)
        node = offset if offset and cmds.objExists(offset) else control

        current_parent = cmds.listRelatives(node, parent=True, fullPath=True)
        current_parent = current_parent[0] if current_parent else None

        spaces = []
        drivers = set()

        if current_parent:
            spaces.append(("Local", current_parent))
            drivers.add(current_parent)

        for target in targets:

            driver = self.resolve_space_target(target)

            if not driver or driver in drivers:
                continue

            spaces.append((driver.split("|")[-1], driver))
            drivers.add(driver)

        if len(spaces) < 2:
            return None

        return switchSpace_utilities.SpaceSwitch(
            target=node,
            spaces=spaces,
            default=0,
            attr_name=attr_name,
            attr_host=control,
            parent=current_parent
        )

    def resolve_space_target(self, target):

        """
        Résout une cible de space switch vers le node à utiliser comme
        driver au build. On ne peut ajouter que des guides depuis le
        panel (les ctrls/joints n'existent pas encore à l'édition des
        guides) : on retrouve donc le joint créé à partir de ce guide.
        Si 'target' n'est pas un guide (node déjà existant/persistant,
        ex: un groupe world), il est utilisé tel quel.
        """

        if not target or not cmds.objExists(target):
            return None

        short_name = target.split("|")[-1]

        if "_GUIDE" not in short_name:
            return target

        base_name, side, index = self.main.get_guide_naming(target)
        candidate = f"{side}_{base_name}_{index:02d}_jnt"

        if cmds.objExists(candidate):
            return candidate

        cmds.warning(f"Space switch target '{target}' has no built joint ('{candidate}').")

        return None

    # ======================================================
    # SETUP
    # ======================================================

    def build_setup(self):

        self.setups = self.create_setup()

        return self.setups

    def create_setup(self):
        """
        Override par les modules spécifiques : contraintes, IK, FK, nodes...
        """
        return []

    def connect_setup(self):
        """
        Override par les modules spécifiques : connecte les setups aux joints.
        """
        pass
