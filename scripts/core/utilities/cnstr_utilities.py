# ====================================================================================================================
# CNSTR UTILITIES
# ====================================================================================================================
#
#   Classic (native Maya) constraints with the same interface as the cnstrMtx_utilities matrix constraints (same
#   constructor arguments, build() / delete()), and the factory switching between both: a module builds any
#   constraint through create_constraint(kind, ..., method) whatever the method.
#
#   CNSTR (base class of ParentCnstr / PointCnstr / OrientCnstr / ScaleCnstr / AimCnstr / PoleVectorCnstr)
#       __init__(target, ctrls, mo=False, dcmpMtx=True)     - store the settings, call build() (dcmpMtx unused)
#       prepare_target()                                    - baked offsetParentMatrix back to the channels
#       get_flags()                                         - [subclasses] extra flags of the Maya command
#       build()                                             - prepare_target() + native constraint(s)
#       delete()                                            - delete the constraint nodes
#   PARENTCNSTR(Cnstr)     __init__(target, ctrls, mo, dcmpMtx, scale=True) - parentConstraint (+ scaleConstraint)
#   POINTCNSTR(Cnstr)      pointConstraint
#   ORIENTCNSTR(Cnstr)     orientConstraint
#   SCALECNSTR(Cnstr)      scaleConstraint
#   AIMCNSTR(Cnstr)        __init__(target, ctrls, worldUpObject, mo, dcmpMtx, aimVector, upVector, invertAimVector,
#                          invertUpVector) - aimConstraint
#   POLEVECTORCNSTR(Cnstr) __init__(target, ctrls, mo=False) - poleVectorConstraint (target = ikHandle)
#   UTILITY
#       bake_offset_to_channels(node)                       - offsetParentMatrix -> translate / rotate (jointOrient)
#                                                             / scale, same world pose
#       remove_constraints(node)                            - drop the matrix (offsetParentMatrix) and classic
#                                                             constraints driving a node
#   FACTORY
#       METHODS                                             - ("Matrix", "Classic")
#       get_constraint_class(kind, method)                  - class of a constraint kind for a method
#       create_constraint(kind, target, ctrls, method, **kwargs) - build it
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from . import cnstrMtx_utilities

from importlib import reload

reload(cnstrMtx_utilities)


IDENTITY = list(om.MMatrix())


# --------------------------------------------------
# UTILITY
# --------------------------------------------------

def bake_offset_to_channels(node):

    """
    Native constraints ignore the offsetParentMatrix: move the full local transform
    of 'node' (channels + offsetParentMatrix) back to its channels, offsetParentMatrix
    reset to identity, same world pose. Joints: rotation in jointOrient (rotate 0).
    Skipped when the offsetParentMatrix is identity or driven.
    """

    if cmds.listConnections(f"{node}.offsetParentMatrix", source=True, destination=False):
        return

    if om.MMatrix(cmds.getAttr(f"{node}.offsetParentMatrix")).isEquivalent(om.MMatrix()):
        return

    local = om.MTransformationMatrix(
        om.MMatrix(cmds.getAttr(f"{node}.worldMatrix[0]"))
        * om.MMatrix(cmds.getAttr(f"{node}.parentInverseMatrix[0]"))
    )

    translation = local.translation(om.MSpace.kTransform)
    scale = local.scale(om.MSpace.kTransform)

    cmds.setAttr(f"{node}.offsetParentMatrix", IDENTITY, type="matrix")

    cmds.setAttr(f"{node}.translate", translation.x, translation.y, translation.z)
    cmds.setAttr(f"{node}.scale", *scale)

    if cmds.nodeType(node) == "joint":

        rotation = local.rotation()

        cmds.setAttr(f"{node}.rotate", 0, 0, 0)
        cmds.setAttr(f"{node}.jointOrient", *[om.MAngle(angle).asDegrees() for angle in (rotation.x, rotation.y, rotation.z)])

        return

    rotation = local.rotation()
    rotation.reorderIt(cmds.getAttr(f"{node}.rotateOrder"))

    cmds.setAttr(f"{node}.rotate", *[om.MAngle(angle).asDegrees() for angle in (rotation.x, rotation.y, rotation.z)])


def remove_constraints(node):

    """
    Remove what constrains 'node', matrix or classic: offsetParentMatrix input
    disconnected (identity), native constraint nodes deleted. The node then sits
    on its own channels (re-place it before constraining it again).
    """

    for source in cmds.listConnections(f"{node}.offsetParentMatrix", source=True, destination=False, plugs=True) or []:
        cmds.disconnectAttr(source, f"{node}.offsetParentMatrix")

    cmds.setAttr(f"{node}.offsetParentMatrix", IDENTITY, type="matrix")

    constraints = set(cmds.listConnections(node, type="constraint", source=True, destination=False) or [])

    if constraints:
        cmds.delete(list(constraints))


# --------------------------------------------------
# CLASSIC CONSTRAINT BASE
# --------------------------------------------------

