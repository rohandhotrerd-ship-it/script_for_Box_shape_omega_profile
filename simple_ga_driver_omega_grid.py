# -*- coding: utf-8 -*-
"""
simple_ga_driver_omega_grid.py

ONE-STAGE GA driver for the fixed row-column Omega stiffener model.

Use this when topology is fixed in Grasshopper and the GA should optimize only
sizing/profile variables. There is no Stage 1 / Stage 2 and no coordinate
mutation/crossover.
"""

import os
import csv
import json
import time
import random

from evaluate_design_omega_grid import evaluate_design


# ============================================================
# GA SETTINGS
# ============================================================
POP_SIZE = 8
N_GENERATIONS = 10

ELITE_COUNT = 2
TOURNAMENT_K = 3
CROSSOVER_RATE = 0.70

# Fitness to optimize:
# - "fitness_paper" is minimized
# - "fitness_lambda_over_mass" is maximized
ACTIVE_FITNESS = "fitness_paper"

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ============================================================
# PATHS - CHANGE THESE
# ============================================================
WORK_DIR = r"C:\CHANGE_ME\Omega_grid_GA_work"
RESULTS_DIR = r"C:\CHANGE_ME\Omega_grid_GA_results"

if not os.path.isdir(WORK_DIR):
    os.makedirs(WORK_DIR)
if not os.path.isdir(RESULTS_DIR):
    os.makedirs(RESULTS_DIR)

