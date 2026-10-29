# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# MATRIXCNSTR (base class, voir ParentCnstrMtx/PointCnstrMtx/OrientCnstrMtx/AimCnstrMtx/PoleVectorCnstr)
#   __init__(target, ctrls, mo=False, dcmpMtx=True)      - stocke les parametres, appelle build()
#   get_target_data()                                     - sauvegarde le transform initial du target
#   get_ctrl_parents()                                     - parent DAG actuel de chaque ctrl
#   get_target_parent()                                    - parent DAG actuel du target
#   reset_targetTransform(translate, rotate, scale)        - remet translate/rotate/scale du target
#   reset_offsetParentMatrix(matrix=None)                  - remet offsetParentMatrix (identite par defaut)
#   create_mo()                                             - calcule l'offset de maintien de pose (holdMatrix)
#   connect_mo(hold)                                        - insere l'offset devant la sortie de la contrainte
#   disconnect_mo()                                         - retire le maintain offset (supprime ses noeuds)
#   connect_offParentMtx()                                  - branche la sortie dans target.offsetParentMatrix
#   disconnect_offParentMtx(ctrl=None)                      - debranche + restaure le transform d'origine
#   connect_dcmpMtx(translate, rotate, scale)               - branche la sortie via un decomposeMatrix
#   disconnect_dcmpMtx()                                    - debranche le decomposeMatrix + restaure
#   build_mtx()                                             - [a implementer par les sous-classes]
#   build()                                                 - orchestre build_mtx() + mo + dcmpMtx/offsetParentMatrix
#   delete()                                                - debranche tout et supprime les noeuds crees
#
# UTILITY (fonctions de module)
#   create_parent_space_matrix(ctrl, target, nodes, suffix) - matrice du ctrl dans l'espace du parent DAG du target
#   remove_scale(matrix, target, nodes, name)               - pickMatrix : translate + rotate seuls
#   create_matrix_blend(matrices, target, nodes, name)      - blend N matrices deja dans le meme espace (moyenne)
#   get_offset_matrix(node, reference)                      - node.worldMatrix * reference.worldInverseMatrix (valeur)
#
# PARENTCNSTRMTX(MatrixCnstr)
#   __init__(target, ctrls, mo, dcmpMtx, scale=True)          - scale : suivre aussi le scale des ctrls
#   connect_dcmpMtx(translate, rotate, scale)                - sans target.scale si scale=False
#   build_mtx()                                             - dispatch single/multi selon le nombre de ctrls
#   _build_single()                                          - 1 ctrl : ctrl.world * parentTarget.worldInverse
#   _build_multi()                                           - N ctrls : centre + offsets + blend pondere
#
# POINTCNSTRMTX(MatrixCnstr)
#   build_mtx()                                              - blend des positions (translate seul)
#
# ORIENTCNSTRMTX(MatrixCnstr)
#   build_mtx()                                              - blend des rotations (rotate seul)
#
# SCALECNSTRMTX(MatrixCnstr)
#   build_mtx()                                              - scale des ctrls, translate / rotate du build
#   connect_dcmpMtx(translate, rotate, scale)                - target.scale seul
#
# AIMCNSTRMTX(MatrixCnstr)
#   __init__(target, ctrls, worldUpObject, mo, dcmpMtx, ...) - parametres aim/up specifiques, appelle build()
#   create_target_proxy()                                    - locator proxy qui reprend le target (evite un cycle)
#   build_mtx()                                              - construit la matrice aim (vecteurs + fourByFourMatrix)
#
# POLEVECTORCNSTR(MatrixCnstr)
#   __init__(target, ctrls, mo=False)                        - target = ikHandle (ikRPsolver), recupere le start joint
#   get_target_data()                                        - + poleVector initial
#   get_pole_space()                                         - parent DAG de l'ikHandle (espace du poleVector)
#   to_pole_space(matrix_plug, name)                         - matrice monde -> espace du parent de l'ikHandle
#   build_mtx()                                              - ctrl(s) dans l'espace du parent de l'ikHandle
#   build_vector()                                           - pole - start joint, meme espace (plusMinusAverage)
#   delete_native_cnstr()                                    - supprime un poleVectorConstraint classique existant
#   connect_poleVector()                                     - branche le vecteur dans ikHandle.poleVector
#   build()                                                  - orchestre build_mtx() + vecteur + mo + connexion
#   create_mo() / connect_mo(offset) / disconnect_mo()       - maintain offset vectoriel (input3D[2])
#   delete()                                                 - debranche, restaure le poleVector, supprime les noeuds

# ====================================================================================================================
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om


# --------------------------------------------------
# MATRIX CONSTRAINT BASE
# --------------------------------------------------

