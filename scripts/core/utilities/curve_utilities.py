# ====================================================================================================================
# CURVE UTILITIES
# ====================================================================================================================
#
#   create_curve(points, name, degree)              - curve with one CV per point (degree capped by the point count)
#   create_offset_curve(curve, offsets, name)       - copy of a curve with each CV moved by its world offset
#   get_curve_shape(curve)                          - curve shape (non intermediate)
#   get_curve_fn(curve)                             - MFnNurbsCurve of the curve shape
#   get_curve_length(curve)                         - curve length
#   get_cv_positions(curve)                         - world positions of the CVs
#   get_closest_parameter(curve, position)          - parameter of the closest curve point
#   get_points_along_curve(curve, count)            - 'count' evenly spaced positions along the curve
#   get_points_along_points(points, count, degree)  - same, on a temporary create_curve(points)
#   ATTACH
#       create_point_on_curve(curve, parameter, name)            - world pointOnCurveInfo at a parameter
#       attach_to_curve(node, curve, parameter, name)            - node world translate driven by a curve point
#       create_locators_on_curve(curve, positions, names, parent) - locators attached at the closest points
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om


def create_curve(points, name="curve", degree=3):
    """Curve with one CV per point (degree capped at len(points) - 1). Returns its transform."""

    if len(points) < 2:
        raise ValueError("create_curve : au moins 2 points sont nécessaires.")

    degree = max(1, min(int(degree), len(points) - 1))

    return cmds.curve(point=[list(point) for point in points], degree=degree, name=name)


def create_offset_curve(curve, offsets, name="offset_crv"):
    """
    New curve (same degree) through the CVs of 'curve', each moved by its world
    vector of 'offsets' (one per CV, missing ones = no offset). Returns its transform.
    """

    positions = get_cv_positions(curve)
    offsets = list(offsets) + [(0.0, 0.0, 0.0)] * (len(positions) - len(offsets))

    points = [[p[k] + o[k] for k in range(3)] for p, o in zip(positions, offsets)]

    return create_curve(points, name=name, degree=cmds.getAttr(f"{get_curve_shape(curve)}.degree"))


def get_curve_shape(curve):
    """Non intermediate shape of 'curve' (the curve itself if it is a shape)."""

    return (cmds.listRelatives(curve, shapes=True, noIntermediate=True, fullPath=True) or [curve])[0]


def get_curve_fn(curve):
    """MFnNurbsCurve of the (non intermediate) shape of 'curve'."""

    selection = om.MSelectionList()
    selection.add(get_curve_shape(curve))

    return om.MFnNurbsCurve(selection.getDagPath(0))


def get_curve_length(curve):
    """Length of 'curve'."""

    return get_curve_fn(curve).length()


def get_cv_positions(curve):
    """World positions [x, y, z] of the CVs of 'curve'."""

    return [[point.x, point.y, point.z] for point in get_curve_fn(curve).cvPositions(om.MSpace.kWorld)]


def get_closest_parameter(curve, position):
    """Parameter of the point of 'curve' closest to the world 'position'."""

    _, parameter = get_curve_fn(curve).closestPoint(om.MPoint(*position), 1e-6, om.MSpace.kWorld)

    return parameter


def get_points_along_curve(curve, count):
    """'count' (min 2) evenly spaced world positions [x, y, z] along 'curve', ends included."""

    count = max(2, int(count))

    curve_fn = get_curve_fn(curve)
    length = curve_fn.length()

    points = []

    for i in range(count):
        parameter = curve_fn.findParamFromLength(length * i / (count - 1))
        point = curve_fn.getPointAtParam(parameter, om.MSpace.kWorld)
        points.append([point.x, point.y, point.z])

    return points


def get_points_along_points(points, count, degree=3):
    """'count' evenly spaced positions along a temporary create_curve(points, degree) (deleted afterwards)."""

    curve = create_curve(points, name="curve_utilities_temp_crv", degree=degree)

    try:
        return get_points_along_curve(curve, count)
    finally:
        cmds.delete(curve)


# ==========================================================
# ATTACH
# ==========================================================

def create_point_on_curve(curve, parameter, name=None):
    """pointOnCurveInfo reading the world shape of 'curve' at 'parameter'. Returns the node."""

    shape = get_curve_shape(curve)

    info = cmds.createNode("pointOnCurveInfo", name=name or f"{shape.split('|')[-1]}_poci")

    cmds.connectAttr(f"{shape}.worldSpace[0]", f"{info}.inputCurve")
    cmds.setAttr(f"{info}.parameter", parameter)

    return info


def attach_to_curve(node, curve, parameter, name=None):
    """
    Drive the world position of 'node' with the point of 'curve' at 'parameter':
    pointOnCurveInfo -> translate, inheritsTransform off (the parent does not
    move it). Returns the pointOnCurveInfo.
    """

    info = create_point_on_curve(curve, parameter, name=name or f"{node}_poci")

    cmds.setAttr(f"{node}.inheritsTransform", 0)
    cmds.connectAttr(f"{info}.position", f"{node}.translate", force=True)

    return info


def create_locators_on_curve(curve, positions, names, parent=None):
    """
    One locator per name, attached (attach_to_curve) at the point of 'curve'
    closest to its world position, under 'parent'. Returns the locators.
    """

    locators = []

    for name, position in zip(names, positions):

        locator = cmds.spaceLocator(name=name)[0]

        if parent and cmds.objExists(parent):
            locator = cmds.parent(locator, parent)[0]

        attach_to_curve(locator, curve, get_closest_parameter(curve, position))

        locators.append(locator)

    return locators
