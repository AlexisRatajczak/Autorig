# ====================================================================================================================
# CUSTOM STEPS
# ====================================================================================================================
#
#   get_script_paths(rig_data, attribute)   - script paths stored as JSON on the rig data
#   run_scripts(paths, label)               - exec each script, log failures and keep going
#
# ====================================================================================================================

import json

import maya.cmds as cmds

from ... import log


def get_script_paths(rig_data, attribute):
    """
    Script paths stored as a JSON list in 'rig_data.attribute'
    (preBuildScripts / postBuildScripts), or [] if missing or invalid.
    """

    if not rig_data or not cmds.objExists(rig_data):
        return []

    if not cmds.attributeQuery(attribute, node=rig_data, exists=True):
        return []

    raw = cmds.getAttr(f"{rig_data}.{attribute}") or ""

    if not raw:
        return []

    try:
        paths = json.loads(raw)
    except (TypeError, ValueError):
        return []

    return paths if isinstance(paths, list) else []


def run_scripts(paths, label="custom step"):
    """
    Exec each .py path in order. A failing script is logged and skipped.

    label : used in the log messages (ex: "pre-build step").
    """

    for path in paths:

        try:
            with open(path, "r", encoding="utf-8") as file:
                source = file.read()

            exec(compile(source, path, "exec"), {"__name__": "__main__", "__file__": path})

        except Exception as error:
            log.error(f"Could not run {label} '{path}' : {error}")
            continue

        log.success(f"Ran {label} : {path}")
