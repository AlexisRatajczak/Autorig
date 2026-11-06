# ====================================================================================================================
# METACARPAL BUILDER
# ====================================================================================================================
#
#   Builder - limb on a 2 joint chain (metacarpal base -> knuckle): FK / IK / IK-FK switch / stretch / ribbon
#             inherited from limb. 2 joints: always an ikSCsolver, no pole vector.
#
#       rotate_plane_solver     - always False (SC, no pole)
#
# ====================================================================================================================

from ..limb import builder as limb_builder

from importlib import reload

reload(limb_builder)


class Builder(limb_builder.Builder):

    def rotate_plane_solver(self):
        """2 joint chain: always an ikSCsolver, no pole vector."""

        return False
