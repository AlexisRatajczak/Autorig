# ====================================================================================================================
# UPDATE GUIDES
# ====================================================================================================================
#
#   Updates the modules already in the scene when their attributes.json changed:
#       missing attributes   - created with their default value (Guides.add_attribute)
#       changed enums        - enumName updated (index kept)
#       obsolete attributes  - reported, deleted with remove_obsolete
#       different type       - reported only (fix by hand)
#
#   Usage (in Maya):
#       from scripts.core.autorig.modules import update_guides
#       update_guides.update_guides()                      # every module
#       update_guides.update_guides(dry_run=True)          # report only
#       update_guides.update_guides(["C_Limb_00_GUIDE_DATA"], remove_obsolete=True)
#
#   list_data_nodes()                                       - module data nodes of the scene
#   expected_type(infos)                                    - expected type of an ATTRIBUTES entry
#   update_data_node(data_node, remove_obsolete, dry_run)   - update one data node
#   update_guides(data_nodes, remove_obsolete, dry_run)     - update several data nodes, print the reports
#   print_report(data_node, report, dry_run)                - log one report
#
# ====================================================================================================================

import maya.cmds as cmds

from . import registry
from ... import log

from importlib import reload

reload(registry)


DATA_NODE_PATTERN = "*_GUIDE_DATA"


def list_data_nodes():
    """Module data nodes of the scene."""

    return cmds.ls(DATA_NODE_PATTERN, type="network") or []


def expected_type(infos):
    """Expected type of an ATTRIBUTES entry ('dt' first, then 'at')."""

    return infos.get("dt") or infos.get("at")


def update_data_node(data_node, remove_obsolete=False, dry_run=False):

    """
    Update a data node from the ATTRIBUTES of its Guides class.
    Returns {added, enums, obsolete, removed, mismatched}, or None if the module is unknown.
    """

    instance = registry.load_guide(data_node)

    if not instance:
        log.error(f"update_guides : module introuvable pour '{data_node}'.")
        return None

    definitions = instance.ATTRIBUTES

    report = {"added": [], "enums": [], "obsolete": [], "removed": [], "mismatched": []}

    # Vector attributes: their X / Y / Z children are not in ATTRIBUTES.
    children = {
        f"{attr}{axis}"
        for attr, infos in definitions.items()
        if infos.get("at") == "double3"
        for axis in "XYZ"
    }

    # Missing / enums / types.
    for attr, infos in definitions.items():

        if not cmds.attributeQuery(attr, node=data_node, exists=True):

            report["added"].append(attr)

            if not dry_run:
                instance.add_attribute(attr, infos)

            continue

        wanted = expected_type(infos)

        if wanted and infos.get("at") not in ("message", "double3"):

            current = cmds.attributeQuery(attr, node=data_node, attributeType=True)

            if current == "typed":
                current = cmds.getAttr(f"{data_node}.{attr}", type=True)

            if current != wanted:
                report["mismatched"].append((attr, current, wanted))
                continue

        if infos.get("at") == "enum" and infos.get("enumName"):

            current_enum = ":".join(cmds.attributeQuery(attr, node=data_node, listEnum=True) or [])

            if current_enum != infos["enumName"]:

                report["enums"].append((attr, current_enum, infos["enumName"]))

                if not dry_run:
                    locked = cmds.getAttr(f"{data_node}.{attr}", lock=True)
                    cmds.setAttr(f"{data_node}.{attr}", lock=False)
                    cmds.addAttr(f"{data_node}.{attr}", edit=True, enumName=infos["enumName"])
                    cmds.setAttr(f"{data_node}.{attr}", lock=locked)

    # Obsolete: user attributes no longer in the schema.
    for attr in cmds.listAttr(data_node, userDefined=True) or []:

        if attr in definitions or attr in children:
            continue

        report["obsolete"].append(attr)

        if remove_obsolete and not dry_run:
            cmds.setAttr(f"{data_node}.{attr}", lock=False)
            cmds.deleteAttr(data_node, attribute=attr)
            report["removed"].append(attr)

    if not dry_run:
        instance.lock_attributes()

    return report


def update_guides(data_nodes=None, remove_obsolete=False, dry_run=False):

    """
    Update 'data_nodes' (every one in the scene by default) and log a report per module.

    remove_obsolete : delete the attributes missing from the schema.
    dry_run         : report only, nothing is changed.

    Returns {data_node: report}.
    """

    reports = {}

    for data_node in data_nodes or list_data_nodes():

        if not cmds.objExists(data_node):
            log.error(f"update_guides : '{data_node}' n'existe pas.")
            continue

        report = update_data_node(data_node, remove_obsolete=remove_obsolete, dry_run=dry_run)

        if report is None:
            continue

        reports[data_node] = report

        print_report(data_node, report, dry_run)

    changed = sum(1 for report in reports.values() if report["added"] or report["enums"] or report["removed"])

    prefix = "[dry run] " if dry_run else ""
    log.success(f"{prefix}update_guides : {len(reports)} module(s) vérifié(s), {changed} mis à jour.")

    return reports


def print_report(data_node, report, dry_run=False):
    """Log the report of a data node (nothing if it is up to date)."""

    verb = "à ajouter" if dry_run else "ajoutés"

    lines = []

    if report["added"]:
        lines.append(f"  attributs {verb} : {', '.join(report['added'])}")

    for attr, current, wanted in report["enums"]:
        lines.append(f"  enum '{attr}' : '{current}' -> '{wanted}'")

    if report["removed"]:
        lines.append(f"  attributs supprimés : {', '.join(report['removed'])}")
    elif report["obsolete"]:
        lines.append(f"  attributs obsolètes (gardés) : {', '.join(report['obsolete'])}")

    for attr, current, wanted in report["mismatched"]:
        lines.append(f"  type différent '{attr}' : {current} (attendu {wanted}) - à corriger à la main")

    if lines:
        log.info(f"{data_node} :\n" + "\n".join(lines))
