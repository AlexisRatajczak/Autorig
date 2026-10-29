import json
from pathlib import Path

import maya.cmds as cmds

from .. import log
from ..utilities import blendshape_utilities as bsU


# ==========================================================
# BLENDSHAPE WORKFLOW
# ==========================================================
#
# Logique blendShape specifique a l'Auto Rig Tool : groupes (convention de
# nommage sur l'alias), inbetweens (index/nom personnalise), mesh duplicata
# de sculpt (creation/assignation/renommage), templates. Pas de dependance
# a l'UI - uniquement de la logique de scene.
#
# Les commandes generiques (core/utilities/blendshape_utilities.py) sont
# appelees directement via 'bsU.' ci-dessous - pas de reexport : l'UI
# importe ce module pour la logique workflow, et core/utilities/
# blendshape_utilities directement pour le generique (voir blendshape_tab.py).

# Dossier des templates JSON (groupes + shapes), voir import_template().
TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "config" / "blendshape_templates"

# Suffixe des meshes duplicata (targets) : permet au MeshPanel de les
# exclure de sa liste des meshes "reels" de la scene (voir is_target_mesh).
TARGET_MESH_SUFFIX = "_shape"


# --------------------------------------------------
# QUERY
# --------------------------------------------------

def is_target_mesh(mesh):
    """True si 'mesh' est un duplicata de target (nom se terminant par TARGET_MESH_SUFFIX)."""

    short_name = (mesh or "").split("|")[-1]

    return short_name.endswith(TARGET_MESH_SUFFIX)


# --------------------------------------------------
# INBETWEENS
# --------------------------------------------------
#
# Chaque target a toujours une entree a 1.0 (la target elle-meme). On peut
# lui ajouter d'autres shapes sculptables a n'importe quelle autre valeur
# (negative ou > 1 incluses - Maya n'impose pas de limite 0-1, seule 1.0
# est reservee a la target principale) : les inbetweens, via le flag
# documente -inBetween de blendShape. Pour les lister, on s'appuie sur la
# convention Maya bien connue de la communaute (mais non documentee
# officiellement) des index de 'inputTargetItem' : index = 5000 +
# valeur*1000 (donc 6000 = 1.0, 5500 = 0.5, 4500 = -0.5, ...) - a verifier
# sur cette version de Maya.

_INBETWEEN_INDEX_OFFSET = 5000
_INBETWEEN_INDEX_SCALE = 1000


def _weight_to_item_index(value):
    return int(round(_INBETWEEN_INDEX_OFFSET + value * _INBETWEEN_INDEX_SCALE))


def _item_index_to_weight(index):
    return (index - _INBETWEEN_INDEX_OFFSET) / float(_INBETWEEN_INDEX_SCALE)


def _format_inbetween_value(value):
    """
    Nom (fragment) derive d'une valeur d'inbetween, valide pour un nom Maya
    (jamais de point - '0.5' casserait cmds.duplicate) : pourcentage entier
    signe, ex. 0.5 -> '50', 1.5 -> '150', -0.5 -> 'm50'.
    """

    percent = int(round(value * 100))

    return f"m{abs(percent)}" if percent < 0 else str(percent)


def _inbetween_mesh_basename(target_name, value):
    """
    Nom de base (sans TARGET_MESH_SUFFIX) du mesh duplicata d'un inbetween -
    toujours derive de sa valeur, jamais de son nom personnalise. Le Shape
    Editor (aliasAttr/inputTargetItem) est la seule source de verite pour
    l'identite d'une target/inbetween ; le mesh duplicata n'est qu'un
    support de sculpt transitoire (souvent supprime une fois le delta
    capture) - rien ne doit en dependre pour fonctionner.
    """

    return f"{target_name}_ib{_format_inbetween_value(value)}"


def get_inbetween_mesh(blendshape_node, target_name, value):
    """
    Retourne le nom du mesh duplicata d'un inbetween (ou de la target
    elle-meme si value == 1.0), ou None s'il n'existe plus dans la scene
    (cas normal - un mesh sculpte est generalement supprimable une fois
    son delta capture par le blendShape).
    """

    if value == 1.0:
        mesh = f"{target_name}{TARGET_MESH_SUFFIX}"
    else:
        mesh = f"{_inbetween_mesh_basename(target_name, value)}{TARGET_MESH_SUFFIX}"

    return mesh if cmds.objExists(mesh) else None