class MatrixCnstr(object):
    """Base class for matrix constraints."""

    def __init__(self, target, ctrls, mo=False, dcmpMtx=True):
        """
        Stocke les parametres, capture l'etat initial du target/des ctrls,
        puis appelle build() (voir build_mtx(), a implementer par chaque
        sous-classe).

        target  : node pilote par la contrainte.
        ctrls   : node (ou liste de nodes) pilotant le target.
        mo      : maintain offset - si True, le target garde sa pose
                   actuelle au build au lieu de sauter sur les ctrls.
        dcmpMtx : si True, la sortie passe par un decomposeMatrix vers
                   translate/rotate/scale ; si False, elle va directement
                   dans offsetParentMatrix.
        """

        self.target = target
        self.ctrls = ctrls if isinstance(ctrls, (list, tuple)) else [ctrls]

        self.parents = self.get_ctrl_parents()
        self.parent_target = self.get_target_parent()
        self.target_data = self.get_target_data()

        self.mo = mo
        self.dcmpMtx = dcmpMtx

        self.outMatrix = None
        self._pre_mo_outMatrix = None
        self._mo_baked = False

        self.nodes = {}
        self.offset = {}

        self.build()

    # --------------------------------------------------
    # GET DATA
    # --------------------------------------------------

    def get_target_data(self):
        """Store initial transform data from target (offsetParentMatrix, translate, rotate, scale)."""

        data = {}

        data["offsetParentMatrix"] = cmds.getAttr(f"{self.target}.offsetParentMatrix")
        data["translate"] = cmds.getAttr(f"{self.target}.translate")[0]
        data["rotate"] = cmds.getAttr(f"{self.target}.rotate")[0]
        data["scale"] = cmds.getAttr(f"{self.target}.scale")[0]

        return data

    def get_ctrl_parents(self):
        """Return {ctrl: parent} - le parent DAG actuel de chaque node de self.ctrls."""

        parents = {}

        for ctrl in self.ctrls:
            parent = cmds.listRelatives(ctrl, parent=True, fullPath=True)
            parents[ctrl] = parent[0] if parent else None

        return parents

    def get_target_parent(self):
        """Return le parent DAG actuel de self.target, ou None s'il n'en a pas."""

        parent = cmds.listRelatives(self.target, parent=True, fullPath=True)

        return parent[0] if parent else None

    # --------------------------------------------------
    # RESET TRANSFORM
    # --------------------------------------------------

    def reset_targetTransform(self, translate=(0, 0, 0), rotate=(0, 0, 0), scale=(1, 1, 1)):
        """
        Reset target transform values.

        translate : valeur [x, y, z] a ecrire sur target.translate.
        rotate    : valeur [x, y, z] a ecrire sur target.rotate.
        scale     : valeur [x, y, z] a ecrire sur target.scale.
        """

        cmds.setAttr(f"{self.target}.translate", *translate)
        cmds.setAttr(f"{self.target}.rotate", *rotate)
        cmds.setAttr(f"{self.target}.scale", *scale)

    def reset_offsetParentMatrix(self, matrix=None):
        """
        Reset target offsetParentMatrix.

        matrix : matrice (16 valeurs) a ecrire, ou None pour l'identite.
        """

        if matrix is None:
            matrix = [
                1, 0, 0, 0,
                0, 1, 0, 0,
                0, 0, 1, 0,
                0, 0, 0, 1
            ]

        cmds.setAttr(f"{self.target}.offsetParentMatrix", matrix, type="matrix")

    # --------------------------------------------------
    # MAINTAIN OFFSET
    # --------------------------------------------------

    def create_mo(self):
        """
        Calcule (numériquement) l'offset de maintien de pose et le stocke
        dans un holdMatrix :

            offset = (target.worldMatrix * target.parentInverseMatrix)
                     * constraintOutput⁻¹
                   = target_local * outMatrix⁻¹   (= T_orig * ctrl.world⁻¹)

        Important : on LIT les valeurs (cmds.getAttr) au lieu de brancher
        self.outMatrix dans des nodes temporaires puis de les supprimer —
        cette suppression détruit en cascade le node amont de
        self.outMatrix tant qu'il n'a pas encore d'autre consommateur
        (connect_offParentMtx / connect_dcmpMtx tournent APRÈS).
        """

        if self.outMatrix is None:
            raise RuntimeError("No output matrix available.")

        target_world = om.MMatrix(cmds.getAttr(f"{self.target}.worldMatrix[0]"))
        target_parent_inverse = om.MMatrix(cmds.getAttr(f"{self.target}.parentInverseMatrix[0]"))
        constraint_output = om.MMatrix(cmds.getAttr(self.outMatrix))

        offset = (target_world * target_parent_inverse) * constraint_output.inverse()

        hold = cmds.createNode("holdMatrix", n=f"{self.target}_offset_hm")
        cmds.setAttr(f"{hold}.inMatrix", list(offset), type="matrix")

        self.nodes[f"{self.target}_holdMatrix"] = hold
        self.offset = hold

        return hold

    def connect_mo(self, hold):
        """
        Applique le maintain offset devant la sortie de la contrainte :

            outMatrix = offset * outMatrix

        avec offset = target.world * ctrl.world⁻¹ (calculé par create_mo).
        L'ordre compte : offset doit multiplier À GAUCHE, sinon au build
        target ne reste pas en place (offset * ctrl.world = T_orig).

        hold : noeud holdMatrix portant l'offset (voir create_mo()).
        """

        if not self.outMatrix:
            raise RuntimeError("outMatrix has not been initialized.")

        mult = cmds.createNode("multMatrix", n=f"{self.target}_offset_mm")
        self.nodes["maintainOffset_multMatrix"] = mult

        self._pre_mo_outMatrix = self.outMatrix

        cmds.connectAttr(f"{hold}.outMatrix", f"{mult}.matrixIn[0]", f=True)
        cmds.connectAttr(self.outMatrix, f"{mult}.matrixIn[1]", f=True)

        self.outMatrix = f"{mult}.matrixSum"

    def disconnect_mo(self):
        """Retire le maintain offset : supprime son multMatrix/holdMatrix, restaure la sortie brute."""

        key = "maintainOffset_multMatrix"

        if key not in self.nodes:
            return

        mult = self.nodes.pop(key)

        if cmds.objExists(mult):
            cmds.delete(mult)

        if self._pre_mo_outMatrix is not None:
            self.outMatrix = self._pre_mo_outMatrix
            self._pre_mo_outMatrix = None

        hold_key = f"{self.target}_holdMatrix"

        if hold_key in self.nodes:
            hold = self.nodes.pop(hold_key)

            if cmds.objExists(hold):
                cmds.delete(hold)

        self.offset = {}

    # --------------------------------------------------
    # OFFSET PARENT MATRIX
    # --------------------------------------------------

    def connect_offParentMtx(self):
        """Connect output matrix to target offsetParentMatrix, puis reset translate/rotate/scale du target."""

        if not self.outMatrix:
            raise RuntimeError("outMatrix has not been initialized.")

        cmds.connectAttr(self.outMatrix, f"{self.target}.offsetParentMatrix", f=True)

        self.reset_targetTransform()

    def disconnect_offParentMtx(self, ctrl=None):
        """
        Debranche outMatrix de target.offsetParentMatrix et restaure
        l'offsetParentMatrix/transform d'origine (voir get_target_data()).

        ctrl : non utilise (reserve pour un usage futur).
        """

        if not self.outMatrix:
            raise RuntimeError("outMatrix has not been initialized.")

        if cmds.isConnected(self.outMatrix, f"{self.target}.offsetParentMatrix"):
            cmds.disconnectAttr(self.outMatrix, f"{self.target}.offsetParentMatrix")

        self.reset_offsetParentMatrix(self.target_data["offsetParentMatrix"])

        self.reset_targetTransform(
            translate=self.target_data["translate"],
            rotate=self.target_data["rotate"],
            scale=self.target_data["scale"]
        )

    # --------------------------------------------------
    # DECOMPOSE MATRIX
    # --------------------------------------------------

    def connect_dcmpMtx(self, translate=True, rotate=True, scale=True):
        """
        Connect output matrix through decomposeMatrix vers le target, puis
        reset son offsetParentMatrix (identite).

        translate : connecter outputTranslate -> target.translate.
        rotate    : connecter outputRotate -> target.rotate.
        scale     : connecter outputScale -> target.scale.
        """

        if not self.outMatrix:
            raise RuntimeError("outMatrix has not been initialized.")

        dcmp = cmds.createNode("decomposeMatrix", n=f"{self.target}_dcmp")
        cmds.connectAttr(self.outMatrix, f"{dcmp}.inputMatrix", f=True)

        if translate:
            cmds.connectAttr(f"{dcmp}.outputTranslate", f"{self.target}.translate", f=True)

        if rotate:
            cmds.connectAttr(f"{dcmp}.outputRotate", f"{self.target}.rotate", f=True)

        if scale:
            cmds.connectAttr(f"{dcmp}.outputScale", f"{self.target}.scale", f=True)

        self.nodes[f"{self.target}_dcmpMtx"] = dcmp

        self.reset_offsetParentMatrix()

        return dcmp

    def disconnect_dcmpMtx(self):
        """Debranche et supprime le decomposeMatrix, restaure offsetParentMatrix/transform d'origine."""

        key = f"{self.target}_dcmpMtx"

        if key not in self.nodes:
            return

        dcmp = self.nodes.pop(key)

        for attr in ("translate", "rotate", "scale"):
            dst = f"{self.target}.{attr}"
            src = cmds.listConnections(dst, s=True, d=False, p=True)

            if src:
                cmds.disconnectAttr(src[0], dst)

        if cmds.objExists(dcmp):
            cmds.delete(dcmp)

        self.reset_offsetParentMatrix(self.target_data["offsetParentMatrix"])
        self.reset_targetTransform()

    # --------------------------------------------------
    # BUILD
    # --------------------------------------------------

    def build_mtx(self):
        """A implementer par chaque sous-classe : doit remplir self.outMatrix (plug matrice)."""
        raise NotImplementedError

    def build(self):
        """Orchestre le build complet : build_mtx(), puis maintain offset (si mo), puis connexion finale au target."""

        self.build_mtx()

        if self.mo and not self._mo_baked:
            hold = self.create_mo()
            self.connect_mo(hold)

        if self.dcmpMtx:
            self.connect_dcmpMtx()
        else:
            self.connect_offParentMtx()

    # --------------------------------------------------
    # DELETE
    # --------------------------------------------------

    def delete(self):
        """Debranche la contrainte (restaure le target) et supprime tous les noeuds crees."""

        try:
            if self.dcmpMtx:
                self.disconnect_dcmpMtx()
            else:
                self.disconnect_offParentMtx()
        except Exception:
            pass

        for node in list(self.nodes.values()):
            if cmds.objExists(node):
                cmds.delete(node)

        self.nodes.clear()
        self.offset = {}
        self.outMatrix = None


