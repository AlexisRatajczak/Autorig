# ====================================================================================================================
# SKINCLUSTER UTILITIES
# ====================================================================================================================
#
# BIND
#   bind_skin(joints, geometry, name, max_influences, **flags) - skinCluster avec les options du Bind Skin de Maya
#   skin_to_closest_joints(joints, geometry, name)             - chaque CV à 100% sur le joint le plus proche
#   skin_cvs_to_joints(curve, joints, name)                    - chaque CV d'une courbe à 100% sur le joint de même index
#   skin_by_segments(joints, surface, name, tolerance)         - surface NURBS : chaque CV au joint de son segment
#
# HELPERS
#   get_shape(node)                                            - shape non intermédiaire d'un transform
#   get_cvs(geometry)                                          - CVs (courbe ou surface NURBS), à plat
#   get_joint_surface_params(shape, joints)                    - paramètres des joints sur la surface, le long du ruban
#   get_cv_greville_params(shape, direction)                   - abscisse de Greville de chaque CV d'une surface
#   get_param_joint_index(param, joint_params, tolerance)      - joint qui possède un paramètre (segments)
#   get_segment_joint_index(point, positions, tolerance)       - joint qui possède un point (segments en positions)
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om


# ==========================================================
# HELPERS
# ==========================================================

def _names(joints):
    """Noms des joints (noms ou Joint)."""

    return [getattr(joint, "name", joint) for joint in joints]


def get_shape(node):
    """Shape non intermédiaire de 'node' (transform ou shape)."""

    return (cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or [node])[0]


def get_cvs(geometry):
    """CVs de 'geometry' (courbe ou surface NURBS), à plat."""

    shape = get_shape(geometry)

    pattern = f"{shape}.cv[*][*]" if cmds.nodeType(shape) == "nurbsSurface" else f"{shape}.cv[*]"

    return cmds.ls(pattern, flatten=True) or []


# ==========================================================
# BIND
# ==========================================================

def bind_skin(joints, geometry, name=None, max_influences=2, **flags):

    """
    skinCluster de 'geometry' sur 'joints' avec les options du Bind Skin de
    Maya : Selected joints, Closest distance, Classic linear, Normalize
    Interactive, Weight distribution Neighbors, Max influences
    'max_influences', Maintain max influences, Remove unused influences.
    'flags' : options de cmds.skinCluster qui remplacent ces défauts.
    Retourne le skinCluster.
    """

    options = {
        "toSelectedBones": True,
        "bindMethod": 0,
        "skinMethod": 0,
        "normalizeWeights": 1,
        "weightDistribution": 1,
        "maximumInfluences": max_influences,
        "obeyMaxInfluences": True,
        "removeUnusedInfluence": True,
        "includeHiddenSelections": False,
    }
    options.update(flags)

    if name:
        options["name"] = name

    return cmds.skinCluster(_names(joints), geometry, **options)[0]


def skin_to_closest_joints(joints, geometry, name=None):

    """
    Skinne 'geometry' à 'joints', puis met chaque CV à 100% sur le joint
    le plus proche de lui (distance monde CV -> position du joint).

    Le bind 'closest distance' de Maya mesure la distance aux os (segments
    joint -> parent), pas aux joints : un CV peut y être attribué au parent
    d'un joint pourtant plus proche. D'où la réattribution explicite.
    """

    joints = _names(joints)

    skin = bind_skin(joints, geometry, name=name, max_influences=2, weightDistribution=0, removeUnusedInfluence=False)

    joint_positions = [
        (joint, om.MVector(cmds.xform(joint, query=True, worldSpace=True, translation=True)))
        for joint in joints
    ]

    for cv in get_cvs(geometry):

        position = om.MVector(cmds.pointPosition(cv, world=True))

        closest = min(joint_positions, key=lambda item: (item[1] - position).length())[0]

        cmds.skinPercent(skin, cv, transformValue=[(closest, 1.0)])

    return skin


def skin_cvs_to_joints(curve, joints, name=None):

    """
    Skinne 'curve' à 'joints' : le CV i à 100% sur le joint i (autant de
    joints que de CVs, ex : courbe curve_utilities.create_curve sur leurs
    positions). Retourne le skinCluster.
    """

    joints = _names(joints)

    skin = bind_skin(joints, curve, name=name or f"{curve}_skin", max_influences=1, removeUnusedInfluence=False)

    for index, joint in enumerate(joints):
        cmds.skinPercent(skin, f"{curve}.cv[{index}]", transformValue=[(joint, 1.0)])

    return skin


