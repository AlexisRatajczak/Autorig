# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# SPACESWITCH (class)
#   __init__(target, spaces, default, attr_name, ..., scale) - construit l'attribut + le reseau, appelle build()
#                                                        scale : suivre aussi le scale de l'espace (sinon retiré)
#   build()                                              - cree le blendMatrix + les conditions, connecte target
#   add_attribute()                                      - cree/initialise l'attribut de switch (enum, ou float si blend)
#   get_space_matrix(driver)                             - matrice d'un espace (avec offset de maintien de pose)
#   compute_offset(driver)                                - offset monde pour garder la pose au switch
#   create_weight_condition(index)                        - condition node (1 si l'enum == index, sinon 0)
#   delete()                                              - supprime tous les noeuds crees par le switch

# ====================================================================================================================
# ====================================================================================================================

import maya.cmds as cmds


# --------------------------------------------------
# SPACE SWITCH
# --------------------------------------------------
#
# Bascule le parent effectif de 'target' (généralement l'offset group
# d'un ctrl) entre plusieurs 'spaces' (drivers), sans pop, via un
# blendMatrix piloté par un attribut enum. Suit le même principe que
# les contraintes de cnstrMtx_utilities (matrices, offsetParentMatrix),
# mais pour un choix exclusif (one-hot) entre plusieurs drivers au lieu
# d'un blend continu.
#

