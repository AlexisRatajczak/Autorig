# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# SELECTION CHECKS
#   check_single_vertex_selection(obj)          - erreur si 'obj' n'est pas exactement 1 vertex
#   check_face_selection(obj)                   - erreur si 'obj' ne contient pas uniquement des faces
#
# SCENE
#   dag_path(node)                              - MDagPath du node (via MSelectionList)
#   leaf(node)                                  - '|a|ns:b' -> 'b'
#   short(node)                                 - '|a|ns:b' -> 'ns:b'
#   node_of(item)                               - '|a|bShape.f[3]' -> '|a|bShape'
#   group_by_node(items)                        - regroupe des composants par node proprietaire
#   _filtered(nodes, settings)                  - filtre des nodes selon settings['general']
#   transforms(scope, settings)                 - transforms (scene ou selection), filtres par settings
#   shapes_of(transform, shape_type)            - shapes d'un transform (type optionnel)
#   groups(scope, settings)                     - transforms sans aucune shape
#   shape_transforms(scope, settings, shape_type) - transforms ayant au moins une shape du type donne
#   meshes(scope, settings)                     - shapes mesh non-intermediaires
#   select_items(items)                         - selectionne nodes/composants existants
#   rename_many(nodes, new_leaf_for)            - renomme plusieurs nodes en toute securite (via uuid)
#   undo_chunk(name) [contextmanager]           - regroupe des commandes dans un seul undo
#   safe(function, *args, **kwargs)             - execute une commande Maya, transforme une erreur en warning
#
# HISTORY
#   remove_polyTweak(obj)                       - supprime les noeuds polyTweak de l'historique de 'obj'
#
# MESH - CHECKS
#   ngons(mesh, max_sides)                      - faces avec plus de 'max_sides' cotes
#   non_manifold(mesh)                          - aretes/vertices non-manifold
#   lamina_faces(mesh)                           - faces lamina
#   zero_area_faces(mesh, tolerance)            - faces d'aire quasi nulle
#   zero_length_edges(mesh, tolerance)          - aretes de longueur quasi nulle
#   has_history(mesh, ignore_types)             - True si le mesh a de l'historique (hors types ignores)
#   is_unfrozen(transform, tolerance)           - True si translate/rotate/scale ne sont pas a l'identite
#   has_locked_normals(mesh)                    - True si au moins une normale est verrouillee
#
# MESH - FIXES
#   triangulate_faces(faces)                    - triangule les faces donnees
#   delete_components(components)               - supprime les composants donnes
#   collapse_edges(edges)                       - collapse les aretes donnees
#   delete_history(meshes)                      - supprime l'historique de construction
#   freeze_transforms(transforms)               - freeze translate/rotate/scale (makeIdentity)
#   unlock_normals(meshes)                      - deverrouille toutes les normales
#
# UV - CHECKS
#   uv_sets(mesh)                               - liste des UV sets du mesh
#   missing_uvs(mesh)                           - mesh (ou faces) sans UVs
#   out_of_range(mesh, allow_udim, udim_max_u)  - UVs hors zone valide (negatifs ou hors 0-1/UDIM)
#   crossing_borders(mesh)                      - faces dont les UVs traversent plusieurs tiles
#   flipped(mesh)                               - faces dont le winding UV est inverse
#   overlapping(mesh)                           - faces dont les UVs se superposent
#   _face_uv_issues(mesh, test)                 - faces dont les UVs verifient test(us, vs)
#   _crosses_tile(us, vs)                       - True si les UVs d'une face couvrent plusieurs tiles
#   _is_flipped(us, vs)                         - True si le winding UV d'une face est inverse
#
# UV - FIXES
#   delete_extra_sets(meshes, keep)             - supprime les UV sets en trop
#   rename_first_set(meshes, name)              - renomme le premier UV set
#
# MATERIAL
#   shading_groups(mesh)                        - shadingEngine(s) connectes au mesh
#   has_per_face_assignment(mesh)               - True si des matieres sont assignees par face
#   breaks_policy(mesh, default_group, policy)  - True si l'assignation enfreint la policy donnee
#   assign(meshes, shading_group)               - assigne un shadingEngine aux meshes
#
# COLOR
#   color_sets(mesh)                            - liste des color sets du mesh
#   has_display_color(node)                     - True si une couleur d'affichage custom est active
#   has_outliner_color(node)                    - True si une couleur d'outliner custom est active
#   delete_color_sets(meshes)                   - supprime tous les color sets
#   reset_display_color(nodes)                  - desactive la couleur d'affichage custom
#   reset_outliner_color(nodes)                 - desactive la couleur d'outliner custom

