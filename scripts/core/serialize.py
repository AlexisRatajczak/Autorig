# ====================================================================================================================
# RIG SERIALIZE
# ====================================================================================================================
#
#   export_rig() dumps a whole rig (rig data + every module: hierarchy, settings, guide xforms, guide count,
#   pivot guides such as the foot heel / tiptoe / bank locators) to a dict / .json. rebuild_rig() rebuilds the
#   rig data and modules from it; modules with an unknown moduleType are skipped and listed in the report.
#
#   HELPERS     _connections, _module_root, _module_guides, _module_pivots, _jsonable, _guide_xform,
#               _read_settings, _module_parent, _order_modules
#   EXPORT      export_rig(rig_data_node, filepath), _export_module
#   REBUILD     rebuild_rig(source), rebuild_rig_data_only(source), rebuild_modules(source, module_nodes, rig_name),
#               _descendants, _rebuild_module_list, _load_json, _rebuild_rig_data, _rebuild_module,
#               _reconnect_messages
#   CTRL SHAPES export_ctrl_shapes(filepath, controls) - selected ctrls (else every '*_ctrl') shapes to a dict / .json,
#               import_ctrl_shapes(source) - re-apply them on every ctrl that exists, list_ctrls, _ctrl_transform
#
# ====================================================================================================================

import json

import maya.cmds as cmds

from .autorig.modules import registry
from .autorig.rigData import init_rigData
from .utilities import ctrl_utilities

from importlib import reload

reload(registry)
reload(init_rigData)
reload(ctrl_utilities)


SCHEMA_VERSION = 1

# Message attributes of a module's own wiring: rebuilt by create() / connect_rig_data(), never exported.
_INTERNAL_MESSAGE = {"parent", "rigData", "rootGuide", "guides"}


# ==========================================================
# HELPERS (scene reading)
# ==========================================================

def _connections(plug):
    return cmds.listConnections(plug, source=True, destination=False) or []


def _module_root(data_node):
    conns = _connections(f"{data_node}.rootGuide")
    return conns[0] if conns else None


def _module_guides(data_node):
    return _connections(f"{data_node}.guides")


def _jsonable(value):

    """Turn a cmds.getAttr value into plain JSON data."""

    if isinstance(value, (list, tuple)):

        # double3 getAttr returns [(x, y, z)] -> [x, y, z]
        if len(value) == 1 and isinstance(value[0], (list, tuple)):
            return list(value[0])

        return [_jsonable(item) for item in value]

    return value


def _guide_xform(guide):

    return {
        "translate": list(cmds.xform(guide, query=True, worldSpace=True, translation=True)),
        "rotate": list(cmds.xform(guide, query=True, worldSpace=True, rotation=True)),
        "scale": list(cmds.getAttr(f"{guide}.scale")[0]),
    }


def _read_settings(node):

    """
    Raw values of the user-defined attributes of 'node' (enums as int).
    Skips compound children and internal messages; other messages
    (ex: spaceSwitchTargets) are stored as {"__message__": [targets]}.
    """

    settings = {}

    for attr in cmds.listAttr(node, userDefined=True) or []:

        plug = f"{node}.{attr}"

        if not cmds.objExists(plug):
            continue

        try:
            if cmds.attributeQuery(attr, node=node, listParent=True):
                continue
        except Exception:
            pass

        try:
            attr_type = cmds.getAttr(plug, type=True)
        except Exception:
            continue

        if attr_type == "message":

            if attr in _INTERNAL_MESSAGE:
                continue

            targets = _connections(plug)

            if targets:
                settings[attr] = {"__message__": targets}

            continue

        try:
            settings[attr] = _jsonable(cmds.getAttr(plug))
        except Exception:
            continue

    return settings


