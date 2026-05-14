# -*- coding: mbcs -*-
# Abaqus/CAE Python 2.7
#
# Creating_Sets5_OMEGA_MESHBASED.py
#
# Omega workflow:
#   Parts/instances:
#     - Lower_Skin / Lower_Skin-1
#     - S_full / S_full-1
#     - S_half_patches / S_half_patches-1
#
# Main change from I-profile script:
#   - No separate S_half_web and Patches parts
#   - Reads only:
#       Sfull_Shalf&Patches.json
#   - Creates mesh/element-based interface surfaces for:
#       S_full <-> S_half_patches
#
# Important:
#   - Boundary/load/BC sets are still assembly edge sets.
#     This is intentional because the next BC/load script needs edge lengths.
#   - Tie/contact interface between S_full and S_half_patches is mesh-based.

from abaqus import *
from abaqusConstants import *
import os, json, codecs, math

MODEL = "Model-1"

# ============================================================
# CASE DIRECTORY
# ============================================================
if 'CASE_DIR' not in globals() or not CASE_DIR:
    raise RuntimeError(
        "CASE_DIR is not defined.\n"
        "This script must be launched by RUN_ALL_PIPELINE3.py with CASE_DIR set."
    )

CASE_DIR = os.path.normpath(CASE_DIR)

# Optional design variables written by MASTER_GH_TO_ABAQUS3.py
DESIGN_VARS_JSON = os.path.join(CASE_DIR, "design_vars.json")

def _read_design_vars():
    if not os.path.isfile(DESIGN_VARS_JSON):
        return {}
    try:
        f = open(DESIGN_VARS_JSON, "r")
        try:
            data = json.load(f)
        finally:
            f.close()
        if isinstance(data, dict):
            return data
    except:
        pass
    return {}

DESIGN_VARS = _read_design_vars()

def _get_design_height(default_value):
    try:
        return float(DESIGN_VARS.get("Height", default_value))
    except:
        return float(default_value)

# ============================================================
# JSON names inside the CASE folder
# ============================================================
JSON_NAME_SFULL_SHALF_PATCHES = "Sfull_Shalf&Patches.json"
JSON_SFULL_SHALF_PATCHES = os.path.join(CASE_DIR, JSON_NAME_SFULL_SHALF_PATCHES)

# ============================================================
# Parts
# ============================================================
PART_SFULL          = "S_full"
PART_SHALF_PATCHES = "S_half_patches"
PART_LOWERSKIN      = "Lower_Skin"

# ============================================================
# Instances
# ============================================================
INST_SFULL          = "S_full-1"
INST_SHALF_PATCHES = "S_half_patches-1"
INST_LOWERSKIN      = "Lower_Skin-1"

# ============================================================
# Names: sets / surfaces
# ============================================================

# Lower skin / S_full broad contact
SET_SFULL_BOT_FLANGE_LOWER_FACES = "SET_SFULL_BOT_FLANGE_LOWER_FACES"
SURF_SFULL_BOT_FLANGE_SNEG       = "SURF_SFULL_BOT_FLANGE_SNEG"

SET_LOWERSKIN_UPPER_FACES = "SET_LOWERSKIN_UPPER_FACES"
SURF_LOWERSKIN_TOP_SPOS   = "SURF_LOWERSKIN_TOP_SPOS"

# Optional local lower-skin contact surfaces.
# These are only created when the XY footprint selection succeeds.
# If not created, 04_static_combined_validation_omega.py falls back to SURF_LOWERSKIN_TOP_SPOS.
SET_LOWERSKIN_SFULL_CONTACT_FACES         = "SET_LOWERSKIN_SFULL_CONTACT_FACES"
SURF_LOWERSKIN_SFULL_CONTACT_SPOS         = "SURF_LOWERSKIN_SFULL_CONTACT_SPOS"
SET_LOWERSKIN_SHALF_PATCHES_CONTACT_FACES = "SET_LOWERSKIN_SHALF_PATCHES_CONTACT_FACES"
SURF_LOWERSKIN_SHALF_PATCHES_CONTACT_SPOS = "SURF_LOWERSKIN_SHALF_PATCHES_CONTACT_SPOS"

# S_half_patches lower contact to lower skin
SET_SHALF_PATCHES_LOWER_FACES = "SET_SHALF_PATCHES_LOWER_FACES"
SURF_SHALF_PATCHES_LOWER_SNEG = "SURF_SHALF_PATCHES_LOWER_SNEG"
SURF_SHALF_PATCHES_LOWER_SPOS = "SURF_SHALF_PATCHES_LOWER_SPOS"

# Lower skin perimeter edge sets for BC/load
SET_LOWERSKIN_EDGE_LEFT   = "SET_LOWERSKIN_EDGE_LEFT"
SET_LOWERSKIN_EDGE_RIGHT  = "SET_LOWERSKIN_EDGE_RIGHT"
SET_LOWERSKIN_EDGE_TOP    = "SET_LOWERSKIN_EDGE_TOP"
SET_LOWERSKIN_EDGE_BOTTOM = "SET_LOWERSKIN_EDGE_BOTTOM"

