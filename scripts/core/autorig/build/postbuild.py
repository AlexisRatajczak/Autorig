# ====================================================================================================================
# POST BUILD
# ====================================================================================================================
#
#   PostBuild(rig_data)
#       execute()               - run every post build step
#       COMMON                  organize_hierarchy, create_sets, lock_attributes, clean_scene
#       CUSTOM                  custom() - run the postBuildScripts of the rig data
#
# ====================================================================================================================

import maya.cmds as cmds

from ..build import custom_steps
from importlib import reload

reload(custom_steps)


class PostBuild():

    def __init__(self, rig_data=None):
        self.rig_data = rig_data
        self.execute()

    def execute(self):
        """Run every post build step."""
        self.organize_hierarchy()
        self.create_sets()
        self.lock_attributes()
        self.clean_scene()
        self.custom()

    # ======================================================
    # COMMON
    # ======================================================

    def organize_hierarchy(self):
        """Sort the rig groups."""
        pass

    def create_sets(self):
        """Create the rig objectSets."""
        pass

    def lock_attributes(self):
        """Lock and hide unused attributes."""
        pass

    def clean_scene(self):
        """Delete guides, history, etc."""
        pass

    # ======================================================
    # CUSTOM
    # ======================================================

    def custom(self):
        """Character specific post build: run the postBuildScripts of the rig data."""

        paths = custom_steps.get_script_paths(self.rig_data, "postBuildScripts")
        custom_steps.run_scripts(paths, label="post-build step")
