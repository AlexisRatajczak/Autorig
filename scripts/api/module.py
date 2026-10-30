# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# API - MODULE
# ==========================================================
#
# Création et gestion des modules d'autorig (guides) : les mêmes classes
# Guides que l'UI, trouvées par leur moduleType (registry). Un module
# s'utilise par son instance Guides, son data node ou son root guide.
#
#   from api import module
#
#   module.create_rig_data("Dragon")
#   spine = module.create_module("IkSpine", rig_data="Dragon")
#   arm = module.create_arm(side="Left", parent=spine.guides[-1], rig_data="Dragon",
#                           settings={"useRibbon": 1, "stretchIk": 1})
#   module.mirror_module(arm)
#   module.build_rig("Dragon")
#
# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
# TYPES
#   list_module_types()                                        - moduleTypes disponibles (MODULE_NAME)
#   get_module_class(module_type)                              - classe Guides d'un moduleType
#   get_module_attributes(module_type)                         - attributs (ATTRIBUTES) d'un moduleType
#   get_joint_limits(module_type)                              - (min, max) de joints / guides d'un moduleType
#   check_joint_count(module_type, count)                      - erreur si 'count' sort de ces limites
#
# CREATE
#   create_module(module_type, name, side, index, parent, rig_data, settings, guides)
#                                                              - crée un module (+ rig data, settings)
#   create_base / create_simple_fk / create_simple_ik / create_ik_spine / create_limb /
#   create_arm / create_leg_biped / create_leg_quadruped / create_ribbon_module
#                                                              - create_module pour chaque type
#
# SCENE
#   list_modules(module_type)                                  - modules de la scène (instances Guides)
#   get_module(module)                                         - instance Guides (data node, root ou instance)
#   get_module_attribute(module, attribute)                    - valeur d'un attribut du data node
#   set_module_attribute(module, attribute, value)             - set un attribut (enum par nom, message par node)
#   set_module_attributes(module, settings)                    - set plusieurs attributs {attr: valeur}
#   add_guide(module, offset)                                  - ajoute un guide à la chaîne
#   duplicate_module(module) / mirror_module(module, side, axis) - copie / miroir (+ modules enfants)
#   delete_module(module)                                      - supprime le module (data node + guides)
#   update_guides(modules, remove_obsolete, dry_run)           - ajoute les attributs manquants (update_guides)
#
# RIG
#   create_rig_data(rig_name)                                  - crée (ou reprend) le node RIG_DATA
#   connect_to_rig(module, rig_data)                           - connecte un module à un RIG_DATA
#   build_rig(rig_data)                                        - PreBuild -> MainBuild -> PostBuild
#
# BUILD (un module seul : création + joints / guides + attributs + son Builder)
#   get_default_settings(module_type)                          - dict 'attributes' complet (valeurs par défaut)
#   get_joint_chain(joints, count)                             - joints d'une chaîne existante (racine ou liste)
#   build_module(module_type, joints, attributes, name, side, rig_data, parent, guides, delete_guides)
#                                                              - construit un module seul, retourne son Builder
#   build_base / build_simple_fk / build_simple_ik / build_ik_spine / build_limb /
#   build_arm / build_leg_biped / build_leg_quadruped / build_ribbon
#                                                              - build_module pour chaque Builder
#   place_guides(module, targets)                              - place les guides sur des nodes / positions
#   build_modules(modules, rig_data)                           - Builders de modules existants (sans le rig)
#
# Exemples complets de 'attributes' pour chaque module : api.module_settings.

# ====================================================================================================================
# ====================================================================================================================

import maya.cmds as cmds

from core.autorig.modules import registry
from core.autorig.modules import update_guides as update_guides_utilities
from core.autorig.rigData import init_rigData
from core.autorig.build import prebuild
from core.autorig.build import mainbuild
from core.autorig.build import postbuild

from importlib import reload

reload(registry)
reload(update_guides_utilities)
reload(init_rigData)
reload(prebuild)
reload(mainbuild)
reload(postbuild)


__all__ = [
    # types
    "list_module_types", "get_module_class", "get_module_attributes", "get_joint_limits",
    "check_joint_count",
    # create
    "create_module", "create_base", "create_simple_fk", "create_simple_ik", "create_ik_spine",
    "create_limb", "create_arm", "create_leg_biped", "create_leg_quadruped", "create_ribbon_module",
    # scene
    "list_modules", "get_module", "get_module_attribute", "set_module_attribute",
    "set_module_attributes", "add_guide", "duplicate_module", "mirror_module", "delete_module",
    "update_guides",
    # rig
    "create_rig_data", "connect_to_rig", "build_rig",
    # build
    "get_default_settings", "get_joint_chain",
    "build_module", "place_guides", "build_modules", "build_base", "build_simple_fk",
    "build_simple_ik", "build_ik_spine", "build_limb", "build_arm", "build_leg_biped",
    "build_leg_quadruped", "build_ribbon",
]

SIDES = ("Center", "Left", "Right")

RIG_DATA_SUFFIX = "_RIG_DATA"


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def _side(side):
    """'C' / 'L' / 'R' (ou nom complet, casse libre) -> 'Center' / 'Left' / 'Right'."""

    for name in SIDES:
        if str(side).lower() in (name.lower(), name[0].lower()):
            return name

    raise ValueError(f"Side '{side}' invalide (attendu : {', '.join(SIDES)}).")


def _rig_name(rig_data):
    """Nom du rig, qu'on passe 'Dragon' ou 'Dragon_RIG_DATA'."""

    rig_data = getattr(rig_data, "name", rig_data)

    return rig_data[: -len(RIG_DATA_SUFFIX)] if rig_data.endswith(RIG_DATA_SUFFIX) else rig_data


