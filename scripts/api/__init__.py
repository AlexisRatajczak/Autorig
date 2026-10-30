# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# API
# ==========================================================
#
# Façade sur les modules utilities, séparée par domaine :
#
#   rig        - joints, ctrls, contraintes de matrix, space switch, ruban
#   blendshape - noeuds blendShape et targets
#   geo        - requêtes scène, checks/fixes mesh, UV, matières, couleurs, naming
#   settings   - fichiers de settings des outils
#   module     - modules d'autorig (guides) : création, scène, build
#   module_settings - exemples complets du dict 'attributes' de chaque module
#
#   from api import rig, geo, module
#   rig.create_ctrl("L_arm_00_ctrl", shape="circle")
#   module.create_arm(side="Left", rig_data="Dragon")
#
# Toutes les fonctions sont aussi accessibles à plat :
#
#   import api
#   api.create_ctrl("L_arm_00_ctrl", shape="circle")

# ====================================================================================================================
# ====================================================================================================================

from . import rig
from . import blendshape
from . import geo
from . import settings
from . import module
from . import module_settings

from importlib import reload

reload(rig)
reload(blendshape)
reload(geo)
reload(settings)
reload(module)
reload(module_settings)

from .rig import *
from .blendshape import *
from .geo import *
from .settings import *
from .module import *
