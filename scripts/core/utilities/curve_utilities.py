# ====================================================================================================================
# CURVE UTILITIES
# ====================================================================================================================
#
#   create_curve(points, name, degree)              - curve with one CV per point (degree capped by the point count)
#   get_curve_fn(curve)                             - MFnNurbsCurve of the curve shape
#   get_curve_length(curve)                         - curve length
#   get_points_along_curve(curve, count)            - 'count' evenly spaced positions along the curve
#   get_points_along_points(points, count, degree)  - same, on a temporary create_curve(points)
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


def get_curve_fn(curve):
    """MFnNurbsCurve of the (non intermediate) shape of 'curve'."""

    shape = (cmds.listRelatives(curve, shapes=True, noIntermediate=True, fullPath=True) or [curve])[0]

    selection = om.MSelectionList()
    selection.add(shape)

    return om.MFnNurbsCurve(selection.getDagPath(0))


def get_curve_length(curve):
    """Length of 'curve'."""

    return get_curve_fn(curve).length()


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
