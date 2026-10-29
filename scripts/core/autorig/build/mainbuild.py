from abc import ABC, abstractmethod

import maya.cmds as cmds

from ..modules import registry
from ..rigData import init_rigData
from ...utilities import ctrl_utilities
from importlib import reload

reload(registry)
reload(init_rigData)
reload(ctrl_utilities)


class MainBuild():

    def __init__(self, data):

        self.rig_data = data.get("rig_data")
        self.data = data.get("modules", {})

        self.groups = {}
        self.sets = {}
        self.layers = {}

        self.builders = {}

        self.joints = []
        self.controls = []
        self.setups = []

        self.build()

    # ======================================================
    # BUILD
    # ======================================================

    def build(self):

        self.create_groups()
        self.create_sets()
        self.create_layers()
        self.create_builders()
        self.build_modules()
        self.parent_ctrls_module()
        self.create_space_switches()
        self.parent_misc_module()
        self.cleanup_temp()
        self.custom()

    # ======================================================
    # RIG NAME
    # ======================================================

    def get_rig_name(self):

        if self.rig_data and cmds.objExists(self.rig_data) and cmds.attributeQuery("rigName", node=self.rig_data, exists=True):
            return cmds.getAttr(f"{self.rig_data}.rigName") or self.rig_data

        return self.rig_data or "RIG"

    # ======================================================
    # GROUPS
    # ======================================================

    def create_groups(self):

        self.groups["rig"] = self.get_or_create_group(f"{self.get_rig_name()}_RIG")
        self.groups["geo"] = self.get_or_create_group("GEO_grp", parent=self.groups["rig"])
        self.groups["joints"] = self.get_or_create_group("JNT_grp", parent=self.groups["rig"])
        self.groups["controls"] = self.get_or_create_group("CTRL_grp", parent=self.groups["rig"])
        self.groups["misc"] = self.get_or_create_group("MISC_grp", parent=self.groups["rig"])

    def get_or_create_group(self, name, parent=None):

        """
        Retourne le groupe 'name' s'il existe déjà dans la scène, sinon le
        crée (vide, sous 'parent' si fourni).
        """

        if cmds.objExists(name):
            return name

        if parent:
            return cmds.group(empty=True, name=name, parent=parent)

        return cmds.group(empty=True, name=name)

    # ======================================================
    # SETS
    # ======================================================

    def create_sets(self):

        self.sets["joints"] = self.get_or_create_set("JNT_set")
        self.sets["controls"] = self.get_or_create_set("CTRL_set")
        self.sets["setup"] = self.get_or_create_set("SETUP_set")

        self.sets["rig"] = self.get_or_create_set(
            f"{self.get_rig_name()}_set",
            members=[self.sets["joints"], self.sets["controls"], self.sets["setup"]]
        )

    def get_or_create_set(self, name, members=None):

        """
        Retourne le set 'name' s'il existe déjà dans la scène, sinon le
        crée (avec 'members' si fourni, vide sinon).
        """

        if cmds.objExists(name):
            return name

        if members:
            return cmds.sets(members, name=name)

        return cmds.sets(name=name, em=True)

    def add_to_set(self, node, set_name):

        if cmds.objExists(node):
            cmds.sets(node, add=set_name)

    # ======================================================
    # LAYERS
    # ======================================================

    def create_layers(self):

        self.layers["geo"] = self.create_layer("GEO_layer", [self.groups["geo"]])
        self.layers["joints"] = self.create_layer("JNT_layer", [self.groups["joints"]])
        self.layers["controls"] = self.create_layer("CTRL_layer", [self.groups["controls"]])

    def create_layer(self, name, members=None):

        """
        Retourne le display layer 'name' s'il existe déjà dans la scène,
        sinon le crée (avec 'members' si fourni).
        """

        if cmds.objExists(name):
            return name

        layer = cmds.createDisplayLayer(name=name, empty=True)

        if members:
            cmds.editDisplayLayerMembers(layer, members, noRecurse=True)

        return layer

    # ======================================================
    # BUILDERS
    # ======================================================

    def create_builders(self):

        """
        Instancie, pour chaque module, le Builder correspondant à son
        moduleType (résolu via le registry, comme pour les guides). Ces
        instances sont réutilisées pour toutes les étapes de build
        (joints, ctrls, setup) afin que chaque builder garde son propre
        état (self.joints/self.controls) d'une étape à l'autre.
        """

        self.builders = {}

        for module, data in self.data.items():

            # Module déjà construit (son premier joint existe) : il n'a pas
            # de builder, donc il est ignoré par toutes les étapes suivantes.
            first_joint = self.get_first_joint_name(data)

            if first_joint and cmds.objExists(first_joint):
                cmds.warning(f"'{module}' déjà construit ('{first_joint}' existe) : module ignoré.")
                continue

            self.builders[module] = self.get_builder(module, data)

    def get_first_joint_name(self, data):

        """
        Nom du premier joint d'un module ({side}_{baseName}_{index:02d}_jnt),
        déduit de son premier guide (voir get_guide_naming). None si le
        module n'a pas de guide.
        """

        guides = list((data or {}).get("guides") or [])

        if not guides:
            return None

        base_name, side, index = self.get_guide_naming(guides[0])

        return f"{side}_{base_name}_{index:02d}_jnt"

    def get_builder(self, module, data):

        """
        Résout la classe Builder à utiliser pour ce module en fonction de
        son moduleType. À défaut de builder spécifique trouvé, retombe
        sur le Builder de base (comportement par défaut).
        """

        builder_class = (
            registry.get_builder_class(data.get("moduleType"))
            or registry.get_base_builder_class()
        )

        return builder_class(module, data, self)

    # ======================================================
    # COLORS
    # ======================================================

    def get_color(self, side, color_type):

        """
        Retourne la couleur RGB (0-1) configurée sur le rig_data pour ce
        side/type (ex: 'Left', 'FK Main'). Retombe sur la couleur par
        défaut du projet (config/colorCtrl_config.json) si le rig_data
        n'existe pas ou n'a pas encore cet attribut.
        """

        attribute = init_rigData.RigData.color_name(side, color_type)

        if (
            self.rig_data
            and cmds.objExists(self.rig_data)
            and cmds.attributeQuery(attribute, node=self.rig_data, exists=True)
        ):

            rgb = cmds.getAttr(f"{self.rig_data}.{attribute}")

            if isinstance(rgb, list) and rgb:
                rgb = rgb[0]

            if rgb:
                return tuple(rgb)

        return tuple(
            init_rigData.DEFAULT_COLORS.get(side, {}).get(color_type, (1.0, 1.0, 1.0))
        )

    # ======================================================
    # MODULES
    # ======================================================

    def build_modules(self):

        """
        Délègue à chaque builder la construction complète de son module
        (joints, ctrls, setup, puis connexion du setup), en 4 passes
        séparées (une par étape, sur tous les modules) pour ne pas
        dépendre de l'ordre de traitement des modules : parent_joint_modules()
        s'intercale entre joints et ctrls pour que chaque joint ait déjà
        son parent DAG final (inter-module) avant que connect_control()
        ne construise sa contrainte - sinon ParentCnstrMtx capturerait un
        parent_target vide pour la racine de chaque module (voir
        parent_module_root). Le parentage ctrls/misc, lui, se fait après
        coup (voir parent_ctrls_module / parent_misc_module).
        """

        for module, builder in self.builders.items():
            builder.build_joints()

        self.parent_joint_modules()

        for module, builder in self.builders.items():
            builder.build_controls()

        for module, builder in self.builders.items():
            builder.build_setup()

        for module, builder in self.builders.items():
            builder.connect_setup()

            self.joints.extend(builder.joints)
            self.controls.extend(builder.controls)
            self.setups.extend(builder.setups)

            for joint in builder.joints:
                self.add_to_set(joint.name, self.sets["joints"])

            for control in builder.controls:
                self.add_to_set(control, self.sets["controls"])

            for setup in builder.setups:
                self.add_to_set(setup, self.sets["setup"])

    # ======================================================
    # JOINTS
    # ======================================================

    def parent_joint_modules(self):

        """
        Parente le joint de base de chaque module, une fois que tous les
        joints existent (pour ne pas dépendre de l'ordre de traitement
        des modules).
        """

        for module, builder in self.builders.items():

            if not builder.joints:
                continue

            module_parent = self.data.get(module, {}).get("parent")

            self.parent_module_root(builder.joints[0], module_parent)

    def parent_module_root(self, joint, module_parent):

        """
        Parente le joint de base d'un module au joint correspondant au
        guide parent du module. À défaut (pas de parent, ou joint parent
        introuvable), le parente au groupe JNT - le joint reste donc
        toujours rattaché à la hiérarchie JNT (voir parent_ctrls_module /
        parent_module_root_control, qui ne touchent jamais à un joint,
        même utilisé comme control via le mode 'No Ctrl').

        Le joint a déjà, depuis sa création, son offsetParentMatrix baké
        (translate/rotate/scale/jointOrient à zéro - voir
        Builder.create_joints, Joint.freeze_transform). Si rien
        ne le pilote (static, cas 'No Ctrl' ou 'Simple Connection'), un
        simple cmds.parent laisserait Maya recalculer translate/rotate
        pour compenser le nouveau parent en plus de cet offsetParentMatrix
        déjà présent : les canaux ne resteraient plus propres. Sa position
        monde est donc sauvée puis restaurée après un reparent "relatif",
        et l'offsetParentMatrix est re-baké pour le nouveau parent - même
        sans parent de guide (parenté direct au groupe JNT).

        Si en revanche il est déjà connecté (cas par défaut : piloté en
        live par ParentCnstrMtx, voir Builder.connect_control), il ne
        doit pas être re-baké (setAttr sur un attribut connecté lèverait
        une erreur) - un simple cmds.parent suffit, la contrainte reste
        valide quel que soit le parent DAG du joint.
        """

        target = None

        if module_parent and cmds.objExists(module_parent):

            base_name, side, index = self.get_guide_naming(module_parent)
            candidate = f"{side}_{base_name}_{index:02d}_jnt"

            if cmds.objExists(candidate):
                target = candidate

        if not target:
            target = self.groups.get("joints")

        if not target or not cmds.objExists(target) or not cmds.objExists(joint.name):
            return

        current_parent = cmds.listRelatives(joint.name, parent=True, fullPath=True) or []
        target_path = cmds.ls(target, long=True)[0]

        if current_parent and current_parent[0] == target_path:
            return

        if cmds.listConnections(f"{joint.name}.offsetParentMatrix", source=True, destination=False):
            cmds.parent(joint.name, target)
            return

        world_matrix = cmds.xform(joint.name, query=True, matrix=True, worldSpace=True)

        cmds.parent(joint.name, target, relative=True)
        cmds.xform(joint.name, worldSpace=True, matrix=world_matrix)

        joint.freeze_transform()

    def get_guide_naming(self, guide):

        """
        Déduit (baseName, side, index) à partir du nom du guide
        (ex: L_Brow_00_GUIDE ou L_Brow_00_GUIDE_ROOT).
        """

        short_name = guide.split("|")[-1]
        base = short_name.split("_GUIDE")[0]
        parts = base.split("_")

        side = parts[0]
        index = int(parts[-1])
        base_name = "_".join(parts[1:-1])

        return base_name, side, index

    # ======================================================
    # CONTROLS
    # ======================================================

    def parent_ctrls_module(self):

        """
        Parente le ctrl de base de chaque module au ctrl du module
        parent, une fois que tous les ctrls existent (pour ne pas
        dépendre de l'ordre de traitement des modules).
        """

        for module, builder in self.builders.items():

            if not builder.controls:
                continue

            module_parent = self.data.get(module, {}).get("parent")

            self.parent_module_root_control(builder.controls[0], module_parent)

    def parent_module_root_control(self, control, module_parent):

        """
        Rattache le ctrl de base d'un module au ctrl correspondant au
        guide parent du module. À défaut (pas de parent, ou ctrl parent
        introuvable), le rattache au groupe CTRL.

        Si un offset group dédié existe encore (Control.create_offset
        appelé avec use_group=True), c'est lui qui est reparenté, comme
        avant. Sinon (cas par défaut désormais - voir
        Control.transfer_offset_parent_matrix), le ctrl lui-même est
        reparenté : sa position monde est sauvée, il est reparenté "relatif"
        (aucune compensation automatique, pour ne pas polluer son
        offsetParentMatrix déjà baké avec l'ancien parent), remis à sa
        position monde d'origine, puis son offsetParentMatrix est re-baké
        relativement à son nouveau parent (canaux remis à zéro).

        En mode 'No Ctrl' (voir Builder.create_joint_shape), 'control'
        est en réalité le joint lui-même ('..._jnt', pas '..._ctrl') : il
        ne doit jamais être déplacé ici, sous peine de le sortir de la
        hiérarchie JNT - son parentage est entièrement géré par
        parent_joint_modules / parent_module_root.
        """

        if not control or not cmds.objExists(control) or not control.endswith("_ctrl"):
            return

        offset = self.get_offset_group(control)
        node = offset if offset and cmds.objExists(offset) else control

        target = None

        if module_parent and cmds.objExists(module_parent):

            base_name, side, index = self.get_guide_naming(module_parent)
            candidate = f"{side}_{base_name}_{index:02d}_ctrl"

            if cmds.objExists(candidate):
                target = candidate

        if not target:
            target = self.groups.get("controls")

        if not target or not cmds.objExists(target):
            return

        current_parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        target_path = cmds.ls(target, long=True)[0]

        if current_parent and current_parent[0] == target_path:
            return

        if node == offset:
            cmds.parent(node, target)
            return

        world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)

        cmds.parent(node, target, relative=True)
        cmds.xform(node, worldSpace=True, matrix=world_matrix)

        ctrl_utilities.Control(node).transfer_offset_parent_matrix()

    def get_offset_group(self, control):

        """
        Déduit le nom du offset group d'un ctrl à partir de sa convention
        de nommage ({side}_{baseName}_{index:02d}_ctrl -> ..._offset).
        """

        if control and control.endswith("_ctrl"):
            return control[: -len("_ctrl")] + "_offset"

        return None

    # ======================================================
    # SPACE SWITCH
    # ======================================================

    def create_space_switches(self):

        """
        Délègue à chaque builder la création de ses space switches (voir
        Builder.create_space_switches), une fois que tous les ctrls sont
        à leur place finale (après parent_ctrls_module) - avant ça, le
        parent DAG d'un ctrl racine n'est pas encore le bon, et les
        matrices que SpaceSwitch calcule pour chaque espace seraient
        fausses.
        """

        for builder in self.builders.values():
            builder.create_space_switches()

    # ======================================================
    # MISC
    # ======================================================

    def parent_misc_module(self):

        """
        Filet de sécurité : parente au groupe MISC (racine du rig) tout
        node de setup qui n'a pas déjà été parenté par son builder
        (ikHandle, surface de ruban, follicules...  tout ce qui n'est ni
        un joint ni un ctrl). La plupart des builders parentent déjà
        eux-mêmes leurs nodes de setup à la création (self.main.groups
        ["misc"]) ; cette passe rattrape ceux laissés à la racine de la
        scène.
        """

        misc_group = self.groups.get("misc")

        if not misc_group or not cmds.objExists(misc_group):
            return

        for setup in self.setups:

            if not setup or not cmds.objExists(setup):
                continue

            current_parent = cmds.listRelatives(setup, parent=True) or []

            if not current_parent:
                cmds.parent(setup, misc_group)

    # ======================================================
    # CLEAN
    # ======================================================

    def cleanup_temp(self):

        """
        Supprime tous les nodes temporaires.
        """

        temp_nodes = cmds.ls("*_temp")

        if temp_nodes:
            cmds.delete(temp_nodes)

    # ======================================================
    # CUSTOM
    # ======================================================

    @abstractmethod
    def custom(self):
        pass