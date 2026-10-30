# ====================================================================================================================
# RIBBON BUILDER
# ====================================================================================================================
#
#   NURBS ribbon driven by an existing joint chain (ribbonJointGuides) and N ctrl levels (levelCount), with
#   bindJointCount skin joints on follicles.
#
#   JOINTS (the surface must exist to place / orient the joints)
#       main nurb    ribbonSurface if given, else built through the chain: degree 3 + pinch only
#       level nurbs  one surface per level built on the chain for its ctrls (degree), an isoparm on each driver,
#                    no pinch (a copy of the main nurb when ribbonSurface is given)
#       follicles    one per sk joint on the top surface
#       root    {side}_{name}_{idx}_jnt                 joints[0] (MainBuild)
#       sk      {side}_{name}_{idx}_{i}_sk_jnt          self.sk_joints, under the root, on their follicle
#       driver  {side}_{name}_{idx}_{i}_lvl{L}_drv_jnt  self.level_drivers[L-1], under the root, at the origin
#       sk joints are oriented on the surface: aimVector along the ribbon (ribbonDirection U / V, 'Auto' = the
#       longest), upVector on its normal.
#   CONTROLS
#       root    {side}_{name}_{idx}_ctrl                controls[0], drives the root joint
#       level   {side}_{name}_{idx}_{i}_lvl{L}_ctrl     under the root ctrl, drives its driver
#   SETUP / CONNECT
#       follicle -> sk joint (ParentCnstrMtx). Stack: main nurb (skinned to the chain) -> level 1 -> ... -> level N.
#       Level ctrls ride follicles on the surface below (attach_level_controls).
#       Skins: main nurb -> chain joints, level nurb -> its drivers. Follicle scale (root scale + stretch).
#
#   Builder
#       DATA            has_ribbon_input, get_setup_group, get_nurbs_group, parent_to_nurbs, parent_to_setup
#       JOINTS          build_joints, create_root_joint, create_ribbon_joint, create_sk_joints, create_level_joints
#       SURFACE         create_nurb, create_chain_surface, create_level_nurbs, insert_driver_isoparms,
#                       create_follicules
#       CONTROLS        create_controls, create_level_controls, create_ribbon_control
#       SETUP           create_setup, attach_level_controls, get_level_follicle, get_level_attach_target,
#                       constrain_sk_joints, connect_setup
#       FOLLICLE SCALE  use_follicle_scale, use_follicle_stretch, get_root_scale, connect_follicle_scale
#       SKIN            skin_main_nurbs, skin_level_nurbs
#
# ====================================================================================================================

import maya.cmds as cmds
import maya.api.OpenMaya as om

from ..base.builder import Builder as BaseBuilder
from ....utilities import joint_utilities
from ....utilities import ctrl_utilities
from ....utilities import cnstrMtx_utilities
from ....utilities import ribbon_utilities
from ....utilities import skinCluster_utilities

from importlib import reload

reload(joint_utilities)
reload(ctrl_utilities)
reload(cnstrMtx_utilities)
reload(ribbon_utilities)
reload(skinCluster_utilities)


