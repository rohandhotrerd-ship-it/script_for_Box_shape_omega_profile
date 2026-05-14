# -*- coding: utf-8 -*-
"""
ONE-STAGE ROW-COLUMN GRID VERSION.
- No coords required.
- No Stage 1 / Stage 2.
- Evaluates only sizing/profile variables.

evaluate_design_omega_grid.py

Runs ONE design through the existing MASTER_GH_TO_ABAQUS3_omega_grid.py pipeline.

This version keeps the structure of your previous evaluator, but adds:
# - coordinate-based designs (coords list)
# - lambda_1_crit = min(lambda1_compression, lambda1_shear, lambda1_combined)
# - two fitness values:
#       1) fitness_lambda_over_mass
#       2) fitness_paper
# - mass + lambda logging support for the GA CSV

IMPORTANT:
# - This script evaluates ONE design only.
# - The GA loop / generations / stages are handled in simple_ga_driver.
# - MASTER_GH_TO_ABAQUS3_omega_grid.py must support the new "coords" field for the
#   coordinate-based workflow to run end-to-end.
# - separate shell-property thickness variables for skin and stiffeners
"""

import os
import sys
import json
import time
import subprocess


# ============================================================
# PATH CONFIG
# ============================================================
MASTER_SCRIPT = r"C:\Rhino Hiwi\Thesis\cad_to_stp\Trial_I and_C_seperate\Omega_Profiles_voronoi\Omega_GA_sripts\MASTER_GH_TO_ABAQUS3_omega_grid.py"
PYTHON_EXE = sys.executable

WORK_DIR = r"C:\CHANGE_ME\Omega_grid_GA_work"
if not os.path.isdir(WORK_DIR):
    os.makedirs(WORK_DIR)


# ============================================================
# FITNESS SETTINGS
# ============================================================
# ------------------------------------------------------------
# Reference design used for normalized paper-style fitness
# ------------------------------------------------------------
# These values come from the previously solved reference model:
#   N25.0_P5.0_H18.50_W5.00_R100.00
#
# Reference mass:
MASS_REF = 1

# Reference critical lambda:
LAMBDA_REF = 1

# Keep the reference model name explicit for logs / CSV traceability.
REFERENCE_MODEL_NAME = "OMEGA_GRID_REFERENCE_TO_BE_DEFINED"

# Paper-style weights:
# - slightly more priority to mass reduction
# - but still keeping buckling strength important
W_MASS = 0.60
W_LAMBDA = 0.40

# Large penalty for failed / invalid designs.
PENALTY_FITNESS_PAPER = 1.0e6

# ------------------------------------------------------------
# Lambda constraint settings
#
# Stage 1:
# - keep ONLY soft penalty because stage-1 has fixed sizing params
# - this lets GA still rank "less bad" topologies
#
# Stage 2:
# - keep soft penalty
# - add a hard penalty if any load case has lambda < 1.0
# - this follows the mentor rule that good solutions should have lambda >= 1
# ------------------------------------------------------------
LAMBDA_LIMIT = 1.0
LAMBDA_PENALTY_K = 5.0
STAGE2_HARD_PENALTY = 100.0


# ============================================================
# HELPERS
# ============================================================
def _safe_int(v, name):
    try:
        return int(v)
    except:
        raise RuntimeError("Invalid integer for %s: %r" % (name, v))


def _safe_float(v, name):
    try:
        return float(v)
    except:
        raise RuntimeError("Invalid float for %s: %r" % (name, v))


def _round2(x):
    return round(float(x), 2)


def _round6(x):
    return round(float(x), 6)


def _write_json(path, data):
    f = open(path, "w")
    try:
        json.dump(data, f, indent=4, sort_keys=True)
    finally:
        f.close()


def _read_json(path):
    f = open(path, "r")
    try:
        return json.load(f)
    finally:
        f.close()


def _read_text(path):
    if not path or not os.path.isfile(path):
        return ""
    f = open(path, "r")
    try:
        return f.read()
    finally:
        f.close()


def _tail_text(text, n=20):
    lines = (text or "").splitlines()
    if len(lines) <= n:
        return "\n".join(lines)
    return "\n".join(lines[-n:])


