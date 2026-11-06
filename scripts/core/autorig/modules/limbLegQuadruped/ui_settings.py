# ====================================================================================================================
# LEGQUADRUPED - UI SETTINGS
# ====================================================================================================================
#
#   SettingsWidget - settings UI of the 'legQuadruped' module, generated from its attributes.json (merged with
#                    limb/). Override build_ui / build_attributes / create_attribute_widget / post_build
#                    here for a custom UI.
#
# ====================================================================================================================

from importlib import reload

from ..limb import ui_settings as limb_ui_settings

reload(limb_ui_settings)


class SettingsWidget(limb_ui_settings.SettingsWidget):

    pass
