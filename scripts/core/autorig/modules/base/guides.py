# ====================================================================================================================
# BASE - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'base' module, parent of every module Guides: data node (network, ATTRIBUTES from
#   attributes.json), root guide + guide chain, duplicate / mirror of a module tree, renaming.
#
#       from_data_node(data_node) [classmethod]  - instance from an existing data node
#       BUILD               create, duplicate, create_mirror, get_child_modules, collect_module_tree,
#                           rebuild_module_tree, apply_guide_xform, mirror_guide, apply_settings, get_mirror_parent,
#                           copy_rig_data_connection_to
#       DATA NODE           create_data_node, get_parent_data, inherit_parent_attributes, inherit_parent_messages,
#                           add_attributes, add_attribute, add_vector_attribute, lock_attributes, unlock_attributes,
#                           set_attribute, rename_from_data
#       CONNECTIONS         connect_rig_data, connect_message, connect_guides
#       GUIDE MANAGEMENT    has_reached_max_guides, create_guide, get_next_guide_name, apply_offset, create_root,
#                           create_guides, add_guide, get_data_node, get_root_node, select_root_node
#       UTILS               rename, delete, get_positions, get_data, serialize
#
# ====================================================================================================================

from pathlib import Path

import maya.cmds as cmds

from .. import registry
from ..ui_schema import attribute_defs, load_ui_settings
from .... import log

# Module folder (holds attributes.json).
_MODULE_DIR = Path(__file__).resolve().parent


