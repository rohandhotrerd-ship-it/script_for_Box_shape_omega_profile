# -*- coding: mbcs -*-
# Abaqus/CAE Python 2.7
#
# 06_postprocess_dat2_omega.py
#
# ------------------------------------------------------------
# WHAT THIS SCRIPT DOES
# ------------------------------------------------------------
# 1) Reads the .dat files created by script 05 from:
#       CASE_DIR/Results/Compression/
#       CASE_DIR/Results/Shear/
#       CASE_DIR/Results/Combined/
#
# 2) Extracts:
#       - total mass
#       - signed eigenvalues (mode-by-mode)
#       - lambda_1 for each load case
#
# 3) Builds:
#       - lambda1_compression
#       - lambda1_shear
#       - lambda1_combined
#
# 4) Writes:
#       - kpi_results_all.json
#       - kpi_results_all.csv
#       - kpi_summary.json
#
# 5) Keeps compatibility with the new coordinate-based workflow:
#       - reads design_vars.json
#       - supports "coords"
#       - derives Nodes from len(coords)/2
#       - Seeds is no longer used
#
# IMPORTANT:
# This script DOES NOT compute the final GA fitness.
# That is done later in evaluate_design.py.
# Here we only extract raw KPI values cleanly.
# ------------------------------------------------------------

import os
import re
import json
import csv

# ============================================================
# CASE DIRECTORY
# ============================================================
if 'CASE_DIR' not in globals() or not CASE_DIR:
    raise RuntimeError(
        "CASE_DIR is not defined.\n"
        "This script must be launched by RUN_ALL_PIPELINE3.py with CASE_DIR set."
    )

CASE_DIR = os.path.normpath(CASE_DIR)
RESULTS_DIR = os.path.join(CASE_DIR, "Results")
DESIGN_VARS_JSON = os.path.join(CASE_DIR, "design_vars.json")

CASE_FOLDERS = [
    ("Compression", os.path.join(RESULTS_DIR, "Compression")),
    ("Shear",       os.path.join(RESULTS_DIR, "Shear")),
    ("Combined",    os.path.join(RESULTS_DIR, "Combined")),
]

JSON_OUT_ALL     = os.path.join(RESULTS_DIR, "kpi_results_all.json")
CSV_OUT_ALL      = os.path.join(RESULTS_DIR, "kpi_results_all.csv")
JSON_OUT_SUMMARY = os.path.join(RESULTS_DIR, "kpi_summary.json")


# ============================================================
# HELPERS
# ============================================================
def _require_dir(path):
    if not os.path.isdir(path):
        raise RuntimeError("Required folder not found:\n%s" % path)


def _safe_float(v):
    try:
        return float(v)
    except:
        return None


def _read_text(path):
    f = open(path, 'rb')
    try:
        raw = f.read()
    finally:
        f.close()

    try:
        return raw.decode('utf-8', 'ignore')
    except:
        try:
            return raw.decode('latin-1', 'ignore')
        except:
            return str(raw)


def _write_json(path, data):
    f = open(path, 'w')
    try:
        json.dump(data, f, indent=4, sort_keys=True)
    finally:
        f.close()


def _write_csv(path, rows):
    # --------------------------------------------------------
    # CSV columns:
    # - per-case lambda_1 ... lambda_6
    # - mass
    # - positive / negative mode counts
    # --------------------------------------------------------
    fieldnames = [
        "case_name",
        "case_dir",
        "results_dir",
        "dat_file",
        "status",
        "mass",
        "lambda_1",
        "lambda_2",
        "lambda_3",
        "lambda_4",
        "lambda_5",
        "lambda_6",
        "lambda_first_positive",
        "num_positive_modes",
        "num_negative_modes",
    ]

    f = open(path, 'wb')
    try:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "case_name": row.get("case_name"),
                "case_dir": row.get("case_dir"),
                "results_dir": row.get("results_dir"),
                "dat_file": row.get("dat_file"),
                "status": row.get("status"),
                "mass": row.get("mass"),
                "lambda_1": row.get("lambda_1"),
                "lambda_2": row.get("lambda_2"),
                "lambda_3": row.get("lambda_3"),
                "lambda_4": row.get("lambda_4"),
                "lambda_5": row.get("lambda_5"),
                "lambda_6": row.get("lambda_6"),
                "lambda_first_positive": row.get("lambda_first_positive"),
                "num_positive_modes": row.get("num_positive_modes"),
                "num_negative_modes": row.get("num_negative_modes"),
            })
    finally:
        f.close()


