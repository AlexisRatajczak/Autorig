# ====================================================================================================================
# GEO UTILITIES
# ====================================================================================================================
#
# SELECTION CHECKS
#   check_single_vertex_selection(obj)          - error unless 'obj' is exactly 1 vertex
#   check_face_selection(obj)                   - error unless 'obj' holds only faces
#
# SCENE
#   dag_path(node)                              - MDagPath of the node
#   leaf(node)                                  - '|a|ns:b' -> 'b'
#   short(node)                                 - '|a|ns:b' -> 'ns:b'
#   node_of(item)                               - '|a|bShape.f[3]' -> '|a|bShape'
#   group_by_node(items)                        - group components by owner node
#   _filtered(nodes, settings)                  - filter nodes with settings['general']
#   transforms(scope, settings)                 - transforms (scene or selection), filtered
#   shapes_of(transform, shape_type)            - shapes of a transform (optional type)
#   groups(scope, settings)                     - transforms without shape
#   shape_transforms(scope, settings, shape_type) - transforms with a shape of that type
#   meshes(scope, settings)                     - non intermediate mesh shapes
#   select_items(items)                         - select the existing nodes / components
#   rename_many(nodes, new_leaf_for)            - safely rename several nodes (through uuids)
#   undo_chunk(name) [contextmanager]           - group commands into one undo
#   safe(function, *args, **kwargs)             - run a Maya command, errors become warnings
#
# HISTORY
#   remove_polyTweak(obj)                       - delete the polyTweak nodes in the history of 'obj'
#
# MESH - CHECKS
#   ngons(mesh, max_sides)                      - faces with more than 'max_sides' sides
#   non_manifold(mesh)                          - non-manifold edges / vertices
#   lamina_faces(mesh)                          - lamina faces
#   zero_area_faces(mesh, tolerance)            - near zero area faces
#   zero_length_edges(mesh, tolerance)          - near zero length edges
#   has_history(mesh, ignore_types)             - True if the mesh has history (ignored types aside)
#   is_unfrozen(transform, tolerance)           - True if translate / rotate / scale are not identity
#   has_locked_normals(mesh)                    - True if a normal is locked
#
# MESH - FIXES
#   triangulate_faces(faces)                    - triangulate the faces
#   delete_components(components)               - delete the components
#   collapse_edges(edges)                       - collapse the edges
#   delete_history(meshes)                      - delete construction history
#   freeze_transforms(transforms)               - freeze translate/rotate/scale (makeIdentity)
#   unlock_normals(meshes)                      - unlock every normal
#
# UV - CHECKS
#   uv_sets(mesh)                               - UV sets of the mesh
#   missing_uvs(mesh)                           - mesh (or faces) without UVs
#   out_of_range(mesh, allow_udim, udim_max_u)  - UVs out of the valid range (negative, or out of 0-1 / UDIM)
#   crossing_borders(mesh)                      - faces whose UVs cross several tiles
#   flipped(mesh)                               - faces with a reversed UV winding
#   overlapping(mesh)                           - faces with overlapping UVs
#   _face_uv_issues(mesh, test)                 - faces whose UVs match test(us, vs)
#   _crosses_tile(us, vs)                       - True if a face's UVs span several tiles
#   _is_flipped(us, vs)                         - True if a face's UV winding is reversed
#
# UV - FIXES
#   delete_extra_sets(meshes, keep)             - delete the extra UV sets
#   rename_first_set(meshes, name)              - rename the first UV set
#
# MATERIAL
#   shading_groups(mesh)                        - shadingEngines connected to the mesh
#   has_per_face_assignment(mesh)               - True if materials are assigned per face
#   breaks_policy(mesh, default_group, policy)  - True if the assignment breaks the policy
#   assign(meshes, shading_group)               - assign a shadingEngine to the meshes
#
# COLOR
#   color_sets(mesh)                            - color sets of the mesh
#   has_display_color(node)                     - True if a custom display color is on
#   has_outliner_color(node)                    - True if a custom outliner color is on
#   delete_color_sets(meshes)                   - delete every color set
#   reset_display_color(nodes)                  - turn off the custom display color
#   reset_outliner_color(nodes)                 - turn off the custom outliner color
#
# ====================================================================================================================

import math
from contextlib import contextmanager

import maya.api.OpenMaya as om
import maya.cmds as cmds

SCENE = "scene"
SELECTION = "selection"

