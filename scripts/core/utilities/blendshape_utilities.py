# ====================================================================================================================
# BLENDSHAPE UTILITIES
# ====================================================================================================================
#
#   QUERY
#       get_selected_mesh()                             - first mesh of the Maya selection
#       get_blendshape_nodes(mesh)                      - blendShape nodes in a mesh history
#       has_blendshape(mesh)                            - True if the mesh has a blendShape
#       list_targets(blendshape_node)                   - target aliases of a blendShape
#       get_weight_index(blendshape_node, alias)        - weight[i] index of an alias
#       build_target_map(blendshape_nodes)              - {target_lower: (node, alias)} over several blendShapes
#       get_target_weight(node, attr)                   - current weight of a target
#       get_next_weight_index(blendshape_node)          - first free weight index
#       get_envelope(blendshape_node)                   - global weight (envelope)
#   EDIT
#       set_target_weight(node, attr, value)            - set a target weight
#       set_envelope(blendshape_node, value)            - set the envelope
#       create_blendshape(base_mesh, name)              - blendShape (no target) on a mesh
#       delete_blendshape_node(blendshape_node)         - delete a blendShape node
#       rename_blendshape_node(blendshape_node, new_name) - rename a blendShape node
#       delete_target(blendshape_node, target_name)     - delete a target
#   BCS
#       get_bcs_node(mesh)                              - first 'bcs' node in the history (selection by default)
#       connect_blendshape(bcs_node, ctrl_suffix, attr_to_channel) - connect the weights to the ctrl channels
#
# ====================================================================================================================

import maya.cmds as cmds
import re


from .. import log

# --------------------------------------------------
# QUERY
# --------------------------------------------------

def get_selected_mesh():
    """First mesh transform of the Maya selection, or None."""

    for node in cmds.ls(selection=True, long=True) or []:

        if cmds.nodeType(node) == "mesh":

            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []

            if parents:
                return parents[0]

            continue

        shapes = cmds.listRelatives(node, shapes=True, fullPath=True, type="mesh") or []

        if shapes:
            return node

    return None


def get_blendshape_nodes(mesh):
    """blendShape nodes in the history of 'mesh' (transform or shape)."""

    if not mesh or not cmds.objExists(mesh):
        return []

    history = cmds.listHistory(mesh) or []

    return cmds.ls(history, type="blendShape") or []


def has_blendshape(mesh):
    """True if 'mesh' has at least one blendShape in its history."""

    return bool(get_blendshape_nodes(mesh))


def list_targets(blendshape_node):
    """Target names (weight aliases) of a blendShape."""

    if not blendshape_node or not cmds.objExists(blendshape_node):
        return []

    aliases = cmds.aliasAttr(blendshape_node, query=True) or []

    # cmds.aliasAttr returns [alias1, plug1, alias2, plug2, ...]
    return aliases[::2]


def get_weight_index(blendshape_node, alias):
    """Index i of the 'weight[i]' plug of a target alias, or None."""

    aliases = cmds.aliasAttr(blendshape_node, query=True) or []

    for name, plug in zip(aliases[::2], aliases[1::2]):

        if name == alias:

            try:
                return int(plug.split("[")[-1].rstrip("]"))
            except (ValueError, IndexError):
                return None

    return None


def build_target_map(blendshape_nodes=None):
    """{target_lower: (node, alias)} for 'blendshape_nodes' (every blendShape of the scene if None)."""

    nodes = blendshape_nodes if blendshape_nodes is not None else (cmds.ls(type="blendShape") or [])

    target_map = {}

    for node in nodes:
        for target in list_targets(node):
            target_map[target.lower()] = (node, target)

    return target_map


def get_target_weight(node, attr):
    """Weight of a target ('attr': alias or "weight[i]"), or None if the plug is missing."""

    plug = f"{node}.{attr}"

    if not cmds.objExists(plug):
        log.warning(f"Target '{plug}' does not exist.")
        return None

    return cmds.getAttr(plug)


def get_next_weight_index(blendshape_node):
    """First free 'weight' index of 'blendshape_node'."""

    existing = cmds.getAttr(f"{blendshape_node}.weight", multiIndices=True) or []

    return (max(existing) + 1) if existing else 0


def get_envelope(blendshape_node):
    """Envelope (global weight) of a blendShape, or None if it does not exist."""

    if not blendshape_node or not cmds.objExists(blendshape_node):
        return None

    return cmds.getAttr(f"{blendshape_node}.envelope")


# --------------------------------------------------
# EDIT
# --------------------------------------------------

