# ====================================================================================================================
# BASICCTRL - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'BasicCtrl' module (BaseGuides), ATTRIBUTES from attributes.json
#            (merged with base/ through 'extends'). Root guide only: one ctrl, no joint.
#
# ====================================================================================================================

from pathlib import Path

from ..simpleBase.guides import Guides as BaseGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(BaseGuides):

    MODULE_NAME = "Simple_Ctrl"
    DEFAULT_NAME = "Ctrl"

    # Root guide only.
    AUTO_GUIDES = 1
    MAX_GUIDES = 1

    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