class SpaceSwitch:

    def __init__(self, target, spaces, default=0, attr_name="space", attr_host=None, mo=True, parent=None, blend=False, scale=True):

        """
        target     : node dont l'offsetParentMatrix sera piloté (le plus
                     souvent l'offset group du ctrl, pas le ctrl lui-même,
                     pour laisser ses canaux translate/rotate/scale libres
                     à l'animation).
        spaces     : liste ordonnée de (name, driver) ; 'name' alimente
                     l'enum, 'driver' est le node dont le worldMatrix
                     pilote target dans cet espace.
        default    : index de l'espace actif par défaut.
        attr_name  : nom de l'attribut enum créé/utilisé pour le switch.
        attr_host  : node qui porte l'attribut enum (par défaut : target).
                     Utile pour héberger l'attribut sur le ctrl tout en
                     pilotant son offset group.
        mo         : si True, calcule un offset par espace pour que le
                     switch ne fasse pas sauter target (garde sa pose
                     actuelle au moment du build).
        parent     : node parent DAG de target, dont le worldInverseMatrix
                     ramène les drivers dans l'espace du parent. Par défaut,
                     le vrai parent DAG de target. On lit ce plug sur le
                     PARENT et non `target.parentInverseMatrix` : ce dernier
                     est redéclenché par target.worldMatrix (donc par
                     target.offsetParentMatrix qu'on pilote), ce qui crée
                     un cycle. Le parent, lui, ne dépend pas de target.
        blend      : si True (exactement 2 spaces, ex: switch IK/FK),
                     l'attribut est un float 0..1 au lieu d'un enum,
                     connecté à l'envelope du blendMatrix (target à
                     weight 1) : interpolation continue entre les 2 spaces.
        scale      : target suit aussi le scale de l'espace actif (blendé
                     entre deux espaces). False : scale et shear retirés
                     (pickMatrix) - translate + rotate seuls.
        """

        self.target = target
        self.blend = blend
        self.scale = scale
        self.spaces = list(spaces)

        self.default = default
        self.attr_name = attr_name
        self.attr_host = attr_host or target
        self.mo = mo

        if parent is None:
            dag_parent = cmds.listRelatives(target, parent=True, fullPath=True)
            self.parent = dag_parent[0] if dag_parent else None
        else:
            self.parent = parent

        self.nodes = {}

        self.build()

    # --------------------------------------------------
    # BUILD
    # --------------------------------------------------

    def build(self):
        """
        Construit le reseau complet : attribut enum, matrice par espace
        (get_space_matrix), blendMatrix pilote par des conditions
        (create_weight_condition), puis connecte le resultat dans
        target.offsetParentMatrix et remet translate/rotate/scale a zero.
        Ne fait rien (warning) si moins de 2 spaces ou si target n'a pas
        d'offsetParentMatrix.
        """

        if len(self.spaces) < 2:
            cmds.warning("SpaceSwitch needs at least 2 spaces.")
            return

        if self.blend and len(self.spaces) != 2:
            cmds.warning("SpaceSwitch blend mode needs exactly 2 spaces.")
            return

        if not cmds.objExists(self.target) or not cmds.objExists(f"{self.target}.offsetParentMatrix"):
            cmds.warning(f"'{self.target}' does not exist or has no offsetParentMatrix.")
            return

        self.add_attribute()

        blend = cmds.createNode("blendMatrix", name=f"{self.target}_space_bm")
        self.nodes["blendMatrix"] = blend

        base_name, base_driver = self.spaces[0]

        cmds.connectAttr(
            self.get_space_matrix(base_driver),
            f"{blend}.inputMatrix",
            force=True
        )

        for index, (name, driver) in enumerate(self.spaces[1:], start=1):

            target_index = index - 1

            cmds.connectAttr(
                self.get_space_matrix(driver),
                f"{blend}.target[{target_index}].targetMatrix",
                force=True
            )

            if self.blend:
                cmds.setAttr(f"{blend}.target[{target_index}].weight", 1.0)
                continue

            cmds.connectAttr(
                self.create_weight_condition(index),
                f"{blend}.target[{target_index}].weight",
                force=True
            )

        # Mode blend : l'attribut float pilote l'envelope du blendMatrix
        # (0 = inputMatrix / space 0, 1 = target / space 1).
        if self.blend:
            cmds.connectAttr(f"{self.attr_host}.{self.attr_name}", f"{blend}.envelope", force=True)

        output = f"{blend}.outputMatrix"

        # Scale de l'espace : gardé (matrices complètes) ou retiré.
        if not self.scale:
            pick = cmds.createNode("pickMatrix", name=f"{self.target}_space_noScale_pm")
            cmds.connectAttr(output, f"{pick}.inputMatrix", force=True)
            cmds.setAttr(f"{pick}.useScale", 0)
            cmds.setAttr(f"{pick}.useShear", 0)
            self.nodes["noScale_pickMatrix"] = pick
            output = f"{pick}.outputMatrix"

        cmds.connectAttr(output, f"{self.target}.offsetParentMatrix", force=True)

        cmds.setAttr(f"{self.target}.translate", 0, 0, 0)
        cmds.setAttr(f"{self.target}.rotate", 0, 0, 0)
        cmds.setAttr(f"{self.target}.scale", 1, 1, 1)

    # --------------------------------------------------
    # ATTRIBUTE
    # --------------------------------------------------

    def add_attribute(self):

        """
        Crée (si besoin) l'attribut de switch sur attr_host, puis le met
        a self.default : enum avec un nom par space, ou float de 0 a
        1 si self.blend.
        """

        names = ":".join(name for name, _ in self.spaces)

        if not cmds.attributeQuery(self.attr_name, node=self.attr_host, exists=True):

            if self.blend:
                cmds.addAttr(
                    self.attr_host,
                    longName=self.attr_name,
                    attributeType="double",
                    minValue=0.0,
                    maxValue=1.0,
                    keyable=True
                )
            else:
                cmds.addAttr(
                    self.attr_host,
                    longName=self.attr_name,
                    attributeType="enum",
                    enumName=names,
                    keyable=True
                )

        cmds.setAttr(f"{self.attr_host}.{self.attr_name}", self.default)

    # --------------------------------------------------
    # PER-SPACE MATRIX
    # --------------------------------------------------

    def get_space_matrix(self, driver):

        """
        Matrice (dans l'espace du parent de target) pour ce driver,
        avec l'offset de maintien de pose si mo=True :
        offset(hold) * driver.worldMatrix * parent.worldInverseMatrix.

        Sans parent DAG (target au monde), le terme d'inverse parent est
        omis (driver.worldMatrix est déjà dans le bon espace).

        driver : node dont le worldMatrix pilote target dans cet espace.
        """

        mult = cmds.createNode("multMatrix", name=f"{self.target}_{driver}_space_mm")
        self.nodes[f"{driver}_multMatrix"] = mult

        index = 0

        if self.mo:

            offset = self.compute_offset(driver)

            hold = cmds.createNode("holdMatrix", name=f"{self.target}_{driver}_space_hold")
            cmds.setAttr(f"{hold}.inMatrix", offset, type="matrix")
            self.nodes[f"{driver}_holdMatrix"] = hold

            cmds.connectAttr(f"{hold}.outMatrix", f"{mult}.matrixIn[{index}]", force=True)
            index += 1

        cmds.connectAttr(f"{driver}.worldMatrix[0]", f"{mult}.matrixIn[{index}]", force=True)
        index += 1

        if self.parent and cmds.objExists(self.parent):
            cmds.connectAttr(
                f"{self.parent}.worldInverseMatrix[0]",
                f"{mult}.matrixIn[{index}]",
                force=True
            )

        return f"{mult}.matrixSum"

    def compute_offset(self, driver):

        """
        Offset monde (constant) permettant de conserver la pose actuelle
        de target au moment du switch vers 'driver' :
        offset = target.worldMatrix * inverse(driver.worldMatrix).

        driver : node dont le worldMatrix sert de reference pour l'offset.
        """

        inv = cmds.createNode("inverseMatrix")
        mult = cmds.createNode("multMatrix")

        cmds.connectAttr(f"{driver}.worldMatrix[0]", f"{inv}.inputMatrix", force=True)
        cmds.connectAttr(f"{self.target}.worldMatrix[0]", f"{mult}.matrixIn[0]", force=True)
        cmds.connectAttr(f"{inv}.outputMatrix", f"{mult}.matrixIn[1]", force=True)

        offset = cmds.getAttr(f"{mult}.matrixSum")

        cmds.delete(inv, mult)

        return offset

    # --------------------------------------------------
    # WEIGHT CONDITION
    # --------------------------------------------------

    def create_weight_condition(self, index):

        """
        Condition node : 1.0 si l'attribut de switch vaut 'index', sinon 0.0.

        index : valeur de l'enum (position du space dans self.spaces) a tester.
        """

        condition = cmds.createNode("condition", name=f"{self.target}_space{index}_cond")

        cmds.setAttr(f"{condition}.operation", 0)  # equal
        cmds.setAttr(f"{condition}.secondTerm", index)
        cmds.setAttr(f"{condition}.colorIfTrueR", 1)
        cmds.setAttr(f"{condition}.colorIfFalseR", 0)

        cmds.connectAttr(f"{self.attr_host}.{self.attr_name}", f"{condition}.firstTerm", force=True)

        self.nodes[f"space{index}_condition"] = condition

        return f"{condition}.outColorR"

    # --------------------------------------------------
    # CLEAN
    # --------------------------------------------------

    def delete(self):
        """Supprime tous les noeuds crees par ce SpaceSwitch (self.nodes)."""

        for node in list(self.nodes.values()):
            if cmds.objExists(node):
                cmds.delete(node)

        self.nodes.clear()
