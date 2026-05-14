# -*- coding: mbcs -*-
# Abaqus/CAE Python 2.7
#
# 04_property_step_interaction_load_bc3_omega.py
#
# PURPOSE
# - Keep the previously working material / section / tie workflow
# - Keep the existing assembly/tie setup
# - Update only the BC and load application to a mentor-style simply
#   supported benchmark:
#     * U3 = 0 on all outer boundary edges
#     * Corner stabilization points:
#         A = bottom-left  -> U1=0, U2=0
#         B = top-left     -> U1=0
#         C = bottom-right -> U2=0
#     * Compression : left/right inward loads
#     * Shear       : left up, right down, top left, bottom right
#     * Combined    : compression + shear together
#
# IMPORTANT NOTES
# - Loads are still applied to the Lower_Skin boundary edges only.
#   The rest of the structure receives load through the existing ties.
# - We keep the existing RP/coupling approach and add only the minimum
#   changes needed for mentor-style BC/loading.
#

from abaqus import mdb
from abaqusConstants import *
from interaction import *
from load import *
from step import *
import os
import json

# ============================================================
# USER SETTINGS
# ============================================================
BASE_MODEL = "Model-1"

MODEL_COMPRESSION = "Model-Compression"
MODEL_SHEAR       = "Model-Shear"
MODEL_COMBINED    = "Model-Combined"

# Parts
PARTS = ["S_full", "S_half_patches", "Lower_Skin"]

# Instances
INST_SFULL          = "S_full-1"
INST_SHALF_PATCHES = "S_half_patches-1"
INST_LOWERSKIN      = "Lower_Skin-1"

# Material / section
MAT_NAME = "Aluminium_2024_T3"
SEC_NAME_SKIN = "Shell_Lower_Skin"
SEC_NAME_STIFF = "Shell_Stiffeners"
DEFAULT_THICKNESS_SKIN = 3.0   # mm fallback
DEFAULT_THICKNESS_STIFF = 3.0  # mm fallback

DENSITY = 2.78e-9
E = 73100.0
NU = 0.33

PLASTIC_TABLE = (
    (345.0, 0.0),
    (483.0, 0.15),
)

# Step (Buckle)
STEP_NAME = "Step-1"
NUM_EIGEN = 6
VECTORS_PER_ITER = 12
MAX_ITER = 300

# ------------------------------------------------------------
# Boundary edge sets created by Creating_Sets5_ALLINONE2.py
# ------------------------------------------------------------
SET_LOWER_LEFT   = "SET_LOWERSKIN_EDGE_LEFT"
SET_LOWER_RIGHT  = "SET_LOWERSKIN_EDGE_RIGHT"
SET_LOWER_TOP    = "SET_LOWERSKIN_EDGE_TOP"
SET_LOWER_BOTTOM = "SET_LOWERSKIN_EDGE_BOTTOM"

SET_SFULL_LEFT   = "SET_SFULL_BOUNDARY_EDGE_LEFT"
SET_SFULL_RIGHT  = "SET_SFULL_BOUNDARY_EDGE_RIGHT"
SET_SFULL_TOP    = "SET_SFULL_BOUNDARY_EDGE_TOP"
SET_SFULL_BOTTOM = "SET_SFULL_BOUNDARY_EDGE_BOTTOM"

# ------------------------------------------------------------
# Load surfaces: use EXISTING assembly edge-surfaces from Creating_Sets5 script
# ------------------------------------------------------------
SURF_LOAD_LEFT   = "SURF_EDGES__SET_LOWERSKIN_EDGE_LEFT"
SURF_LOAD_RIGHT  = "SURF_EDGES__SET_LOWERSKIN_EDGE_RIGHT"
SURF_LOAD_TOP    = "SURF_EDGES__SET_LOWERSKIN_EDGE_TOP"
SURF_LOAD_BOT    = "SURF_EDGES__SET_LOWERSKIN_EDGE_BOTTOM"

# ------------------------------------------------------------
# RP / coupling names
# ------------------------------------------------------------
RP_SET_LEFT      = "SET_RP_LEFT"
RP_SET_RIGHT     = "SET_RP_RIGHT"
RP_SET_SHEAR_TOP = "SET_RP_SHEAR_TOP"
RP_SET_SHEAR_BOT = "SET_RP_SHEAR_BOTTOM"

COUPLING_LEFT      = "Coupling_Left"
COUPLING_RIGHT     = "Coupling_Right"
COUPLING_SHEAR_TOP = "Coupling_Shear_Top"
COUPLING_SHEAR_BOT = "Coupling_Shear_Bottom"

# Corner stabilization point sets on Lower_Skin
SET_CORNER_A = "SET_CORNER_A_BOTTOM_LEFT"
SET_CORNER_B = "SET_CORNER_B_TOP_LEFT"
SET_CORNER_C = "SET_CORNER_C_BOTTOM_RIGHT"

# Small offset for outside RPs
RP_OFFSET_MM = 20.0

