# ====================================================================================================================
# TRANSFORM UTILITIES
# ====================================================================================================================
#
#   build_matrix(x_axis, y_axis, z_axis, position)          - world matrix (list) from 3 axes and a position
#   create_pivot(name, matrix, parent)                      - locator placed by a world matrix, baked, under parent
#   set_rotation_limit(node, axis, minimum, maximum)        - rotate limit on one axis (value or plug), enabled
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om


def build_matrix(x_axis, y_axis, z_axis, position):
    """World matrix (16 floats) with the given axis rows and position."""

    return [
        x_axis[0], x_axis[1], x_axis[2], 0.0,
        y_axis[0], y_axis[1], y_axis[2], 0.0,
        z_axis[0], z_axis[1], z_axis[2], 0.0,
        position[0], position[1], position[2], 1.0,
    ]


def create_pivot(name, matrix, parent=None):

    """
    Locator 'name' placed by the world 'matrix', under 'parent', its local transform
    baked into the offsetParentMatrix (clean channels: rotations / limits start at 0).
    Returns its name.
    """

    pivot = cmds.spaceLocator(name=name)[0]

    if parent and cmds.objExists(parent):
        pivot = cmds.parent(pivot, parent)[0]

    cmds.xform(pivot, worldSpace=True, matrix=list(matrix))

    local = om.MMatrix(cmds.getAttr(f"{pivot}.worldMatrix[0]")) * om.MMatrix(cmds.getAttr(f"{pivot}.parentInverseMatrix[0]"))

    cmds.setAttr(f"{pivot}.offsetParentMatrix", list(local), type="matrix")

    cmds.setAttr(f"{pivot}.translate", 0, 0, 0)
    cmds.setAttr(f"{pivot}.rotate", 0, 0, 0)
    cmds.setAttr(f"{pivot}.scale", 1, 1, 1)

    return pivot


def set_rotation_limit(node, axis, minimum=None, maximum=None):

    """
    Rotate limit of 'node' on 'axis' ("X" / "Y" / "Z"): 'minimum' / 'maximum' as a
    value or a plug (connected, the limit then follows it), None = no limit on
    that side. The transform clamps its rotation, even when rotate is driven.
    """

    for bound, value in (("min", minimum), ("max", maximum)):

        if value is None:
            continue

        attr = f"{node}.{bound}Rot{axis}Limit"

        if isinstance(value, str):
            cmds.connectAttr(value, attr, force=True)
        else:
            cmds.setAttr(attr, value)

        cmds.setAttr(f"{attr}Enable", 1)
