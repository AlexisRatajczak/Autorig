# ====================================================================================================================
# SIMPLEIK - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'SimpleIk' module (BaseGuides), ATTRIBUTES from attributes.json
#            (merged with base/ through 'extends').
#
# ====================================================================================================================

from pathlib import Path

from ..simpleBase.guides import Guides as BaseGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(BaseGuides):

    MODULE_NAME = "Simple_Ik"
    DEFAULT_NAME = "SimpleIk"

    # Auto chain of 3 guides.
    AUTO_GUIDES = 3

    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