# ====================================================================================================================
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
    """
    Erreur (cmds.error) si 'obj' n'est pas exactement un vertex. Retourne True sinon.

    obj : liste de composants selectionnes (ex. cmds.ls(selection=True)).
    """

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
    """
    Erreur (cmds.error) si 'obj' ne contient pas uniquement des faces. Retourne True sinon.

    obj : liste de composants selectionnes (ex. cmds.ls(selection=True)).
    """

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
    """
    MDagPath de 'node', pour les iterateurs/fonctions de l'API (MItMeshPolygon, MFnMesh, ...).

    node : nom du node (long ou court, doit etre unique/resoluble).
    """

    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDagPath(0)

# --------------------------------------------------
# NODE NAMES
# --------------------------------------------------

def leaf(node):
    """Nom court sans namespace : '|a|ns:b' -> 'b'."""
    return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


def short(node):
    """Nom court avec namespace : '|a|ns:b' -> 'ns:b'."""
    return node.rsplit("|", 1)[-1]


def node_of(item):
    """Node proprietaire d'un composant : '|a|bShape.f[3]' -> '|a|bShape'."""
    return item.split(".", 1)[0]


def group_by_node(items):
    """
    Regroupe une liste de composants par node proprietaire (voir node_of).

    items : liste de composants (ex. faces, aretes, vertices).
    """

    grouped = {}

    for item in items:
        grouped.setdefault(node_of(item), []).append(item)

    return grouped

# --------------------------------------------------
# SCENE QUERIES
# --------------------------------------------------

def _filtered(nodes, settings):
    """
    Filtre 'nodes' selon settings["general"] (ignore_nodes, ignore_referenced).

    nodes    : liste de nodes (noms longs).
    settings : dict de settings (voir settings_utilities.py).
    """

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
    Transforms simples (hors joints, contraintes, ...), filtres par settings.

    scope    : SCENE (toute la scene) ou SELECTION (selection + descendants).
    settings : dict de settings (voir _filtered).
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
    """
    Shapes de 'transform' (non-intermediaires), eventuellement filtrees par type.

    transform  : transform dont on veut les shapes.
    shape_type : type de shape a filtrer (ex. "mesh"), ou None pour toutes.
    """

    kwargs = {"shapes": True, "fullPath": True, "noIntermediate": True}

    if shape_type:
        kwargs["type"] = shape_type

    return cmds.listRelatives(transform, **kwargs) or []


def groups(scope, settings):
    """Transforms sans aucune shape (voir transforms)."""
    return [t for t in transforms(scope, settings) if not cmds.listRelatives(t, shapes=True)]


def shape_transforms(scope, settings, shape_type):
    """Transforms ayant au moins une shape du type donne (voir transforms, shapes_of)."""
    return [t for t in transforms(scope, settings) if shapes_of(t, shape_type)]


def meshes(scope, settings):
    """Shapes mesh non-intermediaires de tous les transforms (voir transforms, shapes_of)."""

    result = []

    for transform in transforms(scope, settings):
        result.extend(shapes_of(transform, "mesh"))

    return result

# --------------------------------------------------
# SELECTION
# --------------------------------------------------

def select_items(items):
    """
    Selectionne les nodes/composants encore existants dans 'items'.

    items : liste de noms de nodes et/ou de composants.

    Retourne le nombre d'elements effectivement selectionnes.
    """

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
    Renomme 'nodes' en toute securite, meme si parents et enfants sont tous
    renommes dans le meme lot (resolution par uuid, pas par nom).

    nodes        : liste de nodes (noms longs) a renommer.
    new_leaf_for : fonction(node_long_name) -> nouveau nom court, ou None pour ignorer.

    Retourne la liste des nodes qui n'ont pas pu etre renommes.
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
    """Regroupe toutes les commandes executees dans le bloc en un seul undo (Ctrl+Z)."""

    cmds.undoInfo(openChunk=True, chunkName=name)

    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def safe(function, *args, **kwargs):
    """
    Execute une commande Maya, transforme une erreur en warning plutot que de lever.

    function : commande/callable a executer (ex. cmds.delete).

    Retourne True si l'appel a reussi, False sinon.
    """

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
    """
    Supprime les noeuds polyTweak trouves dans l'historique de 'obj'.

    obj : mesh (ou composant) dont on veut nettoyer l'historique.
    """

    history = cmds.listHistory(obj) or []
    tweaks = cmds.ls(history, type="polyTweak")

    if tweaks:
        cmds.delete(tweaks)

# --------------------------------------------------
# MESH - TOPOLOGY CHECKS
# --------------------------------------------------

def ngons(mesh, max_sides=4):
    """Faces de 'mesh' ayant plus de 'max_sides' cotes."""

    result = []
    iterator = om.MItMeshPolygon(dag_path(mesh))

    while not iterator.isDone():
        if iterator.polygonVertexCount() > max_sides:
            result.append("{}.f[{}]".format(mesh, iterator.index()))
        iterator.next()

    return result


