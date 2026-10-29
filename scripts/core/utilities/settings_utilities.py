# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
#   _read(path)                                 - lit et parse un fichier JSON
#   _merge(base, override)                      - fusion recursive de 'override' dans 'base'
#   user_path(app_name, env_var)                - chemin du fichier de settings utilisateur
#   defaults(default_path)                      - lit le fichier de settings par defaut
#   load(default_path, app_name, env_var)       - defaults fusionnes avec le fichier utilisateur
#   save(data, app_name, env_var)                - ecrit 'data' dans le fichier utilisateur
#   reset(app_name, env_var, default_path)      - supprime le fichier utilisateur, retourne les defaults

# ====================================================================================================================
# ====================================================================================================================

import copy
import json
import os

# --------------------------------------------------
# PATHS
# --------------------------------------------------

def user_path(app_name, env_var=None):
    """
    Chemin du fichier de settings utilisateur pour 'app_name'.

    app_name : nom du dossier de l'outil sous les prefs Maya (ex. "modeling_checker").
    env_var  : variable d'environnement permettant de forcer un chemin partage
               (ex. pour pointer toute une equipe vers le meme fichier).
    """

    if env_var:
        env = os.environ.get(env_var)
        if env:
            return env

    try:
        from maya import cmds
        base = cmds.internalVar(userAppDir=True)
    except Exception:
        base = os.path.expanduser("~")

    return os.path.join(base, app_name, "settings.json")

# --------------------------------------------------
# READ / MERGE
# --------------------------------------------------

def _read(path):
    """Lit et parse un fichier JSON."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _merge(base, override):
    """
    Fusionne recursivement 'override' dans 'base' (les listes sont remplacees,
    pas fusionnees).
    """

    result = copy.deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)

    return result

# --------------------------------------------------
# DEFAULTS / LOAD
# --------------------------------------------------

def defaults(default_path):
    """Lit et retourne le fichier de settings par defaut (fourni par l'outil)."""
    return _read(default_path)


def load(default_path, app_name, env_var=None):
    """
    Settings par defaut, surcharges par le fichier utilisateur s'il existe (les
    nouvelles cles de defaults apparaissent toujours, meme si absentes du
    fichier utilisateur).

    default_path : chemin du fichier de settings par defaut.
    app_name      : voir user_path.
    env_var       : voir user_path.
    """

    data = defaults(default_path)
    path = user_path(app_name, env_var)

    if os.path.isfile(path):
        try:
            data = _merge(data, _read(path))
        except (ValueError, OSError) as exc:
            print("{}: cannot read {} ({}), using defaults".format(app_name, path, exc))

    return data

# --------------------------------------------------
# SAVE / RESET
# --------------------------------------------------

def save(data, app_name, env_var=None):
    """Ecrit 'data' dans le fichier de settings utilisateur. Retourne le chemin ecrit."""

    path = user_path(app_name, env_var)
    folder = os.path.dirname(path)

    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4)

    return path


def reset(app_name, env_var=None, default_path=None):
    """
    Supprime le fichier de settings utilisateur et retourne les defaults.

    default_path : chemin du fichier de settings par defaut, ou None pour ne
                    pas les recharger (retourne None dans ce cas).
    """

    path = user_path(app_name, env_var)

    if os.path.isfile(path):
        os.remove(path)

    return defaults(default_path) if default_path else None
