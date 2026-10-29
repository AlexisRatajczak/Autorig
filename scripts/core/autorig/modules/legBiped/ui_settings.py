from importlib import reload

from ..limb import ui_settings as limb_ui_settings

reload(limb_ui_settings)


# ==========================================================
# LEGBIPED MODULE - UI SETTINGS WIDGET
# ==========================================================
#
# UI de settings du module 'legBiped'. Par defaut : UI de limb, generee
# depuis le schema (attributes.json de ce dossier, fusionne avec limb/).
# Pour une UI custom, surcharger build_ui() / build_attributes() /
# create_attribute_widget() / post_build() ici.
#

class SettingsWidget(limb_ui_settings.SettingsWidget):

    pass
