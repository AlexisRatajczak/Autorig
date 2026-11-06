# ====================================================================================================================
# JOINT UTILITIES
# ====================================================================================================================
#
#   LABEL
#       set_joint_label(joint, side, joint_type, other_type)    - Maya joint label: side, type, otherType (Other)
#   JOINT (class)
#       __init__(data, suffix="jnt")                            - store the settings, find a free index
#       index (property / setter)                               - numeric index of the name
#       name (property / setter)                                - name {side}_{baseName}_{index}_{suffix}
#       create_joint()                                          - create the joint node, parent it if needed, label it
#       label()                                                 - set_joint_label from the joint side / type
#       match_transform(target, matchPos, matchRot, matchScale) - match the joint on a guide / node
#       freeze_transform()                                      - bake the local transform (+ jointOrient) into OPM
#       rename(baseName, side, index, suffix)                   - rename (and update the naming attributes)
#       mirror(axis, searchSide, replaceSide, replace_name)     - mirror the joint, return a new Joint
#       duplicate_chain(root_joint, replace_name) [static]      - duplicate a whole chain, rebuild the hierarchy
#       replace_shape(ctrl)                                     - copy a ctrl's shapes onto the joint
#   CHAIN HELPERS
#       as_joint(joint)                                         - Joint for an existing joint name, or as is
#       parent_joint(joint, parent)                             - reparent, world position kept, transform re-baked
#       create_chain(positions, names, parent, aim_vector, up_vector, up_objects)
#                                                               - oriented chain (aim to the next) at the positions
#       move_offset_to_channels(joint)                          - baked OPM back to translate + jointOrient
#       create_ik_handle(start, end, name, solver, parent)      - hidden ikHandle, effector renamed
#       get_world_vector(node, vector)                          - local direction of a node in world space
#       attach_chain_to_curve(joints, curve, up_objects, aim_vector, up_vector)
#                                                               - chain on a curve: position, aim next, up object
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from . import curve_utilities


# ==========================================================
# LABEL
# ==========================================================

# Name side prefix -> joint 'side' enum label.
LABEL_SIDES = {"C": "Center", "L": "Left", "R": "Right"}


def set_joint_label(joint, side=None, joint_type=None, other_type=None):

    """
    Maya joint label of 'joint' (Joint or name), used by Mirror Skin Weights / HIK:

        side       : "C" / "L" / "R" (or Center / Left / Right / None), else the
                     name prefix (L_..., R_..., else Center);
        joint_type : type enum label ("Hip", "Knee", "Shoulder", "Spine"...), None /
                     unknown = "Other";
        other_type : "Other" only: its label, else the name without the side prefix
                     (unique, identical on both sides: L / R match by label).

    Enum indexes read on the joint (attributeQuery): no Maya version table.
    """

    name = getattr(joint, "name", joint)

    if not name or not cmds.objExists(name) or cmds.nodeType(name) != "joint":
        return

    short = name.split("|")[-1]
    prefix = short.split("_")[0]

    side = LABEL_SIDES.get(side, side) if side else LABEL_SIDES.get(prefix, "Center")

    def enum_index(attr, label, default):
        names = (cmds.attributeQuery(attr, node=name, listEnum=True) or [""])[0].split(":")
        return names.index(label) if label in names else default

    cmds.setAttr(f"{name}.side", enum_index("side", side, 0))

    type_index = enum_index("type", joint_type, -1) if joint_type else -1
    other_index = enum_index("type", "Other", 18)

    if type_index < 0:
        type_index = other_index

    cmds.setAttr(f"{name}.type", type_index)

    if type_index == other_index:
        label = other_type or (short[len(prefix) + 1:] if prefix in LABEL_SIDES else short)
        cmds.setAttr(f"{name}.otherType", label, type="string")


