# ====================================================================================================================
# BLENDSHAPE WORKFLOW
# ====================================================================================================================
#
#   Auto Rig Tool blendShape logic, no UI: groups (alias naming convention), inbetweens (index / custom name),
#   sculpt duplicate meshes (create / assign / rename), templates. Generic commands come from
#   utilities/blendshape_utilities ('bsU'), not re-exported.
#
#   QUERY           is_target_mesh
#   INBETWEENS      _weight_to_item_index, _item_index_to_weight, _format_inbetween_value, _inbetween_mesh_basename,
#                   get_inbetween_mesh, select_inbetween, _inbetween_info_plug, get_inbetween_name,
#                   set_inbetween_name, list_inbetweens, add_inbetween, delete_inbetween, set_inbetween_value
#   TARGET RENAME   rename_target
#   TARGET MESH     duplicate_as_target, create_target, create_target_mesh, assign_mesh_to_target
#   OUTLINER GROUPS get_targets_root_name, get_group_transform_name, ensure_group_transform
#   GROUPS          split_target_group, create_target_group, rename_target_group, delete_target_group,
#                   list_target_groups
#   TEMPLATES       list_templates, import_template
#
# ====================================================================================================================

import json
from pathlib import Path

import maya.cmds as cmds

from .. import log
from ..utilities import blendshape_utilities as bsU


# JSON templates folder (groups + shapes), see import_template().
TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "config" / "blendshape_templates"

# Suffix of the target duplicate meshes: lets the MeshPanel skip them (see is_target_mesh).
TARGET_MESH_SUFFIX = "_shape"


# --------------------------------------------------
# QUERY
# --------------------------------------------------

def is_target_mesh(mesh):
    """True if 'mesh' is a target duplicate (name ending with TARGET_MESH_SUFFIX)."""

    short_name = (mesh or "").split("|")[-1]

    return short_name.endswith(TARGET_MESH_SUFFIX)


# --------------------------------------------------
# INBETWEENS
# --------------------------------------------------
#
# Each target always has an entry at 1.0 (itself). Inbetweens are extra sculptable shapes at any other value
# (negative or > 1 too) through blendShape -inBetween. 'inputTargetItem' index = 5000 + value * 1000
# (6000 = 1.0, 5500 = 0.5, 4500 = -0.5): community convention, not officially documented.

_INBETWEEN_INDEX_OFFSET = 5000
_INBETWEEN_INDEX_SCALE = 1000


def _weight_to_item_index(value):
    return int(round(_INBETWEEN_INDEX_OFFSET + value * _INBETWEEN_INDEX_SCALE))


def _item_index_to_weight(index):
    return (index - _INBETWEEN_INDEX_OFFSET) / float(_INBETWEEN_INDEX_SCALE)


def _format_inbetween_value(value):
    """
    Name fragment of an inbetween value, valid in a Maya name (no dot):
    signed integer percent, ex: 0.5 -> '50', 1.5 -> '150', -0.5 -> 'm50'.
    """

    percent = int(round(value * 100))

    return f"m{abs(percent)}" if percent < 0 else str(percent)


def _inbetween_mesh_basename(target_name, value):
    """
    Base name (without TARGET_MESH_SUFFIX) of an inbetween duplicate mesh,
    always from its value, never its custom name. The Shape Editor is the only
    source of truth; the duplicate mesh is only a temporary sculpt support.
    """

    return f"{target_name}_ib{_format_inbetween_value(value)}"


def get_inbetween_mesh(blendshape_node, target_name, value):
    """
    Duplicate mesh of an inbetween (or of the target itself at 1.0), or None
    if it is gone (normal: it can be deleted once its delta is captured).
    """

    if value == 1.0:
        mesh = f"{target_name}{TARGET_MESH_SUFFIX}"
    else:
        mesh = f"{_inbetween_mesh_basename(target_name, value)}{TARGET_MESH_SUFFIX}"

    return mesh if cmds.objExists(mesh) else None


def select_inbetween(blendshape_node, target_name, value):
    """Select the duplicate mesh of an inbetween, if it still exists."""

    mesh = get_inbetween_mesh(blendshape_node, target_name, value)

    if not mesh:
        return False

    cmds.select(mesh, replace=True)

    return True


# Custom inbetween names (ex: 'up' / 'down') use the native Shape Editor attribute:
#   blendShape1.inbetweenInfoGroup[weightIndex].inbetweenInfo[itemIndex].inbetweenTargetName -type "string"
# 'itemIndex' follows the 'inputTargetItem' convention (5000 + value * 1000).

def _inbetween_info_plug(blendshape_node, weight_index, value, attr="inbetweenTargetName"):
    return (
        f"{blendshape_node}.inbetweenInfoGroup[{weight_index}]"
        f".inbetweenInfo[{_weight_to_item_index(value)}].{attr}"
    )


def get_inbetween_name(blendshape_node, target_name, value):
    """Custom name of an inbetween (native Shape Editor attribute), or None."""

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
    """Set (or clear with an empty 'name') the custom name of an inbetween: metadata only."""

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
    """[{'value': float, 'name': str | None}, ...] of a target, sorted by value; 1.0 always included."""

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
    Add an empty inbetween (zero delta) to 'target_name' at 'value' (any value
    but 1.0, reserved for the target), with an optional custom 'name' (ex: 'up').
    No duplicate mesh is left: see create_target_mesh / assign_mesh_to_target
    to give it a shape.
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
    """Delete an inbetween (not the 1.0 target, see delete_target). Not tested live."""

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

    # Clear its name too (it would come back with a new inbetween at the same value).
    set_inbetween_name(blendshape_node, target_name, value, None)

    if mesh and cmds.objExists(mesh):
        cmds.delete(mesh)

    log.success(f"Inbetween {value} deleted from '{target_name}'.")

    return True


