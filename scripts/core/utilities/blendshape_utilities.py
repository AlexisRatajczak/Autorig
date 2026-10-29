# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# QUERY
#   get_selected_mesh()                                - 1er mesh de la selection Maya
#   get_blendshape_nodes(mesh)                          - noeuds blendShape de l'historique d'un mesh
#   has_blendshape(mesh)                                - True si le mesh a au moins un blendShape
#   list_targets(blendshape_node)                       - alias de toutes les targets d'un blendShape
#   get_weight_index(blendshape_node, alias)            - index weight[i] correspondant a un alias
#   build_target_map(blendshape_nodes=None)             - {target_lower: (node, alias)} sur plusieurs blendShapes
#   get_target_weight(node, attr)                       - valeur actuelle du poids d'une target
#   get_next_weight_index(blendshape_node)              - 1er index de weight libre
#   get_envelope(blendshape_node)                       - poids global (envelope) du blendShape
#
# EDIT
#   set_target_weight(node, attr, value)                - set le poids d'une target
#   set_envelope(blendshape_node, value)                - set le poids global (envelope)
#   create_blendshape(base_mesh, name=None)             - cree un blendShape (sans target) sur un mesh
#   delete_blendshape_node(blendshape_node)             - supprime un noeud blendShape
#   rename_blendshape_node(blendshape_node, new_name)   - renomme un noeud blendShape
#   delete_target(blendshape_node, target_name)         - supprime une target d'un blendShape
#
# BCS
#   get_bcs_node(mesh=None)                             - 1er node 'bcs' de l'historique (selection par defaut)
#   connect_blendshape(bcs_node, ctrl_suffix, attr_to_channel) - connecte les weights aux canaux des ctrls

# ====================================================================================================================
# ====================================================================================================================

import maya.cmds as cmds
import re


from .. import log

# --------------------------------------------------
# QUERY
# --------------------------------------------------

def get_selected_mesh():
    """Retourne le premier transform de mesh trouve dans la selection Maya, ou None."""

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
    """
    Retourne les noeuds blendShape trouves dans l'historique de 'mesh'.

    mesh : transform (ou shape) dont on veut l'historique.
    """

    if not mesh or not cmds.objExists(mesh):
        return []

    history = cmds.listHistory(mesh) or []

    return cmds.ls(history, type="blendShape") or []


def has_blendshape(mesh):
    """
    True si 'mesh' porte au moins un blendShape dans son historique.

    mesh : transform (ou shape) a verifier.
    """

    return bool(get_blendshape_nodes(mesh))


def list_targets(blendshape_node):
    """
    Retourne les noms de targets (alias des attributs weight) d'un blendShape.

    blendshape_node : noeud blendShape a interroger.
    """

    if not blendshape_node or not cmds.objExists(blendshape_node):
        return []

    aliases = cmds.aliasAttr(blendshape_node, query=True) or []

    # cmds.aliasAttr retourne [alias1, plug1, alias2, plug2, ...]
    return aliases[::2]


def get_weight_index(blendshape_node, alias):
    """
    Retourne l'index numerique du plug 'weight[i]' correspondant a un alias.

    blendshape_node : noeud blendShape a interroger.
    alias           : nom de la target (alias de weight[i]).
    """

    aliases = cmds.aliasAttr(blendshape_node, query=True) or []

    for name, plug in zip(aliases[::2], aliases[1::2]):

        if name == alias:

            try:
                return int(plug.split("[")[-1].rstrip("]"))
            except (ValueError, IndexError):
                return None

    return None


def build_target_map(blendshape_nodes=None):
    """
    Associe chaque target (nom en minuscules) a son (node, attr), pour les
    blendShape donnes (tous ceux de la scene si 'blendshape_nodes' est None).

    blendshape_nodes : liste de noeuds blendShape a inclure, ou None pour
                        tous ceux de la scene.
    """

    nodes = blendshape_nodes if blendshape_nodes is not None else (cmds.ls(type="blendShape") or [])

    target_map = {}

    for node in nodes:
        for target in list_targets(node):
            target_map[target.lower()] = (node, target)

    return target_map


