# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# MODULE
#   _get_cv_positions(shape)                            - positions (objectSpace) des CV d'une courbe
#   _set_cv_positions(shape, points)                     - repositionne les CV d'une courbe
#   load_shapes()                                        - charge shapesCtrl_config.json (SHAPES)
#   _mat3_mul(a, b)                                       - produit de deux matrices 3x3
#   _rotation_matrix(rx, ry, rz)                          - matrice de rotation 3x3 (euler XYZ, degres)
#   _transform_point(point, translate, rotation, ...)    - transforme un point (scale/rotate/translate)
#
# CONTROL (class)
#   __init__(name, shape, size, color)                   - stocke les parametres, ne cree rien dans la scene
#   create(parent=None)                                  - cree le transform du ctrl + sa shape + couleur
#   create_offset(suffix, use_group, parent)             - compense son transform (offsetParentMatrix ou groupe)
#   transfer_offset_parent_matrix(reset=True)            - bake le transform local dans offsetParentMatrix
#   transfer_to_joint(joint)                              - transfere la shape du ctrl sur un joint, supprime le ctrl
#   create_neg_offset(translate, rotate, scale)          - groupes d'offset inverse (contre-animation live)
#   reset()                                               - remet les attributs keyable/channel box par defaut
#   mirror()                                              - duplique le ctrl (+ offset group) en miroir L_/R_
#   add_lock_limit_attr()                                 - attribut 'lockLimit' connecte aux LimitEnable
#   set_shape(shape, size=None)                          - (re)construit les courbes du ctrl depuis SHAPES
#   set_shape_from(source)                                - copie les shapes d'un autre transform
#   delete_shapes()                                       - supprime les shapes actuelles du ctrl
#   get_shapes()                                          - liste les shapes (courbes) du ctrl
#   set_color(color)                                      - couleur d'override (index ou RGB) des shapes
#   set_line_width(width)                                 - epaisseur d'affichage des shapes
#   transform_shape(translate, rotate, scale, pivot)      - transforme les CV de la shape (pas le ctrl)
#   translate_shape(translate)                            - raccourci transform_shape (translate seul)
#   rotate_shape(rotate, pivot)                           - raccourci transform_shape (rotate seul)
#   scale_shape(scale, pivot)                             - raccourci transform_shape (scale seul)
#   _as_vector3(value, default)                           - normalise scalaire/liste en tuple (x, y, z)

# ====================================================================================================================
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
    """
    Positions (objectSpace) des CV d'une shape de courbe.

    shape : noeud shape de la courbe (nurbsCurve) a lire.
    """
    cvs = cmds.ls(f"{shape}.cv[*]", flatten=True) or []
    return [
        cmds.xform(cv, query=True, objectSpace=True, translation=True)
        for cv in cvs
    ]


def _set_cv_positions(shape, points):
    """
    Repositionne (objectSpace) les CV d'une shape de courbe.

    shape  : noeud shape de la courbe (nurbsCurve) a modifier.
    points : liste de positions (objectSpace), une par CV, dans l'ordre.
    """
    cvs = cmds.ls(f"{shape}.cv[*]", flatten=True) or []
    for cv, point in zip(cvs, points):
        cmds.xform(cv, objectSpace=True, translation=list(point))
    if cmds.objExists(shape):
        cmds.dgdirty(shape)


