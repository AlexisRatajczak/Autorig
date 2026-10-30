# ====================================================================================================================
# RIBBON UTILITIES
# ====================================================================================================================
#
#   MODULE
#       lerp_polyline(points, t)                - point at length ratio t (0..1) of a polyline
#       create_follicle(surface, u, v, name)    - follicle on a NURBS surface at (u, v)
#   RIBBON
#       BUILD          __init__, prefix, build, create_follicles, create_bind_joints, create_drivers,
#                      skin_surface
#       CHAIN          joint_position, get_node_axes, get_joint_chain_axes
#       CURVES / LOFT  create_curve_from_joints, create_offset_curves, create_ribbon_curves,
#                      create_ribbon_from_curves, create_surface_from_joints, create_surface_from_chain
#       DEGREE / SPANS get_degree_for_count, parse_degree, get_max_control_count, rebuild_degree,
#                      get_isoparms, insert_isoparms, subdivide_spans, get_closest_parameter,
#                      insert_isoparms_at_points, pinch_knots
#       EXACT NURBS    elevate_curve_degree, uniformize_curve_knots, read_surface, map_surface_curves,
#                      replace_surface_shape, elevate_surface_degree
#       UV RANGE       get_surface_shape, get_uv_range, is_normalized_uv_range, normalize_uv_range,
#                      remap_uv_range_in_place, to_surface_parameters
#       SURFACE FRAME  get_isoparm_length, get_longest_direction, resolve_direction, get_surface_uv,
#                      get_surface_matrix, build_oriented_matrix, orthonormal_frame
#       LEVELS         parent_keep_inherits, parent_once, create_level_surfaces, get_top_surface,
#                      get_level_base_surface, create_follicles_along
#
# ====================================================================================================================

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om

from . import joint_utilities
from . import skinCluster_utilities

from importlib import reload

reload(joint_utilities)
reload(skinCluster_utilities)


# ==========================================================
# MODULE
# ==========================================================

def lerp_polyline(points, t):
    """Position [x, y, z] at length ratio 't' (0..1) along 'points'."""

    if not points:
        return [0.0, 0.0, 0.0]

    if len(points) == 1 or t <= 0.0:
        return list(points[0])

    if t >= 1.0:
        return list(points[-1])

    lengths = [
        sum((points[i + 1][k] - points[i][k]) ** 2 for k in range(3)) ** 0.5
        for i in range(len(points) - 1)
    ]

    total = sum(lengths)

    if total == 0.0:
        return list(points[0])

    target = t * total
    accumulated = 0.0

    for i, length in enumerate(lengths):

        if accumulated + length >= target:
            local = (target - accumulated) / length if length else 0.0
            a, b = points[i], points[i + 1]
            return [a[k] + (b[k] - a[k]) * local for k in range(3)]

        accumulated += length

    return list(points[-1])


def create_follicle(surface, u, v, name):
    """Follicle on 'surface' at (u, v), on its visible shape. Returns its transform."""

    follicle_shape = cmds.createNode("follicle")
    follicle = cmds.rename(cmds.listRelatives(follicle_shape, parent=True)[0], name)
    follicle_shape = cmds.listRelatives(follicle, shapes=True)[0]

    # Visible shape (never the Orig): the follicle follows the deformed surface.
    surface_shape = (
        cmds.listRelatives(surface, shapes=True, noIntermediate=True, fullPath=True)
        or cmds.listRelatives(surface, shapes=True, fullPath=True)
    )[0]

    cmds.connectAttr(f"{surface_shape}.local", f"{follicle_shape}.inputSurface", force=True)
    cmds.connectAttr(f"{surface_shape}.worldMatrix[0]", f"{follicle_shape}.inputWorldMatrix", force=True)
    cmds.connectAttr(f"{follicle_shape}.outTranslate", f"{follicle}.translate", force=True)
    cmds.connectAttr(f"{follicle_shape}.outRotate", f"{follicle}.rotate", force=True)

    cmds.setAttr(f"{follicle_shape}.parameterU", u)
    cmds.setAttr(f"{follicle_shape}.parameterV", v)

    return follicle


# ==========================================================
# RIBBON
# ==========================================================