def select_inbetween(blendshape_node, target_name, value):
    """Selectionne le mesh duplicata d'un inbetween, s'il existe encore dans la scene."""

    mesh = get_inbetween_mesh(blendshape_node, target_name, value)

    if not mesh:
        return False

    cmds.select(mesh, replace=True)

    return True


# Les noms personnalises d'inbetween (ex. 'up'/'down') utilisent
# l'attribut natif du Shape Editor - confirme fonctionnel (capture des
# commandes echo, comme blendShapeCreateGroupForSelected en son temps) :
#   blendShape1.inbetweenInfoGroup[weightIndex]
#              .inbetweenInfo[itemIndex].inbetweenTargetName -type "string"
# 'itemIndex' suit la meme convention que 'inputTargetItem' (voir plus
# haut : 5000 + valeur*1000), desormais confirmee correcte puisque c'est
# exactement l'index utilise par cet attribut natif.

def _inbetween_info_plug(blendshape_node, weight_index, value, attr="inbetweenTargetName"):
    return (
        f"{blendshape_node}.inbetweenInfoGroup[{weight_index}]"
        f".inbetweenInfo[{_weight_to_item_index(value)}].{attr}"
    )


def get_inbetween_name(blendshape_node, target_name, value):
    """Retourne le nom personnalise d'un inbetween (attribut natif du Shape Editor), ou None."""

    if value == 1.0:
        return None

    weight_index = bsU.get_weight_index(blendshape_node, target_name)

    if weight_index is None:
        return None

    plug = _inbetween_info_plug(blendshape_node, weight_index, value)

    if not cmds.objExists(plug):
        return None

    return cmds.getAttr(plug) or None


def set_inbetween_name(blendshape_node, target_name, value, name):
    """
    Definit (ou efface, si 'name' est vide/None) le nom personnalise d'un
    inbetween, via l'attribut natif 'inbetweenTargetName' du Shape Editor -
    purement une metadonnee, independante du mesh duplicata.
    """

    if value == 1.0:
        log.warning("Cannot rename the main target this way - rename the target itself.")
        return False

    weight_index = bsU.get_weight_index(blendshape_node, target_name)

    if weight_index is None:
        log.error(f"Target '{target_name}' not found on '{blendshape_node}'.")
        return False

    plug = _inbetween_info_plug(blendshape_node, weight_index, value)

    try:
        cmds.setAttr(plug, name or "", type="string")
    except Exception as error:
        log.error(f"Could not set inbetween name : {error}")
        return False

    return True


def list_inbetweens(blendshape_node, target_name):
    """
    Retourne [{'value': float, 'name': str|None}, ...] pour une target,
    triees par valeur ; 1.0 (la target elle-meme, sans nom) est toujours
    incluse.
    """

    values = {1.0}

    weight_index = bsU.get_weight_index(blendshape_node, target_name)

    if weight_index is not None:

        plug = f"{blendshape_node}.inputTarget[0].inputTargetGroup[{weight_index}].inputTargetItem"

        if cmds.objExists(plug):
            indices = cmds.getAttr(plug, multiIndices=True) or []
            values.update(round(_item_index_to_weight(i), 3) for i in indices)

    return [
        {
            "value": value,
            "name": get_inbetween_name(blendshape_node, target_name, value) if value != 1.0 else None,
        }
        for value in sorted(values)
    ]


def add_inbetween(base_mesh, blendshape_node, target_name, value, name=None):
    """
    Ajoute un inbetween (vide, delta a zero) a 'target_name' a 'value'
    (n'importe quelle valeur, negative ou > 1 incluses - seule 1.0 est
    reservee a la target elle-meme), avec un 'name' personnalise optionnel
    (ex. 'up'). Aucun mesh duplicata n'est laisse dans la scene - un
    duplicata temporaire de 'base_mesh' sert juste a connecter/creer
    l'entree puis est supprime ; voir create_target_mesh /
    assign_mesh_to_target pour lui donner une forme.
    """

    if value == 1.0:
        log.error("Value 1.0 is reserved for the target itself.")
        return None

    weight_index = bsU.get_weight_index(blendshape_node, target_name)

    if weight_index is None:
        log.error(f"Target '{target_name}' not found on '{blendshape_node}'.")
        return None

    if not base_mesh or not cmds.objExists(base_mesh):
        log.error(f"Cannot add inbetween : '{base_mesh}' does not exist.")
        return None

    temp = cmds.duplicate(base_mesh, name=f"{target_name}_TEMP", renameChildren=True)[0]

    if cmds.listRelatives(temp, parent=True):
        temp = cmds.parent(temp, world=True)[0]

    try:
        cmds.blendShape(
            blendshape_node,
            edit=True,
            inBetween=True,
            topologyCheck=True,
            target=(base_mesh, weight_index, temp, value),
        )
    except Exception as error:
        log.error(f"Could not add inbetween at {value} on '{target_name}' : {error}")
        return None
    finally:
        if cmds.objExists(temp):
            cmds.delete(temp)

    if name:
        set_inbetween_name(blendshape_node, target_name, value, name)

    log.success(f"Inbetween {value} added to '{target_name}' on '{blendshape_node}'.")

    return target_name