def non_manifold(mesh):
    """Aretes et vertices non-manifold de 'mesh'."""

    edges = cmds.polyInfo(mesh, nonManifoldEdges=True) or []
    vertices = cmds.polyInfo(mesh, nonManifoldVertices=True) or []

    return cmds.ls(edges + vertices, long=True) if edges or vertices else []


def lamina_faces(mesh):
    """Faces lamina de 'mesh' (deux faces partageant exactement les memes aretes)."""

    faces = cmds.polyInfo(mesh, laminaFaces=True) or []

    return cmds.ls(faces, long=True) if faces else []


def zero_area_faces(mesh, tolerance=1e-8):
    """Faces de 'mesh' dont l'aire est inferieure a 'tolerance'."""

    result = []
    iterator = om.MItMeshPolygon(dag_path(mesh))

    while not iterator.isDone():
        if iterator.getArea() < tolerance:
            result.append("{}.f[{}]".format(mesh, iterator.index()))
        iterator.next()

    return result


def zero_length_edges(mesh, tolerance=1e-6):
    """Aretes de 'mesh' dont la longueur est inferieure a 'tolerance'."""

    result = []
    iterator = om.MItMeshEdge(dag_path(mesh))

    while not iterator.isDone():
        if iterator.length() < tolerance:
            result.append("{}.e[{}]".format(mesh, iterator.index()))
        iterator.next()

    return result


def has_history(mesh, ignore_types=()):
    """
    True si 'mesh' a de l'historique de construction (hors types listes dans 'ignore_types').

    ignore_types : types de nodes a ignorer dans l'historique (ex. ("groupId",)).
    """

    history = cmds.listHistory(mesh, pruneDagObjects=True) or []

    return any(cmds.nodeType(node) not in ignore_types for node in history)


def is_unfrozen(transform, tolerance=1e-5):
    """
    True si translate/rotate ne sont pas a zero ou si scale n'est pas a 1,
    a 'tolerance' pres.
    """

    translate = cmds.getAttr(transform + ".translate")[0]
    rotate = cmds.getAttr(transform + ".rotate")[0]
    scale = cmds.getAttr(transform + ".scale")[0]

    if any(abs(value) > tolerance for value in translate + rotate):
        return True

    return any(abs(value - 1.0) > tolerance for value in scale)


def has_locked_normals(mesh):
    """True si au moins une normale de 'mesh' est verrouillee."""

    fn_mesh = om.MFnMesh(dag_path(mesh))
    _, normal_ids = fn_mesh.getNormalIds()

    return any(fn_mesh.isNormalLocked(index) for index in set(normal_ids))

# --------------------------------------------------
# MESH - TOPOLOGY FIXES
# --------------------------------------------------

def triangulate_faces(faces):
    """Triangule les faces donnees (regroupees par mesh)."""

    for components in group_by_node(faces).values():
        safe(cmds.polyTriangulate, components, constructionHistory=False)


def delete_components(components):
    """Supprime les composants donnes (regroupes par mesh)."""

    for items in group_by_node(components).values():
        safe(cmds.delete, items)


def collapse_edges(edges):
    """Collapse les aretes donnees (regroupees par mesh)."""

    for items in group_by_node(edges).values():
        safe(cmds.polyCollapseEdge, items, constructionHistory=False)


def delete_history(meshes_):
    """Supprime l'historique de construction de chaque mesh de 'meshes_'."""

    for mesh in meshes_:
        safe(cmds.delete, mesh, constructionHistory=True)


def freeze_transforms(transforms_):
    """Freeze translate/rotate/scale (makeIdentity) de chaque transform de 'transforms_'."""

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
    """Deverrouille toutes les normales de chaque mesh de 'meshes_'."""

    for mesh in meshes_:
        safe(cmds.polyNormalPerVertex, mesh, unFreezeNormal=True)

# --------------------------------------------------
# UV - CHECKS
# --------------------------------------------------

def uv_sets(mesh):
    """Liste des UV sets de 'mesh'."""
    return cmds.polyUVSet(mesh, query=True, allUVSets=True) or []


def missing_uvs(mesh):
    """Mesh entier (si aucune UV) ou liste des faces sans UVs."""

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
    UVs a coordonnees negatives, ou hors 0-1 si les UDIMs ne sont pas autorises.

    allow_udim  : autorise les UVs au-dela de u=1 (tiles UDIM).
    udim_max_u  : u maximum autorise quand allow_udim est actif.
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
    """Faces de 'mesh' pour lesquelles test(us, vs) est vrai (voir crossing_borders, flipped)."""

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
    """True si les UVs (us, vs) d'une face s'etendent sur plus d'une tile UDIM."""
    return (
        math.floor(min(us) + _UV_EPSILON) != math.floor(max(us) - _UV_EPSILON)
        or math.floor(min(vs) + _UV_EPSILON) != math.floor(max(vs) - _UV_EPSILON)
    )