def load_shapes():
    """Charge et retourne le contenu de SHAPES_PATH (shapesCtrl_config.json)."""

    with open(SHAPES_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


SHAPES = load_shapes()


# --------------------------------------------------
# SHAPE TRANSFORM MATH
# --------------------------------------------------

def _mat3_mul(a, b):
    """
    Produit matriciel de deux matrices 3x3 (listes de listes).

    a : matrice 3x3 (gauche).
    b : matrice 3x3 (droite).
    """
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _rotation_matrix(rx, ry, rz):

    """
    Matrice de rotation 3x3, euler XYZ en degrés, convention row-vector (p' = p . R).

    rx : rotation autour de X, en degres.
    ry : rotation autour de Y, en degres.
    rz : rotation autour de Z, en degres.
    """

    rx, ry, rz = math.radians(rx), math.radians(ry), math.radians(rz)

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    mat_x = [[1, 0, 0], [0, cx, sx], [0, -sx, cx]]
    mat_y = [[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]]
    mat_z = [[cz, sz, 0], [-sz, cz, 0], [0, 0, 1]]

    return _mat3_mul(_mat3_mul(mat_x, mat_y), mat_z)


def _transform_point(point, translate, rotation, scale, pivot):

    """
    point relatif au pivot -> scale -> rotate -> retour + translate.

    point     : position [x, y, z] a transformer.
    translate : decalage [x, y, z] applique apres rotation/scale.
    rotation  : matrice 3x3 (voir _rotation_matrix).
    scale     : echelle [sx, sy, sz].
    pivot     : centre [x, y, z] de la rotation/du scale.
    """

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
        Stocke les parametres du ctrl - ne cree rien dans la scene (voir create()).

        name  : nom du transform a creer/piloter.
        shape : cle de forme dans SHAPES (ex. "circle"), ou None pour aucune shape.
        size  : echelle appliquee aux points de la shape.
        color : couleur d'override (index 0-31, ou tuple/list RGB 0-1), ou None.
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
        """
        Cree le transform du ctrl (supprime un ancien node du meme nom s'il
        existe), sa shape et sa couleur, et le parente si demande.

        parent : node sous lequel parenter le ctrl, ou None.
        """

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
        Compense le transform local du ctrl, pour qu'il reparte de canaux
        translate/rotate/scale propres une fois inséré dans la hiérarchie.

        - use_group=False (défaut) : directement dans l'offsetParentMatrix
          du ctrl (voir transfer_offset_parent_matrix), sans nœud
          supplémentaire dans la hiérarchie. Si 'parent' est fourni, le
          ctrl y est d'abord reparenté (monde préservé) pour que le bake
          tienne compte du bon parent final - sinon l'offset serait
          calculé relatif au mauvais parent (ou à aucun).
        - use_group=True : reproduit l'ancien comportement - un groupe
          matché au-dessus du ctrl, parenté à 'parent' (sinon au parent
          courant du ctrl), le ctrl étant ensuite reparenté dessous.

        suffix    : suffixe du groupe d'offset cree (mode use_group=True seulement).
        use_group : False pour l'offsetParentMatrix (defaut), True pour un vrai groupe.
        parent    : node sous lequel reparenter (ctrl ou groupe, selon le mode), ou None.
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
        Bake le transform local actuel du ctrl (relatif à son parent
        courant) dans son offsetParentMatrix, puis (si reset) remet
        translate/rotate/scale à zéro/identité - le ctrl garde la même
        position dans la hiérarchie, mais ses canaux repartent propres,
        prêts à être animés/connectés. Mêmes conventions que
        Joint.freeze_transform (joint_utilities.py) et
        Builder.connect_control_direct (modules/base/builder.py).

        reset : True pour remettre translate/rotate/scale a zero/identite
                une fois le bake fait.
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

        """
        Transfere les shapes du ctrl directement sur 'joint' (plus de ctrl
        separe), puis supprime le ctrl. Le joint garde l'offsetParentMatrix
        déjà baké à sa création (voir Builder.create_joints,
        Joint.freeze_transform, joint_utilities.py) - rien à
        re-baker ici, ses canaux sont déjà à zéro.

        joint : joint cible sur lequel transferer la shape du ctrl.
        """

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
        Empile, au-dessus du ctrl, un groupe d'offset "negatif" par canal
        demande : sa valeur est connectee en live a l'inverse (ou l'oppose)
        du canal du ctrl, pour compenser une contre-animation (ex. un
        parent qui bouge que le ctrl ne doit pas suivre sur ce canal).

        translate : ajoute un groupe qui annule le translate du ctrl.
        rotate    : ajoute un groupe qui annule le rotate du ctrl (ordre inverse).
        scale     : ajoute un groupe qui annule le scale du ctrl.
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
        """
        Remet les attributs keyable/channel box de self.name a leur
        valeur par defaut (ignore les attributs verrouilles ou sans
        valeur par defaut).
        """

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
        Duplique le ctrl (et tout son offset group) en miroir, a partir
        de la convention de nommage L_/R_ (prefixe du ctrl) : remonte la
        hierarchie jusqu'au premier offset group ('..._offset'), le
        duplique, renomme chaque descendant (L_/R_), puis inverse
        scaleX/translateX/rotateY sur le duplicata.

        Retourne (offset_mirror, ctrl_mirror), ou None si impossible
        (ctrl introuvable, pas de prefixe L_/R_, pas d'offset group
        trouve, ou le miroir existe deja).
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

        """
        Ajoute un attribut 'lockLimit' (bool) sur self.name et le
        connecte a tous ses attributs 'min/max...LimitEnable' existants
        (translate, rotate, scale) : un seul switch verrouille/
        deverrouille toutes les limites du ctrl.
        """

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
        (Re)construit les shapes du self.name à partir d'une config de
        shapes.json (une forme = une liste de courbes, chacune définie
        par ses points et son degree).

        shape : cle de forme dans SHAPES.
        size  : echelle appliquee aux points, ou None pour garder self.size.
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

        """
        Remplace les shapes du ctrl par une copie des shapes d'un autre
        transform déjà existant dans la scène (garde sa propre couleur).

        source : transform dont on copie les shapes.
        """

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
        """Supprime toutes les shapes actuelles du ctrl (self.get_shapes())."""

        shapes = self.get_shapes()

        if shapes:
            cmds.delete(*shapes)

    def get_shapes(self):
        """Retourne la liste des shapes (courbes) du ctrl, ou [] s'il n'existe pas."""

        if not cmds.objExists(self.name):
            return []

        return cmds.listRelatives(self.name, shapes=True, fullPath=True) or []

    # ----------------------------------------
    # COLOR
    # ----------------------------------------

    def set_color(self, color):

        """
        Applique une couleur aux shapes du ctrl : un index (override
        color 0-31) ou un tuple/list RGB (0-1) pour une couleur directe.

        color : index entier (0-31), ou tuple/list RGB (0-1).
        """

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

        """
        Change l'épaisseur d'affichage (lineWidth) des shapes du ctrl.

        width : epaisseur d'affichage (ex. 1.0, 2.0, ... ; -1 = defaut Maya).
        """

        for shape in self.get_shapes():

            if cmds.objExists(f"{shape}.lineWidth"):
                cmds.setAttr(f"{shape}.lineWidth", width)

        return self.get_shapes()

    # ----------------------------------------
    # SHAPE TRANSFORM
    # ----------------------------------------

    def transform_shape(self, translate=(0, 0, 0), rotate=(0, 0, 0), scale=1.0, pivot=(0, 0, 0)):

        """
        Transforme UNIQUEMENT la/les shape(s) du ctrl (déplace ses points
        de contrôle), sans toucher au transform du ctrl.

        translate : décalage en unités locales.
        rotate    : rotation en degrés (ordre XYZ).
        scale     : scalaire, ou (sx, sy, sz).
        pivot     : centre local de la rotation / du scale.
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
        """
        Décale les points de contrôle du ctrl (raccourci de transform_shape).

        translate : décalage en unités locales.
        """
        return self.transform_shape(translate=translate)

    def rotate_shape(self, rotate, pivot=(0, 0, 0)):
        """
        Tourne les points de contrôle du ctrl (raccourci de transform_shape).

        rotate : rotation en degrés (ordre XYZ).
        pivot  : centre local de la rotation.
        """
        return self.transform_shape(rotate=rotate, pivot=pivot)

    def scale_shape(self, scale, pivot=(0, 0, 0)):
        """
        Scale les points de contrôle du ctrl (raccourci de transform_shape).

        scale : scalaire, ou (sx, sy, sz).
        pivot : centre local du scale.
        """
        return self.transform_shape(scale=scale, pivot=pivot)

    @staticmethod
    def _as_vector3(value, default):
        """
        Normalise 'value' en tuple (x, y, z) : un scalaire est duplique sur
        les 3 axes, une liste/tuple de 3 est convertie telle quelle,
        n'importe quoi d'autre retombe sur 'default' sur les 3 axes.

        value   : scalaire, ou liste/tuple de 3 valeurs.
        default : valeur de repli (sur les 3 axes) si 'value' est invalide.
        """

        if isinstance(value, (int, float)):
            return (float(value), float(value), float(value))

        if isinstance(value, (list, tuple)) and len(value) == 3:
            return tuple(float(component) for component in value)

        return (default, default, default)