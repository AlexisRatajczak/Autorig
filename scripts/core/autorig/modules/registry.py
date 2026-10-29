import ast
import importlib
from pathlib import Path

import maya.cmds as cmds

from ... import log


# ==========================================================
# MODULE REGISTRY
# ==========================================================
#
# Retrouve la classe Guides / Builder correcte pour un data node, à
# partir de son attribut moduleType, en scannant les dossiers
# core/autorig/modules/<name>/guides.py et en n'important que celui qui
# correspond.
#

MODULES_DIR = Path(__file__).resolve().parent

# Builder dont héritent tous les autres (voir get_builder_class).
BASE_BUILDER_PATH = "scripts.core.autorig.modules.base.builder"


def _read_module_name(guides_file):

    """
    MODULE_NAME de la classe Guides de 'guides_file', lu sans importer le
    fichier (ast), ou None.
    """

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

    """
    {moduleType: dossier} de tous les modules de core/autorig/modules
    (MODULE_NAME de la classe Guides de chaque guides.py), triés par nom.
    """

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

    """
    Retrouve le dossier de core/modules correspondant à un moduleType
    (ex: 'base', 'SimpleFk'), en lisant MODULE_NAME sur la classe
    Guides de guides.py de chaque module (sans l'importer, via ast).
    """

    if not module_type:
        return None

    return list_module_types().get(module_type)


def get_module_class(module_type):

    """
    Retrouve la classe Guides correspondant à un moduleType (ex: 'base',
    'SimpleFk'), en scannant les dossiers de core/modules.
    """

    module_dir = _find_module_dir(module_type)

    if not module_dir:
        log.error(f"No module class found for moduleType '{module_type}'.")
        return None

    import_path = f"scripts.core.autorig.modules.{module_dir.name}.guides"

    try:
        python_module = importlib.import_module(import_path)
        importlib.reload(python_module)
    except Exception as e:
        print(f"Could not import '{import_path}' : {e}")
        return None

    return getattr(python_module, "Guides", None)


def get_builder_class(module_type):

    """
    Retrouve la classe Builder correspondant à un moduleType (ex: 'base',
    'SimpleFk'), en s'appuyant sur le même dossier que
    get_module_class (identifié via MODULE_NAME dans guides.py), mais en
    important builder.py.
    """

    module_dir = _find_module_dir(module_type)

    if not module_dir:
        log.error(f"No builder class found for moduleType '{module_type}'.")
        return None

    builder_file = module_dir / "builder.py"

    if not builder_file.exists():
        return None

    import_path = f"scripts.core.autorig.modules.{module_dir.name}.builder"

    try:
        # Builder de base rechargé d'abord : les builders l'importent sans le
        # recharger (from ..base.builder import Builder) - sinon ils
        # garderaient l'ancienne classe Base de la session Maya. Rechargé
        # une seule fois ici : tous partagent la même classe Base.
        importlib.reload(importlib.import_module(BASE_BUILDER_PATH))

        python_module = importlib.import_module(import_path)
        importlib.reload(python_module)
    except Exception as e:
        print(f"Could not import '{import_path}' : {e}")
        return None

    return getattr(python_module, "Builder", None)


def get_settings_widget_class(module_type):

    """
    Retourne la classe SettingsWidget du module correspondant à un
    moduleType (définie dans <module>/ui_settings.py). C'est le widget
    Qt complet du panneau de settings de ce module (layout + build).
    Retourne None si introuvable.
    """

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
    """Classe Guides du module 'base'."""
    return get_module_class("base")


def get_base_builder_class():
    """Classe Builder du module 'base'."""
    return get_builder_class("base")


def load_guide(data_node):

    """
    Reconstruit l'instance Guides correcte pour un data node, en
    résolvant sa classe via son attribut moduleType (au lieu de supposer
    la même classe que l'appelant).
    """

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
