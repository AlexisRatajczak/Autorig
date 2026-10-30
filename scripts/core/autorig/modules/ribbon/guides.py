# ====================================================================================================================
# RIBBON - GUIDES
# ====================================================================================================================
#
#   Guides - guide class of the 'Ribbon' module (BaseGuides), ATTRIBUTES from attributes.json
#       create_root(radius, parent)     - base root with a wavy ribbon shape instead of the sphere
#       get_root_shape_curves()         - local points of the ribbon shape curves
#
# ====================================================================================================================

import math
from pathlib import Path

import maya.cmds as cmds

from ..base.guides import Guides as BaseGuides
from ..ui_schema import attribute_defs, load_ui_settings
from .... import log

_MODULE_DIR = Path(__file__).resolve().parent


class Guides(BaseGuides):

    MODULE_NAME = "Ribbon"
    DEFAULT_NAME = "Ribbon"

    # Root guide only.
    AUTO_GUIDES = 1
    MAX_GUIDES = 1

    # Root shape: wavy ribbon along X (2 sine edges + rungs) instead of the base sphere.
    ROOT_SHAPE_LENGTH = 3.0
    ROOT_SHAPE_WIDTH = 0.8
    ROOT_SHAPE_WAVE = 0.35
    ROOT_SHAPE_SAMPLES = 24
    ROOT_SHAPE_RUNGS = 7
    ROOT_SHAPE_COLOR = 18

    ATTRIBUTES = attribute_defs(load_ui_settings(_MODULE_DIR), MODULE_NAME, DEFAULT_NAME)

    def create_root(self, radius=0.5, parent=None):

        """Base root ({module}_GUIDE_ROOT) with a ribbon shape instead of the sphere (get_root_shape_curves)."""

        if parent is None:
            parent = self.parent

        guide = self.create_guide(parent)
        self.root = cmds.rename(guide, f"{self.module_name}_GUIDE_ROOT")
        self.guides[self.guides.index(guide)] = self.root

        for index, points in enumerate(self.get_root_shape_curves()):

            curve = cmds.curve(degree=1, point=points, name=f"{self.module_name}_RIBBON_{index:02d}_temp")
            shape = cmds.listRelatives(curve, shapes=True)[0]

            cmds.parent(shape, self.root, shape=True, relative=True)
            cmds.delete(curve)

            cmds.setAttr(f"{shape}.overrideEnabled", True)
            cmds.setAttr(f"{shape}.overrideColor", self.ROOT_SHAPE_COLOR)

        log.info(f"Root guide created : {self.root}")

        return self.root

    def get_root_shape_curves(self):

        """
        Local points of the root shape curves: two sine edges along X
        (offset by +/- width / 2 in Z), then straight rungs between them.
        """

        half_length = self.ROOT_SHAPE_LENGTH * 0.5
        half_width = self.ROOT_SHAPE_WIDTH * 0.5

        def edge_point(t, side):
            x = -half_length + t * self.ROOT_SHAPE_LENGTH
            y = math.sin(t * math.pi * 2.0) * self.ROOT_SHAPE_WAVE
            return (x, y, side * half_width)

        samples = [i / self.ROOT_SHAPE_SAMPLES for i in range(self.ROOT_SHAPE_SAMPLES + 1)]

        curves = [
            [edge_point(t, -1) for t in samples],
            [edge_point(t, 1) for t in samples],
        ]

        rungs = max(2, self.ROOT_SHAPE_RUNGS)

        for i in range(rungs):
            t = i / (rungs - 1)
            curves.append([edge_point(t, -1), edge_point(t, 1)])

        return curves
