# ====================================================================================================================
# ATTRIBUTE UTILITIES
# ====================================================================================================================
#
#   ADD
#       add_attribute(node, name, attr_type, default, minimum, maximum, keyable, channel_box, lock, nice_name,
#                     enum_names)                   - one call for any attribute type, skipped if it exists
#       add_separator(node, label, name)            - locked enum '____________' in the channel box (UI section),
#                                                     once per label and node
#       add_attributes(node, label, attributes)     - a separator, then a list of add_attribute (one section)
#   CONNECTIONS
#       get_connections(plug)                       - {"inputs": [...], "outputs": [...]} plugs of an attribute
#       get_node_connections(node, attributes)      - {attr: get_connections} of a node (user attributes default)
#   HELPERS
#       get_free_name(node, base)                   - first free attribute name 'base', 'base1', 'base2'...
#
# ====================================================================================================================

import maya.cmds as cmds


# Separator nice name: the line shown in the channel box.
SEPARATOR = "____________"

# attr_type -> addAttr flags (numeric 'at', 'dt' data types, compounds of 3).
NUMERIC_TYPES = ("float", "double", "long", "short", "byte", "bool", "enum", "doubleAngle", "doubleLinear", "time")
DATA_TYPES = ("string", "matrix", "stringArray", "doubleArray", "floatArray", "Int32Array", "vectorArray")
COMPOUND_TYPES = {"double3": "double", "float3": "float", "long3": "long"}


# ==========================================================
# ADD
# ==========================================================

def add_attribute(
    node,
    name,
    attr_type="float",
    default=None,
    minimum=None,
    maximum=None,
    keyable=True,
    channel_box=False,
    lock=False,
    nice_name=None,
    enum_names=None
):

    """
    Add attribute 'name' to 'node' (nothing if it already exists) and return its plug.

        attr_type   : "float" / "double" / "long" / "bool" / "enum" ... (numeric),
                      "string" / "matrix" ... (data), "double3" / "float3" (vector),
                      "message";
        default     : default value (number, string, 3 values for a vector);
        minimum / maximum : bounds (numeric types);
        keyable     : keyable (shown in the channel box); False + channel_box:
                      shown but not keyable;
        lock        : locked once set;
        nice_name   : display name;
        enum_names  : enum fields, list or "A:B:C" ("enum" only).

    Returns '{node}.{name}', or None if 'node' does not exist.
    """

    if not node or not cmds.objExists(node):
        return None

    plug = f"{node}.{name}"

    if cmds.attributeQuery(name, node=node, exists=True):
        return plug

    flags = {"longName": name}

    if nice_name:
        flags["niceName"] = nice_name

    if attr_type == "message":
        flags["attributeType"] = "message"
        cmds.addAttr(node, **flags)
        return plug

    if attr_type in DATA_TYPES:
        flags["dataType"] = attr_type
        cmds.addAttr(node, **flags)

        if attr_type == "string" and default is not None:
            cmds.setAttr(plug, default, type="string")

        return _finish(plug, keyable=False, channel_box=False, lock=lock)

    if attr_type in COMPOUND_TYPES:

        child_type = COMPOUND_TYPES[attr_type]
        values = list(default) if default is not None else [0.0, 0.0, 0.0]

        cmds.addAttr(node, attributeType=attr_type, keyable=keyable, **flags)

        for axis, value in zip("XYZ", values):
            cmds.addAttr(node, longName=f"{name}{axis}", attributeType=child_type, parent=name, keyable=keyable)

        cmds.setAttr(plug, *values, type=attr_type)

        return _finish(plug, keyable=keyable, channel_box=channel_box, lock=lock)

    flags["attributeType"] = attr_type

    if attr_type == "enum":
        flags["enumName"] = ":".join(enum_names) if isinstance(enum_names, (list, tuple)) else (enum_names or "Off:On")

    if minimum is not None:
        flags["minValue"] = minimum

    if maximum is not None:
        flags["maxValue"] = maximum

    if default is not None:
        flags["defaultValue"] = default

    cmds.addAttr(node, keyable=keyable, **flags)

    return _finish(plug, keyable=keyable, channel_box=channel_box, lock=lock)