def skin_by_segments(joints, surface, name=None, tolerance=1e-4):

    """
    Skinne 'surface' (NURBS) à 'joints' (dans l'ordre de la chaîne) par
    segments, une seule influence par CV. Comparaison dans l'espace des
    paramètres de la surface, le long du ruban (les CVs d'une NURBS de
    degré > 1 ne sont pas sur la surface) :

    - paramètre de chaque joint : point le plus proche sur la surface, dans
      la direction où les joints varient le plus (get_joint_surface_params) ;
    - paramètre de chaque CV : son abscisse de Greville (get_cv_greville_params) ;
    - un CV au paramètre d'un joint va à ce joint ; entre le joint i et
      i + 1, au joint i (get_param_joint_index).

    Retourne le skinCluster.
    """

    joints = _names(joints)

    shape = get_shape(surface)

    # Paramètres au repos, avant le skin.
    direction, joint_params = get_joint_surface_params(shape, joints)
    cv_params = get_cv_greville_params(shape, direction)

    skin = bind_skin(joints, surface, name=name, max_influences=2, weightDistribution=0, removeUnusedInfluence=False)

    for cv, param in cv_params:
        index = get_param_joint_index(param, joint_params, tolerance)
        cmds.skinPercent(skin, cv, transformValue=[(joints[index], 1.0)])

    return skin


# ==========================================================
# SEGMENT HELPERS
# ==========================================================

def get_joint_surface_params(shape, joints):

    """
    (direction, [param, ...]) des joints sur la surface : point le plus
    proche de chaque joint (MFnNurbsSurface.closestPoint, monde), dans la
    direction ("U" / "V") où leurs paramètres varient le plus.
    """

    selection = om.MSelectionList()
    selection.add(shape)

    fn_surface = om.MFnNurbsSurface(selection.getDagPath(0))

    uvs = []

    for joint in joints:
        position = om.MPoint(cmds.xform(joint, query=True, worldSpace=True, translation=True))
        _, u, v = fn_surface.closestPoint(position, space=om.MSpace.kWorld)
        uvs.append((u, v))

    u_range = max(u for u, _ in uvs) - min(u for u, _ in uvs)
    v_range = max(v for _, v in uvs) - min(v for _, v in uvs)

    if u_range >= v_range:
        return "U", [u for u, _ in uvs]

    return "V", [v for _, v in uvs]


def get_cv_greville_params(shape, direction):

    """
    [(cv, param), ...] pour tous les CVs de la surface : abscisse de
    Greville du CV dans 'direction' (moyenne de 'degré' knots consécutifs
    du vecteur de knots Maya).
    """

    axis = "U" if str(direction).upper() == "U" else "V"

    degree = cmds.getAttr(f"{shape}.degree{axis}")

    info = cmds.createNode("surfaceInfo", name="skin_surfaceInfo_temp")

    try:
        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{info}.inputSurface", force=True)
        knots = list(cmds.getAttr(f"{info}.knots{axis}")[0] or [])
    finally:
        cmds.delete(info)

    result = []

    for cv in cmds.ls(f"{shape}.cv[*][*]", flatten=True) or []:

        indices = cv.split(".cv")[-1].strip("[]").split("][")
        index = int(indices[0] if axis == "U" else indices[1])

        window = knots[index:index + degree]
        param = sum(window) / len(window) if window else (knots[-1] if knots else 0.0)

        result.append((cv, param))

    return result


def get_param_joint_index(param, joint_params, tolerance=1e-4):

    """
    Index du joint qui possède 'param' ('joint_params' dans l'ordre de la
    chaîne) : même paramètre qu'un joint -> ce joint (le dernier des
    confondus) ; entre i et i + 1 -> i ; avant le premier -> 0 ; au-delà
    du dernier -> le dernier.
    """

    if len(joint_params) < 2:
        return 0

    span = abs(joint_params[-1] - joint_params[0]) or 1.0
    snap = max(tolerance * span, 1e-6)

    coincident = [index for index, value in enumerate(joint_params) if abs(param - value) <= snap]

    if coincident:
        return coincident[-1]

    sign = 1.0 if joint_params[-1] >= joint_params[0] else -1.0

    t = sign * param
    ts = [sign * value for value in joint_params]

    if t < ts[0]:
        return 0

    for index in range(len(ts) - 1):
        if ts[index] <= t < ts[index + 1]:
            return index

    return len(ts) - 1


def get_segment_joint_index(point, positions, tolerance=1e-4):

    """
    Index du joint qui possède 'point' (MVector) le long de la chaîne
    'positions' (MVector) : segment le plus proche ; joint i, ou i + 1 si
    la projection arrive au bout du segment. Un point au même emplacement
    qu'un joint va à ce joint (le dernier des confondus).
    """

    if len(positions) < 2:
        return 0

    best_index = 0
    best_distance = None
    best_projection = positions[0]

    for i in range(len(positions) - 1):

        start, end = positions[i], positions[i + 1]
        segment = end - start
        length_sq = segment * segment

        u = 0.0 if length_sq < 1e-12 else max(0.0, min(1.0, ((point - start) * segment) / length_sq))

        projection = start + segment * u
        distance = (point - projection).length()

        if best_distance is None or distance < best_distance - 1e-9:
            best_distance = distance
            best_projection = projection
            best_index = i + 1 if u >= 1.0 - tolerance else i

    chain_length = sum((positions[i + 1] - positions[i]).length() for i in range(len(positions) - 1))
    snap = max(tolerance * chain_length, 1e-6)

    coincident = [index for index, position in enumerate(positions) if (best_projection - position).length() <= snap]

    if coincident:
        return coincident[-1]

    return best_index
