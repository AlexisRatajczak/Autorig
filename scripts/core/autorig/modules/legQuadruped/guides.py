# ====================================================================================================================
# LEGQUADRUPED - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'legQuadruped' module (LimbGuides), ATTRIBUTES from attributes.json
#            (merged with limb/ through 'extends').
#
# ====================================================================================================================

from pathlib import Path

from ..limb.guides import Guides as LimbGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(LimbGuides):

    MODULE_NAME = "legQuadruped"
    DEFAULT_NAME = "legQuadruped"

    # Auto chain: hip, knee, hock, foot.
    AUTO_GUIDES = 4
    MAX_GUIDES = 4

    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
