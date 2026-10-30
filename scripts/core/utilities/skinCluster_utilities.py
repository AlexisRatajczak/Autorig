# ====================================================================================================================
# SKINCLUSTER UTILITIES
# ====================================================================================================================
#
#   HELPERS
#       _names(joints)                                          - joint names (names or Joint)
#       get_shape(node)                                         - non intermediate shape of a transform
#       get_cvs(geometry)                                       - CVs (NURBS curve or surface), flattened
#   BIND
#       bind_skin(joints, geometry, name, max_influences, **flags) - skinCluster with Maya Bind Skin options
#       skin_to_closest_joints(joints, geometry, name)             - each CV 100% on its closest joint
#       skin_cvs_to_joints(curve, joints, name)                    - curve CV i 100% on joint i
#       skin_by_segments(joints, surface, name, tolerance)         - NURBS surface: each CV on the joint of its segment
#   SEGMENT HELPERS
#       get_joint_surface_params(shape, joints)                 - joint parameters on the surface, along the ribbon
#       get_cv_greville_params(shape, direction)                - Greville abscissa of each surface CV
#       get_param_joint_index(param, joint_params, tolerance)   - joint owning a parameter (segments)
#       get_segment_joint_index(point, positions, tolerance)    - joint owning a point (segments in positions)
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om


# ==========================================================
# HELPERS
# ==========================================================

def _names(joints):
    """Joint names (names or Joint)."""

    return [getattr(joint, "name", joint) for joint in joints]


def get_shape(node):
    """Non intermediate shape of 'node' (transform or shape)."""

    return (cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or [node])[0]


def get_cvs(geometry):
    """CVs of 'geometry' (NURBS curve or surface), flattened."""

    shape = get_shape(geometry)

    pattern = f"{shape}.cv[*][*]" if cmds.nodeType(shape) == "nurbsSurface" else f"{shape}.cv[*]"

    return cmds.ls(pattern, flatten=True) or []


# ==========================================================
# BIND
# ==========================================================

def bind_skin(joints, geometry, name=None, max_influences=2, **flags):

    """
    skinCluster of 'geometry' on 'joints' with the Maya Bind Skin options:
    Selected joints, Closest distance, Classic linear, Normalize Interactive,
    Neighbors, 'max_influences', Maintain max influences, Remove unused.
    'flags' : cmds.skinCluster options overriding these defaults.
    Returns the skinCluster.
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
    Skin 'geometry' to 'joints', then put each CV 100% on its closest joint
    (world distance). Maya's closest distance measures bones, not joints,
    so a CV can land on the parent of a closer joint.
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
    Skin 'curve' to 'joints': CV i 100% on joint i (one joint per CV, ex:
    curve_utilities.create_curve on their positions). Returns the skinCluster.
    """

    joints = _names(joints)

    skin = bind_skin(joints, curve, name=name or f"{curve}_skin", max_influences=1, removeUnusedInfluence=False)

    for index, joint in enumerate(joints):
        cmds.skinPercent(skin, f"{curve}.cv[{index}]", transformValue=[(joint, 1.0)])

    return skin


def skin_by_segments(joints, surface, name=None, tolerance=1e-4):

    """
    Skin a NURBS 'surface' to 'joints' (chain order) by segments, one
    influence per CV, compared in surface parameter space along the ribbon
    (CVs of a degree > 1 NURBS are not on the surface):

    - joint parameter : closest surface point (get_joint_surface_params);
    - CV parameter    : its Greville abscissa (get_cv_greville_params);
    - a CV on a joint parameter goes to that joint, between joint i and i + 1 to joint i.

    Returns the skinCluster.
    """

    joints = _names(joints)

    shape = get_shape(surface)

    # Rest parameters, before the skin.
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
    (direction, [param, ...]) of the joints on the surface: closest point of
    each joint, in the direction ("U" / "V") where their parameters vary most.
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
    [(cv, param), ...] for every surface CV: its Greville abscissa in
    'direction' (mean of 'degree' consecutive knots of the Maya knot vector).
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
    Index of the joint owning 'param' ('joint_params' in chain order): on a
    joint -> that joint (last of coincident ones); between i and i + 1 -> i;
    before the first -> 0; past the last -> the last.
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
    Index of the joint owning 'point' (MVector) along the 'positions' chain:
    closest segment, joint i (i + 1 at the segment end). A point on a joint
    goes to that joint (last of coincident ones).
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
