# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# API - RIG
# ==========================================================
#
# Façade sur les utilities de rig (joints, ctrls, contraintes de matrix,
# space switch, ruban) : des fonctions simples qui s'appuient sur les
# classes existantes sans les modifier. Partout, un node peut être passé
# par son nom, un Joint ou un Control.
#
#   from api import rig
#
#   jnt = rig.create_joint("L", "arm", index=0, match="L_arm_00_GUIDE")
#   ctrl = rig.create_ctrl("L_arm_00_ctrl", shape="circle", match=jnt)
#   rig.parent_constraint(jnt, ctrl, mo=True, dcmpMtx=False)
#   rig.space_switch(ctrl, [("Local", "CTRL_grp"), ("World", "C_world_ctrl")], attr_host=ctrl)
#
# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# JOINT (joint_utilities)
#   create_joint(side, base_name, index, suffix, parent, match, ...)   - crée un Joint (match + freeze optionnels)
#   get_joint(name)                                                    - Joint pour un joint existant
#   freeze_joint(joint)                                                - bake le transform local dans offsetParentMatrix
#   rename_joint(joint, base_name, side, index, suffix)                - renomme un joint
#   mirror_joint(joint, axis, search_side, replace_side, replace_name) - miroir d'un joint
#   duplicate_chain(root, replace_name)                                - duplique une chaîne de joints
#   replace_joint_shape(joint, ctrl)                                   - copie les shapes d'un ctrl sur un joint
#
# CONTROL (ctrl_utilities)
#   list_ctrl_shapes()                                                 - formes disponibles (shapesCtrl_config.json)
#   create_ctrl(name, shape, size, color, match, parent, ...)          - crée un ctrl (+ offset)
#   get_ctrl(name)                                                     - Control pour un ctrl existant
#   bake_offset(node)                                                  - bake le transform local dans offsetParentMatrix
#   create_neg_offset(ctrl, translate, rotate, scale)                  - offsets inverses (contre-animation)
#   set_ctrl_shape / copy_ctrl_shape / delete_ctrl_shapes              - (re)construit / copie / supprime les shapes
#   set_ctrl_color / set_ctrl_line_width                               - couleur / épaisseur des shapes
#   transform_ctrl_shape(ctrl, translate, rotate, scale, pivot)        - transforme les CV (pas le ctrl)
#   transfer_shape_to_joint(ctrl, joint)                               - shape du ctrl sur un joint, supprime le ctrl
#   reset_ctrl / mirror_ctrl / add_lock_limit_attr                     - reset / miroir L_-R_ / attribut lockLimit
#
# CONTROL - BATCH (tools_facialRig : sélection, sinon tous les '*_ctrl')
#   get_ctrls(ctrls, suffix)                                           - ctrls donnés, sélection, ou '*{suffix}'
#   reset_ctrls / mirror_ctrls / limit_ctrls / neg_offset_ctrls        - reset_ctrl / mirror_ctrl / ... sur plusieurs ctrls
#
# CONSTRAINT (cnstrMtx_utilities)
#   parent_constraint / point_constraint / orient_constraint           - contraintes de matrix
#   aim_constraint(target, drivers, world_up, ...)                     - contrainte aim de matrix
#   pole_vector_constraint(ik_handle, drivers, mo)                     - pole vector de matrix (ikRPsolver)
#   offset_matrix(node, reference)                                     - node.worldMatrix * reference.worldInverseMatrix
#
# SPACE SWITCH (switchSpace_utilities)
#   space_switch(target, spaces, default, attr_name, attr_host, ...)   - switch d'espace (enum, ou blend float)
#
# RIBBON (ribbon_utilities)
#   create_ribbon(side, base_name, positions, ...)                     - Ribbon (construit par défaut)
#   create_ribbon_surface(side, base_name, joints, ...)                - surface de ruban sur une chaîne (degré, pincement)
#   rebuild_ribbon_degree(surface, control_count, ...)                 - degré / isoparms / pincement, forme conservée
#   elevate_surface_degree(surface, degree, direction)                 - élévation de degré exacte
#   normalize_surface_uv(surface)                                      - U / V en 0..1, isoparms uniformes
#   insert_surface_isoparms(surface, direction, parameters)            - isoparms aux paramètres donnés
#   insert_surface_isoparms_at(surface, direction, positions)          - isoparms au plus près de positions monde
#   pinch_surface(surface, direction, isoparms, offset)                - pincement autour d'isoparms
#   surface_matrix(surface, t, direction, aim_vector, up_vector)       - matrice monde le long d'une surface
#   create_follicle(surface, u, v, name)                               - follicule sur une surface NURBS
#   lerp_polyline(points, t)                                           - position à l'abscisse t d'une polyligne