_UV_EPSILON = 1e-5

# --------------------------------------------------
# CHECK SINGLE VERTEX SELECTION
# --------------------------------------------------

def check_single_vertex_selection(obj):
    """cmds.error unless 'obj' (selected components) is exactly one vertex. Returns True."""

    if not obj:
        cmds.error("Aucun vertex sélectionné.")

    if len(obj) != 1:
        cmds.error("Sélectionne un seul vertex.")

    if ".vtx[" not in obj[0]:
        cmds.error("La sélection doit être un vertex.")

    return True

# --------------------------------------------------
# CHECK FACE SELECTION
# --------------------------------------------------

def check_face_selection(obj):
    """cmds.error unless 'obj' (selected components) holds only faces. Returns True."""

    if not obj:
        cmds.error("Aucune sélection.")

    for sel in obj:
        if ".f[" not in sel:
            cmds.error("La sélection doit contenir uniquement des faces.")

    return True

# --------------------------------------------------
# DAG PATH
# --------------------------------------------------

def dag_path(node):
    """MDagPath of 'node' (unique name) for the API iterators / function sets."""

    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDagPath(0)

# --------------------------------------------------
# NODE NAMES
# --------------------------------------------------

def leaf(node):
    """Short name without namespace : '|a|ns:b' -> 'b'."""
    return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


def short(node):
    """Short name with namespace : '|a|ns:b' -> 'ns:b'."""
    return node.rsplit("|", 1)[-1]


def node_of(item):
    """Owner node of a component : '|a|bShape.f[3]' -> '|a|bShape'."""
    return item.split(".", 1)[0]


def group_by_node(items):
    """{owner node: [components]} (see node_of)."""

    grouped = {}

    for item in items:
        grouped.setdefault(node_of(item), []).append(item)

    return grouped

# --------------------------------------------------
# SCENE QUERIES
# --------------------------------------------------

def _filtered(nodes, settings):
    """Filter 'nodes' (long names) with settings["general"] (ignore_nodes, ignore_referenced)."""

    general = settings.get("general", {})
    ignore = set(general.get("ignore_nodes", []))
    skip_referenced = general.get("ignore_referenced", True)

    result = []

    for node in nodes:

        if short(node) in ignore:
            continue

        if skip_referenced and cmds.referenceQuery(node, isNodeReferenced=True):
            continue

        result.append(node)

    return result


def transforms(scope, settings):
    """
    Plain transforms (no joints, constraints...), filtered by settings.

    scope : SCENE (whole scene) or SELECTION (selection + descendants).
    """

    if scope == SELECTION:

        selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []

        if not selected:
            return []

        roots = set()

        for node in selected:
            if cmds.objectType(node, isAType="shape"):
                roots.update(cmds.listRelatives(node, parent=True, fullPath=True) or [])
            else:
                roots.add(node)

        nodes = set(roots)
        nodes.update(cmds.listRelatives(list(roots), allDescendents=True, fullPath=True) or [])

        if not nodes:
            return []

        nodes = cmds.ls(list(nodes), long=True, exactType="transform") or []

    else:
        nodes = cmds.ls(long=True, exactType="transform") or []

    return _filtered(sorted(set(nodes)), settings)


def shapes_of(transform, shape_type=None):
    """Non intermediate shapes of 'transform', of 'shape_type' (ex: "mesh") or all."""

    kwargs = {"shapes": True, "fullPath": True, "noIntermediate": True}

    if shape_type:
        kwargs["type"] = shape_type

    return cmds.listRelatives(transform, **kwargs) or []


def groups(scope, settings):
    """Transforms without shape (see transforms)."""
    return [t for t in transforms(scope, settings) if not cmds.listRelatives(t, shapes=True)]


def shape_transforms(scope, settings, shape_type):
    """Transforms with a shape of the given type."""
    return [t for t in transforms(scope, settings) if shapes_of(t, shape_type)]


def meshes(scope, settings):
    """Non intermediate mesh shapes of every transform."""

    result = []

    for transform in transforms(scope, settings):
        result.extend(shapes_of(transform, "mesh"))

    return result

# --------------------------------------------------
# SELECTION
# --------------------------------------------------