# S_full outer boundary edge sets for U3 simply-supported BC
SET_SFULL_BND_EDGE_LEFT   = "SET_SFULL_BOUNDARY_EDGE_LEFT"
SET_SFULL_BND_EDGE_RIGHT  = "SET_SFULL_BOUNDARY_EDGE_RIGHT"
SET_SFULL_BND_EDGE_TOP    = "SET_SFULL_BOUNDARY_EDGE_TOP"
SET_SFULL_BND_EDGE_BOTTOM = "SET_SFULL_BOUNDARY_EDGE_BOTTOM"

# Mesh-based JSON interface surfaces: S_full <-> S_half_patches
SET_SFULL_SHALF_PATCH_IFACE_MESH_ELEMS = "SET_SFULL_SHALF_PATCH_IFACE_MESH_ELEMS"
SURF_SFULL_SHALF_PATCH_IFACE_MESH_S1   = "SURF_SFULL_SHALF_PATCH_IFACE_MESH_S1"
SURF_SFULL_SHALF_PATCH_IFACE_MESH_S2   = "SURF_SFULL_SHALF_PATCH_IFACE_MESH_S2"

SET_SHALF_PATCHES_SFULL_IFACE_MESH_ELEMS = "SET_SHALF_PATCHES_SFULL_IFACE_MESH_ELEMS"
SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S1   = "SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S1"
SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S2   = "SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S2"

# ============================================================
# Tuning
# ============================================================
DEFAULT_HEIGHT = 20.0
DESIGN_HEIGHT = _get_design_height(DEFAULT_HEIGHT)
Z_TARGET_BOT = -0.5 * DESIGN_HEIGHT

Z_TOL_FACE   = 2.0
NZ_HORIZ_MIN = 0.60

BND_TOL_XY      = 2.0
ONLY_FREE_EDGES = True
LOWERSKIN_Z_TOL = 2.0

# JSON-to-mesh picking tolerance.
# Start value for 4 mm mesh. Increase to 8 or 10 if zero elements are selected.
MESH_PICK_TOL = 6.0

# Geometry edge picking / boundary
PICK_TOL = 2.0

# Optional local lower-skin contact selection tolerance in XY.
# This is not allowed to stop the pipeline. If local selection fails,
# the static validation script falls back to the old full lower-skin top surface.
LOWERSKIN_CONTACT_XY_TOL = 5.0

# Auto-surface creation from assembly sets
EDGE_SURF_PREFIX = "SURF_EDGES__"
FACE_SURF_PREFIX = "SURF_FACES__"
SURF_OVERWRITE = True

# Combine load top surfaces
DO_COMBINE_TOP_EDGES = True
COMBINE_SURF_A   = "SURF_EDGES__SET_LOWERSKIN_EDGE_TOP"
COMBINE_SURF_B   = "SURF_EDGES__SET_SFULL_BOUNDARY_EDGE_TOP"
COMBINE_SURF_OUT = "SURF_EDGES__COMBINED_TOP_EDGES"
COMBINE_SET_OUT  = "SET_EDGES__COMBINED_TOP_EDGES"
COMBINE_OVERWRITE = True

print("=" * 72)
print("Creating_Sets5_OMEGA_MESHBASED.py")
print("CASE_DIR        :", CASE_DIR)
print("JSON            :", JSON_SFULL_SHALF_PATCHES)
print("DESIGN_HEIGHT   :", DESIGN_HEIGHT)
print("Z_TARGET_BOT    :", Z_TARGET_BOT)
print("MESH_PICK_TOL   :", MESH_PICK_TOL)
print("=" * 72)


# =========================================================================
# Helpers
# =========================================================================
def _safe_delete_set(asm, name):
    try:
        if name in asm.sets.keys():
            del asm.sets[name]
    except:
        pass

def _safe_delete_part_set(part, name):
    try:
        if name in part.sets.keys():
            del part.sets[name]
    except:
        pass

def _safe_delete_part_surface(part, name):
    try:
        if name in part.surfaces.keys():
            del part.surfaces[name]
    except:
        pass

def _safe_delete_asm_surface(asm, name):
    try:
        if name in asm.surfaces.keys():
            del asm.surfaces[name]
    except:
        pass

def _edge_mid(edge):
    try:
        return edge.pointOn[0]
    except:
        return None

def _face_point(face):
    try:
        return face.pointOn[0]
    except:
        return None

def _face_normal(face, pt):
    try:
        return face.getNormal(pt)
    except:
        return None

def _rep_face_normal_points_up(face_obj):
    p = _face_point(face_obj)
    n = _face_normal(face_obj, p)
    if n is None:
        return True
    return (n[2] > 0.0)

def _face_bbox_z(face_obj):
    try:
        bb = face_obj.getBoundingBox()
        return bb['low'][2], bb['high'][2]
    except:
        p = _face_point(face_obj)
        if p is None:
            return None, None
        return p[2], p[2]

def _is_horizontal_face(face_obj):
    p = _face_point(face_obj)
    if p is None:
        return (False, None)
    n = _face_normal(face_obj, p)
    if n is None:
        return (False, None)
    if abs(n[2]) < NZ_HORIZ_MIN:
        return (False, n)
    return (True, n)

def _dedupe_faces_by_index(faces):
    uniq = []
    seen = set()
    for f in faces:
        try:
            idx = int(f.index)
        except:
            idx = id(f)
        if idx in seen:
            continue
        seen.add(idx)
        uniq.append(f)
    return uniq