# --------------------------------------------------
# UTILITY
# --------------------------------------------------

def create_parent_space_matrix(ctrl, target, nodes, suffix="mm"):
    """
    Convert control world matrix to target parent space.

    CTRL WORLD
        *
    TARGET PARENT INVERSE
        =
    CTRL IN TARGET PARENT SPACE

    ctrl   : node dont on convertit le worldMatrix.
    target : node dont l'espace du PARENT est l'espace cible : on lit le
             worldInverseMatrix de son parent DAG (et non
             target.parentInverseMatrix, qui ferait lire le node piloté
             -> cycle, l'évaluation se fait par node). Sans parent : monde.
    nodes  : dict ou enregistrer le noeud cree (cle "{ctrl}_{suffix}").
    suffix : suffixe de nommage du multMatrix cree.
    """

    mult = cmds.createNode("multMatrix", n=f"{ctrl}_{suffix}")

    cmds.connectAttr(f"{ctrl}.worldMatrix[0]", f"{mult}.matrixIn[0]", f=True)

    parent = cmds.listRelatives(target, parent=True, fullPath=True)

    if parent:
        cmds.connectAttr(f"{parent[0]}.worldInverseMatrix[0]", f"{mult}.matrixIn[1]", f=True)

    nodes[f"{ctrl}_{suffix}"] = mult

    return f"{mult}.matrixSum"


def get_offset_matrix(node, reference):
    """
    Calcule numériquement (sans laisser de noeud dans la scène) la
    matrice de 'node' dans l'espace de 'reference' :

        offsetMatrix = node.worldMatrix * reference.worldInverseMatrix

    Passe par un multMatrix temporaire (plus simple/robuste qu'une
    inversion manuelle via l'API) dont la sortie est lue (cmds.getAttr)
    puis stockée dans une variable avant de supprimer le noeud.

    node      : node dont on lit le worldMatrix.
    reference : node dont on lit le worldInverseMatrix (espace cible).
    """

    mult = cmds.createNode("multMatrix", n=f"{node}_offset_temp_mm")

    cmds.connectAttr(f"{node}.worldMatrix[0]", f"{mult}.matrixIn[0]", f=True)
    cmds.connectAttr(f"{reference}.worldInverseMatrix[0]", f"{mult}.matrixIn[1]", f=True)

    offset_matrix = cmds.getAttr(f"{mult}.matrixSum")

    cmds.delete(mult)

    return offset_matrix


def remove_scale(matrix, target, nodes, name="noScale"):
    """
    pickMatrix sur 'matrix' (plug) qui ne garde que translation et rotation
    (scale et shear retirés). Retourne le plug de sortie.
    """

    pick = cmds.createNode("pickMatrix", n=f"{target}_{name}_pm")
    nodes[name] = pick

    cmds.connectAttr(matrix, f"{pick}.inputMatrix", f=True)
    cmds.setAttr(f"{pick}.useScale", 0)
    cmds.setAttr(f"{pick}.useShear", 0)

    return f"{pick}.outputMatrix"


def create_matrix_blend(matrices, target, nodes, name="blendMatrix"):
    """
    Blend matrices already existing in the same space (poids egaux).

    Le blendMatrix applique ses cibles en chaine : chaque target[i]
    interpole entre le resultat precedent et sa matrice. Pour une
    moyenne, la i-eme cible (2e matrice et suivantes) a donc un poids
    1/(i+2) : 1/2, 1/3, 1/4... (un poids de 1.0 ferait gagner la derniere).

    matrices : liste de plugs matrice (deja dans le meme espace).
    target   : node utilise pour nommer le blendMatrix cree.
    nodes    : dict ou enregistrer le noeud cree (cle 'name').
    name     : cle d'enregistrement dans 'nodes' / suffixe de nommage.
    """

    if not matrices:
        raise RuntimeError("No matrices supplied.")

    if len(matrices) == 1:
        return matrices[0]

    blend = cmds.createNode("blendMatrix", n=f"{target}_{name}_bm")
    nodes[name] = blend

    cmds.connectAttr(matrices[0], f"{blend}.inputMatrix", f=True)

    for i, matrix in enumerate(matrices[1:]):
        cmds.connectAttr(matrix, f"{blend}.target[{i}].targetMatrix", f=True)
        cmds.setAttr(f"{blend}.target[{i}].weight", 1.0 / (i + 2))

    return f"{blend}.outputMatrix"


