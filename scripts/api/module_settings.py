# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# API - MODULE SETTINGS
# ==========================================================
#
# Exemple complet du dict 'attributes' de chaque build_* de api.module,
# avec les valeurs par défaut de son attributes.json (enums par nom ;
# baseName / side / index / moduleType se passent en argument).
# Copier le dict, garder / modifier les clés voulues :
#
#   from api import module, module_settings
#
#   settings = dict(module_settings.ARM_SETTINGS, stretchIk=1, useRibbon=1)
#   module.build_arm(joints="L_shoulder_jnt", attributes=settings, side="L")
#
# Valeurs par défaut toujours à jour (lues sur le module) :
# api.module.get_default_settings(module_type).
#
# Fichier généré à partir des attributes.json : à régénérer s'ils changent.

# ====================================================================================================================
# ====================================================================================================================


__all__ = [
    "BASE_SETTINGS",
    "SIMPLE_FK_SETTINGS",
    "SIMPLE_IK_SETTINGS",
    "IK_SPINE_SETTINGS",
    "LIMB_SETTINGS",
    "ARM_SETTINGS",
    "LEG_BIPED_SETTINGS",
    "LEG_QUADRUPED_SETTINGS",
    "RIBBON_SETTINGS",
    "SETTINGS",
]


# ==========================================================
# base - build_base
# ==========================================================

BASE_SETTINGS = {
    # Build
    "simpleConnection":    0,
    "offsetGroup":         0,
    "noCtrl":              0,
    "attributesHost":      None,                       # node

    # Shape
    "shapeCtrl":           "Default",                  # Default | circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "shapeTranslate":      (0.0, 0.0, 0.0),
    "shapeRotate":         (0.0, 0.0, 0.0),
    "shapeScale":          (1.0, 1.0, 1.0),

    # Orientation
    "jointOrientation":    "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":           (1.0, 0.0, 0.0),
    "upVector":            (0.0, 0.0, 1.0),

    # Space Switch
    "spaceSwitchTargets":  [],                         # liste de nodes
}

# ==========================================================
# SimpleFk - build_simple_fk
# ==========================================================

SIMPLE_FK_SETTINGS = {
    # Build
    "simpleConnection":    0,
    "offsetGroup":         0,
    "noCtrl":              0,
    "attributesHost":      None,                       # node

    # Shape
    "shapeCtrl":           "Default",                  # Default | circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "shapeTranslate":      (0.0, 0.0, 0.0),
    "shapeRotate":         (0.0, 0.0, 0.0),
    "shapeScale":          (1.0, 1.0, 1.0),

    # Orientation
    "jointOrientation":    "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":           (1.0, 0.0, 0.0),
    "upVector":            (0.0, 0.0, 1.0),

    # Space Switch
    "spaceSwitchTargets":  [],                         # liste de nodes
}

# ==========================================================
# SimpleIk - build_simple_ik
# ==========================================================

SIMPLE_IK_SETTINGS = {
    # Build
    "simpleConnection":        0,
    "offsetGroup":             0,
    "noCtrl":                  0,
    "attributesHost":          None,                       # node

    # IK
    "rotatePlaneSolver":       1,
    "stretchIk":               1,
    "ikCtrlOrient":            "Joint",                    # Joint | World
    "poleCtrlOrient":          "World",                    # World | Joint

    # Shape
    "shapeCtrl":               "Default",                  # Default | circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "shapeTranslate":          (0.0, 0.0, 0.0),
    "shapeRotate":             (0.0, 0.0, 0.0),
    "shapeScale":              (1.0, 1.0, 1.0),

    # Orientation
    "jointOrientation":        "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":               (1.0, 0.0, 0.0),
    "upVector":                (0.0, 0.0, 1.0),

    # Space Switch
    "spaceSwitchTargets":      [],                         # liste de nodes
    "ikSpaceSwitchTargets":    [],                         # liste de nodes
    "poleSpaceSwitchTargets":  [],                         # liste de nodes
}

# ==========================================================
# IkSpine - build_ik_spine
# ==========================================================

IK_SPINE_SETTINGS = {
    # Build
    "simpleConnection":    0,
    "offsetGroup":         0,
    "attributesHost":      None,                       # node

    # IK Spine
    "spineJointCount":     8,
    "mainShape":           "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "mainSize":            1.5,
    "subShape":            "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "subSize":             1.0,

    # Shape
    "shapeTranslate":      (0.0, 0.0, 0.0),
    "shapeRotate":         (0.0, 0.0, 0.0),
    "shapeScale":          (1.0, 1.0, 1.0),

    # Orientation
    "jointOrientation":    "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":           (1.0, 0.0, 0.0),
    "upVector":            (0.0, 0.0, 1.0),

    # Space Switch
    "spaceSwitchTargets":  [],                         # liste de nodes
}