class Joint:

    def __init__(self, data, suffix="jnt"):
        """
        Store the joint settings and find a free index (creates nothing, see create_joint).

        data   : "baseName" and "side" (initial), optionally "parent", "guide", "index",
                 "type" (joint label type, ex: "Hip"; None = Other, see set_joint_label).
        suffix : naming suffix (ex: "jnt", "fk_jnt").
        """

        self.baseName = data["baseName"]
        self.side = data["side"][0]
        self.parent = data.get("parent")
        self.suffix = suffix
        self.guide = data.get("guide")
        self.joint_type = data.get("type")

        self._index = data.get("index", 0)
        self._name = None

        while cmds.objExists(f'{self.side}_{self.baseName}_{self._index:02d}_{self.suffix}'):
            self._index += 1


    @property
    def index(self):
        """Numeric index used in the name."""
        return self._index

    @index.setter
    def index(self, value):
        self._index = value

    @property
    def name(self):
        """Name set explicitly, else {side}_{baseName}_{index:02d}_{suffix}."""
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
        """Create the joint node (self.name), parented under self.parent if it exists, labeled (label)."""

        self.name = cmds.createNode("joint", name=self.name)

        if self.parent and cmds.objExists(self.parent):
            cmds.parent(self.name, self.parent)

        self.label()

        return self.name

    def label(self):
        """Joint label from its side and type (set_joint_label: otherType from its current name)."""

        set_joint_label(self.name, side=self.side, joint_type=self.joint_type)

        return self

    # --------------------------------------------------
    # MATCH TRANSFORM
    # --------------------------------------------------

    def match_transform(self, target = None,  matchPos=True, matchRot=True, matchScale=None):
        """Match the joint on 'target' (self.guide by default): position / rotation / scale."""

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
        Bake the local matrix (worldMatrix * parent worldInverseMatrix) into
        the offsetParentMatrix, then reset translate / rotate / scale and
        jointOrient (already part of the joint matrix: keeping it would
        double the rotation).
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
        """Update the given naming attributes (None keeps the current one) and rename the joint."""

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

            # Side / otherType follow the new name.
            self.label()

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
        Mirror the joint (cmds.mirrorJoint) and rename the copy. Returns a new
        Joint, or None if the mirror failed.

        axis         : mirror plane ("XY", "YZ" or "XZ").
        searchSide   : side replaced in the copy name (ex: "L").
        replaceSide  : new side (ex: "R").
        replace_name : extra {old: new} replacements, applied before the side.
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
        Duplicate the chain under 'root_joint', rename each joint ('replace_name'
        {old: new} then standard naming) and rebuild the hierarchy.
        Returns the new Joints, root first.
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
        """Replace the joint shapes with a copy of the shapes of 'ctrl'."""

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
    """Joint as is, or a Joint wrapping an existing joint name (for its methods)."""

    if isinstance(joint, Joint):
        return joint

    wrapper = Joint({"baseName": joint, "side": "C"})
    wrapper.name = joint

    return wrapper


def parent_joint(joint, parent):

    """
    Parent 'joint' (Joint or name) under 'parent', world position kept and
    offsetParentMatrix re-baked (clean channels). Returns the Joint.
    """

    joint = as_joint(joint)

    world_matrix = cmds.xform(joint.name, query=True, matrix=True, worldSpace=True)

    cmds.parent(joint.name, parent, relative=True)
    cmds.xform(joint.name, worldSpace=True, matrix=world_matrix)

    joint.freeze_transform()

    return joint


def create_chain(positions, names, parent=None, aim_vector=(1, 0, 0), up_vector=(0, 0, 1), up_objects=None):

    """
    Joint chain 'names' at the world 'positions': each joint aims at the next
    (aimVector), up = Y axis of 'up_objects[i]' or world Y; the last one keeps
    the previous orientation. Created flat, baked, then chained under 'parent'.
    Returns the Joints, root first.
    """

    if len(positions) != len(names):
        raise ValueError("create_chain : autant de noms que de positions.")

    joints = []

    for name, position in zip(names, positions):

        joint = cmds.createNode("joint", name=name)

        # Label from the name: side prefix, Other + otherType.
        set_joint_label(joint)

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


def move_offset_to_channels(joint):

    """
    Classic joint channels from a baked offsetParentMatrix (Joint.freeze_transform):
    its translation -> translate, its rotation -> jointOrient, offsetParentMatrix
    reset to identity (same world pose). For solvers reading the joint channels
    (spline IK bone lengths) or a stretch on translate. Skipped if driven.
    """

    joint = getattr(joint, "name", joint)

    if cmds.listConnections(f"{joint}.offsetParentMatrix", source=True, destination=False):
        return

    matrix = om.MTransformationMatrix(om.MMatrix(cmds.getAttr(f"{joint}.offsetParentMatrix")))

    translation = matrix.translation(om.MSpace.kTransform)
    rotation = matrix.rotation()

    cmds.setAttr(f"{joint}.offsetParentMatrix", list(om.MMatrix()), type="matrix")

    cmds.setAttr(f"{joint}.translate", translation.x, translation.y, translation.z)
    cmds.setAttr(f"{joint}.rotate", 0, 0, 0)
    cmds.setAttr(f"{joint}.jointOrient", *[om.MAngle(angle).asDegrees() for angle in (rotation.x, rotation.y, rotation.z)])


