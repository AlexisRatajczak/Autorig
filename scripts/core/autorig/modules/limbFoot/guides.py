# ====================================================================================================================
# FOOT - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'Foot' module (BaseGuides), ATTRIBUTES from attributes.json
#            (merged with base/ through 'extends').
#
# ====================================================================================================================

from pathlib import Path

from ..simpleBase.guides import Guides as BaseGuides
from ..ui_schema import attribute_defs, load_ui_settings

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(BaseGuides):

    MODULE_NAME = "Limb_Foot"
    DEFAULT_NAME = "Foot"

    # Ankle, ball, [phalanges...], tip: 3 at creation, + Add Guide for each extra phalanx
    # (parent the root guide under the leg end guide to attach it).
    AUTO_GUIDES = 3
    MAX_GUIDES = None

    # Reverse foot pivots (no joint), under the root (ankle): heel, tiptoe, left / right edges.
    PIVOT_GUIDES = {
        "heelGuide": ("heel", (0, -2, -2)),
        "tiptoeGuide": ("tiptoe", (0, -2, 10)),
        "bankLGuide": ("bankL", (2, -2, 5)),
        "bankRGuide": ("bankR", (-2, -2, 5)),
    }

    # Mirror: the left edge of the mirrored foot comes from the right edge of the source.
    PIVOT_MIRROR_SWAP = {"bankLGuide": "bankRGuide", "bankRGuide": "bankLGuide"}

    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)