# ====================================================================================================================
# ====================================================================================================================

import maya.cmds as cmds

from core.utilities import joint_utilities
from core.utilities import ctrl_utilities
from core.utilities import cnstrMtx_utilities
from core.utilities import switchSpace_utilities
from core.utilities import ribbon_utilities

from importlib import reload

reload(joint_utilities)
reload(ctrl_utilities)
reload(cnstrMtx_utilities)
reload(switchSpace_utilities)
reload(ribbon_utilities)


__all__ = [
    # joint
    "create_joint", "get_joint", "freeze_joint", "rename_joint", "mirror_joint",
    "duplicate_chain", "replace_joint_shape",
    # control
    "list_ctrl_shapes", "create_ctrl", "get_ctrl", "bake_offset", "create_neg_offset",
    "set_ctrl_shape", "copy_ctrl_shape", "delete_ctrl_shapes", "set_ctrl_color",
    "set_ctrl_line_width", "transform_ctrl_shape", "transfer_shape_to_joint",
    "reset_ctrl", "mirror_ctrl", "add_lock_limit_attr",
    # control - batch
    "get_ctrls", "reset_ctrls", "mirror_ctrls", "limit_ctrls", "neg_offset_ctrls",
    # constraint
    "parent_constraint", "point_constraint", "orient_constraint", "aim_constraint",
    "pole_vector_constraint", "offset_matrix",
    # space switch
    "space_switch",
    # ribbon
    "create_ribbon", "create_follicle", "lerp_polyline", "create_ribbon_surface",
    "rebuild_ribbon_degree", "elevate_surface_degree", "normalize_surface_uv",
    "insert_surface_isoparms", "insert_surface_isoparms_at", "pinch_surface", "surface_matrix",
]


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def _name(node):
    """Nom d'un node, qu'on passe un nom, un Joint ou un Control."""

    return getattr(node, "name", node)


def _names(nodes):
    """Liste de noms (voir _name) : accepte un node seul ou une liste."""

    if isinstance(nodes, (list, tuple)):
        return [_name(node) for node in nodes]

    return [_name(nodes)]


# ==========================================================
# JOINT
# ==========================================================

def create_joint(
    side,
    base_name,
    index=0,
    suffix="jnt",
    parent=None,
    match=None,
    match_rotation=True,
    match_scale=False,
    freeze=True,
    guide=None
):

    """
    Crée un joint '{side}_{base_name}_{index:02d}_{suffix}' (index
    auto-incrémenté s'il est déjà pris) et retourne son Joint.

    parent         : node sous lequel parenter le joint.
    match          : node (ou guide) sur lequel matcher le joint, ou None.
    match_rotation : matcher aussi la rotation de 'match'.
    match_scale    : matcher aussi l'échelle de 'match'.
    freeze         : bake le transform local dans l'offsetParentMatrix
                     (canaux remis à zéro, voir Joint.freeze_transform).
    guide          : guide associé au joint (stocké sur Joint.guide).
    """

    joint = joint_utilities.Joint(
        {
            "baseName": base_name,
            "side": side,
            "parent": _name(parent) if parent else None,
            "index": index,
            "guide": guide
        },
        suffix=suffix
    )
    joint.create_joint()

    if match:
        joint.match_transform(_name(match), matchPos=True, matchRot=match_rotation, matchScale=match_scale)

    if freeze:
        joint.freeze_transform()

    return joint


def get_joint(name):

    """
    Joint (joint_utilities) pour un joint existant '{side}_{baseName}_..._{suffix}',
    pour utiliser ses méthodes (freeze_transform, rename, mirror...).
    """

    name = _name(name)
    parts = name.split("|")[-1].split("_")

    # Index = dernier token numérique (ex: L_arm_00_fk_jnt -> 00, suffixe 'fk_jnt').
    digits = [i for i, part in enumerate(parts) if part.isdigit() and i > 0]
    split = digits[-1] if digits else len(parts) - 1

    joint = joint_utilities.Joint(
        {
            "baseName": "_".join(parts[1:split]) or parts[0],
            "side": parts[0],
            "index": int(parts[split]) if digits else 0
        },
        suffix="_".join(parts[split + 1:]) or parts[-1]
    )
    joint.name = name

    return joint


