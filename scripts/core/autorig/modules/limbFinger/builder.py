# ====================================================================================================================
# FINGER BUILDER
# ====================================================================================================================
#
#   Builder - limb on a finger chain (base -> middle -> distal -> tip): FK / IK / IK-FK switch / ribbon inherited
#             from limb, plus a driven group above each FK ctrl for the finger attributes.
#
#   CONTROLS
#       driven  {..}_fk_sdk         - group between each FK ctrl (but the tip) and its parent, matched on it: the
#                                     finger attributes rotate it, the FK ctrl keeps its channels free
#   ATTRIBUTES (attributes host: 'attributesHost', else the limb switch ctrl)
#       FINGER  curl                - every phalanx, bend axis
#               crunch              - base phalanx -crunch, the others +crunch (bend axis)
#               scrunch             - factor per phalanx from the phalanx lengths (ratio = base / middle):
#                                     base x-1, middle x(1 + ratio), distal x-ratio: the tip keeps its
#                                     orientation and stays on the finger axis (get_scrunch_factors)
#               spread              - base phalanx, side axis, * 'spreadFactor' (module setting, per finger)
#               twist               - every phalanx, aim axis
#       axes from aimVector / upVector: aim = aimVector, bend = upVector (Chain Plane normal), side = the
#       third one; 'invertCurl' flips the bend.
#
#   Builder
#       CONTROLS        create_controls, insert_driven_group
#       SETUP           create_setup, get_axes, get_scrunch_factors, connect_finger_attributes
#
# ====================================================================================================================

import maya.cmds as cmds

from ..limb import builder as limb_builder
from ....utilities import ctrl_utilities
from ....utilities import attribute_utilities

from importlib import reload

reload(limb_builder)
reload(ctrl_utilities)
reload(attribute_utilities)


