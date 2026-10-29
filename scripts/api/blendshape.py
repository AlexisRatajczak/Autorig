# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# API - BLENDSHAPE
# ==========================================================
#
# Façade sur blendshape_utilities (alias directs, noms explicites).
#
#   from api import blendshape
#
#   node = blendshape.create_blendshape("C_head_geo", name="C_head_bcs")
#   blendshape.set_target_weight(node, "jawOpen", 1.0)
#
# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# QUERY
#   get_selected_mesh, get_blendshape_nodes, has_blendshape, list_blendshape_targets,
#   get_target_weight_index, build_target_map, get_target_weight, get_next_weight_index,
#   get_blendshape_envelope, get_bcs_node
#
# EDIT
#   set_target_weight, set_blendshape_envelope, create_blendshape, delete_blendshape,
#   rename_blendshape, delete_blendshape_target, connect_blendshape
#
# BATCH (tools_facialRig)
#   connect_blendshapes(meshes)   - connect_blendshape sur le noeud 'bcs' de chaque mesh (sélection par défaut)

# ====================================================================================================================
# ====================================================================================================================

import maya.cmds as cmds

from core.utilities import blendshape_utilities

from importlib import reload

reload(blendshape_utilities)


__all__ = [
    # query
    "get_selected_mesh", "get_blendshape_nodes", "has_blendshape", "list_blendshape_targets",
    "get_target_weight_index", "build_target_map", "get_target_weight", "get_next_weight_index",
    "get_blendshape_envelope", "get_bcs_node",
    # edit
    "set_target_weight", "set_blendshape_envelope", "create_blendshape", "delete_blendshape",
    "rename_blendshape", "delete_blendshape_target", "connect_blendshape",
    # batch
    "connect_blendshapes",
]


# --------------------------------------------------
# QUERY
# --------------------------------------------------

get_selected_mesh = blendshape_utilities.get_selected_mesh
get_blendshape_nodes = blendshape_utilities.get_blendshape_nodes
has_blendshape = blendshape_utilities.has_blendshape
list_blendshape_targets = blendshape_utilities.list_targets
get_target_weight_index = blendshape_utilities.get_weight_index
build_target_map = blendshape_utilities.build_target_map
get_target_weight = blendshape_utilities.get_target_weight
get_next_weight_index = blendshape_utilities.get_next_weight_index
get_blendshape_envelope = blendshape_utilities.get_envelope
get_bcs_node = blendshape_utilities.get_bcs_node

# --------------------------------------------------
# EDIT
# --------------------------------------------------

set_target_weight = blendshape_utilities.set_target_weight
set_blendshape_envelope = blendshape_utilities.set_envelope
create_blendshape = blendshape_utilities.create_blendshape
delete_blendshape = blendshape_utilities.delete_blendshape_node
rename_blendshape = blendshape_utilities.rename_blendshape_node
delete_blendshape_target = blendshape_utilities.delete_target
connect_blendshape = blendshape_utilities.connect_blendshape

# --------------------------------------------------
# BATCH
# --------------------------------------------------

def connect_blendshapes(meshes=None):

    """
    Pour chaque mesh ('meshes', sinon la sélection), connecte son noeud
    blendShape 'bcs' (get_bcs_node) aux ctrls correspondants
    (connect_blendshape). Retourne les noeuds 'bcs' traités.
    """

    if meshes is None:
        meshes = cmds.ls(selection=True) or []
    elif isinstance(meshes, str):
        meshes = [meshes]

    nodes = []

    for mesh in meshes:

        bcs_node = blendshape_utilities.get_bcs_node(mesh)

        if bcs_node:
            blendshape_utilities.connect_blendshape(bcs_node)
            nodes.append(bcs_node)

    return nodes
