# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# JOINT (class)
#   __init__(data, suffix="jnt")                         - stocke les parametres, resout un index libre
#   index (property / setter)                            - index numerique du nom (auto-incremente)
#   name (property / setter)                              - nom calcule {side}_{baseName}_{index}_{suffix}
#   create_joint()                                        - cree le node joint, le parente si besoin
#   match_transform(target, matchPos, matchRot, matchScale) - matche le joint sur un guide/node cible
#   freeze_transform()                                    - bake le transform local (+ jointOrient) dans offsetParentMatrix
#   rename(baseName, side, index, suffix)                 - renomme (et met a jour ses attributs de nommage)
#   mirror(axis, searchSide, replaceSide, replace_name)   - duplique/miroir le joint, retourne un nouveau Joint
#   duplicate_chain(root_joint, replace_name) [static]    - duplique toute une chaine, reconstruit la hierarchie
#   replace_shape(ctrl)                                   - copie les shapes d'un ctrl sur le joint
#
# CHAIN HELPERS
#   as_joint(joint)                                       - Joint pour un joint existant (nom), ou tel quel
#   parent_joint(joint, parent)                           - reparente, position monde gardée, transform re-baké
#   create_chain(positions, names, parent, aim_vector, up_vector, up_objects)
#                                                         - chaîne orientée (aim vers le suivant) aux positions données

# ====================================================================================================================
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om