def _facearray_from_face_indices(inst, face_indices):
    fa = None
    for idx in face_indices:
        try:
            one = inst.faces[idx:idx+1]
        except:
            continue
        fa = one if fa is None else (fa + one)
    return fa

def _edgearray_from_edge_indices(inst, edge_indices):
    ea = None
    for idx in edge_indices:
        try:
            one = inst.edges[idx:idx+1]
        except:
            continue
        ea = one if ea is None else (ea + one)
    return ea

def _is_free_edge(edge):
    try:
        fs = edge.getFaces()
        if fs is None:
            return True
        return (len(fs) == 1)
    except:
        return True

def _collect_candidate_edge_midpoints(inst, only_free=True, z_target=None, z_tol=None):
    out = []
    for e in inst.edges:
        if only_free and (not _is_free_edge(e)):
            continue
        p = _edge_mid(e)
        if p is None:
            continue
        if (z_target is not None) and (z_tol is not None):
            if abs(p[2] - z_target) > z_tol:
                continue
        try:
            idx = int(e.index)
        except:
            continue
        out.append((idx, p))
    return out

def _bounds_xy(edge_mid_list):
    xs = [p[0] for (_, p) in edge_mid_list]
    ys = [p[1] for (_, p) in edge_mid_list]
    if len(xs) == 0 or len(ys) == 0:
        raise RuntimeError("Could not compute XY bounds. No candidate edges.")
    return min(xs), max(xs), min(ys), max(ys)

def _edge_key(e):
    try:
        return int(e.index)
    except:
        return id(e)

def _dedupe_edges(edges):
    out = []
    seen = set()
    for e in edges:
        k = _edge_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out

def _require_instance(asm, name):
    if name not in asm.instances.keys():
        raise RuntimeError("Missing instance '%s'. Run import+mesh first." % name)

def _require_file(path):
    if not os.path.isfile(path):
        raise RuntimeError("Missing file: %s" % path)

def _vsub(a, b):
    return (float(a[0])-float(b[0]), float(a[1])-float(b[1]), float(a[2])-float(b[2]))

def _dist_point_to_segment(pt, a, b):
    ax, ay, az = float(a[0]), float(a[1]), float(a[2])
    bx, by, bz = float(b[0]), float(b[1]), float(b[2])
    px, py, pz = float(pt[0]), float(pt[1]), float(pt[2])

    abx = bx - ax
    aby = by - ay
    abz = bz - az

    apx = px - ax
    apy = py - ay
    apz = pz - az

    ab2 = abx*abx + aby*aby + abz*abz
    if ab2 <= 1e-18:
        dx = px - ax
        dy = py - ay
        dz = pz - az
        return math.sqrt(dx*dx + dy*dy + dz*dz)

    t = (apx*abx + apy*aby + apz*abz) / ab2
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0

    qx = ax + t * abx
    qy = ay + t * aby
    qz = az + t * abz

    dx = px - qx
    dy = py - qy
    dz = pz - qz
    return math.sqrt(dx*dx + dy*dy + dz*dz)

def _elem_centroid(elem):
    try:
        nds = elem.getNodes()
    except:
        return None
    if nds is None or len(nds) == 0:
        return None

    sx = sy = sz = 0.0
    n = 0
    for nd in nds:
        c = nd.coordinates
        sx += float(c[0])
        sy += float(c[1])
        sz += float(c[2])
        n += 1
    if n == 0:
        return None
    return (sx / n, sy / n, sz / n)

def _elem_min_node_dist_to_segment(elem, a, b):
    try:
        nds = elem.getNodes()
    except:
        return 1e99
    if nds is None or len(nds) == 0:
        return 1e99

    best = 1e99
    for nd in nds:
        d = _dist_point_to_segment(nd.coordinates, a, b)
        if d < best:
            best = d
    return best

def _elems_from_labels(part, labels):
    labels = tuple(sorted(list(labels)))
    if len(labels) == 0:
        return None

    try:
        return part.elements.sequenceFromLabels(labels=labels)
    except:
        elems = None
        label_set = set(labels)
        for el in part.elements:
            try:
                lbl = int(el.label)
            except:
                continue
            if lbl in label_set:
                one = part.elements[el.index:el.index+1]
                elems = one if elems is None else (elems + one)
        return elems

def _build_mesh_region_from_json_records(part, records, label, base_pick_tol=MESH_PICK_TOL):
    selected_labels = set()

    for rec in records:
        p0 = rec.get("p0", None)
        p1 = rec.get("p1", None)
        mid = rec.get("mid", None)

        if p0 is None or p1 is None:
            continue

        seg_len = math.sqrt(
            (float(p1[0]) - float(p0[0]))**2 +
            (float(p1[1]) - float(p0[1]))**2 +
            (float(p1[2]) - float(p0[2]))**2
        )

        pick_tol = max(float(base_pick_tol), 0.35 * seg_len)

        for elem in part.elements:
            ctr = _elem_centroid(elem)
            if ctr is None:
                continue

            d_ctr = _dist_point_to_segment(ctr, p0, p1)
            d_nd  = _elem_min_node_dist_to_segment(elem, p0, p1)

            if (d_ctr <= pick_tol) or (d_nd <= 0.60 * pick_tol):
                try:
                    selected_labels.add(int(elem.label))
                except:
                    pass

    elems = _elems_from_labels(part, selected_labels)

    if elems is None or len(elems) == 0:
        raise RuntimeError("%s mesh region selection produced 0 elements. Increase MESH_PICK_TOL." % label)

    print("Mesh region:", label, "elements=", len(elems), "records=", len(records), "pick_tol=", base_pick_tol)
    return elems