def delete_inbetween(blendshape_node, target_name, value):
    """
    Supprime un inbetween (pas la target principale a 1.0 - supprime la
    target elle-meme pour ca, voir delete_target). Non verifie en live.
    """

    if value == 1.0:
        log.error("Cannot delete the main target's value (1.0) this way - delete the target itself.")
        return False

    weight_index = bsU.get_weight_index(blendshape_node, target_name)

    if weight_index is None:
        log.warning(f"Target '{target_name}' not found on '{blendshape_node}'.")
        return False

    mesh = get_inbetween_mesh(blendshape_node, target_name, value)

    plug = f"{blendshape_node}.inputTarget[0].inputTargetGroup[{weight_index}].inputTargetItem[{_weight_to_item_index(value)}]"

    if not cmds.objExists(plug):
        log.warning(f"Inbetween {value} not found on '{target_name}'.")
        return False

    try:
        cmds.removeMultiInstance(plug, b=True)
    except Exception as error:
        log.error(f"Could not delete inbetween {value} : {error}")
        return False

    # Efface aussi son nom (sinon il resterait orphelin sur 'inbetweenInfo'
    # et pourrait resurgir si un inbetween est recree a la meme valeur).
    set_inbetween_name(blendshape_node, target_name, value, None)

    if mesh and cmds.objExists(mesh):
        cmds.delete(mesh)

    log.success(f"Inbetween {value} deleted from '{target_name}'.")

    return True


def set_inbetween_value(base_mesh, blendshape_node, target_name, old_value, new_value):
    """
    Change la valeur d'un inbetween existant : capture sa forme actuelle
    (duplique le mesh depuis la valeur de poids 'old_value'), supprime
    l'ancienne entree, la recree a 'new_value' (en conservant son nom
    personnalise s'il en avait un). Non verifie en live.
    """

    if old_value == 1.0:
        log.error("Cannot move the main target (value 1.0).")
        return False

    if new_value == 1.0:
        log.error("Value 1.0 is reserved for the target itself.")
        return False

    weight_index = bsU.get_weight_index(blendshape_node, target_name)

    if weight_index is None:
        log.error(f"Target '{target_name}' not found on '{blendshape_node}'.")
        return False

    existing_name = get_inbetween_name(blendshape_node, target_name, old_value)

    weight_plug = f"{blendshape_node}.weight[{weight_index}]"
    previous_weight = cmds.getAttr(weight_plug)

    # Capture la forme actuelle de l'inbetween en dupliquant le mesh
    # deforme a son poids, puis remet le poids d'origine (nom base sur la
    # nouvelle valeur uniquement - voir _inbetween_mesh_basename).
    cmds.setAttr(weight_plug, old_value)
    capture = duplicate_as_target(base_mesh, _inbetween_mesh_basename(target_name, new_value))
    cmds.setAttr(weight_plug, previous_weight)

    if not capture:
        return False

    # Supprime l'ancienne entree (et son mesh duplicata, s'il existe encore).
    if not delete_inbetween(blendshape_node, target_name, old_value):
        return False

    try:
        cmds.blendShape(
            blendshape_node,
            edit=True,
            inBetween=True,
            topologyCheck=True,
            target=(base_mesh, weight_index, capture, new_value),
        )
    except Exception as error:
        log.error(f"Could not add inbetween at {new_value} : {error}")
        return False

    if existing_name:
        set_inbetween_name(blendshape_node, target_name, new_value, existing_name)

    log.success(f"Inbetween moved : {old_value} -> {new_value} on '{target_name}'.")

    return True


