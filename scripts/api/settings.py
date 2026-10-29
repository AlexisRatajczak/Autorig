# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# API - SETTINGS
# ==========================================================
#
# Façade sur settings_utilities (alias directs, noms explicites).
#
#   from api import settings
#
#   data = settings.load_settings(DEFAULT_PATH, "modeling_checker")
#   settings.save_settings(data, "modeling_checker")
#
# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
#   settings_user_path(app_name, env_var)              - chemin du fichier de settings utilisateur
#   default_settings(default_path)                     - lit le fichier de settings par défaut
#   load_settings(default_path, app_name, env_var)     - défauts fusionnés avec le fichier utilisateur
#   save_settings(data, app_name, env_var)             - écrit 'data' dans le fichier utilisateur
#   reset_settings(app_name, env_var, default_path)    - supprime le fichier utilisateur, retourne les défauts

# ====================================================================================================================
# ====================================================================================================================

from core.utilities import settings_utilities

from importlib import reload

reload(settings_utilities)


__all__ = [
    "settings_user_path", "default_settings", "load_settings", "save_settings", "reset_settings",
]


settings_user_path = settings_utilities.user_path
default_settings = settings_utilities.defaults
load_settings = settings_utilities.load
save_settings = settings_utilities.save
reset_settings = settings_utilities.reset