# =========================================================================
# Lower_Skin upper face set + surface
# =========================================================================
def create_lowerskin_upper_set_and_surface():
    model = mdb.models[MODEL]
    asm = model.rootAssembly
    _require_instance(asm, INST_LOWERSKIN)
    instK = asm.instances[INST_LOWERSKIN]

    cand = []
    for f0 in instK.faces:
        okH, n = _is_horizontal_face(f0)
        if not okH:
            continue
        zlow, zhigh = _face_bbox_z(f0)
        if zhigh is None:
            continue
        if abs(zhigh - Z_TARGET_BOT) <= Z_TOL_FACE:
            cand.append(f0)

    if len(cand) == 0:
        raise RuntimeError("No Lower_Skin upper faces selected. Increase Z_TOL_FACE or relax NZ_HORIZ_MIN.")

    fa_list = _dedupe_faces_by_index(cand)
    idxs = []
    seen = set()
    for ff in fa_list:
        idx = int(ff.index)
        if idx in seen:
            continue
        seen.add(idx)
        idxs.append(idx)

    fa = _facearray_from_face_indices(instK, idxs)
    if fa is None or len(fa) == 0:
        raise RuntimeError("Could not build FaceArray for Lower_Skin upper faces.")

    _safe_delete_set(asm, SET_LOWERSKIN_UPPER_FACES)
    asm.Set(name=SET_LOWERSKIN_UPPER_FACES, faces=fa)

    normal_up = _rep_face_normal_points_up(fa[0])
    _safe_delete_asm_surface(asm, SURF_LOWERSKIN_TOP_SPOS)

    if normal_up:
        asm.Surface(name=SURF_LOWERSKIN_TOP_SPOS, side1Faces=fa)
    else:
        asm.Surface(name=SURF_LOWERSKIN_TOP_SPOS, side2Faces=fa)

    print("Created:", SET_LOWERSKIN_UPPER_FACES, "faces=", len(fa))
    print("Created ASM surface:", SURF_LOWERSKIN_TOP_SPOS, "faces=", len(fa))


# =========================================================================
# S_full bottom flange underside faces set + surface
# =========================================================================
def create_sfull_bottom_flange_lower_set_and_surface():
    model = mdb.models[MODEL]
    asm = model.rootAssembly
    _require_instance(asm, INST_SFULL)
    instS = asm.instances[INST_SFULL]

    cand = []
    for f0 in instS.faces:
        okH, n = _is_horizontal_face(f0)
        if not okH:
            continue
        zlow, zhigh = _face_bbox_z(f0)
        if zlow is None:
            continue
        if abs(zlow - Z_TARGET_BOT) <= Z_TOL_FACE:
            cand.append(f0)

    if len(cand) == 0:
        raise RuntimeError("No S_full bottom flange faces selected. Increase Z_TOL_FACE or relax NZ_HORIZ_MIN.")

    fa_list = _dedupe_faces_by_index(cand)
    idxs = []
    seen = set()
    for ff in fa_list:
        idx = int(ff.index)
        if idx in seen:
            continue
        seen.add(idx)
        idxs.append(idx)

    fa = _facearray_from_face_indices(instS, idxs)
    if fa is None or len(fa) == 0:
        raise RuntimeError("Could not build FaceArray for S_full bottom flange faces.")

    _safe_delete_set(asm, SET_SFULL_BOT_FLANGE_LOWER_FACES)
    asm.Set(name=SET_SFULL_BOT_FLANGE_LOWER_FACES, faces=fa)

    normal_up = _rep_face_normal_points_up(fa[0])
    _safe_delete_asm_surface(asm, SURF_SFULL_BOT_FLANGE_SNEG)

    if normal_up:
        asm.Surface(name=SURF_SFULL_BOT_FLANGE_SNEG, side2Faces=fa)
    else:
        asm.Surface(name=SURF_SFULL_BOT_FLANGE_SNEG, side1Faces=fa)

    print("Created:", SET_SFULL_BOT_FLANGE_LOWER_FACES, "faces=", len(fa))
    print("Created ASM surface:", SURF_SFULL_BOT_FLANGE_SNEG, "faces=", len(fa))