class Builder(BaseBuilder):

    CONTROL_SHAPE = "square"
    CONTROL_COLOR_TYPE = "Tweaker Main"

    MAX_LEVELS = 5

    # Degree of the built main nurb (levels follow ribbonDegree).
    MAIN_DEGREE = 3

    SK_JOINT_SUFFIX = "sk_jnt"
    DRIVER_SUFFIX = "drv_jnt"

    def __init__(self, module, data, main):

        super().__init__(module, data, main)

        root_guide = self.get_root_guide()

        self.base_name, self.side, self.module_index = (
            self.main.get_guide_naming(root_guide) if root_guide else (data.get("baseName", "Ribbon"), "C", 0)
        )

        self.root_joint = None
        self.sk_joints = []
        self.level_drivers = []

        self.root_control = None
        self.level_controls = []

        self.ribbon = None
        self.nurb = None
        self.level_nurbs = []
        self.follicle_group = None
        self.follicles = []

        # Level ctrls riding the surface below (attach_level_controls).
        self.level_follicle_group = None
        self.level_follicles = {}
        self.level_attach_targets = []

        # Module setup group in MISC (get_setup_group) and its nurbs group (get_nurbs_group).
        self.setup_group = None
        self.nurbs_group = None

        # Setup nodes created in build_joints, handed to MainBuild by create_setup.
        self.setup_nodes = []

        # "U" / "V": ribbon length direction on the main nurb (ribbonDirection, resolved in create_nurb).
        self.ribbon_direction = None

    # ======================================================
    # DATA
    # ======================================================
    
    def has_ribbon_input(self, tolerance=1e-4):

        """True if the ribbon can be built: a given surface, or 2+ chain guides with distinct first / last (else a warning)."""

        if self.get_message("ribbonSurface"):
            return True

        positions = self.get_chain_positions()

        if len(positions) < 2:
            return False

        first, last = positions[0], positions[-1]

        if sum((last[i] - first[i]) ** 2 for i in range(3)) ** 0.5 < tolerance:
            cmds.warning(
                f"Ribbon '{self.prefix}' : premier et dernier guide de la chaîne au même endroit "
                f"({', '.join(self.get_chain_guides())}) - placer les guides."
            )
            return False

        return True

    def get_setup_group(self):

        """Module setup group ({prefix}_setup_grp) in MISC, holding every ribbon setup node. Created on first call."""

        group = getattr(self, "setup_group", None)

        if group and cmds.objExists(group):
            return group

        group = cmds.group(empty=True, name=f"{self.prefix}_setup_grp")

        misc = self.get_misc_group()

        if misc:
            group = cmds.parent(group, misc)[0]

        self.setup_group = group

        return group

    def get_nurbs_group(self):

        """Ribbon nurbs group ({prefix}_nurbs_grp) in the setup group (main + level nurbs). Created on first call."""

        group = getattr(self, "nurbs_group", None)

        if group and cmds.objExists(group):
            return group

        group = cmds.group(empty=True, name=f"{self.prefix}_nurbs_grp")

        self.nurbs_group = self.parent_to_setup(group)

        return self.nurbs_group

    def parent_to_nurbs(self, node):
        """Put 'node' (a ribbon nurb) in the nurbs group."""

        return self.parent_to_setup(node, group=self.get_nurbs_group())

    def parent_to_setup(self, node, group=None):

        """Put 'node' in 'group' (setup group by default) if not already there. Returns its name."""

        group = group or self.get_setup_group()

        current_parent = (cmds.listRelatives(node, parent=True) or [None])[0]

        if current_parent == group:
            return node

        # No 'Turning on inheritTransform' warning (surfaces without inheritance).
        return ribbon_utilities.Ribbon.parent_keep_inherits(node, group)

    # ======================================================
    # JOINTS
    # ======================================================

    def build_joints(self, suffix="jnt"):

        """
        Surfaces (main + levels) and follicles first, then the root joint
        (joints[0]), sk joints on their follicles and level drivers.
        """

        if not self.has_ribbon_input():
            cmds.warning(
                f"Ribbon '{self.prefix}' : ni 'Ribbon Surface' ni au moins 2 'Joint Guides' : module ignoré."
            )
            self.joints = []
            return self.joints

        self.setup_nodes = self.create_nurb()
        self.setup_nodes.extend(self.create_follicules())

        self.root_joint = self.create_root_joint(suffix=suffix)

        self.sk_joints = self.create_sk_joints()
        self.level_drivers = self.create_level_joints()

        self.joints = [self.root_joint] + self.sk_joints + [
            driver for drivers in self.level_drivers for driver in drivers
        ]

        return self.joints

    def create_root_joint(self, suffix="jnt"):
        """Root joint '{prefix}_jnt' matched on the root guide."""

        joint = joint_utilities.Joint(
            {
                "baseName": self.base_name,
                "side": self.side,
                "index": self.module_index,
                "guide": self.get_root_guide()
            },
            suffix=suffix
        )
        joint.create_joint()
        joint.match_transform(self.get_root_guide(), matchPos=True, matchRot=True)
        joint.freeze_transform()

        return joint

    def create_ribbon_joint(self, index, suffix, matrix):

        """Joint '{prefix}_{index:02d}_{suffix}' under the root joint, placed by the world 'matrix', baked."""

        joint = joint_utilities.Joint(
            {
                "baseName": f"{self.base_name}_{self.module_index:02d}",
                "side": self.side,
                "index": index,
                "parent": self.root_joint.name
            },
            suffix=suffix
        )
        joint.create_joint()

        cmds.xform(joint.name, worldSpace=True, matrix=matrix)

        joint.freeze_transform()

        return joint

    def create_sk_joints(self):
        """One sk joint per follicle, on the same surface point."""

        count = len(self.follicles)

        aim_vector = self.get_vector_attribute("aimVector", default=(1.0, 0.0, 0.0))
        up_vector = self.get_vector_attribute("upVector", default=(0.0, 0.0, 1.0))

        return [
            self.create_ribbon_joint(
                i,
                self.SK_JOINT_SUFFIX,
                ribbon_utilities.Ribbon.get_surface_matrix(
                    self.nurb,
                    i / (count - 1) if count > 1 else 0.0,
                    direction=self.ribbon_direction,
                    aim_vector=aim_vector,
                    up_vector=up_vector
                )
            )
            for i in range(count)
        ]

    def create_level_joints(self):

        """Per level, levelNControlCount drivers at the origin: their ctrl brings them onto the surface (attach_level_controls)."""

        levels = []

        identity = list(om.MMatrix())

        for level in range(1, self.level_count + 1):

            count = max(2, self.get_int(f"level{level}ControlCount", 3))

            levels.append([
                self.create_ribbon_joint(i, f"lvl{level}_{self.DRIVER_SUFFIX}", identity)
                for i in range(count)
            ])

        return levels

    # ======================================================
    # SURFACE
    # ======================================================
    # Logic in ribbon_utilities.Ribbon (SURFACE BUILD).

    def create_nurb(self):

        """
        Main nurb: ribbonSurface as is if given, else built through the chain
        (degree 3, ribbonPinch, no isoparm subdivision), U and V in 0..1. Then one
        nurb per level (create_level_nurbs). Returns the created nodes.
        """

        nodes = []

        self.nurb = self.get_message("ribbonSurface")

        built = not self.nurb

        if built:

            self.nurb = self.create_chain_surface(
                f"{self.prefix}_ribbon",
                control_count=2,
                direction=self.data.get("ribbonDirection"),
                degree=self.MAIN_DEGREE,
                subdivide=False,
                pinch_offset=self.get_float("ribbonPinch", 0.0)
            )

            nodes.append(self.nurb)

        else:
            # Given surface: U and V to 0..1 (a built one already is, Ribbon.rebuild_degree).
            ribbon_utilities.Ribbon.normalize_uv_range(self.nurb)

        self.ribbon_direction = ribbon_utilities.Ribbon.resolve_direction(self.nurb, self.data.get("ribbonDirection"))

        # Main nurb (given or built): hidden, in the module nurbs group.
        self.nurb = self.parent_to_nurbs(self.nurb)
        cmds.setAttr(f"{self.nurb}.visibility", 0)

        nodes.append(self.get_setup_group())

        self.level_nurbs = self.create_level_nurbs(built)

        nodes.extend(self.level_nurbs)

        return nodes

    def create_chain_surface(self, name, control_count, direction, degree=None, subdivide=True, pinch_offset=0.0):

        """Surface '{name}_srf' through the chain (ribbonWidth, ribbonUniformIsoparms), in the nurbs group."""

        positions = self.get_chain_positions()
        chain_guides = self.get_chain_guides()

        if not getattr(self, "ribbon", None):
            self.ribbon =ribbon_utilities.Ribbon(self.side, self.base_name, positions, index=self.module_index)

        return self.ribbon.create_surface_from_chain(
            positions,
            width=self.get_float("ribbonWidth", 2.0),
            parent=self.get_nurbs_group(),
            reference=chain_guides[0] if chain_guides else None,
            uniform=bool(self.data.get("ribbonUniformIsoparms", 1)),
            control_count=control_count,
            direction=direction,
            pinch_offset=pinch_offset,
            degree=degree,
            subdivide=subdivide,
            name=name
        )

    def create_level_nurbs(self, from_chain=True):

        """
        One hidden nurb per level '{prefix}_lvl{N}_srf':

            from_chain : built through the chain for ITS ctrls, degree ribbonDegree
                         (Auto = from levelNControlCount), an isoparm on each driver,
                         no pinch, main nurb direction;
            else       : copy of the main nurb (ribbonSurface given).

        Returns the nurbs, level 1 first.
        """

        if not from_chain:
            return ribbon_utilities.Ribbon.create_level_surfaces(
                self.nurb, self.level_count, self.prefix, parent=self.get_nurbs_group()
            )

        degree = ribbon_utilities.Ribbon.parse_degree(self.data.get("ribbonDegree"))

        level_nurbs = []

        for level in range(1, self.level_count + 1):

            count = max(2, self.get_int(f"level{level}ControlCount", 3))

            nurb = self.create_chain_surface(
                f"{self.prefix}_lvl{level}",
                control_count=count,
                direction=self.ribbon_direction,
                degree=degree,
                subdivide=False,
                pinch_offset=0.0
            )

            # The ctrls of this level ride the surface below.
            base = self.nurb if level == 1 else level_nurbs[-1]

            self.insert_driver_isoparms(nurb, base, count)

            cmds.setAttr(f"{nurb}.visibility", 0)

            level_nurbs.append(self.parent_to_nurbs(nurb))

        return level_nurbs

    def insert_driver_isoparms(self, nurb, base, count):

        """
        An isoparm on 'nurb' at the rest position of each of the 'count' drivers
        (their ctrl rides 'base' at t = i / (count - 1), mid width). Returns the
        inserted isoparms.
        """

        positions = []

        for i in range(count):

            t = i / (count - 1) if count > 1 else 0.0

            u, v = ribbon_utilities.Ribbon.to_surface_parameters(
                base, *ribbon_utilities.Ribbon.get_surface_uv(self.ribbon_direction, t)
            )

            positions.append(cmds.pointOnSurface(base, u=u, v=v, position=True))

        return ribbon_utilities.Ribbon.insert_isoparms_at_points(nurb, self.ribbon_direction, positions)

    def create_follicules(self):

        """
        bindJointCount follicles on the top surface of the stack, spread 0 -> 1
        along the ribbon, under a group in the setup group. Returns the group.
        """

        self.follicle_group, self.follicles = ribbon_utilities.Ribbon.create_follicles_along(
            ribbon_utilities.Ribbon.get_top_surface(self.nurb, self.level_nurbs),
            self.get_int("bindJointCount", 5),
            self.ribbon_direction,
            self.prefix,
            parent=self.get_setup_group()
        )

        return [self.follicle_group]

    # ======================================================
    # CONTROLS
    # ======================================================

    def create_controls(self):

        """
        Root ctrl (controls[0]) driving the root joint, then one ctrl per level
        driver under it, placed on the surface at setup (attach_level_controls).
        """

        if not self.root_joint:
            return []

        self.root_control = self.create_ribbon_control(
            f"{self.prefix}_ctrl",
            self.root_joint.name,
            shape=self.CONTROL_SHAPE,
            size=1.5
        )

        return [self.root_control] + self.create_level_controls(parent=self.root_control)

    def create_level_controls(self, parent=None):

        """
        One ctrl per level driver, matched on it (origin), under 'parent' (else
        CTRL_grp), shape from levelNShape / ShapeTranslate / ShapeScale. Fills
        self.level_controls (one list per level), returns all ctrls flattened.
        Also used by modules adding a ribbon (ex: limb).
        """

        controls = []

        self.level_controls = []

        for level, drivers in enumerate(self.level_drivers, start=1):

            shape = self.data.get(f"level{level}Shape") or "circle"
            translate = self.get_vector_attribute(f"level{level}ShapeTranslate", default=(0.0, 0.0, 0.0))
            scale = self.get_vector_attribute(f"level{level}ShapeScale", default=(1.0, 1.0, 1.0))

            level_controls = []

            for i, driver in enumerate(drivers):

                control = self.create_ribbon_control(
                    f"{self.prefix}_{i:02d}_lvl{level}_ctrl",
                    driver.name,
                    shape=shape,
                    translate=translate,
                    scale=scale,
                    parent=parent
                )

                level_controls.append(control)

            self.level_controls.append(level_controls)
            controls.extend(level_controls)

        return controls

    def create_ribbon_control(self, name, joint, shape, size=1.0, translate=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), parent=None):

        """
        Ctrl 'name' matched on 'joint', shape offset / scaled, under 'parent' (else
        CTRL_grp), connected to the joint. 'No Ctrl' mode: shape on the joint, which
        is returned.
        """

        if self.no_ctrl():

            shape_joint = self.create_joint_shape(joint, self.base_name, self.side, self.module_index, joint, shape=shape, size=size)

            if tuple(translate) != (0.0, 0.0, 0.0) or tuple(scale) != (1.0, 1.0, 1.0):
                ctrl_utilities.Control(shape_joint, shape=None).transform_shape(translate=translate, scale=scale)

            return shape_joint

        control = ctrl_utilities.Control(name, shape=shape, size=size, color=self.get_control_color())
        control.create()

        if tuple(translate) != (0.0, 0.0, 0.0) or tuple(scale) != (1.0, 1.0, 1.0):
            control.transform_shape(translate=translate, scale=scale)

        cmds.matchTransform(control.name, joint, position=True, rotation=True)

        target_parent = parent if parent and cmds.objExists(parent) else self.main.groups.get("controls")

        control.create_offset(parent=target_parent, use_group=self.offset_group())

        self.connect_control(control.name, joint)

        return control.name

    # ======================================================
    # SETUP
    # ======================================================

    def create_setup(self):

        """
        Constrain each sk joint to its follicle, attach the level ctrls. Done after
        parent_joint_modules so the constraint uses the final parents. Returns the
        setup nodes.
        """

        if not self.root_joint:
            return []

        self.constrain_sk_joints()

        self.setup_nodes.extend(self.attach_level_controls())

        return list(self.setup_nodes)

    # --------------------------------------------------
    # LEVEL CONTROLS ON SURFACE
    # --------------------------------------------------

    def attach_level_controls(self):

        """
        Attach each level's ctrls to the surface below (no cycle: the stack goes
        up only):

            level 1 ctrls -> main nurb
            level N ctrls -> level N-1 nurb

        Per ctrl: a follicle at get_surface_uv(i / (count - 1)), mid width (shared
        when same surface / uv, get_level_follicle); the attach target is
        constrained to it without offset. Returns the follicle group.
        """

        if not self.level_drivers or not self.nurb:
            return []

        self.level_follicle_group = cmds.group(empty=True, name=f"{self.prefix}_ctrl_follicles_grp")
        cmds.setAttr(f"{self.level_follicle_group}.inheritsTransform", 0)

        self.level_follicle_group = self.parent_to_setup(self.level_follicle_group)

        self.level_follicles = {}

        # Node attached to the follicle for each driver (same layout as level_drivers).
        self.level_attach_targets = []

        for level, drivers in enumerate(self.level_drivers, start=1):

            count = len(drivers)
            controls = self.level_controls[level - 1] if level - 1 < len(self.level_controls) else []

            base_nurb = ribbon_utilities.Ribbon.get_level_base_surface(self.nurb, self.level_nurbs, level)

            self.level_attach_targets.append([])

            for i, driver in enumerate(drivers):

                control = controls[i] if i < len(controls) else None

                t = i / (count - 1) if count > 1 else 0.0

                follicle = self.get_level_follicle(base_nurb, *ribbon_utilities.Ribbon.get_surface_uv(self.ribbon_direction, t))

                target = self.get_level_attach_target(control, driver)

                self.level_attach_targets[-1].append(target)

                # No maintain offset: the ctrl (or its offset) takes the follicle position / orientation.
                cnstrMtx_utilities.ParentCnstrMtx(target, follicle, mo=False, dcmpMtx=False)

        return [self.level_follicle_group]

    def get_level_follicle(self, surface, u, v, precision=6):

        """Follicle of 'surface' at (u, v) (0..1), reused for the same rounded parameters, else created."""

        key = (surface, round(u, precision), round(v, precision))

        if key in self.level_follicles:
            return self.level_follicles[key]

        surface_u, surface_v = ribbon_utilities.Ribbon.to_surface_parameters(surface, u, v)

        follicle = ribbon_utilities.create_follicle(
            surface,
            surface_u,
            surface_v,
            f"{self.prefix}_{len(self.level_follicles):02d}_ctrl_fol"
        )

        follicle = cmds.parent(follicle, self.level_follicle_group)[0]

        self.level_follicles[key] = follicle

        return follicle

    def get_level_attach_target(self, control, driver):

        """
        Node attached to the follicle for a level ctrl: the level joint ('No Ctrl'),
        the offset group ('Offset Group'), else the ctrl itself.
        """

        if self.no_ctrl() or not control:
            return driver.name

        offset = self.main.get_offset_group(control)

        if self.offset_group() and offset and cmds.objExists(offset):
            return offset

        return control

    def constrain_sk_joints(self):
        """Follicle -> sk joint (ParentCnstrMtx into the offsetParentMatrix)."""

        return [
            cnstrMtx_utilities.ParentCnstrMtx(joint.name, follicle, mo=False, dcmpMtx=False)
            for joint, follicle in zip(self.sk_joints, self.follicles)
        ]

    def connect_setup(self):

        """Skin the main nurb (chain) and each level nurb (drivers), then the follicle scale."""

        if not self.nurb:
            return

        self.skin_main_nurbs()
        self.skin_level_nurbs()

        # After the skins: the surface is at its deformed rest pose.
        self.connect_follicle_scale()

    # --------------------------------------------------
    # FOLLICLE SCALE
    # --------------------------------------------------

    def use_follicle_scale(self):
        """'Follicle Scale' option: root joint scale (and stretch) on the follicles."""

        return bool(self.data.get("follicleScale", 1))

    def use_follicle_stretch(self):
        """Follicle stretch: 'Ribbon Stretch' (ribbon module), else 'Stretch' (stretchIk, limb)."""

        value = self.data.get("ribbonStretch")

        if value is None:
            value = self.data.get("stretchIk")

        return bool(value)

    def get_root_scale(self):

        """
        World scale (X) plug of the module root joint (ribbon or limb root), read
        by a ScaleCnstrMtx on a hidden '{prefix}_follicleScale_grp'. 1.0 without root.
        """

        root = getattr(self, "root_joint", None)
        root = getattr(root, "name", root)

        if not root or not cmds.objExists(root):
            return 1.0

        group = f"{self.prefix}_follicleScale_grp"

        if not cmds.objExists(group):

            group = self.parent_to_setup(cmds.group(empty=True, name=group))
            cmds.setAttr(f"{group}.visibility", 0)

            cnstrMtx_utilities.ScaleCnstrMtx(group, root, mo=False, dcmpMtx=True)

        return f"{group}.scaleX"

    def connect_follicle_scale(self):

        """
        Scale of every follicle (sk joint ones on the top surface, level ctrl ones
        on the surface below), passed on to what they drive. Level ctrl follicles
        get the root scale only; sk joint follicles get:

            no stretch     : root scale on the 3 axes;
            IK stretch     : (limb, stretchIk) closest IK bone at build: root scale *
                             its stretch factor along the ribbon, root scale * its
                             squash on the other axes, weighted by the IK/FK switch;
            ribbon stretch : (ribbon module, ribbonStretch) root scale * |surface
                             tangent| / (rest length * root scale) along the ribbon,
                             root scale on the other axes.

        Nothing without 'Follicle Scale'. Returns the created nodes.
        """

        if not self.use_follicle_scale():
            return []

        # (follicle, its surface, stretch allowed): stretch for sk joints only, root scale for ctrls.
        top_surface = ribbon_utilities.Ribbon.get_top_surface(self.nurb, self.level_nurbs)

        targets = [(follicle, top_surface, True) for follicle in (getattr(self, "follicles", None) or [])]
        targets += [
            (follicle, surface, False)
            for (surface, _, _), follicle in (getattr(self, "level_follicles", None) or {}).items()
        ]

        if not targets:
            return []

        root_scale = self.get_root_scale()

        # IK stretch (simpleIk.stretch_ik) if any, else the ribbon one.
        ik_segments = getattr(self, "ik_stretch_segments", None) or []
        stretch = self.use_follicle_stretch() and not ik_segments

        tangent_attr = "tangentU" if self.ribbon_direction == "U" else "tangentV"

        def drive(plug_or_value, attr):
            if isinstance(plug_or_value, str):
                cmds.connectAttr(plug_or_value, attr, force=True)
            else:
                cmds.setAttr(attr, plug_or_value)

        nodes = []
        ik_scales = {}

        def ik_scale(index, slot, name):
            # root scale * (bone factor or squash, weighted by the IK/FK switch): one node per bone.
            key = (index, slot)

            if key not in ik_scales:

                plug = ik_segments[index][slot]
                switch = getattr(self, "ik_fk_plug", None)

                if switch and cmds.objExists(switch):
                    bta = cmds.createNode("blendTwoAttr", name=f"{self.prefix}_ik{index:02d}_{name}_bta")
                    cmds.setAttr(f"{bta}.input[0]", 1.0)
                    cmds.connectAttr(plug, f"{bta}.input[1]")
                    cmds.connectAttr(switch, f"{bta}.attributesBlender")
                    plug = f"{bta}.output"
                    nodes.append(bta)

                fm = cmds.createNode("floatMath", name=f"{self.prefix}_ik{index:02d}_{name}Scale_fm")
                cmds.setAttr(f"{fm}.operation", 2)
                drive(root_scale, f"{fm}.floatA")
                cmds.connectAttr(plug, f"{fm}.floatB")
                nodes.append(fm)

                ik_scales[key] = f"{fm}.outFloat"

            return ik_scales[key]

        def closest_segment(position):
            point = om.MVector(position)

            def gap(segment):
                start, end = om.MVector(segment[0]), om.MVector(segment[1])
                bone = end - start
                t = 0.0 if bone.length() < 1e-6 else min(max(((point - start) * bone) / (bone * bone), 0.0), 1.0)
                return (point - (start + bone * t)).length()

            return min(range(len(ik_segments)), key=lambda i: gap(ik_segments[i]))

        for follicle, surface, can_stretch in targets:

            if not cmds.objExists(follicle):
                continue

            surface_shape = (cmds.listRelatives(surface, shapes=True, noIntermediate=True, fullPath=True) or [surface])[0]

            follicle_shape = (cmds.listRelatives(follicle, shapes=True, type="follicle") or [None])[0]

            scales = [root_scale, root_scale, root_scale]

            if not can_stretch:
                pass

            elif ik_segments and follicle_shape:

                index = closest_segment(cmds.xform(follicle, query=True, worldSpace=True, translation=True))

                # Follicle axis closest to the bone (ribbon length).
                start, end = ik_segments[index][:2]
                bone = (om.MVector(end) - om.MVector(start)).normal()
                matrix = cmds.getAttr(f"{follicle}.worldMatrix[0]")

                axis = max(
                    range(3),
                    key=lambda k: abs(om.MVector(matrix[k * 4:k * 4 + 3]).normal() * bone)
                )

                squash = ik_scale(index, 3, "squash")
                scales = [ik_scale(index, 2, "stretch") if k == axis else squash for k in range(3)]

            elif stretch and follicle_shape:

                # Surface tangent (not normalized) at the follicle.
                info = cmds.createNode("pointOnSurfaceInfo", name=f"{follicle}_scale_posi")
                cmds.connectAttr(f"{surface_shape}.worldSpace[0]", f"{info}.inputSurface")
                cmds.connectAttr(f"{follicle_shape}.parameterU", f"{info}.parameterU")
                cmds.connectAttr(f"{follicle_shape}.parameterV", f"{info}.parameterV")

                length = cmds.createNode("distanceBetween", name=f"{follicle}_tangent_db")
                cmds.connectAttr(f"{info}.{tangent_attr}", f"{length}.point2")

                rest_length = cmds.getAttr(f"{length}.distance") or 1.0

                # Rest length at rig scale.
                rest = cmds.createNode("floatMath", name=f"{follicle}_restLength_fm")
                cmds.setAttr(f"{rest}.operation", 2)
                drive(root_scale, f"{rest}.floatA")
                cmds.setAttr(f"{rest}.floatB", rest_length)

                factor = cmds.createNode("floatMath", name=f"{follicle}_stretch_fm")
                cmds.setAttr(f"{factor}.operation", 3)
                cmds.connectAttr(f"{length}.distance", f"{factor}.floatA")
                cmds.connectAttr(f"{rest}.outFloat", f"{factor}.floatB")

                stretch_scale = cmds.createNode("floatMath", name=f"{follicle}_stretchScale_fm")
                cmds.setAttr(f"{stretch_scale}.operation", 2)
                drive(root_scale, f"{stretch_scale}.floatA")
                cmds.connectAttr(f"{factor}.outFloat", f"{stretch_scale}.floatB")

                # Follicle axis closest to the tangent (ribbon length).
                tangent = om.MVector(cmds.getAttr(f"{info}.{tangent_attr}")[0]).normal()
                matrix = cmds.getAttr(f"{follicle}.worldMatrix[0]")

                axis = max(
                    range(3),
                    key=lambda k: abs(om.MVector(matrix[k * 4:k * 4 + 3]).normal() * tangent)
                )

                scales[axis] = f"{stretch_scale}.outFloat"

                nodes += [info, length, rest, factor, stretch_scale]

            for value, axis in zip(scales, "XYZ"):
                drive(value, f"{follicle}.scale{axis}")

        return nodes

    def skin_main_nurbs(self):

        """
        Skin the main nurb (stack base) to the ribbonJointGuides joints: the only
        chain input of the stack. Static without joints. Maya Bind Skin options,
        max influences 2.
        """

        joints = self.get_chain_joints()

        if not joints:
            cmds.warning(f"Ribbon '{self.prefix}' : aucun joint de chaîne, main nurb non skinnée.")
            return None

        return skinCluster_utilities.bind_skin(joints, self.nurb, name=f"{self.prefix}_ribbon_skin", max_influences=2)

    def skin_level_nurbs(self):

        """
        Skin each level nurb to its drivers (closest driver per CV). The level nurb
        already gets the lower deformation through its Orig; its drivers follow it
        through their ctrls.
        """

        skins = []

        targets_by_level = getattr(self, "level_attach_targets", [])

        for level, (nurb, drivers) in enumerate(zip(self.level_nurbs, self.level_drivers), start=1):

            # Each CV 100% on its closest driver.
            skin = skinCluster_utilities.skin_to_closest_joints(
                [driver.name for driver in drivers],
                nurb,
                f"{self.prefix}_lvl{level}_skin"
            )

            skins.append(skin)

        return skins
