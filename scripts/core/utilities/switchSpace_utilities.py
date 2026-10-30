# ====================================================================================================================
# SWITCH SPACE UTILITIES
# ====================================================================================================================
#
#   SpaceSwitch - switches the effective parent of 'target' (usually a ctrl offset group) between several
#                 'spaces' (drivers) without popping, through a blendMatrix driven by an enum (or a 0..1 float
#                 in blend mode) into its offsetParentMatrix.
#
#       __init__(target, spaces, default, attr_name, attr_host, mo, parent, blend, scale) - build the switch
#       build()                         - blendMatrix + conditions, connected to target
#       add_attribute()                 - create / set the switch attribute (enum, or float in blend mode)
#       get_space_matrix(driver)        - matrix of a space (with the hold offset)
#       compute_offset(driver)          - world offset keeping the pose at switch time
#       create_weight_condition(index)  - condition node (1 if the enum == index, else 0)
#       delete()                        - delete every node created by the switch
#
# ====================================================================================================================

import maya.cmds as cmds


class SpaceSwitch:

    def __init__(self, target, spaces, default=0, attr_name="space", attr_host=None, mo=True, parent=None, blend=False, scale=True):

        """
        target    : node whose offsetParentMatrix is driven (usually the ctrl
                    offset group, so the ctrl channels stay free).
        spaces    : ordered [(name, driver)]: 'name' feeds the enum, 'driver'
                    worldMatrix drives target in that space.
        default   : default space index.
        attr_name : switch attribute name.
        attr_host : node holding the attribute (target by default).
        mo        : offset per space so the switch keeps the build pose.
        parent    : DAG parent of target (real parent by default). Its
                    worldInverseMatrix is read instead of
                    target.parentInverseMatrix, which would cycle.
        blend     : exactly 2 spaces (ex: IK/FK): 0..1 float on the
                    blendMatrix envelope instead of an enum.
        scale     : follow the space scale too. False: scale and shear
                    removed (pickMatrix).
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
        Build the network: attribute, one matrix per space, blendMatrix
        driven by conditions, connected to target.offsetParentMatrix
        (channels reset). Warning only with < 2 spaces or no offsetParentMatrix.
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

        # Blend mode: the float drives the envelope (0 = space 0, 1 = space 1).
        if self.blend:
            cmds.connectAttr(f"{self.attr_host}.{self.attr_name}", f"{blend}.envelope", force=True)

        output = f"{blend}.outputMatrix"

        # Space scale: kept (full matrices) or removed.
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

        """Create the switch attribute on attr_host if needed (enum, or 0..1 float in blend mode), set to default."""

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
        Matrix of 'driver' in target parent space:
        offset (hold, if mo) * driver.worldMatrix * parent.worldInverseMatrix
        (no parent term when target is at the world).
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

        """Constant world offset keeping target's pose: target.worldMatrix * inverse(driver.worldMatrix)."""

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

        """Condition node output: 1.0 if the switch attribute == 'index' (space position), else 0.0."""

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
        """Delete every node created by this SpaceSwitch (self.nodes)."""

        for node in list(self.nodes.values()):
            if cmds.objExists(node):
                cmds.delete(node)

        self.nodes.clear()
