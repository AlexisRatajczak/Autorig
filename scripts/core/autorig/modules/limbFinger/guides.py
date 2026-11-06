# ====================================================================================================================
# FINGER - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'Finger' module (LimbGuides), ATTRIBUTES from attributes.json
#            (merged with limb/ through 'extends').
#
# ====================================================================================================================

from pathlib import Path

from ..limb.guides import Guides as LimbGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(LimbGuides):

    MODULE_NAME = "Limb_Finger"
    DEFAULT_NAME = "Finger"

    # Base, middle, distal, tip (+ Add Guide: one more phalanx).
    AUTO_GUIDES = 4
    MAX_GUIDES = 5

    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