# --------------------------------------------------
# PARENT CONSTRAINT
# --------------------------------------------------

class ParentCnstrMtx(MatrixCnstr):
    """Matrix parent constraint (translate + rotate, et scale si 'scale')."""

    def __init__(self, target, ctrls, mo=False, dcmpMtx=True, scale=True):
        """
        Voir MatrixCnstr.__init__.

        scale : le target suit aussi le scale des ctrls (matrices
                complètes). False : scale et shear retirés de la sortie
                (pickMatrix), et target.scale non connecté en dcmpMtx.
        """

        self.use_scale = scale

        super().__init__(target, ctrls, mo=mo, dcmpMtx=dcmpMtx)

    def build_mtx(self):
        """
        Dispatch vers _build_single() (1 ctrl) ou _build_multi() (plusieurs
        ctrls), puis retire le scale si 'scale' est False.
        """

        if len(self.ctrls) == 1:
            self._build_single()
        else:
            self._build_multi()

        if not self.use_scale:
            self.outMatrix = remove_scale(self.outMatrix, self.target, self.nodes, name="parentConstraint_noScale")

    def connect_dcmpMtx(self, translate=True, rotate=True, scale=True):
        """MatrixCnstr.connect_dcmpMtx, sans le scale si 'scale' est False."""

        return super().connect_dcmpMtx(translate=translate, rotate=rotate, scale=scale and self.use_scale)

    def _build_single(self):
        """1 ctrl : ctrl.world * parentTarget.worldInverse (le maintain
        offset est géré par mo=True)."""

        ctrl = self.ctrls[0]

        matrix = cmds.createNode("multMatrix", n=f"{ctrl}_parentConstraint_mm")
        self.nodes[f"{ctrl}_parentConstraint_mm"] = matrix

        cmds.connectAttr(f"{ctrl}.worldMatrix[0]", f"{matrix}.matrixIn[0]", f=True)

        if self.parent_target:
            cmds.connectAttr(
                f"{self.parent_target}.worldInverseMatrix[0]", f"{matrix}.matrixIn[1]", f=True
            )

        self.outMatrix = f"{matrix}.matrixSum"

    def _build_multi(self):
        """
        N ctrls :

        1. position du centre des ctrls -> holdMatrix.
        2. par ctrl : offset ctrl->centre = ctrl.world_build⁻¹ * centre
           -> holdMatrix.
        3. par ctrl : offset * ctrl.worldMatrix * parentTarget.worldInverse.
        4. mo=True : par ctrl, un multMatrix (avant le blend) qui préfixe
           la contrainte par l'offset de maintien de pose
           mo_i = target_local * M_i_build⁻¹  -> chaque ctrl vaut la pose
           du target au build, le target ne bouge donc pas.
        5. blend des matrices (poids égaux -> i-ème cible 1/(i+2)).

        mo=False -> le target se place au centre des ctrls.
        mo=True  -> il garde sa pose.
        """

        ctrl_worlds = [cmds.getAttr(f"{ctrl}.worldMatrix[0]") for ctrl in self.ctrls]
        count = len(ctrl_worlds)

        # 1. centre (position moyenne des ctrls, rotation identité)
        center = om.MMatrix([
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            sum(w[12] for w in ctrl_worlds) / count,
            sum(w[13] for w in ctrl_worlds) / count,
            sum(w[14] for w in ctrl_worlds) / count,
            1.0,
        ])

        center_hold = cmds.createNode("holdMatrix", n=f"{self.target}_parentConstraint_center_hm")
        cmds.setAttr(f"{center_hold}.inMatrix", list(center), type="matrix")
        self.nodes["parentConstraint_center"] = center_hold

        if self.mo:
            parent_inverse = om.MMatrix(cmds.getAttr(f"{self.target}.parentInverseMatrix[0]"))
            target_local = om.MMatrix(cmds.getAttr(f"{self.target}.worldMatrix[0]")) * parent_inverse
        else:
            parent_inverse = None

        # 2 + 3 (+ 4). offset par ctrl + contrainte + maintain offset
        matrices = []

        for ctrl, world in zip(self.ctrls, ctrl_worlds):

            world_mtx = om.MMatrix(world)
            offset = world_mtx.inverse() * center

            offset_hold = cmds.createNode("holdMatrix", n=f"{ctrl}_parentConstraint_offset_hm")
            cmds.setAttr(f"{offset_hold}.inMatrix", list(offset), type="matrix")
            self.nodes[f"{ctrl}_parentConstraint_offset_hm"] = offset_hold

            matrix = cmds.createNode("multMatrix", n=f"{ctrl}_parentConstraint_mm")
            self.nodes[f"{ctrl}_parentConstraint_mm"] = matrix

            cmds.connectAttr(f"{offset_hold}.outMatrix", f"{matrix}.matrixIn[0]", f=True)
            cmds.connectAttr(f"{ctrl}.worldMatrix[0]", f"{matrix}.matrixIn[1]", f=True)

            if self.parent_target:
                cmds.connectAttr(
                    f"{self.parent_target}.worldInverseMatrix[0]", f"{matrix}.matrixIn[2]", f=True
                )

            ctrl_plug = f"{matrix}.matrixSum"

            # 4. maintain offset par ctrl, AVANT le blend
            if self.mo:

                m_build = offset * world_mtx
                if parent_inverse is not None:
                    m_build = m_build * parent_inverse

                mo_offset = target_local * m_build.inverse()

                mo_hold = cmds.createNode("holdMatrix", n=f"{ctrl}_parentConstraint_mo_hm")
                cmds.setAttr(f"{mo_hold}.inMatrix", list(mo_offset), type="matrix")
                self.nodes[f"{ctrl}_parentConstraint_mo_hm"] = mo_hold

                mo_mm = cmds.createNode("multMatrix", n=f"{ctrl}_parentConstraint_mo_mm")
                self.nodes[f"{ctrl}_parentConstraint_mo_mm"] = mo_mm

                cmds.connectAttr(f"{mo_hold}.outMatrix", f"{mo_mm}.matrixIn[0]", f=True)
                cmds.connectAttr(f"{matrix}.matrixSum", f"{mo_mm}.matrixIn[1]", f=True)

                ctrl_plug = f"{mo_mm}.matrixSum"

            matrices.append(ctrl_plug)

        self._mo_baked = self.mo

        # 5. blend
        blend = cmds.createNode("blendMatrix", n=f"{self.target}_parentConstraint_bm")
        self.nodes["parentConstraint_blend"] = blend

        cmds.connectAttr(matrices[0], f"{blend}.inputMatrix", f=True)

        for i, matrix in enumerate(matrices[1:]):
            cmds.connectAttr(matrix, f"{blend}.target[{i}].targetMatrix", f=True)
            cmds.setAttr(f"{blend}.target[{i}].weight", 1.0 / (i + 2))

        self.outMatrix = f"{blend}.outputMatrix"


