from pathlib import Path

import maya.cmds as cmds

from .. import registry
from ..ui_schema import attribute_defs, load_ui_settings
from .... import log

# Dossier du module (contient attributes.json).
_MODULE_DIR = Path(__file__).resolve().parent


class Guides():

    MODULE_NAME = "base"

    DEFAULT_NAME = "Base"

    # Nombre maximum de guides pour ce module (None = pas de limite)
    MAX_GUIDES = None

    # Nombre de guides créés automatiquement à la création du module,
    AUTO_GUIDES = None

    # Offset (world) appliqué à un guide ajouté à la chaîne, aussi bien
    ADD_GUIDE_OFFSET = {"translate": (0, 6, 0)}

    # Attributs herités du data node du guide parent (s'il existe) a la
    # creation du module - voir inherit_parent_attributes().
    INHERITED_ATTRIBUTES = ("side", "aimVector", "upVector", "simpleConnection", "offsetGroup", "noCtrl", "attributesHost")

    # ATTRIBUTES est dérivé de attributes.json (source unique, partagée, avec l'UI).
    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)

    def __init__(self, name, side="Center", index=0, parent=None):

        self.name = name
        self.side = side
        self.index = index
        self.update_index()
        print(self.index)

        self.parent = parent
        if parent == None : 
            selection = cmds.ls(sl=True)

            if selection:
                self.parent = selection[0]

        self.root = None
        self.guides = []

        self.data_node = None

    @property
    def module_name(self):
        return f"{self.side[0]}_{self.name}_{self.index:02d}"

    def update_index(self):

        # Incrémente l'index tant que {module_name}_GUIDE_DATA est pris
        # PAR UN AUTRE module (jamais par notre propre data node, sinon
        # un simple renommage/normalisation ferait dériver l'index).
        own = getattr(self, "data_node", None)

        while True:
            candidate = f"{self.module_name}_GUIDE_DATA"

            if not cmds.objExists(candidate) or candidate == own:
                break

            self.index += 1

    # --------------------------------------------------
    # CLASS METHOD
    # --------------------------------------------------
    @classmethod
    def from_data_node(cls, data_node):

        # --------------------------------------------------
        # VALIDATION
        # --------------------------------------------------

        if not cmds.objExists(data_node):
            log.error(f"Data node inexistant : {data_node}")
            return None

        if cmds.nodeType(data_node) != "network":
            log.error(f"{data_node} n'est pas un network.")
            return None

        # --------------------------------------------------
        # CREATION DE L'INSTANCE SANS APPELER __init__
        # --------------------------------------------------

        instance = cls.__new__(cls)

        # --------------------------------------------------
        # DATA NODE
        # --------------------------------------------------

        instance.data_node = data_node

        # --------------------------------------------------
        # RECUPERATION DES ATTRIBUTS
        # --------------------------------------------------

        # NAME
        if cmds.attributeQuery("baseName", node=data_node, exists=True):
            instance.name = cmds.getAttr(
                f"{data_node}.baseName"
            )
        else:
            instance.name = data_node.split("_")[1]

        # SIDE
        if cmds.attributeQuery("side", node=data_node, exists=True):

            side_index = cmds.getAttr(
                f"{data_node}.side"
            )

            side_names = [
                "Center",
                "Left",
                "Right"
            ]

            instance.side = side_names[side_index]

        else:
            instance.side = "Center"

        # INDEX
        if cmds.attributeQuery("index", node=data_node, exists=True):
            instance.index = cmds.getAttr(
                f"{data_node}.index"
            )
        else:
            instance.index = 0

        # --------------------------------------------------
        # ROOT GUIDE
        # --------------------------------------------------

        instance.root = None

        if cmds.attributeQuery("rootGuide", node=data_node, exists=True):

            connections = cmds.listConnections(
                f"{data_node}.rootGuide",
                source=True,
                destination=False
            ) or []

            if connections:
                instance.root = connections[0]

        # --------------------------------------------------
        # GUIDES
        # --------------------------------------------------

        instance.guides = []

        if cmds.attributeQuery("guides", node=data_node, exists=True):

            connections = cmds.listConnections(
                f"{data_node}.guides",
                source=True,
                destination=False
            ) or []

            instance.guides = connections

        # --------------------------------------------------
        # PARENT
        # --------------------------------------------------
        #
        # L'attribut message 'parent' du data node n'est jamais connecté
        # nulle part (connect_guides() ne connecte que rootGuide/guides) :
        # on retrouve donc le parent via la vraie hiérarchie Maya (le
        # parent DAG du root guide), pas via cet attribut.

        instance.parent = None

        if instance.root and cmds.objExists(instance.root):

            parent = cmds.listRelatives(instance.root, parent=True)

            if parent:
                instance.parent = parent[0]

        # --------------------------------------------------
        # RIG DATA
        # --------------------------------------------------

        instance.rig_data = None

        if cmds.attributeQuery("rigData", node=data_node, exists=True):

            connections = cmds.listConnections(
                f"{data_node}.rigData",
                source=True,
                destination=False
            ) or []

            if connections:
                instance.rig_data = connections[0]

        return instance

    # --------------------------------------------------
    # BUILD
    # --------------------------------------------------

    def create(self):

        log.info(f"Creating module '{self.module_name}' ({self.__class__.__module__})...")

        self.create_data_node()
        self.create_root()
        self.create_guides()
        self.connect_guides()
        self.lock_attributes()
        self.inherit_parent_attributes()
        self.rename_from_data()

        log.success(f"Module '{self.module_name}' created : {self.data_node}")

    def duplicate(self):

        """
        Duplique ce module ET tous ses modules enfants (récursivement).
        Chaque guide est recréé de zéro (create_root/create_guide) à
        partir de ses données capturées (settings + xform), plutôt que
        dupliqué directement dans Maya : ça évite d'entraîner les guides
        des modules enfants dans la duplication, et garantit que le bon
        nombre de guides / les bons settings sont recréés.
        """

        if not self.root or not cmds.objExists(self.root):
            log.warning("No root guide to duplicate.")
            return None

        tree = self.collect_module_tree()

        created = self.rebuild_module_tree(tree, root_parent=self.parent)

        return created.get(self.data_node)

    def create_mirror(self, replace_side="Right", axis="YZ", parent=None):

        """
        Crée un miroir de ce module ET de tous ses modules enfants
        (récursivement). Chaque guide est recréé de zéro à partir de ses
        données capturées (settings + xform miroité), plutôt que dupliqué
        directement dans Maya.

        'parent' permet de forcer le parent du miroir (utilisé lors d'un
        appel imbriqué) au lieu de le résoudre via get_mirror_parent().
        """

        if not self.root or not cmds.objExists(self.root):
            log.warning("No root guide to mirror.")
            return None

        mirror_parent = parent if parent is not None else self.get_mirror_parent()

        tree = self.collect_module_tree()

        created = self.rebuild_module_tree(
            tree,
            root_parent=mirror_parent,
            root_side=replace_side,
            mirror_axis=axis
        )

        return created.get(self.data_node)

    def get_child_modules(self):

        """
        Retourne les data nodes des modules dont le root guide est
        parenté (au sens hiérarchie Maya réelle) sur un des guides de ce
        module. L'attribut message 'parent' du data node n'étant jamais
        connecté nulle part, on ne peut pas s'y fier : on regarde donc le
        vrai parent DAG du root guide de chaque module de la scène.
        """

        if not self.guides:
            return []

        guide_set = set(self.guides)
        children = []

        for data_node in cmds.ls("*_GUIDE_DATA", type="network") or []:

            if data_node == self.data_node:
                continue

            root = self.get_root_node(data_node)

            if not root or not cmds.objExists(root):
                continue

            parent = cmds.listRelatives(root, parent=True)

            if parent and parent[0] in guide_set:
                children.append(data_node)

        return children

    def collect_module_tree(self):

        """
        Collecte les données (settings + xforms de chaque guide) de ce
        module et de tous ses modules enfants (récursivement), pour
        pouvoir les recréer de zéro via rebuild_module_tree().

        Retourne une liste de dicts (parents toujours avant leurs
        enfants) :
        {
            "data_node": <data node d'origine>,
            "instance": <instance Guides d'origine>,
            "parent_data_node": <data node du parent dans CETTE liste, ou None>,
            "parent_guide_index": <index du guide parent dans sa chaîne, ou None>,
            "settings": {...},  # valeurs d'attributs (hors message)
            "guide_xforms": [{"translate":[...], "rotate":[...], "scale":[...]}, ...]
        }
        """

        tree = []

        def collect(instance, parent_data_node, parent_guide_index):

            settings = {}

            for attr in cmds.listAttr(instance.data_node, userDefined=True) or []:

                plug = f"{instance.data_node}.{attr}"

                if not cmds.objExists(plug):
                    continue

                try:
                    attr_type = cmds.getAttr(plug, type=True)
                except Exception:
                    continue

                if attr_type == "message":
                    continue

                try:
                    settings[attr] = cmds.getAttr(plug)
                except Exception:
                    continue

            guide_xforms = []

            for guide in instance.guides:

                guide_xforms.append({
                    "translate": cmds.xform(guide, q=True, ws=True, t=True),
                    "rotate": cmds.xform(guide, q=True, ws=True, ro=True),
                    "scale": cmds.getAttr(f"{guide}.scale")[0],
                })

            tree.append({
                "data_node": instance.data_node,
                "instance": instance,
                "parent_data_node": parent_data_node,
                "parent_guide_index": parent_guide_index,
                "settings": settings,
                "guide_xforms": guide_xforms,
            })

            for child_data_node in instance.get_child_modules():

                child_instance = registry.load_guide(child_data_node)

                if not child_instance:
                    continue

                try:
                    guide_index = instance.guides.index(child_instance.parent)
                except ValueError:
                    guide_index = None

                collect(child_instance, instance.data_node, guide_index)

        collect(self, None, None)

        return tree

    def rebuild_module_tree(self, tree, root_parent=None, root_side=None, mirror_axis=None):

        """
        Recrée de zéro tous les modules décrits par 'tree' (issu de
        collect_module_tree), en respectant la hiérarchie, avec de
        nouveaux guides positionnés via leurs xforms capturés.

        root_parent : parent à utiliser pour le module racine de l'arbre.
        root_side   : si fourni, force le side du module racine (mirror).
        mirror_axis : si fourni ("YZ"/"XZ"/"XY"), miroite la position de
                      chaque guide recréé, et inverse le side de chaque
                      module (sauf le module racine, qui utilise root_side).

        Retourne {ancien_data_node: nouvelle_instance}.
        """

        side_names = ["Center", "Left", "Right"]
        side_flip = {"Left": "Right", "Right": "Left", "Center": "Center"}

        created = {}

        for entry in tree:

            settings = entry["settings"]
            source_instance = entry["instance"]

            name = settings.get("baseName", source_instance.name)
            side = side_names[settings.get("side", 0)]

            if entry["parent_data_node"] is None:

                new_parent = root_parent

                if root_side:
                    side = root_side

            else:

                parent_new_instance = created.get(entry["parent_data_node"])

                if not parent_new_instance:
                    continue

                guide_index = entry["parent_guide_index"]

                if guide_index is not None and guide_index < len(parent_new_instance.guides):
                    new_parent = parent_new_instance.guides[guide_index]
                else:
                    new_parent = parent_new_instance.root

                if mirror_axis:
                    side = side_flip.get(side, side)

            # Pour un mirror, le side change (Left <-> Right) donc pas de
            # collision de nom : on garde le même index que l'original
            # (paire L/R cohérente, ex: L_Brow_03 <-> R_Brow_03). Pour un
            # duplicate simple (même side), il faut un nouvel index libre.
            initial_index = settings.get("index", source_instance.index) if mirror_axis else 0

            cls = source_instance.__class__
            new_instance = cls(name, side, initial_index, new_parent)

            # __init__ retombe sur la sélection Maya courante si parent
            # vaut None (comportement voulu pour la création interactive) :
            # on force donc explicitement la valeur résolue ici, pour ne
            # jamais accrocher un module racine à ce qui est sélectionné
            # dans la scène au moment du duplicate/mirror.
            new_instance.parent = new_parent

            new_instance.create_data_node()

            new_instance.create_root(parent=new_parent)
            self.apply_guide_xform(new_instance.root, entry["guide_xforms"][0], mirror_axis)

            for guide_xform in entry["guide_xforms"][1:]:

                new_guide = new_instance.create_guide(parent=new_instance.guides[-1])

                if not new_guide:
                    continue

                self.apply_guide_xform(new_guide, guide_xform, mirror_axis)

            new_instance.connect_guides()

            self.apply_settings(
                new_instance,
                settings,
                skip=("baseName", "side", "index", "moduleType")
            )

            source_instance.copy_rig_data_connection_to(new_instance)

            new_instance.lock_attributes()

            created[entry["data_node"]] = new_instance

        return created

    def apply_guide_xform(self, guide, xform, mirror_axis=None):

        """
        Positionne 'guide' avec le xform capturé (translate/rotate/scale
        monde), puis le miroite sur 'mirror_axis' si fourni.
        """

        if not guide or not cmds.objExists(guide):
            return

        cmds.xform(guide, ws=True, t=xform.get("translate", (0, 0, 0)))
        cmds.xform(guide, ws=True, ro=xform.get("rotate", (0, 0, 0)))
        cmds.setAttr(f"{guide}.scale", *xform.get("scale", (1, 1, 1)))

        if mirror_axis:
            self.mirror_guide(guide, mirror_axis)

    def mirror_guide(self, guide, axis="YZ"):

        """
        Miroite un guide (position + orientation) via un groupe temporaire
        à scale négative sur l'axe donné, puis freeze. Restaure son parent
        d'origine ensuite (sinon le guide reste accroché au monde et la
        chaîne perd sa hiérarchie).
        """

        axis_scale = {
            "YZ": (-1, 1, 1),
            "XZ": (1, -1, 1),
            "XY": (1, 1, -1),
        }.get(axis, (-1, 1, 1))

        original_parent = cmds.listRelatives(guide, parent=True)
        original_parent = original_parent[0] if original_parent else None

        mirror_group = cmds.group(empty=True, name=f"{guide}_MIRROR_temp")
        cmds.parent(guide, mirror_group)
        cmds.setAttr(f"{mirror_group}.scale", *axis_scale)
        cmds.parent(guide, world=True)
        cmds.makeIdentity(guide, apply=True, translate=True, rotate=True, scale=True)
        cmds.delete(mirror_group)

        if original_parent and cmds.objExists(original_parent):
            cmds.parent(guide, original_parent, relative=False)

    def apply_settings(self, target_instance, settings, skip=()):

        """
        Applique 'settings' (dict attr -> valeur, capturé par
        collect_module_tree) sur target_instance.data_node, en excluant
        les clés de 'skip'.
        """

        if not target_instance.data_node or not cmds.objExists(target_instance.data_node):
            return

        for attr, value in settings.items():

            if attr in skip:
                continue

            plug = f"{target_instance.data_node}.{attr}"

            if not cmds.objExists(plug):
                continue

            try:
                attr_type = cmds.getAttr(plug, type=True)
            except Exception:
                continue

            if attr_type == "message":
                continue

            target_instance.unlock_attributes([attr])

            try:
                if attr_type == "string":
                    cmds.setAttr(plug, value, type="string")

                elif attr_type in ("double3", "float3", "long3", "short3", "byte3"):
                    if isinstance(value, list) and value:
                        value = value[0]
                    cmds.setAttr(plug, *value)

                elif attr_type in ("matrix", "fltMatrix"):
                    cmds.setAttr(plug, value, type="matrix")

                else:
                    cmds.setAttr(plug, value)

            except Exception:
                pass

    def get_mirror_parent(self):

        """
        Résout le parent à utiliser pour un module miroité : le guide
        correspondant du module parent mais de l'autre side (Left <-> Right).
        Si le parent est Center (ou son side est introuvable), retourne
        le même parent tel quel.
        """

        if not self.parent or not cmds.objExists(self.parent):
            return self.parent

        parent_data_node = self.get_data_node(self.parent)

        if not parent_data_node:
            return self.parent

        side_index = cmds.getAttr(f"{parent_data_node}.side")
        side_names = cmds.attributeQuery(
            "side",
            node=parent_data_node,
            listEnum=True
        )[0].split(":")

        parent_side = side_names[side_index]

        if parent_side not in ("Left", "Right"):
            return self.parent

        mirror_side = "Right" if parent_side == "Left" else "Left"

        short_name = self.parent.split("|")[-1]

        if not short_name.startswith(f"{parent_side[0]}_"):
            return self.parent

        mirror_guide_name = f"{mirror_side[0]}_{short_name[2:]}"

        if cmds.objExists(mirror_guide_name):
            return mirror_guide_name

        log.warning(
            f"No mirrored parent found for '{self.parent}' "
            f"('{mirror_guide_name}'), using original parent."
        )

        return self.parent

    def copy_rig_data_connection_to(self, target_instance):

        """
        Connecte target_instance au même rig_data que ce module,
        si ce module y est lui-même connecté.

        connect_rig_data() connecte {data_node}.message vers
        {RIG_DATA_NODE}.rigData[i] : le lien vit sur le node RIG_DATA
        (attribut multi 'rigData'), pas sur l'attribut 'rigData' du
        module lui-même. Il faut donc remonter les connexions sortantes
        de .message pour retrouver le node RIG_DATA.
        """

        if not self.data_node or not cmds.objExists(self.data_node):
            return

        connections = cmds.listConnections(
            f"{self.data_node}.message",
            source=False,
            destination=True,
            plugs=True
        ) or []

        rig_data_node = None

        for plug in connections:

            node, _, attr = plug.partition(".")

            if node.endswith("_RIG_DATA") and attr.startswith("rigData"):
                rig_data_node = node
                break

        if not rig_data_node:
            return

        rig_name = (
            rig_data_node[: -len("_RIG_DATA")]
            if rig_data_node.endswith("_RIG_DATA")
            else rig_data_node
        )

        target_instance.connect_rig_data(rig_name)

    # --------------------------------------------------
    # DATA NODE
    # --------------------------------------------------
    def create_data_node(self):
        self.data_node = cmds.createNode("network", name=f"{self.module_name}_GUIDE_DATA")
        self.add_attributes()
        log.info(f"Data node created : {self.data_node}")

    def get_parent_data(self):

        """
        Récupère le data node du guide parent (self.parent) et retourne
        ses attributs utilisateur (hors message) sous forme de dict.
        """

        if not self.parent or not cmds.objExists(self.parent):
            return {}
        
        parent_data_node = self.get_data_node(self.parent)

        if not parent_data_node:
            return {}

        data = {}

        for attr in cmds.listAttr(parent_data_node, userDefined=True) or []:

            plug = f"{parent_data_node}.{attr}"

            if not cmds.objExists(plug):
                continue

            try:
                attr_type = cmds.getAttr(plug, type=True)
            except Exception:
                continue

            if attr_type == "message":
                continue

            try:
                data[attr] = cmds.getAttr(plug)
            except Exception:
                continue

        return data

    def inherit_parent_attributes(self):

        """
        Applique a self.data_node la valeur de chaque attribut de
        INHERITED_ATTRIBUTES lue sur le data node du guide parent
        (self.parent), pour que la chaîne reste cohérente (même côté,
        même orientation, ...). Ne fait rien si aucun parent n'existe.
        """

        parent_data = self.get_parent_data()

        if not parent_data or not self.data_node or not cmds.objExists(self.data_node):
            return

        inherited = {
            attr: value for attr, value in parent_data.items()
            if attr in self.INHERITED_ATTRIBUTES
        }

        self.apply_settings(self, inherited)

        self.inherit_parent_messages()

        self.lock_attributes()

    def inherit_parent_messages(self):

        """
        Pendant de inherit_parent_attributes() pour les attributs message
        simples (ex: attributesHost) de INHERITED_ATTRIBUTES, ignorés par
        get_parent_data()/apply_settings() : connecte à self.data_node la
        même source que sur le data node du guide parent.
        """

        parent_data_node = self.get_data_node(self.parent) if self.parent else None

        if not parent_data_node or not self.data_node or not cmds.objExists(self.data_node):
            return

        for attr in self.INHERITED_ATTRIBUTES:

            parent_plug = f"{parent_data_node}.{attr}"
            plug = f"{self.data_node}.{attr}"

            if not cmds.objExists(parent_plug) or not cmds.objExists(plug):
                continue

            if cmds.getAttr(plug, type=True) != "message":
                continue

            if cmds.attributeQuery(attr, node=self.data_node, multi=True):
                continue

            sources = cmds.listConnections(parent_plug, source=True, destination=False) or []

            if not sources:
                continue

            cmds.setAttr(plug, lock=False)
            cmds.connectAttr(f"{sources[0]}.message", plug, force=True)

    # Flags de ATTRIBUTES passés tels quels à cmds.addAttr.
    ADD_ATTR_FLAGS = (
        "at",
        "dt",
        "enumName",
        "multi",
        "min",
        "max",
        "softMin",
        "softMax",
        "parent",
        "keyable",
        "cachedInternally",
        "internalSet",
        "usedAsColor"
    )

    def add_attributes(self):
        """Crée sur le data node tous les attributs de ATTRIBUTES."""

        for attr, infos in self.ATTRIBUTES.items():
            self.add_attribute(attr, infos)

    def add_attribute(self, attr, infos):
        """
        Crée l'attribut 'attr' sur le data node d'après sa définition
        'infos' (une entrée de ATTRIBUTES), avec sa valeur par défaut.
        Utilisé aussi par update_guides pour les attributs manquants.
        """

        if infos.get("at") == "double3":
            self.add_vector_attribute(attr, infos.get("value", (0.0, 0.0, 0.0)))
            return

        kwargs = {"ln": attr}
        kwargs.update({k: v for k, v in infos.items() if k in self.ADD_ATTR_FLAGS})

        cmds.addAttr(self.data_node, **kwargs)

        if "value" not in infos:
            return

        plug = f"{self.data_node}.{attr}"
        at = infos.get("at")

        if at in ("double", "float", "long", "short", "byte", "enum", "bool"):
            cmds.setAttr(plug, infos["value"])

        elif infos.get("dt") == "string":
            cmds.setAttr(plug, infos["value"] or "", type="string")

    def add_vector_attribute(self, name, default=(0.0, 0.0, 0.0)):

        """
        Crée un attribut vecteur (double3) avec ses enfants X/Y/Z,
        puis lui applique sa valeur par défaut.
        """

        cmds.addAttr(self.data_node, longName=name, attributeType="double3")
        cmds.addAttr(self.data_node, longName=f"{name}X", attributeType="double", parent=name)
        cmds.addAttr(self.data_node, longName=f"{name}Y", attributeType="double", parent=name)
        cmds.addAttr(self.data_node, longName=f"{name}Z", attributeType="double", parent=name)

        cmds.setAttr(f"{self.data_node}.{name}", *default, type="double3")

    def lock_attributes(self):
        for attr, infos in self.ATTRIBUTES.items():
            if infos.get("lock", False):
                cmds.setAttr(f"{self.data_node}.{attr}", lock=True)

    def unlock_attributes(self, attributes=None):
        if attributes is None:
            attributes = self.ATTRIBUTES.keys()

        for attr in attributes:
            cmds.setAttr(f"{self.data_node}.{attr}", lock=False)

    def set_attribute(self, attribute, value):

        """
        Set un attribut du data node (tous types), et renomme les nodes
        du module si l'attribut modifié impacte le nommage
        (baseName/side/index).
        """

        if not self.data_node or not cmds.objExists(self.data_node):
            log.error(f"Cannot set attribute '{attribute}' : data node does not exist.")
            return None

        plug = f"{self.data_node}.{attribute}"

        if not cmds.objExists(plug):
            log.error(f"Cannot set attribute : '{plug}' does not exist.")
            return None

        if cmds.getAttr(plug, lock=True):
            log.warning(f"Cannot set attribute : '{plug}' is locked.")
            return None

        self.unlock_attributes([attribute])

        try:
            attr_type = cmds.getAttr(plug, type=True)

            if attr_type == "string":
                cmds.setAttr(plug, value, type="string")

            elif attr_type in ("double3", "float3", "long3", "short3", "byte3"):
                cmds.setAttr(plug, *value)

            elif attr_type in ("matrix", "fltMatrix"):
                cmds.setAttr(plug, value, type="matrix")

            else:
                cmds.setAttr(plug, value)

        except Exception as error:
            log.error(f"Could not set '{plug}' to {value} : {error}")
            return None

        finally:
            self.lock_attributes()

        log.info(f"Set '{plug}' = {value}")

        if attribute in ("baseName", "side", "index"):
            self.rename_from_data()

        return self.data_node

    def rename_from_data(self):

        """
        Relit baseName/side/index depuis le data node et renomme les
        nodes du module (data node, root, guides) en conséquence.
        """

        if not self.data_node or not cmds.objExists(self.data_node):
            return

        side_index = cmds.getAttr(f"{self.data_node}.side")

        side_names = cmds.attributeQuery(
            "side",
            node=self.data_node,
            listEnum=True
        )[0].split(":")

        side_name = side_names[side_index]
        base_name = str(cmds.getAttr(f"{self.data_node}.baseName"))
        index = int(cmds.getAttr(f"{self.data_node}.index"))

        self.rename(base_name, side_name, index)

    # --------------------------------------------------
    # CONNECTIONS
    # --------------------------------------------------

    def connect_rig_data(self, rig_data_name, attr="rigData"):

        node = rig_data_name + "_RIG_DATA"

        if not self.data_node or not cmds.objExists(self.data_node):
            log.error("Le data node n'existe pas.")
            return False

        if not node or not cmds.objExists(node):
            log.error(f"Node invalide : {node}")
            return False

        # ATTRIBUT
        if not cmds.attributeQuery(attr, node=node, exists=True):
            cmds.addAttr(node, longName=attr, attributeType="message", multi=True)
        target_attr = f"{node}.{attr}"
        
        # CHERCHE LE PREMIER INDEX LIBRE
        used_indices = cmds.getAttr(target_attr, multiIndices=True) or []
        index = 0
        while index in used_indices:
            index += 1

        # CONNECTION
        cmds.connectAttr(f"{self.data_node}.message", f"{target_attr}[{index}]", force=True)

        log.success(f"Connected '{self.data_node}' to rig data '{node}'")

        return True

    def connect_message(self, source, target, index=None):
        if index is not None:
            target_attr = f"{self.data_node}.{target}[{index}]"
        else:
            target_attr = f"{self.data_node}.{target}"

        cmds.setAttr(target_attr, lock=False)
        cmds.connectAttr(f"{source}.message", target_attr, force=True)

    def connect_guides(self):
        if self.root:
            self.connect_message(self.root, "rootGuide")

        for index, guide in enumerate(self.guides):
            self.connect_message(guide, "guides", index)

        log.info(f"Connected root + {len(self.guides)} guide(s) to {self.data_node}")

    # --------------------------------------------------
    # GUIDE MANAGEMENT
    # --------------------------------------------------

    def has_reached_max_guides(self):

        """
        Retourne True si le nombre de guides du module a atteint
        MAX_GUIDES (False si MAX_GUIDES est None, pas de limite).
        """

        if self.MAX_GUIDES is None:
            return False

        return len(self.guides) >= self.MAX_GUIDES

    def create_guide(self, parent=None, offset=None):

        if self.has_reached_max_guides():
            log.warning(f"Maximum guides reached ({self.MAX_GUIDES}) for this module.")
            return None

        guide = cmds.createNode("transform", name=self.get_next_guide_name())

        # --------------------------------------------------
        # SHAPES
        # --------------------------------------------------
        size = 2.0

        # Cube jaune (demi-côté size * 0.5) : une seule courbe linéaire qui
        # parcourt ses 12 arêtes (certaines deux fois).
        half = size * 0.5

        cube = [
            (-half,  half,  half), ( half,  half,  half), ( half,  half, -half), (-half,  half, -half),
            (-half,  half,  half), (-half, -half,  half), ( half, -half,  half), ( half,  half,  half),
            ( half, -half,  half), ( half, -half, -half), ( half,  half, -half), ( half, -half, -half),
            (-half, -half, -half), (-half,  half, -half), (-half, -half, -half), (-half, -half,  half),
        ]

        axis_data = {
            "frame": (cube, 17),
            "X": ([(0, 0, 0), (size * 1.5, 0, 0)], 13),
            "Y": ([(0, 0, 0), (0, size * 1.5, 0)], 14),
            "Z": ([(0, 0, 0), (0, 0, size * 1.5)], 6),
        }

        for axis, (points, color) in axis_data.items():

            curve = cmds.curve(
                degree=1,
                point=points,
                name=f"{self.module_name}_AXIS_{axis}"
            )

            shape = cmds.listRelatives(curve, shapes=True)[0]
            cmds.parent(shape, guide, shape=True, relative=True)
            cmds.delete(curve)

            cmds.setAttr(f"{shape}.overrideEnabled", 1)
            cmds.setAttr(f"{shape}.overrideColor", color)

        # --------------------------------------------------
        # PARENT
        # --------------------------------------------------

        if parent:
            if (cmds.objExists(guide) and cmds.objExists(parent)
                and cmds.nodeType(guide) == "transform" and cmds.nodeType(parent) == "transform"):

                # relative=True : garde le transform local (0/0/0, scale 1)
                # du guide fraîchement créé, au lieu de compenser pour
                # préserver sa position monde (ce qui donnerait des
                # translate/rotate locaux non nuls après parentage).
                cmds.parent(guide, parent, relative=True)

                if offset is not None:
                    self.apply_offset(guide, offset)

        self.guides.append(guide)
        return guide

    def get_next_guide_name(self):

        """
        Retourne un nom de guide libre à la convention finale :
        {side}_{baseName}_{moduleIndex:02d}_{guideIndex:02d}_GUIDE
        (= {module_name}_{guideIndex:02d}_GUIDE). C'est aussi ce
        qu'attend MainBuild.get_guide_naming() pour nommer les joints.
        """

        index = len(self.guides)
        name = f"{self.module_name}_{index:02d}_GUIDE"

        while cmds.objExists(name):
            index += 1
            name = f"{self.module_name}_{index:02d}_GUIDE"

        return name

    def apply_offset(self, guide, offset=None):

        """
        Applique un offset (translate/rotate/scale) au guide, relatif a
        son parent : 'guide' est deja parente a ce parent (relative=True,
        voir create_guide) avant cet appel, donc ses attributs locaux
        sont deja exprimes dans l'espace du parent - un simple setAttr
        suffit, pas besoin de xform (world).
        """

        offset = offset or {}

        offset_translate = offset.get("translate", (0, 0, 0))
        offset_rotate = offset.get("rotate", (0, 0, 0))
        offset_scale = offset.get("scale", (1, 1, 1))

        cmds.setAttr(f"{guide}.translate", *offset_translate)
        cmds.setAttr(f"{guide}.rotate", *offset_rotate)
        cmds.setAttr(f"{guide}.scale", *offset_scale)

        return guide

    def create_root(self, radius=0.5, parent=None):

        if parent is None:
            parent = self.parent

        guide = self.create_guide(parent)
        self.root = cmds.rename(guide, f"{self.module_name}_GUIDE_ROOT")
        self.guides[self.guides.index(guide)] = self.root

        sphere, history = cmds.sphere(radius=radius, sections=8, spans=4, constructionHistory=True)

        shape = cmds.listRelatives(sphere, shapes=True)[0]
        cmds.parent(shape, self.root, shape=True, relative=True)
        cmds.delete(sphere)

        cmds.setAttr(f"{shape}.overrideEnabled", True)
        cmds.setAttr(f"{shape}.overrideShading", False)
        cmds.setAttr(f"{shape}.overrideColor", 14)

        log.info(f"Root guide created : {self.root}")

        return self.root

    def create_guides(self):

        """
        Complète la chaîne (après create_root) jusqu'à AUTO_GUIDES guides
        au total, via add_guide() (la même routine que le bouton
        "+ Add Guide"). Ne fait rien si AUTO_GUIDES n'est pas défini.
        """

        target = self.AUTO_GUIDES or 0

        while len(self.guides) < target:

            if self.add_guide() is None:
                break

    def add_guide(self, offset=None):

        """
        Ajoute un guide à la fin de la chaîne du module : création
        (chaînée sur le dernier guide, ou le root), connexion au data
        node (guides[i]) et lock. Retourne le nouveau guide, ou None si
        le maximum est atteint / la création a échoué.

        Routine partagée par create_guides() (AUTO_GUIDES) et par le
        bouton "+ Add Guide" du panneau de settings.
        """

        if self.has_reached_max_guides():
            log.warning(f"Maximum guides reached ({self.MAX_GUIDES}) for this module.")
            return None

        parent = self.guides[-1] if self.guides else self.root

        guide = self.create_guide(
            parent=parent,
            offset=self.ADD_GUIDE_OFFSET if offset is None else offset,
        )

        if not guide:
            return None

        self.connect_message(guide, "guides", len(self.guides) - 1)
        self.lock_attributes()

        log.info(f"Guide added to '{self.data_node}' : {guide}")

        return guide

    @staticmethod
    def get_data_node(guide):
        if not cmds.objExists(guide):
            return None

        connections = cmds.listConnections(f"{guide}.message", source=False,
                                            destination=True, type="network", plugs=True) or []

        # Un guide peut aussi être la cible d'attributs message d'AUTRES
        # modules (spaceSwitchTargets, attributesHost...) : seul le data
        # node qui le connecte en rootGuide/guides[] est le sien.
        for plug in connections:
            node, _, attr = plug.partition(".")

            if attr == "rootGuide" or attr.startswith("guides["):
                return node

        return None

    @staticmethod
    def get_root_node(data_node):
        if not data_node or not cmds.objExists(data_node):
            return None

        connections = cmds.listConnections(f"{data_node}.rootGuide", source=True, destination=False, type="transform", plugs=False)

        if connections:
            return connections[0]

        return None

    @staticmethod
    def select_root_node(data_node):
        root_node = Guides.get_root_node(data_node)

        if root_node and cmds.objExists(root_node):
            cmds.select(root_node, replace=True)

    # --------------------------------------------------
    # UTILS
    # --------------------------------------------------

    def rename(self, name=None, side=None, index=None):

        if name is not None:
            self.name = name

        if side is not None:
            self.side = side

        if index is not None:
            self.index = index

        self.update_index()

        prefix = self.module_name

        # -----------------------------
        # UPDATE DATA NODE
        # -----------------------------

        if self.data_node and cmds.objExists(self.data_node):
            self.data_node = cmds.rename(self.data_node, f"{prefix}_GUIDE_DATA")

        # -----------------------------
        # UPDATE ROOT + GUIDES
        # -----------------------------
        #
        # On renomme le root DANS la boucle (repéré via son ancien nom),
        # sinon le renommer avant casse le test `guide == root` et le
        # root disparaît de self.guides. Convention (identique à
        # get_next_guide_name / attendue par get_guide_naming) :
        #   root     -> {prefix}_GUIDE_ROOT        (position 0)
        #   enfants  -> {prefix}_{position:02d}_GUIDE   (01, 02, ...)

        old_root = self.root

        new_guides = []
        position = 0

        for guide in self.guides:

            if not cmds.objExists(guide):
                continue

            if guide == old_root:
                self.root = cmds.rename(guide, f"{prefix}_GUIDE_ROOT")
                new_guides.append(self.root)
            else:
                new_guides.append(cmds.rename(guide, f"{prefix}_{position:02d}_GUIDE"))

            position += 1

        self.guides = new_guides

        # -----------------------------
        # UPDATE ATTRIBUTES DATA NODE
        # -----------------------------

        if self.data_node:
            self.unlock_attributes([ "baseName", "side", "index"])
            cmds.setAttr(f"{self.data_node}.baseName", self.name, type="string")
            cmds.setAttr(f"{self.data_node}.side", ["Center", "Left", "Right"].index(self.side))
            cmds.setAttr(f"{self.data_node}.index", self.index)

            self.lock_attributes()

    def delete(self):
        if self.root and cmds.objExists(self.root):
            cmds.delete(self.root)

        if self.data_node and cmds.objExists(self.data_node):
            cmds.delete(self.data_node)

    def get_positions(self):

        return {
            guide: cmds.xform(guide, q=True, ws=True, t=True)
            for guide in self.guides
        }

    @staticmethod
    def get_data(self, data_node = None):

        if data_node == None:
            data_node = self.data_node

        side_names = [
            "C",
            "L",
            "R"]

        return {
            "moduleType": cmds.getAttr(f"{data_node}.moduleType"),
            "baseName": cmds.getAttr(f"{data_node}.baseName"),
            "side": side_names[cmds.getAttr(f"{data_node}.side")],
            "positions": self.get_positions()
        }

    def serialize(self):

        return self.get_data()
        
