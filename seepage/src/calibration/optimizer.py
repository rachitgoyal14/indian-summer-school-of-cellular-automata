"""
Phase 7 — Two-stage calibration optimizer.

Stage 1 (Global): NSGA-II via pymoo, collapsed to single-objective by
  summing all Eq 16 error terms into one scalar.

  SIMPLIFICATION NOTE (plan.md §11 risk #3): The Kanagaraj paper uses
  MATLAB's gamultiobj (true multi-objective GA) + goal-attainment. We use
  NSGA-II with a single scalar objective (the sum of squared relative
  errors per Eq 16). This is algorithmically acceptable because the paper's
  multi-objective formulation's multiple objectives all reduce to one Eq 16
  expression in the cited implementation; the gamultiobj→NSGA-II change
  does not claim exact parameter-value replication.

Stage 2 (Local): scipy Nelder-Mead starting from Stage 1 best, for
  refinement on the (non-smooth, stochastic) objective.

PARAMETER SPACE (reduced_mode=True — 12 dimensions):
  max_speed_cells_per_step  × 4 modes
  p_slowdown                × 4 modes
  lane_change_prob          × 4 modes

PARAMETER SPACE (reduced_mode=False — 20 dimensions):
  Above 12 + max_accel_cells_per_step2 × 4 modes
            + position_preference      × 4 modes

  Note: IZOI and seepage safety margins remain at paper values because
  they are not observable in midblock data (no signal, no intersection).
"""

from __future__ import annotations

import copy
import time
import csv
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from src.calibration.objective import calibration_objective


# ---------------------------------------------------------------------------
# Parameter search space
# ---------------------------------------------------------------------------

MODES = ["two_wheeler", "three_wheeler", "car", "bus"]

# (param_key, mode, lower_bound, upper_bound)
# Bounds are physically motivated: speed in [10,40] cells/step (5–20 m/s),
# probabilities in [0.01, 0.99].
REDUCED_PARAMS: List[Tuple[str, str, float, float]] = [
    # max_speed_cells_per_step — two_wheeler fastest (order preserved by bounds)
    ("max_speed_cells_per_step", "two_wheeler",   24, 40),
    ("max_speed_cells_per_step", "three_wheeler", 18, 32),
    ("max_speed_cells_per_step", "car",           18, 32),
    ("max_speed_cells_per_step", "bus",           10, 22),
    # p_slowdown (NaSch randomisation probability)
    ("p_slowdown", "two_wheeler",   0.05, 0.50),
    ("p_slowdown", "three_wheeler", 0.05, 0.55),
    ("p_slowdown", "car",           0.05, 0.50),
    ("p_slowdown", "bus",           0.05, 0.55),
    # lane_change_prob
    ("lane_change_prob", "two_wheeler",   0.20, 0.90),
    ("lane_change_prob", "three_wheeler", 0.10, 0.70),
    ("lane_change_prob", "car",           0.05, 0.50),
    ("lane_change_prob", "bus",           0.01, 0.30),
]

FULL_PARAMS: List[Tuple[str, str, float, float]] = REDUCED_PARAMS + [
    ("max_accel_cells_per_step2", "two_wheeler",   1, 5),
    ("max_accel_cells_per_step2", "three_wheeler", 1, 4),
    ("max_accel_cells_per_step2", "car",           1, 4),
    ("max_accel_cells_per_step2", "bus",           1, 3),
    ("position_preference", "two_wheeler",   0.0, 1.0),
    ("position_preference", "three_wheeler", 0.0, 0.8),
    ("position_preference", "car",           0.0, 0.6),
    ("position_preference", "bus",           0.0, 0.5),
]


def _params_from_vector(x: np.ndarray, param_defs: List[Tuple]) -> Dict[str, Any]:
    """Convert flat parameter vector to nested params dict."""
    mode_params: Dict[str, Dict] = {m: {} for m in MODES}
    for i, (key, mode, lo, hi) in enumerate(param_defs):
        val = float(np.clip(x[i], lo, hi))
        if key in ("max_speed_cells_per_step", "max_accel_cells_per_step2"):
            val = int(round(val))
        mode_params[mode][key] = val
    return {"mode_params": mode_params}


def _objective_from_vector(
    x: np.ndarray,
    param_defs: List[Tuple],
    config_template: Dict,
    field_fd: pd.DataFrame,
    rng_seed: int,
    window_s: int,
) -> float:
    params = _params_from_vector(x, param_defs)
    return calibration_objective(params, config_template, field_fd, rng_seed, window_s)


