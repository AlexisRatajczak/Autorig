# ====================================================================================================================
# SETTINGS UTILITIES
# ====================================================================================================================
#
#   user_path(app_name, env_var)                - path of the user settings file
#   _read(path)                                 - read and parse a JSON file
#   _merge(base, override)                      - recursive merge of 'override' into 'base'
#   defaults(default_path)                      - read the default settings file
#   load(default_path, app_name, env_var)       - defaults merged with the user file
#   save(data, app_name, env_var)               - write 'data' to the user file
#   reset(app_name, env_var, default_path)      - delete the user file, return the defaults
#
# ====================================================================================================================

import copy
import json
import os

# --------------------------------------------------
# PATHS
# --------------------------------------------------

def user_path(app_name, env_var=None):
    """
    Path of the user settings file of 'app_name'.

    app_name : tool folder under the Maya prefs (ex: "modeling_checker").
    env_var  : environment variable forcing a shared path (ex: one file for a whole team).
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
    """Read and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _merge(base, override):
    """Recursively merge 'override' into 'base' (lists are replaced, not merged)."""

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
    """Read and return the default settings file (shipped with the tool)."""
    return _read(default_path)


def load(default_path, app_name, env_var=None):
    """
    Default settings overridden by the user file if it exists (new default
    keys always show up, even when missing from the user file).

    app_name, env_var : see user_path.
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
    """Write 'data' to the user settings file. Returns the written path."""

    path = user_path(app_name, env_var)
    folder = os.path.dirname(path)

    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4)

    return path


def reset(app_name, env_var=None, default_path=None):
    """
    Delete the user settings file and return the defaults
    (None when 'default_path' is not given).
    """

    path = user_path(app_name, env_var)

    if os.path.isfile(path):
        os.remove(path)

    return defaults(default_path) if default_path else None
