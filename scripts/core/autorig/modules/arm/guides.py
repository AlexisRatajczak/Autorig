from pathlib import Path

from ..limb.guides import Guides as LimbGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(LimbGuides):

    MODULE_NAME = "Arm"
    DEFAULT_NAME = "Arm"

    # Guides hérités de limb : épaule, coude, poignet.

    # ATTRIBUTES derive de attributes.json (fusionne avec limb/ via 'extends').
    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
