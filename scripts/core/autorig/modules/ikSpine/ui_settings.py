from importlib import reload

from ..base import ui_settings as base_ui_settings

reload(base_ui_settings)


# ==========================================================
# IKSPINE MODULE - UI SETTINGS WIDGET
# ==========================================================
#
# UI de settings du module 'ikSpine'. Par defaut : UI generee depuis le
# schema (attributes.json de ce dossier, fusionne avec base/). Pour une
# UI custom, surcharger build_ui() / build_attributes() /
# create_attribute_widget() / post_build() ici.
#

class SettingsWidget(base_ui_settings.SettingsWidget):

    pass