# ---------------------------------------------------------------------------
# Stage 1: NSGA-II (single-objective via pymoo)
# ---------------------------------------------------------------------------

class _SingleObjProblem:
    """pymoo Problem wrapper for single-objective NSGA-II."""

    def __init__(self, param_defs, config_template, field_fd, rng_seed, window_s):
        self.param_defs = param_defs
        self.config_template = config_template
        self.field_fd = field_fd
        self.rng_seed = rng_seed
        self.window_s = window_s
        self.n_var = len(param_defs)
        self.xl = np.array([lo for _, _, lo, hi in param_defs])
        self.xu = np.array([hi for _, _, lo, hi in param_defs])

    def evaluate(self, X, out):
        """Evaluate a population matrix X (n_pop × n_var)."""
        F = []
        for x in X:
            f = _objective_from_vector(
                x, self.param_defs, self.config_template,
                self.field_fd, self.rng_seed, self.window_s
            )
            F.append([f])
        out["F"] = np.array(F)


def run_nsga2(
    param_defs: List[Tuple],
    config_template: Dict,
    field_fd: pd.DataFrame,
    rng_seed: int,
    window_s: int,
    pop_size: int = 30,
    n_gen: int = 20,
    convergence_log: Optional[List] = None,
    verbose: bool = True,
) -> Tuple[np.ndarray, float]:
    """
    Run NSGA-II and return (best_x, best_f).

    convergence_log: list to append (gen, best_f, wall_time) tuples.
    """
    from pymoo.algorithms.soo.nonconvex.ga import GA
    from pymoo.core.problem import Problem
    from pymoo.optimize import minimize
    from pymoo.termination import get_termination

    class _Prob(Problem):
        def __init__(prob_self):
            super().__init__(
                n_var=len(param_defs),
                n_obj=1,
                xl=np.array([lo for _, _, lo, hi in param_defs]),
                xu=np.array([hi for _, _, lo, hi in param_defs]),
            )

        def _evaluate(prob_self, X, out, *args, **kwargs):
            F = []
            for x in X:
                f = _objective_from_vector(
                    x, param_defs, config_template,
                    field_fd, rng_seed, window_s
                )
                F.append([f])
            out["F"] = np.array(F)

    from pymoo.algorithms.soo.nonconvex.ga import GA
    from pymoo.operators.crossover.sbx import SBX
    from pymoo.operators.mutation.pm import PolynomialMutation
    from pymoo.operators.sampling.rnd import FloatRandomSampling

    algorithm = GA(
        pop_size=pop_size,
        sampling=FloatRandomSampling(),
        crossover=SBX(prob=0.9, eta=15),
        mutation=PolynomialMutation(prob=1.0 / len(param_defs), eta=20),
        eliminate_duplicates=True,
    )

    t0 = time.time()
    best_per_gen = []

    from pymoo.core.callback import Callback

    class _LogCallback(Callback):
        def notify(self, algorithm):
            gen = algorithm.n_gen
            best_f = algorithm.pop.get("F").min()
            elapsed = time.time() - t0
            best_per_gen.append((gen, float(best_f), elapsed))
            if convergence_log is not None:
                convergence_log.append((gen, float(best_f), elapsed))
            if verbose:
                print(f"    Gen {gen:3d}: best={best_f:.5f}  elapsed={elapsed:.1f}s")

    res = minimize(
        _Prob(),
        algorithm,
        termination=get_termination("n_gen", n_gen),
        seed=rng_seed,
        callback=_LogCallback(),
        verbose=False,
    )

    best_x = res.X
    best_f = float(res.F[0])
    return best_x, best_f


# ---------------------------------------------------------------------------
# Stage 2: Nelder-Mead local refinement
# ---------------------------------------------------------------------------