# --------------------------------------------------
# TARGET RENAME
# --------------------------------------------------

def rename_target(blendshape_node, old_name, new_name):
    """
    Renomme une target (son alias) d'un blendShape, et ses meshes duplicata
    (le sien + ceux de ses inbetweens) s'ils existent encore dans la scene -
    pure convenance d'organisation, la target et ses inbetweens
    fonctionnent independamment du mesh (voir duplicate_as_target /
    TARGET_MESH_SUFFIX). Leurs noms d'inbetween (attribut natif du Shape
    Editor) n'ont rien a migrer : ils sont indexes par le weight index
    (inchange par un renommage), pas par le nom.
    """

    weight_index = bsU.get_weight_index(blendshape_node, old_name)

    if weight_index is None:
        log.error(f"Target '{old_name}' not found on '{blendshape_node}'.")
        return False

    if old_name == new_name:
        return True

    if bsU.get_weight_index(blendshape_node, new_name) is not None:
        log.warning(
            f"Cannot rename '{old_name}' to '{new_name}' : a target with that name already exists on "
            f"'{blendshape_node}' - cancelled."
        )
        return False

    # Recupere les valeurs d'inbetween AVANT de renommer l'alias (on en a
    # besoin pour retrouver leurs meshes sous leur ancien nom).
    inbetween_values = [
        entry["value"] for entry in list_inbetweens(blendshape_node, old_name) if entry["value"] != 1.0
    ]

    cmds.aliasAttr(new_name, f"{blendshape_node}.weight[{weight_index}]")

    old_mesh = f"{old_name}{TARGET_MESH_SUFFIX}"
    new_mesh = f"{new_name}{TARGET_MESH_SUFFIX}"

    if cmds.objExists(old_mesh) and not cmds.objExists(new_mesh):
        cmds.rename(old_mesh, new_mesh)

    for value in inbetween_values:

        old_ib_mesh = f"{_inbetween_mesh_basename(old_name, value)}{TARGET_MESH_SUFFIX}"
        new_ib_mesh = f"{_inbetween_mesh_basename(new_name, value)}{TARGET_MESH_SUFFIX}"

        if cmds.objExists(old_ib_mesh) and not cmds.objExists(new_ib_mesh):
            cmds.rename(old_ib_mesh, new_ib_mesh)

    log.success(f"Target renamed : {old_name} -> {new_name}")

    return True


# --------------------------------------------------
# TARGET MESH (sculpt duplicate)
# --------------------------------------------------

def duplicate_as_target(base_mesh, target_name, organize_under=None):
    """
    Duplique 'base_mesh' en une nouvelle shape nommee
    '{target_name}{TARGET_MESH_SUFFIX}' (le suffixe permet au MeshPanel de
    l'exclure de sa liste de meshes - voir is_target_mesh). Si
    'organize_under' est fourni, le duplicata est parente sous ce groupe
    (cree s'il n'existe pas encore) pour garder l'outliner range.
    """

    if not base_mesh or not cmds.objExists(base_mesh):
        log.error(f"Cannot create shape : '{base_mesh}' does not exist.")
        return None

    mesh_name = f"{target_name}{TARGET_MESH_SUFFIX}"

    if cmds.objExists(mesh_name):
        log.error(f"Cannot create shape : '{mesh_name}' already exists.")
        return None

    duplicate = cmds.duplicate(base_mesh, name=mesh_name, renameChildren=True)[0]

    # cmds.duplicate garde le parent d'origine : on detache au monde avant
    # de re-parenter proprement sous 'organize_under'.
    if cmds.listRelatives(duplicate, parent=True):
        duplicate = cmds.parent(duplicate, world=True)[0]

    if organize_under:

        if not cmds.objExists(organize_under):
            cmds.group(empty=True, name=organize_under)

        duplicate = cmds.parent(duplicate, organize_under)[0]

    return duplicate


