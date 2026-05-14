# -*- coding: mbcs -*-
# Abaqus/CAE Python 2.7
#
# Mesh_testing.py
#
# Robust shell meshing for:
#   S_full
#   S_half_patches
#   Lower_Skin
#
# Uses the same strategy as manual successful meshing:
#   AutoRepair → Edge-based seeding → Mesh

from abaqus import *
from abaqusConstants import *
import mesh

# ============================================================
# USER SETTINGS
# ============================================================

MODEL_NAME = 'Model-1'

PART_SFULL     = 'S_full'
PART_SHALF_PATCHES = 'S_half_patches'
PART_LOWSKIN   = 'Lower_Skin'

# ------------------------------------------------------------
# EDGE BASED MESH SIZE (CHANGE ANYTIME)
# ------------------------------------------------------------
EDGE_SIZE_SFULL     = 4.0
EDGE_SIZE_SHALF_PATCHES = 4.0
EDGE_SIZE_LOWSKIN   = 4.0

DEV_FACTOR = 0.1
MIN_SIZE_FACTOR = 0.5

STOP_ON_ZERO_ELEMS = True

# ============================================================


def _stop_meshing(part_label, detail):

    raise RuntimeError(
        "STOP: Meshing failed for '%s'.\n"
        "Details: %s\n"
        "Comment: Geometry may be too complex or invalid.\n"
        "Try reducing Voronoi nodes or adjusting mesh size."
        % (part_label, detail)
    )


def _safe_delete_mesh_and_seeds(p):

    try:
        p.deleteMesh()
    except:
        pass

    try:
        p.deleteSeeds()
    except:
        pass


def _autorepair_part(p):

    try:
        print("Running AutoRepair on:", p.name)
        p.AutoRepair()
    except:
        print("AutoRepair skipped:", p.name)


def _set_shell_elements(p):

    try:

        region = (p.faces,)

        elemType1 = mesh.ElemType(
            elemCode=S4R,
            elemLibrary=STANDARD
        )

        elemType2 = mesh.ElemType(
            elemCode=S3,
            elemLibrary=STANDARD
        )

        p.setElementType(
            regions=region,
            elemTypes=(elemType1, elemType2)
        )

    except Exception as e:

        print("WARNING: setElementType failed:", str(e))


def _seed_edges(p, size):

    edges = p.edges[:]

    p.seedEdgeBySize(
        edges=edges,
        size=size,
        deviationFactor=DEV_FACTOR,
        constraint=FIXED
    )


def _mesh_part_or_stop(p, edge_size, label):

    try:

        print("\n--------------------------------")
        print("Meshing part:", label)
        print("Edge size   :", edge_size)

        _safe_delete_mesh_and_seeds(p)

        # repair geometry
        _autorepair_part(p)

        # seed edges
        _seed_edges(p, edge_size)

        # shell element types
        _set_shell_elements(p)

        # generate mesh
        p.generateMesh()

        ne = len(p.elements)
        nn = len(p.nodes)

        print(label, "meshed successfully")
        print("Elements:", ne)
        print("Nodes   :", nn)

        if STOP_ON_ZERO_ELEMS and ne == 0:

            _stop_meshing(label, "Meshing produced 0 elements.")

        return ne, nn

    except Exception as e:

        _stop_meshing(label, str(e))


# ============================================================
# MAIN
# ============================================================

mdb_model = mdb.models[MODEL_NAME]

# Ensure parts exist
for pn in (PART_SFULL, PART_SHALF_PATCHES, PART_LOWSKIN):

    if pn not in mdb_model.parts.keys():

        raise RuntimeError(
            "Missing part '%s'. Run STEP import script first." % pn
        )


p_sfull          = mdb_model.parts[PART_SFULL]
p_shalf_patches  = mdb_model.parts[PART_SHALF_PATCHES]
p_lowskin        = mdb_model.parts[PART_LOWSKIN]


print("\n========================================")
print("STARTING AUTOMATIC MESHING")
print("========================================")


# ------------------------------------------------------------
# MESH PARTS
# ------------------------------------------------------------

_mesh_part_or_stop(
    p_sfull,
    EDGE_SIZE_SFULL,
    "S_full"
)

_mesh_part_or_stop(
    p_shalf_patches,
    EDGE_SIZE_SHALF_PATCHES,
    "S_half_patches"
)

_mesh_part_or_stop(
    p_lowskin,
    EDGE_SIZE_LOWSKIN,
    "Lower_Skin"
)


print("\n========================================")
print("MESHING COMPLETED SUCCESSFULLY")
print("========================================")
print("Next step: Creating_Set5_ALLINONE.py")