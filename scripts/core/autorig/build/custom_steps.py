import json

import maya.cmds as cmds

from ... import log


def get_script_paths(rig_data, attribute):
    """
    Return the list of script paths stored (as JSON) in 'attribute' on
    'rig_data', or [] if the node/attribute/value is missing or invalid.

    rig_data  : rig data node to read from.
    attribute : name of the string attribute holding the JSON list
                (preBuildScripts or postBuildScripts).
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
    Execute each script path in turn (its source read then exec'd) - one
    script failing is logged and skipped, it doesn't stop the others.

    paths : list of .py file paths to run, in order.
    label : used in the log messages (e.g. "pre-build step").
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