class Guides():

    MODULE_NAME = "base"

    DEFAULT_NAME = "Base"

    # Max guide count (None = no limit).
    MAX_GUIDES = None

    # Guides created with the module.
    AUTO_GUIDES = None

    # Offset of a guide added to the chain.
    ADD_GUIDE_OFFSET = {"translate": (0, 6, 0)}

    # Attributes inherited from the parent guide data node at creation (inherit_parent_attributes).
    INHERITED_ATTRIBUTES = ("side", "aimVector", "upVector", "simpleConnection", "offsetGroup", "noCtrl", "attributesHost")

    # ATTRIBUTES from attributes.json (single source, shared with the UI).
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

        # Increment while {module_name}_GUIDE_DATA belongs to ANOTHER module (never our own data node).
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
        # INSTANCE WITHOUT __init__
        # --------------------------------------------------

        instance = cls.__new__(cls)

        # --------------------------------------------------
        # DATA NODE
        # --------------------------------------------------

        instance.data_node = data_node

        # --------------------------------------------------
        # ATTRIBUTES
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
        # The 'parent' message is never connected: use the DAG parent of the root guide.

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
        Duplicate this module AND its child modules. Each guide is rebuilt from its
        captured data (settings + xform) instead of a Maya duplicate: child guides
        are not dragged along, the right guide count / settings are rebuilt.
        """

        if not self.root or not cmds.objExists(self.root):
            log.warning("No root guide to duplicate.")
            return None

        tree = self.collect_module_tree()

        created = self.rebuild_module_tree(tree, root_parent=self.parent)

        return created.get(self.data_node)

    def create_mirror(self, replace_side="Right", axis="YZ", parent=None):

        """
        Mirror this module AND its child modules, rebuilt from their captured data
        (settings + mirrored xform). 'parent' forces the mirror parent (nested call)
        instead of get_mirror_parent().
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

        """Data nodes of the modules whose root guide is DAG parented under one of this module's guides."""

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
        Data (settings + guide xforms) of this module and its child modules, to
        rebuild them with rebuild_module_tree(). Parents first:
        {
            "data_node": <source data node>,
            "instance": <source Guides instance>,
            "parent_data_node": <parent data node in THIS list, or None>,
            "parent_guide_index": <parent guide index in its chain, or None>,
            "settings": {...},  # attribute values (no message)
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
        Rebuild every module of 'tree' (collect_module_tree) with new guides placed
        from their xforms, hierarchy kept.

        root_parent : parent of the tree root module.
        root_side   : forced side of the root module (mirror).
        mirror_axis : "YZ" / "XZ" / "XY": mirror every guide and flip every side
                      (root aside, it uses root_side).

        Returns {old_data_node: new_instance}.
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

            # Mirror: the side changes, keep the index (L_Brow_03 <-> R_Brow_03).
            # Duplicate (same side): a new free index.
            initial_index = settings.get("index", source_instance.index) if mirror_axis else 0

            cls = source_instance.__class__
            new_instance = cls(name, side, initial_index, new_parent)

            # __init__ falls back on the selection when parent is None: force the resolved parent.
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

        """Place 'guide' with the captured world xform, then mirror it on 'mirror_axis' if given."""

        if not guide or not cmds.objExists(guide):
            return

        cmds.xform(guide, ws=True, t=xform.get("translate", (0, 0, 0)))
        cmds.xform(guide, ws=True, ro=xform.get("rotate", (0, 0, 0)))
        cmds.setAttr(f"{guide}.scale", *xform.get("scale", (1, 1, 1)))

        if mirror_axis:
            self.mirror_guide(guide, mirror_axis)

    def mirror_guide(self, guide, axis="YZ"):

        """Mirror a guide (position + orientation) through a temporary negative scale group, freeze, original parent restored."""

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

        """Apply 'settings' (attr -> value, from collect_module_tree) to target_instance.data_node, 'skip' keys aside."""

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

        """Parent of a mirrored module: the matching guide of the other side (Left <-> Right), else the same parent."""

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
        Connect target_instance to the same rig data as this module. The link lives
        on the RIG_DATA node (multi 'rigData'): found through the outgoing
        connections of .message.
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

        """User attributes (no message) of the parent guide data node, as a dict."""

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
        Copy each INHERITED_ATTRIBUTES value of the parent guide data node to this
        data node (same side, orientation...). Nothing without a parent.
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

        """Single message INHERITED_ATTRIBUTES (ex: attributesHost): connect the same source as the parent data node."""

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

    # ATTRIBUTES flags passed as is to cmds.addAttr.
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
        """Create every ATTRIBUTES attribute on the data node."""

        for attr, infos in self.ATTRIBUTES.items():
            self.add_attribute(attr, infos)

    def add_attribute(self, attr, infos):
        """Create 'attr' on the data node from its ATTRIBUTES entry 'infos', with its default value (also used by update_guides)."""

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

        """double3 attribute with its X / Y / Z children, set to 'default'."""

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

        """Set a data node attribute (any type); renames the module when baseName / side / index change."""

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

        """Read baseName / side / index from the data node and rename the module nodes."""

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
        
        # FIRST FREE INDEX
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

        """True if the guide count reached MAX_GUIDES (False without limit)."""

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

        # Yellow cube (half side size * 0.5): one linear curve along its 12 edges (some twice).
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

                # relative: keep the clean local transform of the new guide.
                cmds.parent(guide, parent, relative=True)

                if offset is not None:
                    self.apply_offset(guide, offset)

        self.guides.append(guide)
        return guide

    def get_next_guide_name(self):

        """
        Free guide name {side}_{baseName}_{moduleIndex:02d}_{guideIndex:02d}_GUIDE,
        as expected by MainBuild.get_guide_naming().
        """

        index = len(self.guides)
        name = f"{self.module_name}_{index:02d}_GUIDE"

        while cmds.objExists(name):
            index += 1
            name = f"{self.module_name}_{index:02d}_GUIDE"

        return name

    def apply_offset(self, guide, offset=None):

        """Local offset (translate / rotate / scale) of a guide already parented (relative) under its parent."""

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

        """Complete the chain (after create_root) up to AUTO_GUIDES through add_guide()."""

        target = self.AUTO_GUIDES or 0

        while len(self.guides) < target:

            if self.add_guide() is None:
                break

    def add_guide(self, offset=None):

        """
        Add a guide at the end of the chain (under the last guide or the root),
        connected to guides[i] and locked. Returns it, or None (max reached /
        failure). Used by create_guides() and the "+ Add Guide" button.
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

        # Other modules may target the guide (spaceSwitchTargets, attributesHost...):
        # its own data node is the one using it as rootGuide / guides[].
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
        # Root renamed INSIDE the loop (found by its old name). Naming (get_guide_naming):
        #   root     -> {prefix}_GUIDE_ROOT             (position 0)
        #   children -> {prefix}_{position:02d}_GUIDE   (01, 02, ...)

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
        