CSV_LOG = os.path.join(RESULTS_DIR, "ga_master_log_omega_grid_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
BEST_JSON = os.path.join(WORK_DIR, "best_design_omega_grid.json")

GLOBAL_EVALUATION_COUNTER = 0


# ============================================================
# DESIGN BOUNDS
# ============================================================
FIXED_OMEGA_HEAD_GAP = 2.0
FIXED_OMEGA_CORNER_RADIUS = 0.0

PARAM_BOUNDS = {
    "Height": (10.0, 25.0),
    "Thickness_skin": (1.0, 4.0),
    "Thickness_stiff": (1.0, 4.0),
    "stud_max": (22.0, 22.0),

    # Keep fixed by writing same min/max, or open the range if you want GA to vary them.
    "omega_head_width": (6.0, 6.0),
    "omega_head_gap": (FIXED_OMEGA_HEAD_GAP, FIXED_OMEGA_HEAD_GAP),
    "omega_bottom_flange_width": (6.0, 6.0),
    "omega_web_angle_from_vertical": (20.0, 20.0),
    "omega_corner_radius": (FIXED_OMEGA_CORNER_RADIUS, FIXED_OMEGA_CORNER_RADIUS),
}

# Mutation amplitudes for parameters that are not fixed.
MUT_DELTA = {
    "Height": 2.0,
    "Thickness_skin": 0.5,
    "Thickness_stiff": 0.5,
    "stud_max": 2.0,
    "omega_head_width": 0.5,
    "omega_bottom_flange_width": 0.5,
    "omega_web_angle_from_vertical": 1.0,
}

MUTATION_RATE_START = 0.25
MUTATION_RATE_END = 0.05

FAILED_FITNESS_LAMBDA_OVER_MASS = -1.0e12
FAILED_FITNESS_PAPER = 1.0e6


# ------------------------------------------------------------
# Repair / retry settings
# ------------------------------------------------------------
# Attempt 0 = original design.
# Attempts 1..MAX_REPAIR_ATTEMPTS = repaired designs.
# If all attempts fail, the design gets penalty fitness and is
# excluded from the clean convergence plots.
MAX_REPAIR_ATTEMPTS = 3
REPAIR_COORD_JITTER_START = 0.035
REPAIR_COORD_JITTER_STEP  = 0.035
REPAIR_THICKNESS_STEP     = 0.20
REPAIR_HEIGHT_STEP        = 0.50


# ============================================================
# HELPERS
# ============================================================
def _round2(x):
    return round(float(x), 2)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _adaptive_rate(gen, n_generations, start_rate, end_rate):
    if n_generations <= 1:
        return float(end_rate)
    frac = float(gen) / float(n_generations - 1)
    return float(start_rate) + (float(end_rate) - float(start_rate)) * frac


def _is_fixed_param(name):
    lo, hi = PARAM_BOUNDS[name]
    return abs(float(lo) - float(hi)) <= 1e-12


def design_to_key(design):
    return (
        _round2(design["Height"]),
        _round2(design["Thickness_skin"]),
        _round2(design["Thickness_stiff"]),
        _round2(design["stud_max"]),
        _round2(design["omega_head_width"]),
        _round2(design["omega_head_gap"]),
        _round2(design["omega_bottom_flange_width"]),
        _round2(design["omega_web_angle_from_vertical"]),
        _round2(design["omega_corner_radius"]),
    )


def random_param(name):
    lo, hi = PARAM_BOUNDS[name]
    return _round2(random.uniform(float(lo), float(hi)))


def random_design():
    d = {
        "coords": [],      # compatibility only; GH grid topology is fixed
        "Nodes": 0,        # compatibility only
        "Height": random_param("Height"),
        "Thickness_skin": random_param("Thickness_skin"),
        "Thickness_stiff": random_param("Thickness_stiff"),
        "stud_max": random_param("stud_max"),
        "omega_head_width": random_param("omega_head_width"),
        "omega_head_gap": random_param("omega_head_gap"),
        "omega_bottom_flange_width": random_param("omega_bottom_flange_width"),
        "omega_web_angle_from_vertical": random_param("omega_web_angle_from_vertical"),
        "omega_corner_radius": random_param("omega_corner_radius"),
        "stage_name": "grid",
        "baseline_id": "grid",
        # Optional metadata if your GH reads it from design_input_live JSON.
        "grid_rows": 3,
        "grid_columns": 2,
        "grid_spacing_x": None,
        "grid_spacing_y": None,
    }
    return d


def _blend(v1, v2, alpha=0.25):
    lo = min(float(v1), float(v2))
    hi = max(float(v1), float(v2))
    interval = hi - lo
    return random.uniform(lo - alpha * interval, hi + alpha * interval)


def crossover(parent1, parent2):
    if random.random() >= CROSSOVER_RATE:
        child = dict(parent1 if random.random() < 0.5 else parent2)
    else:
        child = {}
        for k in PARAM_BOUNDS.keys():
            if _is_fixed_param(k):
                child[k] = _round2(PARAM_BOUNDS[k][0])
            else:
                child[k] = _round2(clamp(_blend(parent1[k], parent2[k]), PARAM_BOUNDS[k][0], PARAM_BOUNDS[k][1]))

    child["coords"] = []
    child["Nodes"] = 0
    child["stage_name"] = "grid"
    child["baseline_id"] = "grid"
    child["grid_rows"] = parent1.get("grid_rows", 3)
    child["grid_columns"] = parent1.get("grid_columns", 2)
    child["grid_spacing_x"] = parent1.get("grid_spacing_x", None)
    child["grid_spacing_y"] = parent1.get("grid_spacing_y", None)
    return child


def mutate(design, generation_idx):
    d = dict(design)
    rate = _adaptive_rate(generation_idx, N_GENERATIONS, MUTATION_RATE_START, MUTATION_RATE_END)

    for k, delta in MUT_DELTA.items():
        if k not in PARAM_BOUNDS:
            continue
        if _is_fixed_param(k):
            d[k] = _round2(PARAM_BOUNDS[k][0])
            continue

        if random.random() < rate:
            d[k] = _round2(clamp(
                float(d[k]) + random.uniform(-float(delta), float(delta)),
                PARAM_BOUNDS[k][0],
                PARAM_BOUNDS[k][1]
            ))

    # Fixed omega values
    d["omega_head_gap"] = _round2(FIXED_OMEGA_HEAD_GAP)
    d["omega_corner_radius"] = _round2(FIXED_OMEGA_CORNER_RADIUS)
    d["coords"] = []
    d["Nodes"] = 0
    d["stage_name"] = "grid"
    d["baseline_id"] = "grid"
    return d


def _result_to_active_fitness(result):
    if ACTIVE_FITNESS == "fitness_paper":
        return result.get("fitness_paper")
    return result.get("fitness_lambda_over_mass")



def _is_repairable_failure(result):
    """
    Retry only design/geometry/simulation failures.
    Do not retry clear setup errors such as missing scripts, bad paths,
    syntax errors, missing Rhino Compute, or license/server problems.
    """
    if result is None:
        return True

    text = " ".join([
        str(result.get("failure_stage", "")),
        str(result.get("error", "")),
        str(result.get("stdout_tail", "")),
        str(result.get("stderr_tail", "")),
    ]).lower()

    non_repairable_markers = [
        "script not found",
        "not found:",
        "abaqus.bat not found",
        "master script not found",
        "grasshopper file not found",
        "base_dir not found",
        "working_dir not found",
        "syntaxerror",
        "indentationerror",
        "rhino compute server is not running",
        "license",
    ]

    for marker in non_repairable_markers:
        if marker in text:
            return False

    return True


def _repair_failed_design(design, attempt):
    """
    Fixed-grid repair strategy:
    - topology is fixed, so coords remain empty.
    - gently increase thickness and height within bounds.
    - fixed equal-bound parameters stay fixed.
    """
    d = dict(design)

    for k, bounds in PARAM_BOUNDS.items():
        lo, hi = bounds
        if abs(float(lo) - float(hi)) <= 1e-12 and k in d:
            d[k] = _round2(lo)

    if "Thickness_skin" in PARAM_BOUNDS:
        d["Thickness_skin"] = _round2(clamp(
            float(d["Thickness_skin"]) + REPAIR_THICKNESS_STEP * int(attempt),
            PARAM_BOUNDS["Thickness_skin"][0],
            PARAM_BOUNDS["Thickness_skin"][1]
        ))

    if "Thickness_stiff" in PARAM_BOUNDS:
        d["Thickness_stiff"] = _round2(clamp(
            float(d["Thickness_stiff"]) + REPAIR_THICKNESS_STEP * int(attempt),
            PARAM_BOUNDS["Thickness_stiff"][0],
            PARAM_BOUNDS["Thickness_stiff"][1]
        ))

    if "Height" in PARAM_BOUNDS:
        d["Height"] = _round2(clamp(
            float(d["Height"]) + REPAIR_HEIGHT_STEP * int(attempt),
            PARAM_BOUNDS["Height"][0],
            PARAM_BOUNDS["Height"][1]
        ))

    d["omega_head_gap"] = _round2(FIXED_OMEGA_HEAD_GAP)
    d["omega_corner_radius"] = _round2(FIXED_OMEGA_CORNER_RADIUS)
    d["coords"] = []
    d["Nodes"] = 0
    d["stage_name"] = "grid"
    d["baseline_id"] = "grid"
    return d


def evaluate_with_penalty(design, verbose=True):
    """
    Evaluate one GA candidate with limited repair/retry attempts.

    Attempt 0 evaluates the original design.
    Attempts 1..MAX_REPAIR_ATTEMPTS evaluate repaired designs.
    If all attempts fail, penalty fitness is assigned and the failed row
    remains in the CSV but is excluded from clean convergence plots.
    """
    original_design = dict(design)
    candidate = dict(design)
    last_result = None

    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        if attempt > 0:
            candidate = _repair_failed_design(candidate, attempt)
            print("\nGRID REPAIR RETRY %d / %d" % (attempt, MAX_REPAIR_ATTEMPTS))
            print("Design was repaired before re-evaluation.")

        result = evaluate_design(candidate, keep_temp_files=True, verbose=verbose)
        result["fitness"] = _result_to_active_fitness(result)

        if result.get("success") and result["fitness"] is not None:
            result["design"] = dict(candidate)
            result["original_design"] = dict(original_design)
            result["was_repaired"] = (attempt > 0)
            result["repair_attempt"] = attempt
            result["repair_failed_after_attempts"] = None
            return result

        last_result = result

        if not _is_repairable_failure(result):
            print("Failure does not look repairable. Skipping retries.")
            break

    result = last_result if last_result is not None else {}
    result["fitness"] = _result_to_active_fitness(result)

    if ACTIVE_FITNESS == "fitness_paper":
        if result["fitness"] is None:
            result["fitness"] = FAILED_FITNESS_PAPER
    else:
        if result["fitness"] is None:
            result["fitness"] = FAILED_FITNESS_LAMBDA_OVER_MASS

    result["design"] = dict(candidate)
    result["original_design"] = dict(original_design)
    result["was_repaired"] = True
    result["repair_attempt"] = None
    result["repair_failed_after_attempts"] = MAX_REPAIR_ATTEMPTS
    return result

def _is_better(a, b):
    if b is None:
        return True
    if ACTIVE_FITNESS == "fitness_paper":
        return a["fitness"] < b["fitness"]
    return a["fitness"] > b["fitness"]


def _sort_population(scored_population):
    if ACTIVE_FITNESS == "fitness_paper":
        return sorted(scored_population, key=lambda x: x["fitness"])
    return sorted(scored_population, key=lambda x: x["fitness"], reverse=True)


def tournament_select(scored_population):
    contenders = random.sample(scored_population, min(TOURNAMENT_K, len(scored_population)))
    contenders = _sort_population(contenders)
    return contenders[0]["design"]


def ensure_csv_header():
    if os.path.isfile(CSV_LOG):
        return
    with open(CSV_LOG, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "timestamp", "row_type", "generation", "index_in_generation", "global_evaluation",
            "success", "was_repaired", "repair_attempt", "repair_failed_after_attempts",
            "active_fitness_name", "fitness",
            "fitness_lambda_over_mass", "fitness_paper",
            "is_generation_best", "is_global_best_so_far",
            "mass", "lambda_1", "lambda_1_compression", "lambda_1_shear", "lambda_1_combined",
            "lambda_first_positive_compression", "lambda_first_positive_shear", "lambda_first_positive_combined",
            "Height", "Thickness_skin", "Thickness_stiff", "stud_max",
            "omega_head_width", "omega_head_gap", "omega_bottom_flange_width",
            "omega_web_angle_from_vertical", "omega_corner_radius",
            "elapsed_sec", "case_dir", "failure_stage", "error", "stdout_log", "stderr_log",
            "design_json", "original_design_json",
        ])