def create_ik_handle(start, end, name, solver="ikSCsolver", parent=None):

    """
    ikHandle 'name' from 'start' to 'end' (Joint or name), effector '{name}_effector',
    under 'parent', hidden. Returns the ikHandle.
    """

    start = getattr(start, "name", start)
    end = getattr(end, "name", end)

    ik_handle, effector = cmds.ikHandle(startJoint=start, endEffector=end, solver=solver, name=name)[:2]

    cmds.rename(effector, f"{name}_effector")

    if parent and cmds.objExists(parent):
        ik_handle = cmds.parent(ik_handle, parent)[0]

    cmds.setAttr(f"{ik_handle}.visibility", 0)

    return ik_handle


def get_world_vector(node, vector):
    """Local direction 'vector' of 'node' in world space (rotation and scale only), normalized."""

    matrix = om.MMatrix(cmds.getAttr(f"{node}.worldMatrix[0]"))

    return list((om.MVector(vector) * matrix).normal())


def attach_chain_to_curve(joints, curve, up_objects, aim_vector=(1, 0, 0), up_vector=(0, 0, 1)):

    """
    Drive a joint chain with 'curve', per joint (Joint or name):

        position : curve point closest to the joint at build (pointOnCurveInfo,
                   composeMatrix);
        aim      : aimVector to the next joint position (last joint: away from
                   the previous one);
        up       : upVector toward its 'up_objects' node (aimMatrix secondary aim).

    The world result goes into the offsetParentMatrix, in the parent space
    (* parent.worldInverseMatrix): translate / rotate / jointOrient reset and
    inverseScale disconnected (the parent space already holds its scale).
    Returns the created nodes.
    """

    names = [getattr(joint, "name", joint) for joint in joints]

    if len(names) < 2 or len(up_objects) < len(names):
        cmds.warning("attach_chain_to_curve : au moins 2 joints et un up object par joint.")
        return []

    nodes = []
    positions = []

    for name in names:

        position = cmds.xform(name, query=True, worldSpace=True, translation=True)

        info = curve_utilities.create_point_on_curve(curve, curve_utilities.get_closest_parameter(curve, position), name=f"{name}_poci")

        compose = cmds.createNode("composeMatrix", name=f"{name}_position_cm")
        cmds.connectAttr(f"{info}.position", f"{compose}.inputTranslate")

        positions.append(f"{compose}.outputMatrix")
        nodes += [info, compose]

    for i, (name, up_object) in enumerate(zip(names, up_objects)):

        last = i == len(names) - 1

        target = positions[i - 1] if last else positions[i + 1]
        axis = [-value for value in aim_vector] if last else list(aim_vector)

        aim = cmds.createNode("aimMatrix", name=f"{name}_aim")

        cmds.connectAttr(positions[i], f"{aim}.inputMatrix")

        cmds.setAttr(f"{aim}.primaryInputAxis", *axis)
        cmds.setAttr(f"{aim}.primaryMode", 1)
        cmds.connectAttr(target, f"{aim}.primaryTargetMatrix")

        cmds.setAttr(f"{aim}.secondaryInputAxis", *up_vector)
        cmds.setAttr(f"{aim}.secondaryMode", 1)
        cmds.connectAttr(f"{up_object}.worldMatrix[0]", f"{aim}.secondaryTargetMatrix")

        mult = cmds.createNode("multMatrix", name=f"{name}_curve_mm")
        cmds.connectAttr(f"{aim}.outputMatrix", f"{mult}.matrixIn[0]")

        parent = cmds.listRelatives(name, parent=True, fullPath=True)

        if parent:
            cmds.connectAttr(f"{parent[0]}.worldInverseMatrix[0]", f"{mult}.matrixIn[1]")

        for source in cmds.listConnections(f"{name}.inverseScale", source=True, destination=False, plugs=True) or []:
            cmds.disconnectAttr(source, f"{name}.inverseScale")

        cmds.connectAttr(f"{mult}.matrixSum", f"{name}.offsetParentMatrix", force=True)

        cmds.setAttr(f"{name}.translate", 0, 0, 0)
        cmds.setAttr(f"{name}.rotate", 0, 0, 0)

        if cmds.attributeQuery("jointOrient", node=name, exists=True):
            cmds.setAttr(f"{name}.jointOrient", 0, 0, 0)

        nodes += [aim, mult]

    return nodes