def create_target(base_mesh, blendshape_node, target_name):
    """
    Ajoute une nouvelle target (vide, delta a zero) a 'blendshape_node' - le
    Shape Editor (l'entree blendShape elle-meme) est la seule chose creee ;
    aucun mesh duplicata n'est laisse dans la scene (voir le principe :
    le mesh n'est qu'un support de sculpt optionnel). Utilise un duplicata
    temporaire, juste le temps de connecter/reset la target, aussitot
    supprime - voir create_target_mesh pour en materialiser un a la demande,
    ou assign_mesh_to_target pour lui affecter directement une forme.
    """

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.error(f"Cannot create target : '{blendshape_node}' does not exist.")
        return None

    if not base_mesh or not cmds.objExists(base_mesh):
        log.error(f"Cannot create target : '{base_mesh}' does not exist.")
        return None

    weight_index = bsU.get_next_weight_index(blendshape_node)

    temp = cmds.duplicate(base_mesh, name=f"{target_name}_TEMP", renameChildren=True)[0]

    if cmds.listRelatives(temp, parent=True):
        temp = cmds.parent(temp, world=True)[0]

    try:

        cmds.blendShape(
            blendshape_node,
            edit=True,
            topologyCheck=True,
            tangentSpace=True,
            target=(base_mesh, weight_index, temp, 1.0),
            weight=(weight_index, 1),
        )

        cmds.blendShape(blendshape_node, edit=True, resetTargetDelta=(0, weight_index))

    except Exception as error:
        log.error(f"Could not add '{target_name}' as a target of '{blendshape_node}' : {error}")
        return None
    finally:
        if cmds.objExists(temp):
            cmds.delete(temp)

    # L'alias du weight ne reprend pas toujours le nom du duplicata : on le
    # force pour rester coherent avec bsU.list_targets()/build_target_map().
    if cmds.aliasAttr(f"{blendshape_node}.weight[{weight_index}]", query=True) != target_name:
        cmds.aliasAttr(target_name, f"{blendshape_node}.weight[{weight_index}]")

    cmds.setAttr(f"{blendshape_node}.weight[{weight_index}]", 0)

    log.success(f"Target '{target_name}' added to '{blendshape_node}' (index {weight_index}).")

    return target_name


def create_target_mesh(base_mesh, blendshape_node, target_name, value=1.0, organize_under=None):
    """
    Materialise dans la scene un duplicata editable representant la forme
    actuellement stockee pour 'target_name' a 'value' (identique a
    'base_mesh' si rien n'a encore ete sculpte/assigne) - nomme selon la
    convention utilisee par get_inbetween_mesh/is_target_mesh. Isole
    temporairement le poids de 'blendshape_node' pour lire la forme
    deformee de 'base_mesh', puis restaure tous les poids.
    """

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.error(f"Cannot create mesh : '{blendshape_node}' does not exist.")
        return None

    if not base_mesh or not cmds.objExists(base_mesh):
        log.error(f"Cannot create mesh : '{base_mesh}' does not exist.")
        return None

    weight_index = bsU.get_weight_index(blendshape_node, target_name)

    if weight_index is None:
        log.error(f"Target '{target_name}' not found on '{blendshape_node}'.")
        return None

    mesh_basename = target_name if value == 1.0 else _inbetween_mesh_basename(target_name, value)
    mesh_name = f"{mesh_basename}{TARGET_MESH_SUFFIX}"

    if cmds.objExists(mesh_name):
        log.warning(f"Mesh '{mesh_name}' already exists - select it instead of recreating it.")
        return None

    existing_indices = cmds.getAttr(f"{blendshape_node}.weight", multiIndices=True) or []
    original_weights = {index: cmds.getAttr(f"{blendshape_node}.weight[{index}]") for index in existing_indices}

    try:

        for index in existing_indices:
            cmds.setAttr(f"{blendshape_node}.weight[{index}]", 0)

        cmds.setAttr(f"{blendshape_node}.weight[{weight_index}]", value)

        duplicate = duplicate_as_target(base_mesh, mesh_basename, organize_under=organize_under)

    finally:

        for index, weight in original_weights.items():
            cmds.setAttr(f"{blendshape_node}.weight[{index}]", weight)

    if not duplicate:
        return None

    suffix = "" if value == 1.0 else f" @ {value}"
    log.success(f"Mesh '{duplicate}' created for '{target_name}'{suffix}.")

    return duplicate