# --------------------------------------------------
# POINT CONSTRAINT
# --------------------------------------------------

class PointCnstrMtx(MatrixCnstr):
    """Matrix point constraint."""

    def build_mtx(self):
        """Blend la position (translate seul) des ctrls, dans l'espace du parent du target."""

        matrices = []

        for ctrl in self.ctrls:
            matrix = create_parent_space_matrix(ctrl, self.target, self.nodes, suffix="pointSpace_mm")
            matrices.append(matrix)

        output = create_matrix_blend(matrices, self.target, self.nodes, name="pointBlend")

        decompose = cmds.createNode("decomposeMatrix", n=f"{self.target}_point_dm")
        compose = cmds.createNode("composeMatrix", n=f"{self.target}_point_cm")

        self.nodes["point_decomposeMatrix"] = decompose
        self.nodes["point_composeMatrix"] = compose

        cmds.connectAttr(output, f"{decompose}.inputMatrix", f=True)
        cmds.connectAttr(f"{decompose}.outputTranslate", f"{compose}.inputTranslate", f=True)

        self.outMatrix = f"{compose}.outputMatrix"


# --------------------------------------------------
# ORIENT CONSTRAINT
# --------------------------------------------------

class OrientCnstrMtx(MatrixCnstr):
    """Matrix orient constraint."""

    def build_mtx(self):
        """Blend la rotation (rotate seul) des ctrls, dans l'espace du parent du target."""

        matrices = []

        for ctrl in self.ctrls:
            matrix = create_parent_space_matrix(ctrl, self.target, self.nodes, suffix="orientSpace_mm")
            matrices.append(matrix)

        output = create_matrix_blend(matrices, self.target, self.nodes, name="orientBlend")

        decompose = cmds.createNode("decomposeMatrix", n=f"{self.target}_orient_dm")
        compose = cmds.createNode("composeMatrix", n=f"{self.target}_orient_cm")

        self.nodes["orient_decomposeMatrix"] = decompose
        self.nodes["orient_composeMatrix"] = compose

        cmds.connectAttr(output, f"{decompose}.inputMatrix", f=True)
        cmds.connectAttr(f"{decompose}.outputRotate", f"{compose}.inputRotate", f=True)

        self.outMatrix = f"{compose}.outputMatrix"


# --------------------------------------------------
# SCALE CONSTRAINT
# --------------------------------------------------

class ScaleCnstrMtx(MatrixCnstr):

    """
    Matrix scale constraint : le target prend le scale (moyen) des ctrls,
    dans l'espace de son parent ; sa translation et sa rotation restent
    celles du build.

        dcmpMtx=True  : seul target.scale est connecté.
        dcmpMtx=False : offsetParentMatrix = translation / rotation du
                        target au build + scale des ctrls.
    """

    def build_mtx(self):
        """
        Scale des ctrls (blend, espace du parent du target) dans un
        composeMatrix dont translate / rotate sont ceux du target au build.
        """

        matrices = [
            create_parent_space_matrix(ctrl, self.target, self.nodes, suffix="scaleSpace_mm")
            for ctrl in self.ctrls
        ]

        output = create_matrix_blend(matrices, self.target, self.nodes, name="scaleBlend")

        decompose = cmds.createNode("decomposeMatrix", n=f"{self.target}_scale_dm")
        compose = cmds.createNode("composeMatrix", n=f"{self.target}_scale_cm")

        self.nodes["scale_decomposeMatrix"] = decompose
        self.nodes["scale_composeMatrix"] = compose

        cmds.connectAttr(output, f"{decompose}.inputMatrix", f=True)
        cmds.connectAttr(f"{decompose}.outputScale", f"{compose}.inputScale", f=True)

        # Translation / rotation du target au build (espace de son parent).
        local = om.MTransformationMatrix(
            om.MMatrix(cmds.getAttr(f"{self.target}.worldMatrix[0]"))
            * om.MMatrix(cmds.getAttr(f"{self.target}.parentInverseMatrix[0]"))
        )

        translation = local.translation(om.MSpace.kTransform)
        rotation = local.rotation()

        cmds.setAttr(f"{compose}.inputTranslate", translation.x, translation.y, translation.z)
        cmds.setAttr(
            f"{compose}.inputRotate",
            *[om.MAngle(angle).asDegrees() for angle in (rotation.x, rotation.y, rotation.z)]
        )

        self.outMatrix = f"{compose}.outputMatrix"

    def connect_dcmpMtx(self, translate=True, rotate=True, scale=True):
        """Scale seul : translate / rotate du target restent libres."""

        return super().connect_dcmpMtx(translate=False, rotate=False, scale=scale)


# --------------------------------------------------
# AIM CONSTRAINT
# --------------------------------------------------

