"""Base class of every check.

A check is a class with a DESCRIPTION variable and four methods:

    description()  -> returns DESCRIPTION, the text shown under the check
    check(scope)   -> list of nodes / components in error (also kept in self.items)
    select()       -> select the items found by the last check
    fix()          -> repair the items found by the last check

To write a new check, subclass BaseCheck, set id / label / category /
DESCRIPTION and write the methods. Write fix() only when an automatic fix
exists: the Fix button is enabled only for classes that define it.
"""
import functools

from maya import cmds

from ..utilities import geo_utilities


class BaseCheck(object):
    id = ""
    label = ""
    category = ""
    DESCRIPTION = ""

    def __init__(self, settings):
        self.settings = settings
        self.items = []

    def __init_subclass__(cls, **kwargs):
        """Store the result of check() in self.items, whatever the subclass returns."""
        super().__init_subclass__(**kwargs)
        if "check" not in cls.__dict__:
            return
        original = cls.__dict__["check"]

        @functools.wraps(original)
        def check(self, scope=geo_utilities.SCENE):
            self.items = []
            self.items = list(original(self, scope) or [])
            return self.items

        cls.check = check

    # ------------------------------------------------------- the four methods
    def description(self):
        return self.DESCRIPTION

    def check(self, scope=geo_utilities.SCENE):
        raise NotImplementedError("{} must implement check()".format(type(self).__name__))

    def select(self):
        """Select what the last check found. Returns the number of items selected."""
        return geo_utilities.select_items(self.items)

    def fix(self):
        raise NotImplementedError("{} has no automatic fix".format(type(self).__name__))

    # ---------------------------------------------------------------- helpers
    @property
    def can_fix(self):
        return type(self).fix is not BaseCheck.fix

    @property
    def enabled(self):
        return bool(self.settings.get("checks", {}).get(self.id, True))

    def existing_items(self):
        """Items of the last check that are still in the scene."""
        return [item for item in self.items if cmds.objExists(item)]

    def meshes(self, scope):
        return geo_utilities.meshes(scope, self.settings)

    def transforms(self, scope):
        return geo_utilities.transforms(scope, self.settings)

    def mesh_components(self, scope, function, *args):
        """Run function(mesh, *args) on every mesh and gather the components."""
        result = []
        for mesh in self.meshes(scope):
            result.extend(function(mesh, *args))
        return result