# =========================================================================
# S_half_patches lower contact faces to Lower_Skin
# =========================================================================
def create_shalf_patches_lower_contact_surfaces():
    model = mdb.models[MODEL]
    asm = model.rootAssembly
    _require_instance(asm, INST_SHALF_PATCHES)
    instHP = asm.instances[INST_SHALF_PATCHES]

    cand = []
    for f0 in instHP.faces:
        okH, n = _is_horizontal_face(f0)
        if not okH:
            continue
        zlow, zhigh = _face_bbox_z(f0)
        if zlow is None:
            continue

        # Select faces lying on/near the skin contact plane.
        if abs(zlow - Z_TARGET_BOT) <= Z_TOL_FACE or abs(zhigh - Z_TARGET_BOT) <= Z_TOL_FACE:
            cand.append(f0)

    if len(cand) == 0:
        raise RuntimeError("No S_half_patches lower contact faces selected. Increase Z_TOL_FACE or relax NZ_HORIZ_MIN.")

    fa_list = _dedupe_faces_by_index(cand)
    idxs = []
    seen = set()
    for ff in fa_list:
        idx = int(ff.index)
        if idx in seen:
            continue
        seen.add(idx)
        idxs.append(idx)

    fa = _facearray_from_face_indices(instHP, idxs)
    if fa is None or len(fa) == 0:
        raise RuntimeError("Could not build FaceArray for S_half_patches lower contact faces.")

    _safe_delete_set(asm, SET_SHALF_PATCHES_LOWER_FACES)
    asm.Set(name=SET_SHALF_PATCHES_LOWER_FACES, faces=fa)

    _safe_delete_asm_surface(asm, SURF_SHALF_PATCHES_LOWER_SNEG)
    _safe_delete_asm_surface(asm, SURF_SHALF_PATCHES_LOWER_SPOS)

    normal_up = _rep_face_normal_points_up(fa[0])

    if normal_up:
        asm.Surface(name=SURF_SHALF_PATCHES_LOWER_SPOS, side1Faces=fa)
        asm.Surface(name=SURF_SHALF_PATCHES_LOWER_SNEG, side2Faces=fa)
    else:
        asm.Surface(name=SURF_SHALF_PATCHES_LOWER_SPOS, side2Faces=fa)
        asm.Surface(name=SURF_SHALF_PATCHES_LOWER_SNEG, side1Faces=fa)

    print("Created:", SET_SHALF_PATCHES_LOWER_FACES, "faces=", len(fa))
    print("Created ASM surfaces:", SURF_SHALF_PATCHES_LOWER_SNEG, SURF_SHALF_PATCHES_LOWER_SPOS)



# =========================================================================
# Optional local lower-skin contact surfaces for cleaner tie definitions
# =========================================================================
def _bbox_xy_from_face(face_obj, tol=0.0):
    try:
        bb = face_obj.getBoundingBox()
        return (
            float(bb['low'][0]) - tol,
            float(bb['high'][0]) + tol,
            float(bb['low'][1]) - tol,
            float(bb['high'][1]) + tol,
        )
    except:
        p = _face_point(face_obj)
        if p is None:
            return None
        return (
            float(p[0]) - tol,
            float(p[0]) + tol,
            float(p[1]) - tol,
            float(p[1]) + tol,
        )


def _xy_boxes_overlap(a, b):
    if a is None or b is None:
        return False
    ax0, ax1, ay0, ay1 = a
    bx0, bx1, by0, by1 = b
    if ax1 < bx0: return False
    if bx1 < ax0: return False
    if ay1 < by0: return False
    if by1 < ay0: return False
    return True


def _faces_from_asm_set(asm, set_name):
    if set_name not in asm.sets.keys():
        print("WARNING: assembly set not found for local contact:", set_name)
        return []
    try:
        return list(asm.sets[set_name].faces)
    except:
        return []


def _create_lowerskin_local_contact_surface(target_set_name, local_set_name, local_surface_name, label):
    """
    Select lower-skin upper faces whose XY bounding boxes overlap the target
    contact faces. This is intentionally non-fatal. If no local faces are
    found, the static script will fall back to SURF_LOWERSKIN_TOP_SPOS.
    """
    model = mdb.models[MODEL]
    asm = model.rootAssembly

    lower_faces = _faces_from_asm_set(asm, SET_LOWERSKIN_UPPER_FACES)
    target_faces = _faces_from_asm_set(asm, target_set_name)

    print("")
    print("Optional local lower-skin contact selection:", label)
    print("  lower_faces :", len(lower_faces))
    print("  target_faces:", len(target_faces))
    print("  xy_tol      :", LOWERSKIN_CONTACT_XY_TOL)

    if len(lower_faces) == 0 or len(target_faces) == 0:
        print("WARNING: local contact selection skipped for", label)
        return False

    target_boxes = []
    for f in target_faces:
        b = _bbox_xy_from_face(f, LOWERSKIN_CONTACT_XY_TOL)
        if b is not None:
            target_boxes.append(b)

    selected = []
    seen = set()
    for lf in lower_faces:
        lb = _bbox_xy_from_face(lf, 0.0)
        if lb is None:
            continue
        hit = False
        for tb in target_boxes:
            if _xy_boxes_overlap(lb, tb):
                hit = True
                break
        if hit:
            try:
                idx = int(lf.index)
            except:
                idx = id(lf)
            if idx not in seen:
                seen.add(idx)
                selected.append(lf)

    print("  selected lower faces:", len(selected))

    if len(selected) == 0:
        print("WARNING: %s local lower-skin contact selection produced 0 faces." % label)
        print("WARNING: The static validation script will fall back to SURF_LOWERSKIN_TOP_SPOS.")
        return False

    # Build FaceArray from selected assembly faces using their indices on Lower_Skin instance.
    idxs = []
    for f in selected:
        try:
            idxs.append(int(f.index))
        except:
            pass

    if len(idxs) == 0:
        print("WARNING: %s local lower-skin contact selection has no valid face indices." % label)
        return False

    instK = asm.instances[INST_LOWERSKIN]
    fa = _facearray_from_face_indices(instK, idxs)
    if fa is None or len(fa) == 0:
        print("WARNING: Could not build local lower-skin FaceArray for", label)
        return False

    _safe_delete_set(asm, local_set_name)
    _safe_delete_asm_surface(asm, local_surface_name)

    asm.Set(name=local_set_name, faces=fa)

    normal_up = _rep_face_normal_points_up(fa[0])
    if normal_up:
        asm.Surface(name=local_surface_name, side1Faces=fa)
    else:
        asm.Surface(name=local_surface_name, side2Faces=fa)

    print("Created optional local lower-skin set:", local_set_name, "faces=", len(fa))
    print("Created optional local lower-skin surface:", local_surface_name)
    return True


