# -*- coding: mbcs -*-
# Abaqus/CAE Python 2.7
#
# Import STEP parts → Convert to precise → AutoRepair → Assemble
# Omega workflow: Lower_Skin + S_full + S_half_patches

from abaqus import mdb
from abaqusConstants import *
from part import *
import os

# ============================================================
# USER SETTINGS
# ============================================================

MODEL_NAME = 'Model-1'

STEP_FILES = [
    ("Lower_Skin",       "Lower_Skin.stp"),
    ("S_full",           "S_full.stp"),
    ("S_half_patches",   "S_half_patches.stp"),
]

MERGE_SOLID_REGIONS = True
STITCH_TOL = 0.01
MAX_PRECISE_ITERS = 4

INSTANCE_SUFFIX = "-1"
RESET_ASSEMBLY_INSTANCES = True

# ============================================================


# ============================================================
# CASE DIRECTORY
# ============================================================

if 'CASE_DIR' not in globals() or not CASE_DIR:
    raise RuntimeError(
        "CASE_DIR is not defined.\n"
        "Script must be launched from RUN_ALL_PIPELINE2.py"
    )

CASE_DIR = os.path.normpath(CASE_DIR)


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def _assert_files_exist(case_path):

    missing = []

    for _, fn in STEP_FILES:

        fp = os.path.join(case_path, fn)

        if not os.path.isfile(fp):
            missing.append(fp)

    if missing:

        raise IOError(
            "Missing STEP files:\n  - " + "\n  - ".join(missing)
        )


def _safe_delete_part(model, name):

    try:
        if name in model.parts:
            del model.parts[name]
    except:
        pass


def _open_geometry(step_path):

    ext = os.path.splitext(step_path)[1].lower()

    if ext in ('.stp', '.step'):
        return mdb.openStep(step_path)

    elif ext in ('.sat', '.sab'):
        return mdb.openAcis(step_path)

    else:
        raise ValueError(
            "Unsupported geometry extension: %s" % ext
        )


# ============================================================
# IMPORT STEP PART
# ============================================================

def _import_step_as_part(model, part_name, step_path):

    _safe_delete_part(model, part_name)

    geom = _open_geometry(step_path)

    kwargs = dict(
        name=part_name,
        geometryFile=geom,
        dimensionality=THREE_D,
        type=DEFORMABLE_BODY,
        combine=True,
    )

    if MERGE_SOLID_REGIONS:
        kwargs["mergeSolidRegions"] = True

    if STITCH_TOL is not None:
        kwargs["stitchTolerance"] = float(STITCH_TOL)

    model.PartFromGeometryFile(**kwargs)


# ============================================================
# GEOMETRY REPAIR
# ============================================================

def _make_part_precise(model, part_name):

    p = model.parts[part_name]

    print("  [%s] Geometry repair start" % part_name)

    for i in range(MAX_PRECISE_ITERS):

        try:

            print("    iteration:", i + 1)

            # tighten gaps
            p.ConvertToPrecise(method=TIGHTEN_GAPS)

            try:
                p.checkGeometry()
            except:
                pass

            # recompute geometry
            p.ConvertToPrecise(method=RECOMPUTE_GEOMETRY)

            try:
                p.checkGeometry()
            except:
                pass

        except Exception as e:

            msg = str(e).lower()

            if "already precise" in msg or "already valid" in msg:
                break
            else:
                print("    warning:", str(e))

    # --------------------------------------------------------
    # AutoRepair AFTER precise conversion
    # --------------------------------------------------------

    try:

        print("    running AutoRepair")

        p.AutoRepair()

        try:
            p.checkGeometry()
        except:
            pass

    except Exception as e:

        print("    AutoRepair warning:", str(e))

    print("  [%s] Geometry repair complete" % part_name)


# ============================================================
# ASSEMBLY
# ============================================================

def _reset_assembly_instances(asm):

    if not RESET_ASSEMBLY_INSTANCES:
        return

    try:

        for inst_name in list(asm.instances.keys()):
            del asm.instances[inst_name]

    except:
        pass


def _assemble_parts(model):

    asm = model.rootAssembly

    asm.DatumCsysByDefault(CARTESIAN)

    if RESET_ASSEMBLY_INSTANCES:
        _reset_assembly_instances(asm)

    for part_name, _ in STEP_FILES:

        inst_name = part_name + INSTANCE_SUFFIX

        try:
            if inst_name in asm.instances:
                del asm.instances[inst_name]
        except:
            pass

        asm.Instance(
            name=inst_name,
            part=model.parts[part_name],
            dependent=ON
        )

    return asm


# ============================================================
# MAIN
# ============================================================

def main():

    if MODEL_NAME not in mdb.models:
        mdb.Model(name=MODEL_NAME)

    model = mdb.models[MODEL_NAME]

    case_path = CASE_DIR

    print("CASE_DIR:", case_path)

    _assert_files_exist(case_path)

    for part_name, fn in STEP_FILES:

        step_path = os.path.join(case_path, fn)

        print("\n--- Import:", part_name, "---")
        print("STEP:", step_path)

        _import_step_as_part(model, part_name, step_path)

        _make_part_precise(model, part_name)

    print("\n--- Assembly ---")

    asm = _assemble_parts(model)

    print("Instances created:")

    for k in asm.instances.keys():
        print("  -", k)

    print("\n=== DONE: import + geometry repair + assembly ===")


if __name__ == "__main__":
    main()