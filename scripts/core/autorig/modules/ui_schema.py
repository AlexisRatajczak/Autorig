import json
from pathlib import Path


# ==========================================================
# UI SCHEMA LOADER
# ==========================================================
#
# Charge et fusionne les schémas d'attributs UI des modules
# (core/modules/<name>/attributes.json), édités à la main.
#
# Le GuideSettingsPanel n'introspecte plus le node Maya pour deviner
# quels attributs afficher : il demande à ce loader le schéma du module
# (via son moduleType) et n'affiche QUE ce qui y est déclaré (mode
# strict).
#
# Chaque attributs.json a la forme :
#
#   {
#     "extends": "base",                  # optionnel : fusion avec un parent
#     "module_label": "Arm",              # optionnel
#     "sections": {                       # optionnel : dépliants du panneau
#       "Orientation": {                  #   clé = valeur de "section" des attrs
#         "label": "Orientation",         #   optionnel (défaut = la clé)
#         "order": 20,                    #   ordre du dépliant
#         "collapsed": true               #   fermé par défaut
#       }
#     },
#     "attributes": {
#       "<attrName>": {
#         "label": "Nice Name",
#         "widget": "string|bool|int|float|enum|vector|matrix|message|message_list",
#         "order": 10,                    # ordre d'affichage (croissant)
#         "tooltip": "...",               # optionnel
#         "readonly": false,              # optionnel
#         "min": 0, "max": 10,            # optionnel (int/float)
#         "step": 1, "decimals": 3,       # optionnel (int/float)
#         "enum": ["A", "B"],             # optionnel (enum) - sinon lu sur le node
#         "accept": "guide",              # optionnel (message/message_list) : nodes acceptés,
#                                         #   "guide" ou un type de shape Maya (ex: "nurbsSurface").
#                                         #   Défaut : "guide" pour message, tout pour message_list.
#         "hidden": false,                # optionnel : déclaré mais pas affiché
#         "remove": true,                 # optionnel : retire un attribut hérité du parent
#         "section": "Orientation",       # optionnel : range l'attribut dans un dépliant
#         "section_collapsed": true,      # optionnel : dépliant fermé par défaut
#         "visible_when": {               # optionnel : visibilité conditionnelle
#           "attr": "<autreAttr>", "equals": 1      #   ou "in": [..], ou "min"/"max"
#         },                                        #   (valeur numérique >= min / <= max) ;
#                                                   #   ou une liste de conditions (toutes vraies)
#
#         # --- création de l'attribut côté DCC (voir DCC_ATTR_FLAGS) ---
#         "at": "enum", "dt": "string", "enumName": "A:B", "multi": true,
#         "min": 0, "value": 0            # 'value' = défaut (numérique / vecteur)
#       }
#     }
#   }
#
# attributes.json est la source unique : le SettingsWidget en tire l'UI
# (ordered_attributes), les classes Guides en tirent leur ATTRIBUTES
# (attribute_defs) pour créer les attributs Maya.
#

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

# Clés d'un attribut du schéma qui décrivent sa CRÉATION côté DCC
# (passées telles quelles à cmds.addAttr côté Maya). Le reste des clés
# (label, widget, order, tooltip, section, ...) est purement UI.
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
    Fusionne le schéma 'child' par-dessus 'parent' (déjà résolu). La
    fusion est faite entrée par entrée (attribut par attribut, section
    par section) : une entrée du child hérite des clés de la même entrée
    côté parent, puis les surcharge.
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

    """
    Retourne le schéma UI fusionné d'un module (dossier contenant son
    attributes.json), en résolvant récursivement la clé 'extends'.
    Retourne None si le module n'a pas de attributes.json exploitable.
    """

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

        # Un attribut 'hidden' est créé sur le node mais pas affiché : il
        # n'a pas besoin de 'widget'.
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
    Construit le dict ATTRIBUTES d'une classe Guides à partir du schéma
    d'un module : pour chaque attribut, on ne garde que les clés de
    création DCC (DCC_ATTR_FLAGS) + 'value' + 'lock'. Ordre préservé.

    - module_name  : force enumName de 'moduleType' (doit == MODULE_NAME
                     pour que la résolution registry fonctionne).
    - default_name : force la valeur par défaut de 'baseName'.
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

    """
    Retourne [(attrName, spec), ...] trié par 'order' croissant (puis
    par nom), en excluant les attributs 'hidden'.
    """

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

    """
    Retourne [(sectionTitle, spec), ...] trié par 'order' croissant (puis
    par nom), à partir du bloc 'sections' du schéma. Chaque spec peut
    porter 'order', 'collapsed', 'label'.
    """

    if not schema:
        return []

    items = list(schema.get("sections", {}).items())

    items.sort(key=lambda item: (item[1].get("order", 1000), item[0]))

    return items