# ============================================================
# DESIGN-VARS HANDLING
# ============================================================
def _read_design_vars():
    # --------------------------------------------------------
    # Read design_vars.json written by MASTER script.
    # Supports new coordinate-based workflow:
    #   coords + Height + Width + Thickness + stud_max
    #
    # Nodes is derived from coords length if needed.
    # Seeds is intentionally ignored because it no longer drives
    # the Voronoi geometry in the new method.
    # --------------------------------------------------------
    if not os.path.isfile(DESIGN_VARS_JSON):
        return {
            "found": False,
            "Nodes": None,
            "coords_len": None,
            "Height": None,
            "Width": None,
            "Thickness": None,
            "Thickness_skin": None,
            "Thickness_stiff": None,
            "stud_max": None,
            "omega_head_width": None,
            "omega_head_gap": None,
            "omega_bottom_flange_width": None,
            "omega_web_angle_from_vertical": None,
            "raw": None,
        }

    try:
        f = open(DESIGN_VARS_JSON, "r")
        try:
            data = json.load(f)
        finally:
            f.close()
    except Exception as e:
        return {
            "found": False,
            "read_error": str(e),
            "Nodes": None,
            "coords_len": None,
            "Height": None,
            "Width": None,
            "Thickness": None,
            "Thickness_skin": None,
            "Thickness_stiff": None,
            "stud_max": None,
            "omega_head_width": None,
            "omega_head_gap": None,
            "omega_bottom_flange_width": None,
            "omega_web_angle_from_vertical": None,
            "raw": None,
        }

    coords = data.get("coords", None)
    coords_len = None
    nodes = data.get("Nodes", None)

    if isinstance(coords, list):
        coords_len = len(coords)
        if nodes is None and (coords_len % 2) == 0:
            nodes = int(coords_len / 2)

    return {
        "found": True,
        "Nodes": nodes,
        "coords_len": coords_len,
        "Height": data.get("Height", None),
        "Width": data.get("Width", None),
        "Thickness": data.get("Thickness", None),
        "Thickness_skin": data.get("Thickness_skin", None),
        "Thickness_stiff": data.get("Thickness_stiff", None),
        "stud_max": data.get("stud_max", None),
        "omega_head_width": data.get("omega_head_width", None),
        "omega_head_gap": data.get("omega_head_gap", None),
        "omega_bottom_flange_width": data.get("omega_bottom_flange_width", None),
        "omega_web_angle_from_vertical": data.get("omega_web_angle_from_vertical", None),
        "raw": data,
    }


# ============================================================
# FILE FINDERS
# ============================================================
def _find_dat_file(results_dir):
    dat_files = []
    for name in os.listdir(results_dir):
        if name.lower().endswith(".dat"):
            dat_files.append(os.path.join(results_dir, name))

    if not dat_files:
        raise RuntimeError("No .dat file found in folder:\n%s" % results_dir)

    dat_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return dat_files[0]


# ============================================================
# PARSERS
# ============================================================
def _extract_total_mass(text):
    # --------------------------------------------------------
    # Try several common Abaqus mass line patterns.
    # --------------------------------------------------------
    patterns = [
        r'TOTAL\s+MASS\s+OF\s+MODEL\s*[:=]?\s*([+\-]?\d+(?:\.\d+)?(?:[Ee][+\-]?\d+)?)',
        r'TOTAL\s+MASS\s*[:=]?\s*([+\-]?\d+(?:\.\d+)?(?:[Ee][+\-]?\d+)?)',
        r'MASS\s+OF\s+MODEL\s*[:=]?\s*([+\-]?\d+(?:\.\d+)?(?:[Ee][+\-]?\d+)?)',
        r'THE\s+TOTAL\s+MASS\s+IS\s*[:=]?\s*([+\-]?\d+(?:\.\d+)?(?:[Ee][+\-]?\d+)?)',
    ]

    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except:
                pass

    # fallback: scan lines containing TOTAL + MASS
    for line in text.splitlines():
        up = line.upper()
        if "TOTAL" in up and "MASS" in up:
            nums = re.findall(r'[+\-]?\d+(?:\.\d+)?(?:[Ee][+\-]?\d+)?', line)
            if nums:
                try:
                    return float(nums[-1])
                except:
                    pass

    return None