class Joint:

    def __init__(self, data, suffix="jnt"):
        """
        Stocke les parametres du joint et resout un index libre (ne cree
        rien dans la scene - voir create_joint()).

        data   : dict avec au minimum "baseName" et "side" (initiale),
                  optionnellement "parent", "guide", "index".
        suffix : suffixe de nommage (ex. "jnt", "fk_jnt").
        """

        self.baseName = data["baseName"]
        self.side = data["side"][0]
        self.parent = data.get("parent")
        self.suffix = suffix
        self.guide = data.get("guide")

        self._index = data.get("index", 0)
        self._name = None

        while cmds.objExists(f'{self.side}_{self.baseName}_{self._index:02d}_{self.suffix}'):
            self._index += 1


    @property
    def index(self):
        """Index numerique utilise dans le nom calcule (voir name)."""
        return self._index

    @index.setter
    def index(self, value):
        self._index = value

    @property
    def name(self):
        """Nom du joint : explicitement set (voir le setter), sinon calcule {side}_{baseName}_{index:02d}_{suffix}."""
        if self._name:
            return self._name
        return f"{self.side}_{self.baseName}_{self.index:02d}_{self.suffix}"

    @name.setter
    def name(self, value):
        self._name = value

    # --------------------------------------------------
    # CREATE JOINT
    # --------------------------------------------------

    def create_joint(self):
        """Cree le node joint (nomme self.name) et le parente a self.parent s'il existe."""

        self.name = cmds.createNode("joint", name=self.name)

        if self.parent and cmds.objExists(self.parent):
            cmds.parent(self.name, self.parent)

        return self.name

    # --------------------------------------------------
    # MATCH TRANSFORM
    # --------------------------------------------------

    def match_transform(self, target = None,  matchPos=True, matchRot=True, matchScale=None):
        """
        Matche le transform du joint sur 'target' (ou self.guide par defaut).

        target     : node cible, ou None pour utiliser self.guide.
        matchPos   : matcher la position.
        matchRot   : matcher la rotation.
        matchScale : matcher l'echelle.
        """

        if target == None:
            target = self.guide

        if target and cmds.objExists(target):
            if self.name and cmds.objExists(self.name):
                cmds.matchTransform(self.name, target, position=bool(matchPos), rotation=bool(matchRot), scale=bool(matchScale))

        return self

    # --------------------------------------------------
    # FREEZE TRANSFORM
    # --------------------------------------------------

    def freeze_transform(self):
        """
        Bake la matrice locale actuelle du joint (worldMatrix * parent
        worldInverseMatrix s'il a un parent, sinon worldMatrix tel quel)
        dans son offsetParentMatrix, puis remet translate/rotate/scale a
        zero/identite et jointOrient a zero.

        Calculee via worldMatrix/worldInverseMatrix (plutot que lue sur
        '.matrix') pour rester correcte quel que soit l'etat courant du
        joint. jointOrient est explicitement remis a zero car '.matrix'
        d'un joint l'integre deja (contrairement a un transform classique) :
        le laisser non-nul apres le bake doublerait sa rotation - voir
        Builder.connect_control_direct (modules/base/builder.py), meme
        convention.
        """

        if not self.name or not cmds.objExists(self.name):
            return self

        world_matrix = om.MMatrix(cmds.getAttr(f"{self.name}.worldMatrix[0]"))

        parent = cmds.listRelatives(self.name, parent=True, fullPath=True)

        if parent:
            parent_inverse = om.MMatrix(cmds.getAttr(f"{parent[0]}.worldInverseMatrix[0]"))
            local_matrix = world_matrix * parent_inverse
        else:
            local_matrix = world_matrix

        cmds.setAttr(f"{self.name}.offsetParentMatrix", list(local_matrix), type="matrix")

        cmds.setAttr(f"{self.name}.translate", 0, 0, 0)
        cmds.setAttr(f"{self.name}.rotate", 0, 0, 0)
        cmds.setAttr(f"{self.name}.scale", 1, 1, 1)

        if cmds.attributeQuery("jointOrient", node=self.name, exists=True):
            cmds.setAttr(f"{self.name}.jointOrient", 0, 0, 0)

        return self

    # --------------------------------------------------
    # RENAME JOINT
    # --------------------------------------------------

    def rename(self, baseName=None, side=None, index=None, suffix=None):
        """
        Met a jour les attributs de nommage fournis (les autres sont
        inchanges) et renomme le joint dans la scene en consequence.

        baseName : nouveau baseName, ou None pour garder l'actuel.
        side     : nouveau side, ou None pour garder l'actuel.
        index    : nouvel index, ou None pour garder l'actuel.
        suffix   : nouveau suffixe, ou None pour garder l'actuel.
        """

        if baseName is not None:
            self.baseName = baseName

        if side is not None:
            self.side = side

        if index is not None:
            self.index = index

        if suffix is not None:
            self.suffix = suffix


        new_name = f"{self.side}_{self.baseName}_{self.index:02d}_{self.suffix}"

        if cmds.objExists(self.name):
            self.name = cmds.rename(self.name, new_name)

        else:
            self.name = new_name


        return self

    # --------------------------------------------------
    # MIRROR JOINT
    # --------------------------------------------------

    def mirror(
        self,
        axis="YZ",
        searchSide="L",
        replaceSide="R",
        replace_name=None
    ):
        """
        Duplique/miroir le joint (cmds.mirrorJoint) et renomme le resultat
        (side + remplacements optionnels). Retourne un nouveau Joint pour
        le duplicata, ou None si le mirror a echoue.

        axis         : plan de symetrie ("XY", "YZ" ou "XZ").
        searchSide   : prefixe de side a remplacer dans le nom duplique (ex. "L").
        replaceSide  : side de remplacement (ex. "R").
        replace_name : dict {ancien: nouveau} de remplacements supplementaires
                        appliques au nom avant le remplacement de side.
        """

        if not cmds.objExists(self.name):
            return None


        # MIRROR JOINT
        axis_flag = {
            "XY": "mirrorXY",
            "YZ": "mirrorYZ",
            "XZ": "mirrorXZ",
        }.get(str(axis).upper(), "mirrorYZ")

        mirrored = cmds.mirrorJoint(
            self.name, mirrorBehavior=True, **{axis_flag: True}
        ) or []

        if not mirrored:
            return None

        mirror_joint = mirrored[0]

        # RENAME
        old_name = mirror_joint.split("|")[-1]

        if replace_name:
            for old, new in replace_name.items():
                old_name = old_name.replace(old, new)

        old_name = old_name.replace(searchSide, replaceSide)
        mirror_joint = cmds.rename(mirror_joint, old_name)


        # CREATE JOINT OBJECT
        data = {
            "baseName": self.baseName,
            "side": replaceSide,
            "parent": None,
            "index": self.index,
            "guide": None
        }

        obj = Joint(data, suffix=self.suffix)
        obj.name = mirror_joint

        return obj

    # --------------------------------------------------
    # DUPLICATE JOINTS
    # --------------------------------------------------

    @staticmethod
    def duplicate_chain(root_joint, replace_name={"_jnt": "_fk_jnt"}):
        """
        Duplique toute la chaine sous 'root_joint', renomme chaque joint
        (remplacements de nom + Joint pour le nommage standard) et
        reconstruit la hierarchie parent/enfant. Retourne la liste des
        Joint crees (racine en premier).

        root_joint   : joint racine de la chaine a dupliquer.
        replace_name : dict {ancien: nouveau} applique au nom de chaque
                        joint duplique avant de le reformater.
        """

        if not cmds.objExists(root_joint):
            return []

        duplicate_root = cmds.duplicate(root_joint, renameChildren=True)[0]

        joints = cmds.listRelatives(duplicate_root, allDescendents=True, type="joint") or []
        joints.append(duplicate_root)
        joints = list(reversed(joints))

        joint_objects = []

        for index, joint in enumerate(joints):

            old_name = joint.split("|")[-1]

            # REPLACE NAME

            if replace_name:
                for old, new in replace_name.items():
                    old_name = old_name.replace(old, new)


            parts = old_name.split("_")

            side = parts[0]
            base_name = parts[1] if len(parts) > 2 else old_name
            suffix = parts[-1]


            data = {
                "baseName": base_name,
                "side": side,
                "parent": None,
                "index": index,
                "guide": None
            }


            joint_obj = Joint(data, suffix=suffix)

            joint = cmds.rename(joint, joint_obj.name)

            joint_obj.name = joint

            joint_objects.append(joint_obj)

        # REBUILD HIERARCHY

        for i in range(1, len(joint_objects)):
            cmds.parent(joint_objects[i].name, joint_objects[i - 1].name)
            joint_objects[i].parent = joint_objects[i - 1].name


        return joint_objects

    # --------------------------------------------------
    # REPLACE SHAPES
    # --------------------------------------------------

    def replace_shape(self, ctrl):
        """
        Remplace les shapes du joint par une copie des shapes de 'ctrl'.

        ctrl : transform dont on copie les shapes.
        """

        if not cmds.objExists(self.name) or not cmds.objExists(ctrl):
            return None

        # GET CTRL SHAPES
        shapes = cmds.listRelatives(ctrl, shapes=True, fullPath=True) or []

        if not shapes:
            return None

        # DELETE OLD SHAPES
        old_shapes = cmds.listRelatives(self.name, shapes=True, fullPath=True) or []

        if old_shapes:
            cmds.delete(*old_shapes)

        # TRANSFER SHAPES
        new_shapes = []

        for shape in shapes:

            duplicate = cmds.duplicate(shape, returnRootsOnly=True)[0]

            duplicate_shape = cmds.listRelatives(duplicate, shapes=True, fullPath=True)[0]

            cmds.parent(duplicate_shape, self.name, shape=True, relative=True)

            cmds.delete(duplicate)

            new_shapes.append(duplicate_shape)


        # RETURN
        return self


