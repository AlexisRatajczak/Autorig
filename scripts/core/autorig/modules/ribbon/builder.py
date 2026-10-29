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


# ==========================================================
# RIBBON BUILDER
# ==========================================================
#
# Ruban NURBS piloté par une chaîne de joints existante (ribbonJointGuides)
# et par N niveaux de ctrls (levelCount), avec bindJointCount joints de
# skin accrochés à la surface par des follicules.
#
# BUILD JOINTS (la surface doit exister pour placer / orienter les joints)
#   main nurb   : ribbonSurface si fournie, sinon construite à travers la
#                 chaîne (ribbon_utilities.Ribbon.create_surface_from_joints).
#   level nurbs : une surface par niveau, construite sur la chaîne selon
#                 ses ctrls (degré), un isoparm sur chacun de ses drivers,
#                 sans pincement - copie de la main nurb si elle est
#                 fournie (ribbonSurface).
#   main nurb construite : degré 3 et pincement seulement (isoparms des
#                 guides, pas de subdivision).
#   follicules  : un par sk joint sur la main nurb.
#   root    {side}_{name}_{idx}_jnt                -> joints[0] (vu par MainBuild)
#   sk      {side}_{name}_{idx}_{i}_sk_jnt         -> self.sk_joints, sous le root,
#                                                     sur son follicule
#   driver  {side}_{name}_{idx}_{i}_lvl{L}_drv_jnt -> self.level_drivers[L-1], sous le root,
#                                                     créé au centre du monde
#   sk joints posés sur la surface et orientés selon son repère :
#   aimVector le long de la surface (tangente de la direction du ruban,
#   U ou V : attribut ribbonDirection, 'Auto' = la plus longue des deux),
#   upVector sur sa normale (attributs Orientation du module).
#
# CONTROLS
#   root    {side}_{name}_{idx}_ctrl               -> controls[0], pilote le root joint
#   level   {side}_{name}_{idx}_{i}_lvl{L}_ctrl    -> sous le root ctrl, créé au
#                                                     centre du monde sur son driver,
#                                                     qu'il pilote
#
# SETUP / CONNECT
#   follicule -> sk joint : ParentCnstrMtx.
#   pile : main nurb (skinnée à la chaîne) -> niveau 1 -> ... -> niveau N ;
#          chaque surface alimente l'Orig de la suivante (connect_nurbs),
#          les sk joints sont sur la dernière.
#   ctrls de niveau (attach_level_controls) : accrochés par follicules à
#   la surface du niveau du dessous (niveau 1 -> main nurb) ; le ctrl (ou
#   son offset group, ou son joint en 'No Ctrl') y est posé, orienté, et
#   contraint (ParentCnstrMtx).
#   skin : main nurb -> joints de la chaîne ; level nurb -> ses drivers,
#          bindPreMatrix = inverse de l'offset du ctrl (fix_double_transform).
#