def _extract_eigenvalues(text):
    # --------------------------------------------------------
    # Preserve signed eigenvalues and actual mode numbering.
    # This is important because Abaqus can produce negative
    # eigenvalues, especially in shear-type cases.
    #
    # Returns:
    #   [(mode_no, eigenvalue), ...]
    # --------------------------------------------------------
    lines = text.splitlines()
    eig_pairs = []

    capture = False
    for i in range(len(lines)):
        line = lines[i]
        up = line.upper()

        if ("EIGENVALUE OUTPUT" in up or
            "BUCKLING LOAD FACTOR" in up or
            ("MODE NO" in up and "EIGENVALUE" in up)):
            capture = True
            continue

        if capture:
            if not line.strip():
                if eig_pairs:
                    break
                else:
                    continue

            nums = re.findall(r'[+\-]?\d+(?:\.\d+)?(?:[Ee][+\-]?\d+)?', line)
            if len(nums) >= 2:
                try:
                    mode_no = int(float(nums[0]))
                    eig = float(nums[1])

                    if mode_no >= 1 and abs(eig) < 1.0e12:
                        eig_pairs.append((mode_no, eig))
                except:
                    pass
            else:
                if eig_pairs:
                    break

    # fallback pass
    if not eig_pairs:
        for line in lines:
            up = line.upper()
            if "MODE" in up and "EIGENVALUE" in up:
                nums = re.findall(r'[+\-]?\d+(?:\.\d+)?(?:[Ee][+\-]?\d+)?', line)
                if len(nums) >= 2:
                    try:
                        mode_no = int(float(nums[0]))
                        eig = float(nums[1])
                        if mode_no >= 1 and abs(eig) < 1.0e12:
                            eig_pairs.append((mode_no, eig))
                    except:
                        pass

    # Remove duplicate mode numbers, keep first occurrence
    uniq = []
    seen = set()
    for mode_no, eig in eig_pairs:
        if mode_no not in seen:
            uniq.append((mode_no, eig))
            seen.add(mode_no)

    uniq.sort(key=lambda x: x[0])
    return uniq


def _mode_map_first_six(eig_pairs):
    # --------------------------------------------------------
    # Preserve actual Abaqus mode numbers 1..6
    # --------------------------------------------------------
    out = {
        "lambda_1": None,
        "lambda_2": None,
        "lambda_3": None,
        "lambda_4": None,
        "lambda_5": None,
        "lambda_6": None,
    }

    for mode_no, eig in eig_pairs:
        key = "lambda_%d" % mode_no
        if key in out:
            out[key] = eig

    return out




def _first_positive_eigenvalue(eig_pairs):
    # --------------------------------------------------------
    # Return the first POSITIVE buckling eigenvalue in mode order.
    # This is often the most relevant forward-load buckling factor
    # for optimization when early signed modes can be negative.
    # --------------------------------------------------------
    for mode_no, eig in eig_pairs:
        try:
            v = float(eig)
        except:
            continue
        if v > 0.0:
            return v
    return None

def _count_signs(eig_pairs):
    n_pos = 0
    n_neg = 0

    for mode_no, eig in eig_pairs:
        if eig > 0.0:
            n_pos += 1
        elif eig < 0.0:
            n_neg += 1

    return n_pos, n_neg