def select_items(items):
    """Select the nodes / components of 'items' that still exist. Returns how many were selected."""

    existing = [item for item in items if cmds.objExists(item)]

    if not existing:
        cmds.select(clear=True)
        return 0

    components = [item for item in existing if "." in item]

    if components:

        owners = set()

        for node in group_by_node(components):
            if cmds.objectType(node, isAType="shape"):
                owners.update(cmds.listRelatives(node, parent=True, fullPath=True) or [])
            else:
                owners.add(node)

        cmds.select(clear=True)
        cmds.hilite(list(owners), replace=True)

    cmds.select(existing, replace=True)

    return len(existing)

# --------------------------------------------------
# RENAME
# --------------------------------------------------

def rename_many(nodes, new_leaf_for):
    """
    Safely rename 'nodes' (long names), even parents and children together
    (resolved by uuid).

    new_leaf_for : function(long_name) -> new short name, or None to skip.

    Returns the nodes that could not be renamed.
    """

    failed = []
    uuids = [(cmds.ls(node, uuid=True) or [None])[0] for node in nodes]

    for uuid in uuids:

        if not uuid:
            continue

        current = (cmds.ls(uuid, long=True) or [None])[0]

        if not current:
            continue

        new_leaf = new_leaf_for(current)

        if not new_leaf or new_leaf == leaf(current):
            if not new_leaf:
                failed.append(current)
            continue

        name = short(current)
        namespace = name.rsplit(":", 1)[0] + ":" if ":" in name else ""

        try:
            cmds.rename(current, namespace + new_leaf)
        except RuntimeError as exc:
            cmds.warning("{}: impossible de renommer {} ({})".format(__name__, current, exc))
            failed.append(current)

    return failed

# --------------------------------------------------
# UNDO / SAFE CALL
# --------------------------------------------------

@contextmanager
def undo_chunk(name="geo_utilities"):
    """Group every command run in the block into one undo."""

    cmds.undoInfo(openChunk=True, chunkName=name)

    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def safe(function, *args, **kwargs):
    """Run a Maya command (ex: cmds.delete); an error becomes a warning. Returns True on success."""

    try:
        function(*args, **kwargs)
        return True
    except (RuntimeError, ValueError, TypeError) as exc:
        cmds.warning("{}: {}".format(__name__, str(exc).strip()))
        return False

# --------------------------------------------------
# REMOVE POLYTWEAK
# --------------------------------------------------

def remove_polyTweak(obj):
    """Delete the polyTweak nodes in the history of 'obj' (mesh or component)."""

    history = cmds.listHistory(obj) or []
    tweaks = cmds.ls(history, type="polyTweak")

    if tweaks:
        cmds.delete(tweaks)

# --------------------------------------------------
# MESH - TOPOLOGY CHECKS
# --------------------------------------------------

def ngons(mesh, max_sides=4):
    """Faces of 'mesh' with more than 'max_sides' sides."""

    result = []
    iterator = om.MItMeshPolygon(dag_path(mesh))

    while not iterator.isDone():
        if iterator.polygonVertexCount() > max_sides:
            result.append("{}.f[{}]".format(mesh, iterator.index()))
        iterator.next()

    return result


def non_manifold(mesh):
    """Non-manifold edges and vertices of 'mesh'."""

    edges = cmds.polyInfo(mesh, nonManifoldEdges=True) or []
    vertices = cmds.polyInfo(mesh, nonManifoldVertices=True) or []

    return cmds.ls(edges + vertices, long=True) if edges or vertices else []


def lamina_faces(mesh):
    """Lamina faces of 'mesh' (two faces sharing the same edges)."""

    faces = cmds.polyInfo(mesh, laminaFaces=True) or []

    return cmds.ls(faces, long=True) if faces else []


def zero_area_faces(mesh, tolerance=1e-8):
    """Faces of 'mesh' with an area below 'tolerance'."""

    result = []
    iterator = om.MItMeshPolygon(dag_path(mesh))

    while not iterator.isDone():
        if iterator.getArea() < tolerance:
            result.append("{}.f[{}]".format(mesh, iterator.index()))
        iterator.next()

    return result


def zero_length_edges(mesh, tolerance=1e-6):
    """Edges of 'mesh' shorter than 'tolerance'."""

    result = []
    iterator = om.MItMeshEdge(dag_path(mesh))

    while not iterator.isDone():
        if iterator.length() < tolerance:
            result.append("{}.e[{}]".format(mesh, iterator.index()))
        iterator.next()

    return result


