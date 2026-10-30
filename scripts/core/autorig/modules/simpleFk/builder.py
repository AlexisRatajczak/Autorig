# ====================================================================================================================
# SIMPLE FK BUILDER
# ====================================================================================================================
#
#   Classic FK chain: one ctrl per guide, chained to the previous one and connected to its joint
#   (base Builder behaviour). Only the shape and color role are set here.
#
#   Builder
#       CONTROLS            create_fk_controls(joints, suffix, shape, size, color, adjust_shape)
#                           - FK ctrl chain on any joint chain (ex: limb -> self.fk_joints)
#
# ====================================================================================================================

import maya.cmds as cmds

from ..base.builder import Builder as BaseBuilder
from ....utilities import ctrl_utilities

from importlib import reload

reload(ctrl_utilities)


class Builder(BaseBuilder):

    CONTROL_SHAPE = "circle"
    CONTROL_COLOR_TYPE = "FK Main"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        self.fk_controls = []

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_fk_controls(
        self,
        joints=None,
        suffix="ctrl",
        shape=None,
        size=1.0,
        color=None,
        adjust_shape=True
    ):

        """
        One FK ctrl '{side}_{baseName}_{index}_{suffix}' per joint of 'joints'
        (self.joints by default), matched on its joint, chained to the previous
        one (the first under CTRL_grp) and connected to its joint
        (Builder.connect_control). 'No Ctrl' mode: shape on the joint itself.
        """

        joints = self.joints if joints is None else joints

        shape = shape or self.shape_ctrl() or self.CONTROL_SHAPE
        color = self.get_control_color() if color is None else color

        self.fk_controls = []

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

                self.connect_control(control, joint.name)

            self.fk_controls.append(control)

            parent = control

        return self.fk_controls
