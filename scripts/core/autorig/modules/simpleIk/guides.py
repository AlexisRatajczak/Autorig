from pathlib import Path

from ..base.guides import Guides as BaseGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(BaseGuides):

    MODULE_NAME = "SimpleIk"
    DEFAULT_NAME = "SimpleIk"

    # Chaîne créée automatiquement : root + 1 guide (2 au total).
    AUTO_GUIDES = 3

    # ATTRIBUTES derive de attributes.json (fusionne avec base/ via 'extends').
    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
