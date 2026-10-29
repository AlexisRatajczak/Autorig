from ..limb import builder as limb_builder

from importlib import reload

reload(limb_builder)


# ==========================================================
# LEG BIPED BUILDER
# ==========================================================
#
# Limb (hanche -> genou -> cheville) : toutes les étapes sont héritées
# de limb.Builder. Surcharger ici ce qui est propre à la jambe.
#

class Builder(limb_builder.Builder):

    pass
