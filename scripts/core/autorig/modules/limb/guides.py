from pathlib import Path

from ..base.guides import Guides as BaseGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(BaseGuides):

    MODULE_NAME = "Limb"
    DEFAULT_NAME = "Limb"

    # Chaîne créée automatiquement : root + 2 guides (3 au total :
    # épaule/hanche, coude/genou, poignet/cheville).
    AUTO_GUIDES = 3
    MAX_GUIDES = 3

    # ATTRIBUTES derive de attributes.json (fusionne avec base/ via 'extends').
    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