# ==========================================================
# Limb - build_limb
# ==========================================================

LIMB_SETTINGS = {
    # Build
    "simpleConnection":        0,
    "offsetGroup":             0,
    "attributesHost":          None,                       # node

    # Shape
    "shapeTranslate":          (0.0, 0.0, 0.0),
    "shapeRotate":             (0.0, 0.0, 0.0),
    "shapeScale":              (1.0, 1.0, 1.0),

    # Orientation
    "jointOrientation":        "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":               (1.0, 0.0, 0.0),
    "upVector":                (0.0, 0.0, 1.0),

    # IK/FK Switch
    "ikFkDefault":             "FK",                       # FK | IK
    "switchSize":              0.5,
    "switchShapeOffset":       (0.0, 2.0, 0.0),

    # FK
    "fkShape":                 "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "fkSize":                  1.0,

    # IK
    "ikShape":                 "cube",                     # cube | circle | square | sphere | diamond | arrow | plus | pyramid
    "ikSize":                  1.0,
    "ikCtrlOrient":            "Joint",                    # Joint | World
    "poleShape":               "diamond",                  # diamond | circle | square | cube | sphere | arrow | plus | pyramid
    "poleCtrlOrient":          "World",                    # World | Joint
    "poleSize":                1.0,
    "poleDistance":            1.0,
    "stretchIk":               1,

    # Ribbon
    "useRibbon":               0,
    "bindJointCount":          5,
    "ribbonWidth":             2.0,
    "ribbonDirection":         "U",                        # Auto | U | V
    "ribbonOffsetDirection":   "Z",                        # Y | Z
    "ribbonReverse":           0,
    "ribbonPinch":             0.1,
    "ribbonDegree":            "1",                        # Auto | 1 | 2 | 3 | 5 | 7
    "ribbonUniformIsoparms":   0,
    "follicleScale":           1,
    "levelCount":              1,
    "level1ControlCount":      5,
    "level1Shape":             "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level1ShapeTranslate":    (0.0, 0.0, 0.0),
    "level1ShapeScale":        (1.0, 1.0, 1.0),
    "level2ControlCount":      3,
    "level2Shape":             "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level2ShapeTranslate":    (0.0, 0.0, 0.0),
    "level2ShapeScale":        (1.0, 1.0, 1.0),

    # Space Switch
    "spaceSwitchTargets":      [],                         # liste de nodes
    "ikSpaceSwitchTargets":    [],                         # liste de nodes
    "poleSpaceSwitchTargets":  [],                         # liste de nodes
}

# ==========================================================
# Arm - build_arm
# ==========================================================

ARM_SETTINGS = {
    # Build
    "simpleConnection":        0,
    "offsetGroup":             0,
    "attributesHost":          None,                       # node

    # Shape
    "shapeTranslate":          (0.0, 0.0, 0.0),
    "shapeRotate":             (0.0, 0.0, 0.0),
    "shapeScale":              (1.0, 1.0, 1.0),

    # Orientation
    "jointOrientation":        "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":               (1.0, 0.0, 0.0),
    "upVector":                (0.0, 0.0, 1.0),

    # IK/FK Switch
    "ikFkDefault":             "FK",                       # FK | IK
    "switchSize":              0.5,
    "switchShapeOffset":       (0.0, 2.0, 0.0),

    # FK
    "fkShape":                 "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "fkSize":                  1.0,

    # IK
    "ikShape":                 "cube",                     # cube | circle | square | sphere | diamond | arrow | plus | pyramid
    "ikSize":                  1.0,
    "ikCtrlOrient":            "Joint",                    # Joint | World
    "poleShape":               "diamond",                  # diamond | circle | square | cube | sphere | arrow | plus | pyramid
    "poleCtrlOrient":          "World",                    # World | Joint
    "poleSize":                1.0,
    "poleDistance":            1.0,
    "stretchIk":               1,

    # Ribbon
    "useRibbon":               0,
    "bindJointCount":          5,
    "ribbonWidth":             2.0,
    "ribbonDirection":         "U",                        # Auto | U | V
    "ribbonOffsetDirection":   "Z",                        # Y | Z
    "ribbonReverse":           0,
    "ribbonPinch":             0.1,
    "ribbonDegree":            "1",                        # Auto | 1 | 2 | 3 | 5 | 7
    "ribbonUniformIsoparms":   0,
    "follicleScale":           1,
    "levelCount":              1,
    "level1ControlCount":      5,
    "level1Shape":             "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level1ShapeTranslate":    (0.0, 0.0, 0.0),
    "level1ShapeScale":        (1.0, 1.0, 1.0),
    "level2ControlCount":      3,
    "level2Shape":             "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level2ShapeTranslate":    (0.0, 0.0, 0.0),
    "level2ShapeScale":        (1.0, 1.0, 1.0),

    # Space Switch
    "spaceSwitchTargets":      [],                         # liste de nodes
    "ikSpaceSwitchTargets":    [],                         # liste de nodes
    "poleSpaceSwitchTargets":  [],                         # liste de nodes
}