def append_log_row(row_type, generation, idx, result, is_generation_best=False, is_global_best_so_far=False):
    global GLOBAL_EVALUATION_COUNTER

    d = result["design"]

    if row_type == "evaluation":
        GLOBAL_EVALUATION_COUNTER += 1
        global_eval = GLOBAL_EVALUATION_COUNTER
    else:
        global_eval = ""

    with open(CSV_LOG, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            row_type,
            generation,
            idx,
            global_eval,
            result.get("success"),
            result.get("was_repaired", False),
            result.get("repair_attempt"),
            result.get("repair_failed_after_attempts"),
            ACTIVE_FITNESS,
            result.get("fitness"),
            result.get("fitness_lambda_over_mass"),
            result.get("fitness_paper"),
            is_generation_best,
            is_global_best_so_far,
            result.get("mass"),
            result.get("lambda_1_crit"),
            result.get("lambda_1_compression"),
            result.get("lambda_1_shear"),
            result.get("lambda_1_combined"),
            result.get("lambda_first_positive_compression"),
            result.get("lambda_first_positive_shear"),
            result.get("lambda_first_positive_combined"),
            "%.2f" % d.get("Height"),
            "%.2f" % d.get("Thickness_skin"),
            "%.2f" % d.get("Thickness_stiff"),
            "%.2f" % d.get("stud_max"),
            "%.2f" % d.get("omega_head_width"),
            "%.2f" % d.get("omega_head_gap"),
            "%.2f" % d.get("omega_bottom_flange_width"),
            "%.2f" % d.get("omega_web_angle_from_vertical"),
            "%.2f" % d.get("omega_corner_radius"),
            result.get("elapsed_sec"),
            result.get("case_dir"),
            result.get("failure_stage"),
            result.get("error"),
            result.get("stdout_log"),
            result.get("stderr_log"),
            json.dumps(d, sort_keys=True),
            json.dumps(result.get("original_design", {}), sort_keys=True),
        ])


