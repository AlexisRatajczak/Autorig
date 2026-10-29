from pathlib import Path

from ..limb.guides import Guides as LimbGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(LimbGuides):

    MODULE_NAME = "legBiped"
    DEFAULT_NAME = "legBiped"

    # Guides hérités de limb : hanche, genou, cheville.

    # ATTRIBUTES derive de attributes.json (fusionne avec limb/ via 'extends').
    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
