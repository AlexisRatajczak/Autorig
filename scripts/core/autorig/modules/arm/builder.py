from ..limb import builder as limb_builder

from importlib import reload

reload(limb_builder)


# ==========================================================
# ARM BUILDER
# ==========================================================
#
# Limb (épaule -> coude -> poignet) : toutes les étapes sont héritées
# de limb.Builder. Surcharger ici ce qui est propre au bras.
#

class Builder(limb_builder.Builder):

    pass
