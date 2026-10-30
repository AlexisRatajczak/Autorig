# ====================================================================================================================
# UI SCHEMA LOADER
# ====================================================================================================================
#
#   Loads and merges the hand-written attribute schemas of the modules (modules/<name>/attributes.json).
#   attributes.json is the single source: SettingsWidget builds its UI from it (ordered_attributes),
#   the Guides classes build their ATTRIBUTES from it (attribute_defs). Only declared attributes are shown.
#
#   attributes.json:
#
#   {
#     "extends": "base",                  # optional: merged over a parent schema
#     "module_label": "Arm",              # optional
#     "sections": {                       # optional: panel foldouts
#       "Orientation": {                  #   key = "section" value of the attributes
#         "label": "Orientation",         #   optional (default: the key)
#         "order": 20,                    #   foldout order
#         "collapsed": true               #   closed by default
#       }
#     },
#     "attributes": {
#       "<attrName>": {
#         "label": "Nice Name",
#         "widget": "string|bool|int|float|enum|vector|matrix|message|message_list",
#         "order": 10,                    # display order (ascending)
#         "tooltip": "...",               # optional
#         "readonly": false,              # optional
#         "min": 0, "max": 10,            # optional (int / float)
#         "step": 1, "decimals": 3,       # optional (int / float)
#         "enum": ["A", "B"],             # optional (enum), else read on the node
#         "accept": "guide",              # optional (message / message_list): "guide" or a Maya shape type
#                                         #   (ex: "nurbsSurface"). Default: "guide" for message, anything for lists.
#         "hidden": false,                # optional: created but not shown
#         "remove": true,                 # optional: removes an attribute inherited from the parent
#         "section": "Orientation",       # optional: foldout of the attribute
#         "section_collapsed": true,      # optional: foldout closed by default
#         "visible_when": {               # optional: conditional visibility
#           "attr": "<otherAttr>", "equals": 1      #   or "in": [..], or "min" / "max";
#         },                                        #   or a list of conditions (all true)
#
#         # --- DCC attribute creation (see DCC_ATTR_FLAGS) ---
#         "at": "enum", "dt": "string", "enumName": "A:B", "multi": true,
#         "min": 0, "value": 0            # 'value' = default (number / vector)
#       }
#     }
#   }
#
#   _load_raw(module_dir)                           - raw attributes.json of a module folder
#   _empty_schema()                                 - empty schema
#   _merge(parent, child)                           - merge a child schema over its parent
#   load_ui_settings(module_dir)                    - merged schema (resolves 'extends')
#   _validate(module_dir, schema)                   - print missing / unknown widgets
#   attribute_defs(schema, module_name, default_name) - ATTRIBUTES dict of a Guides class
#   ordered_attributes(schema)                      - [(attr, spec)] sorted by 'order', without hidden
#   ordered_sections(schema)                        - [(section, spec)] sorted by 'order'
#
# ====================================================================================================================

import json
from pathlib import Path


MODULES_DIR = Path(__file__).resolve().parent

SCHEMA_FILENAME = "attributes.json"

WIDGET_TYPES = (
    "string",
    "bool",
    "int",
    "float",
    "enum",
    "vector",
    "matrix",
    "message",
    "message_list",
)

# Schema keys describing the attribute CREATION (passed to cmds.addAttr).
# Every other key (label, widget, order, tooltip, section, ...) is UI only.
DCC_ATTR_FLAGS = (
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
    "usedAsColor",
)


def _load_raw(module_dir):

    path = Path(module_dir) / SCHEMA_FILENAME

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as file:
            content = file.read().strip()
    except OSError as error:
        print(f"Could not read '{path}' : {error}")
        return None

    if not content:
        return None

    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        print(f"Invalid JSON in '{path}' : {error}")
        return None


def _empty_schema():
    return {"module_label": None, "attributes": {}, "sections": {}}


def _merge(parent, child):

    """
    Merge 'child' over the resolved 'parent', entry by entry (attribute,
    section): a child entry inherits the parent keys, then overrides them.
    """

    result = _empty_schema()

    if parent:
        result["module_label"] = parent.get("module_label")
        result["attributes"] = {
            name: dict(spec)
            for name, spec in (parent.get("attributes") or {}).items()
        }
        result["sections"] = {
            name: dict(spec)
            for name, spec in (parent.get("sections") or {}).items()
        }

    if child.get("module_label"):
        result["module_label"] = child["module_label"]

    for name, spec in (child.get("attributes") or {}).items():

        spec = dict(spec or {})

        if spec.get("remove"):
            result["attributes"].pop(name, None)
            continue

        merged = dict(result["attributes"].get(name, {}))
        merged.update(spec)
        result["attributes"][name] = merged

    for name, spec in (child.get("sections") or {}).items():

        spec = dict(spec or {})

        if spec.get("remove"):
            result["sections"].pop(name, None)
            continue

        merged = dict(result["sections"].get(name, {}))
        merged.update(spec)
        result["sections"][name] = merged

    return result


def load_ui_settings(module_dir):

    """Merged UI schema of a module folder (resolves 'extends'), or None without a usable attributes.json."""

    module_dir = Path(module_dir)

    raw = _load_raw(module_dir)

    if raw is None:
        return None

    extends = raw.get("extends")

    parent = None

    if extends:

        parent_dir = MODULES_DIR / extends

        if parent_dir.resolve() == module_dir.resolve():
            print(f"'{module_dir.name}/attributes.json' : 'extends' pointe sur lui-même.")
        else:
            parent = load_ui_settings(parent_dir)

    schema = _merge(parent, raw)

    _validate(module_dir, schema)

    return schema


def _validate(module_dir, schema):

    for name, spec in schema.get("attributes", {}).items():

        # Hidden attributes are created but not shown: no 'widget' needed.
        if spec.get("hidden"):
            continue

        widget = spec.get("widget")

        if widget is None:
            print(f"'{module_dir.name}/attributes.json' : attribut '{name}' sans 'widget'.")
        elif widget not in WIDGET_TYPES:
            print(
                f"'{module_dir.name}/attributes.json' : attribut '{name}' widget "
                f"inconnu '{widget}' (attendu : {', '.join(WIDGET_TYPES)})."
            )


def attribute_defs(schema, module_name=None, default_name=None):

    """
    ATTRIBUTES dict of a Guides class: per attribute, only the creation keys
    (DCC_ATTR_FLAGS) + 'value' + 'lock'. Order kept.

    module_name  : forces the 'moduleType' enumName (must match MODULE_NAME for the registry).
    default_name : forces the 'baseName' default value.
    """

    defs = {}

    for name, spec in (schema or {}).get("attributes", {}).items():

        defs[name] = {
            key: value
            for key, value in spec.items()
            if key in DCC_ATTR_FLAGS or key in ("value", "lock")
        }

    if module_name and "moduleType" in defs:
        defs["moduleType"]["enumName"] = module_name

    if default_name is not None and "baseName" in defs:
        defs["baseName"]["value"] = default_name

    return defs


def ordered_attributes(schema):

    """[(attrName, spec), ...] sorted by 'order' then name, without 'hidden' attributes."""

    if not schema:
        return []

    items = [
        (name, spec)
        for name, spec in schema.get("attributes", {}).items()
        if not spec.get("hidden")
    ]

    items.sort(key=lambda item: (item[1].get("order", 1000), item[0]))

    return items


def ordered_sections(schema):

    """[(sectionTitle, spec), ...] of the 'sections' block, sorted by 'order' then name."""

    if not schema:
        return []

    items = list(schema.get("sections", {}).items())

    items.sort(key=lambda item: (item[1].get("order", 1000), item[0]))

    return items