def _module_parent(data_node, all_modules):

    """
    Parent of a module: the module whose guide is the DAG parent of the
    root guide of 'data_node'. Returns {"node": data node | None, "guide_index": int | None}.
    """

    root = _module_root(data_node)

    if not root:
        return {"node": None, "guide_index": None}

    dag_parent = cmds.listRelatives(root, parent=True) or []

    if not dag_parent:
        return {"node": None, "guide_index": None}

    parent_guide = dag_parent[0]

    for module in all_modules:

        if module == data_node:
            continue

        guides = _module_guides(module)

        if parent_guide in guides:
            return {"node": module, "guide_index": guides.index(parent_guide)}

    return {"node": None, "guide_index": None}


def _order_modules(modules):

    """Sort modules parents first (rebuild order)."""

    parent_of = {m: _module_parent(m, modules)["node"] for m in modules}

    ordered = []
    seen = set()

    def visit(module):

        if module in seen:
            return

        parent = parent_of.get(module)

        if parent and parent in parent_of:
            visit(parent)

        seen.add(module)
        ordered.append(module)

    for module in modules:
        visit(module)

    return ordered


# ==========================================================
# EXPORT
# ==========================================================

def export_rig(rig_data_node, filepath=None):

    """
    Export the rig connected to 'rig_data_node' (a *_RIG_DATA node).
    Also writes it to 'filepath' (.json) when given.

    Returns:
    {
        "version": 1,
        "rig_data": {"node", "rig_name", "settings": {...}},
        "modules": [
            {
                "node", "module_type", "base_name", "side", "index",
                "guide_count",
                "guide_nodes": [<names>],
                "guides": [{"translate","rotate","scale"}, ...],
                "pivot_nodes": {<attr>: <name>},          # PIVOT_GUIDES (foot locators), {} if none
                "pivots": {<attr>: {"translate","rotate","scale"}},
                "settings": {...},
                "parent": {"node": <parent data node|None>, "guide_index": <int|None>}
            },
            ...
        ]
    }
    """

    if not rig_data_node or not cmds.objExists(rig_data_node):
        raise ValueError(f"Rig data '{rig_data_node}' introuvable.")

    modules = sorted(set(_connections(f"{rig_data_node}.rigData")))
    ordered = _order_modules(modules)

    data = {
        "version": SCHEMA_VERSION,
        "rig_data": {
            "node": rig_data_node,
            "rig_name": cmds.getAttr(f"{rig_data_node}.rigName"),
            "settings": _read_settings(rig_data_node),
        },
        "modules": [_export_module(module, modules) for module in ordered],
    }

    if filepath:
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    return data


def _module_pivots(data_node):

    """
    {attr: pivot guide} of the module PIVOT_GUIDES (ex: foot heel / tiptoe / bankL / bankR),
    through its Guides class. {} for a module without pivot guides.
    """

    instance = registry.load_guide(data_node)

    return instance.get_pivot_guides() if instance and hasattr(instance, "get_pivot_guides") else {}


def _export_module(data_node, all_modules):

    guide_nodes = _module_guides(data_node)
    pivots = _module_pivots(data_node)

    settings = _read_settings(data_node)

    # Pivot guide messages: rebuilt from "pivots" (their own xforms), not reconnected as settings.
    for attr in pivots:
        settings.pop(attr, None)

    return {
        "node": data_node,
        "module_type": cmds.getAttr(f"{data_node}.moduleType", asString=True),
        "base_name": cmds.getAttr(f"{data_node}.baseName"),
        "side": cmds.getAttr(f"{data_node}.side", asString=True),
        "index": cmds.getAttr(f"{data_node}.index"),
        "guide_count": len(guide_nodes),
        "guide_nodes": guide_nodes,
        "guides": [_guide_xform(guide) for guide in guide_nodes if cmds.objExists(guide)],
        "pivot_nodes": dict(pivots),
        "pivots": {attr: _guide_xform(pivot) for attr, pivot in pivots.items() if cmds.objExists(pivot)},
        "settings": settings,
        "parent": _module_parent(data_node, all_modules),
    }