def _is_flipped(us, vs):
    """True si le winding des UVs (us, vs) d'une face est inverse (aire signee negative)."""

    count = len(us)
    area = 0.0

    for index in range(count):
        following = (index + 1) % count
        area += us[index] * vs[following] - us[following] * vs[index]

    return area < 0.0


def crossing_borders(mesh):
    """Faces de 'mesh' dont les UVs s'etendent sur plus d'une tile."""
    return _face_uv_issues(mesh, _crosses_tile)


def flipped(mesh):
    """Faces de 'mesh' dont le winding UV est inverse."""
    return _face_uv_issues(mesh, _is_flipped)


def overlapping(mesh):
    """Faces de 'mesh' dont les UVs se superposent."""

    faces = cmds.polyUVOverlap(mesh + ".f[*]", overlappingComponents=True) or []

    return cmds.ls(faces, long=True) if faces else []

# --------------------------------------------------
# UV - FIXES
# --------------------------------------------------

def delete_extra_sets(meshes_, keep=1):
    """Supprime les UV sets au-dela des 'keep' premiers, pour chaque mesh de 'meshes_'."""

    for mesh in meshes_:
        for name in uv_sets(mesh)[max(keep, 1):]:
            safe(cmds.polyUVSet, mesh, delete=True, uvSet=name)


def rename_first_set(meshes_, name="map1"):
    """Renomme le premier UV set de chaque mesh de 'meshes_' en 'name'."""

    for mesh in meshes_:
        sets = uv_sets(mesh)
        if sets and sets[0] != name:
            safe(cmds.polyUVSet, mesh, rename=True, uvSet=sets[0], newUVSet=name)

# --------------------------------------------------
# MATERIAL
# --------------------------------------------------

def shading_groups(mesh):
    """ShadingEngine(s) connectes a 'mesh'."""

    connected = cmds.listConnections(mesh, type="shadingEngine") or []

    return sorted(set(connected))


def has_per_face_assignment(mesh):
    """True si des matieres sont assignees par face plutot qu'a l'objet entier."""

    connected = cmds.listConnections(
        mesh + ".instObjGroups[0].objectGroups", type="shadingEngine"
    )

    return bool(connected)


def breaks_policy(mesh, default_group, policy):
    """
    True si l'assignation de shading de 'mesh' enfreint 'policy'.

    default_group : shadingEngine de reference (ex. initialShadingGroup).
    policy        : "required" (seulement default_group), "forbidden" (rien d'autre
                     que default_group), "any" (toujours valide).
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
    """Assigne 'shading_group' a chaque mesh de 'meshes_'."""

    for mesh in meshes_:
        safe(cmds.sets, mesh, edit=True, forceElement=shading_group)

# --------------------------------------------------
# COLOR
# --------------------------------------------------

def color_sets(mesh):
    """Liste des color sets de 'mesh'."""
    return cmds.polyColorSet(mesh, query=True, allColorSets=True) or []


def has_display_color(node):
    """True si 'node' a une couleur d'affichage custom (useObjectColor, ou override hors display layer)."""

    if cmds.getAttr(node + ".useObjectColor"):
        return True

    if not cmds.getAttr(node + ".overrideEnabled"):
        return False

    from_layer = cmds.listConnections(node + ".drawOverride", source=True, destination=False)

    return not from_layer


def has_outliner_color(node):
    """True si 'node' a une couleur d'outliner custom (useOutlinerColor)."""
    return bool(cmds.getAttr(node + ".useOutlinerColor"))


def delete_color_sets(meshes_):
    """Supprime tous les color sets de chaque mesh de 'meshes_'."""

    for mesh in meshes_:
        for name in color_sets(mesh):
            safe(cmds.polyColorSet, mesh, delete=True, colorSet=name)


def reset_display_color(nodes):
    """Desactive la couleur d'affichage custom de chaque node de 'nodes'."""

    for node in nodes:

        safe(cmds.setAttr, node + ".useObjectColor", 0)

        from_layer = cmds.listConnections(node + ".drawOverride", source=True, destination=False)

        if not from_layer:
            safe(cmds.setAttr, node + ".overrideEnabled", 0)


def reset_outliner_color(nodes):
    """Desactive la couleur d'outliner custom de chaque node de 'nodes'."""

    for node in nodes:
        safe(cmds.setAttr, node + ".useOutlinerColor", 0)