# ==========================================================
# TYPES
# ==========================================================

def list_module_types():
    """moduleTypes disponibles (MODULE_NAME de chaque core/autorig/modules/<dossier>/guides.py)."""

    return list(registry.list_module_types())


def get_module_class(module_type):
    """Classe Guides d'un moduleType (ex: 'Limb'), ou erreur s'il n'existe pas."""

    cls = registry.get_module_class(module_type)

    if not cls:
        raise ValueError(f"moduleType '{module_type}' inconnu (disponibles : {', '.join(list_module_types())}).")

    return cls


def get_module_attributes(module_type):
    """{attribut: définition} (ATTRIBUTES, d'après attributes.json) d'un moduleType."""

    return dict(get_module_class(module_type).ATTRIBUTES)


# Nombre de joints / guides acceptés par moduleType : (min, max), max None
# = pas de limite. Par défaut : (AUTO_GUIDES ou 1, MAX_GUIDES) de la classe
# Guides (en dessous d'AUTO_GUIDES, des guides créés resteraient non
# placés). Ruban : sa chaîne (ribbonJointGuides) compte au moins 2 joints.
JOINT_LIMITS = {
    "Ribbon": (2, None),
}


def get_joint_limits(module_type):
    """(min, max) de joints / guides d'un moduleType (max None = pas de limite)."""

    if module_type in JOINT_LIMITS:
        return JOINT_LIMITS[module_type]

    cls = get_module_class(module_type)

    return (cls.AUTO_GUIDES or 1, cls.MAX_GUIDES)


def check_joint_count(module_type, count):
    """Erreur si 'count' joints / guides sort des limites du moduleType (get_joint_limits)."""

    minimum, maximum = get_joint_limits(module_type)

    if count < minimum or (maximum is not None and count > maximum):

        expected = f"{minimum}" if minimum == maximum else (
            f"au moins {minimum}" if maximum is None else f"entre {minimum} et {maximum}"
        )

        raise ValueError(f"{module_type} : {count} joint(s) / guide(s) donné(s), {expected} attendu(s).")

    return count


# ==========================================================
# CREATE
# ==========================================================

def create_module(
    module_type,
    name=None,
    side="Center",
    index=0,
    parent=None,
    rig_data=None,
    settings=None,
    guides=None
):

    """
    Crée un module 'module_type' (data node, root guide, guides) et
    retourne son instance Guides.

    name     : baseName (DEFAULT_NAME du module par défaut).
    side     : 'Center' / 'Left' / 'Right' (ou 'C' / 'L' / 'R').
    index    : index de départ (incrémenté s'il est déjà pris).
    parent   : guide sous lequel ranger le module, ou None (la sélection
               n'est PAS utilisée, contrairement à l'UI).
    rig_data : rig auquel connecter le module ('Dragon' ou 'Dragon_RIG_DATA').
    settings : {attribut: valeur} appliqués après la création (enum par nom
               ou par index).
    guides   : nombre total de guides voulu (ajoutés après les guides auto) :
               erreur s'il sort des limites du module (check_joint_count).
    """

    cls = get_module_class(module_type)

    if guides:
        check_joint_count(module_type, int(guides))

    # Sans parent explicite, Guides prendrait la sélection : on la vide.
    selection = cmds.ls(selection=True) or []

    if parent is None:
        cmds.select(clear=True)

    try:
        instance = cls(name or cls.DEFAULT_NAME, side=_side(side), index=index, parent=getattr(parent, "root", parent))
        instance.create()
    finally:
        if selection:
            cmds.select(selection, replace=True)
        else:
            cmds.select(clear=True)

    if guides:
        while len(instance.guides) < int(guides) and not instance.has_reached_max_guides():
            instance.add_guide()

    if settings:
        set_module_attributes(instance, settings)

    if rig_data:
        connect_to_rig(instance, rig_data)

    return instance


