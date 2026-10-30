# ====================================================================================================================
# SIMPLEFK - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'SimpleFk' module (BaseGuides), ATTRIBUTES from attributes.json
#            (merged with base/ through 'extends').
#
# ====================================================================================================================

from pathlib import Path

from ..base.guides import Guides as BaseGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(BaseGuides):

    MODULE_NAME = "SimpleFk"
    DEFAULT_NAME = "SimpleFk"

    # Auto chain of 3 guides.
    AUTO_GUIDES = 3

    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
