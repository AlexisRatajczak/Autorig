# ====================================================================================================================
# SIMPLE FK BUILDER
# ====================================================================================================================
#
#   Classic FK chain: one ctrl per guide, chained to the previous one and connected to its joint
#   (base Builder behaviour). 'subCtrl': a second level in the chain, one '{..}_sub_ctrl' under each main
#   ctrl but the last, driving its joint and carrying the next main ctrl (main > sub > main > sub > ... > last
#   main). Child modules parent on the main ctrls.
#
#   Builder
#       CONTROLS            create_controls, use_sub_controls,
#                           create_fk_controls(joints, suffix, shape, size, color, adjust_shape, sub)
#                           - FK ctrl chain on any joint chain (ex: limb -> self.fk_joints),
#                           create_sub_control
#
# ====================================================================================================================

import maya.cmds as cmds

from ..simpleBase.builder import Builder as BaseBuilder
from ....utilities import ctrl_utilities

from importlib import reload

reload(ctrl_utilities)


class Builder(BaseBuilder):

    CONTROL_SHAPE = "circle"
    CONTROL_COLOR_TYPE = "FK Main"

    SUB_CONTROL_SUFFIX = "sub_ctrl"
    SUB_CONTROL_COLOR_TYPE = "FK Secondary"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.fk_controls = []

        # Second level ('subCtrl'), one per main ctrl (create_fk_controls).
        self.fk_sub_controls = []

    # ======================================================
    # CONTROLS
    # ======================================================

    def use_sub_controls(self):
        """'Sub Ctrl' option: a second ctrl level driving each joint alone."""

        return bool(self.data.get("subCtrl")) and not self.no_ctrl()

    def create_controls(self):

        """
        Without 'subCtrl': base behaviour (one chained ctrl per guide). With it: the FK
        chain with its sub ctrls (create_fk_controls sub=True). Returns the main ctrls
        (controls[0] = first main) then the sub ctrls.
        """

        if not self.use_sub_controls():
            return super().create_controls()

        return list(self.create_fk_controls(self.joints, sub=True)) + list(self.fk_sub_controls)

    def create_fk_controls(
        self,
        joints=None,
        suffix="ctrl",
        shape=None,
        size=1.0,
        color=None,
        adjust_shape=True,
        sub=False
    ):

        """
        One FK ctrl '{side}_{baseName}_{index}_{suffix}' per joint of 'joints'
        (self.joints by default), matched on its joint, chained to the previous
        one (the first under CTRL_grp) and connected to its joint
        (Builder.connect_control). 'No Ctrl' mode: shape on the joint itself.

        sub : a sub ctrl '{..}_sub_ctrl' under each main ctrl but the last one
              (subCtrlSize, FK Secondary color) drives the joint and carries the
              rest of the chain: main > sub > next main > next sub... The last joint
              has no sub ctrl (its main ctrl drives it). Child modules still parent
              on the main ctrls ({guide}_ctrl). Stored in self.fk_sub_controls.
        """

        joints = self.joints if joints is None else joints

        shape = shape or self.shape_ctrl() or self.CONTROL_SHAPE
        color = self.get_control_color() if color is None else color

        self.fk_controls = []
        self.fk_sub_controls = []

        sub = sub and not self.no_ctrl()

        parent = None

        for joint in joints:

            base_name, side, index = self.main.get_guide_naming(joint.guide)

            if self.no_ctrl():

                control = self.create_joint_shape(
                    joint.guide, base_name, side, index, joint.name,
                    shape=shape, size=size, color=color
                )

            else:

                ctrl = ctrl_utilities.Control(
                    f"{side}_{base_name}_{index:02d}_{suffix}",
                    shape=shape,
                    size=size,
                    color=color
                )
                ctrl.create()

                if adjust_shape:
                    self.adjust_control_shape(ctrl)

                cmds.matchTransform(ctrl.name, joint.name, position=True, rotation=True)

                target_parent = parent if parent and cmds.objExists(parent) else self.main.groups.get("controls")

                ctrl.create_offset(parent=target_parent, use_group=self.offset_group())

                control = ctrl.name

                chain_parent = control

                # Sub ctrl (not on the last joint): drives the joint and carries the rest of the chain.
                if sub and joint is not joints[-1]:
                    sub_control = self.create_sub_control(control, joint, base_name, side, index, shape, size)
                    self.connect_control(sub_control, joint.name)
                    self.fk_sub_controls.append(sub_control)
                    chain_parent = sub_control
                else:
                    self.connect_control(control, joint.name)

            self.fk_controls.append(control)

            # Next main ctrl under the sub ctrl if any, else under this main ctrl.
            parent = control if self.no_ctrl() else chain_parent

        return self.fk_controls

    def create_sub_control(self, main_control, joint, base_name, side, index, shape, size=1.0):

        """
        Sub ctrl '{side}_{baseName}_{index}_sub_ctrl' matched on 'joint', under 'main_control'
        (offset baked, or offset group), size * subCtrlSize, FK Secondary color. Returns it.
        """

        control = ctrl_utilities.Control(
            f"{side}_{base_name}_{index:02d}_{self.SUB_CONTROL_SUFFIX}",
            shape=shape,
            size=size * self.get_float("subCtrlSize", 0.75),
            color=self.main.get_color(self.data.get("side"), self.SUB_CONTROL_COLOR_TYPE)
        )
        control.create()

        self.adjust_control_shape(control)

        cmds.matchTransform(control.name, joint.name, position=True, rotation=True)

        control.create_offset(parent=main_control, use_group=self.offset_group())

        return control.name
