import maya.cmds as cmds

from ..build import custom_steps
from importlib import reload

reload(custom_steps)


class PostBuild():

    def __init__(self, rig_data=None):
        self.rig_data = rig_data
        self.execute()

    def execute(self):
        """Exécute toutes les étapes du post build."""
        self.organize_hierarchy()
        self.create_sets()
        self.lock_attributes()
        self.clean_scene()
        self.custom()

    # ======================================================
    # COMMON
    # ======================================================

    def organize_hierarchy(self):
        """Range les groupes du rig."""
        pass

    def create_sets(self):
        """Crée les objectSets du rig."""
        pass

    def lock_attributes(self):
        """Lock et masque les attributs inutiles."""
        pass

    def clean_scene(self):
        """Supprime les guides, history, etc."""
        pass

    # ======================================================
    # CUSTOM
    # ======================================================

    def custom(self):
        """Post build specifique au personnage - execute les scripts listes dans postBuildScripts (rig_data)."""

        paths = custom_steps.get_script_paths(self.rig_data, "postBuildScripts")
        custom_steps.run_scripts(paths, label="post-build step")