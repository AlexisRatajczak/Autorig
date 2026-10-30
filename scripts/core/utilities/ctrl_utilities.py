# ====================================================================================================================
# CTRL UTILITIES
# ====================================================================================================================
#
#   MODULE
#       _get_cv_positions(shape)                        - object space CV positions of a curve
#       _set_cv_positions(shape, points)                - move the CVs of a curve
#       load_shapes()                                   - load shapesCtrl_config.json (SHAPES)
#       _mat3_mul(a, b)                                 - product of two 3x3 matrices
#       _rotation_matrix(rx, ry, rz)                    - 3x3 rotation matrix (euler XYZ, degrees)
#       _transform_point(point, translate, rotation, ...) - transform a point (scale / rotate / translate)
#   CONTROL (class)
#       __init__(name, shape, size, color)              - store the settings, creates nothing
#       create(parent=None)                             - ctrl transform + shape + color
#       create_offset(suffix, use_group, parent)        - offset its transform (offsetParentMatrix or group)
#       transfer_offset_parent_matrix(reset=True)       - bake the local transform into offsetParentMatrix
#       transfer_to_joint(joint)                        - move the ctrl shapes onto a joint, delete the ctrl
#       create_neg_offset(translate, rotate, scale)     - inverse offset groups (live counter animation)
#       reset()                                         - reset keyable / channel box attributes
#       mirror()                                        - mirror the ctrl (+ offset group) L_ / R_
#       add_lock_limit_attr()                           - 'lockLimit' attribute driving the LimitEnables
#       set_shape(shape, size=None)                     - (re)build the ctrl curves from SHAPES
#       set_shape_from(source)                          - copy the shapes of another transform
#       delete_shapes()                                 - delete the ctrl shapes
#       get_shapes()                                    - ctrl shapes (curves)
#       set_color(color)                                - override color (index or RGB) of the shapes
#       set_line_width(width)                           - display line width of the shapes
#       transform_shape(translate, rotate, scale, pivot) - transform the shape CVs (not the ctrl)
#       translate_shape / rotate_shape / scale_shape    - transform_shape shortcuts
#       _as_vector3(value, default)                     - scalar / list -> (x, y, z)
#
# ====================================================================================================================

import json
import math
import os

import maya.cmds as cmds

SHAPES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "shapesCtrl_config.json")

LIMIT_ENABLE_ATTRS = [
    "minTransXLimitEnable", "maxTransXLimitEnable",
    "minTransYLimitEnable", "maxTransYLimitEnable",
    "minTransZLimitEnable", "maxTransZLimitEnable",
    "minRotXLimitEnable", "maxRotXLimitEnable",
    "minRotYLimitEnable", "maxRotYLimitEnable",
    "minRotZLimitEnable", "maxRotZLimitEnable",
    "minScaleXLimitEnable", "maxScaleXLimitEnable",
    "minScaleYLimitEnable", "maxScaleYLimitEnable",
    "minScaleZLimitEnable", "maxScaleZLimitEnable",
]


# --------------------------------------------------
# CURVE CV HELPERS
# --------------------------------------------------

def _get_cv_positions(shape):
    """Object space CV positions of a nurbsCurve shape."""
    cvs = cmds.ls(f"{shape}.cv[*]", flatten=True) or []
    return [
        cmds.xform(cv, query=True, objectSpace=True, translation=True)
        for cv in cvs
    ]


def _set_cv_positions(shape, points):
    """Move the CVs of a nurbsCurve shape to 'points' (object space, one per CV)."""
    cvs = cmds.ls(f"{shape}.cv[*]", flatten=True) or []
    for cv, point in zip(cvs, points):
        cmds.xform(cv, objectSpace=True, translation=list(point))
    if cmds.objExists(shape):
        cmds.dgdirty(shape)


