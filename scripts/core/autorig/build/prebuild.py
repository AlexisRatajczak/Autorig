# ====================================================================================================================
# PRE BUILD
# ====================================================================================================================
#
#   PreBuild(rig_data)
#       execute()               - run every pre build step
#       MODULE DISCOVERY        find_modules
#       VALIDATION              validate_modules, validate_attributes, validate_connections,
#                               validate_root_connection, validate_guides_connection, validate_parent_connection,
#                               validate_guides
#       DATA COLLECTION         collect_modules_data, collect_module_data
#       HELPERS                 get_root, get_guides, get_parent, get_extra_attributes, get_guide_parent,
#                               get_data_node, get_guide_xform, get_guide_data
#       RIG HIERARCHY           build_rig_hierarchy
#       CUSTOM                  custom() - run the preBuildScripts of the rig data
#       PREPARATION             prepare_scene, prepare_hierarchy, prepare_guides, prepare_modules
#
# ====================================================================================================================

import maya.cmds as cmds

from ..modules import registry
from ..build import custom_steps
from importlib import reload

reload(registry)
reload(custom_steps)


class PreBuild():

    def __init__(self, rig_data):

        self.rig_data = rig_data
        self.modules = []
        self.data = {}
        self.hierarchy_order = []
        self.hierarchy_data = {}

        # Guides class of the 'base' module: shared attributes and generic helpers.
        self.base_guides_class = registry.get_base_guides_class()

        self.execute()

    def execute(self):

        self.find_modules()
        self.validate_modules()
        self.collect_modules_data()
        self.build_rig_hierarchy()
        self.prepare_scene()
        self.prepare_hierarchy()
        self.prepare_guides()
        self.prepare_modules()
        self.custom()

    # ======================================================
    # MODULE DISCOVERY
    # ======================================================

    def find_modules(self):
        """Find every GUIDE_DATA connected to the rig data."""

        if not self.rig_data or not cmds.objExists(self.rig_data):
            raise RuntimeError(f"rig_data invalide : {self.rig_data}")

        if not cmds.attributeQuery("rigData", node=self.rig_data, exists=True):
            raise RuntimeError(f"{self.rig_data} n'a pas d'attribut rigData")

        self.modules = cmds.listConnections(f"{self.rig_data}.rigData", source=True, destination=False) or []

    # ======================================================
    # VALIDATION
    # ======================================================

    def validate_modules(self):
        """Check that every module is valid."""

        for module in self.modules:

            self.validate_attributes(module)
            self.validate_connections(module)
            self.validate_guides(module)

    def validate_attributes(self, module):

        """
        Check that the module has every attribute of ITS Guides class
        (from its moduleType; a module can remove base attributes).
        Falls back on the base Guides class.
        """

        guides_class = None

        if cmds.attributeQuery("moduleType", node=module, exists=True):
            module_type = cmds.getAttr(f"{module}.moduleType", asString=True)
            guides_class = registry.get_module_class(module_type)

        guides_class = guides_class or self.base_guides_class

        if not guides_class:
            return

        for attr in guides_class.ATTRIBUTES:

            if not cmds.attributeQuery(attr, node=module, exists=True):
                raise RuntimeError(f"{module} missing attribute : {attr}")

    # ======================================================
    # CONNECTIONS VALIDATION
    # ======================================================

    def validate_connections(self, module):

        self.validate_root_connection(module)
        self.validate_guides_connection(module)
        self.validate_parent_connection(module)

    def validate_root_connection(self, module):

        root = cmds.listConnections(f"{module}.rootGuide", source=True)
        if not root:
            raise RuntimeError(f"{module} has no rootGuide")

    def validate_guides_connection(self, module):

        guides = cmds.listConnections(f"{module}.guides", source=True)
        if not guides:
            raise RuntimeError(f"{module} has no guides")

    def validate_parent_connection(self, module):

        parent = cmds.listConnections(f"{module}.parent", source=True)
        if parent and not cmds.objExists(parent[0]):
            raise RuntimeError(f"{module} invalid parent")

    def validate_guides(self, module):
        """Check that every guide exists."""
        pass

    # ======================================================
    # DATA COLLECTION
    # ======================================================

    def collect_modules_data(self):
        """Convert every module into a Python dict."""

        self.data = {}

        for module in self.modules:
            self.data[module] = self.collect_module_data(module)

    def collect_module_data(self, module):
        """All the data of one module."""

        data = {
            "module": module,
            "moduleType": cmds.getAttr(f"{module}.moduleType", asString=True),
            "side": cmds.getAttr(f"{module}.side", asString=True),
            "index": cmds.getAttr(f"{module}.index"),
            "root": self.get_root(module),
            "guides": self.get_guides(module),
            "parent": self.get_parent(module),
        }

        data.update(self.get_extra_attributes(module))

        return data

    # ======================================================
    # HELPERS
    # ======================================================

    def get_root(self, module):

        connections = cmds.listConnections(f"{module}.rootGuide", source=True, destination=False)
        return connections[0] if connections else None

    def get_guides(self, module):

        connections = cmds.listConnections(f"{module}.guides", source=True, destination=False)
        return connections or []

    def get_parent(self, module):

        root = self.get_root(module)
        if not root:
            return None
        parent = cmds.listRelatives(root, parent=True, fullPath=True)
        return parent[0] if parent else None

    def get_extra_attributes(self, module):
        """Every other user attribute of the module node (enums as strings, messages as lists)."""

        handled = {"moduleType", "side", "index", "rootGuide", "guides", "parent"}

        extra = {}

        for attr in cmds.listAttr(module, userDefined=True) or []:

            if attr in handled:
                continue

            attr_type = cmds.getAttr(f"{module}.{attr}", type=True)

            if attr_type == "message":
                extra[attr] = cmds.listConnections(f"{module}.{attr}", source=True, destination=False) or []
                continue

            kwargs = {"asString": True} if attr_type == "enum" else {}

            try:
                extra[attr] = cmds.getAttr(f"{module}.{attr}", **kwargs)
            except Exception:
                extra[attr] = None

        return extra

    def get_guide_parent(self, guide):

        parent = cmds.listRelatives(guide, parent=True, fullPath=True)
        return parent[0] if parent else None

    def get_data_node(self, guide):
        """GUIDE_DATA connected to 'guide' (base Guides class, else a generic query)."""

        if self.base_guides_class:
            return self.base_guides_class.get_data_node(guide)

        connections = cmds.listConnections(
            f"{guide}.message", source=False, destination=True, type="network"
        ) or []

        return connections[0] if connections else None

    def get_guide_xform(self, guide):

        return {
            "translate": cmds.xform(guide, query=True, worldSpace=True, translation=True),
            "rotate": cmds.xform(guide, query=True, worldSpace=True, rotation=True),
            "scale": cmds.getAttr(f"{guide}.scale")[0],
        }

    def get_guide_data(self, guide):

        data = {"parent": self.get_guide_parent(guide)}
        data.update(self.get_guide_xform(guide))

        return data

    # ======================================================
    # RIG HIERARCHY
    # ======================================================

    def build_rig_hierarchy(self):
        """
        Dict of the whole rig hierarchy: every module with its attributes,
        every guide with its parent and xform.
        """

        self.hierarchy_data = {
            "rig_data": self.rig_data,
            "modules": {},
        }

        for module in self.modules:

            module_data = dict(self.data.get(module) or self.collect_module_data(module))
            guides = module_data.pop("guides", [])

            module_data["guides"] = {
                guide: self.get_guide_data(guide)
                for guide in guides
            }

            self.hierarchy_data["modules"][module] = module_data

        return self.hierarchy_data

    # ======================================================
    # CUSTOM
    # ======================================================

    def custom(self):
        """Character specific pre build: run the preBuildScripts of the rig data."""

        paths = custom_steps.get_script_paths(self.rig_data, "preBuildScripts")
        custom_steps.run_scripts(paths, label="pre-build step")


    # ======================================================
    # PREPARATION
    # ======================================================

    def prepare_scene(self):
        """Prepare the scene before the build."""
        pass

    def prepare_hierarchy(self):

        while len(self.hierarchy_order) < len(self.modules):
            progress = False
            for module in self.modules:
                if module in self.hierarchy_order:
                    continue
                parent = self.data[module]["parent"]

                if not parent:
                    self.hierarchy_order.append(module)
                    progress = True
                    continue

                parent_data = self.get_data_node(parent)
                if parent_data in self.hierarchy_order:
                    self.hierarchy_order.append(module)
                    progress = True

            if not progress:
                missing = [m for m in self.modules if m not in self.hierarchy_order]
                raise RuntimeError(f"Impossible de résoudre la hiérarchie des modules : {missing}")

        print(self.hierarchy_order)


    def prepare_guides(self):
        """Prepare the guides (freeze, alignment, ...)."""
        pass

    def prepare_modules(self):
        """Prepare the modules before their build."""
        pass
