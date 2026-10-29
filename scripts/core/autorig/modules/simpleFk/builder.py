import maya.cmds as cmds

from ..base.builder import Builder as BaseBuilder
from ....utilities import ctrl_utilities

from importlib import reload

reload(ctrl_utilities)


# ==========================================================
# SIMPLE FK BUILDER
# ==========================================================
#
# Chaîne FK classique : un ctrl par guide, chaîné au ctrl précédent,
# chacun connecté à son joint (comportement déjà fourni par le Builder
# de base). Seuls la forme et le rôle de couleur sont explicités ici.
#
# create_fk_controls construit la même chaîne de ctrls sur n'importe
# quelle chaîne de joints (ex: limb -> self.fk_joints).
#

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
        Un ctrl FK '{side}_{baseName}_{index}_{suffix}' par joint de
        'joints' (self.joints par défaut), matché sur son joint, chaîné au
        précédent (le premier sous CTRL_grp) et connecté à son joint
        (Builder.connect_control : contrainte de matrix, ou connexion
        directe si 'Simple Connection'). En mode 'No Ctrl', la shape est
        posée directement sur le joint (Builder.create_joint_shape).
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