def _as_joint(joint):
    """Joint tel quel, ou Joint reconstruit depuis un nom (voir get_joint)."""

    return joint if isinstance(joint, joint_utilities.Joint) else get_joint(joint)


def freeze_joint(joint):
    """Bake le transform local du joint dans son offsetParentMatrix (canaux à zéro)."""

    return _as_joint(joint).freeze_transform()


def rename_joint(joint, base_name=None, side=None, index=None, suffix=None):
    """Renomme le joint ({side}_{base_name}_{index:02d}_{suffix}, None = inchangé)."""

    return _as_joint(joint).rename(baseName=base_name, side=side, index=index, suffix=suffix)


def mirror_joint(joint, axis="YZ", search_side="L", replace_side="R", replace_name=None):
    """Duplique le joint en miroir (cmds.mirrorJoint), retourne le Joint créé (ou None)."""

    return _as_joint(joint).mirror(axis=axis, searchSide=search_side, replaceSide=replace_side, replace_name=replace_name)


def duplicate_chain(root, replace_name=None):
    """
    Duplique la chaîne sous 'root', renomme chaque joint (replace_name :
    {ancien: nouveau}, ex: {"_jnt": "_fk_jnt"}) et retourne les Joint
    créés (racine en premier).
    """

    return joint_utilities.Joint.duplicate_chain(_name(root), replace_name=replace_name or {"_jnt": "_fk_jnt"})


def replace_joint_shape(joint, ctrl):
    """Remplace les shapes du joint par une copie de celles de 'ctrl'."""

    return _as_joint(joint).replace_shape(_name(ctrl))


# ==========================================================
# CONTROL
# ==========================================================

def list_ctrl_shapes():
    """Noms des formes de ctrl disponibles (config/shapesCtrl_config.json)."""

    return list(ctrl_utilities.SHAPES)


def create_ctrl(
    name,
    shape="circle",
    size=1.0,
    color=None,
    match=None,
    match_rotation=True,
    parent=None,
    offset=True,
    use_group=False
):

    """
    Crée un ctrl et retourne son Control (Control.name = nom final).

    color          : index 0-31, ou RGB (0-1), ou None.
    match          : node sur lequel matcher le ctrl, ou None.
    match_rotation : matcher aussi la rotation de 'match'.
    parent         : node sous lequel le ranger.
    offset         : compenser son transform (canaux propres) : bake dans
                     l'offsetParentMatrix, ou offset group si use_group.
    """

    control = ctrl_utilities.Control(name, shape=shape, size=size, color=color)
    control.create()

    if match:
        cmds.matchTransform(control.name, _name(match), position=True, rotation=bool(match_rotation))

    parent = _name(parent) if parent else None

    if offset:
        control.create_offset(parent=parent, use_group=use_group)
    elif parent and cmds.objExists(parent):
        cmds.parent(control.name, parent)

    return control


def get_ctrl(name):
    """Control (ctrl_utilities) pour un ctrl existant, pour utiliser ses méthodes."""

    return ctrl_utilities.Control(_name(name), shape=None)


def bake_offset(node, reset=True):
    """Bake le transform local de 'node' dans son offsetParentMatrix (canaux remis à zéro si reset)."""

    return get_ctrl(node).transfer_offset_parent_matrix(reset=reset)


def create_neg_offset(ctrl, translate=True, rotate=False, scale=False):
    """Groupes d'offset inverse au-dessus du ctrl (contre-animation live), retourne le plus haut."""

    return get_ctrl(ctrl).create_neg_offset(translate=translate, rotate=rotate, scale=scale)


def set_ctrl_shape(ctrl, shape, size=None, color=None):
    """(Re)construit la shape du ctrl depuis SHAPES (couleur ré-appliquée si fournie)."""

    control = ctrl_utilities.Control(_name(ctrl), shape=None, color=color)

    return control.set_shape(shape, size=size if size is not None else 1.0)


def copy_ctrl_shape(ctrl, source, color=None):
    """Remplace les shapes du ctrl par une copie de celles de 'source'."""

    control = ctrl_utilities.Control(_name(ctrl), shape=None, color=color)

    return control.set_shape_from(_name(source))


def delete_ctrl_shapes(ctrl):
    """Supprime toutes les shapes du ctrl."""

    return get_ctrl(ctrl).delete_shapes()


def set_ctrl_color(ctrl, color):
    """Couleur d'override des shapes : index 0-31, ou RGB (0-1)."""

    return get_ctrl(ctrl).set_color(color)


def set_ctrl_line_width(ctrl, width):
    """Épaisseur d'affichage des shapes (-1 = défaut Maya)."""

    return get_ctrl(ctrl).set_line_width(width)