def create_lowerskin_local_contact_surfaces():
    """
    Optional improvement. It must never stop the pipeline.
    If it fails, 04_static_combined_validation_omega.py will use the old
    full lower-skin top surface as fallback.
    """
    try:
        _create_lowerskin_local_contact_surface(
            SET_SFULL_BOT_FLANGE_LOWER_FACES,
            SET_LOWERSKIN_SFULL_CONTACT_FACES,
            SURF_LOWERSKIN_SFULL_CONTACT_SPOS,
            "LowerSkin-Sfull"
        )
    except Exception as e:
        print("WARNING: LowerSkin-Sfull local contact surface failed:", str(e))
        print("WARNING: Falling back to SURF_LOWERSKIN_TOP_SPOS later.")

    try:
        _create_lowerskin_local_contact_surface(
            SET_SHALF_PATCHES_LOWER_FACES,
            SET_LOWERSKIN_SHALF_PATCHES_CONTACT_FACES,
            SURF_LOWERSKIN_SHALF_PATCHES_CONTACT_SPOS,
            "LowerSkin-Shalf_patches"
        )
    except Exception as e:
        print("WARNING: LowerSkin-Shalf_patches local contact surface failed:", str(e))
        print("WARNING: Falling back to SURF_LOWERSKIN_TOP_SPOS later.")



# =========================================================================
# Lower_Skin perimeter edge sets
# =========================================================================
def create_lowerskin_perimeter_edge_sets():
    model = mdb.models[MODEL]
    asm = model.rootAssembly
    _require_instance(asm, INST_LOWERSKIN)
    instK = asm.instances[INST_LOWERSKIN]

    cand = _collect_candidate_edge_midpoints(
        instK,
        only_free=ONLY_FREE_EDGES,
        z_target=Z_TARGET_BOT,
        z_tol=LOWERSKIN_Z_TOL
    )

    if len(cand) == 0:
        raise RuntimeError("No candidate Lower_Skin edges found. Increase LOWERSKIN_Z_TOL or disable ONLY_FREE_EDGES.")

    xmin, xmax, ymin, ymax = _bounds_xy(cand)

    left_idx, right_idx, top_idx, bottom_idx = [], [], [], []
    for (idx, p) in cand:
        if abs(p[0] - xmin) <= BND_TOL_XY:
            left_idx.append(idx)
        if abs(p[0] - xmax) <= BND_TOL_XY:
            right_idx.append(idx)
        if abs(p[1] - ymax) <= BND_TOL_XY:
            top_idx.append(idx)
        if abs(p[1] - ymin) <= BND_TOL_XY:
            bottom_idx.append(idx)

    def _mk(name, idxs):
        _safe_delete_set(asm, name)
        ea = _edgearray_from_edge_indices(instK, sorted(list(set(idxs))))
        if ea is None or len(ea) == 0:
            print("WARN:", name, "created 0 edges. Increase BND_TOL_XY.")
            return
        asm.Set(name=name, edges=ea)
        print("Created:", name, "edges=", len(ea))

    _mk(SET_LOWERSKIN_EDGE_LEFT, left_idx)
    _mk(SET_LOWERSKIN_EDGE_RIGHT, right_idx)
    _mk(SET_LOWERSKIN_EDGE_TOP, top_idx)
    _mk(SET_LOWERSKIN_EDGE_BOTTOM, bottom_idx)

    print("--- Lower_Skin bounds --- xmin=%.3f xmax=%.3f ymin=%.3f ymax=%.3f" % (xmin, xmax, ymin, ymax))