def set_target_weight(node, attr, value):
    """Set a target weight ('attr': alias or "weight[i]"). False if the plug is missing."""

    plug = f"{node}.{attr}"

    if not cmds.objExists(plug):
        log.warning(f"Target '{plug}' does not exist.")
        return False

    cmds.setAttr(plug, value)

    return True


def set_envelope(blendshape_node, value):
    """Set the envelope (global weight) of a blendShape. False if it does not exist."""

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.warning(f"'{blendshape_node}' does not exist.")
        return False

    cmds.setAttr(f"{blendshape_node}.envelope", value)

    return True


def create_blendshape(base_mesh, name=None):
    """blendShape without target on 'base_mesh' ('name' or Maya's default)."""

    if not base_mesh or not cmds.objExists(base_mesh):
        log.error(f"Cannot create blendShape : '{base_mesh}' does not exist.")
        return None

    kwargs = {"name": name} if name else {}

    node = cmds.blendShape(base_mesh, **kwargs)[0]

    log.success(f"BlendShape created : {node}")

    return node


def delete_blendshape_node(blendshape_node):
    """Delete a blendShape deformer from the scene."""

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.warning(f"'{blendshape_node}' does not exist.")
        return False

    cmds.delete(blendshape_node)

    log.success(f"BlendShape deleted : {blendshape_node}")

    return True


def rename_blendshape_node(blendshape_node, new_name):
    """Rename a blendShape node. Returns the new name, or None on failure."""

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.error(f"Cannot rename : '{blendshape_node}' does not exist.")
        return None

    if cmds.objExists(new_name):
        log.error(f"Cannot rename : '{new_name}' already exists.")
        return None

    renamed = cmds.rename(blendshape_node, new_name)

    log.success(f"BlendShape renamed : {blendshape_node} -> {renamed}")

    return renamed


def delete_target(blendshape_node, target_name):
    """Delete a target through blendShape -remove (not tested live)."""

    weight_index = get_weight_index(blendshape_node, target_name)

    if weight_index is None:
        log.warning(f"Target '{target_name}' not found on '{blendshape_node}'.")
        return False

    base_meshes = cmds.blendShape(blendshape_node, query=True, geometry=True) or []

    if not base_meshes:
        log.error(f"Could not resolve the base geometry of '{blendshape_node}'.")
        return False

    try:
        cmds.blendShape(
            blendshape_node,
            edit=True,
            remove=True,
            target=(base_meshes[0], weight_index, target_name, 1.0),
        )
    except Exception as error:
        log.error(f"Could not delete target '{target_name}' : {error}")
        return False

    log.success(f"Target '{target_name}' deleted from '{blendshape_node}'.")

    return True


# --------------------------------------------------
# BCS
# --------------------------------------------------

def get_bcs_node(mesh=None):

    if mesh is None:
        selection = cmds.ls(sl=True, long=True)
        if not selection:
            return None
        mesh = selection[0]

    history = cmds.listHistory(mesh) or []

    for node in history:
        if "bcs" in node.lower():
            return node

    return None


def connect_blendshape(bcs_node,
                 ctrl_suffix = '_shape_ctrl',
                 attr_to_channel={
                    "InOut": "translateX",
                    "LeftRight": "translateX",
                    "UpDn": "translateY",
                    "Open": "translateY",
                    "FwBw": "translateZ"
                    }):


    indices = cmds.getAttr(f"{bcs_node}.weight", multiIndices=True) or []

    for i in indices:

        attr_name = cmds.aliasAttr(f"{bcs_node}.weight[{i}]", q=True)

        if not attr_name:
            continue

        # -----------------------------------
        for key, channel in attr_to_channel.items():

            if key not in attr_name:
                continue

            match = re.match(rf"(.+?)_{key}([LR]?)$", attr_name)

            if not match:
                continue

            ctrl_name = match.group(1)

            if match.group(2) in ('L', 'R'):
                side = match.group(2)
            else:
                side = 'C'

            ctrl = f"{side}_{ctrl_name[0].lower() + ctrl_name[1:] + ctrl_suffix}"
            src_attr = f"{ctrl}.{channel}"
            dst_attr = f"{bcs_node}.weight[{i}]"
            # -----------------------------------
            if cmds.objExists(src_attr):
                try:
                    if not cmds.isConnected(src_attr, dst_attr):
                        cmds.connectAttr(src_attr, dst_attr, force=True)
                    print(f"CONNECTED : {src_attr} -> {dst_attr}")
                except Exception as e:
                    cmds.warning(str(e))

            else:
                cmds.warning(f"CTRL INTROUVABLE : {src_attr}")