def get_target_weight(node, attr):
    """
    Retourne la valeur du poids d'une target, ou None si le plug n'existe pas.

    node : noeud blendShape.
    attr : nom de l'attribut de poids (alias de la target, ou "weight[i]").
    """

    plug = f"{node}.{attr}"

    if not cmds.objExists(plug):
        log.warning(f"Target '{plug}' does not exist.")
        return None

    return cmds.getAttr(plug)


def get_next_weight_index(blendshape_node):
    """
    Retourne le premier index de 'weight' libre sur 'blendshape_node'.

    blendshape_node : noeud blendShape a interroger.
    """

    existing = cmds.getAttr(f"{blendshape_node}.weight", multiIndices=True) or []

    return (max(existing) + 1) if existing else 0


def get_envelope(blendshape_node):
    """
    Retourne l'envelope (poids global) d'un blendShape node, ou None s'il n'existe pas.

    blendshape_node : noeud blendShape a interroger.
    """

    if not blendshape_node or not cmds.objExists(blendshape_node):
        return None

    return cmds.getAttr(f"{blendshape_node}.envelope")


# --------------------------------------------------
# EDIT
# --------------------------------------------------

def set_target_weight(node, attr, value):
    """
    Set la valeur du poids d'une target. Retourne False si le plug n'existe pas.

    node  : noeud blendShape.
    attr  : nom de l'attribut de poids (alias de la target, ou "weight[i]").
    value : nouvelle valeur du poids.
    """

    plug = f"{node}.{attr}"

    if not cmds.objExists(plug):
        log.warning(f"Target '{plug}' does not exist.")
        return False

    cmds.setAttr(plug, value)

    return True


def set_envelope(blendshape_node, value):
    """
    Set l'envelope (poids global) d'un blendShape node. Retourne False s'il n'existe pas.

    blendshape_node : noeud blendShape a modifier.
    value           : nouvelle valeur de l'envelope.
    """

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.warning(f"'{blendshape_node}' does not exist.")
        return False

    cmds.setAttr(f"{blendshape_node}.envelope", value)

    return True


def create_blendshape(base_mesh, name=None):
    """
    Cree un blendShape (sans target) sur 'base_mesh'.

    base_mesh : mesh sur lequel creer le blendShape.
    name      : nom du noeud blendShape, ou None pour laisser Maya le generer.
    """

    if not base_mesh or not cmds.objExists(base_mesh):
        log.error(f"Cannot create blendShape : '{base_mesh}' does not exist.")
        return None

    kwargs = {"name": name} if name else {}

    node = cmds.blendShape(base_mesh, **kwargs)[0]

    log.success(f"BlendShape created : {node}")

    return node


def delete_blendshape_node(blendshape_node):
    """
    Supprime un noeud blendShape (deformer) de la scene.

    blendshape_node : noeud blendShape a supprimer.
    """

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.warning(f"'{blendshape_node}' does not exist.")
        return False

    cmds.delete(blendshape_node)

    log.success(f"BlendShape deleted : {blendshape_node}")

    return True


def rename_blendshape_node(blendshape_node, new_name):
    """
    Renomme un noeud blendShape. Retourne le nouveau nom, ou None si echec.

    blendshape_node : noeud blendShape a renommer.
    new_name        : nouveau nom.
    """

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
    """
    Supprime une target d'un blendShape, via le flag -remove de la commande
    blendShape. Non verifie en live : a tester.

    blendshape_node : noeud blendShape.
    target_name     : alias de la target a supprimer.
    """

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


# -------------------------------------------------------------------------------------------------
# ------------------------------------------ GET BCS NODE -----------------------------------------
# -------------------------------------------------------------------------------------------------
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


# -------------------------------------------------------------------------------------------------
# --------------------------------------- CONNECT BLENDSHAPE --------------------------------------
# -------------------------------------------------------------------------------------------------
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

