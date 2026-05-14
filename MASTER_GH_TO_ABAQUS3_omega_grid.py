# -*- coding: utf-8 -*-
"""
ONE-STAGE ROW-COLUMN GRID VERSION.
- Topology is fixed in Grasshopper.
- No two-stage topology GA is used.
- coords are kept as an empty compatibility field only.

MASTER_GH_TO_ABAQUS3_omega_grid.py

Minimal-diff update of the previously working master script.

WHAT CHANGED COMPARED TO THE OLD WORKING VERSION:
- RH_IN:Nodes removed
- RH_IN:Seeds removed
- RH_IN:coords added
- coords are passed to Grasshopper as a flat list on branch [0]
- Nodes is now derived only for bookkeeping:
      Nodes = len(coords) / 2
- grid/sizing variables are written into design_vars.json
- RH_IN:omega_corner_radius added for rounded omega corners

WHAT STAYS THE SAME:
- Same GHX file path
- Same Rhino Compute -> Grasshopper -> Abaqus workflow
- Same export verification
- Same results summary logic
"""

import os
import re
import sys
import time
import json
import subprocess
import urllib.request
import requests

import compute_rhino3d.Util
import compute_rhino3d.Grasshopper as gh


# ==========================================================
# CONFIG
# ==========================================================
compute_rhino3d.Util.url = "http://localhost:6500/"
compute_rhino3d.Util.authToken = ""

# Longer Python-side timeout for heavy Grasshopper solves.
# This does not change your workflow; it only prevents the Python client
# from giving up too early and gives a clearer error if Compute returns HTML/empty text.
COMPUTE_TIMEOUT_SEC = 2000

# IMPORTANT: set this to your omega-profile Grasshopper file.
GH_FILE = r"C:\CHANGE_ME\Your_Omega_RowColumn_Grid.ghx"
BASE_DIR = r"C:\CHANGE_ME\Omega_grid_cases"
DESIGN_INPUT_LIVE = r"C:\CHANGE_ME\design_input_live_omega_grid.json"

ABAQUS_BAT = r"C:\SIMULIA\abaqus\Commands\abaqus.bat"
ABAQUS_PIPELINE_SCRIPT = r"C:\Rhino Hiwi\Thesis\cad_to_stp\Trial_I and_C_seperate\Omega_Profiles_voronoi\Omega_GA_sripts\RUN_ALL_PIPELINE3_omega.py"

ABAQUS_WORKING_DIR = r"C:\CHANGE_ME\Omega_grid_working_dir"

# ----------------------------------------------------------
# Row-column grid model: topology is fixed in Grasshopper.
# coords are kept only as an empty compatibility field.
# ----------------------------------------------------------
DEFAULT_COORDS = []

# ----------------------------------------------------------
# SAME GH input pattern as before, except:
# - Nodes removed
# - Seeds removed
# - coords added
# ----------------------------------------------------------
GH_INPUTS = {
    # Only the necessary Grasshopper RH_IN inputs are sent to Rhino Compute.
    # coords + thickness metadata are written to design_input_live.json instead.
    "RH_IN:X_Size": 500,
    "RH_IN:Y_Size": 600,
    "RH_IN:Radius": 100.0,
    "RH_IN:stud_max": 15.0,
    "RH_IN:Height": 20.0,
    "RH_IN:omega_head_width": 6.0,
    "RH_IN:omega_head_gap": 1.0,
    "RH_IN:omega_bottom_flange_width": 4.0,
    "RH_IN:omega_web_angle_from_vertical": 20.0,
    "RH_IN:omega_corner_radius": 0.0,
    # Keep these because the exporter needs them
    "RH_IN:File_Type": 2,
    "RH_IN:BASE_DIR": BASE_DIR,
}