class Builder(BaseBuilder):

    CONTROL_SHAPE = "square"
    CONTROL_COLOR_TYPE = "Tweaker Main"

    MAX_LEVELS = 5

    # Degré de la main nurb construite (les niveaux suivent ribbonDegree).
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

        # Ctrls de niveau accrochés à la surface du niveau du dessous
        # (attach_level_controls).
        self.level_follicle_group = None
        self.level_follicles = {}
        self.level_attach_targets = []

        # Groupe de setup du module dans MISC (get_setup_group), et groupe
        # des nurbs dedans (get_nurbs_group).
        self.setup_group = None
        self.nurbs_group = None

        # Nodes de setup créés pendant build_joints, rendus à MainBuild
        # par create_setup.
        self.setup_nodes = []

        # "U" / "V" : direction de la longueur du ruban sur la main nurb
        # (ribbonDirection, 'Auto' = la plus longue), résolue dans create_nurb.
        self.ribbon_direction = None

    # ======================================================
    # DATA
    # ======================================================
    
    def has_ribbon_input(self, tolerance=1e-4):

        """
        True si le ruban peut être construit : surface fournie, ou chaîne
        d'au moins 2 guides dont le premier et le dernier sont distincts
        (sinon : warning, guides à placer).
        """

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

        """
        Groupe de setup du module ({prefix}_setup_grp), rangé dans MISC :
        reçoit tous les nodes de setup du ruban (nurbs, groupes de
        follicules). Créé au premier appel (et ajouté aux nodes de setup
        rendus à MainBuild).
        """

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

        """
        Groupe des nurbs du ruban ({prefix}_nurbs_grp), rangé dans le
        groupe de setup du module : main nurb et nurbs des niveaux. Créé
        au premier appel.
        """

        group = getattr(self, "nurbs_group", None)

        if group and cmds.objExists(group):
            return group

        group = cmds.group(empty=True, name=f"{self.prefix}_nurbs_grp")

        self.nurbs_group = self.parent_to_setup(group)

        return self.nurbs_group

    def parent_to_nurbs(self, node):
        """Range 'node' (une nurb du ruban) dans le groupe des nurbs (get_nurbs_group)."""

        return self.parent_to_setup(node, group=self.get_nurbs_group())

    def parent_to_setup(self, node, group=None):

        """
        Range 'node' dans 'group' (par défaut le groupe de setup du module,
        get_setup_group), s'il n'y est pas déjà (cmds.parent saute sinon
        l'objet et retourne None). Retourne le nom du node après parentage.
        """

        group = group or self.get_setup_group()

        current_parent = (cmds.listRelatives(node, parent=True) or [None])[0]

        if current_parent == group:
            return node

        # Sans warning 'Turning on inheritTransform' (surfaces sans héritage).
        return ribbon_utilities.Ribbon.parent_keep_inherits(node, group)

    # ======================================================
    # JOINTS
    # ======================================================

    def build_joints(self, suffix="jnt"):

        """
        Surface (main + levels) et follicules d'abord, puis root joint
        (joints[0], parenté par MainBuild), sk joints sur leurs
        follicules et drivers de chaque niveau, posés sur la surface et
        orientés selon elle.
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
        """Root joint '{prefix}_jnt', matché sur le root guide."""

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

        """
        Joint '{prefix}_{index:02d}_{suffix}' sous le root joint, placé et
        orienté par 'matrix' (monde), transform baké
        (Joint.freeze_transform).
        """

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
        """Un sk joint par follicule, sur le même point de la surface."""

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

        """
        Pour chaque niveau, levelNControlCount drivers créés au centre du
        monde : ils sont amenés sur la surface par leur ctrl, lui-même
        accroché à un follicule (voir attach_level_controls).
        """

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
    # Logique dans ribbon_utilities.Ribbon (section SURFACE BUILD).

    def create_nurb(self):

        """
        Main nurb : ribbonSurface si elle est fournie (utilisée telle
        quelle), sinon construite à travers la chaîne
        (Ribbon.create_surface_from_chain) en degré 3, pincée (ribbonPinch),
        sans subdivision des isoparms. U et V ramenés en 0..1.

        Puis une nurb par niveau (create_level_nurbs). Retourne les nodes
        créés.
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
            # Surface fournie : U et V en 0..1 (la surface construite l'est
            # déjà dans Ribbon.rebuild_degree, avant son pincement).
            ribbon_utilities.Ribbon.normalize_uv_range(self.nurb)

        self.ribbon_direction = ribbon_utilities.Ribbon.resolve_direction(self.nurb, self.data.get("ribbonDirection"))

        # Main nurb (fournie ou créée) : cachée, rangée dans le groupe des
        # nurbs du setup du module.
        self.nurb = self.parent_to_nurbs(self.nurb)
        cmds.setAttr(f"{self.nurb}.visibility", 0)

        nodes.append(self.get_setup_group())

        self.level_nurbs = self.create_level_nurbs(built)

        nodes.extend(self.level_nurbs)

        return nodes

    def create_chain_surface(self, name, control_count, direction, degree=None, subdivide=True, pinch_offset=0.0):

        """
        Surface '{name}_srf' construite à travers la chaîne
        (Ribbon.create_surface_from_chain, largeur ribbonWidth, isoparms
        ribbonUniformIsoparms), rangée dans le groupe des nurbs.
        """

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
        Une nurb par niveau '{prefix}_lvl{N}_srf', cachée, dans le groupe
        des nurbs :

            from_chain : construite à travers la chaîne pour SES ctrls -
                         degré ribbonDegree (Auto = selon levelNControlCount),
                         un isoparm sur chacun de ses drivers
                         (insert_driver_isoparms), sans pincement, dans la
                         direction de la main nurb ;
            sinon      : copie de la main nurb (ribbonSurface fournie).

        Retourne les nurbs, du niveau 1 au dernier.
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

            # Surface d'accroche des ctrls de ce niveau : celle du dessous.
            base = self.nurb if level == 1 else level_nurbs[-1]

            self.insert_driver_isoparms(nurb, base, count)

            cmds.setAttr(f"{nurb}.visibility", 0)

            level_nurbs.append(self.parent_to_nurbs(nurb))

        return level_nurbs

    def insert_driver_isoparms(self, nurb, base, count):

        """
        Un isoparm sur 'nurb' à la position de repos de chacun des 'count'
        drivers d'un niveau : leur ctrl est accroché à 'base' (surface du
        dessous) à t = i / (count - 1) le long du ruban, au milieu de la
        largeur (comme attach_level_controls). Retourne les isoparms ajoutés.
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
        bindJointCount follicules sur la dernière surface de la pile
        (Ribbon.get_top_surface : elle reçoit la chaîne et tous les
        niveaux), répartis de 0 à 1 dans la direction du ruban, sous un
        groupe rangé dans le setup (Ribbon.create_follicles_along).
        Retourne le groupe.
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
        Root ctrl (controls[0], reparenté au ctrl du module parent par
        MainBuild) qui pilote le root joint, puis un ctrl par driver de
        chaque niveau, matché sur son driver (donc au centre du monde),
        sous le root ctrl. Les ctrls de niveau sont placés sur la surface
        au setup (attach_level_controls).
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
        Un ctrl par driver de chaque niveau, matché sur son driver (donc au
        centre du monde), rangé sous 'parent' (sinon CTRL_grp), forme /
        translate / scale de la shape selon levelNShape /
        levelNShapeTranslate / levelNShapeScale. Placés sur la surface au
        setup (attach_level_controls). Remplit self.level_controls (une
        liste par niveau) et retourne tous les ctrls à plat.

        Utilisé par create_controls, et par les modules qui ajoutent un
        ruban à leur propre rig (ex: limb).
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
        Ctrl 'name' matché (position + orientation) sur 'joint', shape
        décalée/scalée, rangé sous 'parent' (sinon CTRL_grp), et connecté
        au joint (Builder.connect_control). En mode 'No Ctrl', la shape
        est posée directement sur le joint (Builder.create_joint_shape),
        qui est retourné à la place du ctrl.
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
        Contraint chaque sk joint à son follicule (ParentCnstrMtx,
        maintain offset : le joint garde son orientation sur la surface).
        Fait ici, après MainBuild.parent_joint_modules, pour que la
        contrainte capture le parent final des joints. Retourne les nodes
        de setup (surfaces, groupe de follicules) pour MainBuild.
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
        Accroche les ctrls de chaque niveau à la surface du niveau du
        dessous (Ribbon.get_level_base_surface) :

            ctrls du niveau 1 -> main nurb (base, skinnée à la chaîne)
            ctrls du niveau 2 -> level 1 nurb
            ctrls du niveau N -> level N-1 nurb

        Pas de cycle : la pile va de la main nurb vers le dernier niveau
        (connect_nurbs), une surface ne dépend jamais des niveaux au-dessus.

        Pour chaque ctrl : un follicule sur la surface de base à ses
        paramètres (u, v) : get_surface_uv(i / (count - 1)), 0..1, l'autre
        direction au milieu (0.5) - un follicule déjà créé sur la même
        surface aux mêmes (u, v) est réutilisé (get_level_follicle). Le node
        à accrocher (get_level_attach_target) est contraint au follicule
        sans maintain offset (ParentCnstrMtx, mo=False) : il prend
        exactement la position et l'orientation du follicule.

        Retourne le groupe de follicules.
        """

        if not self.level_drivers or not self.nurb:
            return []

        self.level_follicle_group = cmds.group(empty=True, name=f"{self.prefix}_ctrl_follicles_grp")
        cmds.setAttr(f"{self.level_follicle_group}.inheritsTransform", 0)

        self.level_follicle_group = self.parent_to_setup(self.level_follicle_group)

        self.level_follicles = {}

        # Node accroché au follicule pour chaque driver (même structure que
        # level_drivers) : son espace sert à fix_double_transform.
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

                # Sans maintain offset : le ctrl (ou son offset) prend
                # exactement la position / l'orientation du follicule.
                cnstrMtx_utilities.ParentCnstrMtx(target, follicle, mo=False, dcmpMtx=False)

        return [self.level_follicle_group]

    def get_level_follicle(self, surface, u, v, precision=6):

        """
        Follicule de 'surface' en (u, v) (0..1), réutilisé s'il a déjà été
        créé sur la même surface avec les mêmes paramètres (arrondis à
        'precision' décimales), sinon créé sous level_follicle_group.
        """

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
        Node accroché au follicule pour un ctrl de niveau :
        - 'No Ctrl' : le joint de niveau (il porte la shape) ;
        - 'Offset Group' : l'offset group du ctrl ;
        - sinon : le ctrl lui-même (contrainte dans son
          offsetParentMatrix, ses canaux restent libres).
        """

        if self.no_ctrl() or not control:
            return driver.name

        offset = self.main.get_offset_group(control)

        if self.offset_group() and offset and cmds.objExists(offset):
            return offset

        return control

    def constrain_sk_joints(self):
        """Follicule -> sk joint (ParentCnstrMtx, maintain offset, dans l'offsetParentMatrix)."""

        return [
            cnstrMtx_utilities.ParentCnstrMtx(joint.name, follicle, mo=False, dcmpMtx=False)
            for joint, follicle in zip(self.sk_joints, self.follicles)
        ]

    def connect_setup(self):

        """
        Skin de la main nurb (chaîne de joints), skin de chaque level nurb
        (ses drivers, double transformation corrigée), puis empilement :
        main nurb -> niveau 1 -> ... -> niveau N.
        """

        if not self.nurb:
            return

        self.skin_main_nurbs()
        self.skin_level_nurbs()

        # Après les skins : la surface est à sa pose de repos déformée.
        self.connect_follicle_scale()

    # --------------------------------------------------
    # FOLLICLE SCALE
    # --------------------------------------------------

    def use_follicle_scale(self):
        """Option 'Follicle Scale' : scale du joint root (et stretch) connecté aux follicules."""

        return bool(self.data.get("follicleScale", 1))

    def use_follicle_stretch(self):
        """Stretch des follicules : option 'Ribbon Stretch' (module ribbon), sinon 'Stretch' (stretchIk, limb)."""

        value = self.data.get("ribbonStretch")

        if value is None:
            value = self.data.get("stretchIk")

        return bool(value)

    def get_root_scale(self):

        """
        Plug du scale monde (X) du joint root du module (self.root_joint :
        root du ruban, ou du limb), lu par une ScaleCnstrMtx sur un groupe
        caché '{prefix}_follicleScale_grp' du groupe de setup. 1.0 sans root.
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
        Scale de tous les follicules - ceux des sk joints (surface du
        dessus) et ceux des ctrls de niveau (surface du niveau du dessous,
        get_level_follicle) - et donc des sk joints / ctrls qui les suivent
        (ParentCnstrMtx, qui transmet le scale). Les follicules des ctrls
        de niveau ne reçoivent que le scale root ; ceux des sk joints :

            sans stretch : scale du joint root sur les 3 axes ;
            stretch IK   : (limb, stretchIk) os de la chaîne IK le plus
                           proche du follicule au build : sur l'axe qui
                           suit le ruban, scale root * son facteur de
                           stretch, les deux autres axes scale root * son
                           squash ; dosés par le switch IK/FK (1 en FK) ;
            stretch ruban: (module ribbon, ribbonStretch) sur l'axe qui
                           suit le ruban, scale root * |tangente de la
                           surface au follicule| / (sa longueur au repos *
                           scale root) (pointOnSurfaceInfo) ; les deux
                           autres axes : scale root.

        Rien si l'option 'Follicle Scale' est désactivée. Retourne les nodes
        créés.
        """

        if not self.use_follicle_scale():
            return []

        # (follicule, surface sur laquelle il est posé, stretch autorisé) :
        # stretch pour les sk joints seulement, scale root pour les ctrls.
        top_surface = ribbon_utilities.Ribbon.get_top_surface(self.nurb, self.level_nurbs)

        targets = [(follicle, top_surface, True) for follicle in (getattr(self, "follicles", None) or [])]
        targets += [
            (follicle, surface, False)
            for (surface, _, _), follicle in (getattr(self, "level_follicles", None) or {}).items()
        ]

        if not targets:
            return []

        root_scale = self.get_root_scale()

        # Stretch de l'IK (simpleIk.stretch_ik) s'il existe, sinon celui du ruban.
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
            # root scale * (facteur ou squash de l'os, dosé par le switch IK/FK) : un node par os.
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

                # Axe du follicule le plus aligné sur l'os (longueur du ruban).
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

                # Tangente (non normalisée) de la surface au follicule.
                info = cmds.createNode("pointOnSurfaceInfo", name=f"{follicle}_scale_posi")
                cmds.connectAttr(f"{surface_shape}.worldSpace[0]", f"{info}.inputSurface")
                cmds.connectAttr(f"{follicle_shape}.parameterU", f"{info}.parameterU")
                cmds.connectAttr(f"{follicle_shape}.parameterV", f"{info}.parameterV")

                length = cmds.createNode("distanceBetween", name=f"{follicle}_tangent_db")
                cmds.connectAttr(f"{info}.{tangent_attr}", f"{length}.point2")

                rest_length = cmds.getAttr(f"{length}.distance") or 1.0

                # Longueur au repos à l'échelle du rig.
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

                # Axe du follicule le plus aligné sur la tangente (longueur du ruban).
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
        Skinne la main nurb (base de la pile) aux joints construits à
        partir de ribbonJointGuides. C'est la seule entrée du mouvement de
        la chaîne dans la pile. Sans joints (chaîne pas encore construite,
        ou surface fournie sans chaîne), la main nurb reste statique.

        Mêmes options que le Bind Skin de Maya :
        Bind to : Selected joints, Bind method : Closest distance,
        Skinning method : Classic linear, Normalize weights : Interactive,
        Weight distribution : Neighbors, Max influences : 2,
        Maintain max influences, Remove unused influences.
        """

        joints = self.get_chain_joints()

        if not joints:
            cmds.warning(f"Ribbon '{self.prefix}' : aucun joint de chaîne, main nurb non skinnée.")
            return None

        return skinCluster_utilities.bind_skin(joints, self.nurb, name=f"{self.prefix}_ribbon_skin", max_influences=2)

    def skin_level_nurbs(self):

        """
        Skinne chaque level nurb à ses drivers, puis corrige la double
        transformation (fix_double_transform) : la level nurb reçoit déjà
        la déformation du dessous par son Orig (connect_nurbs), et ses
        drivers la suivent aussi via leurs ctrls accrochés à la surface du
        dessous - leur skin ne doit voir que le mouvement local des ctrls.
        """

        skins = []

        targets_by_level = getattr(self, "level_attach_targets", [])

        for level, (nurb, drivers) in enumerate(zip(self.level_nurbs, self.level_drivers), start=1):

            # Au plus proche : chaque CV à 100% sur le driver le plus proche.
            skin = skinCluster_utilities.skin_to_closest_joints(
                [driver.name for driver in drivers],
                nurb,
                f"{self.prefix}_lvl{level}_skin"
            )

            skins.append(skin)

        return skins
