from pathlib import Path

from ..base.guides import Guides as BaseGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(BaseGuides):

    MODULE_NAME = "IkSpine"
    DEFAULT_NAME = "IkSpine"

    # Chaîne créée automatiquement (bassin -> poitrine) : au moins 3 guides
    # pour la spline IK, plus si besoin (+ Add Guide).
    AUTO_GUIDES = 5

    # ATTRIBUTES derive de attributes.json (fusionne avec base/ via 'extends').
    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
