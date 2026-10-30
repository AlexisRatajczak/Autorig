# ====================================================================================================================
# JOINT UTILITIES
# ====================================================================================================================
#
#   JOINT (class)
#       __init__(data, suffix="jnt")                            - store the settings, find a free index
#       index (property / setter)                               - numeric index of the name
#       name (property / setter)                                - name {side}_{baseName}_{index}_{suffix}
#       create_joint()                                          - create the joint node, parent it if needed
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
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om


class Joint:

    def __init__(self, data, suffix="jnt"):
        """
        Store the joint settings and find a free index (creates nothing, see create_joint).

        data   : "baseName" and "side" (initial), optionally "parent", "guide", "index".
        suffix : naming suffix (ex: "jnt", "fk_jnt").
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
        """Create the joint node (self.name), parented under self.parent if it exists."""

        self.name = cmds.createNode("joint", name=self.name)

        if self.parent and cmds.objExists(self.parent):
            cmds.parent(self.name, self.parent)

        return self.name

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