def has_history(mesh, ignore_types=()):
    """True if 'mesh' has construction history, 'ignore_types' aside (ex: ("groupId",))."""

    history = cmds.listHistory(mesh, pruneDagObjects=True) or []

    return any(cmds.nodeType(node) not in ignore_types for node in history)


def is_unfrozen(transform, tolerance=1e-5):
    """True if translate / rotate are not zero or scale is not 1 (within 'tolerance')."""

    translate = cmds.getAttr(transform + ".translate")[0]
    rotate = cmds.getAttr(transform + ".rotate")[0]
    scale = cmds.getAttr(transform + ".scale")[0]

    if any(abs(value) > tolerance for value in translate + rotate):
        return True

    return any(abs(value - 1.0) > tolerance for value in scale)


def has_locked_normals(mesh):
    """True if a normal of 'mesh' is locked."""

    fn_mesh = om.MFnMesh(dag_path(mesh))
    _, normal_ids = fn_mesh.getNormalIds()

    return any(fn_mesh.isNormalLocked(index) for index in set(normal_ids))

# --------------------------------------------------
# MESH - TOPOLOGY FIXES
# --------------------------------------------------

def triangulate_faces(faces):
    """Triangulate the faces (grouped by mesh)."""

    for components in group_by_node(faces).values():
        safe(cmds.polyTriangulate, components, constructionHistory=False)


def delete_components(components):
    """Delete the components (grouped by mesh)."""

    for items in group_by_node(components).values():
        safe(cmds.delete, items)


def collapse_edges(edges):
    """Collapse the edges (grouped by mesh)."""

    for items in group_by_node(edges).values():
        safe(cmds.polyCollapseEdge, items, constructionHistory=False)


def delete_history(meshes_):
    """Delete the construction history of each mesh."""

    for mesh in meshes_:
        safe(cmds.delete, mesh, constructionHistory=True)


def freeze_transforms(transforms_):
    """Freeze translate / rotate / scale (makeIdentity) of each transform."""

    for transform in transforms_:
        safe(
            cmds.makeIdentity,
            transform,
            apply=True,
            translate=True,
            rotate=True,
            scale=True,
            normal=False,
            preserveNormals=True,
        )


def unlock_normals(meshes_):
    """Unlock every normal of each mesh."""

    for mesh in meshes_:
        safe(cmds.polyNormalPerVertex, mesh, unFreezeNormal=True)

# --------------------------------------------------
# UV - CHECKS
# --------------------------------------------------

def uv_sets(mesh):
    """UV sets of 'mesh'."""
    return cmds.polyUVSet(mesh, query=True, allUVSets=True) or []


def missing_uvs(mesh):
    """Whole mesh (no UV at all) or the faces without UVs."""

    path = dag_path(mesh)

    if om.MFnMesh(path).numUVs() == 0:
        return [mesh]

    result = []
    iterator = om.MItMeshPolygon(path)

    while not iterator.isDone():
        if not iterator.hasUVs():
            result.append("{}.f[{}]".format(mesh, iterator.index()))
        iterator.next()

    return result


def out_of_range(mesh, allow_udim=True, udim_max_u=10):
    """
    UVs with negative coordinates, or out of 0-1 when UDIMs are not allowed.

    allow_udim : allow UVs past u = 1 (UDIM tiles), up to 'udim_max_u'.
    """

    us, vs = om.MFnMesh(dag_path(mesh)).getUVs()
    max_u = float(udim_max_u) if allow_udim else 1.0

    result = []

    for index, (u, v) in enumerate(zip(us, vs)):
        if u < -_UV_EPSILON or v < -_UV_EPSILON or u > max_u + _UV_EPSILON:
            result.append("{}.map[{}]".format(mesh, index))
        elif not allow_udim and v > 1.0 + _UV_EPSILON:
            result.append("{}.map[{}]".format(mesh, index))

    return result


def _face_uv_issues(mesh, test):
    """Faces of 'mesh' where test(us, vs) is True."""

    result = []
    iterator = om.MItMeshPolygon(dag_path(mesh))

    while not iterator.isDone():
        if iterator.hasUVs():
            us, vs = iterator.getUVs()
            if test(us, vs):
                result.append("{}.f[{}]".format(mesh, iterator.index()))
        iterator.next()

    return result


def _crosses_tile(us, vs):
    """True if a face's UVs (us, vs) span more than one UDIM tile."""
    return (
        math.floor(min(us) + _UV_EPSILON) != math.floor(max(us) - _UV_EPSILON)
        or math.floor(min(vs) + _UV_EPSILON) != math.floor(max(vs) - _UV_EPSILON)
    )