# ==========================================================
# REBUILD
# ==========================================================

def _new_report():
    return {"rig_data": None, "created": [], "skipped": [], "warnings": []}


def rebuild_rig(source):

    """
    Rebuild a whole rig (rig data + modules) from an export_rig dict or .json path.
    The rig data is reused if it exists; modules are rebuilt parents first;
    modules with an unknown moduleType are skipped.

    Returns:
    {
        "rig_data": <node>,
        "created": [{"old", "new", "module_type"}, ...],
        "skipped": [{"old", "module_type", "reason"}, ...],
        "warnings": [str, ...],
    }
    """

    data = source if isinstance(source, dict) else _load_json(source)

    report = _new_report()

    rig_obj, rig_name = _rebuild_rig_data(data.get("rig_data") or {}, report)
    report["rig_data"] = rig_obj.data_node

    _rebuild_module_list(data.get("modules") or [], rig_name, report)

    return report


def rebuild_rig_data_only(source):

    """Rebuild ONLY the rig data of the export (settings + colors), reused if it exists."""

    data = source if isinstance(source, dict) else _load_json(source)

    report = _new_report()

    rig_obj, _ = _rebuild_rig_data(data.get("rig_data") or {}, report)
    report["rig_data"] = rig_obj.data_node

    return report


def rebuild_modules(source, module_nodes, rig_name=None):

    """
    Rebuild only 'module_nodes' (exported names) AND their child modules.

    Does NOT rebuild the rig data. Modules are connected to 'rig_name' (or
    the exported one; <rig_name>_RIG_DATA must exist). A module whose parent
    is neither rebuilt nor in the scene goes under the root.
    """

    data = source if isinstance(source, dict) else _load_json(source)

    all_modules = data.get("modules") or []

    wanted = set()

    for node in module_nodes:
        wanted.update(_descendants(node, all_modules))

    # Keep the export order (parents first).
    subset = [module for module in all_modules if module["node"] in wanted]

    if rig_name is None:
        rig_name = (data.get("rig_data") or {}).get("rig_name")

    report = _new_report()

    _rebuild_module_list(subset, rig_name, report)

    return report


def _descendants(node, modules):

    """'node' and all its descendants (through parent.node) in 'modules'."""

    by_node = {module["node"] for module in modules}

    children = {}

    for module in modules:
        parent = (module.get("parent") or {}).get("node")
        children.setdefault(parent, []).append(module["node"])

    result = []
    stack = [node]

    while stack:

        current = stack.pop()

        if current not in by_node or current in result:
            continue

        result.append(current)
        stack.extend(children.get(current, []))

    return result


def _rebuild_module_list(modules, rig_name, report):

    old_to_new = {}
    guide_map = {}
    pending_messages = []

    for module in modules:

        module_type = module.get("module_type")

        cls = registry.get_module_class(module_type)

        if cls is None:
            report["skipped"].append({
                "old": module.get("node"),
                "module_type": module_type,
                "reason": "moduleType inconnu du registry",
            })
            continue

        instance = _rebuild_module(cls, module, old_to_new, guide_map, pending_messages, report)

        old_to_new[module.get("node")] = instance

        if rig_name:
            instance.connect_rig_data(rig_name)

        instance.lock_attributes()

        report["created"].append({
            "old": module.get("node"),
            "new": instance.data_node,
            "module_type": module_type,
        })

    _reconnect_messages(pending_messages, guide_map, report)

    return report


def _load_json(filepath):

    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)


def _rebuild_rig_data(rig_data, report):

    rig_name = rig_data.get("rig_name") or "RIG"
    node = f"{rig_name}_RIG_DATA"

    rig_obj = init_rigData.RigData(rig_name)

    if cmds.objExists(node):
        report["warnings"].append(f"'{node}' existe déjà : réutilisé.")
        rig_obj.data_node = node
    else:
        rig_obj.create()

    for attr, value in (rig_data.get("settings") or {}).items():

        if isinstance(value, dict):
            continue

        if attr in ("rigName",):
            continue

        try:
            rig_obj.set_attribute(attr, value)
        except Exception as error:
            report["warnings"].append(f"rig_data.{attr} : {error}")

    return rig_obj, rig_obj.rig_name


