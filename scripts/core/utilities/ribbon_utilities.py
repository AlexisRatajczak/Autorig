# ====================================================================================================================
# RIBBON UTILITIES
# ====================================================================================================================
#
# MODULE
#   lerp_polyline(points, t)                  - point à l'abscisse t (0..1) d'une polyligne
#   create_follicle(surface, u, v, name)      - follicule sur une surface NURBS en (u, v)
#
# RIBBON
#   BUILD          __init__, prefix, build, create_follicles, create_bind_joints, create_drivers,
#                  skin_surface
#   CHAIN          joint_position, get_node_axes, get_joint_chain_axes
#   CURVES / LOFT  create_curve_from_joints, create_offset_curves, create_ribbon_curves,
#                  create_ribbon_from_curves, create_surface_from_joints, create_surface_from_chain
#   DEGREE / SPANS get_degree_for_count, parse_degree, get_max_control_count, rebuild_degree,
#                  get_isoparms, insert_isoparms, subdivide_spans, get_closest_parameter,
#                  insert_isoparms_at_points, pinch_knots
#   EXACT NURBS    elevate_curve_degree, uniformize_curve_knots, read_surface, map_surface_curves,
#                  replace_surface_shape, elevate_surface_degree
#   UV RANGE       get_surface_shape, get_uv_range, is_normalized_uv_range, normalize_uv_range,
#                  remap_uv_range_in_place, to_surface_parameters
#   SURFACE FRAME  get_isoparm_length, get_longest_direction, resolve_direction, get_surface_uv,
#                  get_surface_matrix, build_oriented_matrix, orthonormal_frame
#   LEVELS         parent_keep_inherits, parent_once, create_level_surfaces, get_top_surface,
#                  get_level_base_surface,
#                  create_follicles_along
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
    """Position [x, y, z] à l'abscisse curviligne 't' (0..1) le long de 'points'."""

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
    """Follicule accroché à 'surface' en (u, v), sur sa shape visible. Retourne son transform."""

    follicle_shape = cmds.createNode("follicle")
    follicle = cmds.rename(cmds.listRelatives(follicle_shape, parent=True)[0], name)
    follicle_shape = cmds.listRelatives(follicle, shapes=True)[0]

    # Shape visible (jamais l'Orig) : le follicule suit la surface déformée.
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

    # Degrés acceptés par rebuildSurface.
    VALID_DEGREES = (1, 2, 3, 5, 7)

    # Décalage minimal des curves, en fraction de la longueur de la chaîne.
    MIN_OFFSET_FACTOR = 0.05

    # Nombre maximal de doublements des spans dans rebuild_degree.
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
        Paramètres du ruban, rien n'est créé (voir build).

        positions        : positions [x, y, z] ou joints, au moins 2.
        width            : largeur du ruban.
        bind_count       : follicules / bind joints (min 2).
        driver_count     : joints driver qui déforment la surface (min 2).
        surface          : surface NURBS existante, ou None pour la créer.
        linear           : curves du ruban linéaires ou lissées.
        offset_direction : axe de la largeur, "Y" ou "Z" (create_offset_curves).
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
        """Préfixe de nommage : {side}_{baseName}_{index:02d}."""
        return f"{self.side}_{self.baseName}_{self.index:02d}"

    # --------------------------------------------------
    # BUILD
    # --------------------------------------------------

    def build(self, parent=None):
        """Surface (créée si besoin), follicules, bind joints, drivers, puis skin."""

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
        """bind_count follicules répartis en U (V = 0.5), sous un groupe dédié."""

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
        """Un Joint (joint_utilities) à zéro sous chaque follicule."""

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
        """driver_count joints driver cachés, répartis le long des positions (ils déforment la surface)."""

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
        """Skinne la surface aux joints driver."""

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
        """Position monde (MVector) d'un joint, ou position [x, y, z] retournée telle quelle."""

        if isinstance(joint, (list, tuple, om.MVector)):
            return om.MVector(joint[0], joint[1], joint[2])

        name = getattr(joint, "name", joint)

        return om.MVector(cmds.xform(name, query=True, worldSpace=True, translation=True))

    @staticmethod
    def get_node_axes(node):
        """Axes monde X, Y, Z normalisés (MVector) de 'node'."""

        matrix = cmds.xform(getattr(node, "name", node), query=True, worldSpace=True, matrix=True)

        return tuple(om.MVector(matrix[i * 4], matrix[i * 4 + 1], matrix[i * 4 + 2]).normal() for i in range(3))

    @staticmethod
    def get_joint_chain_axes(joints, reference=None, tolerance=1e-3):
        """
        Repère de la chaîne : X = premier -> dernier, Y = perpendiculaire vers
        le 2e joint, Z = X ^ Y, d = longueur premier -> dernier.
        Chaîne droite ou 2 joints : Y vient de l'orientation de 'reference'
        (ou du premier joint), puis de l'axe monde le moins aligné avec X.
        Retourne (X, Y, Z, d).
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

        # Repli 1 : orientation du premier guide.
        if y_axis.length() < tolerance * distance:

            if reference is None and not isinstance(joints[0], (list, tuple, om.MVector)):
                reference = joints[0]

            if reference is not None and cmds.objExists(getattr(reference, "name", reference)):

                for candidate in Ribbon.get_node_axes(reference)[1:]:

                    y_axis = candidate - x_axis * (candidate * x_axis)

                    if y_axis.length() >= tolerance:
                        break

        # Repli 2 : axe monde le moins aligné avec X.
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
        """Curve qui passe par les joints (edit points), linéaire ou de degré 'degree'."""

        if len(joints) < 2:
            cmds.warning("Ribbon.create_curve_from_joints : au moins 2 joints sont nécessaires.")
            return None

        points = [list(Ribbon.joint_position(joint)) for joint in joints]

        degree = 1 if linear else max(1, min(int(degree), len(points) - 1))

        return cmds.curve(editPoint=points, degree=degree, name=name)

    @staticmethod
    def create_offset_curves(curve, joints, factor=0.1, name=None, direction="Z", reference=None, reverse=False):
        """
        Duplique 'curve' et décale les CVs : l'original de +axe * d * factor,
        la copie de -axe * d * factor (minimum MIN_OFFSET_FACTOR * d).
        direction : "Z" (ruban dans le plan de la chaîne) ou "Y".
        reverse   : sens opposé, normale de la surface inversée.
        Retourne (curve, copie).
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
        Curve '{name}_crv' par les joints et sa copie décalée '{name}_neg_crv'
        (name : '{prefix}_ribbon' par défaut). Retourne (curve_pos, curve_neg).
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
        Loft entre deux curves (sans historique), curves supprimées si
        'delete_curves'. uniform : isoparms uniformes, sinon selon les curves.
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
        Surface '{name}_srf' (name : '{prefix}_ribbon' par défaut) : loft
        entre deux curves décalées qui passent par 'joints' (largeur
        2 * factor * d). inheritsTransform désactivé. Met à jour
        self.positions et self.surface.
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

        # Après le parentage (sinon warning 'Turning on inheritTransform').
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
        Surface du module ribbon sur la chaîne 'joints' :
        create_surface_from_joints (largeur totale 'width', nom '{name}_srf'),
        puis rebuild_degree dans 'direction' (None / 'Auto' = la plus
        longue) - degré, subdivision si 'subdivide', pincement -, freeze,
        sans historique. Retourne la surface.

        Main nurb : degree=3, subdivide=False, pincement.
        Nurb de niveau : degré / subdivision selon ses ctrls, sans pincement.
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

        # Le freeze remet inheritsTransform à 1 (warning 'Turning on
        # inheritTransform') : réactivé, puis désactivé à nouveau après.
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
        """Degré selon le nombre de ctrls : 2 -> 1, 3 -> 2, 4-5 -> 3, 6-7 -> 5, 8+ -> 7."""

        target = max(1, int(control_count) - 1)

        return max(degree for degree in Ribbon.VALID_DEGREES if degree <= target)

    @staticmethod
    def parse_degree(value):
        """Degré d'un enum 'Auto:1:2:3:5:7' : l'entier, ou None en 'Auto'."""

        value = str(value or "Auto")

        return int(value) if value.isdigit() else None

    @staticmethod
    def get_max_control_count(counts, default=5):
        """Plus grand nombre de ctrls de 'counts' (min 2), 'default' si vide."""

        counts = [max(2, int(count)) for count in counts]

        return max(counts) if counts else max(2, int(default))

    @staticmethod
    def rebuild_degree(surface, control_count, direction="U", match_surface=None, pinch_offset=0.0, degree=None, subdivide=True):
        """
        Prépare 'surface' dans 'direction', sans changer sa forme :

        1. degré 'degree' (None = get_degree_for_count) par élévation exacte
           (avec 'match_surface' : knots matchés, forme approchée) ;
        2. si 'subdivide', spans doublés jusqu'à control_count - 1 ; puis U
           et V en 0..1 avec des isoparms uniformes (normalize_uv_range) ;
        3. pincement autour des isoparms de l'étape 1 si pinch_offset > 0.

        Retourne la surface.
        """

        direction = str(direction).upper()

        if direction not in ("U", "V"):
            raise ValueError(f"Ribbon.rebuild_degree : direction '{direction}' invalide (attendu 'U' ou 'V').")

        # 1. Degré.
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

        # 2. Subdivision (MAX_SUBDIVISIONS au plus, arrêt si rien n'est inséré).
        minimum_spans = int(control_count) - 1

        for _ in range(Ribbon.MAX_SUBDIVISIONS if subdivide else 0):

            spans = len(Ribbon.get_isoparms(surface, direction)) - 1

            if spans >= minimum_spans:
                break

            Ribbon.subdivide_spans(surface, direction)

            if len(Ribbon.get_isoparms(surface, direction)) - 1 <= spans:
                cmds.warning(f"Ribbon.rebuild_degree : impossible de subdiviser '{surface}' en {direction}.")
                break

        # Normalisation : les isoparms d'origine sont suivis par leur rang.
        before = Ribbon.get_isoparms(surface, direction)

        Ribbon.normalize_uv_range(surface)

        after = Ribbon.get_isoparms(surface, direction)

        if len(after) == len(before):
            original_isoparms = [
                after[min(range(len(before)), key=lambda i: abs(before[i] - parameter))]
                for parameter in original_isoparms
            ]

        # 3. Pincement.
        if float(pinch_offset or 0.0) > 0.0 and len(original_isoparms) >= 3:
            Ribbon.pinch_knots(surface, direction, original_isoparms, offset=pinch_offset)

        return surface

    @staticmethod
    def get_isoparms(surface, direction="U", precision=6):
        """Paramètres triés des isoparms (knots uniques, bornes comprises) dans 'direction'."""

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
        """Insère un isoparm à chaque paramètre nouveau et intérieur. Retourne les isoparms ajoutés."""

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
        """Double les spans : un isoparm au milieu de chaque span. Retourne les isoparms ajoutés."""

        isoparms = Ribbon.get_isoparms(surface, direction)

        return Ribbon.insert_isoparms(surface, direction, [(a + b) * 0.5 for a, b in zip(isoparms[:-1], isoparms[1:])])

    @staticmethod
    def get_closest_parameter(surface, position, direction="U"):
        """Paramètre, dans 'direction', du point de 'surface' le plus proche de 'position' (monde)."""

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
        Insère un isoparm dans 'direction' au plus près de chaque position
        monde de 'positions' (insert_isoparms : exact, bornes et doublons
        ignorés). Retourne les isoparms ajoutés.
        """

        parameters = [Ribbon.get_closest_parameter(surface, position, direction) for position in positions]

        return Ribbon.insert_isoparms(surface, direction, parameters)

    @staticmethod
    def pinch_knots(surface, direction, isoparms, offset=0.01):
        """
        Insère deux knots à p - offset et p + offset autour de chaque isoparm
        intérieur p (offset limité à 49% du span voisin) : la surface s'y plie.
        Retourne les paramètres insérés.
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

        # Comme à la main : sélection des isoparms, puis insertKnotSurface
        # ('d' : 1 = U, 0 = V). Sans historique : la surface n'en a pas
        # (sinon warning 'History will be off for the command').
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
    # EXACT NURBS (forme conservée)
    # --------------------------------------------------

    @staticmethod
    def elevate_curve_degree(degree, knots, points, times):
        """
        Élévation de degré exacte d'une B-spline non rationnelle (The NURBS
        Book, A5.9) : même courbe, degré 'degree' + 'times'.
        knots : vecteur complet (len(points) + degree + 1), points : tuples.
        Retourne (knots, points).
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

        # Coefficients d'élévation d'un segment de Bézier.
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

            # Insertion de knots : segment de Bézier [ua, ub].
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

            # Élévation du segment.
            for i in range(lbz, ph + 1):

                point = (0.0, 0.0, 0.0)

                for j in range(max(0, i - t), min(p, i) + 1):
                    point = add(point, mul(bezalfs[i][j], bpts[j]))

                ebpts[i] = point

            # Suppression des knots ajoutés au segment précédent.
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
        Isoparms en i / spans (1 isoparm -> 0.5, 2 -> 1/3 et 2/3...) sans
        changer la forme : chaque knot intérieur est inséré jusqu'à la
        multiplicité 'degree' (segments de Bézier), puis renuméroté.
        Plus de CVs, et pli possible aux isoparms une fois déformée.
        Retourne (knots, points).
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

        # Décomposition en segments de Bézier (insertion de Boehm).
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

        # Knots distincts -> rang / spans.
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
        Données de la shape de 'surface' : dict path, fn, degree_u/v,
        knots_u/v (vecteurs complets), grid[iu][iv] (tuples), cvs, periodic,
        rational.
        """

        selection = om.MSelectionList()
        selection.add(Ribbon.get_surface_shape(surface))

        path = selection.getDagPath(0)
        surface_fn = om.MFnNurbsSurface(path)

        count_u, count_v = surface_fn.numCVsInU, surface_fn.numCVsInV

        cvs = surface_fn.cvPositions(om.MSpace.kObject)

        # Maya omet le premier et le dernier knot du vecteur complet.
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
            # CVs ordonnés U puis V : cvs[iu * count_v + iv].
            "grid": [[(cvs[iu * count_v + iv].x, cvs[iu * count_v + iv].y, cvs[iu * count_v + iv].z)
                      for iv in range(count_v)] for iu in range(count_u)],
            "cvs": cvs,
            "periodic": om.MFnNurbsSurface.kPeriodic in (surface_fn.formInU, surface_fn.formInV),
            "rational": any(abs(point.w - 1.0) > 1e-9 for point in cvs),
        }

    @staticmethod
    def map_surface_curves(grid, direction, function):
        """
        Applique function(points) -> (knots, points) à chaque courbe de CVs
        de 'grid' dans 'direction'. Retourne (knots, grid).
        """

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
        Remplace la shape 'shape_path' par une shape ouverte non rationnelle
        (même nom, même transform). Knots en vecteurs complets. Les connexions
        de l'ancienne shape sont perdues. Retourne la nouvelle shape.
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
        Passe 'surface' au degré 'degree' dans 'direction' sans changer sa
        forme (elevate_curve_degree sur chaque courbe de CVs). Un degré plus
        bas, une surface périodique ou rationnelle : degré conservé (warning).
        Retourne le degré final.
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
        """Shape non intermédiaire de 'surface'."""

        return (cmds.listRelatives(surface, shapes=True, noIntermediate=True) or [surface])[0]

    @staticmethod
    def get_uv_range(surface):
        """(u_min, u_max, v_min, v_max) de 'surface'."""

        shape = Ribbon.get_surface_shape(surface)

        u_min, u_max = cmds.getAttr(f"{shape}.minMaxRangeU")[0]
        v_min, v_max = cmds.getAttr(f"{shape}.minMaxRangeV")[0]

        return u_min, u_max, v_min, v_max

    @staticmethod
    def is_normalized_uv_range(surface, tolerance=1e-6):
        """True si U et V de 'surface' vont de 0 à 1."""

        u_min, u_max, v_min, v_max = Ribbon.get_uv_range(surface)

        return all(
            abs(value - target) < tolerance
            for value, target in ((u_min, 0.0), (u_max, 1.0), (v_min, 0.0), (v_max, 1.0))
        )

    @staticmethod
    def normalize_uv_range(surface):
        """
        U et V en 0..1 avec des isoparms uniformes (1 -> 0.5, 2 -> 1/3 et
        2/3...), forme conservée (uniformize_curve_knots), shape recréée.
        Surface connectée, périodique ou rationnelle : remap_uv_range_in_place.
        Retourne True si la surface est en 0..1.
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
        Knots remappés linéairement en 0..1, en place (connexions gardées,
        isoparms non uniformes). Retourne True si la surface est en 0..1.
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
        """(u, v) en 0..1 -> paramètres réels de 'surface'."""

        u_min, u_max, v_min, v_max = Ribbon.get_uv_range(surface)

        return u_min + u * (u_max - u_min), v_min + v * (v_max - v_min)

    # --------------------------------------------------
    # SURFACE FRAME
    # --------------------------------------------------

    @staticmethod
    def get_isoparm_length(surface, direction, samples=20):
        """Longueur approchée de 'surface' dans 'direction', au milieu de l'autre."""

        points = []

        for i in range(samples + 1):
            u, v = Ribbon.get_surface_uv(direction, i / samples)
            points.append(om.MVector(cmds.pointOnSurface(surface, u=u, v=v, turnOnPercentage=True, position=True)))

        return sum((points[i + 1] - points[i]).length() for i in range(samples))

    @staticmethod
    def get_longest_direction(surface):
        """"U" ou "V" : la plus longue des deux directions."""

        return "U" if Ribbon.get_isoparm_length(surface, "U") >= Ribbon.get_isoparm_length(surface, "V") else "V"

    @staticmethod
    def resolve_direction(surface, direction=None):
        """'direction' si c'est "U" ou "V", sinon ('Auto' / None) la plus longue."""

        direction = str(direction or "Auto").upper()

        return direction if direction in ("U", "V") else Ribbon.get_longest_direction(surface)

    @staticmethod
    def get_surface_uv(direction, t):
        """(u, v) en pourcentage : 't' le long de 'direction', 0.5 dans l'autre."""

        return (t, 0.5) if direction == "U" else (0.5, t)

    @staticmethod
    def get_surface_matrix(surface, t, direction="U", aim_vector=(1.0, 0.0, 0.0), up_vector=(0.0, 0.0, 1.0)):
        """Matrice monde en 't' le long de 'direction' : aim sur la tangente, up sur la normale."""

        u, v = Ribbon.get_surface_uv(direction, t)

        kwargs = {"u": u, "v": v, "turnOnPercentage": True}

        tangent_flag = "normalizedTangentU" if direction == "U" else "normalizedTangentV"

        position = om.MVector(cmds.pointOnSurface(surface, position=True, **kwargs))
        tangent = om.MVector(cmds.pointOnSurface(surface, **{tangent_flag: True}, **kwargs))
        normal = om.MVector(cmds.pointOnSurface(surface, normalizedNormal=True, **kwargs))

        return Ribbon.build_oriented_matrix(position, tangent, normal, aim_vector, up_vector)

    @staticmethod
    def build_oriented_matrix(position, aim_world, up_world, aim_local=(1.0, 0.0, 0.0), up_local=(0.0, 0.0, 1.0)):
        """Matrice monde (16 valeurs) : 'aim_local' sur 'aim_world', 'up_local' sur 'up_world', en 'position'."""

        aim_local, up_local, third_local = Ribbon.orthonormal_frame(aim_local, up_local)
        aim_world, up_world, third_world = Ribbon.orthonormal_frame(aim_world, up_world)

        # M = L^-1 * W (L orthonormé : L^-1 = L transposé).
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
        """(aim, up, aim ^ up) orthonormés ; 'up' parallèle à 'aim' : axe monde le moins aligné."""

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
        cmds.parent(node, parent) sans le warning 'Turning on
        inheritTransform' : un node sans héritage de transform est
        reparenté avec l'héritage activé le temps du parentage, puis
        désactivé à nouveau. Retourne le nom du node après parentage.
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
        """Parente 'node' sous 'parent' s'il n'y est pas déjà (parent_keep_inherits). Retourne son nom."""

        if not parent or not cmds.objExists(parent):
            return node

        if (cmds.listRelatives(node, parent=True) or [None])[0] == parent:
            return node

        return Ribbon.parent_keep_inherits(node, parent)

    @staticmethod
    def create_level_surfaces(surface, level_count, prefix, parent=None):
        """Une copie cachée de 'surface' par niveau ('{prefix}_lvl{N}_srf'), sans shape intermédiaire."""

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
        """Dernière surface de la pile : le dernier niveau, sinon 'surface'."""

        return level_surfaces[-1] if level_surfaces else surface

    @staticmethod
    def get_level_base_surface(surface, level_surfaces, level):
        """Surface d'accroche des ctrls du niveau 'level' : celle du dessous ('surface' au niveau 1)."""

        return surface if level <= 1 else level_surfaces[level - 2]

    @staticmethod
    def create_follicles_along(surface, count, direction, prefix, parent=None):
        """'count' follicules de 0 à 1 le long de 'direction' (0.5 dans l'autre). Retourne (groupe, follicules)."""

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
