# ====================================================================================================================
# CLAVICLE BUILDER
# ====================================================================================================================
#
#   simpleIk on a single 2 joint chain (2 guides): ikSCsolver, no pole vector. The FK ctrl holds the IK ctrl.
#
#   JOINTS
#       {side}_{name}_{i}_jnt   - start (clavicle base) and end (shoulder), joints[0] parented by MainBuild
#   CONTROLS
#       FK  {..start}_ctrl      - simpleIk root ctrl on the start joint (controls[0], reparented by MainBuild):
#                                 drives the chain base, its rotation carries the IK ctrl
#       IK  {..end}_ctrl        - on the end joint, UNDER the FK ctrl: aims the chain (SC ikHandle), orients the
#                                 end joint; child modules (arm) parent their root ctrl under it
#   SETUP
#       simpleIk: SC ikHandle on the IK ctrl, end joint orientation, optional stretch ('stretchIk'), Local / World
#       space switch on the IK ctrl (its Local space: the FK ctrl).
#
#   Builder
#       SETUP           rotate_plane_solver (always SC)
#       CONTROLS        create_controls, parent_ik_controls (IK ctrl kept under the FK ctrl)
#
# ====================================================================================================================

import maya.cmds as cmds

from ..simpleIk import builder as simpleIk_builder
from ....utilities import ctrl_utilities

from importlib import reload

reload(simpleIk_builder)
reload(ctrl_utilities)


class Builder(simpleIk_builder.Builder):

    # FK ctrl (simpleIk root ctrl).
    ROOT_CONTROL_SHAPE = "circle"
    ROOT_CONTROL_COLOR_TYPE = "FK Main"

    # Joint labels: clavicle base (end joint: Other, the arm shoulder is the 'Shoulder').
    JOINT_TYPES = ("Collar",)

    # ======================================================
    # SETUP
    # ======================================================

    def rotate_plane_solver(self):
        """Single 2 joint chain: always an ikSCsolver, no pole vector."""

        return False

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        simpleIk ctrls (FK = root ctrl on the start joint, IK ctrl on the end joint, no
        pole), then the IK ctrl (its offset group if any) under the FK ctrl, world pose
        kept, offsetParentMatrix re-baked. 'No Ctrl' mode: left as simpleIk.
        """

        if len(self.joints) != 2:
            cmds.warning(f"Clavicle '{self.prefix}' : 2 guides attendus, {len(self.joints)} trouvés.")

        controls = super().create_controls()

        if self.no_ctrl() or not self.root_control or not self.ik_control:
            return controls

        node = self.get_control_node(self.ik_control)

        if node != self.ik_control:
            cmds.parent(node, self.root_control)
            return controls

        world_matrix = cmds.xform(node, query=True, matrix=True, worldSpace=True)

        cmds.parent(node, self.root_control, relative=True)
        cmds.xform(node, worldSpace=True, matrix=world_matrix)

        ctrl_utilities.Control(node).transfer_offset_parent_matrix()

        return controls

    def parent_ik_controls(self):
        """Nothing: the IK ctrl stays under the FK ctrl (simpleIk would move it next to it)."""

        return