# ============================================================
# CASE-WISE POSTPROCESS
# ============================================================
def _build_case_result(case_name, case_folder):
    _require_dir(case_folder)

    dat_path = _find_dat_file(case_folder)
    text = _read_text(dat_path)

    mass = _extract_total_mass(text)
    eig_pairs = _extract_eigenvalues(text)

    mode_map = _mode_map_first_six(eig_pairs)
    lambda_first_positive = _first_positive_eigenvalue(eig_pairs)
    n_pos, n_neg = _count_signs(eig_pairs)

    status = "success"
    if len(eig_pairs) == 0:
        status = "missing_eigenvalues"
    elif mass is None:
        status = "missing_mass"

    return {
        "case_name": case_name,
        "case_dir": CASE_DIR,
        "results_dir": case_folder,
        "dat_file": dat_path,
        "status": status,
        "mass": _safe_float(mass),

        # ----------------------------------------------------
        # lambda_1 here means: the FIRST BUCKLING EIGENVALUE
        # of this specific load case (Compression/Shear/Combined)
        # ----------------------------------------------------
        "lambda_1": _safe_float(mode_map["lambda_1"]),
        "lambda_2": _safe_float(mode_map["lambda_2"]),
        "lambda_3": _safe_float(mode_map["lambda_3"]),
        "lambda_4": _safe_float(mode_map["lambda_4"]),
        "lambda_5": _safe_float(mode_map["lambda_5"]),
        "lambda_6": _safe_float(mode_map["lambda_6"]),
        "lambda_first_positive": _safe_float(lambda_first_positive),

        "num_positive_modes": n_pos,
        "num_negative_modes": n_neg,

        "all_modes": [{"mode": m, "eigenvalue": ev} for (m, ev) in eig_pairs],
    }


# ============================================================
# SUMMARY BUILDING
# ============================================================
def _build_summary(case_results, design_info):
    # --------------------------------------------------------
    # Build one compact summary JSON used later by evaluate_design.py
    # --------------------------------------------------------
    by_name = {}
    masses = []

    for r in case_results:
        by_name[r["case_name"]] = {
            "status": r.get("status"),
            "mass": r.get("mass"),

            "lambda_1": r.get("lambda_1"),
            "lambda_2": r.get("lambda_2"),
            "lambda_3": r.get("lambda_3"),
            "lambda_4": r.get("lambda_4"),
            "lambda_5": r.get("lambda_5"),
            "lambda_6": r.get("lambda_6"),
            "lambda_first_positive": r.get("lambda_first_positive"),

            "num_positive_modes": r.get("num_positive_modes"),
            "num_negative_modes": r.get("num_negative_modes"),
            "dat_file": r.get("dat_file"),
        }

        if r.get("mass") is not None:
            masses.append(r.get("mass"))

    unique_masses = []
    for m in masses:
        found = False
        for um in unique_masses:
            if abs(m - um) <= 1.0e-9:
                found = True
                break
        if not found:
            unique_masses.append(m)

    summary = {
        "case_dir": CASE_DIR,
        "results_dir": RESULTS_DIR,

        # ----------------------------------------------------
        # Echo design input information for traceability
        # ----------------------------------------------------
        "design_info": {
            "design_vars_found": design_info.get("found", False),
            "Nodes": design_info.get("Nodes", None),
            "coords_len": design_info.get("coords_len", None),
            "Height": design_info.get("Height", None),
            "Width": design_info.get("Width", None),
            "Thickness": design_info.get("Thickness", None),
            "Thickness_skin": design_info.get("Thickness_skin", None),
            "Thickness_stiff": design_info.get("Thickness_stiff", None),
            "stud_max": design_info.get("stud_max", None),
            "omega_head_width": design_info.get("omega_head_width", None),
            "omega_head_gap": design_info.get("omega_head_gap", None),
            "omega_bottom_flange_width": design_info.get("omega_bottom_flange_width", None),
            "omega_web_angle_from_vertical": design_info.get("omega_web_angle_from_vertical", None),
        },

        "cases": by_name,
        "mass_consistency": {
            "all_equal": len(unique_masses) <= 1,
            "unique_mass_values": unique_masses,
        }
    }

    # --------------------------------------------------------
    # Expose the first eigenvalue of each load case at top level.
    # evaluate_design_omega.py later uses lambda_first_positive_combined
    # as the GA fitness-driving buckling value. Compression and shear values
    # are kept for logging/debugging only.
    # --------------------------------------------------------
    comp = by_name.get("Compression", {})
    shear = by_name.get("Shear", {})
    comb = by_name.get("Combined", {})

    summary["lambda1_compression"] = comp.get("lambda_1")
    summary["lambda1_shear"] = shear.get("lambda_1")
    summary["lambda1_combined"] = comb.get("lambda_1")

    summary["lambda_first_positive_compression"] = comp.get("lambda_first_positive")
    summary["lambda_first_positive_shear"] = shear.get("lambda_first_positive")
    summary["lambda_first_positive_combined"] = comb.get("lambda_first_positive")

    # --------------------------------------------------------
    # Keep these fields for compatibility with earlier scripts.
    # They are NOT the final paper-style GA fitness.
    # --------------------------------------------------------
    summary["fitness_compression"] = comp.get("lambda_1")
    summary["fitness_shear"] = shear.get("lambda_1")
    summary["fitness_combined"] = comb.get("lambda_1")

    vals = [
        summary["fitness_compression"],
        summary["fitness_shear"],
        summary["fitness_combined"]
    ]
    vals = [v for v in vals if v is not None]

    if vals:
        summary["fitness_mean_all_cases"] = sum(vals) / float(len(vals))
    else:
        summary["fitness_mean_all_cases"] = None

    return summary


