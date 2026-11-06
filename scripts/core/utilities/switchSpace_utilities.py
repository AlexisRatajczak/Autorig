# ====================================================================================================================
# SWITCH SPACE UTILITIES
# ====================================================================================================================
#
#   SpaceSwitch - switches the effective parent of 'target' (usually a ctrl offset group) between several
#                 'spaces' (drivers) without popping, through a blendMatrix driven by an enum (or a 0..1 float
#                 in blend mode) into its offsetParentMatrix.
#
#       __init__(target, spaces, default, attr_name, attr_host, mo, parent, blend, scale, world, split,
#                separator)             - build the switch (attributes: attribute_utilities, after a separator)
#       build()                         - blendMatrix + conditions (or split T / R / S), connected to target
#       get_split_attributes()          - {"translate" / "rotate" / "scale": attribute name} of a split switch
#       build_split_blend(matrices)     - one enum blend per channel, merged (split)
#       build_enum_blend(matrices, attr, key, name) - blendMatrix of the space matrices driven by an enum attribute
#       add_attribute(attr, default)    - create / set a switch attribute (enum, or float in blend mode)
#       get_space_matrix(driver)        - matrix of a space (with the hold offset)
#       compute_offset(driver)          - world offset keeping the pose at switch time
#       create_weight_condition(index, attr) - condition node (1 if the enum == index, else 0)
#       delete()                        - delete every node created by the switch
#
#   'split': one enum per channel on the same spaces, '{attr_name}Translate' / 'Rotate' / 'Scale' (ex: space
#   World for the translation, Local for the rotation and scale). The three blends share the space matrices,
#   merged by a blendMatrix (translation from the first, rotation from the second, scale + shear from the third).
#
# ====================================================================================================================

import maya.cmds as cmds

from . import attribute_utilities