class AimCnstrMtx(MatrixCnstr):
    """Matrix aim constraint."""

    def __init__(
        self,
        target,
        ctrls,
        worldUpObject=None,
        mo=False,
        dcmpMtx=True,
        aimVector=(0, 0, 1),
        upVector=(0, 1, 0),
        invertAimVector=False,
        invertUpVector=False
    ):
        """
        Stocke les parametres aim/up (en plus de ceux de MatrixCnstr) et
        appelle build(). Ne reutilise pas MatrixCnstr.__init__ car des
        attributs supplementaires doivent etre poses avant get_target_data()
        / build_mtx().

        target          : node pilote par la contrainte (vise 'ctrls').
        ctrls           : node (ou liste) dont la position moyenne definit
                           la direction a viser.
        worldUpObject   : node de reference pour le vecteur "up", ou None
                           pour un up monde par defaut (0, 1, 0).
        mo              : maintain offset (voir MatrixCnstr.__init__).
        dcmpMtx         : voir MatrixCnstr.__init__.
        aimVector       : axe local du target a aligner sur la direction visee.
        upVector        : axe local du target a aligner sur le vecteur "up".
        invertAimVector : inverse le vecteur aim calcule.
        invertUpVector  : inverse le vecteur up calcule.
        """

        self.target = target
        self.ctrls = ctrls if isinstance(ctrls, (list, tuple)) else [ctrls]

        self.worldUpObject = worldUpObject

        self.aimVector = aimVector
        self.upVector = upVector

        self.invertAimVector = invertAimVector
        self.invertUpVector = invertUpVector

        self.parents = self.get_ctrl_parents()
        self.parent_target = self.get_target_parent()
        self.target_data = self.get_target_data()

        self.mo = mo
        self.dcmpMtx = dcmpMtx

        self.outMatrix = None
        self._pre_mo_outMatrix = None
        self._mo_baked = False

        self.nodes = {}
        self.offset = {}

        self.build()

    # --------------------------------------------------
    # TARGET PROXY
    # --------------------------------------------------

    def create_target_proxy(self):
        """
        Cree un locator qui reprend la position/les connexions entrantes du
        target (translate/rotate/scale/offsetParentMatrix), puis reparente
        le target dessous - evite un cycle d'evaluation puisque build_mtx()
        lit le worldMatrix du target (via le proxy) pour se positionner.
        """

        proxy = cmds.createNode("locator", n=f"{self.target}_aim_ref_loc")

        if self.parent_target:
            cmds.parent(proxy, self.parent_target)

        cmds.matchTransform(proxy, self.target)

        attrs = (
            "translate", "translateX", "translateY", "translateZ",
            "rotate", "rotateX", "rotateY", "rotateZ",
            "scale", "scaleX", "scaleY", "scaleZ",
            "offsetParentMatrix"
        )

        for attr in attrs:

            dst = f"{self.target}.{attr}"

            if not cmds.objExists(dst):
                continue

            connections = cmds.listConnections(dst, s=True, d=False, p=True) or []

            for src in connections:
                cmds.disconnectAttr(src, dst)
                cmds.connectAttr(src, f"{proxy}.{attr}", f=True)

        cmds.parent(self.target, proxy)

        self.nodes["aimProxy"] = proxy

        return proxy

    # --------------------------------------------------
    # BUILD AIM MATRIX
    # --------------------------------------------------

    def build_mtx(self):
        """
        Construit la matrice aim : position du target (via le proxy),
        vecteur aim (target -> moyenne des ctrls), vecteur up (worldUpObject
        ou monde), vecteur right derive, inversions optionnelles, puis
        assemblage dans un fourByFourMatrix selon aimVector/upVector.
        """

        # TARGET POSITION
        proxy = self.create_target_proxy()

        target_dcmp = cmds.createNode("decomposeMatrix", n=f"{self.target}_target_dcmp")
        cmds.connectAttr(f"{proxy}.worldMatrix[0]", f"{target_dcmp}.inputMatrix", f=True)

        self.nodes["target_dcmp"] = target_dcmp

        # CONTROL AVERAGE
        ctrl_avg = cmds.createNode("plusMinusAverage", n=f"{self.target}_ctrlAverage_pma")
        cmds.setAttr(f"{ctrl_avg}.operation", 3)

        for i, ctrl in enumerate(self.ctrls):

            dcmp = cmds.createNode("decomposeMatrix", n=f"{ctrl}_aim_dcmp")

            cmds.connectAttr(f"{ctrl}.worldMatrix[0]", f"{dcmp}.inputMatrix", f=True)
            cmds.connectAttr(f"{dcmp}.outputTranslate", f"{ctrl_avg}.input3D[{i}]", f=True)

            self.nodes[f"{ctrl}_aim_dcmp"] = dcmp

        self.nodes["ctrlAverage"] = ctrl_avg

        # AIM VECTOR
        aim_pma = cmds.createNode("plusMinusAverage", n=f"{self.target}_aim_pma")
        cmds.setAttr(f"{aim_pma}.operation", 2)

        cmds.connectAttr(f"{target_dcmp}.outputTranslate", f"{aim_pma}.input3D[0]", f=True)
        cmds.connectAttr(f"{ctrl_avg}.output3D", f"{aim_pma}.input3D[1]", f=True)

        aim = cmds.createNode("vectorProduct", n=f"{self.target}_aim_vp")

        cmds.setAttr(f"{aim}.operation", 0)
        cmds.setAttr(f"{aim}.normalizeOutput", 1)

        cmds.connectAttr(f"{aim_pma}.output3D", f"{aim}.input1", f=True)

        self.nodes["aim_pma"] = aim_pma
        self.nodes["aim_vp"] = aim

        # WORLD UP
        if self.worldUpObject:

            up_dcmp = cmds.createNode("decomposeMatrix", n=f"{self.target}_worldUp_dcmp")

            cmds.connectAttr(f"{self.worldUpObject}.worldMatrix[0]", f"{up_dcmp}.inputMatrix", f=True)

            world_up_pma = cmds.createNode("plusMinusAverage", n=f"{self.target}_worldUp_pma")
            cmds.setAttr(f"{world_up_pma}.operation", 2)

            cmds.connectAttr(f"{up_dcmp}.outputTranslate", f"{world_up_pma}.input3D[0]", f=True)
            cmds.connectAttr(f"{target_dcmp}.outputTranslate", f"{world_up_pma}.input3D[1]", f=True)

            world_up_vector = cmds.createNode("vectorProduct", n=f"{self.target}_worldUp_vp")

            cmds.setAttr(f"{world_up_vector}.operation", 0)
            cmds.setAttr(f"{world_up_vector}.normalizeOutput", 1)

            cmds.connectAttr(f"{world_up_pma}.output3D", f"{world_up_vector}.input1", f=True)

            self.nodes["worldUp_dcmp"] = up_dcmp
            self.nodes["worldUp_pma"] = world_up_pma
            self.nodes["worldUp_vp"] = world_up_vector

        else:
            world_up_vector = None

        # RIGHT VECTOR
        right = cmds.createNode("vectorProduct", n=f"{self.target}_right_vp")

        cmds.setAttr(f"{right}.operation", 2)
        cmds.setAttr(f"{right}.normalizeOutput", 1)

        if world_up_vector:
            cmds.connectAttr(f"{world_up_vector}.output", f"{right}.input1", f=True)
        else:
            cmds.setAttr(f"{right}.input1", 0, 1, 0, type="double3")

        cmds.connectAttr(f"{aim}.output", f"{right}.input2", f=True)

        self.nodes["right_vp"] = right

        # CORRECTED UP
        up = cmds.createNode("vectorProduct", n=f"{self.target}_correctedUp_vp")

        cmds.setAttr(f"{up}.operation", 2)
        cmds.setAttr(f"{up}.normalizeOutput", 1)

        cmds.connectAttr(f"{aim}.output", f"{up}.input1", f=True)
        cmds.connectAttr(f"{right}.output", f"{up}.input2", f=True)

        self.nodes["up_vp"] = up

        # INVERT AIM
        if self.invertAimVector:

            aim_inv = cmds.createNode("multiplyDivide", n=f"{self.target}_aimInvert_md")

            cmds.setAttr(f"{aim_inv}.input2", -1, -1, -1, type="double3")
            cmds.connectAttr(f"{aim}.output", f"{aim_inv}.input1", f=True)

            aim_output = aim_inv
            self.nodes["aimInvert"] = aim_inv

        else:
            aim_output = aim

        # INVERT UP
        if self.invertUpVector:

            up_inv = cmds.createNode("multiplyDivide", n=f"{self.target}_upInvert_md")

            cmds.setAttr(f"{up_inv}.input2", -1, -1, -1, type="double3")
            cmds.connectAttr(f"{up}.output", f"{up_inv}.input1", f=True)

            up_output = up_inv
            self.nodes["upInvert"] = up_inv

        else:
            up_output = up

        # AXIS MAP
        aim_axis = tuple(int(v) for v in self.aimVector)
        up_axis = tuple(int(v) for v in self.upVector)

        aim_axis_key = tuple(abs(v) for v in aim_axis)
        up_axis_key = tuple(abs(v) for v in up_axis)

        if aim_axis_key == up_axis_key:
            raise ValueError("aimVector and upVector cannot use the same axis.")

        vectors = {"right": right, "up": up_output, "aim": aim_output}

        axis_map = {aim_axis_key: "aim", up_axis_key: "up"}

        all_axes = ((1, 0, 0), (0, 1, 0), (0, 0, 1))

        remaining_axis = next(axis for axis in all_axes if axis not in axis_map)
        axis_map[remaining_axis] = "right"

        # FOUR BY FOUR MATRIX
        matrix = cmds.createNode("fourByFourMatrix", n=f"{self.target}_fbfm")
        self.nodes["fourByFourMatrix"] = matrix

        column_map = {(1, 0, 0): 0, (0, 1, 0): 1, (0, 0, 1): 2}

        for axis, vector_name in axis_map.items():

            column = column_map[axis]
            node = vectors[vector_name]

            cmds.connectAttr(f"{node}.outputX", f"{matrix}.in0{column}", f=True)
            cmds.connectAttr(f"{node}.outputY", f"{matrix}.in1{column}", f=True)
            cmds.connectAttr(f"{node}.outputZ", f"{matrix}.in2{column}", f=True)

        # TRANSLATION
        cmds.connectAttr(f"{target_dcmp}.outputTranslateX", f"{matrix}.in03", f=True)
        cmds.connectAttr(f"{target_dcmp}.outputTranslateY", f"{matrix}.in13", f=True)
        cmds.connectAttr(f"{target_dcmp}.outputTranslateZ", f"{matrix}.in23", f=True)

        cmds.setAttr(f"{matrix}.in33", 1.0)

        # OUTPUT
        self.outMatrix = f"{matrix}.output"