def save_best(best_record):
    payload = {
        "active_fitness_name": ACTIVE_FITNESS,
        "fitness": best_record.get("fitness"),
        "fitness_lambda_over_mass": best_record.get("fitness_lambda_over_mass"),
        "fitness_paper": best_record.get("fitness_paper"),
        "mass": best_record.get("mass"),
        "lambda_1_crit": best_record.get("lambda_1_crit"),
        "lambda_first_positive_combined": best_record.get("lambda_first_positive_combined"),
        "design": best_record["design"],
        "case_dir": best_record.get("case_dir"),
        "summary_json": best_record.get("summary_json"),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(BEST_JSON, "w") as f:
        json.dump(payload, f, indent=4, sort_keys=True)


def result_from_scored_record(scored_record):
    return dict(scored_record)



def _to_float_or_none(v):
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(v)
    except:
        return None


def _to_int_or_none(v):
    try:
        if v is None or str(v).strip() == "":
            return None
        return int(float(v))
    except:
        return None


def _is_true(v):
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def generate_ga_convergence_plots():
    """
    Create clean convergence plots from CSV_LOG.
    Failed/penalty evaluations are excluded from the clean fitness plots.
    The failed rows remain in the CSV for traceability.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print("WARNING: Could not import matplotlib. Skipping plots:", e)
        return

    if not os.path.isfile(CSV_LOG):
        print("WARNING: CSV_LOG not found. Skipping plots:", CSV_LOG)
        return

    rows = []
    try:
        with open(CSV_LOG, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception as e:
        print("WARNING: Could not read CSV_LOG for plots:", e)
        return

    if not rows:
        print("WARNING: CSV_LOG is empty. Skipping plots.")
        return

    def clean_success(row):
        fp = _to_float_or_none(row.get("fitness_paper"))
        if fp is None:
            return False
        if fp >= FAILED_FITNESS_PAPER * 0.5:
            return False
        if not _is_true(row.get("success")):
            return False
        return True

    # --------------------------------------------------------
    # 1) fitness_paper vs continuous global_evaluation
    # --------------------------------------------------------
    eval_rows = [r for r in rows if r.get("row_type") == "evaluation" and clean_success(r)]
    xs, ys = [], []
    fallback_counter = 0
    for r in eval_rows:
        fallback_counter += 1
        ge = _to_int_or_none(r.get("global_evaluation"))
        if ge is None:
            ge = fallback_counter
        fp = _to_float_or_none(r.get("fitness_paper"))
        if fp is not None:
            xs.append(ge)
            ys.append(fp)

    if xs and ys:
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("Global evaluation")
        plt.ylabel("fitness_paper")
        plt.title("Fitness paper vs global evaluation")
        plt.grid(True)
        out_path = os.path.join(RESULTS_DIR, "fitness_paper_vs_global_evaluation.png")
        plt.tight_layout()
        plt.savefig(out_path, dpi=200)
        plt.close()
        print("Saved plot:", out_path)

    # --------------------------------------------------------
    # 2) generation best fitness
    # --------------------------------------------------------
    gen_rows = [r for r in rows if r.get("row_type") == "generation_best" and clean_success(r)]
    xs, ys = [], []
    for r in gen_rows:
        gen = _to_int_or_none(r.get("generation"))
        fp = _to_float_or_none(r.get("fitness_paper"))
        if gen is not None and fp is not None:
            xs.append(gen)
            ys.append(fp)

    if xs and ys:
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("Generation")
        plt.ylabel("generation best fitness_paper")
        plt.title("Generation best convergence")
        plt.grid(True)
        out_path = os.path.join(RESULTS_DIR, "fitness_paper_generation_best.png")
        plt.tight_layout()
        plt.savefig(out_path, dpi=200)
        plt.close()
        print("Saved plot:", out_path)

    # --------------------------------------------------------
    # 3) global best so far
    # --------------------------------------------------------
    gb_rows = [r for r in rows if r.get("row_type") == "global_best_so_far" and clean_success(r)]
    xs, ys = [], []
    for r in gb_rows:
        gen = _to_int_or_none(r.get("generation"))
        fp = _to_float_or_none(r.get("fitness_paper"))
        if gen is not None and fp is not None:
            xs.append(gen)
            ys.append(fp)

    if xs and ys:
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("Generation")
        plt.ylabel("global best fitness_paper")
        plt.title("Global best fitness convergence")
        plt.grid(True)
        out_path = os.path.join(RESULTS_DIR, "fitness_paper_global_best_so_far.png")
        plt.tight_layout()
        plt.savefig(out_path, dpi=200)
        plt.close()
        print("Saved plot:", out_path)

    # --------------------------------------------------------
    # 4) failed evaluations per generation
    # --------------------------------------------------------
    fail_counts = {}
    for r in rows:
        if r.get("row_type") != "evaluation":
            continue
        gen = _to_int_or_none(r.get("generation"))
        if gen is None:
            continue
        if not _is_true(r.get("success")):
            fail_counts[gen] = fail_counts.get(gen, 0) + 1

    if fail_counts:
        xs = sorted(fail_counts.keys())
        ys = [fail_counts[x] for x in xs]
        plt.figure()
        plt.bar(xs, ys)
        plt.xlabel("Generation")
        plt.ylabel("failed evaluations")
        plt.title("Failed evaluations per generation")
        plt.grid(True)
        out_path = os.path.join(RESULTS_DIR, "failed_evaluations_per_generation.png")
        plt.tight_layout()
        plt.savefig(out_path, dpi=200)
        plt.close()
        print("Saved plot:", out_path)


def run_ga():
    print("\n" + "#" * 100)
    print("ONE-STAGE OMEGA GRID GA")
    print("#" * 100)
    print("POP_SIZE      :", POP_SIZE)
    print("N_GENERATIONS :", N_GENERATIONS)
    print("ACTIVE_FITNESS:", ACTIVE_FITNESS)
    print("CSV_LOG       :", CSV_LOG)

    ensure_csv_header()

    evaluated_cache = {}
    population = [random_design() for _ in range(POP_SIZE)]
    global_best = None

    for gen in range(N_GENERATIONS):
        mut_rate = _adaptive_rate(gen, N_GENERATIONS, MUTATION_RATE_START, MUTATION_RATE_END)

        print("\n" + "=" * 100)
        print("GRID GA | GENERATION %d / %d" % (gen, N_GENERATIONS - 1))
        print("=" * 100)
        print("Mutation rate:", round(mut_rate, 4))

        scored_population = []

        for i, design in enumerate(population):
            print("\n" + "-" * 80)
            print("[GRID | GEN %d | EVAL %d/%d]" % (gen, i + 1, len(population)))
            print(json.dumps(design, indent=4, sort_keys=True))

            key = design_to_key(design)

            if key in evaluated_cache:
                result = dict(evaluated_cache[key])
                result["design"] = dict(design)
                print("Using cached result. Active fitness =", result["fitness"])
            else:
                result = evaluate_with_penalty(design, verbose=True)
                evaluated_cache[key] = dict(result)

            append_log_row("evaluation", gen, i, result)

            evaluated_design = result.get("design", design)
            scored_record = dict(result)
            scored_record["design"] = dict(evaluated_design)
            scored_record["fitness"] = result["fitness"]
            scored_population.append(scored_record)

            if _is_better(scored_record, global_best):
                global_best = dict(scored_record)
                save_best(global_best)

            print("Evaluation complete.")
            print("Success       :", result.get("success"))
            print("Case dir      :", result.get("case_dir"))
            print("Mass          :", result.get("mass"))
            print("Lambda_1_crit :", result.get("lambda_1_crit"))
            print("Fit L/M       :", result.get("fitness_lambda_over_mass"))
            print("Fit paper     :", result.get("fitness_paper"))

        scored_population = _sort_population(scored_population)
        generation_best = scored_population[0]

        append_log_row("generation_best", gen, -1, generation_best, is_generation_best=True)
        if global_best is not None:
            append_log_row("global_best_so_far", gen, -1, global_best, is_global_best_so_far=True)

        print("\nGENERATION BEST")
        print("Fitness:", generation_best.get("fitness"))
        print("Mass   :", generation_best.get("mass"))
        print("Lambda :", generation_best.get("lambda_1_crit"))
        print("Case   :", generation_best.get("case_dir"))

        # Elitism: carry best unchanged to next generation.
        next_population = [
            dict(scored_population[i]["design"])
            for i in range(min(ELITE_COUNT, len(scored_population)))
        ]

        while len(next_population) < POP_SIZE:
            p1 = tournament_select(scored_population)
            p2 = tournament_select(scored_population)
            child = crossover(p1, p2)
            child = mutate(child, gen)
            next_population.append(child)

        population = next_population

    print("\n" + "#" * 100)
    print("GRID GA FINISHED")
    print("#" * 100)
    if global_best is not None:
        print("Best fitness:", global_best.get("fitness"))
        print("Best mass   :", global_best.get("mass"))
        print("Best lambda :", global_best.get("lambda_1_crit"))
        print("Best case   :", global_best.get("case_dir"))
        print("Best JSON   :", BEST_JSON)
    generate_ga_convergence_plots()
    print("CSV_LOG:", CSV_LOG)


if __name__ == "__main__":
    run_ga()