# ==========================================================
# legBiped - build_leg_biped
# ==========================================================

LEG_BIPED_SETTINGS = {
    # Build
    "simpleConnection":        0,
    "offsetGroup":             0,
    "attributesHost":          None,                       # node

    # Shape
    "shapeTranslate":          (0.0, 0.0, 0.0),
    "shapeRotate":             (0.0, 0.0, 0.0),
    "shapeScale":              (1.0, 1.0, 1.0),

    # Orientation
    "jointOrientation":        "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":               (1.0, 0.0, 0.0),
    "upVector":                (0.0, 0.0, 1.0),

    # IK/FK Switch
    "ikFkDefault":             "FK",                       # FK | IK
    "switchSize":              0.5,
    "switchShapeOffset":       (0.0, 2.0, 0.0),

    # FK
    "fkShape":                 "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "fkSize":                  1.0,

    # IK
    "ikShape":                 "cube",                     # cube | circle | square | sphere | diamond | arrow | plus | pyramid
    "ikSize":                  1.0,
    "ikCtrlOrient":            "Joint",                    # Joint | World
    "poleShape":               "diamond",                  # diamond | circle | square | cube | sphere | arrow | plus | pyramid
    "poleCtrlOrient":          "World",                    # World | Joint
    "poleSize":                1.0,
    "poleDistance":            1.0,
    "stretchIk":               1,

    # Ribbon
    "useRibbon":               0,
    "bindJointCount":          5,
    "ribbonWidth":             2.0,
    "ribbonDirection":         "U",                        # Auto | U | V
    "ribbonOffsetDirection":   "Z",                        # Y | Z
    "ribbonReverse":           0,
    "ribbonPinch":             0.1,
    "ribbonDegree":            "1",                        # Auto | 1 | 2 | 3 | 5 | 7
    "ribbonUniformIsoparms":   0,
    "follicleScale":           1,
    "levelCount":              1,
    "level1ControlCount":      5,
    "level1Shape":             "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level1ShapeTranslate":    (0.0, 0.0, 0.0),
    "level1ShapeScale":        (1.0, 1.0, 1.0),
    "level2ControlCount":      3,
    "level2Shape":             "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level2ShapeTranslate":    (0.0, 0.0, 0.0),
    "level2ShapeScale":        (1.0, 1.0, 1.0),

    # Space Switch
    "spaceSwitchTargets":      [],                         # liste de nodes
    "ikSpaceSwitchTargets":    [],                         # liste de nodes
    "poleSpaceSwitchTargets":  [],                         # liste de nodes
}

# ==========================================================
# legQuadruped - build_leg_quadruped
# ==========================================================

