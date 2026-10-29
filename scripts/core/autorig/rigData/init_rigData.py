import json
import os

import maya.cmds as cmds

from ... import log

COLORS_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "config", "colorCtrl_config.json"
)


def load_default_colors():

    with open(COLORS_CONFIG_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


DEFAULT_COLORS = load_default_colors()


class RigData:

    COLORS = {

        "Left": [
            "FK Main",
            "FK Secondary",
            "IK Main",
            "IK Secondary",
            "Tweaker Main",
            "Tweaker Secondary"
        ],

        "Center": [
            "FK Main",
            "FK Secondary",
            "IK Main",
            "IK Secondary",
            "Tweaker Main",
            "Tweaker Secondary"
        ],

        "Right": [
            "FK Main",
            "FK Secondary",
            "IK Main",
            "IK Secondary",
            "Tweaker Main",
            "Tweaker Secondary"
        ]
    }

    ATTRIBUTES = {

        # ==================================================
        # GENERAL
        # ==================================================

        "rigName": {"dt": "string"},
        "majorVersion": {"at": "long", "min": 1},
        "minorVersion": {"at": "long", "min": 0},
        "author": {"dt": "string"},
        "creationDate": {"dt": "string"},
        "lastBuildDate": {"dt": "string"},

        # ==================================================
        # BUILD SETTINGS
        # ==================================================

        "rigScale": {"at": "double", "min": 0.001},
        "controlSize": {"at": "double", "min": 0.001},
        "mirrorAxis": {
            "at": "enum",
            "enumName": "X:Y:Z"
        },
        "controlShape": {
            "at": "enum",
            "enumName": "Circle:Square:Cube:Sphere"
        },
        "useRGBColors": {"at": "bool"},

        # ==================================================
        # CUSTOM STEPS
        # ==================================================

        "preBuildScripts": {"dt": "string"},
        "postBuildScripts": {"dt": "string"},

        # ==================================================
        # MODULES
        # ==================================================

        "rigData": {
            "at": "message",
            "multi": True
        },
    }


    def __init__(self, rig_name):

        self.rig_name = rig_name
        self.data_node = None

        # Copie du dictionnaire pour éviter de modifier
        # ATTRIBUTES directement sur la classe.
        self.attributes = self.ATTRIBUTES.copy()

        self.add_color_attributes()


    # ==================================================
    # COLORS
    # ==================================================

    @staticmethod
    def color_name(side, name):

        return (
            f"{side.lower()}"
            f"{name.replace(' ','')}"
            f"Color"
        )


    def add_color_attributes(self):

        for side, colors in self.COLORS.items():

            for color in colors:

                attribute = self.color_name(
                    side,
                    color
                )

                self.attributes[attribute] = {
                    "at": "float3",
                    "usedAsColor": True
                }

                self.attributes[f"{attribute}R"] = {
                    "at": "float",
                    "parent": attribute
                }

                self.attributes[f"{attribute}G"] = {
                    "at": "float",
                    "parent": attribute
                }

                self.attributes[f"{attribute}B"] = {
                    "at": "float",
                    "parent": attribute
                }


    # ==================================================
    # BUILD
    # ==================================================

    def create(self):

        self.data_node = cmds.createNode(
            "network",
            name=f"{self.rig_name}_RIG_DATA"
        )

        self.add_attributes()

        cmds.setAttr(
            f"{self.data_node}.rigName",
            self.rig_name,
            type="string"
        )

        log.success(f"Rig data created : {self.data_node}")

        return self.data_node


    # ==================================================
    # ATTRIBUTES
    # ==================================================

    def add_attributes(self):

        for attr, infos in self.attributes.items():

            kwargs = {
                "ln": attr
            }

            kwargs.update(infos)

            cmds.addAttr(
                self.data_node,
                **kwargs
            )

        self.apply_default_colors()


    def apply_default_colors(self):

        for side, colors in self.COLORS.items():

            for color in colors:

                default = DEFAULT_COLORS.get(side, {}).get(color)

                if not default:
                    continue

                attribute = self.color_name(side, color)
                plug = f"{self.data_node}.{attribute}"

                if cmds.objExists(plug):
                    cmds.setAttr(plug, *default, type="float3")


    def set_attribute(self, attribute, value):

        plug = f"{self.data_node}.{attribute}"

        if not cmds.objExists(plug):

            log.warning(
                f"Attribute '{attribute}' does not exist "
                f"on '{self.data_node}'."
            )

            return

        attr_type = cmds.getAttr(
            plug,
            type=True
        )

        if attr_type == "string":

            cmds.setAttr(
                plug,
                value,
                type="string"
            )

        elif attr_type == "float3":

            if not isinstance(value, (list, tuple)) or len(value) != 3:

                log.warning(
                    f"'{attribute}' requires 3 values."
                )

                return

            cmds.setAttr(
                plug,
                value[0],
                value[1],
                value[2],
                type="float3"
            )

        else:

            cmds.setAttr(
                plug,
                value
            )

        if attribute == "rigName":
            self.rig_name = value

        self.data_node = cmds.rename(self.data_node, f"{self.rig_name}_RIG_DATA")


    def get_attribute(self, attribute):

        return cmds.getAttr(
            f"{self.data_node}.{attribute}"
        )


    # ==================================================
    # COLORS
    # ==================================================

    def set_color(self, side, color, rgb):

        attribute = self.color_name(
            side,
            color
        )

        self.set_attribute(
            attribute,
            rgb
        )


    def get_color(self, side, color):

        attribute = self.color_name(
            side,
            color
        )

        return self.get_attribute(attribute)


    # ==================================================
    # MODULES
    # ==================================================

    def add_module(self, module_data):

        index = cmds.getAttr(
            f"{self.data_node}.modules",
            size=True
        )

        cmds.connectAttr(
            f"{module_data}.message",
            f"{self.data_node}.modules[{index}]",
            force=True
        )


    def get_modules(self):

        return cmds.listConnections(
            f"{self.data_node}.modules",
            source=True,
            destination=False
        ) or []


    # ==================================================
    # UTILS
    # ==================================================

    @staticmethod
    def find():

        for network in cmds.ls(type="network"):

            if cmds.attributeQuery(
                "modules",
                node=network,
                exists=True
            ):
                return network

        return None


    def delete(self):

        if (
            self.data_node
            and cmds.objExists(self.data_node)
        ):
            cmds.delete(self.data_node)