DEFAULT_DESIGN = {
    "coords": list(DEFAULT_COORDS),
    "Height": 20.0,
    "omega_head_width": 6.0,
    "omega_head_gap": 2.00,
    "omega_bottom_flange_width": 6.0,
    "omega_web_angle_from_vertical": 20.0,
    "omega_corner_radius": 0.0,
    "Thickness_skin": 1.50,
    "Thickness_stiff": 1.0,
    "stud_max": 15.0,
    # Optional grid metadata. Keep fixed unless your GH file reads these values.
    "grid_rows": 3,
    "grid_columns": 2,
    "grid_spacing_x": None,
    "grid_spacing_y": None,

    # ------------------------------------------------------
    # Optional metadata used only for folder naming in GH.
    # These are written into design_input_live.json.
    # ------------------------------------------------------
    "run_stage": None,
    "run_generation": None,
    "run_evaluation": None,
    "run_baseline": None,
}


# ==========================================================
# HELPERS
# ==========================================================
def print_section(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def get_first_value(inner_tree):
    if not inner_tree:
        return None
    for branch in inner_tree.values():
        if branch:
            return branch[0].get("data")
    return None


def normalize_value(v):
    if v is None:
        return None

    if isinstance(v, str):
        s = v.strip()

        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            s = s[1:-1]

        s = s.replace("\\n", "\n")

        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False

        return s

    return v


def build_run_folder(base_dir, case_name, out_folder_raw=None):
    if isinstance(out_folder_raw, str) and out_folder_raw.strip():
        return os.path.normpath(out_folder_raw.strip())

    if isinstance(case_name, str) and case_name.strip():
        return os.path.normpath(os.path.join(base_dir, case_name.strip()))

    return None


def verify_expected_files(run_folder, file_type):
    missing = []

    geom_files = []
    if file_type in (1, 3):
        geom_files.extend([
            "Lower_Skin.sat",
            "S_full.sat",
            "S_half_patches.sat",
        ])
    if file_type in (2, 3):
        geom_files.extend([
            "Lower_Skin.stp",
            "S_full.stp",
            "S_half_patches.stp",
        ])

    json_files = [
        "Sfull_Shalf&Patches.json",
    ]

    expected = geom_files + json_files

    for name in expected:
        path = os.path.join(run_folder, name)
        if not os.path.isfile(path):
            missing.append(path)

    return missing


def parse_run_folder_from_log(log_msg):
    if not log_msg:
        return None

    m = re.search(r"Run folder:\s*(.+)", log_msg)
    if not m:
        return None

    path = m.group(1).strip()
    path = path.replace("\\\\", "\\")
    return os.path.normpath(path)


def check_paths():
    if not os.path.isfile(GH_FILE):
        raise RuntimeError("Grasshopper file not found:\n%s" % GH_FILE)

    if not os.path.isfile(ABAQUS_PIPELINE_SCRIPT):
        raise RuntimeError("RUN_ALL_PIPELINE3_omega.py not found:\n%s" % ABAQUS_PIPELINE_SCRIPT)

    if not os.path.isfile(ABAQUS_BAT):
        raise RuntimeError(
            "abaqus.bat not found.\n"
            "Current value:\n%s\n\n"
            "Please use the full file path, usually ending with abaqus.bat." % ABAQUS_BAT
        )

    if not os.path.isdir(BASE_DIR):
        raise RuntimeError("BASE_DIR not found:\n%s" % BASE_DIR)

    if not os.path.isdir(ABAQUS_WORKING_DIR):
        raise RuntimeError("ABAQUS_WORKING_DIR not found:\n%s" % ABAQUS_WORKING_DIR)


def _safe_float(v, name):
    try:
        return float(v)
    except:
        raise RuntimeError("Invalid float for %s: %r" % (name, v))


def _round2(x):
    return round(float(x), 2)


def _safe_coords_list(v):
    if v is None:
        raise RuntimeError("coords missing in design input.")

    if not isinstance(v, (list, tuple)):
        raise RuntimeError("coords must be a list/tuple. Got: %r" % type(v))

    out = []
    for idx, item in enumerate(v):
        try:
            val = float(item)
        except:
            raise RuntimeError("coords[%d] is not numeric: %r" % (idx, item))

        # Keep normalized bounds identical to Gene Pool logic
        if val < 0.0:
            val = 0.0
        if val > 1.0:
            val = 1.0

        out.append(val)

    if len(out) < 2 or (len(out) % 2) != 0:
        raise RuntimeError("coords must contain an even number of values. Got length=%d" % len(out))

    return out


def _bounded(design):
    d = dict(design)

    d["coords"] = _safe_coords_list(d.get("coords"))
    d["Height"] = _safe_float(d["Height"], "Height")
    d["Thickness_skin"] = _safe_float(d["Thickness_skin"], "Thickness_skin")
    d["Thickness_stiff"] = _safe_float(d["Thickness_stiff"], "Thickness_stiff")
    d["stud_max"] = _safe_float(d["stud_max"], "stud_max")
    d["omega_head_width"] = _safe_float(d.get("omega_head_width", 8.0), "omega_head_width")
    d["omega_head_gap"] = _safe_float(d.get("omega_head_gap", 3.0), "omega_head_gap")
    d["omega_bottom_flange_width"] = _safe_float(d.get("omega_bottom_flange_width", 8.0), "omega_bottom_flange_width")
    d["omega_web_angle_from_vertical"] = _safe_float(d.get("omega_web_angle_from_vertical", 20.0), "omega_web_angle_from_vertical")
    d["omega_corner_radius"] = _safe_float(d.get("omega_corner_radius", 1.0), "omega_corner_radius")

    # Same bounds philosophy as before
    if d["Height"] < 5.0 or d["Height"] > 30.0:
        raise RuntimeError("Height out of range [5, 30]: %s" % d["Height"])
    if d["Thickness_skin"] < 1.0 or d["Thickness_skin"] > 10.0:
        raise RuntimeError("Thickness_skin out of range [1, 10]: %s" % d["Thickness_skin"])
    if d["Thickness_stiff"] < 1.0 or d["Thickness_stiff"] > 10.0:
        raise RuntimeError("Thickness_stiff out of range [1, 10]: %s" % d["Thickness_stiff"])
    if d["stud_max"] < 10.0 or d["stud_max"] > 100.0:
        raise RuntimeError("stud_max out of range [12, 30]: %s" % d["stud_max"])
    if d["omega_head_width"] < 2.0 or d["omega_head_width"] > 20.0:
        raise RuntimeError("omega_head_width out of range [4, 12]: %s" % d["omega_head_width"])
    if d["omega_head_gap"] < 1.0 or d["omega_head_gap"] > 6.0:
        raise RuntimeError("omega_head_gap out of range [1, 6]: %s" % d["omega_head_gap"])
    if d["omega_bottom_flange_width"] < 2.0 or d["omega_bottom_flange_width"] > 20.0:
        raise RuntimeError("omega_bottom_flange_width out of range [4, 12]: %s" % d["omega_bottom_flange_width"])
    if d["omega_web_angle_from_vertical"] < 5.0 or d["omega_web_angle_from_vertical"] > 40.0:
        raise RuntimeError("omega_web_angle_from_vertical out of range [5, 40]: %s" % d["omega_web_angle_from_vertical"])
    if d["omega_corner_radius"] < 0.0 or d["omega_corner_radius"] > 10.0:
        raise RuntimeError("omega_corner_radius out of range [0, 10]: %s" % d["omega_corner_radius"])

    # Nodes is derived only for bookkeeping and file naming logic later
    d["Nodes"] = int(len(d["coords"]) / 2)

    # ------------------------------------------------------
    # Optional run metadata used only for folder naming in GH.
    # ------------------------------------------------------
    d["run_stage"] = d.get("run_stage", None)
    d["run_generation"] = d.get("run_generation", None)
    d["run_evaluation"] = d.get("run_evaluation", None)
    d["run_baseline"] = d.get("run_baseline", None)

    return d


def load_external_design_from_argv():
    """
    Expected usage from evaluate_design.py:
        python MASTER_GH_TO_ABAQUS3_omega_grid.py <design_input_json>
    """
    if len(sys.argv) < 2:
        return dict(DEFAULT_DESIGN), None

    design_json_path = os.path.normpath(sys.argv[1])

    if not os.path.isfile(design_json_path):
        raise RuntimeError("Design input JSON not found:\n%s" % design_json_path)

    f = open(design_json_path, "r")
    try:
        raw = json.load(f)
    finally:
        f.close()

    design = dict(DEFAULT_DESIGN)
    design.update(raw)
    design = _bounded(design)

    return design, design_json_path


def write_design_input_live_json(design, source_json_path=None):
    """
    Write the fixed live JSON file that Grasshopper now reads directly.

    This file is overwritten before every GH solve.
    GH point-generation script + exporter script both read this file.
    """
    live_dir = os.path.dirname(DESIGN_INPUT_LIVE)
    if live_dir and not os.path.isdir(live_dir):
        os.makedirs(live_dir)

    payload = {
        "coords": list(design["coords"]),
        "Height": _round2(design["Height"]),
        "omega_head_width": _round2(design.get("omega_head_width", 6.0)),
        "omega_head_gap": _round2(design.get("omega_head_gap", 2.0)),
        "omega_bottom_flange_width": _round2(design.get("omega_bottom_flange_width", 6.0)),
        "omega_web_angle_from_vertical": _round2(design.get("omega_web_angle_from_vertical", 20.0)),
        "omega_corner_radius": _round2(design.get("omega_corner_radius", 1.0)),
        "Thickness_skin": _round2(design["Thickness_skin"]),
        "Thickness_stiff": _round2(design["Thickness_stiff"]),
        "stud_max": _round2(design["stud_max"]),
        "grid_rows": design.get("grid_rows"),
        "grid_columns": design.get("grid_columns"),
        "grid_spacing_x": design.get("grid_spacing_x"),
        "grid_spacing_y": design.get("grid_spacing_y"),
        "Radius": _round2(GH_INPUTS.get("RH_IN:Radius", 100.0)),
        "run_stage": design.get("run_stage"),
        "run_generation": design.get("run_generation"),
        "run_evaluation": design.get("run_evaluation"),
        "run_baseline": design.get("run_baseline"),
        "source_json_path": source_json_path,
        "written_by": "MASTER_GH_TO_ABAQUS3_omega_grid.py",
        "timestamp_epoch_sec": time.time(),
    }

    f = open(DESIGN_INPUT_LIVE, "w")
    try:
        json.dump(payload, f, indent=4, sort_keys=True)
    finally:
        f.close()

    print("\nWrote design_input_live.json:")
    print(DESIGN_INPUT_LIVE)
    return DESIGN_INPUT_LIVE


def apply_design_to_gh_inputs(design):
    """
    Push resolved design values into GH inputs.

    IMPORTANT:
    - coords are NO LONGER passed through RH_IN:coords
    - Grasshopper now reads coords + metadata directly from
      design_input_live.json
    - Height / stud_max / omega profile dimensions are pushed as RH_IN values
    """
    GH_INPUTS["RH_IN:Height"] = _round2(design["Height"])
    GH_INPUTS["RH_IN:stud_max"] = _round2(design["stud_max"])
    GH_INPUTS["RH_IN:omega_head_width"] = _round2(design.get("omega_head_width", 6.0))
    GH_INPUTS["RH_IN:omega_head_gap"] = _round2(design.get("omega_head_gap", 2.0))
    GH_INPUTS["RH_IN:omega_bottom_flange_width"] = _round2(design.get("omega_bottom_flange_width", 6.0))
    GH_INPUTS["RH_IN:omega_web_angle_from_vertical"] = _round2(design.get("omega_web_angle_from_vertical", 20.0))
    GH_INPUTS["RH_IN:omega_corner_radius"] = _round2(design.get("omega_corner_radius", 1.0))


def write_design_vars_json(run_folder, design, source_json_path=None):
    """
    Write design_vars.json into CASE_DIR so later Abaqus scripts can read:
    - coords
    - Height
    - Width
    - Thickness_skin
    - Thickness_stiff
    - stud_max
    - derived Nodes
    """
    out_path = os.path.join(run_folder, "design_vars.json")

    payload = {
        "Nodes": int(design["Nodes"]),
        "coords": list(design["coords"]),
        "Height": _round2(design["Height"]),
        "omega_head_width": _round2(design.get("omega_head_width", 6.0)),
        "omega_head_gap": _round2(design.get("omega_head_gap", 2.0)),
        "omega_bottom_flange_width": _round2(design.get("omega_bottom_flange_width", 6.0)),
        "omega_web_angle_from_vertical": _round2(design.get("omega_web_angle_from_vertical", 20.0)),
        "omega_corner_radius": _round2(design.get("omega_corner_radius", 1.0)),
        "Thickness_skin": _round2(design["Thickness_skin"]),
        "Thickness_stiff": _round2(design["Thickness_stiff"]),
        "stud_max": _round2(design["stud_max"]),
        "grid_rows": design.get("grid_rows"),
        "grid_columns": design.get("grid_columns"),
        "grid_spacing_x": design.get("grid_spacing_x"),
        "grid_spacing_y": design.get("grid_spacing_y"),
        "run_stage": design.get("run_stage"),
        "run_generation": design.get("run_generation"),
        "run_evaluation": design.get("run_evaluation"),
        "run_baseline": design.get("run_baseline"),
        "source_json_path": source_json_path,
        "written_by": "MASTER_GH_TO_ABAQUS3_omega_grid.py",
        "timestamp_epoch_sec": time.time(),
    }

    f = open(out_path, "w")
    try:
        json.dump(payload, f, indent=4, sort_keys=True)
    finally:
        f.close()

    print("\nWrote design_vars.json:")
    print(out_path)

    return out_path



def _compute_fetch_with_timeout(url, args):
    import requests

    timeout_sec = 2000

    # Fix relative Rhino Compute endpoint, e.g. "grasshopper"
    if not url.lower().startswith("http"):
        base_url = compute_rhino3d.Util.url.rstrip("/")
        url = base_url + "/" + url.lstrip("/")

    try:
        response = requests.post(
            url,
            json=args,
            timeout=timeout_sec
        )

        if response.status_code != 200:
            raise RuntimeError(
                "Rhino Compute returned HTTP %s\nURL: %s\nResponse:\n%s"
                % (response.status_code, url, response.text[:2000])
            )

        try:
            return response.json()
        except Exception:
            raise RuntimeError(
                "Rhino Compute returned non-JSON response.\nURL: %s\nResponse text:\n%s"
                % (url, response.text[:2000])
            )

    except Exception as e:
        raise RuntimeError(
            "Rhino Compute request failed before a response was received.\n"
            "URL: %s\n"
            "Error: %s"
            % (url, str(e))
        )

    status = getattr(response, "status_code", None)
    text = response.text if response.text is not None else ""

    if status is not None and status >= 400:
        raise RuntimeError(
            "Rhino Compute returned HTTP status %s.\n"
            "URL: %s\n"
            "Response preview:\n%s" % (status, url, text[:3000])
        )

    if not text.strip():
        raise RuntimeError(
            "Rhino Compute returned an empty response while solving the GHX file.\n"
            "This usually means Rhino Compute crashed, timed out internally, or the GH definition failed headlessly.\n"
            "Check the Rhino Compute console for the real Grasshopper/Rhino error.\n"
            "GH_FILE:\n%s" % GH_FILE
        )

    try:
        return response.json()
    except Exception as e:
        raise RuntimeError(
            "Rhino Compute returned a non-JSON response.\n"
            "This normally means Rhino Compute failed internally before returning GH results.\n"
            "URL: %s\n"
            "JSON parse error: %s\n"
            "Response preview:\n%s" % (url, str(e), text[:3000])
        )

# ==========================================================
# RHINO COMPUTE STAGE
# ==========================================================
def run_grasshopper_export():
    print_section("CHECKING RHINO COMPUTE SERVER")

    # Minimal-diff health check without extra dependency
    try:
        with urllib.request.urlopen(compute_rhino3d.Util.url + "healthcheck", timeout=5) as resp:
            health_txt = resp.read().decode("utf-8", "ignore")
        print("Compute healthcheck:", health_txt)
    except Exception as e:
        raise RuntimeError(
            "Rhino Compute server is not running at http://localhost:6500/\n"
            "Start rhino.compute first."
        )

    print_section("INPUTS BEING SENT TO GRASSHOPPER")
    for k, v in GH_INPUTS.items():
        print("%s: %s" % (k, v))
    print("DESIGN_INPUT_LIVE: %s" % DESIGN_INPUT_LIVE)

    trees = []

    # ------------------------------------------------------
    # Current GH setup:
    # - no RH_IN:coords anymore
    # - GH reads coords from design_input_live.json
    # ------------------------------------------------------
    for key, value in GH_INPUTS.items():
        tree = gh.DataTree(key)
        tree.Append([0], [value])
        trees.append(tree)

    print_section("RUNNING GRASSHOPPER DEFINITION")
    print("Compute timeout set to %s seconds" % COMPUTE_TIMEOUT_SEC)

    # Patch only the Compute HTTP fetch used internally by gh.EvaluateDefinition.
    # This keeps the rest of the script sequence unchanged.
    old_compute_fetch = compute_rhino3d.Util.ComputeFetch
    compute_rhino3d.Util.ComputeFetch = _compute_fetch_with_timeout

    start_time = time.time()
    try:
        result = gh.EvaluateDefinition(GH_FILE, trees)
    finally:
        compute_rhino3d.Util.ComputeFetch = old_compute_fetch

    elapsed = time.time() - start_time
    print("Solve completed in %.2f seconds" % elapsed)

    print_section("RETURNED PARAMETER NAMES")
    for item in result.get("values", []):
        print(item.get("ParamName"))

    outputs = {}
    for item in result.get("values", []):
        name = item.get("ParamName")
        raw_value = get_first_value(item.get("InnerTree", {}))
        outputs[name] = normalize_value(raw_value)

    out_folder_raw = outputs.get("RH_OUT:OUT_FOLDER")
    out_case_name = outputs.get("RH_OUT:OUT_CASE_NAME")
    ok_all = outputs.get("RH_OUT:OK_ALL")
    log_msg = outputs.get("RH_OUT:LOG")
    geom = outputs.get("RH_OUT:Geom")

    run_folder = build_run_folder(BASE_DIR, out_case_name, out_folder_raw)

    if not run_folder:
        run_folder = parse_run_folder_from_log(log_msg)

    print_section("GRASSHOPPER OUTPUT SUMMARY")
    print("OUT_FOLDER (raw from GH):")
    print(out_folder_raw)

    print("\nOUT_CASE_NAME:")
    print(out_case_name)

    print("\nRUN_FOLDER (final resolved path):")
    print(run_folder)

    print("\nOK_ALL:")
    print(ok_all)

    print("\nGEOM:")
    print(geom)

    print("\nLOG:")
    print(log_msg)

    if ok_all is not True:
        raise RuntimeError("Grasshopper export FAILED.\n\n%s" % log_msg)

    if not run_folder:
        raise RuntimeError(
            "Grasshopper export succeeded, but RUN_FOLDER could not be resolved.\n\n"
            "OUT_FOLDER=%s\nOUT_CASE_NAME=%s\n\nLOG:\n%s" % (
                out_folder_raw, out_case_name, log_msg
            )
        )

    if not os.path.isdir(run_folder):
        raise RuntimeError("Resolved run folder does not exist:\n%s" % run_folder)

    file_type = 2
    missing_files = verify_expected_files(run_folder, file_type)
    if missing_files:
        raise RuntimeError(
            "Grasshopper export reported success, but some files are missing.\n\n"
            "Run folder:\n%s\n\nMissing files:\n- %s" % (
                run_folder, "\n- ".join(missing_files)
            )
        )

    return {
        "run_folder": run_folder,
        "case_name": out_case_name,
        "ok_all": ok_all,
        "log": log_msg,
        "elapsed_sec": elapsed,
    }


# ==========================================================
# ABAQUS STAGE
# ==========================================================
def run_abaqus_pipeline(case_dir):
    print_section("LAUNCHING ABAQUS PIPELINE")

    cmd = [
        ABAQUS_BAT,
        "cae",
        'noGUI=%s' % ABAQUS_PIPELINE_SCRIPT,
        "--",
        case_dir,
    ]

    print("ABAQUS_BAT:")
    print(ABAQUS_BAT)

    print("\nRUN_ALL_PIPELINE3_omega.py:")
    print(ABAQUS_PIPELINE_SCRIPT)

    print("\nCASE_DIR passed to Abaqus:")
    print(case_dir)

    print("\nCommand:")
    print(" ".join(['"%s"' % c if " " in c else c for c in cmd]))

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=ABAQUS_WORKING_DIR,
            check=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        elapsed = time.time() - start_time

        print_section("ABAQUS STDOUT")
        print(result.stdout if result.stdout else "[no stdout]")

        print_section("ABAQUS STDERR")
        print(result.stderr if result.stderr else "[no stderr]")

        return {
            "success": True,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed_sec": elapsed,
        }

    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time

        print_section("ABAQUS STDOUT")
        print(e.stdout if e.stdout else "[no stdout]")

        print_section("ABAQUS STDERR")
        print(e.stderr if e.stderr else "[no stderr]")

        return {
            "success": False,
            "returncode": e.returncode,
            "stdout": e.stdout,
            "stderr": e.stderr,
            "elapsed_sec": elapsed,
        }


# ==========================================================
# RESULTS / KPI READING
# ==========================================================
def read_results_summary(run_folder):
    results_dir = os.path.join(run_folder, "Results")
    summary_json = os.path.join(results_dir, "kpi_summary.json")
    all_json = os.path.join(results_dir, "kpi_results_all.json")
    all_csv = os.path.join(results_dir, "kpi_results_all.csv")

    out = {
        "results_dir": results_dir,
        "results_dir_exists": os.path.isdir(results_dir),
        "summary_json": summary_json,
        "summary_json_exists": os.path.isfile(summary_json),
        "all_json": all_json,
        "all_json_exists": os.path.isfile(all_json),
        "all_csv": all_csv,
        "all_csv_exists": os.path.isfile(all_csv),
        "summary_data": None,
    }

    if os.path.isfile(summary_json):
        try:
            f = open(summary_json, "r")
            try:
                out["summary_data"] = json.load(f)
            finally:
                f.close()
        except Exception as e:
            out["summary_data"] = {"read_error": str(e)}

    return out


# ==========================================================
# FINAL SUMMARY
# ==========================================================
def print_final_summary(gh_info, abaqus_info, results_info, design_info):
    print_section("FINAL SUMMARY")

    print("Design inputs used:")
    print("  Nodes(derived) : %s" % design_info.get("Nodes"))
    print("  coords_len     : %s" % len(design_info.get("coords", [])))
    print("  Height         : %s" % design_info.get("Height"))
    print("  omega_head_width             : %s" % design_info.get("omega_head_width"))
    print("  omega_head_gap               : %s" % design_info.get("omega_head_gap"))
    print("  omega_bottom_flange_width    : %s" % design_info.get("omega_bottom_flange_width"))
    print("  omega_web_angle_from_vertical: %s" % design_info.get("omega_web_angle_from_vertical"))
    print("  omega_corner_radius        : %s" % design_info.get("omega_corner_radius"))
    print("  Thickness_skin : %s" % design_info.get("Thickness_skin"))
    print("  Thickness_stiff: %s" % design_info.get("Thickness_stiff"))
    print("  stud_max       : %s" % design_info.get("stud_max"))

    print("\nGrasshopper stage:")
    print("  Success      : %s" % gh_info["ok_all"])
    print("  Case name    : %s" % gh_info["case_name"])
    print("  Run folder   : %s" % gh_info["run_folder"])
    print("  Solve time   : %.2f sec" % gh_info["elapsed_sec"])

    print("\nAbaqus stage:")
    print("  Success      : %s" % abaqus_info["success"])
    print("  Return code  : %s" % abaqus_info["returncode"])
    print("  Run time     : %.2f sec" % abaqus_info["elapsed_sec"])

    print("\nExpected results folder:")
    print("  %s" % results_info["results_dir"])
    print("  Exists       : %s" % results_info["results_dir_exists"])

    print("\nPostprocess outputs:")
    print("  kpi_summary.json     : %s" % results_info["summary_json_exists"])
    print("  kpi_results_all.json : %s" % results_info["all_json_exists"])
    print("  kpi_results_all.csv  : %s" % results_info["all_csv_exists"])

    summary = results_info.get("summary_data")

    if isinstance(summary, dict) and "read_error" not in summary:
        print("\nKPI SUMMARY")
        print("  lambda1_compression    : %s" % summary.get("lambda1_compression"))
        print("  lambda1_shear          : %s" % summary.get("lambda1_shear"))
        print("  lambda1_combined       : %s" % summary.get("lambda1_combined"))
        print("  fitness_compression    : %s" % summary.get("fitness_compression"))
        print("  fitness_shear          : %s" % summary.get("fitness_shear"))
        print("  fitness_combined       : %s" % summary.get("fitness_combined"))
        print("  fitness_mean_all_cases : %s" % summary.get("fitness_mean_all_cases"))

        mass_consistency = summary.get("mass_consistency", {})
        print("  mass_all_equal         : %s" % mass_consistency.get("all_equal"))
        print("  unique_mass_values     : %s" % mass_consistency.get("unique_mass_values"))
    elif isinstance(summary, dict) and "read_error" in summary:
        print("\nWARNING:")
        print("  Could not read kpi_summary.json")
        print("  Error: %s" % summary["read_error"])
    else:
        print("\nWARNING:")
        print("  kpi_summary.json not found. Abaqus may have failed before postprocessing.")


# ==========================================================
# MAIN
# ==========================================================
def main():
    check_paths()

    design_info, source_json_path = load_external_design_from_argv()
    # ------------------------------------------------------
    # Make sure Nodes is always derived from coords.
    # This keeps old print/debug code safe even when the
    # incoming design JSON does not explicitly store Nodes.
    # ------------------------------------------------------
    design_info["coords"] = list(design_info.get("coords", []))
    design_info["Nodes"] = int(len(design_info.get("coords", [])) / 2)

    apply_design_to_gh_inputs(design_info)
    write_design_input_live_json(design_info, source_json_path=source_json_path)

    print_section("DESIGN INPUT SOURCE")
    print("External JSON:" if source_json_path else "Using defaults")
    print(source_json_path if source_json_path else "[default internal values]")

    print("\nResolved design:")
    print(json.dumps({
        "Nodes": design_info["Nodes"],
        "coords_len": len(design_info["coords"]),
        "coords_first_10": design_info["coords"][:10],
        "Height": design_info["Height"],
        "omega_head_width": design_info.get("omega_head_width"),
        "omega_head_gap": design_info.get("omega_head_gap"),
        "omega_bottom_flange_width": design_info.get("omega_bottom_flange_width"),
        "omega_web_angle_from_vertical": design_info.get("omega_web_angle_from_vertical"),
        "omega_corner_radius": design_info.get("omega_corner_radius"),
        "Thickness_skin": design_info["Thickness_skin"],
        "Thickness_stiff": design_info["Thickness_stiff"],
        "stud_max": design_info["stud_max"],
        "run_stage": design_info.get("run_stage"),
        "run_generation": design_info.get("run_generation"),
        "run_evaluation": design_info.get("run_evaluation"),
        "run_baseline": design_info.get("run_baseline"),
    }, indent=4, sort_keys=True))

    print("\nLive JSON path:")
    print(DESIGN_INPUT_LIVE)

    gh_info = run_grasshopper_export()

    write_design_vars_json(
        gh_info["run_folder"],
        design_info,
        source_json_path=source_json_path
    )

    abaqus_info = run_abaqus_pipeline(gh_info["run_folder"])
    results_info = read_results_summary(gh_info["run_folder"])
    print_final_summary(gh_info, abaqus_info, results_info, design_info)

    if not abaqus_info["success"]:
        raise RuntimeError(
            "Abaqus pipeline failed.\n"
            "Return code: %s" % abaqus_info["returncode"]
        )

    print_section("AUTOMATION COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