def _coords_count_to_nodes(coords):
    if coords is None:
        return None
    return int(len(coords) // 2)


def sanitize_design(design):
    """
    One-stage row-column grid design dictionary.

    Topology is fixed in Grasshopper, so coords/Nodes are not required.
    The GA only changes sizing/profile variables.
    """
    d = dict(design)

    # Compatibility fields for older logging/postprocess code.
    d["coords"] = list(d.get("coords", []))
    d["Nodes"] = int(len(d["coords"]) // 2)

    d["Height"] = _safe_float(d["Height"], "Height")
    d["Thickness_skin"] = _safe_float(d["Thickness_skin"], "Thickness_skin")
    d["Thickness_stiff"] = _safe_float(d["Thickness_stiff"], "Thickness_stiff")
    d["stud_max"] = _safe_float(d["stud_max"], "stud_max")

    d["omega_head_width"] = _safe_float(d.get("omega_head_width", 6.0), "omega_head_width")
    d["omega_bottom_flange_width"] = _safe_float(d.get("omega_bottom_flange_width", 6.0), "omega_bottom_flange_width")
    d["omega_web_angle_from_vertical"] = _safe_float(d.get("omega_web_angle_from_vertical", 20.0), "omega_web_angle_from_vertical")

    # Fixed values for sharp-corner row-column study unless you change them here.
    d["omega_head_gap"] = float(d.get("omega_head_gap", FIXED_OMEGA_HEAD_GAP))
    d["omega_corner_radius"] = float(d.get("omega_corner_radius", FIXED_OMEGA_CORNER_RADIUS))

    # Optional metadata if your GH file reads row/column values from JSON.
    d["grid_rows"] = d.get("grid_rows", 3)
    d["grid_columns"] = d.get("grid_columns", 2)
    d["grid_spacing_x"] = d.get("grid_spacing_x", None)
    d["grid_spacing_y"] = d.get("grid_spacing_y", None)

    if "Seeds" not in d:
        d["Seeds"] = None

    if d["Height"] < 5.0 or d["Height"] > 40.0:
        raise RuntimeError("Height out of range [5, 40]: %s" % d["Height"])
    if d["Thickness_skin"] < 0.5 or d["Thickness_skin"] > 10.0:
        raise RuntimeError("Thickness_skin out of range [0.5, 10]: %s" % d["Thickness_skin"])
    if d["Thickness_stiff"] < 0.5 or d["Thickness_stiff"] > 10.0:
        raise RuntimeError("Thickness_stiff out of range [0.5, 10]: %s" % d["Thickness_stiff"])
    if d["stud_max"] < 1.0 or d["stud_max"] > 80.0:
        raise RuntimeError("stud_max out of range [1, 80]: %s" % d["stud_max"])

    d["Height"] = _round2(d["Height"])
    d["Thickness_skin"] = _round2(d["Thickness_skin"])
    d["Thickness_stiff"] = _round2(d["Thickness_stiff"])
    d["stud_max"] = _round2(d["stud_max"])
    d["omega_head_width"] = _round2(d["omega_head_width"])
    d["omega_head_gap"] = _round2(d["omega_head_gap"])
    d["omega_bottom_flange_width"] = _round2(d["omega_bottom_flange_width"])
    d["omega_web_angle_from_vertical"] = _round2(d["omega_web_angle_from_vertical"])
    d["omega_corner_radius"] = _round2(d["omega_corner_radius"])

    # one-stage label
    d["stage_name"] = d.get("stage_name", "grid")
    d["baseline_id"] = d.get("baseline_id", "grid")

    return d

def _make_design_tag(design):
    """
    Compact readable tag for the fixed row-column grid study.
    """
    return "GRID_H%s_OHW%s_OHG%s_OBF%s_OWA%s_TS%s_TW%s_SM%s" % (
        ("%.2f" % design["Height"]).replace(".", "_"),
        ("%.2f" % design["omega_head_width"]).replace(".", "_"),
        ("%.2f" % design["omega_head_gap"]).replace(".", "_"),
        ("%.2f" % design["omega_bottom_flange_width"]).replace(".", "_"),
        ("%.2f" % design["omega_web_angle_from_vertical"]).replace(".", "_"),
        ("%.2f" % design["Thickness_skin"]).replace(".", "_"),
        ("%.2f" % design["Thickness_stiff"]).replace(".", "_"),
        ("%.2f" % design["stud_max"]).replace(".", "_"),
    )

def _extract_run_folder_from_stdout(stdout_text):
    if not stdout_text:
        return None

    lines = stdout_text.splitlines()

    # Format used by MASTER_GH_TO_ABAQUS3_omega_grid.py final summary.
    for i, line in enumerate(lines):
        s = line.strip()
        if s == "Run folder:" and i + 1 < len(lines):
            path_line = lines[i + 1].strip()
            if path_line:
                return os.path.normpath(path_line)

    for i, line in enumerate(lines):
        s = line.strip()
        if s == "RUN_FOLDER (final resolved path):" and i + 1 < len(lines):
            path_line = lines[i + 1].strip()
            if path_line:
                return os.path.normpath(path_line)

    for line in lines:
        s = line.strip()
        if s.startswith("Run folder:"):
            path_line = s.split("Run folder:", 1)[1].strip()
            if path_line:
                return os.path.normpath(path_line)

    return None


def _extract_failure_stage_and_error(stdout_text, stderr_text):
    """
    Infer likely failing script and most useful error line from logs.
    """
    combined = ((stdout_text or "") + "\n" + (stderr_text or "")).splitlines()

    failure_stage = None
    error_msg = None

    for idx in range(len(combined) - 1, -1, -1):
        s = combined[idx].strip()
        if not s:
            continue

        if error_msg is None and (
            "RuntimeError:" in s or
            "Error:" in s or
            "Exception:" in s or
            "Abaqus Error:" in s or
            "Traceback" in s
        ):
            error_msg = s

        if failure_stage is None:
            if 'File "' in s and ".py" in s:
                try:
                    part = s.split('File "', 1)[1]
                    path = part.split('"', 1)[0]
                    failure_stage = os.path.basename(path)
                except:
                    pass

        if error_msg and failure_stage:
            break

    if failure_stage is None:
        text = (stdout_text or "") + "\n" + (stderr_text or "")
        for name in [
            "Creating_Sets5_OMEGA_MESHBASED.py",
            "Mesh_testing2_omega.py",
            "00_import_parts_makeprecise_assemble3_omega.py",
            "04_property_step_interaction_load_bc3_omega.py",
            "05_job_write_datacheck_submit3_omega.py",
            "06_postprocess_dat2_omega.py",
            "RUN_ALL_PIPELINE3_omega.py",
            "MASTER_GH_TO_ABAQUS3_omega_grid.py",
        ]:
            if name in text:
                failure_stage = name
                break

    if error_msg is None:
        for idx in range(len(combined) - 1, -1, -1):
            s = combined[idx].strip()
            if s:
                error_msg = s
                break

    return failure_stage, error_msg


# ============================================================
# FITNESS CALCULATION
# ============================================================
def _compute_lambda_1_crit(summary_data):
    """
    lambda_1_crit = minimum of the FIRST eigenvalue from:
    # - Compression
    # - Shear
    # - Combined
    """
    if not isinstance(summary_data, dict):
        return None

    vals = [
        summary_data.get("lambda1_compression"),
        summary_data.get("lambda1_shear"),
        summary_data.get("lambda1_combined"),
    ]
    vals = [float(v) for v in vals if v is not None]

    if not vals:
        return None

    return min(vals)


def _extract_mass(summary_data):
    """
    Mass is taken from kpi_summary.json.
    The postprocessor stores mass_consistency.unique_mass_values.
    """
    if not isinstance(summary_data, dict):
        return None

    mc = summary_data.get("mass_consistency", {})
    vals = mc.get("unique_mass_values", [])

    if isinstance(vals, list) and len(vals) > 0:
        try:
            return float(vals[0])
        except:
            return None

    return None


def _compute_fitness_lambda_over_mass(lambda_1_crit, mass):
    """
    Current simple efficiency metric:
    # maximize lambda_1_crit / mass
    """
    if lambda_1_crit is None or mass is None or mass <= 0.0:
        return None
    return float(lambda_1_crit) / float(mass)


def _soft_lambda_penalty(lambda_comp, lambda_shear, lambda_combined):
    """
    Soft quadratic penalty used in BOTH stage-1 and stage-2.

    # Why keep this?
    # - It gives GA a gradient among bad designs
    # - A design with lambda=0.30 should still rank better than lambda=0.10
    """
    total = 0.0

    for val in [lambda_comp, lambda_shear, lambda_combined]:
        if val is None:
            continue
        try:
            v = float(val)
        except:
            continue

        if v < LAMBDA_LIMIT:
            total += LAMBDA_PENALTY_K * ((LAMBDA_LIMIT - v) ** 2)

    return total


def _hard_stage2_lambda_penalty(stage_name, lambda_comp, lambda_shear, lambda_combined):
    """
    Hard penalty is applied ONLY in stage-2.

    # Why only stage-2?
    # - stage-1 has fixed H/W/T/stud_max and is only topology screening
    # - stage-2 has enough freedom to enforce lambda >= 1.0 more strictly
    """
    if stage_name != "stage2":
        return 0.0

    vals = [lambda_comp, lambda_shear, lambda_combined]
    for val in vals:
        if val is None:
            return STAGE2_HARD_PENALTY
        try:
            v = float(val)
        except:
            return STAGE2_HARD_PENALTY

        if v < LAMBDA_LIMIT:
            return STAGE2_HARD_PENALTY

    return 0.0


def _compute_fitness_paper(lambda_1_crit, mass, lambda_comp=None, lambda_shear=None, lambda_combined=None, stage_name=None):
    """
    Paper-style scalar fitness to MINIMIZE.

    Base term:

        F_base = 0.6 * (mass / MASS_REF) + 0.4 * (LAMBDA_REF / lambda_1_crit)

    Added constraint handling:
    # - soft quadratic penalty in BOTH stages
    # - hard +100 penalty ONLY in stage-2 if any lambda < 1.0
    """
    if lambda_1_crit is None or mass is None or mass <= 0.0:
        return PENALTY_FITNESS_PAPER

    if lambda_1_crit <= 0.0:
        return PENALTY_FITNESS_PAPER

    base_fitness = (W_MASS * (float(mass) / MASS_REF)) + (W_LAMBDA * (LAMBDA_REF / float(lambda_1_crit)))

    # --------------------------------------------------------
    # Soft penalty keeps ranking information among infeasible designs
    # in both stage-1 and stage-2.
    # --------------------------------------------------------
    soft_penalty = _soft_lambda_penalty(lambda_comp, lambda_shear, lambda_combined)

    # --------------------------------------------------------
    # Hard penalty is applied ONLY in stage-2.
    # --------------------------------------------------------
    hard_penalty = _hard_stage2_lambda_penalty(stage_name, lambda_comp, lambda_shear, lambda_combined)

    return base_fitness + soft_penalty + hard_penalty


# ============================================================
# MAIN EVALUATOR
# ============================================================
def evaluate_design(design, keep_temp_files=True, verbose=True):
    """
    Returns a rich result dictionary that the GA driver can use for:
    # - fitness comparison
    # - CSV logging
    # - progress printing
    # - failure diagnostics

    Returned keys include:
    # - fitness_lambda_over_mass
    # - fitness_paper
    # - lambda_1_crit
    # - mass
    # - summary_data
    # - case_dir
    # - logs / failure info
    """
    design = sanitize_design(design)

    if not os.path.isfile(MASTER_SCRIPT):
        raise RuntimeError("MASTER script not found:\n%s" % MASTER_SCRIPT)

    tag = _make_design_tag(design)
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_id = "%s__%s" % (ts, tag)

    # ------------------------------------------------------------
    # Each evaluation writes temp input JSON + stdout/stderr logs.
    # These are stored in GA_Work for debugging and traceability.
    # ------------------------------------------------------------
    design_json_path = os.path.join(WORK_DIR, "design_input_%s.json" % run_id)
    stdout_log_path = os.path.join(WORK_DIR, "stdout_%s.txt" % run_id)
    stderr_log_path = os.path.join(WORK_DIR, "stderr_%s.txt" % run_id)

    _write_json(design_json_path, design)

    cmd = [PYTHON_EXE, MASTER_SCRIPT, design_json_path]

    if verbose:
        print("\n" + "=" * 80)
        print("EVALUATING DESIGN")
        print("=" * 80)
        print(json.dumps(design, indent=4, sort_keys=True))
        print("\nCommand:")
        print(" ".join(['"%s"' % c if " " in c else c for c in cmd]))

    t0 = time.time()

    try:
        p = subprocess.run(
            cmd,
            check=False,
            text=True,
            encoding="utf-8",
            errors="ignore",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        elapsed = time.time() - t0

        # Save stdout/stderr logs for every evaluation.
        f = open(stdout_log_path, "w")
        try:
            f.write(p.stdout if p.stdout else "")
        finally:
            f.close()

        f = open(stderr_log_path, "w")
        try:
            f.write(p.stderr if p.stderr else "")
        finally:
            f.close()

        stdout_text = p.stdout if p.stdout else ""
        stderr_text = p.stderr if p.stderr else ""

        stdout_tail = _tail_text(stdout_text, n=30)
        stderr_tail = _tail_text(stderr_text, n=20)

        case_dir = _extract_run_folder_from_stdout(stdout_text)
        summary_json = None
        summary_data = None

        # These are the new KPI values we want the GA / CSV to store.
        lambda_1_crit = None
        mass = None
        fitness_lambda_over_mass = None
        fitness_paper = PENALTY_FITNESS_PAPER

        success = False
        error = None
        failure_stage = None

        if case_dir:
            summary_json = os.path.join(case_dir, "Results", "kpi_summary.json")

            if os.path.isfile(summary_json):
                try:
                    summary_data = _read_json(summary_json)

                    lambda_1_crit = _compute_lambda_1_crit(summary_data)
                    mass = _extract_mass(summary_data)
                    fitness_lambda_over_mass = _compute_fitness_lambda_over_mass(lambda_1_crit, mass)
                    fitness_paper = _compute_fitness_paper(
                        lambda_1_crit,
                        mass,
                        lambda_comp=summary_data.get("lambda1_compression"),
                        lambda_shear=summary_data.get("lambda1_shear"),
                        lambda_combined=summary_data.get("lambda1_combined"),
                        stage_name="grid",
                    )

                    # Success means the pipeline reached KPI summary successfully.
                    success = True
                except Exception as e:
                    failure_stage, extracted_error = _extract_failure_stage_and_error(stdout_text, stderr_text)
                    error = "Could not read/interpret kpi_summary.json: %s" % str(e)
                    if extracted_error and extracted_error not in error:
                        error += " | " + extracted_error
            else:
                failure_stage, error = _extract_failure_stage_and_error(stdout_text, stderr_text)
                if not error:
                    error = "kpi_summary.json not found"
        else:
            failure_stage, error = _extract_failure_stage_and_error(stdout_text, stderr_text)
            if not error:
                error = "Could not extract case_dir from MASTER stdout"

        # If the process itself failed, success must remain False.
        if p.returncode != 0:
            success = False
            if error is None:
                failure_stage, extracted_error = _extract_failure_stage_and_error(stdout_text, stderr_text)
                error = extracted_error or ("Pipeline failed with return code %s" % p.returncode)

        result = {
            "success": success,

            # ----------------------------------------------------
            # Two fitness functions requested by you:
            # ----------------------------------------------------
            "fitness_lambda_over_mass": fitness_lambda_over_mass,
            "fitness_paper": fitness_paper,

            # ----------------------------------------------------
            # Important KPI values to store in the GA CSV:
            # ----------------------------------------------------
            "lambda_1_crit": lambda_1_crit,
            "mass": mass,

            # Optional per-case lambda_1 values (helpful for debugging)
            "lambda_1_compression": None if not isinstance(summary_data, dict) else summary_data.get("lambda1_compression"),
            "lambda_1_shear": None if not isinstance(summary_data, dict) else summary_data.get("lambda1_shear"),
            "lambda_1_combined": None if not isinstance(summary_data, dict) else summary_data.get("lambda1_combined"),

            "case_dir": case_dir,
            "summary_json": summary_json,
            "summary_data": summary_data,
            "stdout_log": stdout_log_path,
            "stderr_log": stderr_log_path,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "elapsed_sec": elapsed,
            "design": design,
            "error": error,
            "failure_stage": failure_stage,
            "returncode": p.returncode,

            # ----------------------------------------------------
            # Reference values used for normalized fitness
            # ----------------------------------------------------
            "reference_model_name": REFERENCE_MODEL_NAME,
            "mass_ref": MASS_REF,
            "lambda_ref": LAMBDA_REF,
        }

        if verbose:
            print("\n" + "=" * 80)
            print("EVALUATION FINISHED")
            print("=" * 80)
            print("Success       :", result["success"])
            print("Return code   :", result["returncode"])
            print("Elapsed sec   :", result["elapsed_sec"])
            print("Ref model     :", result["reference_model_name"])
            print("Mass ref      :", result["mass_ref"])
            print("Lambda ref    :", result["lambda_ref"])
            print("Lambda limit  :", LAMBDA_LIMIT)
            print("Penalty K     :", LAMBDA_PENALTY_K)
            print("Stage2 hard   :", STAGE2_HARD_PENALTY)
            print("Case dir      :", result["case_dir"])
            print("Summary JSON  :", result["summary_json"])
            print("Mass          :", result["mass"])
            print("Lambda_1_crit :", result["lambda_1_crit"])
            print("Fitness L/M   :", result["fitness_lambda_over_mass"])
            print("Fitness paper :", result["fitness_paper"])
            print("Failure stage :", result["failure_stage"])
            if result["error"]:
                print("Error         :", result["error"])
            print("Stdout log    :", result["stdout_log"])
            print("Stderr log    :", result["stderr_log"])

            if not result["success"]:
                print("\n" + "-" * 80)
                print("STDOUT TAIL")
                print("-" * 80)
                print(result["stdout_tail"])
                print("\n" + "-" * 80)
                print("STDERR TAIL")
                print("-" * 80)
                print(result["stderr_tail"])

        if not keep_temp_files:
            try:
                if os.path.isfile(design_json_path):
                    os.remove(design_json_path)
            except:
                pass

        return result

    except Exception as e:
        elapsed = time.time() - t0
        return {
            "success": False,
            "fitness_lambda_over_mass": None,
            "fitness_paper": PENALTY_FITNESS_PAPER,
            "lambda_1_crit": None,
            "mass": None,
            "lambda_1_compression": None,
            "lambda_1_shear": None,
            "lambda_1_combined": None,
            "case_dir": None,
            "summary_json": None,
            "summary_data": None,
            "stdout_log": stdout_log_path,
            "stderr_log": stderr_log_path,
            "stdout_tail": "",
            "stderr_tail": "",
            "elapsed_sec": elapsed,
            "design": design,
            "error": str(e),
            "failure_stage": None,
            "returncode": None,

            # ----------------------------------------------------
            # Reference values used for normalized fitness
            # ----------------------------------------------------
            "reference_model_name": REFERENCE_MODEL_NAME,
            "mass_ref": MASS_REF,
            "lambda_ref": LAMBDA_REF,
        }


# ============================================================
# DIRECT TEST
# ============================================================
if __name__ == "__main__":
    # ------------------------------------------------------------
    # Example for 25 Voronoi points -> 50 coordinate values.
    # ------------------------------------------------------------
    test_design = {
        "coords": [0.50] * 50,
        "Height": 18.50,
        "Thickness_skin": 4.00,
        "Thickness_stiff": 4.00,
        "stud_max": 15.00,
        "stage_name": "stage1",
        "baseline_id": "A",
    }

    out = evaluate_design(test_design, keep_temp_files=True, verbose=True)

    print("\n" + "=" * 80)
    print("EVALUATION RESULT")
    print("=" * 80)
    print(json.dumps(out, indent=4, sort_keys=True))