def transform_ctrl_shape(ctrl, translate=(0, 0, 0), rotate=(0, 0, 0), scale=1.0, pivot=(0, 0, 0)):
    """Transforme uniquement les CV des shapes du ctrl (pas son transform)."""

    return get_ctrl(ctrl).transform_shape(translate=translate, rotate=rotate, scale=scale, pivot=pivot)


def transfer_shape_to_joint(ctrl, joint):
    """Transfère les shapes du ctrl sur 'joint', puis supprime le ctrl. Retourne le joint."""

    return get_ctrl(ctrl).transfer_to_joint(_name(joint))


def reset_ctrl(ctrl):
    """Remet les attributs keyable / channel box du ctrl à leur valeur par défaut."""

    return get_ctrl(ctrl).reset()


def mirror_ctrl(ctrl):
    """Duplique le ctrl (et son offset group) en miroir L_/R_ : (offset_mirror, ctrl_mirror) ou None."""

    return get_ctrl(ctrl).mirror()


def add_lock_limit_attr(ctrl):
    """Attribut 'lockLimit' sur le ctrl, connecté à tous ses LimitEnable."""

    return get_ctrl(ctrl).add_lock_limit_attr()


# ==========================================================
# CONTROL - BATCH
# ==========================================================
#
# Versions "plusieurs ctrls" des outils du shelf (tools_facialRig) :
# sans 'ctrls', elles agissent sur la sélection, ou à défaut sur tous
# les nodes de la scène finissant par '_ctrl'.
#

def get_ctrls(ctrls=None, suffix="_ctrl"):
    """'ctrls' (node seul ou liste), sinon la sélection, sinon tous les nodes '*{suffix}'."""

    if ctrls:
        return _names(ctrls)

    return cmds.ls(selection=True) or cmds.ls(f"*{suffix}") or []


def reset_ctrls(ctrls=None):
    """reset_ctrl sur chaque ctrl (voir get_ctrls)."""

    return [reset_ctrl(ctrl) for ctrl in get_ctrls(ctrls)]


def mirror_ctrls(ctrls=None):
    """mirror_ctrl sur chaque ctrl (voir get_ctrls)."""

    return [mirror_ctrl(ctrl) for ctrl in get_ctrls(ctrls)]


def limit_ctrls(ctrls=None):
    """add_lock_limit_attr sur chaque ctrl (voir get_ctrls)."""

    return [add_lock_limit_attr(ctrl) for ctrl in get_ctrls(ctrls)]


def neg_offset_ctrls(ctrls=None, translate=True, rotate=False, scale=False):
    """create_neg_offset sur chaque ctrl (voir get_ctrls)."""

    return [
        create_neg_offset(ctrl, translate=translate, rotate=rotate, scale=scale)
        for ctrl in get_ctrls(ctrls)
    ]


# ==========================================================
# CONSTRAINT
# ==========================================================
#
# dcmpMtx : True -> sortie via decomposeMatrix vers translate/rotate/
# scale ; False -> directement dans l'offsetParentMatrix du target.
#

def parent_constraint(target, drivers, mo=False, dcmpMtx=True):
    """Contrainte parent de matrix (ParentCnstrMtx) de 'target' sur 'drivers' (un ou plusieurs)."""

    return cnstrMtx_utilities.ParentCnstrMtx(_name(target), _names(drivers), mo=mo, dcmpMtx=dcmpMtx)


def point_constraint(target, drivers, mo=False, dcmpMtx=True):
    """Contrainte point de matrix (PointCnstrMtx) : translate seul."""

    return cnstrMtx_utilities.PointCnstrMtx(_name(target), _names(drivers), mo=mo, dcmpMtx=dcmpMtx)


def orient_constraint(target, drivers, mo=False, dcmpMtx=True):
    """Contrainte orient de matrix (OrientCnstrMtx) : rotate seul."""

    return cnstrMtx_utilities.OrientCnstrMtx(_name(target), _names(drivers), mo=mo, dcmpMtx=dcmpMtx)


def aim_constraint(
    target,
    drivers,
    world_up=None,
    mo=False,
    dcmpMtx=True,
    aim_vector=(0, 0, 1),
    up_vector=(0, 1, 0),
    invert_aim=False,
    invert_up=False
):

    """
    Contrainte aim de matrix (AimCnstrMtx) : 'target' vise la position
    moyenne de 'drivers', up vers 'world_up' (sinon monde Y).
    """

    return cnstrMtx_utilities.AimCnstrMtx(
        _name(target),
        _names(drivers),
        worldUpObject=_name(world_up) if world_up else None,
        mo=mo,
        dcmpMtx=dcmpMtx,
        aimVector=aim_vector,
        upVector=up_vector,
        invertAimVector=invert_aim,
        invertUpVector=invert_up
    )


