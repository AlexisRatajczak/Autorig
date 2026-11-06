# ====================================================================================================================
# MODULE REGISTRY
# ====================================================================================================================
#
#   Finds the Guides / Builder / SettingsWidget class of a moduleType by scanning
#   core/autorig/modules/<name>/guides.py (MODULE_NAME read with ast) and importing only the matching one.
#
#   _read_module_name(guides_file)          - MODULE_NAME of a guides.py, without importing it
#   list_module_types()                     - {moduleType: folder} of every module
#   _find_module_dir(module_type)           - folder of a moduleType
#   get_module_class(module_type)           - Guides class (parent guides reloaded first)
#   reload_parent_guides(guides_class)      - reload the parent guides modules (base first)
#   get_builder_class(module_type)          - Builder class (base builder reloaded first)
#   get_settings_widget_class(module_type)  - SettingsWidget class (ui_settings.py)
#   get_base_guides_class()                 - Guides class of 'base'
#   get_base_builder_class()                - Builder class of 'base'
#   load_guide(data_node)                   - Guides instance of a data node
#
# ====================================================================================================================

import ast
import importlib
import sys
from pathlib import Path

import maya.cmds as cmds

from ... import log


MODULES_DIR = Path(__file__).resolve().parent

# Builder every other builder inherits from (see get_builder_class).
BASE_BUILDER_PATH = "scripts.core.autorig.modules.simpleBase.builder"

# moduleType of the simpleBase module (MODULE_NAME), parent of every module with joints.
BASE_MODULE_TYPE = "Simple_Jnt"


def _read_module_name(guides_file):

    """MODULE_NAME of the Guides class of 'guides_file', read with ast (no import), or None."""

    try:

        with open(guides_file, "r", encoding="utf-8") as file:
            tree = ast.parse(file.read())

    except Exception as e:
        print(f"Could not parse '{guides_file}' : {e}")
        return None

    for node in tree.body:

        if not isinstance(node, ast.ClassDef) or node.name != "Guides":
            continue

        for class_node in node.body:

            if not isinstance(class_node, ast.Assign):
                continue

            for target in class_node.targets:

                if isinstance(target, ast.Name) and target.id == "MODULE_NAME":
                    return ast.literal_eval(class_node.value)

    return None


def list_module_types():

    """{moduleType: folder} of every module in core/autorig/modules, sorted by name."""

    module_types = {}

    for module_dir in sorted(MODULES_DIR.iterdir()):

        if not module_dir.is_dir() or module_dir.name == "__pycache__":
            continue

        guides_file = module_dir / "guides.py"

        if not guides_file.exists():
            continue

        module_name = _read_module_name(guides_file)

        if module_name:
            module_types[module_name] = module_dir

    return dict(sorted(module_types.items(), key=lambda item: item[0].lower()))


def _find_module_dir(module_type):

    """Folder of a moduleType (ex: 'base', 'SimpleFk'), or None."""

    if not module_type:
        return None

    return list_module_types().get(module_type)


def get_module_class(module_type):

    """Guides class of a moduleType (ex: 'base', 'SimpleFk')."""

    module_dir = _find_module_dir(module_type)

    if not module_dir:
        log.error(f"No module class found for moduleType '{module_type}'.")
        return None

    import_path = f"scripts.core.autorig.modules.{module_dir.name}.guides"

    try:
        python_module = importlib.import_module(import_path)

        # Reload the parent guides first (base -> ... -> this one): a module guides.py only
        # imports them, the Maya session would keep their stale class (ex: base mirror code).
        reload_parent_guides(getattr(python_module, "Guides", None))

        importlib.reload(python_module)
    except Exception as e:
        print(f"Could not import '{import_path}' : {e}")
        return None

    return getattr(python_module, "Guides", None)


def reload_parent_guides(guides_class):

    """
    Reload the python modules of the parent classes of 'guides_class' (MRO, base
    first), this package only, each once. Called before reloading the module itself
    so it subclasses the fresh parents.
    """

    if guides_class is None:
        return

    package = __name__.rsplit(".", 1)[0]

    done = set()

    for cls in reversed(guides_class.__mro__[1:]):

        name = cls.__module__

        if name in done or not name.startswith(package) or name not in sys.modules:
            continue

        done.add(name)
        importlib.reload(sys.modules[name])


def get_builder_class(module_type):

    """Builder class of a moduleType (builder.py of the same folder as get_module_class)."""

    module_dir = _find_module_dir(module_type)

    if not module_dir:
        log.error(f"No builder class found for moduleType '{module_type}'.")
        return None

    builder_file = module_dir / "builder.py"

    if not builder_file.exists():
        return None

    import_path = f"scripts.core.autorig.modules.{module_dir.name}.builder"

    try:
        # Reload the base builder first: module builders import it without
        # reloading, they would keep the stale class of the Maya session.
        importlib.reload(importlib.import_module(BASE_BUILDER_PATH))

        python_module = importlib.import_module(import_path)
        importlib.reload(python_module)
    except Exception as e:
        print(f"Could not import '{import_path}' : {e}")
        return None

    return getattr(python_module, "Builder", None)


def get_settings_widget_class(module_type):

    """SettingsWidget class of a moduleType (<module>/ui_settings.py), or None."""

    module_dir = _find_module_dir(module_type)

    if not module_dir:
        log.error(f"No settings widget found for moduleType '{module_type}'.")
        return None

    import_path = f"scripts.core.autorig.modules.{module_dir.name}.ui_settings"

    try:
        python_module = importlib.import_module(import_path)
        importlib.reload(python_module)
    except Exception as e:
        print(f"Could not import '{import_path}' : {e}")
        return None

    return getattr(python_module, "SettingsWidget", None)


def get_base_guides_class():
    """Guides class of the 'base' module."""
    return get_module_class(BASE_MODULE_TYPE)


def get_base_builder_class():
    """Builder class of the 'base' module."""
    return get_builder_class(BASE_MODULE_TYPE)


def load_guide(data_node):

    """Guides instance of a data node, from its moduleType."""

    if not data_node or not cmds.objExists(data_node):
        return None

    if not cmds.attributeQuery("moduleType", node=data_node, exists=True):
        return None

    enum_names = cmds.attributeQuery("moduleType", node=data_node, listEnum=True)

    if not enum_names:
        return None

    module_type = enum_names[0]

    cls = get_module_class(module_type)

    if not cls:
        return None

    return cls.from_data_node(data_node)