def create_base(name=None, side="Center", parent=None, rig_data=None, settings=None, guides=None):

    """
    Module 'base' (chaîne simple) : create_module. Guides / joints : 1 ou plus.

    settings (exemple complet : module_settings.BASE_SETTINGS) :

        Build
            simpleConnection    bool    0
            offsetGroup         bool    0
            noCtrl              bool    0
            attributesHost      node    None

        Shape
            shapeCtrl           enum    "Default"                 Default | circle | square | cube | sphere | diamond | arrow | plus | pyramid
            shapeTranslate      vector  (0.0, 0.0, 0.0)
            shapeRotate         vector  (0.0, 0.0, 0.0)
            shapeScale          vector  (1.0, 1.0, 1.0)

        Orientation
            jointOrientation    enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector           vector  (1.0, 0.0, 0.0)
            upVector            vector  (0.0, 0.0, 1.0)

        Space Switch
            spaceSwitchTargets  nodes   []
    """

    return create_module("base", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


def create_simple_fk(name=None, side="Center", parent=None, rig_data=None, settings=None, guides=None):

    """
    Module 'SimpleFk' (chaîne FK) : create_module. Guides / joints : 3 ou plus.

    settings (exemple complet : module_settings.SIMPLE_FK_SETTINGS) :

        Build
            simpleConnection    bool    0
            offsetGroup         bool    0
            noCtrl              bool    0
            attributesHost      node    None

        Shape
            shapeCtrl           enum    "Default"                 Default | circle | square | cube | sphere | diamond | arrow | plus | pyramid
            shapeTranslate      vector  (0.0, 0.0, 0.0)
            shapeRotate         vector  (0.0, 0.0, 0.0)
            shapeScale          vector  (1.0, 1.0, 1.0)

        Orientation
            jointOrientation    enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector           vector  (1.0, 0.0, 0.0)
            upVector            vector  (0.0, 0.0, 1.0)

        Space Switch
            spaceSwitchTargets  nodes   []
    """

    return create_module("SimpleFk", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


def create_simple_ik(name=None, side="Center", parent=None, rig_data=None, settings=None, guides=None):

    """
    Module 'SimpleIk' (IK + pole, stretch) : create_module. Guides / joints : 3 ou plus.

    settings (exemple complet : module_settings.SIMPLE_IK_SETTINGS) :

        Build
            simpleConnection        bool    0
            offsetGroup             bool    0
            noCtrl                  bool    0
            attributesHost          node    None

        IK
            rotatePlaneSolver       bool    1
            stretchIk               bool    1
            ikCtrlOrient            enum    "Joint"                   Joint | World
            poleCtrlOrient          enum    "World"                   World | Joint

        Shape
            shapeCtrl               enum    "Default"                 Default | circle | square | cube | sphere | diamond | arrow | plus | pyramid
            shapeTranslate          vector  (0.0, 0.0, 0.0)
            shapeRotate             vector  (0.0, 0.0, 0.0)
            shapeScale              vector  (1.0, 1.0, 1.0)

        Orientation
            jointOrientation        enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector               vector  (1.0, 0.0, 0.0)
            upVector                vector  (0.0, 0.0, 1.0)

        Space Switch
            spaceSwitchTargets      nodes   []
            ikSpaceSwitchTargets    nodes   []
            poleSpaceSwitchTargets  nodes   []
    """

    return create_module("SimpleIk", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


def create_ik_spine(name=None, side="Center", parent=None, rig_data=None, settings=None, guides=None):

    """
    Module 'IkSpine' (spline IK, main + sub ctrl par guide) : create_module. Guides / joints : 5 ou plus (bassin -> poitrine).

    settings (exemple complet : module_settings.IK_SPINE_SETTINGS) :

        Build
            simpleConnection    bool    0
            offsetGroup         bool    0
            attributesHost      node    None

        IK Spine
            spineJointCount     int     8
            mainShape           enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            mainSize            float   1.5
            subShape            enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            subSize             float   1.0

        Shape
            shapeTranslate      vector  (0.0, 0.0, 0.0)
            shapeRotate         vector  (0.0, 0.0, 0.0)
            shapeScale          vector  (1.0, 1.0, 1.0)

        Orientation
            jointOrientation    enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector           vector  (1.0, 0.0, 0.0)
            upVector            vector  (0.0, 0.0, 1.0)

        Space Switch
            spaceSwitchTargets  nodes   []
    """

    return create_module("IkSpine", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


def create_limb(name=None, side="Left", parent=None, rig_data=None, settings=None, guides=None):

    """
    Module 'Limb' (IK/FK, stretch, ruban optionnel) : create_module. Guides / joints : 3.

    settings (exemple complet : module_settings.LIMB_SETTINGS) :

        Build
            simpleConnection        bool    0
            offsetGroup             bool    0
            attributesHost          node    None

        Shape
            shapeTranslate          vector  (0.0, 0.0, 0.0)
            shapeRotate             vector  (0.0, 0.0, 0.0)
            shapeScale              vector  (1.0, 1.0, 1.0)

        Orientation
            jointOrientation        enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector               vector  (1.0, 0.0, 0.0)
            upVector                vector  (0.0, 0.0, 1.0)

        IK/FK Switch
            ikFkDefault             enum    "FK"                      FK | IK
            switchSize              float   0.5
            switchShapeOffset       vector  (0.0, 2.0, 0.0)

        FK
            fkShape                 enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            fkSize                  float   1.0

        IK
            ikShape                 enum    "cube"                    cube | circle | square | sphere | diamond | arrow | plus | pyramid
            ikSize                  float   1.0
            ikCtrlOrient            enum    "Joint"                   Joint | World
            poleShape               enum    "diamond"                 diamond | circle | square | cube | sphere | arrow | plus | pyramid
            poleCtrlOrient          enum    "World"                   World | Joint
            poleSize                float   1.0
            poleDistance            float   1.0
            stretchIk               bool    1

        Ribbon
            useRibbon               bool    0
            bindJointCount          int     5
            ribbonWidth             float   2.0
            ribbonDirection         enum    "U"                       Auto | U | V
            ribbonOffsetDirection   enum    "Z"                       Y | Z
            ribbonReverse           bool    0
            ribbonPinch             float   0.1
            ribbonDegree            enum    "1"                       Auto | 1 | 2 | 3 | 5 | 7
            ribbonUniformIsoparms   bool    0
            follicleScale           bool    1
            levelCount              int     1
            level1ControlCount      int     5
            level1Shape             enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level1ShapeTranslate    vector  (0.0, 0.0, 0.0)
            level1ShapeScale        vector  (1.0, 1.0, 1.0)
            level2ControlCount      int     3
            level2Shape             enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level2ShapeTranslate    vector  (0.0, 0.0, 0.0)
            level2ShapeScale        vector  (1.0, 1.0, 1.0)

        Space Switch
            spaceSwitchTargets      nodes   []
            ikSpaceSwitchTargets    nodes   []
            poleSpaceSwitchTargets  nodes   []
    """

    return create_module("Limb", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


def create_arm(name=None, side="Left", parent=None, rig_data=None, settings=None, guides=None):

    """
    Module 'Arm' (limb) : create_module. Guides / joints : 3 (épaule, coude, poignet).

    settings (exemple complet : module_settings.ARM_SETTINGS) :

        Build
            simpleConnection        bool    0
            offsetGroup             bool    0
            attributesHost          node    None

        Shape
            shapeTranslate          vector  (0.0, 0.0, 0.0)
            shapeRotate             vector  (0.0, 0.0, 0.0)
            shapeScale              vector  (1.0, 1.0, 1.0)

        Orientation
            jointOrientation        enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector               vector  (1.0, 0.0, 0.0)
            upVector                vector  (0.0, 0.0, 1.0)

        IK/FK Switch
            ikFkDefault             enum    "FK"                      FK | IK
            switchSize              float   0.5
            switchShapeOffset       vector  (0.0, 2.0, 0.0)

        FK
            fkShape                 enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            fkSize                  float   1.0

        IK
            ikShape                 enum    "cube"                    cube | circle | square | sphere | diamond | arrow | plus | pyramid
            ikSize                  float   1.0
            ikCtrlOrient            enum    "Joint"                   Joint | World
            poleShape               enum    "diamond"                 diamond | circle | square | cube | sphere | arrow | plus | pyramid
            poleCtrlOrient          enum    "World"                   World | Joint
            poleSize                float   1.0
            poleDistance            float   1.0
            stretchIk               bool    1

        Ribbon
            useRibbon               bool    0
            bindJointCount          int     5
            ribbonWidth             float   2.0
            ribbonDirection         enum    "U"                       Auto | U | V
            ribbonOffsetDirection   enum    "Z"                       Y | Z
            ribbonReverse           bool    0
            ribbonPinch             float   0.1
            ribbonDegree            enum    "1"                       Auto | 1 | 2 | 3 | 5 | 7
            ribbonUniformIsoparms   bool    0
            follicleScale           bool    1
            levelCount              int     1
            level1ControlCount      int     5
            level1Shape             enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level1ShapeTranslate    vector  (0.0, 0.0, 0.0)
            level1ShapeScale        vector  (1.0, 1.0, 1.0)
            level2ControlCount      int     3
            level2Shape             enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level2ShapeTranslate    vector  (0.0, 0.0, 0.0)
            level2ShapeScale        vector  (1.0, 1.0, 1.0)

        Space Switch
            spaceSwitchTargets      nodes   []
            ikSpaceSwitchTargets    nodes   []
            poleSpaceSwitchTargets  nodes   []
    """

    return create_module("Arm", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


def create_leg_biped(name=None, side="Left", parent=None, rig_data=None, settings=None, guides=None):

    """
    Module 'legBiped' (limb) : create_module. Guides / joints : 3 (hanche, genou, cheville).

    settings (exemple complet : module_settings.LEG_BIPED_SETTINGS) :

        Build
            simpleConnection        bool    0
            offsetGroup             bool    0
            attributesHost          node    None

        Shape
            shapeTranslate          vector  (0.0, 0.0, 0.0)
            shapeRotate             vector  (0.0, 0.0, 0.0)
            shapeScale              vector  (1.0, 1.0, 1.0)

        Orientation
            jointOrientation        enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector               vector  (1.0, 0.0, 0.0)
            upVector                vector  (0.0, 0.0, 1.0)

        IK/FK Switch
            ikFkDefault             enum    "FK"                      FK | IK
            switchSize              float   0.5
            switchShapeOffset       vector  (0.0, 2.0, 0.0)

        FK
            fkShape                 enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            fkSize                  float   1.0

        IK
            ikShape                 enum    "cube"                    cube | circle | square | sphere | diamond | arrow | plus | pyramid
            ikSize                  float   1.0
            ikCtrlOrient            enum    "Joint"                   Joint | World
            poleShape               enum    "diamond"                 diamond | circle | square | cube | sphere | arrow | plus | pyramid
            poleCtrlOrient          enum    "World"                   World | Joint
            poleSize                float   1.0
            poleDistance            float   1.0
            stretchIk               bool    1

        Ribbon
            useRibbon               bool    0
            bindJointCount          int     5
            ribbonWidth             float   2.0
            ribbonDirection         enum    "U"                       Auto | U | V
            ribbonOffsetDirection   enum    "Z"                       Y | Z
            ribbonReverse           bool    0
            ribbonPinch             float   0.1
            ribbonDegree            enum    "1"                       Auto | 1 | 2 | 3 | 5 | 7
            ribbonUniformIsoparms   bool    0
            follicleScale           bool    1
            levelCount              int     1
            level1ControlCount      int     5
            level1Shape             enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level1ShapeTranslate    vector  (0.0, 0.0, 0.0)
            level1ShapeScale        vector  (1.0, 1.0, 1.0)
            level2ControlCount      int     3
            level2Shape             enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level2ShapeTranslate    vector  (0.0, 0.0, 0.0)
            level2ShapeScale        vector  (1.0, 1.0, 1.0)

        Space Switch
            spaceSwitchTargets      nodes   []
            ikSpaceSwitchTargets    nodes   []
            poleSpaceSwitchTargets  nodes   []
    """

    return create_module("legBiped", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


def create_leg_quadruped(name=None, side="Left", parent=None, rig_data=None, settings=None, guides=None, method=None):

    """
    Module 'legQuadruped' (limb, 2 ikHandles) : create_module. Guides / joints : 4 (hanche, genou, jarret, pied).

    method : raccourci de settings['quadrupedIkMethod'] ('SC_RP', 'RP_RP', 'RP_SC').

    settings (exemple complet : module_settings.LEG_QUADRUPED_SETTINGS) :

        Build
            simpleConnection        bool    0
            offsetGroup             bool    0
            attributesHost          node    None

        Shape
            shapeTranslate          vector  (0.0, 0.0, 0.0)
            shapeRotate             vector  (0.0, 0.0, 0.0)
            shapeScale              vector  (1.0, 1.0, 1.0)

        Orientation
            jointOrientation        enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector               vector  (1.0, 0.0, 0.0)
            upVector                vector  (0.0, 0.0, 1.0)

        IK/FK Switch
            ikFkDefault             enum    "FK"                      FK | IK
            switchSize              float   0.5
            switchShapeOffset       vector  (0.0, 2.0, 0.0)

        FK
            fkShape                 enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            fkSize                  float   1.0

        IK
            ikShape                 enum    "cube"                    cube | circle | square | sphere | diamond | arrow | plus | pyramid
            ikSize                  float   1.0
            ikCtrlOrient            enum    "Joint"                   Joint | World
            poleShape               enum    "diamond"                 diamond | circle | square | cube | sphere | arrow | plus | pyramid
            poleCtrlOrient          enum    "World"                   World | Joint
            quadrupedIkMethod       enum    "RP_RP"                   SC_RP | RP_RP | RP_SC
            poleSize                float   1.0
            secondaryShape          enum    "sphere"                  sphere | circle | square | cube | diamond | arrow | plus | pyramid
            secondarySize           float   0.75
            poleDistance            float   1.0
            stretchIk               bool    1

        Ribbon
            useRibbon               bool    0
            bindJointCount          int     5
            ribbonWidth             float   2.0
            ribbonDirection         enum    "U"                       Auto | U | V
            ribbonOffsetDirection   enum    "Z"                       Y | Z
            ribbonReverse           bool    0
            ribbonPinch             float   0.1
            ribbonDegree            enum    "1"                       Auto | 1 | 2 | 3 | 5 | 7
            ribbonUniformIsoparms   bool    0
            follicleScale           bool    1
            levelCount              int     1
            level1ControlCount      int     5
            level1Shape             enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level1ShapeTranslate    vector  (0.0, 0.0, 0.0)
            level1ShapeScale        vector  (1.0, 1.0, 1.0)
            level2ControlCount      int     3
            level2Shape             enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level2ShapeTranslate    vector  (0.0, 0.0, 0.0)
            level2ShapeScale        vector  (1.0, 1.0, 1.0)

        Space Switch
            spaceSwitchTargets      nodes   []
            ikSpaceSwitchTargets    nodes   []
            poleSpaceSwitchTargets  nodes   []
    """

    settings = dict(settings or {})

    if method:
        settings["quadrupedIkMethod"] = method

    return create_module("legQuadruped", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


def create_ribbon_module(name=None, side="Center", parent=None, rig_data=None, settings=None, guides=None, joint_guides=None):

    """
    Module 'Ribbon' (ruban NURBS) : create_module. Guides / joints : 2 ou plus (chaîne du ruban).

    joint_guides : chaîne du ruban (guides ou joints, 2 ou plus), raccourci de
                   settings['ribbonJointGuides'].

    settings (exemple complet : module_settings.RIBBON_SETTINGS) :

        Build
            simpleConnection       bool    0
            offsetGroup            bool    0
            noCtrl                 bool    0
            attributesHost         node    None

        Orientation
            jointOrientation       enum    "Chain Plane"             Chain Plane | Guide Up | Guides
            aimVector              vector  (1.0, 0.0, 0.0)
            upVector               vector  (0.0, 0.0, 1.0)

        Ribbon
            bindJointCount         int     9
            ribbonWidth            float   2.0
            ribbonSurface          node    None
            ribbonJointGuides      nodes   []
            ribbonDirection        enum    "U"                       Auto | U | V
            ribbonOffsetDirection  enum    "Z"                       Y | Z
            ribbonReverse          bool    0
            ribbonPinch            float   0.01
            ribbonDegree           enum    "2"                       Auto | 1 | 2 | 3 | 5 | 7
            ribbonUniformIsoparms  bool    0
            follicleScale          bool    1
            ribbonStretch          bool    0
            levelCount             int     1

        Level 1
            level1ControlCount     int     3
            level1Shape            enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level1ShapeTranslate   vector  (0.0, 0.0, 0.0)
            level1ShapeScale       vector  (1.0, 1.0, 1.0)

        Level 2
            level2ControlCount     int     3
            level2Shape            enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level2ShapeTranslate   vector  (0.0, 0.0, 0.0)
            level2ShapeScale       vector  (1.0, 1.0, 1.0)

        Level 3
            level3ControlCount     int     3
            level3Shape            enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level3ShapeTranslate   vector  (0.0, 0.0, 0.0)
            level3ShapeScale       vector  (1.0, 1.0, 1.0)

        Level 4
            level4ControlCount     int     3
            level4Shape            enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level4ShapeTranslate   vector  (0.0, 0.0, 0.0)
            level4ShapeScale       vector  (1.0, 1.0, 1.0)

        Level 5
            level5ControlCount     int     3
            level5Shape            enum    "circle"                  circle | square | cube | sphere | diamond | arrow | plus | pyramid
            level5ShapeTranslate   vector  (0.0, 0.0, 0.0)
            level5ShapeScale       vector  (1.0, 1.0, 1.0)
    """

    settings = dict(settings or {})

    if joint_guides:
        check_joint_count("Ribbon", len(joint_guides))
        settings["ribbonJointGuides"] = list(joint_guides)

    return create_module("Ribbon", name, side, parent=parent, rig_data=rig_data, settings=settings, guides=guides)


# ==========================================================
# SCENE
# ==========================================================

def list_modules(module_type=None):
    """Modules de la scène (instances Guides), filtrés par moduleType si donné."""

    modules = []

    for data_node in update_guides_utilities.list_data_nodes():

        instance = registry.load_guide(data_node)

        if instance and (module_type is None or instance.MODULE_NAME == module_type):
            modules.append(instance)

    return modules


def get_module(module):

    """
    Instance Guides d'un module : instance telle quelle, data node
    ('*_GUIDE_DATA'), ou un guide du module (son data node est retrouvé).
    """

    if hasattr(module, "data_node"):
        return module

    node = getattr(module, "name", module)

    if not cmds.objExists(node):
        raise ValueError(f"'{node}' n'existe pas.")

    if cmds.nodeType(node) != "network":
        node = get_module_class("base").get_data_node(node)

    instance = registry.load_guide(node) if node else None

    if not instance:
        raise ValueError(f"Aucun module trouvé pour '{module}'.")

    return instance


def get_module_attribute(module, attribute):
    """Valeur d'un attribut du data node du module (enum : index)."""

    return cmds.getAttr(f"{get_module(module).data_node}.{attribute}")


def set_module_attribute(module, attribute, value):

    """
    Set un attribut du data node du module (Guides.set_attribute). Un
    enum accepte son nom (ex: 'RP_RP') ou son index ; un attribut
    message un node, ou une liste de nodes s'il est multi.
    """

    instance = get_module(module)

    plug = f"{instance.data_node}.{attribute}"

    if cmds.objExists(plug) and cmds.getAttr(plug, type=True) == "message":

        instance.unlock_attributes([attribute])

        try:
            return _connect_message(instance.data_node, attribute, value)
        finally:
            instance.lock_attributes()

    if isinstance(value, str) and cmds.objExists(plug) and cmds.getAttr(plug, type=True) == "enum":

        names = cmds.attributeQuery(attribute, node=instance.data_node, listEnum=True)[0].split(":")

        if value not in names:
            raise ValueError(f"'{value}' n'est pas une valeur de '{plug}' ({', '.join(names)}).")

        value = names.index(value)

    return instance.set_attribute(attribute, value)


def _connect_message(data_node, attribute, value):

    """
    Connecte 'value' (node, ou liste de nodes si l'attribut est multi)
    à l'attribut message 'attribute' du data node (anciennes
    connexions retirées). Retourne le data node.
    """

    plug = f"{data_node}.{attribute}"

    nodes = [getattr(node, 'root', getattr(node, 'name', node)) for node in (value if isinstance(value, (list, tuple)) else [value]) if node]

    multi = cmds.attributeQuery(attribute, node=data_node, multi=True)

    # listConnections(connections=True) : [plug du data node, source, ...].
    connections = cmds.listConnections(plug, source=True, destination=False, plugs=True, connections=True) or []

    for own, source in zip(connections[::2], connections[1::2]):
        cmds.disconnectAttr(source, own)

    if multi:
        for index in cmds.getAttr(plug, multiIndices=True) or []:
            cmds.removeMultiInstance(f"{plug}[{index}]", b=True)

    for index, node in enumerate(nodes if multi else nodes[:1]):
        cmds.connectAttr(f"{node}.message", f"{plug}[{index}]" if multi else plug, force=True)

    return data_node


def set_module_attributes(module, settings):
    """set_module_attribute pour chaque {attribut: valeur} de 'settings'."""

    instance = get_module(module)

    for attribute, value in settings.items():
        set_module_attribute(instance, attribute, value)

    return instance


def add_guide(module, offset=None):
    """Ajoute un guide à la chaîne du module (limité par MAX_GUIDES). Retourne l'instance."""

    instance = get_module(module)
    instance.add_guide(offset=offset)

    return instance


def duplicate_module(module):
    """Copie du module et de ses modules enfants. Retourne la nouvelle instance."""

    return get_module(module).duplicate()


def mirror_module(module, side="Right", axis="YZ"):
    """Miroir du module et de ses modules enfants. Retourne la nouvelle instance."""

    return get_module(module).create_mirror(replace_side=_side(side), axis=axis)


def delete_module(module):
    """Supprime le module (data node, root et guides)."""

    return get_module(module).delete()


def update_guides(modules=None, remove_obsolete=False, dry_run=False):
    """Met à jour les attributs des modules (tous par défaut) d'après leur attributes.json."""

    data_nodes = [get_module(module).data_node for module in modules] if modules else None

    return update_guides_utilities.update_guides(data_nodes, remove_obsolete=remove_obsolete, dry_run=dry_run)


# ==========================================================
# RIG
# ==========================================================

def create_rig_data(rig_name):
    """Crée le node '{rig_name}_RIG_DATA' (ou reprend celui qui existe). Retourne le RigData."""

    rig_name = _rig_name(rig_name)

    rig_data = init_rigData.RigData(rig_name)

    if cmds.objExists(f"{rig_name}{RIG_DATA_SUFFIX}"):
        rig_data.data_node = f"{rig_name}{RIG_DATA_SUFFIX}"
    else:
        rig_data.create()

    return rig_data


def connect_to_rig(module, rig_data):
    """Connecte le module au node RIG_DATA du rig ('Dragon' ou 'Dragon_RIG_DATA')."""

    instance = get_module(module)
    instance.connect_rig_data(_rig_name(rig_data))

    return instance


def build_rig(rig_data):
    """Build complet d'un rig, comme le bouton Build : PreBuild -> MainBuild -> PostBuild."""

    # Comme l'UI : PreBuild / PostBuild reçoivent le node '{rig}_RIG_DATA'.
    node = f"{_rig_name(rig_data)}{RIG_DATA_SUFFIX}"

    if not cmds.objExists(node):
        raise ValueError(f"'{node}' n'existe pas.")

    pre = prebuild.PreBuild(node)
    main = mainbuild.MainBuild(pre.hierarchy_data)
    postbuild.PostBuild(node)

    return main


# ==========================================================
# BUILD (un module seul)
# ==========================================================
#
# Une fonction par Builder : crée le module (guides nommés comme le
# build les attend), le place sur une chaîne de joints existante
# ('joints') ou sur 'guides', applique 'attributes' ({attr: valeur},
# exemples complets dans api.module_settings) puis lance SON Builder
# via MainBuild, comme le build complet mais pour ce seul module.
# Retourne le Builder (builder.joints, builder.controls, ...).
#
#   from api import module, module_settings
#
#   arm = module.build_arm(
#       joints="L_shoulder_jnt",                                 # chaîne existante
#       attributes=dict(module_settings.ARM_SETTINGS, useRibbon=1),
#       side="L",
#   )
#

def get_default_settings(module_type):

    """
    Dict 'attributes' complet d'un moduleType avec ses valeurs par défaut
    (lues sur sa classe Guides) : enums par nom, vecteurs en tuple,
    messages vides. Sans baseName / side / index / moduleType.
    """

    settings = {}

    for attribute, definition in get_module_class(module_type).ATTRIBUTES.items():

        if attribute in ("baseName", "side", "index", "moduleType", "parent", "rigData", "rootGuide", "guides"):
            continue

        kind = definition.get("at")
        value = definition.get("value")

        if kind == "message":
            value = [] if definition.get("multi") else None

        elif kind == "enum":
            names = (definition.get("enumName") or "").split(":")
            value = names[int(value or 0)] if names else value

        elif kind == "double3":
            value = tuple(value or (0.0, 0.0, 0.0))

        settings[attribute] = value

    return settings


def get_joint_chain(joints, count=None):

    """
    Joints d'une chaîne existante : liste de joints telle quelle, ou joint
    racine suivi de son premier enfant joint à chaque niveau. 'count' :
    nombre maximum de joints (None = toute la chaîne).
    """

    if isinstance(joints, (list, tuple)):
        chain = [getattr(joint, "name", joint) for joint in joints]

    else:
        chain = [getattr(joints, "name", joints)]

        while True:

            children = cmds.listRelatives(chain[-1], children=True, type="joint", fullPath=True) or []

            if not children:
                break

            chain.append(cmds.ls(children[0])[0])

    for joint in chain:
        if not cmds.objExists(joint):
            raise ValueError(f"Joint '{joint}' introuvable.")

    return chain[:count] if count else chain


def build_module(
    module_type,
    joints=None,
    attributes=None,
    name=None,
    side="Center",
    rig_data=None,
    parent=None,
    guides=None,
    delete_guides=False
):

    """
    Crée puis construit un module 'module_type' seul. Retourne son Builder.

    joints        : chaîne de joints existante (racine, ou liste) : si
                    différent de None, les guides sont placés dessus
                    (position + orientation) au lieu de 'guides'. Racine :
                    chaîne suivie jusqu'au max du module. Erreur si le
                    nombre de joints sort des limites (check_joint_count).
                    Ruban : la chaîne entière devient ribbonJointGuides.
    attributes    : {attribut: valeur} du module (exemples complets :
                    api.module_settings ; enum par nom ou index, message
                    par node ou liste de nodes).
    rig_data      : rig ('Dragon' / 'Dragon_RIG_DATA') : connexion + couleurs
                    et nom des groupes du rig.
    parent        : guide parent du module (son joint / ctrl sert de parent).
    guides        : sans 'joints' : un élément par guide (le premier = root),
                    node ou position [x, y, z].
    delete_guides : supprimer les guides du module une fois construit.
    """

    cls = get_module_class(module_type)
    attributes = dict(attributes or {})

    if joints is not None:

        is_ribbon = cls.MODULE_NAME == "Ribbon"

        # Joint racine : la chaîne est suivie jusqu'au max du module ; liste :
        # prise telle quelle. Dans les deux cas, erreur hors des limites.
        _, maximum = get_joint_limits(module_type)

        chain = get_joint_chain(joints, maximum if isinstance(joints, str) else None)

        check_joint_count(module_type, len(chain))

        if is_ribbon:
            # Ruban : 1 guide (root) ; la chaîne porte la surface.
            if not attributes.get("ribbonJointGuides"):
                attributes["ribbonJointGuides"] = chain
            chain = chain[:1]

        guides = chain

    guides = list(guides or [])

    if guides and joints is None:
        check_joint_count(module_type, len(guides))

    instance = create_module(
        module_type,
        name=name,
        side=side,
        parent=parent,
        rig_data=rig_data,
        settings=attributes,
        guides=(len(guides) or None) if cls.MODULE_NAME != "Ribbon" else None
    )

    place_guides(instance, guides)

    builder = build_modules([instance], rig_data=rig_data).get(instance.data_node)

    if delete_guides:
        instance.delete()

    return builder


def place_guides(module, targets):

    """
    Place les guides du module (root en premier) sur 'targets' : node
    (position + orientation) ou position [x, y, z]. Les guides sont
    chaînés : chacun est placé après son parent.
    """

    instance = get_module(module)

    for guide, target in zip(instance.guides, targets):

        if isinstance(target, (list, tuple)):
            cmds.xform(guide, worldSpace=True, translation=list(target))
        else:
            cmds.matchTransform(guide, getattr(target, "name", target), position=True, rotation=True)

    return instance


def build_modules(modules, rig_data=None):

    """
    Construit 'modules' (instances, data nodes ou guides) avec MainBuild,
    comme le bouton Build mais sans passer par tout le rig : données
    collectées comme PreBuild (collect_module_data / guides). Retourne
    {data_node: Builder}.
    """

    data_nodes = [get_module(module).data_node for module in modules]

    rig_node = f"{_rig_name(rig_data)}{RIG_DATA_SUFFIX}" if rig_data else None

    # PreBuild sans son __init__ (qui lit et valide tout le rig) : seules
    # ses méthodes de collecte servent ici.
    pre = prebuild.PreBuild.__new__(prebuild.PreBuild)
    pre.rig_data = rig_node
    pre.base_guides_class = registry.get_base_guides_class()
    pre.modules = data_nodes
    pre.data = {data_node: pre.collect_module_data(data_node) for data_node in data_nodes}

    for data_node in data_nodes:
        pre.validate_attributes(data_node)

    main = mainbuild.MainBuild(pre.build_rig_hierarchy())

    return dict(main.builders)


def build_base(joints=None, attributes=None, name=None, side="Center", rig_data=None, parent=None, guides=None):

    """
    Builder 'base' (chaîne simple) : build_module. Joints : 1 ou plus (erreur sinon, voir check_joint_count).
    attributes : mêmes clés que les settings de create_base (exemple complet :
    module_settings.BASE_SETTINGS).
    """

    return build_module("base", joints, attributes, name, side, rig_data, parent, guides)


def build_simple_fk(joints=None, attributes=None, name=None, side="Center", rig_data=None, parent=None, guides=None):

    """
    Builder 'SimpleFk' (chaîne FK) : build_module. Joints : 3 ou plus (erreur sinon, voir check_joint_count).
    attributes : mêmes clés que les settings de create_simple_fk (exemple complet :
    module_settings.SIMPLE_FK_SETTINGS).
    """

    return build_module("SimpleFk", joints, attributes, name, side, rig_data, parent, guides)


def build_simple_ik(joints=None, attributes=None, name=None, side="Center", rig_data=None, parent=None, guides=None):

    """
    Builder 'SimpleIk' (IK + pole, stretch) : build_module. Joints : 3 ou plus (erreur sinon, voir check_joint_count).
    attributes : mêmes clés que les settings de create_simple_ik (exemple complet :
    module_settings.SIMPLE_IK_SETTINGS).
    """

    return build_module("SimpleIk", joints, attributes, name, side, rig_data, parent, guides)


def build_ik_spine(joints=None, attributes=None, name=None, side="Center", rig_data=None, parent=None, guides=None):

    """
    Builder 'IkSpine' (spline IK, main + sub ctrl par guide) : build_module. Joints : 5 ou plus (bassin -> poitrine) (erreur sinon, voir check_joint_count).
    attributes : mêmes clés que les settings de create_ik_spine (exemple complet :
    module_settings.IK_SPINE_SETTINGS).
    """

    return build_module("IkSpine", joints, attributes, name, side, rig_data, parent, guides)


def build_limb(joints=None, attributes=None, name=None, side="Left", rig_data=None, parent=None, guides=None):

    """
    Builder 'Limb' (IK/FK, stretch, ruban optionnel) : build_module. Joints : 3 (erreur sinon, voir check_joint_count).
    attributes : mêmes clés que les settings de create_limb (exemple complet :
    module_settings.LIMB_SETTINGS).
    """

    return build_module("Limb", joints, attributes, name, side, rig_data, parent, guides)


def build_arm(joints=None, attributes=None, name=None, side="Left", rig_data=None, parent=None, guides=None):

    """
    Builder 'Arm' (limb) : build_module. Joints : 3 (épaule, coude, poignet) (erreur sinon, voir check_joint_count).
    attributes : mêmes clés que les settings de create_arm (exemple complet :
    module_settings.ARM_SETTINGS).
    """

    return build_module("Arm", joints, attributes, name, side, rig_data, parent, guides)


def build_leg_biped(joints=None, attributes=None, name=None, side="Left", rig_data=None, parent=None, guides=None):

    """
    Builder 'legBiped' (limb) : build_module. Joints : 3 (hanche, genou, cheville) (erreur sinon, voir check_joint_count).
    attributes : mêmes clés que les settings de create_leg_biped (exemple complet :
    module_settings.LEG_BIPED_SETTINGS).
    """

    return build_module("legBiped", joints, attributes, name, side, rig_data, parent, guides)


def build_leg_quadruped(joints=None, attributes=None, name=None, side="Left", rig_data=None, parent=None, guides=None):

    """
    Builder 'legQuadruped' (limb, 2 ikHandles) : build_module. Joints : 4 (hanche, genou, jarret, pied) (erreur sinon, voir check_joint_count).
    attributes : mêmes clés que les settings de create_leg_quadruped (exemple complet :
    module_settings.LEG_QUADRUPED_SETTINGS).
    """

    return build_module("legQuadruped", joints, attributes, name, side, rig_data, parent, guides)


def build_ribbon(joints=None, attributes=None, name=None, side="Center", rig_data=None, parent=None, guides=None):

    """
    Builder 'Ribbon' (ruban NURBS) : build_module. Joints : 2 ou plus (chaîne du ruban) (erreur sinon, voir check_joint_count).
    'joints' = chaîne du ruban (ribbonJointGuides), root du module sur son premier
    joint ; sinon attributes['ribbonSurface'].
    attributes : mêmes clés que les settings de create_ribbon_module (exemple complet :
    module_settings.RIBBON_SETTINGS).
    """

    return build_module("Ribbon", joints, attributes, name, side, rig_data, parent, guides)