def pole_vector_constraint(ik_handle, drivers, mo=False):
    """Pole vector de matrix (PoleVectorCnstr) de l'ikHandle (ikRPsolver) sur 'drivers'."""

    return cnstrMtx_utilities.PoleVectorCnstr(_name(ik_handle), _names(drivers), mo=mo)


def offset_matrix(node, reference):
    """Matrice (valeur) de 'node' dans l'espace de 'reference'."""

    return cnstrMtx_utilities.get_offset_matrix(_name(node), _name(reference))


# ==========================================================
# SPACE SWITCH
# ==========================================================

def space_switch(target, spaces, default=0, attr_name="space", attr_host=None, mo=True, parent=None, blend=False):

    """
    Switch d'espace sur l'offsetParentMatrix de 'target'.

    spaces    : liste ordonnée de (nom, driver).
    attr_host : node qui porte l'attribut (target par défaut).
    mo        : garder la pose actuelle dans chaque espace.
    blend     : 2 espaces exactement, attribut float 0..1 (ex: IK/FK).
    """

    return switchSpace_utilities.SpaceSwitch(
        target=_name(target),
        spaces=[(name, _name(driver)) for name, driver in spaces],
        default=default,
        attr_name=attr_name,
        attr_host=_name(attr_host) if attr_host else None,
        mo=mo,
        parent=_name(parent) if parent else None,
        blend=blend
    )


# ==========================================================
# RIBBON
# ==========================================================

def create_ribbon(
    side,
    base_name,
    positions,
    index=0,
    width=2.0,
    bind_count=5,
    driver_count=3,
    surface=None,
    linear=True,
    parent=None,
    build=True
):

    """
    Ruban (Ribbon) le long de 'positions' (positions monde ou joints, au
    moins 2).
    surface : surface NURBS existante, ou None pour la créer au build à
              partir des curves qui passent par les positions.
    linear  : curves linéaires (segments droits) ou lissées.
    build   : construire tout de suite (surface, follicules, bind joints,
              drivers, skin) sous 'parent'.
    """

    ribbon = ribbon_utilities.Ribbon(
        side,
        base_name,
        positions,
        index=index,
        width=width,
        bind_count=bind_count,
        driver_count=driver_count,
        surface=_name(surface) if surface else None,
        linear=linear
    )

    if build:
        ribbon.build(parent=_name(parent) if parent else None)

    return ribbon


create_follicle = ribbon_utilities.create_follicle
lerp_polyline = ribbon_utilities.lerp_polyline


def create_ribbon_surface(
    side,
    base_name,
    joints,
    index=0,
    width=2.0,
    control_count=3,
    degree=None,
    subdivide=True,
    pinch_offset=0.0,
    direction=None,
    uniform=True,
    linear=True,
    parent=None,
    name=None
):

    """
    Surface de ruban à travers 'joints' (Ribbon.create_surface_from_chain),
    forme conservée : degré 'degree' (None = selon control_count),
    isoparms subdivisés si 'subdivide', pincement si pinch_offset > 0.
    Ex : main nurb du module ribbon = degree=3, subdivide=False.
    Retourne la surface.
    """

    ribbon = ribbon_utilities.Ribbon(side, base_name, joints, index=index, linear=linear)

    return ribbon.create_surface_from_chain(
        [_name(joint) if not isinstance(joint, (list, tuple)) else joint for joint in joints],
        width=width,
        parent=_name(parent) if parent else None,
        uniform=uniform,
        control_count=control_count,
        direction=direction,
        pinch_offset=pinch_offset,
        degree=degree,
        subdivide=subdivide,
        name=name
    )


rebuild_ribbon_degree = ribbon_utilities.Ribbon.rebuild_degree
elevate_surface_degree = ribbon_utilities.Ribbon.elevate_surface_degree
normalize_surface_uv = ribbon_utilities.Ribbon.normalize_uv_range
insert_surface_isoparms = ribbon_utilities.Ribbon.insert_isoparms
insert_surface_isoparms_at = ribbon_utilities.Ribbon.insert_isoparms_at_points
pinch_surface = ribbon_utilities.Ribbon.pinch_knots
surface_matrix = ribbon_utilities.Ribbon.get_surface_matrix