def _is_flipped(us, vs):
    """True if a face's UV winding is reversed (negative signed area)."""

    count = len(us)
    area = 0.0

    for index in range(count):
        following = (index + 1) % count
        area += us[index] * vs[following] - us[following] * vs[index]

    return area < 0.0


def crossing_borders(mesh):
    """Faces of 'mesh' whose UVs span more than one tile."""
    return _face_uv_issues(mesh, _crosses_tile)


def flipped(mesh):
    """Faces of 'mesh' with a reversed UV winding."""
    return _face_uv_issues(mesh, _is_flipped)


def overlapping(mesh):
    """Faces of 'mesh' with overlapping UVs."""

    faces = cmds.polyUVOverlap(mesh + ".f[*]", overlappingComponents=True) or []

    return cmds.ls(faces, long=True) if faces else []

# --------------------------------------------------
# UV - FIXES
# --------------------------------------------------

def delete_extra_sets(meshes_, keep=1):
    """Delete the UV sets past the first 'keep' ones, on each mesh."""

    for mesh in meshes_:
        for name in uv_sets(mesh)[max(keep, 1):]:
            safe(cmds.polyUVSet, mesh, delete=True, uvSet=name)


def rename_first_set(meshes_, name="map1"):
    """Rename the first UV set of each mesh to 'name'."""

    for mesh in meshes_:
        sets = uv_sets(mesh)
        if sets and sets[0] != name:
            safe(cmds.polyUVSet, mesh, rename=True, uvSet=sets[0], newUVSet=name)

# --------------------------------------------------
# MATERIAL
# --------------------------------------------------

def shading_groups(mesh):
    """ShadingEngines connected to 'mesh'."""

    connected = cmds.listConnections(mesh, type="shadingEngine") or []

    return sorted(set(connected))


def has_per_face_assignment(mesh):
    """True if materials are assigned per face instead of per object."""

    connected = cmds.listConnections(
        mesh + ".instObjGroups[0].objectGroups", type="shadingEngine"
    )

    return bool(connected)


def breaks_policy(mesh, default_group, policy):
    """
    True if the shading assignment of 'mesh' breaks 'policy'.

    default_group : reference shadingEngine (ex: initialShadingGroup).
    policy        : "required" (only default_group), "forbidden" (no default_group), "any" (always valid).
    """

    groups_ = shading_groups(mesh)

    if not groups_ or policy == "any":
        return False

    if policy == "required":
        return groups_ != [default_group]

    if policy == "forbidden":
        return default_group in groups_

    return False


def assign(meshes_, shading_group):
    """Assign 'shading_group' to each mesh."""

    for mesh in meshes_:
        safe(cmds.sets, mesh, edit=True, forceElement=shading_group)

# --------------------------------------------------
# COLOR
# --------------------------------------------------

def color_sets(mesh):
    """Color sets of 'mesh'."""
    return cmds.polyColorSet(mesh, query=True, allColorSets=True) or []


def has_display_color(node):
    """True if 'node' has a custom display color (useObjectColor, or an override not from a display layer)."""

    if cmds.getAttr(node + ".useObjectColor"):
        return True

    if not cmds.getAttr(node + ".overrideEnabled"):
        return False

    from_layer = cmds.listConnections(node + ".drawOverride", source=True, destination=False)

    return not from_layer


def has_outliner_color(node):
    """True if 'node' has a custom outliner color (useOutlinerColor)."""
    return bool(cmds.getAttr(node + ".useOutlinerColor"))


def delete_color_sets(meshes_):
    """Delete every color set of each mesh."""

    for mesh in meshes_:
        for name in color_sets(mesh):
            safe(cmds.polyColorSet, mesh, delete=True, colorSet=name)


def reset_display_color(nodes):
    """Turn off the custom display color of each node."""

    for node in nodes:

        safe(cmds.setAttr, node + ".useObjectColor", 0)

        from_layer = cmds.listConnections(node + ".drawOverride", source=True, destination=False)

        if not from_layer:
            safe(cmds.setAttr, node + ".overrideEnabled", 0)


def reset_outliner_color(nodes):
    """Turn off the custom outliner color of each node."""

    for node in nodes:
        safe(cmds.setAttr, node + ".useOutlinerColor", 0)
