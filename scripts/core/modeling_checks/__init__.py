"""Check classes, one module per category.

CHECKS lists the classes in the order they appear in the window. To add a
check: write a BaseCheck subclass, add it to the CHECKS list of its module,
and add its id to the "checks" block of config/mode_settings.json.
"""
from ..modeling_checks import uv_checks
from ..modeling_checks import naming_checks
from ..modeling_checks import material_checks
from ..modeling_checks import color_checks
from ..modeling_checks import mesh_checks
from .base import BaseCheck

_MODULES = [naming_checks, mesh_checks, uv_checks, material_checks, color_checks]

CATEGORIES = [module.CATEGORY for module in _MODULES]
CHECKS = [check for module in _MODULES for check in module.CHECKS]


def create_all(settings):
    """One instance of every check, sharing the same settings dict."""
    return [check(settings) for check in CHECKS]


__all__ = ["BaseCheck", "CATEGORIES", "CHECKS", "create_all"]
