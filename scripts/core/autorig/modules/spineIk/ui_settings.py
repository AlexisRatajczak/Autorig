# ====================================================================================================================
# SPINE - UI SETTINGS
# ====================================================================================================================
#
#   SettingsWidget - settings UI of the 'spine' module, generated from its attributes.json (merged with
#                    base/). Override build_ui / build_attributes / create_attribute_widget / post_build
#                    here for a custom UI.
#
# ====================================================================================================================

from importlib import reload

from ..simpleBase import ui_settings as base_ui_settings

reload(base_ui_settings)


class SettingsWidget(base_ui_settings.SettingsWidget):

    pass