def _rebuild_module(cls, module, old_to_new, guide_map, pending_messages, report):

    # -- parent --------------------------------------------------------
    new_parent = None
    parent_ref = module.get("parent") or {}
    parent_old = parent_ref.get("node")
    guide_index = parent_ref.get("guide_index")

    if parent_old and parent_old in old_to_new:

        parent_instance = old_to_new[parent_old]
        parent_guides = parent_instance.guides

        if guide_index is not None and guide_index < len(parent_guides):
            new_parent = parent_guides[guide_index]
        else:
            new_parent = parent_instance.root

    elif parent_old and cmds.objExists(parent_old):

        # Parent already in the scene (modules imported into an existing rig).
        parent_guides = _module_guides(parent_old)

        if guide_index is not None and guide_index < len(parent_guides):
            new_parent = parent_guides[guide_index]
        elif parent_guides:
            new_parent = parent_guides[0]

    elif parent_old:
        report["warnings"].append(
            f"Module '{module.get('node')}' : parent '{parent_old}' absent, "
            f"rattaché à la racine."
        )

    # -- instance -----------------------------------------------------
    name = module.get("base_name") or module.get("module_type") or "Module"
    side = module.get("side") or "Center"
    index = module.get("index") or 0

    instance = cls(name, side, index, new_parent)
    instance.parent = new_parent
    instance.create_data_node()

    # -- guides -----------------------------------------------------
    guides = module.get("guides") or []

    instance.create_root(parent=new_parent)

    if guides:
        instance.apply_guide_xform(instance.root, guides[0])

    for guide_xform in guides[1:]:

        new_guide = instance.create_guide(parent=instance.guides[-1])

        if new_guide:
            instance.apply_guide_xform(new_guide, guide_xform)

    instance.connect_guides()

    # Old guide name -> new one (for message lists).
    for old_guide, new_guide in zip(module.get("guide_nodes") or [], instance.guides):
        guide_map[old_guide] = new_guide

    # -- pivot guides (ex: foot heel / tiptoe / bankL / bankR) ----------
    if hasattr(instance, "create_pivot_guides"):

        pivot_xforms = module.get("pivots") or {}
        old_pivots = module.get("pivot_nodes") or {}

        for attr, pivot in instance.create_pivot_guides().items():

            if attr in pivot_xforms:
                instance.apply_guide_xform(pivot, pivot_xforms[attr])

            if attr in old_pivots:
                guide_map[old_pivots[attr]] = pivot

    # -- settings -----------------------------------------------------
    pivot_attrs = getattr(instance, "PIVOT_GUIDES", {})

    for attr, value in (module.get("settings") or {}).items():

        # Pivot guide messages: connected by create_pivot_guides (older exports kept them in settings).
        if attr == "moduleType" or attr in pivot_attrs:
            continue

        if isinstance(value, dict) and "__message__" in value:
            pending_messages.append((instance, attr, value["__message__"]))
            continue

        try:
            instance.set_attribute(attr, value)
        except Exception as error:
            report["warnings"].append(
                f"Module '{instance.data_node}' : settings '{attr}' -> {error}"
            )

    return instance