# =========================================================================
# S_full boundary edge sets
# =========================================================================
def create_sfull_boundary_edge_sets():
    model = mdb.models[MODEL]
    asm = model.rootAssembly
    _require_instance(asm, INST_SFULL)
    instS = asm.instances[INST_SFULL]

    cand = _collect_candidate_edge_midpoints(instS, only_free=ONLY_FREE_EDGES)
    if len(cand) == 0:
        raise RuntimeError("No candidate S_full edges found. Disable ONLY_FREE_EDGES if needed.")

    xmin, xmax, ymin, ymax = _bounds_xy(cand)

    left_idx, right_idx, top_idx, bottom_idx = [], [], [], []
    for (idx, p) in cand:
        if abs(p[0] - xmin) <= BND_TOL_XY:
            left_idx.append(idx)
        if abs(p[0] - xmax) <= BND_TOL_XY:
            right_idx.append(idx)
        if abs(p[1] - ymax) <= BND_TOL_XY:
            top_idx.append(idx)
        if abs(p[1] - ymin) <= BND_TOL_XY:
            bottom_idx.append(idx)

    def _mk(name, idxs):
        _safe_delete_set(asm, name)
        ea = _edgearray_from_edge_indices(instS, sorted(list(set(idxs))))
        if ea is None or len(ea) == 0:
            print("WARN:", name, "created 0 edges. Increase BND_TOL_XY.")
            return
        asm.Set(name=name, edges=ea)
        print("Created:", name, "edges=", len(ea))

    _mk(SET_SFULL_BND_EDGE_LEFT, left_idx)
    _mk(SET_SFULL_BND_EDGE_RIGHT, right_idx)
    _mk(SET_SFULL_BND_EDGE_TOP, top_idx)
    _mk(SET_SFULL_BND_EDGE_BOTTOM, bottom_idx)

    print("--- S_full bounds --- xmin=%.3f xmax=%.3f ymin=%.3f ymax=%.3f" % (xmin, xmax, ymin, ymax))


# =========================================================================
# Mesh-based JSON Interface: S_full <-> S_half_patches
# =========================================================================
def create_sfull_shalf_patches_mesh_interface_from_json(json_path):
    model = mdb.models[MODEL]
    asm = model.rootAssembly

    _require_instance(asm, INST_SFULL)
    _require_instance(asm, INST_SHALF_PATCHES)
    _require_file(json_path)

    partS  = model.parts[PART_SFULL]
    partHP = model.parts[PART_SHALF_PATCHES]

    if len(partS.elements) == 0:
        raise RuntimeError("S_full has 0 elements. Run mesh script before this script.")
    if len(partHP.elements) == 0:
        raise RuntimeError("S_half_patches has 0 elements. Run mesh script before this script.")

    f = codecs.open(json_path, 'r', 'utf-8-sig')
    try:
        j = json.load(f)
    finally:
        f.close()

    sfull_recs = j.get("S_full_touch", {}).get("edges", [])
    hp_recs    = j.get("S_half_patches_touch", {}).get("edges", [])

    if len(sfull_recs) == 0 or len(hp_recs) == 0:
        raise RuntimeError("JSON has 0 edges in S_full_touch or S_half_patches_touch.")

    elemsS = _build_mesh_region_from_json_records(
        partS,
        sfull_recs,
        "S_full <-> S_half_patches"
    )

    elemsHP = _build_mesh_region_from_json_records(
        partHP,
        hp_recs,
        "S_half_patches <-> S_full"
    )

    _safe_delete_part_set(partS, SET_SFULL_SHALF_PATCH_IFACE_MESH_ELEMS)
    _safe_delete_part_surface(partS, SURF_SFULL_SHALF_PATCH_IFACE_MESH_S1)
    _safe_delete_part_surface(partS, SURF_SFULL_SHALF_PATCH_IFACE_MESH_S2)

    _safe_delete_part_set(partHP, SET_SHALF_PATCHES_SFULL_IFACE_MESH_ELEMS)
    _safe_delete_part_surface(partHP, SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S1)
    _safe_delete_part_surface(partHP, SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S2)

    partS.Set(name=SET_SFULL_SHALF_PATCH_IFACE_MESH_ELEMS, elements=elemsS)
    partS.Surface(name=SURF_SFULL_SHALF_PATCH_IFACE_MESH_S1, side1Elements=elemsS)
    partS.Surface(name=SURF_SFULL_SHALF_PATCH_IFACE_MESH_S2, side2Elements=elemsS)

    partHP.Set(name=SET_SHALF_PATCHES_SFULL_IFACE_MESH_ELEMS, elements=elemsHP)
    partHP.Surface(name=SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S1, side1Elements=elemsHP)
    partHP.Surface(name=SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S2, side2Elements=elemsHP)

    print("Created PART mesh set/surfaces:")
    print("  ", PART_SFULL, SET_SFULL_SHALF_PATCH_IFACE_MESH_ELEMS, len(elemsS))
    print("  ", PART_SFULL, SURF_SFULL_SHALF_PATCH_IFACE_MESH_S1)
    print("  ", PART_SFULL, SURF_SFULL_SHALF_PATCH_IFACE_MESH_S2)
    print("  ", PART_SHALF_PATCHES, SET_SHALF_PATCHES_SFULL_IFACE_MESH_ELEMS, len(elemsHP))
    print("  ", PART_SHALF_PATCHES, SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S1)
    print("  ", PART_SHALF_PATCHES, SURF_SHALF_PATCHES_SFULL_IFACE_MESH_S2)


# =========================================================================
# Convert assembly sets to assembly surfaces
# =========================================================================
def _sanitize(name):
    bad = [' ', '-', '.', ':', '/', '\\', '[', ']', '(', ')', '{', '}', ',']
    out = name
    for b in bad:
        out = out.replace(b, '_')
    return out[:70]

def _has_edges(set_obj):
    try:
        return (set_obj.edges is not None) and (len(set_obj.edges) > 0)
    except:
        return False