def set_inbetween_value(base_mesh, blendshape_node, target_name, old_value, new_value):
    """
    Move an inbetween to 'new_value': capture its current shape at 'old_value',
    delete the old entry, recreate it (custom name kept). Not tested live.
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

    # Capture the current inbetween shape (mesh duplicated at its weight), then restore the weight.
    cmds.setAttr(weight_plug, old_value)
    capture = duplicate_as_target(base_mesh, _inbetween_mesh_basename(target_name, new_value))
    cmds.setAttr(weight_plug, previous_weight)

    if not capture:
        return False

    # Delete the old entry (and its duplicate mesh, if any).
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
    Rename a target alias and its duplicate meshes (its own + its inbetweens')
    if they still exist. Inbetween names are indexed by weight index, nothing
    to migrate.
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

    # Inbetween values BEFORE renaming the alias (to find their meshes by the old name).
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
    Duplicate 'base_mesh' as '{target_name}{TARGET_MESH_SUFFIX}' (skipped by the
    MeshPanel, see is_target_mesh), under 'organize_under' (created if needed).
    """

    if not base_mesh or not cmds.objExists(base_mesh):
        log.error(f"Cannot create shape : '{base_mesh}' does not exist.")
        return None

    mesh_name = f"{target_name}{TARGET_MESH_SUFFIX}"

    if cmds.objExists(mesh_name):
        log.error(f"Cannot create shape : '{mesh_name}' already exists.")
        return None

    duplicate = cmds.duplicate(base_mesh, name=mesh_name, renameChildren=True)[0]

    # cmds.duplicate keeps the parent: unparent to the world, then parent under 'organize_under'.
    if cmds.listRelatives(duplicate, parent=True):
        duplicate = cmds.parent(duplicate, world=True)[0]

    if organize_under:

        if not cmds.objExists(organize_under):
            cmds.group(empty=True, name=organize_under)

        duplicate = cmds.parent(duplicate, organize_under)[0]

    return duplicate


def create_target(base_mesh, blendshape_node, target_name):
    """
    Add an empty target (zero delta) to 'blendshape_node'. Only the blendShape
    entry is created: the temporary duplicate is deleted. See create_target_mesh
    / assign_mesh_to_target to give it a shape.
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

    # Force the weight alias (it does not always follow the duplicate name).
    if cmds.aliasAttr(f"{blendshape_node}.weight[{weight_index}]", query=True) != target_name:
        cmds.aliasAttr(target_name, f"{blendshape_node}.weight[{weight_index}]")

    cmds.setAttr(f"{blendshape_node}.weight[{weight_index}]", 0)

    log.success(f"Target '{target_name}' added to '{blendshape_node}' (index {weight_index}).")

    return target_name


def create_target_mesh(base_mesh, blendshape_node, target_name, value=1.0, organize_under=None):
    """
    Editable duplicate of the shape stored for 'target_name' at 'value' (equal to
    'base_mesh' if nothing is sculpted yet), named like get_inbetween_mesh.
    Temporarily changes the blendShape weights, then restores them.
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
    Bake the shape of 'mesh' as the delta of 'target_name' at 'value' (1.0
    included); 'mesh' is renamed with the shape naming convention, replacing an
    older mesh of the same name.
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
# Each group (see GROUPS) has a DAG group in the outliner so the sculpt meshes stay sorted by category
# instead of all under '{blendshape_node}_targets_GRP'.

def get_targets_root_name(blendshape_node):
    """Root (catch-all) DAG group of the shapes of 'blendshape_node'."""

    return f"{blendshape_node}_targets_GRP"


def get_group_transform_name(blendshape_node, group_name):
    """DAG group name of a Shape Editor group."""

    return f"{group_name}_GRP"


def ensure_group_transform(blendshape_node, group_name):
    """DAG group of a Shape Editor group (created if needed) under the catch-all group. Returns its name."""

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
# GROUPS (naming convention)
# --------------------------------------------------
#
# The Shape Editor 'targetDirectory' proved unreliable across Maya versions: groups are only a naming convention
# on the target alias, '{group}___{name}' (GROUP_SEPARATOR). Each group still has a DAG group
# (ensure_group_transform) to sort the shape meshes in the outliner.

GROUP_SEPARATOR = "___"


def split_target_group(alias):
    """(group_name, short_name) if 'alias' is '{group}___{name}', else (None, alias)."""

    if GROUP_SEPARATOR in alias:

        group_name, _, short_name = alias.partition(GROUP_SEPARATOR)

        if group_name:
            return group_name, short_name

    return None, alias


def create_target_group(blendshape_node, name):
    """
    "Create" a group: only its DAG group (ensure_group_transform). Membership is
    a naming convention on the alias, no target is moved here.
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
    """Rename a group: the prefix of all its targets + its DAG group."""

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
    """Ungroup every target (prefix removed) and delete its DAG group (shapes go back to the catch-all)."""

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
    """Groups from the '{group}___' alias prefixes: {group_name: [alias, ...]}."""

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
    """Paths of the available JSON templates."""

    if not TEMPLATES_DIR.is_dir():
        return []

    return sorted(TEMPLATES_DIR.glob("*.json"))


def import_template(base_mesh, blendshape_node, template_path):
    """
    Import a JSON template (groups + shapes, see config/blendshape_templates) on
    'blendshape_node': one group (Shape Editor + DAG) per 'groups' entry, each
    shape added as a target (create_target) with its group prefix, under the
    matching DAG group.
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
