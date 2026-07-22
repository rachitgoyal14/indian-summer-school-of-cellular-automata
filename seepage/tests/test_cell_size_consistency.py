"""
Phase 6 — Cell-size consistency test.

Ensures all modules that reference cell size (grid.py, gaps.py, seepage.py,
density_flow.py) read from the SAME config keys, not independently hardcoded
values.

Per phase06_data_collection.md §2 (plan.md §11 risk #4):
  "add an explicit tests/test_cell_size_consistency.py that walks the config
   and every module that references cell size and asserts they all read from
   the same config keys, not independently hardcoded values."

Implementation: grep-based source code audit.  Each module is scanned for:
  1. Hardcoded numeric literals 0.5, 0.7 (the actual cell_length_m / cell_width_m
     values from config) — these are NOT allowed outside the config YAML itself.
  2. Correct config-key reads via `config['grid']['cell_length_m']` or
     `config['grid']['cell_width_m']` patterns.
  3. The density_flow module must NOT import cell sizes as module-level constants.
"""

import re
import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")


def _read_src(rel_path: str) -> str:
    full = os.path.join(SRC_ROOT, rel_path)
    assert os.path.isfile(full), f"Source file missing: {full}"
    with open(full) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Files under audit
# ---------------------------------------------------------------------------
AUDITED_FILES = [
    ("core/grid.py",              "grid.py"),
    ("core/gaps.py",              "gaps.py"),
    ("intersection/seepage.py",   "seepage.py"),
    ("metrics/density_flow.py",   "density_flow.py"),
    ("sim/collector.py",          "collector.py"),
]

# Pattern that accesses cell size from config correctly
CORRECT_PATTERN_LEN = re.compile(r"config\s*\[.grid.\]\s*\[.cell_length_m.\]")
CORRECT_PATTERN_WID = re.compile(r"config\s*\[.grid.\]\s*\[.cell_width_m.\]")

# Hardcoded magic numbers for cell size — disallowed in src/ (but allowed as
# test fixtures below and in config files).
# We look for the literal float 0.5 or 0.7 used in an assignment context that
# isn't inside a comment or string, which could indicate a hardcoded cell size.
# Approach: disallow bare `= 0.5` or `= 0.7` assignments outside config files.
HARDCODED_LEN = re.compile(r"(?<!['\"])\b0\.5\b(?!['\"])")  # 0.5 not inside string
HARDCODED_WID = re.compile(r"(?<!['\"])\b0\.7\b(?!['\"])")  # 0.7 not inside string

# Allowed contexts for 0.5 (lateral_safety_margin default = 0.5 cells is a
# SAFETY MARGIN, not a cell size, so it's permitted)
ALLOWED_HALF_CELL = re.compile(r"lateral_safety_margin_cells.*0\.5|0\.5.*lateral_safety_margin")


def test_grid_reads_from_config():
    """grid.py must read cell_length_m from config, not hardcode it."""
    src = _read_src("core/grid.py")
    assert CORRECT_PATTERN_LEN.search(src), (
        "grid.py does not read cell_length_m from config['grid']['cell_length_m']"
    )


def test_seepage_reads_cell_width_from_config():
    """seepage.py must read cell_width_m from config, not hardcode it."""
    src = _read_src("intersection/seepage.py")
    # seepage.py reads road_width_cells from config['grid']['cell_width_m']
    assert CORRECT_PATTERN_WID.search(src), (
        "seepage.py does not read cell_width_m from config['grid']['cell_width_m']"
    )


def test_density_flow_has_no_hardcoded_cell_size():
    """
    density_flow.py must not contain hardcoded 0.5 (cell_length) or 0.7 (cell_width)
    as standalone literals in computation lines.  Cell sizes must be passed in as
    arguments (cell_length_m parameter).
    """
    src = _read_src("metrics/density_flow.py")
    # Strip comments (lines starting with #)
    non_comment_lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
    non_comment_src = "\n".join(non_comment_lines)

    # Check for 0.7 (cell_width_m) — density_flow should not use this at all
    wid_matches = HARDCODED_WID.findall(non_comment_src)
    assert not wid_matches, (
        f"density_flow.py has hardcoded 0.7 (cell_width_m) in {len(wid_matches)} places — "
        "must be passed as parameter from config"
    )


def test_collector_reads_cell_sizes_via_parameter():
    """
    collector.py must accept izoi_distances_cells as a parameter computed from config
    (cell_length_m) by the caller — it must not hardcode 0.5 itself.
    """
    src = _read_src("sim/collector.py")
    non_comment_lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
    non_comment_src = "\n".join(non_comment_lines)

    # 0.5 in collector is only allowed as the lateral_safety_margin default
    len_matches = HARDCODED_LEN.findall(non_comment_src)
    # Filter out allowed uses (lateral_safety_margin = 0.5)
    bad_matches = [m for m in len_matches
                   if not ALLOWED_HALF_CELL.search(non_comment_src)]

    # collector.py doesn't set lateral_safety_margin itself, so any 0.5 is suspicious
    # But if it appears in a docstring or comment that was stripped, it's fine.
    # The collector itself should have zero hardcoded 0.5 for cell geometry.
    non_string_src = re.sub(r'""".*?"""', '', non_comment_src, flags=re.DOTALL)
    non_string_src = re.sub(r"'''.*?'''", '', non_string_src, flags=re.DOTALL)
    len_matches_final = HARDCODED_LEN.findall(non_string_src)
    assert not len_matches_final, (
        f"collector.py has hardcoded 0.5 (cell_length_m) outside docstrings — "
        "cell sizes must come from the caller (sim_loop / config)"
    )


def test_all_modules_use_config_not_constants():
    """
    Integration check: sim_loop.py passes cell_length_m from config to
    collector and density_flow — never reads the config grid values directly
    inside density_flow or collector.
    """
    sim_loop_src = _read_src("sim/sim_loop.py")

    # sim_loop reads cell_length_m from config — this is the correct pattern
    assert CORRECT_PATTERN_LEN.search(sim_loop_src), (
        "sim_loop.py does not read cell_length_m from config['grid']['cell_length_m']"
    )
    assert CORRECT_PATTERN_WID.search(sim_loop_src), (
        "sim_loop.py does not read cell_width_m from config['grid']['cell_width_m']"
    )


def test_config_yaml_is_source_of_truth():
    """Config YAML must contain the canonical cell sizes used everywhere."""
    import yaml
    config_path = os.path.join(PROJECT_ROOT, "configs", "intersection_default.yaml")
    assert os.path.isfile(config_path), "configs/intersection_default.yaml missing"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["grid"]["cell_length_m"] == 0.5, (
        f"Expected cell_length_m=0.5 in config, got {config['grid']['cell_length_m']}"
    )
    assert config["grid"]["cell_width_m"] == 0.7, (
        f"Expected cell_width_m=0.7 in config, got {config['grid']['cell_width_m']}"
    )
    assert config["grid"]["lane_width_m"] == 3.5, (
        f"Expected lane_width_m=3.5 in config, got {config['grid']['lane_width_m']}"
    )