def assign_mesh_to_target(base_mesh, blendshape_node, target_name, value, mesh):
    """
    Bake la forme de 'mesh' comme delta de 'target_name' a 'value'
    (n'importe quelle valeur existante, y compris 1.0 - la target
    elle-meme) - 'mesh' est renomme selon la convention de nommage des
    shapes (get_inbetween_mesh/is_target_mesh) pour rester coherent, en
    remplacant l'ancien mesh du meme nom s'il en existait deja un.
    """

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.error(f"Cannot assign mesh : '{blendshape_node}' does not exist.")
        return False

    if not mesh or not cmds.objExists(mesh):
        log.error("Cannot assign mesh : select a mesh first.")
        return False

    if mesh == base_mesh:
        log.error("Cannot assign the base mesh itself as a target shape.")
        return False

    weight_index = bsU.get_weight_index(blendshape_node, target_name)

    if weight_index is None:
        log.error(f"Target '{target_name}' not found on '{blendshape_node}'.")
        return False

    mesh_basename = target_name if value == 1.0 else _inbetween_mesh_basename(target_name, value)
    mesh_name = f"{mesh_basename}{TARGET_MESH_SUFFIX}"

    if mesh_name != mesh:

        if cmds.objExists(mesh_name):
            cmds.delete(mesh_name)

        mesh = cmds.rename(mesh, mesh_name)

    try:

        if value == 1.0:
            cmds.blendShape(
                blendshape_node,
                edit=True,
                topologyCheck=True,
                tangentSpace=True,
                target=(base_mesh, weight_index, mesh, 1.0),
                weight=(weight_index, 1),
            )
        else:
            cmds.blendShape(
                blendshape_node,
                edit=True,
                inBetween=True,
                topologyCheck=True,
                target=(base_mesh, weight_index, mesh, value),
            )

    except Exception as error:
        log.error(f"Could not assign '{mesh}' to '{target_name}' : {error}")
        return False

    suffix = "" if value == 1.0 else f" @ {value}"
    log.success(f"Mesh '{mesh}' assigned to '{target_name}'{suffix}.")

    return True


# --------------------------------------------------
# OUTLINER GROUPS
# --------------------------------------------------
#
# Chaque groupe (voir GROUPS plus bas) a un groupe transform (DAG) associe
# dans l'outliner, pour que les meshes de shape en cours de sculpt restent
# ranges par categorie plutot que tous en vrac sous
# '{blendshape_node}_targets_GRP'.

def get_targets_root_name(blendshape_node):
    """Nom du groupe DAG racine (catch-all) des shapes de 'blendshape_node'."""

    return f"{blendshape_node}_targets_GRP"


def get_group_transform_name(blendshape_node, group_name):
    """Nom du groupe DAG associe a un groupe du Shape Editor."""

    return f"{group_name}_GRP"


def ensure_group_transform(blendshape_node, group_name):
    """
    Cree (si besoin) le groupe DAG associe a un groupe du Shape Editor,
    nesté sous le groupe catch-all de 'blendshape_node'. Retourne son nom.
    """

    root = get_targets_root_name(blendshape_node)

    if not cmds.objExists(root):
        cmds.group(empty=True, name=root)

    transform = get_group_transform_name(blendshape_node, group_name)

    if not cmds.objExists(transform):
        cmds.group(empty=True, name=transform, parent=root)
    else:

        parents = cmds.listRelatives(transform, parent=True) or []

        if parents != [root]:

            try:
                cmds.parent(transform, root)
            except Exception:
                pass

    return transform


# --------------------------------------------------
# GROUPS (convention de nommage)
# --------------------------------------------------
#
# Le mecanisme interne du Shape Editor ('targetDirectory') s'est avere peu
# fiable (noms d'attributs qui different selon la version de Maya). Les
# groupes sont donc purement une convention de nommage sur l'alias de la
# target : '{group}___{nom}' (GROUP_SEPARATOR). Aucun etat cache, aucune
# lecture/ecriture d'attribut interne - juste cmds.aliasAttr/cmds.rename,
# solides et documentes. Le groupe garde quand meme un groupe DAG associe
# (ensure_group_transform) pour ranger les meshes de shape dans l'outliner.

GROUP_SEPARATOR = "___"


def split_target_group(alias):
    """
    Si 'alias' suit la convention '{group}___{nom}', retourne
    (group_name, short_name). Sinon retourne (None, alias).
    """

    if GROUP_SEPARATOR in alias:

        group_name, _, short_name = alias.partition(GROUP_SEPARATOR)

        if group_name:
            return group_name, short_name

    return None, alias