# --------------------------------------------------
# POLE VECTOR CONSTRAINT
# --------------------------------------------------

class PoleVectorCnstr(MatrixCnstr):
    """
    Pole vector constraint en matrix. Le poleVector d'un ikHandle est lu
    dans l'espace du PARENT DE L'IKHANDLE (comme la contrainte native :
    constraintParentInverseMatrix = ikHandle.parentInverseMatrix) - pas
    dans celui du parent du start joint (décalé de sa rotation, ex : root
    joint d'un limb, orienté comme le premier joint).

        ctrl.worldMatrix * ikHandleParent.worldInverseMatrix
            -> blendMatrix si plusieurs ctrls                (create_matrix_blend)
            -> decomposeMatrix.outputTranslate
            -> plusMinusAverage : pole - start joint (même espace) (- offset si mo)
            -> ikHandle.poleVector

    Rien n'est lu sur le start joint ni sur l'ikHandle eux-mêmes (pilotés :
    cycle, évalué par node) : inverses lues sur leurs parents, position du
    start joint = son offsetParentMatrix * worldMatrix de son parent.

    La sortie n'est pas une transform mais un vecteur : build() est
    surcharge, offsetParentMatrix / decomposeMatrix vers le target ne
    sont pas utilises.
    """

    def __init__(self, target, ctrls, mo=False):
        """
        target : ikHandle (ikRPsolver) pilote par la contrainte.
        ctrls  : controleur (ou liste de controleurs) de pole vector.
        mo     : maintain offset - si True, l'ikHandle garde son poleVector
                 actuel au build au lieu de sauter sur le(s) ctrl(s).
        """

        if cmds.nodeType(target) != "ikHandle":
            raise RuntimeError(f"'{target}' n'est pas un ikHandle.")

        solver = cmds.listConnections(f"{target}.ikSolver") or []
        if not solver or cmds.nodeType(solver[0]) != "ikRPsolver":
            cmds.warning(f"'{target}' n'utilise pas un ikRPsolver : le pole vector n'aura pas d'effet.")

        self.start_joint = cmds.listConnections(f"{target}.startJoint")[0]
        self.vector = None

        super().__init__(target, ctrls, mo=mo, dcmpMtx=False)

    # --------------------------------------------------
    # GET DATA
    # --------------------------------------------------

    def get_target_data(self):
        """Ajoute le poleVector initial aux donnees de MatrixCnstr."""

        data = super().get_target_data()
        data["poleVector"] = cmds.getAttr(f"{self.target}.poleVector")[0]

        return data

    # --------------------------------------------------
    # BUILD
    # --------------------------------------------------

    def get_pole_space(self):
        """Parent DAG de l'ikHandle (espace du poleVector), ou None s'il est au monde."""

        parent = cmds.listRelatives(self.target, parent=True, fullPath=True)

        return parent[0] if parent else None

    def to_pole_space(self, matrix_plug, name):
        """multMatrix : 'matrix_plug' (monde) * worldInverseMatrix du parent de l'ikHandle."""

        mult = cmds.createNode("multMatrix", n=f"{self.target}_{name}")
        cmds.connectAttr(matrix_plug, f"{mult}.matrixIn[0]", f=True)

        parent = self.get_pole_space()

        if parent:
            cmds.connectAttr(f"{parent}.worldInverseMatrix[0]", f"{mult}.matrixIn[1]", f=True)

        self.nodes[name] = mult

        return f"{mult}.matrixSum"

    def build_mtx(self):
        """Matrice du/des ctrl(s) dans l'espace du parent de l'ikHandle."""

        matrices = [
            self.to_pole_space(f"{ctrl}.worldMatrix[0]", f"{ctrl.split('|')[-1]}_pv_mm")
            for ctrl in self.ctrls
        ]

        self.outMatrix = create_matrix_blend(matrices, self.target, self.nodes, name="pv_blendMatrix")

    def build_vector(self):
        """
        Vecteur pole = position du pole - position du start joint, dans
        l'espace du parent de l'ikHandle. Position monde du start joint :
        son offsetParentMatrix (sa source si elle est connectée, sinon sa
        valeur - joint figé, translate à 0) * worldMatrix de son parent.
        """

        if not self.outMatrix:
            raise RuntimeError("outMatrix has not been initialized.")

        dcmp = cmds.createNode("decomposeMatrix", n=f"{self.target}_pv_dcmp")
        cmds.connectAttr(self.outMatrix, f"{dcmp}.inputMatrix", f=True)
        self.nodes["pv_dcmpMtx"] = dcmp

        start_world = cmds.createNode("multMatrix", n=f"{self.target}_pv_start_world_mm")
        self.nodes["pv_start_world_multMatrix"] = start_world

        source = cmds.listConnections(f"{self.start_joint}.offsetParentMatrix", source=True, destination=False, plugs=True)

        if source:
            cmds.connectAttr(source[0], f"{start_world}.matrixIn[0]", f=True)
        else:
            cmds.setAttr(f"{start_world}.matrixIn[0]", cmds.getAttr(f"{self.start_joint}.offsetParentMatrix"), type="matrix")

        start_parent = cmds.listRelatives(self.start_joint, parent=True, fullPath=True)

        if start_parent:
            cmds.connectAttr(f"{start_parent[0]}.worldMatrix[0]", f"{start_world}.matrixIn[1]", f=True)

        start_dcmp = cmds.createNode("decomposeMatrix", n=f"{self.target}_pv_start_dcmp")
        cmds.connectAttr(self.to_pole_space(f"{start_world}.matrixSum", "pv_start_mm"), f"{start_dcmp}.inputMatrix", f=True)
        self.nodes["pv_start_dcmpMtx"] = start_dcmp

        sub = cmds.createNode("plusMinusAverage", n=f"{self.target}_pv_pma")
        cmds.setAttr(f"{sub}.operation", 2)  # Subtract : in[0] - in[1] - in[2]
        cmds.connectAttr(f"{dcmp}.outputTranslate", f"{sub}.input3D[0]", f=True)
        cmds.connectAttr(f"{start_dcmp}.outputTranslate", f"{sub}.input3D[1]", f=True)
        self.nodes["pv_minus"] = sub

        self.vector = f"{sub}.output3D"

        return self.vector

    def check_side(self):

        """
        Diagnostic : warning si le vecteur calculé vers le(s) ctrl(s) est
        opposé (angle > 90°) au poleVector de l'ikHandle au build (plan de
        la chaîne au repos) - la chaîne se retournerait en connectant la
        contrainte.
        """

        computed = om.MVector(cmds.getAttr(self.vector)[0])
        current = om.MVector(self.target_data["poleVector"])

        if computed.length() < 1e-6 or current.length() < 1e-6:
            return

        angle = om.MAngle(computed.angle(current)).asDegrees()

        if angle > 90.0:
            cmds.warning(
                f"PoleVectorCnstr '{self.target}' : vecteur vers le pole à {angle:.0f}° du plan de la "
                "chaîne au repos - la chaîne va se retourner (pole du mauvais côté ?)."
            )

    def delete_native_cnstr(self):
        """Supprime un eventuel poleVectorConstraint classique deja sur l'ikHandle."""

        old = cmds.listConnections(self.target, type="poleVectorConstraint") or []

        if old:
            cmds.delete(list(set(old)))

    def connect_poleVector(self):
        """Branche le vecteur dans ikHandle.poleVector."""

        if not self.vector:
            raise RuntimeError("vector has not been initialized.")

        cmds.connectAttr(self.vector, f"{self.target}.poleVector", f=True)

    def build(self):
        """build_mtx(), vecteur, maintain offset (si mo), puis connexion au poleVector."""

        self.delete_native_cnstr()

        self.build_mtx()
        self.build_vector()

        self.check_side()

        if self.mo and not self._mo_baked:
            offset = self.create_mo()
            self.connect_mo(offset)

        self.connect_poleVector()

    # --------------------------------------------------
    # MAINTAIN OFFSET
    # --------------------------------------------------

    def create_mo(self):
        """
        Offset vectoriel (pas de holdMatrix ici) :

            offset = vecteur calcule - poleVector initial

        Soustrait en input3D[2], au build : vecteur - offset = poleVector initial.
        """

        if not self.vector:
            raise RuntimeError("vector has not been initialized.")

        computed = om.MVector(cmds.getAttr(self.vector)[0])
        current = om.MVector(self.target_data["poleVector"])

        return computed - current

    def connect_mo(self, offset):
        """offset : MVector (voir create_mo()), ecrit dans input3D[2] du plusMinusAverage."""

        sub = self.nodes["pv_minus"]
        cmds.setAttr(f"{sub}.input3D[2]", offset.x, offset.y, offset.z)

        self.offset = offset

    def disconnect_mo(self):
        """Retire le maintain offset (input3D[2] remis a zero)."""

        sub = self.nodes.get("pv_minus")

        if sub and cmds.objExists(sub):
            cmds.setAttr(f"{sub}.input3D[2]", 0, 0, 0)

        self.offset = {}

    # --------------------------------------------------
    # DELETE
    # --------------------------------------------------

    def delete(self):
        """Debranche le poleVector, restaure sa valeur initiale et supprime les noeuds crees."""

        dst = f"{self.target}.poleVector"

        if self.vector and cmds.objExists(self.vector.split(".")[0]) and cmds.isConnected(self.vector, dst):
            cmds.disconnectAttr(self.vector, dst)

        cmds.setAttr(dst, *self.target_data["poleVector"])

        for node in list(self.nodes.values()):
            if cmds.objExists(node):
                cmds.delete(node)

        self.nodes.clear()
        self.offset = {}
        self.outMatrix = None
        self.vector = None
