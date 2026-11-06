# ====================================================================================================================
# CLAVICLE - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'Clavicle' module (SimpleIkGuides), ATTRIBUTES from attributes.json
#            (merged with simpleIk/ and base/ through 'extends').
#
# ====================================================================================================================

from pathlib import Path

from ..simpleIk.guides import Guides as SimpleIkGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(SimpleIkGuides):

    MODULE_NAME = "Limb_Clavicle"
    DEFAULT_NAME = "Clavicle"

    # Clavicle base -> shoulder.
    AUTO_GUIDES = 2
    MAX_GUIDES = 2

    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