def create_target_group(blendshape_node, name):
    """
    "Cree" un groupe : juste son groupe DAG (ensure_group_transform), pour
    ranger les futures shapes dans l'outliner. L'appartenance au groupe
    cote blendShape est purement une convention de nom sur l'alias -
    aucune target existante n'est deplacee ici.
    """

    if not blendshape_node or not cmds.objExists(blendshape_node):
        log.error(f"Cannot create group : '{blendshape_node}' does not exist.")
        return None

    if not name:
        return None

    ensure_group_transform(blendshape_node, name)

    log.success(f"Group '{name}' ready on '{blendshape_node}'.")

    return name


def rename_target_group(blendshape_node, old_name, new_name):
    """Renomme un groupe : le prefixe de toutes ses targets + son groupe DAG."""

    prefix = f"{old_name}{GROUP_SEPARATOR}"
    renamed = 0

    for target in bsU.list_targets(blendshape_node):

        if target.startswith(prefix):

            new_alias = f"{new_name}{GROUP_SEPARATOR}{target[len(prefix):]}"

            if rename_target(blendshape_node, target, new_alias):
                renamed += 1

    old_transform = get_group_transform_name(blendshape_node, old_name)

    if cmds.objExists(old_transform):
        cmds.rename(old_transform, get_group_transform_name(blendshape_node, new_name))
    else:
        ensure_group_transform(blendshape_node, new_name)

    log.success(f"Group renamed : {old_name} -> {new_name} ({renamed} target(s)).")

    return True


def delete_target_group(blendshape_node, group_name):
    """
    Degroupe toutes les targets du groupe (retire le prefixe de leur alias)
    et supprime son groupe DAG (les shapes qu'il contenait remontent sous
    le groupe catch-all).
    """

    prefix = f"{group_name}{GROUP_SEPARATOR}"

    for target in bsU.list_targets(blendshape_node):

        if target.startswith(prefix):
            rename_target(blendshape_node, target, target[len(prefix):])

    transform = get_group_transform_name(blendshape_node, group_name)
    root = get_targets_root_name(blendshape_node)

    if cmds.objExists(transform):

        children = cmds.listRelatives(transform, children=True, fullPath=True) or []

        if children and cmds.objExists(root):
            cmds.parent(children, root)

        cmds.delete(transform)

    log.success(f"Group '{group_name}' deleted from '{blendshape_node}'.")

    return True


def list_target_groups(blendshape_node):
    """
    Deduit les groupes a partir du prefixe '{group}___' des alias de target
    (voir GROUP_SEPARATOR). Retourne {group_name: [alias, ...]}.
    """

    groups = {}

    for target in bsU.list_targets(blendshape_node):

        group_name, _ = split_target_group(target)

        if group_name:
            groups.setdefault(group_name, []).append(target)

    return groups


# --------------------------------------------------
# TEMPLATES
# --------------------------------------------------

def list_templates():
    """Retourne les chemins (Path) des templates JSON disponibles."""

    if not TEMPLATES_DIR.is_dir():
        return []

    return sorted(TEMPLATES_DIR.glob("*.json"))


def import_template(base_mesh, blendshape_node, template_path):
    """
    Importe un template JSON (groupes + shapes, voir config/blendshape_templates)
    sur 'blendshape_node' : cree un groupe (Shape Editor + DAG) par entree
    'groups', et pour chaque shape declaree, l'ajoute comme target (voir
    create_target), son alias deja prefixe par le groupe (voir GROUP_SEPARATOR)
    et organisee sous le groupe DAG correspondant.
    """

    template_path = Path(template_path)

    if not template_path.is_file():
        log.error(f"Template not found : '{template_path}'.")
        return []

    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
    except Exception as error:
        log.error(f"Could not read template '{template_path.name}' : {error}")
        return []

    created = []

    for group_data in data.get("groups", []):

        group_name = group_data.get("name")

        if not group_name:
            continue

        create_target_group(blendshape_node, group_name)

        for shape in group_data.get("shapes", []):

            shape_short_name = shape.get("name") if isinstance(shape, dict) else shape

            if not shape_short_name:
                continue

            target_name = f"{group_name}{GROUP_SEPARATOR}{shape_short_name}"

            if bsU.get_weight_index(blendshape_node, target_name) is not None:
                continue

            if create_target(base_mesh, blendshape_node, target_name):
                created.append(target_name)

    log.success(
        f"Template '{data.get('name', template_path.stem)}' imported : "
        f"{len(created)} shape(s) created."
    )

    return created