# Loads from mentor / curvilinear paper
COMP_LINE_LOAD_N_PER_MM  = 16.0
SHEAR_LINE_LOAD_N_PER_MM = 86.0

# Load names
LOAD_COMP_LEFT_NAME   = "Load_Compression_Left"
LOAD_COMP_RIGHT_NAME  = "Load_Compression_Right"

LOAD_SHEAR_LEFT_NAME  = "Load_Shear_Left"
LOAD_SHEAR_RIGHT_NAME = "Load_Shear_Right"
LOAD_SHEAR_TOP_NAME   = "Load_Shear_Top"
LOAD_SHEAR_BOT_NAME   = "Load_Shear_Bottom"

LOAD_COMB_LEFT_NAME        = "Load_Combined_Compression_Left"
LOAD_COMB_RIGHT_NAME       = "Load_Combined_Compression_Right"
LOAD_COMB_SHEAR_LEFT_NAME  = "Load_Combined_Shear_Left"
LOAD_COMB_SHEAR_RIGHT_NAME = "Load_Combined_Shear_Right"
LOAD_COMB_TOP_NAME         = "Load_Combined_Shear_Top"
LOAD_COMB_BOT_NAME         = "Load_Combined_Shear_Bottom"

# Old names to clean if present
OLD_LOAD_NAMES = [
    "Load-1",
    "Load_Compression",
    "Load_Shear",
    "Load_Combined",
    LOAD_COMP_LEFT_NAME,
    LOAD_COMP_RIGHT_NAME,
    LOAD_SHEAR_LEFT_NAME,
    LOAD_SHEAR_RIGHT_NAME,
    LOAD_SHEAR_TOP_NAME,
    LOAD_SHEAR_BOT_NAME,
    LOAD_COMB_LEFT_NAME,
    LOAD_COMB_RIGHT_NAME,
    LOAD_COMB_SHEAR_LEFT_NAME,
    LOAD_COMB_SHEAR_RIGHT_NAME,
    LOAD_COMB_TOP_NAME,
    LOAD_COMB_BOT_NAME,
]

OLD_BC_NAMES = [
    "Lower_Skin_bot_edge",
    "Sfull_endbot_edges",
    "LowerSkin_top",
    "Sfull_endtop",
    "LowerSkin_right",
    "Sfull_endright",
    "LowerSkin_left",
    "Sfull_endleft",
    "BC_SS_LowerSkin_Left",
    "BC_SS_LowerSkin_Right",
    "BC_SS_Sfull_Left",
    "BC_SS_Sfull_Right",
    "BC_CLAMP_LowerSkin_Left",
    "BC_CLAMP_Sfull_Left",
    "BC_SS_LowerSkin_Top",
    "BC_SS_Sfull_Top",
    "BC_SS_LowerSkin_Bottom",
    "BC_SS_Sfull_Bottom",
    "BC_Bottom_LowerSkin",
    "BC_Bottom_Sfull",
    "BC_Bottom_U1_LowerSkin",
    "BC_Bottom_U1_Sfull",
    "BC_Bottom_U2_LowerSkin",
    "BC_Bottom_U2_Sfull",
    "BC_Stab_Corner_U1",
    "BC_Stab_Corner_U2",
    "BC_CORNER_A",
    "BC_CORNER_B",
    "BC_CORNER_C",
]

# Important: do NOT include tie-interaction names here.
# This cleanup runs again after copying the base model into
# Compression/Shear/Combined models. If tie names are listed here,
# the copied load-case models lose all structural tie interactions.
# Keep only RP/coupling constraints that are recreated per load case.
OLD_CONSTRAINT_NAMES = [
    "Coupling_LoadEdge",
    COUPLING_LEFT,
    COUPLING_RIGHT,
    COUPLING_SHEAR_TOP,
    COUPLING_SHEAR_BOT,
]

OLD_SET_NAMES = [
    "SET_RP_LOAD",
    RP_SET_LEFT,
    RP_SET_RIGHT,
    RP_SET_SHEAR_TOP,
    RP_SET_SHEAR_BOT,
    SET_CORNER_A,
    SET_CORNER_B,
    SET_CORNER_C,
]

# Tie interactions
# Omega workflow:
# - S_half_patches is already the combined Shalf + S_half_patches part.
# - S_full <-> S_half_patches uses the mesh-based surfaces created in
#   Creating_Sets5_OMEGA_MESHBASED.py.
# - Lower_Skin is tied to both stiffener-side parts.
TIES = [
    ("Lower_skin_Sfull",
     ("ASM", "SURF_LOWERSKIN_TOP_SPOS"),
     ("ASM", "SURF_SFULL_BOT_FLANGE_SNEG")),

    ("Lower_skin_ShalfS_half_patches",
     ("ASM", "SURF_SHALF_PATCHES_LOWER_SNEG"),
     ("ASM", "SURF_LOWERSKIN_TOP_SPOS")),

    ("Sfull_ShalfS_half_patches",
     (INST_SFULL, "SURF_SFULL_SHALF_PATCH_IFACE_MESH_S1"),
     (INST_SHALF_PATCHES, "SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S1")),
]
# ============================================================


