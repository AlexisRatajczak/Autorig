# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# API - GEO
# ==========================================================
#
# Façade sur geo_utilities et naming_utilities (alias directs). Les noms
# trop génériques sont préfixés (ex: 'meshes' -> list_meshes, 'ngons' ->
# find_ngons, 'is_valid' -> is_valid_name).
#
#   from api import geo
#
#   for mesh in geo.list_meshes(geo.SELECTION, settings):
#       print(mesh, geo.find_ngons(mesh))
#
# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# SCENE    : SCENE, SELECTION, check_single_vertex_selection, check_face_selection, dag_path,
#            leaf_name, short_name, node_of, group_by_node, list_transforms, list_shapes_of,
#            list_groups, list_shape_transforms, list_meshes, select_items, rename_many,
#            undo_chunk, safe_call, remove_poly_tweak
# CHECKS   : find_ngons, find_non_manifold, find_lamina_faces, find_zero_area_faces,
#            find_zero_length_edges, has_history, is_unfrozen, has_locked_normals
# FIXES    : triangulate_faces, delete_components, collapse_edges, delete_history,
#            freeze_transforms, unlock_normals
# UV       : uv_sets, find_missing_uvs, find_uvs_out_of_range, find_uvs_crossing_borders,
#            find_flipped_uvs, find_overlapping_uvs, delete_extra_uv_sets, rename_first_uv_set
# MATERIAL : shading_groups, has_per_face_assignment, breaks_material_policy, assign_shading_group
# COLOR    : color_sets, has_display_color, has_outliner_color, delete_color_sets,
#            reset_display_color, reset_outliner_color
# NAMING   : is_valid_name, suggest_name, expected_shape_name

# ====================================================================================================================
# ====================================================================================================================

from core.utilities import geo_utilities
from core.utilities import naming_utilities

from importlib import reload

reload(geo_utilities)
reload(naming_utilities)


__all__ = [
    # scene
    "SCENE", "SELECTION", "check_single_vertex_selection", "check_face_selection", "dag_path",
    "leaf_name", "short_name", "node_of", "group_by_node", "list_transforms", "list_shapes_of",
    "list_groups", "list_shape_transforms", "list_meshes", "select_items", "rename_many",
    "undo_chunk", "safe_call", "remove_poly_tweak",
    # checks
    "find_ngons", "find_non_manifold", "find_lamina_faces", "find_zero_area_faces",
    "find_zero_length_edges", "has_history", "is_unfrozen", "has_locked_normals",
    # fixes
    "triangulate_faces", "delete_components", "collapse_edges", "delete_history",
    "freeze_transforms", "unlock_normals",
    # uv
    "uv_sets", "find_missing_uvs", "find_uvs_out_of_range", "find_uvs_crossing_borders",
    "find_flipped_uvs", "find_overlapping_uvs", "delete_extra_uv_sets", "rename_first_uv_set",
    # material
    "shading_groups", "has_per_face_assignment", "breaks_material_policy", "assign_shading_group",
    # color
    "color_sets", "has_display_color", "has_outliner_color", "delete_color_sets",
    "reset_display_color", "reset_outliner_color",
    # naming
    "is_valid_name", "suggest_name", "expected_shape_name",
]


# --------------------------------------------------
# SCENE
# --------------------------------------------------

SCENE = geo_utilities.SCENE
SELECTION = geo_utilities.SELECTION

check_single_vertex_selection = geo_utilities.check_single_vertex_selection
check_face_selection = geo_utilities.check_face_selection
dag_path = geo_utilities.dag_path
leaf_name = geo_utilities.leaf
short_name = geo_utilities.short
node_of = geo_utilities.node_of
group_by_node = geo_utilities.group_by_node
list_transforms = geo_utilities.transforms
list_shapes_of = geo_utilities.shapes_of
list_groups = geo_utilities.groups
list_shape_transforms = geo_utilities.shape_transforms
list_meshes = geo_utilities.meshes
select_items = geo_utilities.select_items
rename_many = geo_utilities.rename_many
undo_chunk = geo_utilities.undo_chunk
safe_call = geo_utilities.safe
remove_poly_tweak = geo_utilities.remove_polyTweak

# --------------------------------------------------
# MESH - CHECKS
# --------------------------------------------------

find_ngons = geo_utilities.ngons
find_non_manifold = geo_utilities.non_manifold
find_lamina_faces = geo_utilities.lamina_faces
find_zero_area_faces = geo_utilities.zero_area_faces
find_zero_length_edges = geo_utilities.zero_length_edges
has_history = geo_utilities.has_history
is_unfrozen = geo_utilities.is_unfrozen
has_locked_normals = geo_utilities.has_locked_normals

# --------------------------------------------------
# MESH - FIXES
# --------------------------------------------------

triangulate_faces = geo_utilities.triangulate_faces
delete_components = geo_utilities.delete_components
collapse_edges = geo_utilities.collapse_edges
delete_history = geo_utilities.delete_history
freeze_transforms = geo_utilities.freeze_transforms
unlock_normals = geo_utilities.unlock_normals

# --------------------------------------------------
# UV
# --------------------------------------------------

uv_sets = geo_utilities.uv_sets
find_missing_uvs = geo_utilities.missing_uvs
find_uvs_out_of_range = geo_utilities.out_of_range
find_uvs_crossing_borders = geo_utilities.crossing_borders
find_flipped_uvs = geo_utilities.flipped
find_overlapping_uvs = geo_utilities.overlapping
delete_extra_uv_sets = geo_utilities.delete_extra_sets
rename_first_uv_set = geo_utilities.rename_first_set

# --------------------------------------------------
# MATERIAL
# --------------------------------------------------

shading_groups = geo_utilities.shading_groups
has_per_face_assignment = geo_utilities.has_per_face_assignment
breaks_material_policy = geo_utilities.breaks_policy
assign_shading_group = geo_utilities.assign

# --------------------------------------------------
# COLOR
# --------------------------------------------------

color_sets = geo_utilities.color_sets
has_display_color = geo_utilities.has_display_color
has_outliner_color = geo_utilities.has_outliner_color
delete_color_sets = geo_utilities.delete_color_sets
reset_display_color = geo_utilities.reset_display_color
reset_outliner_color = geo_utilities.reset_outliner_color

# --------------------------------------------------
# NAMING
# --------------------------------------------------

is_valid_name = naming_utilities.is_valid
suggest_name = naming_utilities.suggest
expected_shape_name = naming_utilities.expected_shape_name