def load_shapes():
    """Content of SHAPES_PATH (shapesCtrl_config.json)."""

    with open(SHAPES_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


SHAPES = load_shapes()


# --------------------------------------------------
# SHAPE TRANSFORM MATH
# --------------------------------------------------

def _mat3_mul(a, b):
    """Product a * b of two 3x3 matrices (lists of lists)."""
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _rotation_matrix(rx, ry, rz):

    """3x3 rotation matrix, euler XYZ in degrees, row-vector convention (p' = p . R)."""

    rx, ry, rz = math.radians(rx), math.radians(ry), math.radians(rz)

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    mat_x = [[1, 0, 0], [0, cx, sx], [0, -sx, cx]]
    mat_y = [[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]]
    mat_z = [[cz, sz, 0], [-sz, cz, 0], [0, 0, 1]]

    return _mat3_mul(_mat3_mul(mat_x, mat_y), mat_z)


def _transform_point(point, translate, rotation, scale, pivot):

    """Point relative to 'pivot' -> scale -> rotate (3x3 'rotation') -> back + translate."""

    x = (point[0] - pivot[0]) * scale[0]
    y = (point[1] - pivot[1]) * scale[1]
    z = (point[2] - pivot[2]) * scale[2]

    nx = x * rotation[0][0] + y * rotation[1][0] + z * rotation[2][0]
    ny = x * rotation[0][1] + y * rotation[1][1] + z * rotation[2][1]
    nz = x * rotation[0][2] + y * rotation[1][2] + z * rotation[2][2]

    return [
        nx + pivot[0] + translate[0],
        ny + pivot[1] + translate[1],
        nz + pivot[2] + translate[2],
    ]


# --------------------------------------------------
# CONTROL
# --------------------------------------------------

class Control:

    def __init__(self, name, shape="circle", size=1.0, color=None):
        """
        Store the ctrl settings, creates nothing (see create()).

        shape : SHAPES key (ex: "circle"), or None for no shape.
        size  : scale of the shape points.
        color : override color (index 0-31, or RGB 0-1), or None.
        """

        self.name = name
        self.shape = shape
        self.size = size
        self.color = color

        self.offset = None
        self.neg_offset = None

    # ----------------------------------------
    # CREATE
    # ----------------------------------------

    def create(self, parent=None):
        """Create the ctrl transform (replacing a node of the same name), shape and color, under 'parent'."""

        if cmds.objExists(self.name):
            cmds.delete(self.name)

        self.name = cmds.group(empty=True, name=self.name)

        if self.shape:
            self.set_shape(self.shape, size=self.size)

        if self.color is not None:
            self.set_color(self.color)

        if parent and cmds.objExists(parent):
            cmds.parent(self.name, parent)

        return self.name

    # ----------------------------------------
    # OFFSET GROUP
    # ----------------------------------------

    def create_offset(self, suffix="offset", use_group=False, parent=None):

        """
        Offset the ctrl local transform so its channels start clean.

        - use_group=False (default): baked into the ctrl offsetParentMatrix;
          the ctrl is parented under 'parent' first so the bake uses the final parent.
        - use_group=True: a matched '{name}_{suffix}' group above the ctrl,
          parented under 'parent' (else the current parent).
        """

        if not cmds.objExists(self.name):
            cmds.warning(f"{self.name} n'existe pas.")
            return None

        if not use_group:

            if parent and cmds.objExists(parent):
                cmds.parent(self.name, parent)

            self.transfer_offset_parent_matrix()
            self.offset = None

            return self.name

        base_name = self.name[: -len("_ctrl")] if self.name.endswith("_ctrl") else self.name
        offset_name = f"{base_name}_{suffix}"

        if cmds.objExists(offset_name):
            cmds.delete(offset_name)

        offset = cmds.group(empty=True, name=offset_name)

        cmds.matchTransform(offset, self.name, position=True, rotation=True)

        current_parent = cmds.listRelatives(self.name, parent=True)

        if current_parent:
            cmds.parent(offset, current_parent[0])

        cmds.parent(self.name, offset)

        if parent and cmds.objExists(parent):
            cmds.parent(offset, parent)

        self.offset = offset

        return offset

    # ----------------------------------------
    # OFFSET PARENT MATRIX
    # ----------------------------------------

    def transfer_offset_parent_matrix(self, reset=True):

        """
        Bake the current local transform (relative to the parent) into the
        offsetParentMatrix, then reset translate / rotate / scale if 'reset'.
        Same convention as Joint.freeze_transform.
        """

        if not cmds.objExists(self.name):
            cmds.warning(f"{self.name} n'existe pas.")
            return None

        current_parent = cmds.listRelatives(self.name, parent=True, fullPath=True)

        mult = cmds.createNode("multMatrix", n=f"{self.name}_offset_temp_mm")

        cmds.connectAttr(f"{self.name}.worldMatrix[0]", f"{mult}.matrixIn[0]", f=True)

        if current_parent:
            cmds.connectAttr(f"{current_parent[0]}.worldInverseMatrix[0]", f"{mult}.matrixIn[1]", f=True)

        local_matrix = cmds.getAttr(f"{mult}.matrixSum")

        cmds.delete(mult)

        cmds.setAttr(f"{self.name}.offsetParentMatrix", local_matrix, type="matrix")

        if reset:
            cmds.setAttr(f"{self.name}.translate", 0, 0, 0)
            cmds.setAttr(f"{self.name}.rotate", 0, 0, 0)
            cmds.setAttr(f"{self.name}.scale", 1, 1, 1)

        return local_matrix

    # ----------------------------------------
    # TRANSFER TO JOINT
    # ----------------------------------------

    def transfer_to_joint(self, joint):

        """Move the ctrl shapes onto 'joint' (already baked, nothing to re-bake), then delete the ctrl."""

        if not cmds.objExists(self.name) or not cmds.objExists(joint):
            cmds.warning(f"{self.name} ou {joint} n'existe pas.")
            return None

        for shape in self.get_shapes():

            duplicate = cmds.duplicate(shape, returnRootsOnly=True)[0]
            duplicate_shape = cmds.listRelatives(duplicate, shapes=True, fullPath=True)[0]

            cmds.parent(duplicate_shape, joint, shape=True, relative=True)
            cmds.delete(duplicate)

        cmds.delete(self.name)

        return joint

    # ----------------------------------------
    # NEG OFFSET
    # ----------------------------------------

    def create_neg_offset(self, translate=True, rotate=False, scale=False):
        """
        Stack one "negative" offset group per requested channel above the ctrl,
        live connected to the inverse of the ctrl channel (counter animation).
        rotate uses the reversed rotate order.
        """

        if not cmds.objExists(self.name):
            cmds.error(f"{self.name} n'existe pas")

        # ---------------------------------------------------
        # BASE OFFSET
        # ---------------------------------------------------
        parent = cmds.listRelatives(self.name, parent=True)

        current_parent = parent[0] if parent else None

        top_offset = None
        last_offset = None

        # ---------------------------------------------------
        # SCALE OFFSET
        # ---------------------------------------------------
        if scale:

            neg_scale_offset = f"{self.name}_neg_scale_offset"
            if not cmds.objExists(neg_scale_offset):
                neg_scale_offset = cmds.group(empty=True, name=neg_scale_offset)
                cmds.matchTransform(neg_scale_offset, self.name, position=True, rotation=True)
                if current_parent:
                    cmds.parent(neg_scale_offset, current_parent)

            top_offset = neg_scale_offset
            last_offset = neg_scale_offset
            invert_md = cmds.createNode("multiplyDivide", name=f"{self.name}_scale_invert_MD")
            scale_md = cmds.createNode("multiplyDivide", name=f"{self.name}_scale_neg_MD")
            cmds.setAttr(f"{invert_md}.operation", 2)

            for axis in "XYZ":
                cmds.connectAttr(f"{self.name}.scale{axis}", f"{invert_md}.input2{axis}", force=True)
                cmds.setAttr(f"{invert_md}.input1{axis}", 1)
                cmds.connectAttr(f"{invert_md}.output{axis}", f"{scale_md}.input1{axis}", force=True)
                cmds.setAttr(f"{scale_md}.input2{axis}", 1)
                cmds.connectAttr(f"{scale_md}.output{axis}", f"{neg_scale_offset}.scale{axis}", force=True)

        # ---------------------------------------------------
        # ROTATE OFFSET
        # ---------------------------------------------------
        if rotate:

            rotate_orders = {
                0: 5,
                1: 4,
                2: 3,
                3: 2,
                4: 1,
                5: 0
            }

            self.name_ro = cmds.getAttr(f"{self.name}.rotateOrder")
            neg_ro = rotate_orders[self.name_ro]
            neg_rotate_offset = f"{self.name}_neg_rotate_offset"

            if not cmds.objExists(neg_rotate_offset):
                neg_rotate_offset = cmds.group(empty=True, name=neg_rotate_offset)
                cmds.matchTransform(neg_rotate_offset, self.name, position=True, rotation=True)

                if last_offset:
                    cmds.parent(neg_rotate_offset, last_offset)

                elif current_parent:
                    cmds.parent(neg_rotate_offset, current_parent)

            cmds.setAttr(f"{neg_rotate_offset}.rotateOrder", neg_ro)

            if not top_offset:
                top_offset = neg_rotate_offset

            last_offset = neg_rotate_offset
            md_r = cmds.createNode("multiplyDivide", name=f"{self.name}_rotate_neg_MD")

            for axis in "XYZ":
                cmds.connectAttr(f"{self.name}.rotate{axis}", f"{md_r}.input1{axis}", force=True)
                cmds.setAttr(f"{md_r}.input2{axis}", -1)
                cmds.connectAttr(f"{md_r}.output{axis}", f"{neg_rotate_offset}.rotate{axis}", force=True)

        # ---------------------------------------------------
        # TRANSLATE OFFSET
        # ---------------------------------------------------

        if translate:
            neg_translate_offset = f"{self.name}_neg_translate_offset"

            if not cmds.objExists(neg_translate_offset):
                neg_translate_offset = cmds.group(empty=True, name=neg_translate_offset)
                cmds.matchTransform(neg_translate_offset, self.name, position=True, rotation=True)

                if last_offset:
                    cmds.parent(neg_translate_offset, last_offset)

                elif current_parent:
                    cmds.parent(neg_translate_offset, current_parent)

            if not top_offset:
                top_offset = neg_translate_offset

            cmds.parent(self.name, neg_translate_offset)
            translate_md = cmds.createNode("multiplyDivide", name=f"{self.name}_translate_neg_MD")

            for axis in "XYZ":
                cmds.connectAttr(f"{self.name}.translate{axis}", f"{translate_md}.input1{axis}", force=True)
                cmds.setAttr(f"{translate_md}.input2{axis}", -1)
                cmds.connectAttr(f"{translate_md}.output{axis}", f"{neg_translate_offset}.translate{axis}", force=True)

        return top_offset

    # ----------------------------------------
    # RESET
    # ----------------------------------------

    def reset(self):
        """Reset the keyable / channel box attributes to their default (locked ones skipped)."""

        if not cmds.objExists(self.name):
            cmds.warning(f"{self.name} n'existe pas.")
            return self

        attrs = cmds.listAttr(self.name, keyable=True) or []
        attrs += cmds.listAttr(self.name, channelBox=True) or []

        for attr in set(attrs):

            full_attr = f"{self.name}.{attr}"

            if not cmds.objExists(full_attr) or cmds.getAttr(full_attr, lock=True):
                continue

            default = cmds.attributeQuery(attr, node=self.name, listDefault=True)

            if default:
                cmds.setAttr(full_attr, default[0])

        return self

    # ----------------------------------------
    # MIRROR
    # ----------------------------------------

    def mirror(self):

        """
        Mirror the ctrl and its offset group from the L_ / R_ prefix: duplicate
        the first '..._offset' above it, rename the descendants, negate
        scaleX / translateX / rotateY.

        Returns (offset_mirror, ctrl_mirror), or None (no ctrl, no L_ / R_,
        no offset group, mirror already there).
        """

        if not cmds.objExists(self.name):
            return None

        if self.name.startswith("L_"):
            search, replace = "L_", "R_"
        elif self.name.startswith("R_"):
            search, replace = "R_", "L_"
        else:
            return None

        parents = cmds.listRelatives(self.name, parent=True)

        if not parents:
            return None

        offset = parents[0]

        while offset and not offset.endswith("_offset"):

            parents = cmds.listRelatives(offset, parent=True)

            if not parents:
                return None

            offset = parents[0]

        ctrl_mirror = self.name.replace(search, replace)
        offset_mirror = offset.replace(search, replace)

        if cmds.objExists(ctrl_mirror) or cmds.objExists(offset_mirror):
            return None

        offset_mirror = cmds.duplicate(offset, name=offset_mirror)[0]

        for child in cmds.listRelatives(offset_mirror, allDescendents=True, fullPath=True) or []:

            short_name = child.split("|")[-1]
            new_name = short_name.replace(search, replace)

            if new_name != short_name:
                cmds.rename(child, new_name)

        scale_x = cmds.getAttr(f"{offset}.scaleX")
        translate_x = cmds.getAttr(f"{offset}.translateX")
        rotate_y = cmds.getAttr(f"{offset}.rotateY")

        cmds.setAttr(f"{offset_mirror}.scaleX", -scale_x)
        cmds.setAttr(f"{offset_mirror}.translateX", -translate_x)
        cmds.setAttr(f"{offset_mirror}.rotateY", -rotate_y)

        return offset_mirror, ctrl_mirror

    # ----------------------------------------
    # LOCK LIMIT ATTRIBUTE
    # ----------------------------------------

    def add_lock_limit_attr(self):

        """'lockLimit' bool driving every existing min / max ...LimitEnable: one switch for all the ctrl limits."""

        if not cmds.objExists(self.name):
            cmds.warning(f"{self.name} n'existe pas.")
            return None

        if not cmds.attributeQuery("lockLimit", node=self.name, exists=True):
            cmds.addAttr(self.name, longName="lockLimit", attributeType="bool", defaultValue=1, keyable=True)

        for attr in LIMIT_ENABLE_ATTRS:

            destination = f"{self.name}.{attr}"

            if cmds.objExists(destination):
                try:
                    cmds.connectAttr(f"{self.name}.lockLimit", destination, force=True)
                except RuntimeError:
                    continue

        return f"{self.name}.lockLimit"

    # ----------------------------------------
    # SHAPE
    # ----------------------------------------

    def set_shape(self, shape, size=None):

        """
        (Re)build the ctrl shapes from SHAPES[shape] (curves with points and degree).

        size : point scale, or None to keep self.size.
        """

        if not cmds.objExists(self.name):
            cmds.warning(f"{self.name} n'existe pas.")
            return None

        if shape not in SHAPES:
            cmds.warning(f"Shape inconnue : '{shape}'.")
            return None

        size = size if size is not None else self.size

        self.delete_shapes()

        new_shapes = []

        for index, curve_data in enumerate(SHAPES[shape]):

            degree = curve_data.get("degree", 1)
            points = [
                [axis * size for axis in point]
                for point in curve_data["points"]
            ]

            curve = cmds.curve(point=points, degree=degree, name=f"{self.name}_shape_{index}_temp")
            curve_shape = cmds.listRelatives(curve, shapes=True)[0]

            cmds.parent(curve_shape, self.name, shape=True, relative=True)
            cmds.delete(curve)

            new_shapes.append(curve_shape)

        self.shape = shape
        self.size = size

        if self.color is not None:
            self.set_color(self.color)

        return new_shapes

    def set_shape_from(self, source):

        """Replace the ctrl shapes with a copy of the shapes of 'source' (keeps the ctrl color)."""

        if not cmds.objExists(self.name) or not cmds.objExists(source):
            cmds.warning("Ctrl ou source introuvable.")
            return None

        source_shapes = cmds.listRelatives(source, shapes=True, fullPath=True)

        if not source_shapes:
            cmds.warning(f"{source} n'a pas de shape.")
            return None

        self.delete_shapes()

        new_shapes = []

        for shape in source_shapes:

            duplicate = cmds.duplicate(shape, returnRootsOnly=True)[0]
            duplicate_shape = cmds.listRelatives(duplicate, shapes=True, fullPath=True)[0]

            cmds.parent(duplicate_shape, self.name, shape=True, relative=True)
            cmds.delete(duplicate)

            new_shapes.append(duplicate_shape)

        self.shape = None

        if self.color is not None:
            self.set_color(self.color)

        return new_shapes

    def delete_shapes(self):
        """Delete every ctrl shape."""

        shapes = self.get_shapes()

        if shapes:
            cmds.delete(*shapes)

    def get_shapes(self):
        """Ctrl shapes (curves), or [] if the ctrl does not exist."""

        if not cmds.objExists(self.name):
            return []

        return cmds.listRelatives(self.name, shapes=True, fullPath=True) or []

    # ----------------------------------------
    # COLOR
    # ----------------------------------------

    def set_color(self, color):

        """Color the ctrl shapes: override index (0-31) or RGB (0-1)."""

        self.color = color

        for shape in self.get_shapes():

            cmds.setAttr(f"{shape}.overrideEnabled", True)

            if isinstance(color, (tuple, list)):
                cmds.setAttr(f"{shape}.overrideRGBColors", True)
                cmds.setAttr(f"{shape}.overrideColorRGB", *color)
            else:
                cmds.setAttr(f"{shape}.overrideRGBColors", False)
                cmds.setAttr(f"{shape}.overrideColor", color)

        return self.get_shapes()

    # ----------------------------------------
    # LINE WIDTH
    # ----------------------------------------

    def set_line_width(self, width):

        """Display line width of the ctrl shapes (-1 = Maya default)."""

        for shape in self.get_shapes():

            if cmds.objExists(f"{shape}.lineWidth"):
                cmds.setAttr(f"{shape}.lineWidth", width)

        return self.get_shapes()

    # ----------------------------------------
    # SHAPE TRANSFORM
    # ----------------------------------------

    def transform_shape(self, translate=(0, 0, 0), rotate=(0, 0, 0), scale=1.0, pivot=(0, 0, 0)):

        """
        Transform ONLY the ctrl shapes (CVs), not the ctrl transform.

        translate : local offset.
        rotate    : degrees (XYZ).
        scale     : scalar or (sx, sy, sz).
        pivot     : local rotate / scale center.
        """

        translate = self._as_vector3(translate, 0.0)
        rotate = self._as_vector3(rotate, 0.0)
        scale = self._as_vector3(scale, 1.0)
        pivot = self._as_vector3(pivot, 0.0)

        rotation = _rotation_matrix(*rotate)

        for shape in self.get_shapes():

            points = _get_cv_positions(shape)

            if not points:
                continue

            _set_cv_positions(
                shape,
                [_transform_point(point, translate, rotation, scale, pivot) for point in points],
            )

        return self.get_shapes()

    def translate_shape(self, translate):
        """Offset the ctrl CVs (transform_shape shortcut)."""
        return self.transform_shape(translate=translate)

    def rotate_shape(self, rotate, pivot=(0, 0, 0)):
        """Rotate the ctrl CVs (degrees, XYZ) around 'pivot' (transform_shape shortcut)."""
        return self.transform_shape(rotate=rotate, pivot=pivot)

    def scale_shape(self, scale, pivot=(0, 0, 0)):
        """Scale the ctrl CVs around 'pivot' (transform_shape shortcut)."""
        return self.transform_shape(scale=scale, pivot=pivot)

    @staticmethod
    def _as_vector3(value, default):
        """'value' as (x, y, z): a scalar on the 3 axes, a 3 item list as is, else 'default' x 3."""

        if isinstance(value, (int, float)):
            return (float(value), float(value), float(value))

        if isinstance(value, (list, tuple)) and len(value) == 3:
            return tuple(float(component) for component in value)

        return (default, default, default)