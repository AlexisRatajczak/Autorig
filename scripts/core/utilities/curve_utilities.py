# ====================================================================================================================
# CURVE UTILITIES
# ====================================================================================================================
#
#   create_curve(points, name, degree)              - courbe avec un CV par point (degré limité au nombre de points)
#   get_curve_fn(curve)                             - MFnNurbsCurve de la shape de la courbe
#   get_curve_length(curve)                         - longueur de la courbe
#   get_points_along_curve(curve, count)            - 'count' positions à distance égale le long de la courbe
#   get_points_along_points(points, count, degree)  - idem sur la courbe de create_curve(points) (temporaire)
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om


def create_curve(points, name="curve", degree=3):
    """Courbe avec un CV par point (degré 'degree', limité à len(points) - 1). Retourne son transform."""

    if len(points) < 2:
        raise ValueError("create_curve : au moins 2 points sont nécessaires.")

    degree = max(1, min(int(degree), len(points) - 1))

    return cmds.curve(point=[list(point) for point in points], degree=degree, name=name)


def get_curve_fn(curve):
    """MFnNurbsCurve de la shape (non intermédiaire) de 'curve'."""

    shape = (cmds.listRelatives(curve, shapes=True, noIntermediate=True, fullPath=True) or [curve])[0]

    selection = om.MSelectionList()
    selection.add(shape)

    return om.MFnNurbsCurve(selection.getDagPath(0))


def get_curve_length(curve):
    """Longueur de 'curve'."""

    return get_curve_fn(curve).length()


def get_points_along_curve(curve, count):
    """'count' positions monde [x, y, z] (min 2) à distance égale le long de 'curve', extrémités comprises."""

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
    """
    'count' positions à distance égale le long de la courbe que créerait
    create_curve(points, degree=degree) (courbe temporaire, supprimée).
    """

    curve = create_curve(points, name="curve_utilities_temp_crv", degree=degree)

    try:
        return get_points_along_curve(curve, count)
    finally:
        cmds.delete(curve)
