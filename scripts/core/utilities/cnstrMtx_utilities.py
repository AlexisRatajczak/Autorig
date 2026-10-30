# ====================================================================================================================
# CNSTRMTX UTILITIES
# ====================================================================================================================
#
#   MATRIXCNSTR (base class of ParentCnstrMtx / PointCnstrMtx / OrientCnstrMtx / ScaleCnstrMtx / AimCnstrMtx /
#   PoleVectorCnstr)
#       __init__(target, ctrls, mo=False, dcmpMtx=True)     - store the settings, call build()
#       get_target_data()                                   - initial target transform
#       get_ctrl_parents()                                  - current DAG parent of each ctrl
#       get_target_parent()                                 - current DAG parent of the target
#       reset_targetTransform(translate, rotate, scale)     - reset the target channels
#       reset_offsetParentMatrix(matrix=None)               - reset offsetParentMatrix (identity by default)
#       create_mo()                                         - maintain offset (holdMatrix)
#       connect_mo(hold)                                    - put the offset before the constraint output
#       disconnect_mo()                                     - remove the maintain offset
#       connect_offParentMtx()                              - output -> target.offsetParentMatrix
#       disconnect_offParentMtx(ctrl=None)                  - disconnect + restore the original transform
#       connect_dcmpMtx(translate, rotate, scale)           - output through a decomposeMatrix
#       disconnect_dcmpMtx()                                - disconnect the decomposeMatrix + restore
#       build_mtx()                                         - [subclasses]
#       build()                                             - build_mtx() + mo + dcmpMtx / offsetParentMatrix
#       delete()                                            - disconnect and delete the created nodes
#   UTILITY (module functions)
#       create_parent_space_matrix(ctrl, target, nodes, suffix) - ctrl matrix in the target DAG parent space
#       get_offset_matrix(node, reference)                  - node.worldMatrix * reference.worldInverseMatrix (value)
#       remove_scale(matrix, target, nodes, name)           - pickMatrix: translate + rotate only
#       create_matrix_blend(matrices, target, nodes, name)  - average of N matrices in the same space
#   PARENTCNSTRMTX(MatrixCnstr)
#       __init__(target, ctrls, mo, dcmpMtx, scale=True)    - scale: follow the ctrls scale too
#       build_mtx()                                         - single / multi from the ctrl count
#       connect_dcmpMtx(translate, rotate, scale)           - no target.scale when scale=False
#       _build_single()                                     - 1 ctrl: ctrl.world * parentTarget.worldInverse
#       _build_multi()                                      - N ctrls: center + offsets + weighted blend
#   POINTCNSTRMTX(MatrixCnstr)        build_mtx() - position blend (translate only)
#   ORIENTCNSTRMTX(MatrixCnstr)       build_mtx() - rotation blend (rotate only)
#   SCALECNSTRMTX(MatrixCnstr)
#       build_mtx()                                         - ctrls scale, build translate / rotate
#       connect_dcmpMtx(translate, rotate, scale)           - target.scale only
#   AIMCNSTRMTX(MatrixCnstr)
#       __init__(target, ctrls, worldUpObject, mo, dcmpMtx, ...) - aim / up settings, call build()
#       create_target_proxy()                               - proxy locator taking over the target (no cycle)
#       build_mtx()                                         - aim matrix (vectors + fourByFourMatrix)
#   POLEVECTORCNSTR(MatrixCnstr)
#       __init__(target, ctrls, mo=False)                   - target = ikHandle (ikRPsolver)
#       get_target_data()                                   - + initial poleVector
#       get_pole_space()                                    - ikHandle DAG parent (poleVector space)
#       to_pole_space(matrix_plug, name)                    - world matrix -> ikHandle parent space
#       build_mtx()                                         - ctrl(s) in the ikHandle parent space
#       build_vector()                                      - pole - start joint, same space
#       check_side()                                        - warning if the pole is on the wrong side
#       delete_native_cnstr()                               - delete an existing native poleVectorConstraint
#       connect_poleVector()                                - vector -> ikHandle.poleVector
#       build()                                             - build_mtx() + vector + mo + connection
#       create_mo() / connect_mo(offset) / disconnect_mo()  - vector maintain offset (input3D[2])
#       delete()                                            - disconnect, restore the poleVector, delete the nodes
#
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
        Store the settings, capture the initial target / ctrls state, then build()
        (build_mtx() is implemented by each subclass).

        target  : driven node.
        ctrls   : driver node (or list).
        mo      : maintain offset: the target keeps its build pose.
        dcmpMtx : True: output through a decomposeMatrix to translate / rotate /
                  scale; False: straight into offsetParentMatrix.
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
        """{ctrl: parent}: current DAG parent of each ctrl."""

        parents = {}

        for ctrl in self.ctrls:
            parent = cmds.listRelatives(ctrl, parent=True, fullPath=True)
            parents[ctrl] = parent[0] if parent else None

        return parents

    def get_target_parent(self):
        """Current DAG parent of the target, or None."""

        parent = cmds.listRelatives(self.target, parent=True, fullPath=True)

        return parent[0] if parent else None

    # --------------------------------------------------
    # RESET TRANSFORM
    # --------------------------------------------------

    def reset_targetTransform(self, translate=(0, 0, 0), rotate=(0, 0, 0), scale=(1, 1, 1)):
        """Set the target translate / rotate / scale."""

        cmds.setAttr(f"{self.target}.translate", *translate)
        cmds.setAttr(f"{self.target}.rotate", *rotate)
        cmds.setAttr(f"{self.target}.scale", *scale)

    def reset_offsetParentMatrix(self, matrix=None):
        """Set the target offsetParentMatrix ('matrix', identity by default)."""

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
        Compute the maintain offset as a value and store it in a holdMatrix:

            offset = (target.worldMatrix * target.parentInverseMatrix) * constraintOutput^-1

        Values are READ (cmds.getAttr): connecting self.outMatrix to temporary nodes
        then deleting them would cascade-delete its upstream node.
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
        Put the maintain offset before the constraint output:

            outMatrix = offset * outMatrix

        The offset multiplies on the LEFT, else the target moves at build time.

        hold : holdMatrix holding the offset (create_mo()).
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
        """Remove the maintain offset: delete its nodes, restore the raw output."""

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
        """Output matrix -> target offsetParentMatrix, then reset the target channels."""

        if not self.outMatrix:
            raise RuntimeError("outMatrix has not been initialized.")

        cmds.connectAttr(self.outMatrix, f"{self.target}.offsetParentMatrix", f=True)

        self.reset_targetTransform()

    def disconnect_offParentMtx(self, ctrl=None):
        """Disconnect the output from target.offsetParentMatrix and restore the original transform ('ctrl' unused)."""

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
        """Output matrix through a decomposeMatrix to the chosen target channels, offsetParentMatrix reset."""

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
        """Disconnect and delete the decomposeMatrix, restore the original transform."""

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
        """Implemented by each subclass: fills self.outMatrix (matrix plug)."""
        raise NotImplementedError

    def build(self):
        """build_mtx(), maintain offset (if mo), then the final connection to the target."""

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
        """Disconnect the constraint (target restored) and delete every created node."""

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
    Control world matrix in the target parent space:
    ctrl.worldMatrix * targetParent.worldInverseMatrix.

    The DAG parent worldInverseMatrix is read, not target.parentInverseMatrix
    (reading the driven node would cycle). No parent: world.

    nodes  : dict receiving the created node ("{ctrl}_{suffix}").
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
    Matrix of 'node' in 'reference' space, as a value (temporary multMatrix,
    deleted): node.worldMatrix * reference.worldInverseMatrix.
    """

    mult = cmds.createNode("multMatrix", n=f"{node}_offset_temp_mm")

    cmds.connectAttr(f"{node}.worldMatrix[0]", f"{mult}.matrixIn[0]", f=True)
    cmds.connectAttr(f"{reference}.worldInverseMatrix[0]", f"{mult}.matrixIn[1]", f=True)

    offset_matrix = cmds.getAttr(f"{mult}.matrixSum")

    cmds.delete(mult)

    return offset_matrix


def remove_scale(matrix, target, nodes, name="noScale"):
    """pickMatrix on 'matrix' keeping translation and rotation only. Returns its output plug."""

    pick = cmds.createNode("pickMatrix", n=f"{target}_{name}_pm")
    nodes[name] = pick

    cmds.connectAttr(matrix, f"{pick}.inputMatrix", f=True)
    cmds.setAttr(f"{pick}.useScale", 0)
    cmds.setAttr(f"{pick}.useShear", 0)

    return f"{pick}.outputMatrix"


def create_matrix_blend(matrices, target, nodes, name="blendMatrix"):
    """
    Average of matrices already in the same space. The blendMatrix chains its
    targets, so the i-th target (2nd matrix on) weighs 1 / (i + 2).

    nodes : dict receiving the created node ('name').
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
    """Matrix parent constraint (translate + rotate, and scale with 'scale')."""

    def __init__(self, target, ctrls, mo=False, dcmpMtx=True, scale=True):
        """
        See MatrixCnstr.__init__.

        scale : follow the ctrls scale too. False: scale and shear removed from the
                output (pickMatrix), target.scale not connected in dcmpMtx mode.
        """

        self.use_scale = scale

        super().__init__(target, ctrls, mo=mo, dcmpMtx=dcmpMtx)

    def build_mtx(self):
        """_build_single() (1 ctrl) or _build_multi(), then remove the scale if 'scale' is False."""

        if len(self.ctrls) == 1:
            self._build_single()
        else:
            self._build_multi()

        if not self.use_scale:
            self.outMatrix = remove_scale(self.outMatrix, self.target, self.nodes, name="parentConstraint_noScale")

    def connect_dcmpMtx(self, translate=True, rotate=True, scale=True):
        """MatrixCnstr.connect_dcmpMtx, without scale when 'scale' is False."""

        return super().connect_dcmpMtx(translate=translate, rotate=rotate, scale=scale and self.use_scale)

    def _build_single(self):
        """1 ctrl: ctrl.world * parentTarget.worldInverse (offset handled by mo)."""

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
        N ctrls:

        1. ctrls center -> holdMatrix.
        2. per ctrl: ctrl -> center offset = ctrl.world_build^-1 * center -> holdMatrix.
        3. per ctrl: offset * ctrl.worldMatrix * parentTarget.worldInverse.
        4. mo: per ctrl, before the blend, mo_i = target_local * M_i_build^-1.
        5. blend (equal weights: i-th target 1 / (i + 2)).

        mo=False: the target goes to the ctrls center; mo=True: it keeps its pose.
        """

        ctrl_worlds = [cmds.getAttr(f"{ctrl}.worldMatrix[0]") for ctrl in self.ctrls]
        count = len(ctrl_worlds)

        # 1. center (mean ctrl position, identity rotation)
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

        # 2 + 3 (+ 4). offset per ctrl + constraint + maintain offset
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

            # 4. maintain offset per ctrl, BEFORE the blend
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
        """Blend the ctrls position (translate only) in the target parent space."""

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
        """Blend the ctrls rotation (rotate only) in the target parent space."""

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
    Matrix scale constraint: the target takes the (mean) ctrls scale in its
    parent space; translation and rotation stay at their build value.

        dcmpMtx=True  : only target.scale is connected.
        dcmpMtx=False : offsetParentMatrix = build translation / rotation + ctrls scale.
    """

    def build_mtx(self):
        """Ctrls scale (blend, target parent space) in a composeMatrix with the build translate / rotate."""

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

        # Target translation / rotation at build time (parent space).
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
        """Scale only: target translate / rotate stay free."""

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
        Store the aim / up settings and build(). Does not call MatrixCnstr.__init__:
        extra attributes are needed before get_target_data() / build_mtx().

        target          : driven node (aims at 'ctrls').
        ctrls           : node (or list) whose mean position is aimed at.
        worldUpObject   : up reference node, or None for world up (0, 1, 0).
        aimVector       : target local axis aligned on the aim direction.
        upVector        : target local axis aligned on the up vector.
        invertAimVector : invert the computed aim vector.
        invertUpVector  : invert the computed up vector.
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
        Locator taking over the target position and incoming connections, the
        target parented under it: build_mtx() reads the proxy, no cycle.
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
        Aim matrix: target position (proxy), aim vector (target -> ctrls mean), up
        vector (worldUpObject or world), derived right vector, optional inversions,
        assembled in a fourByFourMatrix from aimVector / upVector.
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
    Matrix pole vector constraint. The ikHandle poleVector lives in the
    IKHANDLE PARENT space (like the native constraint), not the start joint
    parent space.

        ctrl.worldMatrix * ikHandleParent.worldInverseMatrix
            -> blendMatrix with several ctrls        (create_matrix_blend)
            -> decomposeMatrix.outputTranslate
            -> plusMinusAverage: pole - start joint (same space) (- offset if mo)
            -> ikHandle.poleVector

    Nothing is read on the start joint or the ikHandle (driven: cycle): start
    joint position = its offsetParentMatrix * parent worldMatrix. The output is
    a vector: build() is overridden.
    """

    def __init__(self, target, ctrls, mo=False):
        """
        target : ikHandle (ikRPsolver).
        ctrls  : pole ctrl (or list).
        mo     : maintain offset: the ikHandle keeps its current poleVector.
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
        """MatrixCnstr data + the initial poleVector."""

        data = super().get_target_data()
        data["poleVector"] = cmds.getAttr(f"{self.target}.poleVector")[0]

        return data

    # --------------------------------------------------
    # BUILD
    # --------------------------------------------------

    def get_pole_space(self):
        """ikHandle DAG parent (poleVector space), or None at the world."""

        parent = cmds.listRelatives(self.target, parent=True, fullPath=True)

        return parent[0] if parent else None

    def to_pole_space(self, matrix_plug, name):
        """multMatrix: 'matrix_plug' (world) * ikHandle parent worldInverseMatrix."""

        mult = cmds.createNode("multMatrix", n=f"{self.target}_{name}")
        cmds.connectAttr(matrix_plug, f"{mult}.matrixIn[0]", f=True)

        parent = self.get_pole_space()

        if parent:
            cmds.connectAttr(f"{parent}.worldInverseMatrix[0]", f"{mult}.matrixIn[1]", f=True)

        self.nodes[name] = mult

        return f"{mult}.matrixSum"

    def build_mtx(self):
        """Ctrl(s) matrix in the ikHandle parent space."""

        matrices = [
            self.to_pole_space(f"{ctrl}.worldMatrix[0]", f"{ctrl.split('|')[-1]}_pv_mm")
            for ctrl in self.ctrls
        ]

        self.outMatrix = create_matrix_blend(matrices, self.target, self.nodes, name="pv_blendMatrix")

    def build_vector(self):
        """
        Pole vector = pole position - start joint position, in the ikHandle parent
        space. Start joint world position: its offsetParentMatrix (source or value)
        * parent worldMatrix.
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
        Warning if the computed vector is opposite (> 90 degrees) to the build
        poleVector: the chain would flip when connecting.
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
        """Delete a native poleVectorConstraint already on the ikHandle."""

        old = cmds.listConnections(self.target, type="poleVectorConstraint") or []

        if old:
            cmds.delete(list(set(old)))

    def connect_poleVector(self):
        """Vector -> ikHandle.poleVector."""

        if not self.vector:
            raise RuntimeError("vector has not been initialized.")

        cmds.connectAttr(self.vector, f"{self.target}.poleVector", f=True)

    def build(self):
        """build_mtx(), vector, maintain offset (if mo), then the poleVector connection."""

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
        Vector offset (no holdMatrix): offset = computed vector - initial poleVector,
        subtracted in input3D[2]: at build, vector - offset = initial poleVector.
        """

        if not self.vector:
            raise RuntimeError("vector has not been initialized.")

        computed = om.MVector(cmds.getAttr(self.vector)[0])
        current = om.MVector(self.target_data["poleVector"])

        return computed - current

    def connect_mo(self, offset):
        """'offset' (MVector, create_mo()) written in the plusMinusAverage input3D[2]."""

        sub = self.nodes["pv_minus"]
        cmds.setAttr(f"{sub}.input3D[2]", offset.x, offset.y, offset.z)

        self.offset = offset

    def disconnect_mo(self):
        """Remove the maintain offset (input3D[2] reset)."""

        sub = self.nodes.get("pv_minus")

        if sub and cmds.objExists(sub):
            cmds.setAttr(f"{sub}.input3D[2]", 0, 0, 0)

        self.offset = {}

    # --------------------------------------------------
    # DELETE
    # --------------------------------------------------

    def delete(self):
        """Disconnect the poleVector, restore its initial value, delete the created nodes."""

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