def _require(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def _safe_del(obj_dict, key):
    try:
        if key in obj_dict.keys():
            del obj_dict[key]
    except:
        pass


def _safe_del_tie(model, tie_name):
    if hasattr(model, "constraints"):
        _safe_del(model.constraints, tie_name)
    if hasattr(model, "interactions"):
        _safe_del(model.interactions, tie_name)


def _safe_del_load(model, load_name):
    try:
        if load_name in model.loads.keys():
            del model.loads[load_name]
    except:
        pass


def _safe_del_bc(model, bc_name):
    try:
        if bc_name in model.boundaryConditions.keys():
            del model.boundaryConditions[bc_name]
    except:
        pass


def _safe_del_constraint(model, name):
    try:
        if hasattr(model, "constraints") and name in model.constraints.keys():
            del model.constraints[name]
    except:
        pass


def _safe_del_asm_set(asm, name):
    try:
        if name in asm.sets.keys():
            del asm.sets[name]
    except:
        pass


def _get_model(model_name):
    _require(model_name in mdb.models.keys(), "Model '%s' not found." % model_name)
    return mdb.models[model_name]


def _get_asm(model):
    return model.rootAssembly


def _get_region_from_surface(model, surf_ref):
    asm = _get_asm(model)

    scope, name = surf_ref
    if scope == "ASM":
        _require(name in asm.surfaces.keys(), "Assembly surface not found: %s" % name)
        return asm.surfaces[name]
    else:
        _require(scope in asm.instances.keys(), "Instance not found: %s" % scope)
        inst = asm.instances[scope]
        _require(name in inst.surfaces.keys(), "Instance surface not found: %s.%s" % (scope, name))
        return inst.surfaces[name]


def _get_region_from_set(model, set_name):
    asm = _get_asm(model)
    _require(set_name in asm.sets.keys(), "Assembly set not found: %s" % set_name)
    return asm.sets[set_name]


def _edge_length(edge):
    try:
        return float(edge.getSize(printResults=False))
    except:
        pass
    try:
        return float(edge.getSize(False))
    except:
        pass
    raise RuntimeError("Could not evaluate edge length.")


def _sum_edge_set_length_mm(model, set_name):
    asm = _get_asm(model)
    _require(set_name in asm.sets.keys(), "Assembly set not found: %s" % set_name)
    s = asm.sets[set_name]
    try:
        edges = s.edges
    except:
        edges = None
    _require(edges is not None and len(edges) > 0, "Set '%s' does not contain edges." % set_name)
    total = 0.0
    for e in edges:
        total += _edge_length(e)
    return total


def _bbox_of_edge_set(model, set_name):
    asm = _get_asm(model)
    _require(set_name in asm.sets.keys(), "Assembly set not found: %s" % set_name)
    s = asm.sets[set_name]
    edges = s.edges
    _require(edges is not None and len(edges) > 0, "Set '%s' does not contain edges." % set_name)
    bb = edges.getBoundingBox()
    return bb['low'], bb['high']


def _outside_rp_point_from_set(model, set_name, direction):
    low, high = _bbox_of_edge_set(model, set_name)
    x_mid = 0.5 * (low[0] + high[0])
    y_mid = 0.5 * (low[1] + high[1])
    z_mid = 0.5 * (low[2] + high[2])

    if direction == "left":
        pt = (low[0] - RP_OFFSET_MM, y_mid, z_mid)
    elif direction == "right":
        pt = (high[0] + RP_OFFSET_MM, y_mid, z_mid)
    elif direction == "top":
        pt = (x_mid, high[1] + RP_OFFSET_MM, z_mid)
    elif direction == "bottom":
        pt = (x_mid, low[1] - RP_OFFSET_MM, z_mid)
    else:
        raise RuntimeError("Unknown direction: %s" % direction)

    print("\nRP DEBUG for set:", set_name)
    print("  bbox low  =", low)
    print("  bbox high =", high)
    print("  direction =", direction)
    print("  RP point  =", pt)
    return pt


def _create_rp_set_outside(model, rp_set_name, source_set_name, direction):
    asm = _get_asm(model)
    _safe_del_asm_set(asm, rp_set_name)
    rp_pt = _outside_rp_point_from_set(model, source_set_name, direction)
    feat = asm.ReferencePoint(point=rp_pt)
    rp = asm.referencePoints[feat.id]
    asm.Set(name=rp_set_name, referencePoints=(rp,))
    print("Created RP set:", rp_set_name, "at", rp_pt)


def _read_design_vars_json():
    if 'CASE_DIR' not in globals() or not CASE_DIR:
        print("WARNING: CASE_DIR not found in globals(); using default thickness.")
        return None

    case_dir = os.path.normpath(CASE_DIR)
    design_path = os.path.join(case_dir, "design_vars.json")

    if not os.path.isfile(design_path):
        print("WARNING: design_vars.json not found; using default thickness.")
        print("Expected:", design_path)
        return None

    try:
        f = open(design_path, "r")
        try:
            data = json.load(f)
        finally:
            f.close()
        print("Read design_vars.json:", design_path)
        print("Design vars:", data)
        return data
    except Exception as e:
        print("WARNING: Could not read design_vars.json; using default thickness.")
        print(str(e))
        return None


def _get_thicknesses_from_design():
    data = _read_design_vars_json()

    t_skin = DEFAULT_THICKNESS_SKIN
    t_stiff = DEFAULT_THICKNESS_STIFF

    if not isinstance(data, dict):
        return t_skin, t_stiff

    try:
        t_skin = float(data.get("Thickness_skin", data.get("Thickness", DEFAULT_THICKNESS_SKIN)))
        if t_skin <= 0.0:
            raise RuntimeError("Thickness_skin must be > 0")
    except:
        print("WARNING: Invalid Thickness_skin in design_vars.json; using default thickness.")
        t_skin = DEFAULT_THICKNESS_SKIN

    try:
        t_stiff = float(data.get("Thickness_stiff", data.get("Thickness", DEFAULT_THICKNESS_STIFF)))
        if t_stiff <= 0.0:
            raise RuntimeError("Thickness_stiff must be > 0")
    except:
        print("WARNING: Invalid Thickness_stiff in design_vars.json; using default thickness.")
        t_stiff = DEFAULT_THICKNESS_STIFF

    return t_skin, t_stiff


def create_material_and_sections(model, thickness_skin, thickness_stiff):
    if MAT_NAME in model.materials.keys():
        mat = model.materials[MAT_NAME]
    else:
        mat = model.Material(name=MAT_NAME)

    try:
        mat.Density(table=((DENSITY,),))
    except:
        pass
    try:
        mat.Elastic(table=((E, NU),))
    except:
        pass
    try:
        mat.Plastic(table=PLASTIC_TABLE)
    except:
        pass

    if SEC_NAME_SKIN in model.sections.keys():
        _safe_del(model.sections, SEC_NAME_SKIN)
    if SEC_NAME_STIFF in model.sections.keys():
        _safe_del(model.sections, SEC_NAME_STIFF)

    model.HomogeneousShellSection(
        name=SEC_NAME_SKIN,
        material=MAT_NAME,
        thicknessType=UNIFORM,
        thickness=thickness_skin,
        thicknessField='',
        idealization=NO_IDEALIZATION,
        poissonDefinition=DEFAULT,
        thicknessModulus=None,
        temperature=GRADIENT,
        useDensity=OFF,
        integrationRule=SIMPSON,
        numIntPts=5
    )

    model.HomogeneousShellSection(
        name=SEC_NAME_STIFF,
        material=MAT_NAME,
        thicknessType=UNIFORM,
        thickness=thickness_stiff,
        thicknessField='',
        idealization=NO_IDEALIZATION,
        poissonDefinition=DEFAULT,
        thicknessModulus=None,
        temperature=GRADIENT,
        useDensity=OFF,
        integrationRule=SIMPSON,
        numIntPts=5
    )

    print("Created/updated material:", MAT_NAME)
    print("Created shell section:", SEC_NAME_SKIN, "thickness=", thickness_skin)
    print("Created shell section:", SEC_NAME_STIFF, "thickness=", thickness_stiff)


def assign_section_to_all_parts(model):
    for p_name in PARTS:
        _require(p_name in model.parts.keys(), "Part not found: %s" % p_name)
        p = model.parts[p_name]
        set_all = "ALL_FACES__" + p_name
        if set_all in p.sets.keys():
            _safe_del(p.sets, set_all)
        p.Set(name=set_all, faces=p.faces)
        section_name = SEC_NAME_SKIN if p_name == "Lower_Skin" else SEC_NAME_STIFF
        p.SectionAssignment(
            region=p.sets[set_all],
            sectionName=section_name,
            offset=0.0,
            offsetType=MIDDLE_SURFACE,
            offsetField='',
            thicknessAssignment=FROM_SECTION
        )
        print("Assigned section to part:", p_name, "section=", section_name, "(faces=%d)" % len(p.faces))


def create_buckle_step(model):
    if STEP_NAME in model.steps.keys():
        _safe_del(model.steps, STEP_NAME)
    model.BuckleStep(
        name=STEP_NAME,
        previous='Initial',
        numEigen=NUM_EIGEN,
        vectors=VECTORS_PER_ITER,
        maxIterations=MAX_ITER
    )
    try:
        model.steps[STEP_NAME].setValues(nlgeom=OFF)
    except:
        pass
    print("Created step:", STEP_NAME)


def create_ties(model):
    for tie_name, master_ref, slave_ref in TIES:
        _safe_del_tie(model, tie_name)
        master_region = _get_region_from_surface(model, master_ref)
        slave_region  = _get_region_from_surface(model, slave_ref)
        model.Tie(
            name=tie_name,
            master=master_region,
            slave=slave_region,
            positionToleranceMethod=COMPUTED,
            adjust=ON,
            tieRotations=ON,
            thickness=ON
        )
        print("Created Tie:", tie_name)


def clear_old_loads_and_bcs(model):
    asm = _get_asm(model)
    for name in OLD_LOAD_NAMES:
        _safe_del_load(model, name)
    for name in OLD_BC_NAMES:
        _safe_del_bc(model, name)
    for name in OLD_CONSTRAINT_NAMES:
        _safe_del_constraint(model, name)
    for name in OLD_SET_NAMES:
        _safe_del_asm_set(asm, name)


def create_simply_supported_u3_bc(model):
    bc_specs = [
        ("BC_SS_LowerSkin_Left",   SET_LOWER_LEFT),
        ("BC_SS_LowerSkin_Right",  SET_LOWER_RIGHT),
        ("BC_SS_LowerSkin_Top",    SET_LOWER_TOP),
        ("BC_SS_LowerSkin_Bottom", SET_LOWER_BOTTOM),
        ("BC_SS_Sfull_Left",       SET_SFULL_LEFT),
        ("BC_SS_Sfull_Right",      SET_SFULL_RIGHT),
        ("BC_SS_Sfull_Top",        SET_SFULL_TOP),
        ("BC_SS_Sfull_Bottom",     SET_SFULL_BOTTOM),
    ]
    for bc_name, set_name in bc_specs:
        region = _get_region_from_set(model, set_name)
        _safe_del_bc(model, bc_name)
        model.DisplacementBC(
            name=bc_name,
            createStepName='Initial',
            region=region,
            u1=UNSET, u2=UNSET, u3=0.0,
            ur1=UNSET, ur2=UNSET, ur3=UNSET,
            amplitude=UNSET,
            distributionType=UNIFORM,
            fieldName='',
            localCsys=None
        )
        print("Created simply-supported BC:", bc_name, "-> U3=0 on", set_name)


def _pick_closest_vertex(inst, target_xyz):
    best_idx = None
    best_d2 = None
    for i, v in enumerate(inst.vertices):
        try:
            p = v.pointOn[0]
        except:
            continue
        dx = p[0] - target_xyz[0]
        dy = p[1] - target_xyz[1]
        dz = p[2] - target_xyz[2]
        d2 = dx*dx + dy*dy + dz*dz
        if best_idx is None or d2 < best_d2:
            best_idx = i
            best_d2 = d2
    _require(best_idx is not None, "Could not find a corner vertex on %s" % INST_LOWERSKIN)
    return inst.vertices[best_idx:best_idx+1]


def create_corner_stabilization_sets(model):
    asm = _get_asm(model)
    _require(INST_LOWERSKIN in asm.instances.keys(), "Missing instance: %s" % INST_LOWERSKIN)
    inst = asm.instances[INST_LOWERSKIN]

    left_low, left_high = _bbox_of_edge_set(model, SET_LOWER_LEFT)
    right_low, right_high = _bbox_of_edge_set(model, SET_LOWER_RIGHT)
    top_low, top_high = _bbox_of_edge_set(model, SET_LOWER_TOP)
    bot_low, bot_high = _bbox_of_edge_set(model, SET_LOWER_BOTTOM)

    x_left = 0.5 * (left_low[0] + left_high[0])
    x_right = 0.5 * (right_low[0] + right_high[0])
    y_top = 0.5 * (top_low[1] + top_high[1])
    y_bottom = 0.5 * (bot_low[1] + bot_high[1])

    inst_bb = inst.vertices.getBoundingBox()
    z_mid = 0.5 * (inst_bb['low'][2] + inst_bb['high'][2])

    vA = _pick_closest_vertex(inst, (x_left,  y_bottom, z_mid))  # bottom-left
    vB = _pick_closest_vertex(inst, (x_left,  y_top,    z_mid))  # top-left
    vC = _pick_closest_vertex(inst, (x_right, y_bottom, z_mid))  # bottom-right

    _safe_del_asm_set(asm, SET_CORNER_A)
    _safe_del_asm_set(asm, SET_CORNER_B)
    _safe_del_asm_set(asm, SET_CORNER_C)

    asm.Set(name=SET_CORNER_A, vertices=vA)
    asm.Set(name=SET_CORNER_B, vertices=vB)
    asm.Set(name=SET_CORNER_C, vertices=vC)

    print("Created corner stabilization sets:")
    print("  A =", SET_CORNER_A, "(bottom-left)")
    print("  B =", SET_CORNER_B, "(top-left)")
    print("  C =", SET_CORNER_C, "(bottom-right)")


def create_corner_stabilization_bcs(model):
    create_corner_stabilization_sets(model)

    bc_specs = [
        ("BC_CORNER_A", SET_CORNER_A, 0.0, 0.0),   # A: U1=0, U2=0
        ("BC_CORNER_B", SET_CORNER_B, 0.0, UNSET), # B: U1=0
        ("BC_CORNER_C", SET_CORNER_C, UNSET, 0.0), # C: U2=0
    ]

    for bc_name, set_name, u1_val, u2_val in bc_specs:
        region = _get_region_from_set(model, set_name)
        _safe_del_bc(model, bc_name)
        model.DisplacementBC(
            name=bc_name,
            createStepName='Initial',
            region=region,
            u1=u1_val, u2=u2_val, u3=UNSET,
            ur1=UNSET, ur2=UNSET, ur3=UNSET,
            amplitude=UNSET,
            distributionType=UNIFORM,
            fieldName='',
            localCsys=None
        )
        print("Created corner stabilization BC:", bc_name, "on", set_name)


def create_case_rps_and_couplings(model):
    asm = _get_asm(model)

    _require(SURF_LOAD_LEFT in asm.surfaces.keys(),  "Surface not found: %s" % SURF_LOAD_LEFT)
    _require(SURF_LOAD_RIGHT in asm.surfaces.keys(), "Surface not found: %s" % SURF_LOAD_RIGHT)
    _require(SURF_LOAD_TOP in asm.surfaces.keys(),   "Surface not found: %s" % SURF_LOAD_TOP)
    _require(SURF_LOAD_BOT in asm.surfaces.keys(),   "Surface not found: %s" % SURF_LOAD_BOT)

    _create_rp_set_outside(model, RP_SET_LEFT,      SET_LOWER_LEFT,   "left")
    _create_rp_set_outside(model, RP_SET_RIGHT,     SET_LOWER_RIGHT,  "right")
    _create_rp_set_outside(model, RP_SET_SHEAR_TOP, SET_LOWER_TOP,    "top")
    _create_rp_set_outside(model, RP_SET_SHEAR_BOT, SET_LOWER_BOTTOM, "bottom")

    _safe_del_constraint(model, COUPLING_LEFT)
    _safe_del_constraint(model, COUPLING_RIGHT)
    _safe_del_constraint(model, COUPLING_SHEAR_TOP)
    _safe_del_constraint(model, COUPLING_SHEAR_BOT)

    model.Coupling(
        name=COUPLING_LEFT,
        controlPoint=asm.sets[RP_SET_LEFT],
        surface=asm.surfaces[SURF_LOAD_LEFT],
        influenceRadius=WHOLE_SURFACE,
        couplingType=DISTRIBUTING,
        weightingMethod=UNIFORM,
        localCsys=None,
        u1=ON, u2=ON, u3=OFF,
        ur1=OFF, ur2=OFF, ur3=OFF
    )
    print("Created distributing coupling:", COUPLING_LEFT, "RP ->", SURF_LOAD_LEFT)

    model.Coupling(
        name=COUPLING_RIGHT,
        controlPoint=asm.sets[RP_SET_RIGHT],
        surface=asm.surfaces[SURF_LOAD_RIGHT],
        influenceRadius=WHOLE_SURFACE,
        couplingType=DISTRIBUTING,
        weightingMethod=UNIFORM,
        localCsys=None,
        u1=ON, u2=ON, u3=OFF,
        ur1=OFF, ur2=OFF, ur3=OFF
    )
    print("Created distributing coupling:", COUPLING_RIGHT, "RP ->", SURF_LOAD_RIGHT)

    model.Coupling(
        name=COUPLING_SHEAR_TOP,
        controlPoint=asm.sets[RP_SET_SHEAR_TOP],
        surface=asm.surfaces[SURF_LOAD_TOP],
        influenceRadius=WHOLE_SURFACE,
        couplingType=DISTRIBUTING,
        weightingMethod=UNIFORM,
        localCsys=None,
        u1=ON, u2=ON, u3=OFF,
        ur1=OFF, ur2=OFF, ur3=OFF
    )
    print("Created distributing coupling:", COUPLING_SHEAR_TOP, "RP ->", SURF_LOAD_TOP)

    model.Coupling(
        name=COUPLING_SHEAR_BOT,
        controlPoint=asm.sets[RP_SET_SHEAR_BOT],
        surface=asm.surfaces[SURF_LOAD_BOT],
        influenceRadius=WHOLE_SURFACE,
        couplingType=DISTRIBUTING,
        weightingMethod=UNIFORM,
        localCsys=None,
        u1=ON, u2=ON, u3=OFF,
        ur1=OFF, ur2=OFF, ur3=OFF
    )
    print("Created distributing coupling:", COUPLING_SHEAR_BOT, "RP ->", SURF_LOAD_BOT)


def create_case_load(model, case_name, left_edge_length_mm, right_edge_length_mm, top_edge_length_mm, bottom_edge_length_mm):
    asm = _get_asm(model)
    _require(RP_SET_LEFT in asm.sets.keys(),      "RP set not found: %s" % RP_SET_LEFT)
    _require(RP_SET_RIGHT in asm.sets.keys(),     "RP set not found: %s" % RP_SET_RIGHT)
    _require(RP_SET_SHEAR_TOP in asm.sets.keys(), "RP set not found: %s" % RP_SET_SHEAR_TOP)
    _require(RP_SET_SHEAR_BOT in asm.sets.keys(), "RP set not found: %s" % RP_SET_SHEAR_BOT)

    rp_left = asm.sets[RP_SET_LEFT]
    rp_right = asm.sets[RP_SET_RIGHT]
    rp_top  = asm.sets[RP_SET_SHEAR_TOP]
    rp_bot  = asm.sets[RP_SET_SHEAR_BOT]

    f_left = COMP_LINE_LOAD_N_PER_MM  * left_edge_length_mm
    f_right = COMP_LINE_LOAD_N_PER_MM * right_edge_length_mm
    f_top  = SHEAR_LINE_LOAD_N_PER_MM * top_edge_length_mm
    f_bot  = SHEAR_LINE_LOAD_N_PER_MM * bottom_edge_length_mm
    f_vleft  = SHEAR_LINE_LOAD_N_PER_MM * left_edge_length_mm
    f_vright = SHEAR_LINE_LOAD_N_PER_MM * right_edge_length_mm

    for nm in OLD_LOAD_NAMES:
        _safe_del_load(model, nm)

    if case_name == "compression":
        model.ConcentratedForce(
            name=LOAD_COMP_LEFT_NAME,
            createStepName=STEP_NAME,
            region=rp_left,
            cf1=+f_left,
            cf2=0.0,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_COMP_RIGHT_NAME,
            createStepName=STEP_NAME,
            region=rp_right,
            cf1=-f_right,
            cf2=0.0,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        print("Created balanced compression loads:")
        print("  LEFT RP   : CF1 =", +f_left, "N")
        print("  RIGHT RP  : CF1 =", -f_right, "N")

    elif case_name == "shear":
        # Mentor shear sense:
        #   left  = +U2 (up)
        #   right = -U2 (down)
        #   top   = -U1 (left)
        #   bottom= +U1 (right)
        model.ConcentratedForce(
            name=LOAD_SHEAR_LEFT_NAME,
            createStepName=STEP_NAME,
            region=rp_left,
            cf1=0.0,
            cf2=+f_vleft,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_SHEAR_RIGHT_NAME,
            createStepName=STEP_NAME,
            region=rp_right,
            cf1=0.0,
            cf2=-f_vright,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_SHEAR_TOP_NAME,
            createStepName=STEP_NAME,
            region=rp_top,
            cf1=-f_top,
            cf2=0.0,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_SHEAR_BOT_NAME,
            createStepName=STEP_NAME,
            region=rp_bot,
            cf1=+f_bot,
            cf2=0.0,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        print("Created shear loads:")
        print("  LEFT RP   : CF2 =", +f_vleft, "N")
        print("  RIGHT RP  : CF2 =", -f_vright, "N")
        print("  TOP RP    : CF1 =", -f_top, "N")
        print("  BOTTOM RP : CF1 =", +f_bot, "N")

    elif case_name == "combined":
        model.ConcentratedForce(
            name=LOAD_COMB_LEFT_NAME,
            createStepName=STEP_NAME,
            region=rp_left,
            cf1=+f_left,
            cf2=0.0,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_COMB_RIGHT_NAME,
            createStepName=STEP_NAME,
            region=rp_right,
            cf1=-f_right,
            cf2=0.0,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_COMB_SHEAR_LEFT_NAME,
            createStepName=STEP_NAME,
            region=rp_left,
            cf1=0.0,
            cf2=+f_vleft,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_COMB_SHEAR_RIGHT_NAME,
            createStepName=STEP_NAME,
            region=rp_right,
            cf1=0.0,
            cf2=-f_vright,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_COMB_TOP_NAME,
            createStepName=STEP_NAME,
            region=rp_top,
            cf1=-f_top,
            cf2=0.0,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        model.ConcentratedForce(
            name=LOAD_COMB_BOT_NAME,
            createStepName=STEP_NAME,
            region=rp_bot,
            cf1=+f_bot,
            cf2=0.0,
            cf3=0.0,
            distributionType=UNIFORM,
            field='',
            localCsys=None
        )
        print("Created combined loads:")
        print("  LEFT RP   : CF1 =", +f_left, "N")
        print("  RIGHT RP  : CF1 =", -f_right, "N")
        print("  LEFT RP   : CF2 =", +f_vleft, "N")
        print("  RIGHT RP  : CF2 =", -f_vright, "N")
        print("  TOP RP    : CF1 =", -f_top, "N")
        print("  BOTTOM RP : CF1 =", +f_bot, "N")
    else:
        raise RuntimeError("Unknown case_name: %s" % case_name)


def prepare_base_model():
    model = _get_model(BASE_MODEL)
    asm = _get_asm(model)

    for p in PARTS:
        _require(p in model.parts.keys(), "Missing part: %s" % p)

    _require(INST_SFULL in asm.instances.keys(),
             "Missing instance: %s (run import+assemble first)" % INST_SFULL)
    _require(INST_SHALF_PATCHES in asm.instances.keys(),
             "Missing instance: %s (run import+assemble first)" % INST_SHALF_PATCHES)
    _require(INST_LOWERSKIN in asm.instances.keys(),
             "Missing instance: %s (run import+assemble first)" % INST_LOWERSKIN)

    thickness_skin, thickness_stiff = _get_thicknesses_from_design()
    print("\nUsing shell thickness_skin =", thickness_skin, "mm")
    print("Using shell thickness_stiff =", thickness_stiff, "mm")

    clear_old_loads_and_bcs(model)

    create_material_and_sections(model, thickness_skin, thickness_stiff)
    assign_section_to_all_parts(model)
    create_buckle_step(model)
    create_ties(model)

    left_edge_length_mm   = _sum_edge_set_length_mm(model, SET_LOWER_LEFT)
    right_edge_length_mm  = _sum_edge_set_length_mm(model, SET_LOWER_RIGHT)
    top_edge_length_mm    = _sum_edge_set_length_mm(model, SET_LOWER_TOP)
    bottom_edge_length_mm = _sum_edge_set_length_mm(model, SET_LOWER_BOTTOM)

    print("\nMeasured Lower_Skin load edge lengths:")
    print("  Left edge total length   =", left_edge_length_mm, "mm")
    print("  Right edge total length  =", right_edge_length_mm, "mm")
    print("  Top edge total length    =", top_edge_length_mm, "mm")
    print("  Bottom edge total length =", bottom_edge_length_mm, "mm")

    print("\nLine loads:")
    print("  Compression line load    =", COMP_LINE_LOAD_N_PER_MM, "N/mm")
    print("  Shear line load          =", SHEAR_LINE_LOAD_N_PER_MM, "N/mm")

    print("\nEquivalent total forces:")
    print("  Left compression force   =", COMP_LINE_LOAD_N_PER_MM * left_edge_length_mm, "N")
    print("  Right compression force  =", COMP_LINE_LOAD_N_PER_MM * right_edge_length_mm, "N")
    print("  Left shear total force   =", SHEAR_LINE_LOAD_N_PER_MM * left_edge_length_mm, "N")
    print("  Right shear total force  =", SHEAR_LINE_LOAD_N_PER_MM * right_edge_length_mm, "N")
    print("  Top shear total force    =", SHEAR_LINE_LOAD_N_PER_MM * top_edge_length_mm, "N")
    print("  Bottom shear total force =", SHEAR_LINE_LOAD_N_PER_MM * bottom_edge_length_mm, "N")

    return left_edge_length_mm, right_edge_length_mm, top_edge_length_mm, bottom_edge_length_mm


def copy_models_from_base():
    for name in [MODEL_COMPRESSION, MODEL_SHEAR, MODEL_COMBINED]:
        if name in mdb.models.keys():
            del mdb.models[name]

    mdb.Model(name=MODEL_COMPRESSION, objectToCopy=mdb.models[BASE_MODEL])
    mdb.Model(name=MODEL_SHEAR,       objectToCopy=mdb.models[BASE_MODEL])
    mdb.Model(name=MODEL_COMBINED,    objectToCopy=mdb.models[BASE_MODEL])

    print("Created model:", MODEL_COMPRESSION)
    print("Created model:", MODEL_SHEAR)
    print("Created model:", MODEL_COMBINED)


def configure_case_model(model_name, case_name, left_edge_length_mm, right_edge_length_mm, top_edge_length_mm, bottom_edge_length_mm):
    model = _get_model(model_name)

    clear_old_loads_and_bcs(model)

    create_case_rps_and_couplings(model)
    create_simply_supported_u3_bc(model)
    create_corner_stabilization_bcs(model)
    create_case_load(model, case_name, left_edge_length_mm, right_edge_length_mm, top_edge_length_mm, bottom_edge_length_mm)

    print("Configured model '%s' for case '%s'" % (model_name, case_name))


def main():
    left_edge_length_mm, right_edge_length_mm, top_edge_length_mm, bottom_edge_length_mm = prepare_base_model()
    copy_models_from_base()

    configure_case_model(MODEL_COMPRESSION, "compression",
                         left_edge_length_mm, right_edge_length_mm, top_edge_length_mm, bottom_edge_length_mm)
    configure_case_model(MODEL_SHEAR, "shear",
                         left_edge_length_mm, right_edge_length_mm, top_edge_length_mm, bottom_edge_length_mm)
    configure_case_model(MODEL_COMBINED, "combined",
                         left_edge_length_mm, right_edge_length_mm, top_edge_length_mm, bottom_edge_length_mm)

    try:
        if BASE_MODEL in mdb.models.keys():
            del mdb.models[BASE_MODEL]
            print("Deleted base model:", BASE_MODEL)
    except:
        pass

    print("\nDONE: 04_property_step_interaction_load_bc3_balanced_left_right.py")
    print("Prepared models:")
    print("  - %s  -> Compression" % MODEL_COMPRESSION)
    print("  - %s  -> Shear" % MODEL_SHEAR)
    print("  - %s  -> Combined" % MODEL_COMBINED)


if __name__ == "__main__":
    main()