class Cnstr(object):
    """Classic constraint base: same interface as cnstrMtx_utilities.MatrixCnstr."""

    # Maya constraint command (cmds.parentConstraint...) and node suffix.
    COMMAND = None
    SUFFIX = "constraint"

    def __init__(self, target, ctrls, mo=False, dcmpMtx=True):
        """
        Store the settings, then build().

        target  : driven node.
        ctrls   : driver node (or list).
        mo      : maintain offset: the target keeps its build pose.
        dcmpMtx : unused (matrix constraints only), kept for the shared interface.
        """

        self.target = target
        self.ctrls = list(ctrls) if isinstance(ctrls, (list, tuple)) else [ctrls]

        self.mo = mo
        self.dcmpMtx = dcmpMtx

        self.constraints = []
        self.nodes = {}

        self.build()

    def prepare_target(self):
        """Baked offsetParentMatrix back to the channels (bake_offset_to_channels)."""

        bake_offset_to_channels(self.target)

    def get_flags(self):
        """Extra flags of the Maya command (subclasses)."""
        return {}

    def create(self, command, suffix, **flags):
        """One native constraint '{target}_{suffix}' from the ctrls. Returns its node."""

        name = f"{self.target.split('|')[-1]}_{suffix}"

        node = command(*self.ctrls, self.target, name=name, **flags)[0]

        self.constraints.append(node)
        self.nodes[suffix] = node

        return node

    def build(self):
        """prepare_target() then the native constraint."""

        self.prepare_target()

        self.create(self.COMMAND, self.SUFFIX, maintainOffset=bool(self.mo), **self.get_flags())

    def delete(self):
        """Delete every created constraint node."""

        for node in self.constraints:
            if cmds.objExists(node):
                cmds.delete(node)

        self.constraints = []
        self.nodes.clear()


# --------------------------------------------------
# CLASSIC CONSTRAINTS
# --------------------------------------------------

class ParentCnstr(Cnstr):
    """parentConstraint, + scaleConstraint with 'scale' (ParentCnstrMtx interface)."""

    COMMAND = cmds.parentConstraint
    SUFFIX = "parentConstraint"

    def __init__(self, target, ctrls, mo=False, dcmpMtx=True, scale=True):
        """See Cnstr.__init__. scale : also follow the ctrls scale (scaleConstraint)."""

        self.use_scale = scale

        super().__init__(target, ctrls, mo=mo, dcmpMtx=dcmpMtx)

    def build(self):
        """parentConstraint, then scaleConstraint if 'scale'."""

        super().build()

        if self.use_scale:
            self.create(cmds.scaleConstraint, "scaleConstraint", maintainOffset=bool(self.mo))


class PointCnstr(Cnstr):
    """pointConstraint (PointCnstrMtx interface)."""

    COMMAND = cmds.pointConstraint
    SUFFIX = "pointConstraint"


class OrientCnstr(Cnstr):
    """orientConstraint (OrientCnstrMtx interface)."""

    COMMAND = cmds.orientConstraint
    SUFFIX = "orientConstraint"


class ScaleCnstr(Cnstr):
    """scaleConstraint (ScaleCnstrMtx interface)."""

    COMMAND = cmds.scaleConstraint
    SUFFIX = "scaleConstraint"


class AimCnstr(Cnstr):
    """aimConstraint (AimCnstrMtx interface)."""

    COMMAND = cmds.aimConstraint
    SUFFIX = "aimConstraint"

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
        """See AimCnstrMtx.__init__: same arguments."""

        self.worldUpObject = worldUpObject

        self.aimVector = [-v for v in aimVector] if invertAimVector else list(aimVector)
        self.upVector = [-v for v in upVector] if invertUpVector else list(upVector)

        super().__init__(target, ctrls, mo=mo, dcmpMtx=dcmpMtx)

    def get_flags(self):
        """aim / up vectors, up from worldUpObject (object up) or world Y."""

        flags = {"aimVector": self.aimVector, "upVector": self.upVector}

        if self.worldUpObject and cmds.objExists(self.worldUpObject):
            flags.update(worldUpType="object", worldUpObject=self.worldUpObject)
        else:
            flags.update(worldUpType="vector", worldUpVector=(0, 1, 0))

        return flags


class PoleVectorCnstr(Cnstr):
    """poleVectorConstraint (cnstrMtx PoleVectorCnstr interface). target = ikHandle."""

    COMMAND = cmds.poleVectorConstraint
    SUFFIX = "poleVectorConstraint"

    def __init__(self, target, ctrls, mo=False):
        """target : ikHandle (ikRPsolver). mo : unused (the native constraint has no offset)."""

        super().__init__(target, ctrls, mo=mo, dcmpMtx=False)

    def prepare_target(self):
        """Nothing: the poleVector is not a transform channel."""

    def build(self):
        """Native poleVectorConstraint (no maintain offset flag)."""

        self.create(self.COMMAND, self.SUFFIX)


# --------------------------------------------------
# FACTORY
# --------------------------------------------------

METHODS = ("Matrix", "Classic")

# kind -> (matrix class, classic class): same constructor arguments.
CONSTRAINTS = {
    "parent": (cnstrMtx_utilities.ParentCnstrMtx, ParentCnstr),
    "point": (cnstrMtx_utilities.PointCnstrMtx, PointCnstr),
    "orient": (cnstrMtx_utilities.OrientCnstrMtx, OrientCnstr),
    "scale": (cnstrMtx_utilities.ScaleCnstrMtx, ScaleCnstr),
    "aim": (cnstrMtx_utilities.AimCnstrMtx, AimCnstr),
    "poleVector": (cnstrMtx_utilities.PoleVectorCnstr, PoleVectorCnstr),
}


def get_constraint_class(kind, method="Matrix"):
    """Class of the constraint 'kind' ('parent', 'point', ...) for 'method' ('Matrix' / 'Classic')."""

    if kind not in CONSTRAINTS:
        raise ValueError(f"Constraint '{kind}' inconnue (attendu : {', '.join(CONSTRAINTS)}).")

    matrix_class, classic_class = CONSTRAINTS[kind]

    return classic_class if method == "Classic" else matrix_class


def create_constraint(kind, target, ctrls, method="Matrix", **kwargs):
    """Build the constraint 'kind' of 'target' on 'ctrls' with 'method'; kwargs as the class (mo, dcmpMtx, scale...)."""

    return get_constraint_class(kind, method)(target, ctrls, **kwargs)