class SpaceSwitch:

    def __init__(
        self,
        target,
        spaces,
        default=0,
        attr_name="space",
        attr_host=None,
        mo=True,
        parent=None,
        blend=False,
        scale=True,
        world=False,
        split=False,
        separator="default"
    ):

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
        world     : target with inheritsTransform off (ex: a space group): the
                    space matrices stay in world space (no parent term).
        split     : (enum mode) one enum per channel instead of 'attr_name':
                    '{attr_name}Translate', '{attr_name}Rotate', '{attr_name}Scale'
                    (get_split_attributes), each defaulting to 'default'.
        separator : channel box section line before the attribute(s)
                    (attribute_utilities.add_separator): "default" = "SPACE" for an
                    enum switch, none for a blend; a label; or None.
        """

        self.target = target
        self.blend = blend
        self.scale = scale
        self.world = world
        self.spaces = list(spaces)

        self.split = split and not blend

        if separator == "default":
            separator = None if blend else "SPACE"

        self.separator = separator

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
        Build the network: attribute(s), one matrix per space, blendMatrix
        driven by conditions ('split': one per channel on the same matrices,
        merged), connected to target.offsetParentMatrix (channels reset).
        Warning only with < 2 spaces or no offsetParentMatrix.
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

        # Space matrices, computed once (shared by the split blends).
        matrices = [self.get_space_matrix(driver) for _, driver in self.spaces]

        if self.split:
            output = self.build_split_blend(matrices)

        elif self.blend:

            self.add_attribute(self.attr_name, self.default)

            blend = cmds.createNode("blendMatrix", name=f"{self.target}_space_bm")
            self.nodes["blendMatrix"] = blend

            cmds.connectAttr(matrices[0], f"{blend}.inputMatrix", force=True)
            cmds.connectAttr(matrices[1], f"{blend}.target[0].targetMatrix", force=True)
            cmds.setAttr(f"{blend}.target[0].weight", 1.0)

            # The float drives the envelope (0 = space 0, 1 = space 1).
            cmds.connectAttr(f"{self.attr_host}.{self.attr_name}", f"{blend}.envelope", force=True)

            output = f"{blend}.outputMatrix"

        else:
            self.add_attribute(self.attr_name, self.default)

            output = self.build_enum_blend(matrices, self.attr_name, "blendMatrix")

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

    def get_split_attributes(self):
        """{"translate" / "rotate" / "scale": attribute name} of a split switch: '{attr_name}Translate'..."""

        return {channel: f"{self.attr_name}{channel.capitalize()}" for channel in ("translate", "rotate", "scale")}

    def build_split_blend(self, matrices):

        """
        Split switch: one enum per channel (get_split_attributes, each set to 'default'),
        one blendMatrix each on the shared space 'matrices', merged by a blendMatrix:
        input = translate blend, target 0 = rotate blend (rotation only), target 1 =
        scale blend (scale + shear only). Returns the merged output plug.
        """

        attributes = self.get_split_attributes()

        outputs = {}

        for channel, attr in attributes.items():

            self.add_attribute(attr, self.default)

            outputs[channel] = self.build_enum_blend(matrices, attr, f"{channel}_blendMatrix", name=f"space{channel.capitalize()}")

        # Space 0 output in nodes['blendMatrix'] like the other modes (the translate blend).
        self.nodes["blendMatrix"] = self.nodes["translate_blendMatrix"]

        merge = cmds.createNode("blendMatrix", name=f"{self.target}_spaceMerge_bm")
        self.nodes["merge_blendMatrix"] = merge

        cmds.connectAttr(outputs["translate"], f"{merge}.inputMatrix", force=True)

        for index, (channel, weights) in enumerate((
            ("rotate", {"translateWeight": 0, "rotateWeight": 1, "scaleWeight": 0, "shearWeight": 0}),
            ("scale", {"translateWeight": 0, "rotateWeight": 0, "scaleWeight": 1, "shearWeight": 1}),
        )):

            cmds.connectAttr(outputs[channel], f"{merge}.target[{index}].targetMatrix", force=True)
            cmds.setAttr(f"{merge}.target[{index}].weight", 1.0)

            for attr, value in weights.items():
                cmds.setAttr(f"{merge}.target[{index}].{attr}", value)

        return f"{merge}.outputMatrix"

    def build_enum_blend(self, matrices, attr, key, name="space"):

        """
        blendMatrix '{target}_{name}_bm' (self.nodes[key]) of 'matrices' (one per space,
        space 0 as input): target i weighted 1 when the enum 'attr' == i
        (create_weight_condition). Returns its output plug.
        """

        blend = cmds.createNode("blendMatrix", name=f"{self.target}_{name}_bm")
        self.nodes[key] = blend

        cmds.connectAttr(matrices[0], f"{blend}.inputMatrix", force=True)

        for index, matrix in enumerate(matrices[1:], start=1):

            cmds.connectAttr(matrix, f"{blend}.target[{index - 1}].targetMatrix", force=True)

            cmds.connectAttr(
                self.create_weight_condition(index, attr),
                f"{blend}.target[{index - 1}].weight",
                force=True
            )

        return f"{blend}.outputMatrix"

    # --------------------------------------------------
    # ATTRIBUTE
    # --------------------------------------------------

    def add_attribute(self, attr=None, default=None):

        """
        Create a switch attribute 'attr' (attr_name by default) on attr_host if needed
        (enum of the spaces, or 0..1 float in blend mode, attribute_utilities), after the
        'separator' section line, set to 'default'.
        """

        attr = attr or self.attr_name
        default = self.default if default is None else default

        if self.separator:
            attribute_utilities.add_separator(self.attr_host, self.separator)

        if self.blend:
            attribute_utilities.add_attribute(self.attr_host, attr, attr_type="double", minimum=0.0, maximum=1.0)
        else:
            attribute_utilities.add_attribute(
                self.attr_host, attr, attr_type="enum", enum_names=[name for name, _ in self.spaces]
            )

        cmds.setAttr(f"{self.attr_host}.{attr}", default)

    # --------------------------------------------------
    # PER-SPACE MATRIX
    # --------------------------------------------------

    def get_space_matrix(self, driver):

        """
        Matrix of 'driver' in target parent space:
        offset (hold, if mo) * driver.worldMatrix * parent.worldInverseMatrix
        (no parent term when target is at the world or 'world').
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

        # 'world' target (inheritsTransform off): its offsetParentMatrix is already world space.
        if not self.world and self.parent and cmds.objExists(self.parent):
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

    def create_weight_condition(self, index, attr=None):

        """Condition node output: 1.0 if the switch attribute 'attr' (attr_name by default) == 'index', else 0.0."""

        attr = attr or self.attr_name

        condition = cmds.createNode("condition", name=f"{self.target}_{attr}{index}_cond")

        cmds.setAttr(f"{condition}.operation", 0)  # equal
        cmds.setAttr(f"{condition}.secondTerm", index)
        cmds.setAttr(f"{condition}.colorIfTrueR", 1)
        cmds.setAttr(f"{condition}.colorIfFalseR", 0)

        cmds.connectAttr(f"{self.attr_host}.{attr}", f"{condition}.firstTerm", force=True)

        self.nodes[f"{attr}{index}_condition"] = condition

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
