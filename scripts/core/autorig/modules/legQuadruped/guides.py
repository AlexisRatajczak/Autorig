from pathlib import Path

from ..limb.guides import Guides as LimbGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(LimbGuides):

    MODULE_NAME = "legQuadruped"
    DEFAULT_NAME = "legQuadruped"

    # Chaîne créée automatiquement : hanche, genou, jarret, pied.
    AUTO_GUIDES = 4
    MAX_GUIDES = 4

    # ATTRIBUTES derive de attributes.json (fusionne avec limb/ via 'extends').
    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