class Ribbon:

    # Degrees accepted by rebuildSurface.
    VALID_DEGREES = (1, 2, 3, 5, 7)

    # Minimal curve offset, as a fraction of the chain length.
    MIN_OFFSET_FACTOR = 0.05

    # Max span doublings in rebuild_degree.
    MAX_SUBDIVISIONS = 8

    def __init__(
        self,
        side,
        baseName,
        positions,
        index=0,
        width=2.0,
        bind_count=5,
        driver_count=3,
        surface=None,
        linear=True,
        offset_direction="Z"):
        """
        Ribbon settings, nothing is created (see build).

        positions        : [x, y, z] positions or joints, 2 or more.
        width            : ribbon width.
        bind_count       : follicles / bind joints (min 2).
        driver_count     : driver joints deforming the surface (min 2).
        surface          : existing NURBS surface, or None to build it.
        linear           : linear or smooth ribbon curves.
        offset_direction : width axis, "Y" or "Z" (create_offset_curves).
        """

        self.side = side[0]
        self.baseName = baseName
        self.positions = [list(Ribbon.joint_position(p)) for p in positions]
        self.index = index
        self.width = max(0.01, float(width))
        self.bind_count = max(2, int(bind_count))
        self.driver_count = max(2, int(driver_count))
        self.linear = bool(linear)
        self.offset_direction = str(offset_direction).upper()

        self.surface = surface
        self.follicle_group = None
        self.follicles = []
        self.bind_joints = []
        self.drivers = []
        self.skin_cluster = None

    @property
    def prefix(self):
        """Naming prefix: {side}_{baseName}_{index:02d}."""
        return f"{self.side}_{self.baseName}_{self.index:02d}"

    # --------------------------------------------------
    # BUILD
    # --------------------------------------------------

    def build(self, parent=None):
        """Surface (built if needed), follicles, bind joints, drivers, then skin."""

        if len(self.positions) < 2:
            cmds.warning("Ribbon : au moins 2 positions sont nécessaires.")
            return self

        if self.surface is None:
            _, _, _, distance = Ribbon.get_joint_chain_axes(self.positions)
            factor = self.width / (2.0 * distance)
            self.create_surface_from_joints(self.positions, factor=factor, linear=self.linear, parent=parent)

        elif not cmds.objExists(self.surface):
            cmds.warning(f"Ribbon : surface '{self.surface}' introuvable.")
            return self

        self.create_follicles(parent=parent)
        self.create_bind_joints()
        self.create_drivers(parent=parent)
        self.skin_surface()

        return self

    def create_follicles(self, parent=None):
        """bind_count follicles spread in U (V = 0.5), under a dedicated group."""

        if not self.surface or not cmds.objExists(self.surface):
            return []

        self.follicle_group = cmds.group(empty=True, name=f"{self.prefix}_follicles_grp")

        if parent and cmds.objExists(parent):
            self.follicle_group = cmds.parent(self.follicle_group, parent)[0]

        self.follicles = []

        for i in range(self.bind_count):
            follicle = create_follicle(self.surface, i / (self.bind_count - 1), 0.5, f"{self.prefix}_bind_{i:02d}_fol")
            self.follicles.append(cmds.parent(follicle, self.follicle_group)[0])

        return self.follicles

    def create_bind_joints(self, suffix="bind"):
        """A zeroed Joint (joint_utilities) under each follicle."""

        self.bind_joints = []

        for i, follicle in enumerate(self.follicles):

            joint = joint_utilities.Joint(
                {
                    "baseName": self.baseName,
                    "side": self.side,
                    "parent": follicle,
                    "index": i,
                    "guide": None,
                },
                suffix=suffix,
            )
            joint.create_joint()

            cmds.setAttr(f"{joint.name}.translate", 0, 0, 0)
            cmds.setAttr(f"{joint.name}.rotate", 0, 0, 0)

            self.bind_joints.append(joint)

        return self.bind_joints

    def create_drivers(self, parent=None, suffix="ribbon_drv"):
        """driver_count hidden driver joints along the positions (they deform the surface)."""

        self.drivers = []

        for i in range(self.driver_count):

            position = lerp_polyline(self.positions, i / (self.driver_count - 1))

            driver = cmds.createNode("joint", name=f"{self.side}_{self.baseName}_{i:02d}_{suffix}")
            cmds.xform(driver, worldSpace=True, translation=position)
            cmds.setAttr(f"{driver}.drawStyle", 2)

            if parent and cmds.objExists(parent):
                driver = cmds.parent(driver, parent)[0]

            self.drivers.append(driver)

        return self.drivers

    def skin_surface(self, maximumInfluences=2, dropoffRate=2.0):
        """Skin the surface to the driver joints."""

        if not self.surface or not self.drivers:
            return None

        self.skin_cluster = skinCluster_utilities.bind_skin(
            self.drivers,
            self.surface,
            name=f"{self.prefix}_ribbon_skin",
            max_influences=maximumInfluences,
            dropoffRate=dropoffRate,
        )

        return self.skin_cluster

    # --------------------------------------------------
    # CHAIN
    # --------------------------------------------------

    @staticmethod
    def joint_position(joint):
        """World position (MVector) of a joint, or a [x, y, z] position as is."""

        if isinstance(joint, (list, tuple, om.MVector)):
            return om.MVector(joint[0], joint[1], joint[2])

        name = getattr(joint, "name", joint)

        return om.MVector(cmds.xform(name, query=True, worldSpace=True, translation=True))

    @staticmethod
    def get_node_axes(node):
        """Normalized world X, Y, Z axes (MVector) of 'node'."""

        matrix = cmds.xform(getattr(node, "name", node), query=True, worldSpace=True, matrix=True)

        return tuple(om.MVector(matrix[i * 4], matrix[i * 4 + 1], matrix[i * 4 + 2]).normal() for i in range(3))

    @staticmethod
    def get_joint_chain_axes(joints, reference=None, tolerance=1e-3):
        """
        Chain frame: X = first -> last, Y = perpendicular towards the 2nd joint,
        Z = X ^ Y, d = first -> last length. Straight chain or 2 joints: Y from the
        'reference' (or first joint) orientation, then the world axis least aligned
        with X. Returns (X, Y, Z, d).
        """

        if len(joints) < 2:
            raise ValueError("Ribbon.get_joint_chain_axes : au moins 2 joints sont nécessaires.")

        first = Ribbon.joint_position(joints[0])
        last = Ribbon.joint_position(joints[-1])

        first_last = last - first
        distance = first_last.length()

        if distance < 1e-6:
            raise ValueError("Ribbon.get_joint_chain_axes : le premier et le dernier joint sont confondus.")

        x_axis = first_last.normal()

        y_axis = om.MVector()

        if len(joints) > 2:
            second = Ribbon.joint_position(joints[1])
            y_axis = second - (first + x_axis * ((second - first) * x_axis))

        # Fallback 1: first guide orientation.
        if y_axis.length() < tolerance * distance:

            if reference is None and not isinstance(joints[0], (list, tuple, om.MVector)):
                reference = joints[0]

            if reference is not None and cmds.objExists(getattr(reference, "name", reference)):

                for candidate in Ribbon.get_node_axes(reference)[1:]:

                    y_axis = candidate - x_axis * (candidate * x_axis)

                    if y_axis.length() >= tolerance:
                        break

        # Fallback 2: world axis least aligned with X.
        if y_axis.length() < tolerance:
            world_axes = (om.MVector(1, 0, 0), om.MVector(0, 1, 0), om.MVector(0, 0, 1))
            world_reference = min(world_axes, key=lambda axis: abs(axis * x_axis))
            y_axis = world_reference - x_axis * (world_reference * x_axis)

        y_axis.normalize()

        return x_axis, y_axis, (x_axis ^ y_axis).normal(), distance

    # --------------------------------------------------
    # CURVES / LOFT
    # --------------------------------------------------

    @staticmethod
    def create_curve_from_joints(joints, name="curve", degree=3, linear=False):
        """Curve through the joints (edit points), linear or of degree 'degree'."""

        if len(joints) < 2:
            cmds.warning("Ribbon.create_curve_from_joints : au moins 2 joints sont nécessaires.")
            return None

        points = [list(Ribbon.joint_position(joint)) for joint in joints]

        degree = 1 if linear else max(1, min(int(degree), len(points) - 1))

        return cmds.curve(editPoint=points, degree=degree, name=name)

    @staticmethod
    def create_offset_curves(curve, joints, factor=0.1, name=None, direction="Z", reference=None, reverse=False):
        """
        Duplicate 'curve' and offset the CVs: original by +axis * d * factor, copy
        by -axis * d * factor (min MIN_OFFSET_FACTOR * d).
        direction : "Z" (ribbon in the chain plane) or "Y".
        reverse   : opposite way, surface normal flipped.
        Returns (curve, copy).
        """

        direction = str(direction).upper()

        if direction not in ("Y", "Z"):
            raise ValueError(f"Ribbon.create_offset_curves : direction '{direction}' invalide (attendu 'Y' ou 'Z').")

        _, y_axis, z_axis, distance = Ribbon.get_joint_chain_axes(joints, reference=reference)

        axis = y_axis if direction == "Y" else z_axis

        if reverse:
            axis = -axis

        offset = axis * (distance * max(float(factor), Ribbon.MIN_OFFSET_FACTOR))

        duplicate = cmds.duplicate(curve, name=name or f"{curve}_neg")[0]

        cmds.move(offset.x, offset.y, offset.z, f"{curve}.cv[*]", relative=True, worldSpace=True)
        cmds.move(-offset.x, -offset.y, -offset.z, f"{duplicate}.cv[*]", relative=True, worldSpace=True)

        return curve, duplicate

    def create_ribbon_curves(self, joints, factor=0.1, linear=None, direction=None, reference=None, reverse=False, name=None):
        """
        Curve '{name}_crv' through the joints and its offset copy '{name}_neg_crv'
        (name: '{prefix}_ribbon' by default). Returns (curve_pos, curve_neg).
        """

        linear = self.linear if linear is None else linear
        direction = self.offset_direction if direction is None else direction
        name = name or f"{self.prefix}_ribbon"

        curve = self.create_curve_from_joints(joints, name=f"{name}_crv", degree=3, linear=linear)

        return self.create_offset_curves(
            curve,
            joints,
            factor=factor,
            name=f"{name}_neg_crv",
            direction=direction,
            reference=reference,
            reverse=reverse
        )

    @staticmethod
    def create_ribbon_from_curves(curve_a, curve_b, name=None, delete_curves=True, uniform=False):
        """
        Loft between two curves (no history), curves deleted with 'delete_curves'.
        uniform : uniform isoparms, else from the curves.
        """

        for curve in (curve_a, curve_b):
            if not curve or not cmds.objExists(curve):
                cmds.warning(f"Ribbon.create_ribbon_from_curves : '{curve}' n'existe pas.")
                return None

        surface = cmds.loft(
            curve_a, curve_b,
            uniform=bool(uniform),
            ch=0,
            c=0,
            ar=1,
            d=3,
            ss=1,
            rn=0,
            po=0,
            rsn=True,
            name=name or f"{curve_a}_srf"
        )[0]

        if delete_curves:
            cmds.delete(curve_a, curve_b)

        return surface

    def create_surface_from_joints(self, joints, factor=0.1, linear=None, parent=None, direction=None, reference=None, reverse=False, uniform=False, name=None):
        """
        Surface '{name}_srf' (name: '{prefix}_ribbon' by default): loft between two
        offset curves through 'joints' (width 2 * factor * d), inheritsTransform
        off. Updates self.positions and self.surface.
        """

        linear = self.linear if linear is None else linear
        name = name or f"{self.prefix}_ribbon"

        self.positions = [list(self.joint_position(joint)) for joint in joints]

        curve_pos, curve_neg = self.create_ribbon_curves(
            joints, factor=factor, linear=linear, direction=direction, reference=reference, reverse=reverse, name=name
        )

        surface = self.create_ribbon_from_curves(curve_pos, curve_neg, name=f"{name}_srf", uniform=uniform)

        if not surface:
            return None

        if parent and cmds.objExists(parent):
            surface = cmds.parent(surface, parent)[0]

        # After parenting (else 'Turning on inheritTransform' warning).
        cmds.setAttr(f"{surface}.inheritsTransform", 0)

        self.surface = surface

        return self.surface

    def create_surface_from_chain(
        self,
        joints,
        width=2.0,
        parent=None,
        reference=None,
        uniform=True,
        control_count=3,
        direction=None,
        pinch_offset=0.0,
        degree=None,
        subdivide=True,
        name=None
    ):
        """
        Ribbon module surface on the 'joints' chain: create_surface_from_joints
        (total width 'width', name '{name}_srf'), then rebuild_degree in 'direction'
        (None / 'Auto' = longest): degree, subdivision if 'subdivide', pinch;
        frozen, no history. Returns the surface.

        Main nurb  : degree=3, subdivide=False, pinch.
        Level nurb : degree / subdivision from its ctrls, no pinch.
        """

        _, _, _, distance = Ribbon.get_joint_chain_axes(joints, reference=reference)

        surface = self.create_surface_from_joints(
            joints,
            factor=float(width) / (2.0 * distance),
            parent=parent,
            reference=reference,
            uniform=bool(uniform),
            name=name
        )

        if not surface:
            raise RuntimeError(f"Ribbon '{self.prefix}' : la surface n'a pas pu être créée.")

        cmds.delete(surface, constructionHistory=True)

        Ribbon.rebuild_degree(
            surface,
            control_count,
            direction=Ribbon.resolve_direction(surface, direction),
            pinch_offset=max(0.0, float(pinch_offset or 0.0)),
            degree=degree,
            subdivide=subdivide
        )

        # The freeze turns inheritsTransform back on (warning): on during the freeze, off again after.
        cmds.setAttr(f"{surface}.inheritsTransform", 1)
        cmds.makeIdentity(surface, apply=True, translate=True, rotate=True, scale=True, normal=0)
        cmds.setAttr(f"{surface}.inheritsTransform", 0)

        cmds.delete(surface, constructionHistory=True)

        self.surface = surface

        return surface

    # --------------------------------------------------
    # DEGREE / SPANS
    # --------------------------------------------------

    @staticmethod
    def get_degree_for_count(control_count):
        """Degree from the ctrl count: 2 -> 1, 3 -> 2, 4-5 -> 3, 6-7 -> 5, 8+ -> 7."""

        target = max(1, int(control_count) - 1)

        return max(degree for degree in Ribbon.VALID_DEGREES if degree <= target)

    @staticmethod
    def parse_degree(value):
        """Degree of an 'Auto:1:2:3:5:7' enum: the int, or None for 'Auto'."""

        value = str(value or "Auto")

        return int(value) if value.isdigit() else None

    @staticmethod
    def get_max_control_count(counts, default=5):
        """Largest ctrl count of 'counts' (min 2), 'default' if empty."""

        counts = [max(2, int(count)) for count in counts]

        return max(counts) if counts else max(2, int(default))

    @staticmethod
    def rebuild_degree(surface, control_count, direction="U", match_surface=None, pinch_offset=0.0, degree=None, subdivide=True):
        """
        Prepare 'surface' in 'direction' without changing its shape:

        1. degree 'degree' (None = get_degree_for_count) by exact elevation
           (with 'match_surface': matched knots, approximate shape);
        2. if 'subdivide', spans doubled up to control_count - 1; then U and V in
           0..1 with uniform isoparms (normalize_uv_range);
        3. pinch around the step 1 isoparms if pinch_offset > 0.

        Returns the surface.
        """

        direction = str(direction).upper()

        if direction not in ("U", "V"):
            raise ValueError(f"Ribbon.rebuild_degree : direction '{direction}' invalide (attendu 'U' ou 'V').")

        # 1. Degree.
        if match_surface:
            cmds.rebuildSurface(
                surface,
                match_surface,
                constructionHistory=False,
                replaceOriginal=True,
                rebuildType=2,
                direction=2
            )
        else:
            degree = int(degree) if degree else Ribbon.get_degree_for_count(control_count)
            Ribbon.elevate_surface_degree(surface, degree, direction)

        original_isoparms = Ribbon.get_isoparms(surface, direction)

        # 2. Subdivision (MAX_SUBDIVISIONS at most, stops when nothing is inserted).
        minimum_spans = int(control_count) - 1

        for _ in range(Ribbon.MAX_SUBDIVISIONS if subdivide else 0):

            spans = len(Ribbon.get_isoparms(surface, direction)) - 1

            if spans >= minimum_spans:
                break

            Ribbon.subdivide_spans(surface, direction)

            if len(Ribbon.get_isoparms(surface, direction)) - 1 <= spans:
                cmds.warning(f"Ribbon.rebuild_degree : impossible de subdiviser '{surface}' en {direction}.")
                break

        # Normalization: the original isoparms are tracked by rank.
        before = Ribbon.get_isoparms(surface, direction)

        Ribbon.normalize_uv_range(surface)

        after = Ribbon.get_isoparms(surface, direction)

        if len(after) == len(before):
            original_isoparms = [
                after[min(range(len(before)), key=lambda i: abs(before[i] - parameter))]
                for parameter in original_isoparms
            ]

        # 3. Pinch.
        if float(pinch_offset or 0.0) > 0.0 and len(original_isoparms) >= 3:
            Ribbon.pinch_knots(surface, direction, original_isoparms, offset=pinch_offset)

        return surface

    @staticmethod
    def get_isoparms(surface, direction="U", precision=6):
        """Sorted isoparm parameters (unique knots, ends included) in 'direction'."""

        axis = "U" if str(direction).upper() == "U" else "V"

        shape = (cmds.listRelatives(surface, shapes=True, noIntermediate=True, fullPath=True) or [surface])[0]

        info = cmds.createNode("surfaceInfo", name="ribbon_isoparms_surfaceInfo_temp")

        try:
            cmds.connectAttr(f"{shape}.worldSpace[0]", f"{info}.inputSurface", force=True)
            knots = cmds.getAttr(f"{info}.knots{axis}")[0] or []
        finally:
            cmds.delete(info)

        minimum, maximum = cmds.getAttr(f"{shape}.minMaxRange{axis}")[0]

        return sorted({
            round(knot, precision)
            for knot in knots
            if minimum - 1e-6 <= knot <= maximum + 1e-6
        })

    @staticmethod
    def insert_isoparms(surface, direction, parameters, tolerance=1e-4):
        """Insert an isoparm at each new interior parameter. Returns the inserted isoparms."""

        axis = "u" if str(direction).upper() == "U" else "v"

        existing = Ribbon.get_isoparms(surface, direction)

        if len(existing) < 2:
            return []

        minimum, maximum = existing[0], existing[-1]

        wanted = []

        for parameter in sorted(set(parameters)):

            if parameter <= minimum + tolerance or parameter >= maximum - tolerance:
                continue

            if any(abs(parameter - knot) < tolerance for knot in existing + wanted):
                continue

            wanted.append(parameter)

        if not wanted:
            return []

        cmds.insertKnotSurface(
            [f"{surface}.{axis}[{parameter}]" for parameter in wanted],
            numberOfKnots=1,
            addKnots=True,
            insertBetween=False,
            constructionHistory=False,
            replaceOriginal=True
        )

        after = Ribbon.get_isoparms(surface, direction)

        return [knot for knot in after if all(abs(knot - old) >= tolerance for old in existing)]

    @staticmethod
    def subdivide_spans(surface, direction="U"):
        """Double the spans: an isoparm in the middle of each span. Returns the inserted isoparms."""

        isoparms = Ribbon.get_isoparms(surface, direction)

        return Ribbon.insert_isoparms(surface, direction, [(a + b) * 0.5 for a, b in zip(isoparms[:-1], isoparms[1:])])

    @staticmethod
    def get_closest_parameter(surface, position, direction="U"):
        """Parameter in 'direction' of the 'surface' point closest to the world 'position'."""

        shape = (cmds.listRelatives(surface, shapes=True, noIntermediate=True, fullPath=True) or [surface])[0]

        closest = cmds.createNode("closestPointOnSurface", name="ribbon_closestPoint_temp")

        try:
            cmds.connectAttr(f"{shape}.worldSpace[0]", f"{closest}.inputSurface", force=True)
            cmds.setAttr(f"{closest}.inPosition", *position)
            axis = "U" if str(direction).upper() == "U" else "V"
            return cmds.getAttr(f"{closest}.parameter{axis}")
        finally:
            cmds.delete(closest)

    @staticmethod
    def insert_isoparms_at_points(surface, direction, positions):
        """
        Insert an isoparm in 'direction' closest to each world position (exact;
        ends and duplicates skipped). Returns the inserted isoparms.
        """

        parameters = [Ribbon.get_closest_parameter(surface, position, direction) for position in positions]

        return Ribbon.insert_isoparms(surface, direction, parameters)

    @staticmethod
    def pinch_knots(surface, direction, isoparms, offset=0.01):
        """
        Insert two knots at p - offset and p + offset around each interior isoparm p
        (offset capped at 49% of the neighbour span): the surface bends there.
        Returns the inserted parameters.
        """

        offset = float(offset or 0.0)

        isoparms = list(isoparms)

        if offset <= 0.0 or len(isoparms) < 3:
            return []

        parameters = []

        for index in range(1, len(isoparms) - 1):

            parameter = isoparms[index]

            gap = min(parameter - isoparms[index - 1], isoparms[index + 1] - parameter)
            pinch = min(offset, gap * 0.49)

            parameters.extend([parameter - pinch, parameter + pinch])

        # Like by hand: select the isoparms, then insertKnotSurface ('d': 1 = U, 0 = V).
        # No history (the surface has none: avoids 'History will be off for the command').
        axis = "u" if str(direction).upper() == "U" else "v"

        previous_selection = cmds.ls(selection=True) or []

        try:
            cmds.select(clear=True)

            for parameter in parameters:
                cmds.select(f"{surface}.{axis}[{parameter}]", add=True)

            cmds.insertKnotSurface(ch=False, nk=1, add=1, ib=0, rpo=1, d=1 if axis == "u" else 0, p=parameters)

        finally:
            if previous_selection:
                cmds.select(previous_selection, replace=True)
            else:
                cmds.select(clear=True)

        return parameters

    # --------------------------------------------------
    # EXACT NURBS (shape kept)
    # --------------------------------------------------

    @staticmethod
    def elevate_curve_degree(degree, knots, points, times):
        """
        Exact degree elevation of a non rational B-spline (The NURBS Book, A5.9):
        same curve, degree 'degree' + 'times'.
        knots : full vector (len(points) + degree + 1), points : tuples.
        Returns (knots, points).
        """

        def add(a, b):
            return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

        def mul(s, a):
            return (s * a[0], s * a[1], s * a[2])

        def blend(alpha, a, b):
            return add(mul(alpha, a), mul(1.0 - alpha, b))

        p, t = int(degree), int(times)
        U, P = list(knots), list(points)
        n = len(P) - 1
        m = n + p + 1
        ph = p + t
        ph2 = ph // 2

        # Degree elevation coefficients of a Bezier segment.
        bezalfs = [[0.0] * (p + 1) for _ in range(ph + 1)]
        bezalfs[0][0] = bezalfs[ph][p] = 1.0

        for i in range(1, ph2 + 1):
            inverse = 1.0 / math.comb(ph, i)
            for j in range(max(0, i - t), min(p, i) + 1):
                bezalfs[i][j] = inverse * math.comb(p, j) * math.comb(t, i - j)

        for i in range(ph2 + 1, ph):
            for j in range(max(0, i - t), min(p, i) + 1):
                bezalfs[i][j] = bezalfs[ph - i][p - j]

        size = (n + 1) * (t + 1) + ph + 2

        Q = [None] * size
        Uh = [0.0] * (size + ph + 1)

        mh = ph
        kind = ph + 1
        r = -1
        a = p
        b = p + 1
        cind = 1
        ua = U[0]

        Q[0] = P[0]

        for i in range(ph + 1):
            Uh[i] = ua

        bpts = [P[i] for i in range(p + 1)]
        next_bpts = [None] * max(1, p - 1)
        ebpts = [None] * (ph + 1)

        while b < m:

            i = b

            while b < m and U[b] == U[b + 1]:
                b += 1

            mul_b = b - i + 1
            mh += mul_b + t
            ub = U[b]
            oldr = r
            r = p - mul_b

            lbz = (oldr + 2) // 2 if oldr > 0 else 1
            rbz = ph - (r + 1) // 2 if r > 0 else ph

            # Knot insertion: Bezier segment [ua, ub].
            if r > 0:

                numer = ub - ua
                alfs = [0.0] * (p - 1)

                for k in range(p, mul_b, -1):
                    alfs[k - mul_b - 1] = numer / (U[a + k] - ua)

                for j in range(1, r + 1):

                    save = r - j
                    s = mul_b + j

                    for k in range(p, s - 1, -1):
                        bpts[k] = blend(alfs[k - s], bpts[k], bpts[k - 1])

                    next_bpts[save] = bpts[p]

            # Segment elevation.
            for i in range(lbz, ph + 1):

                point = (0.0, 0.0, 0.0)

                for j in range(max(0, i - t), min(p, i) + 1):
                    point = add(point, mul(bezalfs[i][j], bpts[j]))

                ebpts[i] = point

            # Remove the knots added to the previous segment.
            if oldr > 1:

                first = kind - 2
                last = kind
                den = ub - ua
                bet = (ub - Uh[kind - 1]) / den

                for tr in range(1, oldr):

                    i = first
                    j = last
                    kj = j - kind + 1

                    while j - i > tr:

                        if i < cind:
                            alf = (ub - Uh[i]) / (ua - Uh[i])
                            Q[i] = blend(alf, Q[i], Q[i - 1])

                        if j >= lbz:
                            if j - tr <= kind - ph + oldr:
                                gam = (ub - Uh[j - tr]) / den
                                ebpts[kj] = blend(gam, ebpts[kj], ebpts[kj + 1])
                            else:
                                ebpts[kj] = blend(bet, ebpts[kj], ebpts[kj + 1])

                        i += 1
                        j -= 1
                        kj -= 1

                    first -= 1
                    last += 1

            if a != p:
                for i in range(ph - oldr):
                    Uh[kind] = ua
                    kind += 1

            for j in range(lbz, rbz + 1):
                Q[cind] = ebpts[j]
                cind += 1

            if b < m:

                for j in range(r):
                    bpts[j] = next_bpts[j]

                for j in range(r, p + 1):
                    bpts[j] = P[b - p + j]

                a = b
                b += 1
                ua = ub

            else:
                for i in range(ph + 1):
                    Uh[kind + i] = ub

        nh = mh - ph - 1

        return Uh[:nh + ph + 2], Q[:nh + 1]

    @staticmethod
    def uniformize_curve_knots(degree, knots, points, tolerance=1e-9):
        """
        Isoparms at i / spans (1 isoparm -> 0.5, 2 -> 1/3 and 2/3...) without
        changing the shape: each interior knot is inserted up to multiplicity
        'degree' (Bezier segments), then renumbered. More CVs, may crease at the
        isoparms once deformed. Returns (knots, points).
        """

        p = int(degree)
        U = list(knots)
        P = list(points)

        def multiplicity(u):
            return sum(1 for value in U if abs(value - u) <= tolerance)

        interior = []

        for value in U[p + 1:len(U) - p - 1]:
            if not interior or value - interior[-1] > tolerance:
                interior.append(value)

        # Bezier decomposition (Boehm insertion).
        for u in interior:

            while multiplicity(u) < p:

                s = multiplicity(u)
                n = len(P) - 1
                k = max(i for i in range(n + 1) if U[i] <= u + tolerance)

                Q = []

                for i in range(n + 2):

                    if i <= k - p:
                        Q.append(P[i])

                    elif i <= k - s:
                        alpha = (u - U[i]) / (U[i + p] - U[i])
                        Q.append(tuple(alpha * P[i][c] + (1.0 - alpha) * P[i - 1][c] for c in range(3)))

                    else:
                        Q.append(P[i - 1])

                U.insert(k + 1, u)
                P = Q

        # Distinct knots -> rank / spans.
        distinct = []

        for value in U:
            if not distinct or value - distinct[-1] > tolerance:
                distinct.append(value)

        spans = max(1, len(distinct) - 1)

        uniform = [
            min(range(len(distinct)), key=lambda i: abs(distinct[i] - value)) / float(spans)
            for value in U
        ]

        return uniform, P

    @staticmethod
    def read_surface(surface):
        """
        Shape data of 'surface': dict path, fn, degree_u / v, knots_u / v (full
        vectors), grid[iu][iv] (tuples), cvs, periodic, rational.
        """

        selection = om.MSelectionList()
        selection.add(Ribbon.get_surface_shape(surface))

        path = selection.getDagPath(0)
        surface_fn = om.MFnNurbsSurface(path)

        count_u, count_v = surface_fn.numCVsInU, surface_fn.numCVsInV

        cvs = surface_fn.cvPositions(om.MSpace.kObject)

        # Maya omits the first and last knots of the full vector.
        def full(knots):
            knots = list(knots)
            return [knots[0]] + knots + [knots[-1]]

        return {
            "path": path,
            "fn": surface_fn,
            "degree_u": surface_fn.degreeInU,
            "degree_v": surface_fn.degreeInV,
            "knots_u": full(surface_fn.knotsInU()),
            "knots_v": full(surface_fn.knotsInV()),
            # CVs ordered U then V: cvs[iu * count_v + iv].
            "grid": [[(cvs[iu * count_v + iv].x, cvs[iu * count_v + iv].y, cvs[iu * count_v + iv].z)
                      for iv in range(count_v)] for iu in range(count_u)],
            "cvs": cvs,
            "periodic": om.MFnNurbsSurface.kPeriodic in (surface_fn.formInU, surface_fn.formInV),
            "rational": any(abs(point.w - 1.0) > 1e-9 for point in cvs),
        }

    @staticmethod
    def map_surface_curves(grid, direction, function):
        """Apply function(points) -> (knots, points) to each CV curve of 'grid' in 'direction'. Returns (knots, grid)."""

        if str(direction).upper() == "U":

            count_v = len(grid[0])
            columns = []

            for iv in range(count_v):
                knots, column = function([row[iv] for row in grid])
                columns.append(column)

            return knots, [[columns[iv][iu] for iv in range(count_v)] for iu in range(len(columns[0]))]

        rows = []

        for row in grid:
            knots, new_row = function(row)
            rows.append(new_row)

        return knots, rows

    @staticmethod
    def replace_surface_shape(shape_path, grid, knots_u, knots_v, degree_u, degree_v):
        """
        Replace 'shape_path' with an open non rational shape (same name, same
        transform). Full knot vectors. The old shape connections are lost.
        Returns the new shape.
        """

        shape_name = shape_path.partialPathName().split("|")[-1]

        new_shape = om.MFnNurbsSurface().create(
            om.MPointArray([om.MPoint(*point) for row in grid for point in row]),
            om.MDoubleArray(list(knots_u)[1:-1]),
            om.MDoubleArray(list(knots_v)[1:-1]),
            degree_u,
            degree_v,
            om.MFnNurbsSurface.kOpen,
            om.MFnNurbsSurface.kOpen,
            False,
            shape_path.transform()
        )

        new_shape_name = om.MFnDagNode(new_shape).fullPathName()

        cmds.delete(shape_path.fullPathName())
        new_shape_name = cmds.rename(new_shape_name, shape_name)

        try:
            cmds.sets(new_shape_name, edit=True, forceElement="initialShadingGroup")
        except RuntimeError:
            pass

        return new_shape_name

    @staticmethod
    def elevate_surface_degree(surface, degree, direction="U"):
        """
        Raise 'surface' to 'degree' in 'direction' without changing its shape
        (elevate_curve_degree on each CV curve). Lower degree, periodic or rational
        surface: degree kept (warning). Returns the final degree.
        """

        direction = str(direction).upper()

        data = Ribbon.read_surface(surface)

        key = "degree_u" if direction == "U" else "degree_v"
        current = data[key]
        target = int(degree)

        if target == current:
            return current

        if target < current:
            cmds.warning(
                f"Ribbon.elevate_surface_degree : '{surface}' est en degré {current} en {direction}, "
                f"le passer en degré {target} changerait sa forme : degré conservé."
            )
            return current

        if data["periodic"] or data["rational"]:
            cmds.warning(f"Ribbon.elevate_surface_degree : '{surface}' est périodique ou rationnelle : degré conservé.")
            return current

        knots_key = "knots_u" if direction == "U" else "knots_v"

        knots, grid = Ribbon.map_surface_curves(
            data["grid"],
            direction,
            lambda points: Ribbon.elevate_curve_degree(current, data[knots_key], points, target - current)
        )

        data[knots_key] = knots
        data[key] = target

        Ribbon.replace_surface_shape(data["path"], grid, data["knots_u"], data["knots_v"], data["degree_u"], data["degree_v"])

        return target

    # --------------------------------------------------
    # UV RANGE
    # --------------------------------------------------

    @staticmethod
    def get_surface_shape(surface):
        """Non intermediate shape of 'surface'."""

        return (cmds.listRelatives(surface, shapes=True, noIntermediate=True) or [surface])[0]

    @staticmethod
    def get_uv_range(surface):
        """(u_min, u_max, v_min, v_max) of 'surface'."""

        shape = Ribbon.get_surface_shape(surface)

        u_min, u_max = cmds.getAttr(f"{shape}.minMaxRangeU")[0]
        v_min, v_max = cmds.getAttr(f"{shape}.minMaxRangeV")[0]

        return u_min, u_max, v_min, v_max

    @staticmethod
    def is_normalized_uv_range(surface, tolerance=1e-6):
        """True if U and V of 'surface' go from 0 to 1."""

        u_min, u_max, v_min, v_max = Ribbon.get_uv_range(surface)

        return all(
            abs(value - target) < tolerance
            for value, target in ((u_min, 0.0), (u_max, 1.0), (v_min, 0.0), (v_max, 1.0))
        )

    @staticmethod
    def normalize_uv_range(surface):
        """
        U and V in 0..1 with uniform isoparms (1 -> 0.5, 2 -> 1/3 and 2/3...), shape
        kept (uniformize_curve_knots), shape node rebuilt. Connected, periodic or
        rational surface: remap_uv_range_in_place. Returns True if in 0..1.
        """

        data = Ribbon.read_surface(surface)

        connected = cmds.listConnections(data["path"].fullPathName(), source=True, destination=False)

        if data["periodic"] or data["rational"] or connected:
            return Ribbon.remap_uv_range_in_place(surface)

        knots_u, grid = Ribbon.map_surface_curves(
            data["grid"], "U", lambda points: Ribbon.uniformize_curve_knots(data["degree_u"], data["knots_u"], points)
        )

        knots_v, grid = Ribbon.map_surface_curves(
            grid, "V", lambda points: Ribbon.uniformize_curve_knots(data["degree_v"], data["knots_v"], points)
        )

        Ribbon.replace_surface_shape(data["path"], grid, knots_u, knots_v, data["degree_u"], data["degree_v"])

        if not Ribbon.is_normalized_uv_range(surface):
            u_min, u_max, v_min, v_max = Ribbon.get_uv_range(surface)
            cmds.warning(
                f"Ribbon.normalize_uv_range : '{surface}' n'est pas en 0..1 "
                f"(U {u_min:g}..{u_max:g}, V {v_min:g}..{v_max:g})."
            )
            return False

        return True

    @staticmethod
    def remap_uv_range_in_place(surface):
        """
        Knots linearly remapped to 0..1 in place (connections kept, non uniform
        isoparms). Returns True if the surface is in 0..1.
        """

        if Ribbon.is_normalized_uv_range(surface):
            return True

        u_min, u_max, v_min, v_max = Ribbon.get_uv_range(surface)

        def remap(knots, low, high):
            span = (high - low) or 1.0
            return om.MDoubleArray([(knot - low) / span for knot in knots])

        try:
            selection = om.MSelectionList()
            selection.add(Ribbon.get_surface_shape(surface))
            surface_fn = om.MFnNurbsSurface(selection.getDagPath(0))

            knots_u = remap(surface_fn.knotsInU(), u_min, u_max)
            knots_v = remap(surface_fn.knotsInV(), v_min, v_max)

            surface_fn.setKnotsInU(knots_u, 0, len(knots_u) - 1)
            surface_fn.setKnotsInV(knots_v, 0, len(knots_v) - 1)
            surface_fn.updateSurface()

        except (RuntimeError, ValueError) as error:
            cmds.warning(
                f"Ribbon.remap_uv_range_in_place : impossible de reparamétrer '{surface}' en 0..1 ({error}). "
                "Les paramètres sont convertis vers sa plage réelle (to_surface_parameters)."
            )
            return False

        cmds.warning(
            f"Ribbon.normalize_uv_range : '{surface}' est connectée, périodique ou rationnelle : "
            "remise en 0..1 sans isoparms uniformes."
        )

        return Ribbon.is_normalized_uv_range(surface)

    @staticmethod
    def to_surface_parameters(surface, u, v):
        """(u, v) in 0..1 -> real parameters of 'surface'."""

        u_min, u_max, v_min, v_max = Ribbon.get_uv_range(surface)

        return u_min + u * (u_max - u_min), v_min + v * (v_max - v_min)

    # --------------------------------------------------
    # SURFACE FRAME
    # --------------------------------------------------

    @staticmethod
    def get_isoparm_length(surface, direction, samples=20):
        """Approximate length of 'surface' in 'direction', at the middle of the other."""

        points = []

        for i in range(samples + 1):
            u, v = Ribbon.get_surface_uv(direction, i / samples)
            points.append(om.MVector(cmds.pointOnSurface(surface, u=u, v=v, turnOnPercentage=True, position=True)))

        return sum((points[i + 1] - points[i]).length() for i in range(samples))

    @staticmethod
    def get_longest_direction(surface):
        """"U" or "V": the longest direction."""

        return "U" if Ribbon.get_isoparm_length(surface, "U") >= Ribbon.get_isoparm_length(surface, "V") else "V"

    @staticmethod
    def resolve_direction(surface, direction=None):
        """'direction' if "U" or "V", else ('Auto' / None) the longest."""

        direction = str(direction or "Auto").upper()

        return direction if direction in ("U", "V") else Ribbon.get_longest_direction(surface)

    @staticmethod
    def get_surface_uv(direction, t):
        """(u, v) ratios: 't' along 'direction', 0.5 in the other."""

        return (t, 0.5) if direction == "U" else (0.5, t)

    @staticmethod
    def get_surface_matrix(surface, t, direction="U", aim_vector=(1.0, 0.0, 0.0), up_vector=(0.0, 0.0, 1.0)):
        """World matrix at 't' along 'direction': aim on the tangent, up on the normal."""

        u, v = Ribbon.get_surface_uv(direction, t)

        kwargs = {"u": u, "v": v, "turnOnPercentage": True}

        tangent_flag = "normalizedTangentU" if direction == "U" else "normalizedTangentV"

        position = om.MVector(cmds.pointOnSurface(surface, position=True, **kwargs))
        tangent = om.MVector(cmds.pointOnSurface(surface, **{tangent_flag: True}, **kwargs))
        normal = om.MVector(cmds.pointOnSurface(surface, normalizedNormal=True, **kwargs))

        return Ribbon.build_oriented_matrix(position, tangent, normal, aim_vector, up_vector)

    @staticmethod
    def build_oriented_matrix(position, aim_world, up_world, aim_local=(1.0, 0.0, 0.0), up_local=(0.0, 0.0, 1.0)):
        """World matrix (16 values): 'aim_local' on 'aim_world', 'up_local' on 'up_world', at 'position'."""

        aim_local, up_local, third_local = Ribbon.orthonormal_frame(aim_local, up_local)
        aim_world, up_world, third_world = Ribbon.orthonormal_frame(aim_world, up_world)

        # M = L^-1 * W (L orthonormal: L^-1 = L transposed).
        local = om.MMatrix([
            aim_local.x, aim_local.y, aim_local.z, 0.0,
            up_local.x, up_local.y, up_local.z, 0.0,
            third_local.x, third_local.y, third_local.z, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ])

        world = om.MMatrix([
            aim_world.x, aim_world.y, aim_world.z, 0.0,
            up_world.x, up_world.y, up_world.z, 0.0,
            third_world.x, third_world.y, third_world.z, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ])

        values = list(local.transpose() * world)
        values[12:15] = [position.x, position.y, position.z]

        return values

    @staticmethod
    def orthonormal_frame(aim, up):
        """Orthonormal (aim, up, aim ^ up); 'up' parallel to 'aim': world axis least aligned."""

        aim = om.MVector(aim).normal()
        up = om.MVector(up)

        up = up - aim * (up * aim)

        if up.length() < 1e-6:
            axes = (om.MVector(1, 0, 0), om.MVector(0, 1, 0), om.MVector(0, 0, 1))
            reference = min(axes, key=lambda axis: abs(axis * aim))
            up = reference - aim * (reference * aim)

        up.normalize()

        return aim, up, (aim ^ up).normal()

    # --------------------------------------------------
    # LEVELS
    # --------------------------------------------------

    @staticmethod
    def parent_keep_inherits(node, parent):

        """
        cmds.parent(node, parent) without the 'Turning on inheritTransform' warning:
        a node without inheritance is parented with it on, then off again.
        Returns the node name after parenting.
        """

        inherits = cmds.getAttr(f"{node}.inheritsTransform")

        if not inherits:
            cmds.setAttr(f"{node}.inheritsTransform", 1)

        node = cmds.parent(node, parent)[0]

        if not inherits:
            cmds.setAttr(f"{node}.inheritsTransform", 0)

        return node

    @staticmethod
    def parent_once(node, parent):
        """Parent 'node' under 'parent' unless already there (parent_keep_inherits). Returns its name."""

        if not parent or not cmds.objExists(parent):
            return node

        if (cmds.listRelatives(node, parent=True) or [None])[0] == parent:
            return node

        return Ribbon.parent_keep_inherits(node, parent)

    @staticmethod
    def create_level_surfaces(surface, level_count, prefix, parent=None):
        """One hidden copy of 'surface' per level ('{prefix}_lvl{N}_srf'), no intermediate shape."""

        level_surfaces = []

        for level in range(1, int(level_count) + 1):

            copy = cmds.duplicate(surface, name=f"{prefix}_lvl{level}_srf")[0]

            for shape in cmds.listRelatives(copy, shapes=True, fullPath=True) or []:
                if cmds.getAttr(f"{shape}.intermediateObject"):
                    cmds.delete(shape)

            cmds.setAttr(f"{copy}.inheritsTransform", 0)
            cmds.setAttr(f"{copy}.visibility", 0)

            level_surfaces.append(Ribbon.parent_once(copy, parent))

        return level_surfaces

    @staticmethod
    def get_top_surface(surface, level_surfaces):
        """Top surface of the stack: the last level, else 'surface'."""

        return level_surfaces[-1] if level_surfaces else surface

    @staticmethod
    def get_level_base_surface(surface, level_surfaces, level):
        """Surface the 'level' ctrls ride: the one below ('surface' for level 1)."""

        return surface if level <= 1 else level_surfaces[level - 2]

    @staticmethod
    def create_follicles_along(surface, count, direction, prefix, parent=None):
        """'count' follicles from 0 to 1 along 'direction' (0.5 in the other). Returns (group, follicles)."""

        count = max(2, int(count))

        group = cmds.group(empty=True, name=f"{prefix}_follicles_grp")
        cmds.setAttr(f"{group}.inheritsTransform", 0)

        group = Ribbon.parent_once(group, parent)

        follicles = []

        for i in range(count):

            u, v = Ribbon.to_surface_parameters(surface, *Ribbon.get_surface_uv(direction, i / (count - 1)))

            follicle = create_follicle(surface, u, v, f"{prefix}_{i:02d}_fol")

            follicles.append(cmds.parent(follicle, group)[0])

        return group, follicles