def _finish(plug, keyable=True, channel_box=False, lock=False):
    """Channel box display (non keyable but shown) and lock of a new attribute. Returns the plug."""

    if not keyable and channel_box:
        cmds.setAttr(plug, channelBox=True)

    if lock:
        cmds.setAttr(plug, lock=True)

    return plug


def add_separator(node, label="SETTINGS", name=None):

    """
    Channel box separator on 'node': a locked enum shown as '____________' with
    'label' as its only field (ex: STRETCH, FOOT ROLL), not keyable but visible.
    'name' : attribute name (default 'sep{Label}'). Already there (same section
    asked by several modules on one ctrl): kept, not duplicated. Returns its plug.
    Call it BEFORE the attributes of its section (channel box order = creation order).
    """

    if not node or not cmds.objExists(node):
        return None

    attr = name or "sep" + "".join(part.capitalize() for part in str(label).replace("_", " ").split())

    if cmds.attributeQuery(attr, node=node, exists=True):
        return f"{node}.{attr}"

    return add_attribute(
        node,
        attr,
        attr_type="enum",
        enum_names=[SEPARATOR],
        keyable=False,
        channel_box=True,
        lock=True,
        nice_name= str(label).upper() or SEPARATOR
    )


def add_attributes(node, label, attributes):

    """
    One channel box section: add_separator(node, label) (None: no separator), then each
    'attributes' entry as add_attribute(node, **entry) ({"name": ..., "attr_type": ...,
    "default": ...}). Returns {name: plug}.

        add_attributes(ctrl, "STRETCH", [
            {"name": "stretch", "default": 1.0, "minimum": 0.0, "maximum": 1.0},
            {"name": "squash", "default": 0.5, "minimum": 0.0, "maximum": 1.0},
        ])
    """

    if label:
        add_separator(node, label)

    plugs = {}

    for entry in attributes:

        entry = dict(entry)
        name = entry.pop("name")

        plugs[name] = add_attribute(node, name, **entry)

    return plugs


# ==========================================================
# CONNECTIONS
# ==========================================================

def get_connections(plug):

    """
    Connections of the attribute 'plug' ('node.attr'), as plugs:

        {"inputs": [source plugs driving it], "outputs": [destination plugs it drives]}

    Child / element plugs included (ex: translateX of translate, multi[i]). Empty
    lists for a missing plug.
    """

    connections = {"inputs": [], "outputs": []}

    if not plug or not cmds.objExists(plug):
        return connections

    connections["inputs"] = cmds.listConnections(plug, source=True, destination=False, plugs=True, skipConversionNodes=True) or []
    connections["outputs"] = cmds.listConnections(plug, source=False, destination=True, plugs=True, skipConversionNodes=True) or []

    return connections


def get_node_connections(node, attributes=None):

    """
    {attr: {"inputs": [...], "outputs": [...]}} of 'node' for 'attributes' (its user
    defined attributes by default), connected ones only.
    """

    result = {}

    if not node or not cmds.objExists(node):
        return result

    attributes = attributes if attributes is not None else (cmds.listAttr(node, userDefined=True) or [])

    for attr in attributes:

        connections = get_connections(f"{node}.{attr}")

        if connections["inputs"] or connections["outputs"]:
            result[attr] = connections

    return result


# ==========================================================
# HELPERS
# ==========================================================

def get_free_name(node, base):
    """First attribute name free on 'node': 'base', then 'base1', 'base2'..."""

    name = base
    index = 1

    while cmds.attributeQuery(name, node=node, exists=True):
        name = f"{base}{index}"
        index += 1

    return name
