import maya.cmds as cmds

from . import registry
from ... import log

from importlib import reload

reload(registry)


# ==========================================================
# UPDATE GUIDES
# ==========================================================
#
# Met à jour les modules déjà présents dans la scène quand leur
# attributes.json a changé :
#
#   - attributs manquants      : créés avec leur valeur par défaut
#                                (Guides.add_attribute, comme à la création) ;
#   - enums modifiés           : enumName mis à jour (index conservé) ;
#   - attributs obsolètes      : signalés, supprimés si remove_obsolete ;
#   - type différent           : signalé seulement (valeur à reprendre à la main).
#
# Usage (dans Maya) :
#
#   from scripts.core.autorig.modules import update_guides
#   update_guides.update_guides()                      # tous les modules
#   update_guides.update_guides(dry_run=True)          # rapport seulement
#   update_guides.update_guides(["C_Limb_00_GUIDE_DATA"], remove_obsolete=True)
#

DATA_NODE_PATTERN = "*_GUIDE_DATA"


def list_data_nodes():
    """Data nodes des modules de la scène."""

    return cmds.ls(DATA_NODE_PATTERN, type="network") or []


def expected_type(infos):
    """Type attendu d'une entrée de ATTRIBUTES ('dt' prioritaire sur 'at')."""

    return infos.get("dt") or infos.get("at")


def update_data_node(data_node, remove_obsolete=False, dry_run=False):

    """
    Met à jour un data node d'après les ATTRIBUTES de la classe Guides de
    son module (registry.load_guide). Retourne le rapport
    {added, enums, obsolete, removed, mismatched}, ou None si le module
    est introuvable.
    """

    instance = registry.load_guide(data_node)

    if not instance:
        log.error(f"update_guides : module introuvable pour '{data_node}'.")
        return None

    definitions = instance.ATTRIBUTES

    report = {"added": [], "enums": [], "obsolete": [], "removed": [], "mismatched": []}

    # Attributs vecteurs : leurs enfants X / Y / Z ne sont pas dans ATTRIBUTES.
    children = {
        f"{attr}{axis}"
        for attr, infos in definitions.items()
        if infos.get("at") == "double3"
        for axis in "XYZ"
    }

    # Manquants / enums / types.
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

    # Obsolètes : attributs utilisateur qui ne sont plus dans le schéma.
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
    Met à jour les data nodes 'data_nodes' (tous ceux de la scène par
    défaut) et affiche un rapport par module.

    remove_obsolete : supprime les attributs absents du schéma.
    dry_run         : rapport seulement, rien n'est modifié.

    Retourne {data_node: rapport}.
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
    """Affiche le rapport d'un data node (rien s'il est à jour)."""

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