# ============================================================
# MAIN
# ============================================================
def main():
    _require_dir(RESULTS_DIR)

    # --------------------------------------------------------
    # Read design_vars.json for traceability and for coordinate-
    # based workflow support.
    # --------------------------------------------------------
    design_info = _read_design_vars()

    print("\n===================================================")
    print("POSTPROCESSING STARTED")
    print("CASE_DIR :", CASE_DIR)
    print("RESULTS  :", RESULTS_DIR)
    print("===================================================\n")

    print("Design vars info:")
    print("  found      :", design_info.get("found"))
    print("  Nodes      :", design_info.get("Nodes"))
    print("  coords_len :", design_info.get("coords_len"))
    print("  Height     :", design_info.get("Height"))
    print("  Width      :", design_info.get("Width"))
    print("  Thickness      :", design_info.get("Thickness"))
    print("  Thickness_skin :", design_info.get("Thickness_skin"))
    print("  Thickness_stiff:", design_info.get("Thickness_stiff"))
    print("  stud_max       :", design_info.get("stud_max"))
    print("  omega_head_width             :", design_info.get("omega_head_width"))
    print("  omega_head_gap               :", design_info.get("omega_head_gap"))
    print("  omega_bottom_flange_width    :", design_info.get("omega_bottom_flange_width"))
    print("  omega_web_angle_from_vertical:", design_info.get("omega_web_angle_from_vertical"))

    case_results = []
    for case_name, case_folder in CASE_FOLDERS:
        print("\nProcessing case:", case_name)
        print("Folder         :", case_folder)

        result = _build_case_result(case_name, case_folder)
        case_results.append(result)

        print("DAT FILE       :", result["dat_file"])
        print("STATUS         :", result["status"])
        print("MASS           :", result["mass"])
        print("LAMBDA_1       :", result["lambda_1"])
        print("LAMBDA_POS_1ST :", result["lambda_first_positive"])
        print("POS MODES      :", result["num_positive_modes"])
        print("NEG MODES      :", result["num_negative_modes"])

    summary = _build_summary(case_results, design_info)

    out_all = {
        "case_dir": CASE_DIR,
        "results_dir": RESULTS_DIR,
        "design_info": design_info,
        "num_cases": len(case_results),
        "case_results": case_results,
        "summary": summary,
    }

    _write_json(JSON_OUT_ALL, out_all)
    _write_csv(CSV_OUT_ALL, case_results)
    _write_json(JSON_OUT_SUMMARY, summary)

    print("\n===================================================")
    print("POSTPROCESSING COMPLETED")
    print("CASE_DIR        :", CASE_DIR)
    print("JSON OUT (ALL)  :", JSON_OUT_ALL)
    print("CSV  OUT (ALL)  :", CSV_OUT_ALL)
    print("JSON OUT SUMMARY:", JSON_OUT_SUMMARY)
    print("Cases processed :", len(case_results))
    for r in case_results:
        print("  - %-12s status=%s lambda_1=%s lambda_first_positive=%s mass=%s" % (
            r["case_name"], r["status"], r["lambda_1"], r.get("lambda_first_positive"), r["mass"]
        ))
    print("===================================================\n")


main()