LEG_QUADRUPED_SETTINGS = {
    # Build
    "simpleConnection":        0,
    "offsetGroup":             0,
    "attributesHost":          None,                       # node

    # Shape
    "shapeTranslate":          (0.0, 0.0, 0.0),
    "shapeRotate":             (0.0, 0.0, 0.0),
    "shapeScale":              (1.0, 1.0, 1.0),

    # Orientation
    "jointOrientation":        "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":               (1.0, 0.0, 0.0),
    "upVector":                (0.0, 0.0, 1.0),

    # IK/FK Switch
    "ikFkDefault":             "FK",                       # FK | IK
    "switchSize":              0.5,
    "switchShapeOffset":       (0.0, 2.0, 0.0),

    # FK
    "fkShape":                 "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "fkSize":                  1.0,

    # IK
    "ikShape":                 "cube",                     # cube | circle | square | sphere | diamond | arrow | plus | pyramid
    "ikSize":                  1.0,
    "ikCtrlOrient":            "Joint",                    # Joint | World
    "poleShape":               "diamond",                  # diamond | circle | square | cube | sphere | arrow | plus | pyramid
    "poleCtrlOrient":          "World",                    # World | Joint
    "quadrupedIkMethod":       "RP_RP",                    # SC_RP | RP_RP | RP_SC
    "poleSize":                1.0,
    "secondaryShape":          "sphere",                   # sphere | circle | square | cube | diamond | arrow | plus | pyramid
    "secondarySize":           0.75,
    "poleDistance":            1.0,
    "stretchIk":               1,

    # Ribbon
    "useRibbon":               0,
    "bindJointCount":          5,
    "ribbonWidth":             2.0,
    "ribbonDirection":         "U",                        # Auto | U | V
    "ribbonOffsetDirection":   "Z",                        # Y | Z
    "ribbonReverse":           0,
    "ribbonPinch":             0.1,
    "ribbonDegree":            "1",                        # Auto | 1 | 2 | 3 | 5 | 7
    "ribbonUniformIsoparms":   0,
    "follicleScale":           1,
    "levelCount":              1,
    "level1ControlCount":      5,
    "level1Shape":             "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level1ShapeTranslate":    (0.0, 0.0, 0.0),
    "level1ShapeScale":        (1.0, 1.0, 1.0),
    "level2ControlCount":      3,
    "level2Shape":             "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level2ShapeTranslate":    (0.0, 0.0, 0.0),
    "level2ShapeScale":        (1.0, 1.0, 1.0),

    # Space Switch
    "spaceSwitchTargets":      [],                         # liste de nodes
    "ikSpaceSwitchTargets":    [],                         # liste de nodes
    "poleSpaceSwitchTargets":  [],                         # liste de nodes
}

# ==========================================================
# Ribbon - build_ribbon
# ==========================================================

RIBBON_SETTINGS = {
    # Build
    "simpleConnection":       0,
    "offsetGroup":            0,
    "noCtrl":                 0,
    "attributesHost":         None,                       # node

    # Orientation
    "jointOrientation":       "Chain Plane",              # Chain Plane | Guide Up | Guides
    "aimVector":              (1.0, 0.0, 0.0),
    "upVector":               (0.0, 0.0, 1.0),

    # Ribbon
    "bindJointCount":         9,
    "ribbonWidth":            2.0,
    "ribbonSurface":          None,                       # node
    "ribbonJointGuides":      [],                         # liste de nodes
    "ribbonDirection":        "U",                        # Auto | U | V
    "ribbonOffsetDirection":  "Z",                        # Y | Z
    "ribbonReverse":          0,
    "ribbonPinch":            0.01,
    "ribbonDegree":           "2",                        # Auto | 1 | 2 | 3 | 5 | 7
    "ribbonUniformIsoparms":  0,
    "follicleScale":          1,
    "ribbonStretch":          0,
    "levelCount":             1,

    # Level 1
    "level1ControlCount":     3,
    "level1Shape":            "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level1ShapeTranslate":   (0.0, 0.0, 0.0),
    "level1ShapeScale":       (1.0, 1.0, 1.0),

    # Level 2
    "level2ControlCount":     3,
    "level2Shape":            "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level2ShapeTranslate":   (0.0, 0.0, 0.0),
    "level2ShapeScale":       (1.0, 1.0, 1.0),

    # Level 3
    "level3ControlCount":     3,
    "level3Shape":            "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level3ShapeTranslate":   (0.0, 0.0, 0.0),
    "level3ShapeScale":       (1.0, 1.0, 1.0),

    # Level 4
    "level4ControlCount":     3,
    "level4Shape":            "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level4ShapeTranslate":   (0.0, 0.0, 0.0),
    "level4ShapeScale":       (1.0, 1.0, 1.0),

    # Level 5
    "level5ControlCount":     3,
    "level5Shape":            "circle",                   # circle | square | cube | sphere | diamond | arrow | plus | pyramid
    "level5ShapeTranslate":   (0.0, 0.0, 0.0),
    "level5ShapeScale":       (1.0, 1.0, 1.0),
}


# moduleType -> exemple de settings.
SETTINGS = {
    "base": BASE_SETTINGS,
    "SimpleFk": SIMPLE_FK_SETTINGS,
    "SimpleIk": SIMPLE_IK_SETTINGS,
    "IkSpine": IK_SPINE_SETTINGS,
    "Limb": LIMB_SETTINGS,
    "Arm": ARM_SETTINGS,
    "legBiped": LEG_BIPED_SETTINGS,
    "legQuadruped": LEG_QUADRUPED_SETTINGS,
    "Ribbon": RIBBON_SETTINGS,
}