def run_nelder_mead(
    x0: np.ndarray,
    param_defs: List[Tuple],
    config_template: Dict,
    field_fd: pd.DataFrame,
    rng_seed: int,
    window_s: int,
    max_iter: int = 50,
    verbose: bool = True,
) -> Tuple[np.ndarray, float]:
    from scipy.optimize import minimize

    xl = np.array([lo for _, _, lo, hi in param_defs])
    xu = np.array([hi for _, _, lo, hi in param_defs])
    call_count = [0]

    def _obj(x):
        x_clipped = np.clip(x, xl, xu)
        f = _objective_from_vector(
            x_clipped, param_defs, config_template,
            field_fd, rng_seed, window_s
        )
        call_count[0] += 1
        if verbose and call_count[0] % 5 == 0:
            print(f"    Nelder-Mead iter {call_count[0]}: f={f:.5f}")
        return f

    result = minimize(
        _obj, x0,
        method="Nelder-Mead",
        options={"maxiter": max_iter, "xatol": 1e-4, "fatol": 1e-4, "disp": False},
    )
    return np.clip(result.x, xl, xu), float(result.fun)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_calibration(
    config_template: Dict,
    field_data_path: str,
    reduced_mode: bool = True,
    pop_size: int = 30,
    n_gen: int = 20,
    nm_max_iter: int = 50,
    window_s: int = 300,
    rng_seed: int = 42,
    convergence_csv: str = "data/processed/calibration_convergence.csv",
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Run two-stage calibration and return best parameter dict.

    Writes convergence log to convergence_csv (gen, best_objective, wall_time_s).
    """
    from src.calibration.objective import build_field_fd

    param_defs = REDUCED_PARAMS if reduced_mode else FULL_PARAMS
    n_dim = len(param_defs)

    if verbose:
        mode_str = "REDUCED (12-dim)" if reduced_mode else "FULL (20-dim)"
        print(f"\n=== Phase 7 Calibration ({mode_str}) ===")
        print(f"  Pop size: {pop_size}, Generations: {n_gen}, NM max_iter: {nm_max_iter}")
        print(f"  Window: {window_s}s, Seed: {rng_seed}")

    # --- Load and pre-process field data ---
    field_df = pd.read_csv(field_data_path)
    road_length_m = float(field_df["x_m"].max())
    cell_length_m = config_template["grid"]["cell_length_m"]

    if verbose:
        print(f"\nField data: {len(field_df)} rows, "
              f"road={road_length_m:.1f}m, "
              f"t={field_df['time_s'].min():.1f}..{field_df['time_s'].max():.1f}s")

    field_fd = build_field_fd(field_df, window_s, road_length_m, cell_length_m)
    if verbose:
        print(f"Field FD bins: {len(field_fd)}")
        print(f"Field flow range: {field_fd['flow_veh_per_hr'].min():.0f}"
              f"..{field_fd['flow_veh_per_hr'].max():.0f} veh/hr")
        print(f"Field density range: {field_fd['density_veh_per_km'].min():.1f}"
              f"..{field_fd['density_veh_per_km'].max():.1f} veh/km")

    convergence_log = []
    t_total_start = time.time()

    # --- Stage 1: Global GA ---
    if verbose:
        print(f"\nStage 1: NSGA-II (pop={pop_size}, gen={n_gen})...")
    best_x_ga, best_f_ga = run_nsga2(
        param_defs, config_template, field_fd,
        rng_seed, window_s, pop_size, n_gen,
        convergence_log=convergence_log, verbose=verbose,
    )
    if verbose:
        print(f"Stage 1 best: f={best_f_ga:.5f}")

    # --- Stage 2: Local Nelder-Mead ---
    if verbose:
        print(f"\nStage 2: Nelder-Mead (max_iter={nm_max_iter})...")
    best_x_nm, best_f_nm = run_nelder_mead(
        best_x_ga, param_defs, config_template, field_fd,
        rng_seed, window_s, nm_max_iter, verbose=verbose,
    )
    if verbose:
        print(f"Stage 2 best: f={best_f_nm:.5f} (improved by {best_f_ga - best_f_nm:.5f})")

    total_wall_s = time.time() - t_total_start
    if verbose:
        print(f"\nTotal wall-clock time: {total_wall_s:.1f}s ({total_wall_s/60:.1f} min)")

    # --- Write convergence log ---
    Path(convergence_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(convergence_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["generation", "best_objective", "wall_time_s"])
        for row in convergence_log:
            writer.writerow(row)

    # --- Build best params dict ---
    best_params = _params_from_vector(best_x_nm, param_defs)
    best_params["_meta"] = {
        "reduced_mode": reduced_mode,
        "n_dim": n_dim,
        "pop_size": pop_size,
        "n_gen": n_gen,
        "nm_max_iter": nm_max_iter,
        "window_s": window_s,
        "rng_seed": rng_seed,
        "best_f_ga": best_f_ga,
        "best_f_nm": best_f_nm,
        "wall_time_s": total_wall_s,
    }

    return best_params