def _reconnect_messages(pending_messages, guide_map, report):

    """
    Reconnect message attributes (ex: spaceSwitchTargets) once every module
    is rebuilt. Targets are remapped through guide_map, else used as is if they exist.
    """

    for instance, attr, targets in pending_messages:

        plug = f"{instance.data_node}.{attr}"

        if not cmds.objExists(plug):
            continue

        connected = 0

        # Single message (ex: attributesHost): one target, no index.
        is_multi = cmds.attributeQuery(attr, node=instance.data_node, multi=True)

        if not is_multi:
            targets = targets[:1]

        for old_target in targets:

            new_target = guide_map.get(old_target, old_target)

            if not cmds.objExists(new_target) or not cmds.objExists(f"{new_target}.message"):
                report["warnings"].append(
                    f"Module '{instance.data_node}' : cible '{old_target}' de '{attr}' introuvable."
                )
                continue

            cmds.setAttr(plug, lock=False)
            target_plug = f"{plug}[{connected}]" if is_multi else plug
            cmds.connectAttr(f"{new_target}.message", target_plug, force=True)
            connected += 1

    for instance, _, _ in pending_messages:
        instance.lock_attributes()


# ==========================================================
# CTRL SHAPES
# ==========================================================

def _ctrl_transform(node):

    """Ctrl transform of 'node' (a shape -> its parent), if it holds nurbsCurve shapes, else None."""

    if not node or not cmds.objExists(node):
        return None

    if cmds.objectType(node, isAType="shape"):
        node = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]

    if not node or not cmds.objectType(node, isAType="transform"):
        return None

    curves = cmds.listRelatives(node, shapes=True, type="nurbsCurve", fullPath=True) or []

    return node if curves else None


def list_ctrls(controls=None):

    """
    Ctrls to export: 'controls' if given, else the selection, else every '*_ctrl'
    transform of the scene. Only transforms holding curves, each once, in order.
    """

    if controls is None:
        controls = cmds.ls(selection=True, long=True) or cmds.ls("*_ctrl", type="transform", long=True) or []

    result = []

    for node in controls:

        ctrl = _ctrl_transform(node)

        if ctrl and ctrl not in result:
            result.append(ctrl)

    return result


def export_ctrl_shapes(filepath=None, controls=None):

    """
    Shapes of the selected ctrls (every '*_ctrl' if nothing is selected, or 'controls')
    to a dict, written to 'filepath' (.json) when given.

    Returns:
    {
        "version": 1,
        "controls": {
            <ctrl>: {"name", "shapes": [{"name", "points", "degree", "form", "color", "line_width"}, ...]},
            ...
        }
    }
    """

    data = {"version": SCHEMA_VERSION, "controls": {}}

    for ctrl in list_ctrls(controls):

        shapes_data = ctrl_utilities.Control(ctrl).get_shapes_data()

        if shapes_data and shapes_data["shapes"]:
            data["controls"][shapes_data["name"]] = shapes_data

    if filepath:
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    print(f"Ctrl shapes : {len(data['controls'])} ctrl(s) exporté(s){f' -> {filepath}' if filepath else ''}.")

    return data


def import_ctrl_shapes(source):

    """
    Re-apply the shapes of 'source' (export_ctrl_shapes dict, or .json path) on every
    ctrl that exists in the scene (Control.set_shapes_data). Each ctrl is tried on
    its own: one failure does not stop the others.

    Returns {"applied": [ctrl], "missing": [ctrl], "failed": [(ctrl, error)]}.
    """

    data = _load_json(source) if isinstance(source, str) else (source or {})

    report = {"applied": [], "missing": [], "failed": []}

    for ctrl, shapes_data in (data.get("controls") or {}).items():

        if not cmds.objExists(ctrl):
            report["missing"].append(ctrl)
            continue

        try:
            ctrl_utilities.Control(ctrl).set_shapes_data(shapes_data)
            report["applied"].append(ctrl)
        except Exception as error:
            report["failed"].append((ctrl, str(error)))
            cmds.warning(f"Ctrl shapes : échec sur '{ctrl}' : {error}")

    print(
        f"Ctrl shapes : {len(report['applied'])} appliqué(s), "
        f"{len(report['missing'])} introuvable(s), {len(report['failed'])} en échec."
    )

    return report