# ==========================================================
# CHAIN HELPERS
# ==========================================================

def as_joint(joint):
    """Joint tel quel, ou Joint pour un joint existant (nom), pour ses méthodes (freeze_transform...)."""

    if isinstance(joint, Joint):
        return joint

    wrapper = Joint({"baseName": joint, "side": "C"})
    wrapper.name = joint

    return wrapper


def parent_joint(joint, parent):

    """
    Parente 'joint' (Joint ou nom) sous 'parent' en gardant sa position
    monde, offsetParentMatrix re-baké pour le nouveau parent (canaux
    propres, voir Joint.freeze_transform). Retourne le Joint.
    """

    joint = as_joint(joint)

    world_matrix = cmds.xform(joint.name, query=True, matrix=True, worldSpace=True)

    cmds.parent(joint.name, parent, relative=True)
    cmds.xform(joint.name, worldSpace=True, matrix=world_matrix)

    joint.freeze_transform()

    return joint


def create_chain(positions, names, parent=None, aim_vector=(1, 0, 0), up_vector=(0, 0, 1), up_objects=None):

    """
    Chaîne de joints 'names' aux positions monde 'positions' : chaque joint
    vise le suivant (aimVector), up = axe Y de son 'up_objects[i]'
    (rotation de l'objet) ou Y monde ; le dernier garde l'orientation du
    précédent. Créés à plat (orienter un joint ne déplace pas les autres),
    transforms bakés, puis chaînés sous 'parent' (position monde gardée).
    Retourne les Joint, racine en premier.
    """

    if len(positions) != len(names):
        raise ValueError("create_chain : autant de noms que de positions.")

    joints = []

    for name, position in zip(names, positions):

        joint = cmds.createNode("joint", name=name)

        if parent and cmds.objExists(parent):
            cmds.parent(joint, parent, relative=True)

        cmds.xform(joint, worldSpace=True, translation=list(position))

        joints.append(joint)

    for index, joint in enumerate(joints):

        if index + 1 < len(joints):

            kwargs = {"worldUpType": "scene"}

            up_object = up_objects[index] if up_objects else None

            if up_object and cmds.objExists(up_object):
                kwargs = {"worldUpType": "objectrotation", "worldUpVector": (0, 1, 0), "worldUpObject": up_object}

            cmds.delete(cmds.aimConstraint(joints[index + 1], joint, aimVector=aim_vector, upVector=up_vector, **kwargs))

        elif index > 0:
            cmds.matchTransform(joint, joints[index - 1], rotation=True)

    for joint in joints:
        as_joint(joint).freeze_transform()

    for previous, joint in zip(joints[:-1], joints[1:]):
        parent_joint(joint, previous)

    return [as_joint(joint) for joint in joints]