class Builder(limb_builder.Builder):

    DRIVEN_SUFFIX = "fk_sdk"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        # Driven groups, one per FK ctrl but the tip (connect_finger_attributes).
        self.driven_groups = []

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        Limb ctrls, then a driven group above each FK ctrl but the tip
        (insert_driven_group). After limb: the FK root already sits under the root ctrl.
        'No Ctrl' mode: no driven group.
        """

        controls = super().create_controls()

        self.driven_groups = []

        if self.no_ctrl():
            return controls

        for control in self.fk_controls[:-1]:
            self.driven_groups.append(self.insert_driven_group(control))

        return controls

    def insert_driven_group(self, control):

        """
        Group '{..}_fk_sdk' between 'control' and its DAG parent (previous ctrl, its offset
        group, root ctrl...), matched on the ctrl; the ctrl goes under it, world pose kept,
        offsetParentMatrix re-baked (identity). Returns the group.
        """

        base = control[: -len("_ctrl")] if control.endswith("_ctrl") else control

        group = cmds.group(empty=True, name=f"{base}_sdk")

        parent = cmds.listRelatives(control, parent=True, fullPath=True)

        if parent:
            group = cmds.parent(group, parent[0])[0]

        cmds.xform(group, worldSpace=True, matrix=cmds.xform(control, query=True, worldSpace=True, matrix=True))

        world_matrix = cmds.xform(control, query=True, worldSpace=True, matrix=True)

        cmds.parent(control, group, relative=True)
        cmds.xform(control, worldSpace=True, matrix=world_matrix)

        ctrl_utilities.Control(control).transfer_offset_parent_matrix()

        return group

    # ======================================================
    # SETUP
    # ======================================================

    def create_setup(self):
        """Limb setup, then the finger attributes on the driven groups (every ctrl exists by now)."""

        setups = super().create_setup()

        self.connect_finger_attributes()

        return setups

    def get_axes(self):

        """
        (aim, bend, side) axis letters from aimVector / upVector main components: aim along
        the chain, bend around the up vector (Chain Plane normal), side the third axis.
        """

        aim_vector = self.get_vector_attribute("aimVector", default=(1.0, 0.0, 0.0))
        up_vector = self.get_vector_attribute("upVector", default=(0.0, 0.0, 1.0))

        aim = max(range(3), key=lambda k: abs(aim_vector[k]))
        bend = max((k for k in range(3) if k != aim), key=lambda k: abs(up_vector[k]))
        side = 3 - aim - bend

        return "XYZ"[aim], "XYZ"[bend], "XYZ"[side]

    def get_scrunch_factors(self):

        """
        Scrunch factor per driven phalanx, from the phalanx lengths (FK joints at build):
        L0 = base length, L1 = middle length, ratio = L0 / L1:

            base    : -1                (against the curl)
            middle  :  1 + ratio        (with the curl, accentuated)
            distal  : -ratio
            beyond  :  0

        Small angles: the rotations sum to 0 (the tip keeps its orientation) and the tip
        stays on the finger axis (L0 * -1 + L1 * (-1 + 1 + ratio) = 0). Ex: L0 / L1 = 0.75
        -> -1, 1.75, -0.75.
        """

        count = len(self.driven_groups)

        positions = [
            cmds.xform(joint.name, query=True, worldSpace=True, translation=True)
            for joint in self.fk_joints[:3]
        ]

        def length(a, b):
            return sum((b[k] - a[k]) ** 2 for k in range(3)) ** 0.5

        ratio = 1.0

        if len(positions) == 3:

            middle = length(positions[1], positions[2])

            if middle > 1e-6:
                ratio = length(positions[0], positions[1]) / middle

        # Reversed direction: base against the curl, middle with it, distal against it.
        factors = [-1.0, 1.0 + ratio, -ratio]

        return (factors + [0.0] * count)[:count]

    def connect_finger_attributes(self):

        """
        FINGER section (curl, crunch, scrunch, spread, twist) on the attributes host (limb
        switch ctrl by default), into the driven groups:

            bend (each phalanx) = curl + crunch (base: -crunch) + scrunch * factor (from the
                                  phalanx lengths, get_scrunch_factors), * -1 with 'invertCurl'
            aim  (each phalanx) = twist
            side (base)         = spread * spreadFactor

        Returns the created nodes.
        """

        if not self.driven_groups:
            return []

        host = self.get_attributes_host(default=self.limb_root_control)

        if not host or not cmds.objExists(host):
            cmds.warning(f"Finger '{self.prefix}' : aucun ctrl pour porter les attributs du doigt.")
            return []

        attribute_utilities.add_attributes(host, "FINGER", [
            {"name": "curl", "default": 0.0},
            {"name": "crunch", "default": 0.0},
            {"name": "scrunch", "default": 0.0},
            {"name": "spread", "default": 0.0},
            {"name": "twist", "default": 0.0},
        ])

        aim, bend, side = self.get_axes()
        invert = bool(self.data.get("invertCurl"))

        scrunch_factors = self.get_scrunch_factors()

        nodes = []

        def multiply(name, plug, value):
            node = cmds.createNode("multDoubleLinear", name=f"{self.prefix}_{name}_mdl")
            cmds.connectAttr(plug, f"{node}.input1")
            cmds.setAttr(f"{node}.input2", value)
            nodes.append(node)
            return f"{node}.output"

        for index, group in enumerate(self.driven_groups):

            total = cmds.createNode("plusMinusAverage", name=f"{self.prefix}_{index + 1:02d}_curl_pma")
            nodes.append(total)

            crunch = multiply(f"{index + 1:02d}_crunch", f"{host}.crunch", -1.0) if index == 0 else f"{host}.crunch"

            # Scrunch: factor per phalanx from the phalanx lengths (get_scrunch_factors).
            factor = scrunch_factors[index]
            scrunch = f"{host}.scrunch" if factor == 1.0 else multiply(f"{index + 1:02d}_scrunch", f"{host}.scrunch", factor)

            plugs = [f"{host}.curl", crunch, scrunch]

            for slot, plug in enumerate(plugs):
                cmds.connectAttr(plug, f"{total}.input1D[{slot}]")

            output = f"{total}.output1D"

            if invert:
                output = multiply(f"{index + 1:02d}_curl_invert", output, -1.0)

            cmds.connectAttr(output, f"{group}.rotate{bend}", force=True)

            # Twist: every phalanx rolls around its own axis.
            cmds.connectAttr(f"{host}.twist", f"{group}.rotate{aim}", force=True)

        # Spread: base only, * spreadFactor (per finger: index 1, middle 0, pinky -1...).
        spread_factor = self.get_float("spreadFactor", 1.0)
        spread = f"{host}.spread" if spread_factor == 1.0 else multiply("spread", f"{host}.spread", spread_factor)

        cmds.connectAttr(spread, f"{self.driven_groups[0]}.rotate{side}", force=True)

        return nodes