def _has_faces(set_obj):
    try:
        return (set_obj.faces is not None) and (len(set_obj.faces) > 0)
    except:
        return False

def create_surfaces_from_all_assembly_sets():
    model = mdb.models[MODEL]
    asm = model.rootAssembly

    n_edge = 0
    n_face = 0
    n_skip = 0

    set_names = asm.sets.keys()
    set_names.sort()

    for sname in set_names:
        s = asm.sets[sname]
        made_any = False

        if _has_edges(s):
            surf_name = EDGE_SURF_PREFIX + _sanitize(sname)
            if SURF_OVERWRITE:
                _safe_delete_asm_surface(asm, surf_name)
            try:
                asm.Surface(name=surf_name, side1Edges=s.edges)
                n_edge += 1
                made_any = True
            except Exception as e:
                print("WARN: failed edge surface for set:", sname, "->", str(e))

        if _has_faces(s):
            surf_name = FACE_SURF_PREFIX + _sanitize(sname)
            if SURF_OVERWRITE:
                _safe_delete_asm_surface(asm, surf_name)
            try:
                asm.Surface(name=surf_name, side1Faces=s.faces)
                n_face += 1
                made_any = True
            except Exception as e:
                print("WARN: failed face surface for set:", sname, "->", str(e))

        if not made_any:
            n_skip += 1

    print("---- DONE: surfaces created from assembly sets ----")
    print("Edge-surfaces created :", n_edge)
    print("Face-surfaces created :", n_face)
    print("Sets skipped          :", n_skip)


# =========================================================================
# Combine two EDGE-based assembly surfaces
# =========================================================================
def _get_edge_sequence_from_surface(surf):
    try:
        ed = surf.side1Edges
        if ed and len(ed) > 0:
            return ed
    except:
        pass
    try:
        ed = surf.side2Edges
        if ed and len(ed) > 0:
            return ed
    except:
        pass
    try:
        ed = surf.edges
        if ed and len(ed) > 0:
            return ed
    except:
        pass
    return None

def combine_two_edge_surfaces_and_make_set(surf_a, surf_b, surf_out, set_out):
    model = mdb.models[MODEL]
    asm = model.rootAssembly

    if surf_a not in asm.surfaces.keys():
        raise RuntimeError("Surface not found: %s" % surf_a)
    if surf_b not in asm.surfaces.keys():
        raise RuntimeError("Surface not found: %s" % surf_b)

    sa = asm.surfaces[surf_a]
    sb = asm.surfaces[surf_b]

    ea = _get_edge_sequence_from_surface(sa)
    eb = _get_edge_sequence_from_surface(sb)

    if ea is None or len(ea) == 0:
        raise RuntimeError("No edges found on surface: %s" % surf_a)
    if eb is None or len(eb) == 0:
        raise RuntimeError("No edges found on surface: %s" % surf_b)

    if COMBINE_OVERWRITE:
        _safe_delete_asm_surface(asm, surf_out)
        _safe_delete_set(asm, set_out)

    try:
        eall = ea + eb
        asm.Surface(name=surf_out, side1Edges=eall)
        asm.Set(name=set_out, edges=eall)
        print("Created combined surface+set:", surf_out, set_out, "edges=", len(eall))
        return
    except Exception as e:
        print("WARN: combine mode failed:", str(e))

    asm.Surface(name=surf_out, side1Edges=(ea, eb))
    asm.Set(name=set_out, edges=(ea, eb))
    print("Created combined surface+set fallback:", surf_out, set_out)


# =========================================================================
# RUN ALL
# =========================================================================
def main():
    model = mdb.models[MODEL]
    asm = model.rootAssembly

    _require_instance(asm, INST_SFULL)
    _require_instance(asm, INST_SHALF_PATCHES)
    _require_instance(asm, INST_LOWERSKIN)
    _require_file(JSON_SFULL_SHALF_PATCHES)

    print("CASE_DIR:", CASE_DIR)
    print("JSON_SFULL_SHALF_PATCHES:", JSON_SFULL_SHALF_PATCHES)

    # Broad lower skin contacts
    create_lowerskin_upper_set_and_surface()
    create_sfull_bottom_flange_lower_set_and_surface()
    create_shalf_patches_lower_contact_surfaces()

    # Optional local lower-skin surfaces; non-fatal fallback if selection fails
    create_lowerskin_local_contact_surfaces()

    # Boundary edges for BC/load
    create_lowerskin_perimeter_edge_sets()
    create_sfull_boundary_edge_sets()

    # Mesh-based interaction region from JSON
    create_sfull_shalf_patches_mesh_interface_from_json(JSON_SFULL_SHALF_PATCHES)

    # Create edge/face assembly surfaces from assembly sets for BC/load coupling
    create_surfaces_from_all_assembly_sets()

    if DO_COMBINE_TOP_EDGES:
        combine_two_edge_surfaces_and_make_set(
            COMBINE_SURF_A,
            COMBINE_SURF_B,
            COMBINE_SURF_OUT,
            COMBINE_SET_OUT
        )

    print("")
    print("=" * 72)
    print("DONE: Creating_Sets5_OMEGA_MESHBASED")
    print("=" * 72)


if __name__ == "__main__":
    main()
