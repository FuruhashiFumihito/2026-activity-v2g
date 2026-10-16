#!/usr/bin/env python3
"""Run the pre-specified Bryan waiting/contract diagnostic into a fresh folder."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
import scipy

from model import CONTRACTS, MONEY, PATTERNS, TOL, Problem, clean, parameters, scenarios, solve_bundle
from analytic_checks import analytic_comparison


def save_json(path, value):
    path.write_text(json.dumps(clean(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def command_output(command, cwd=None):
    try:
        return subprocess.check_output(command, cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(clean(rows))


def case_grid(smoke=False):
    if smoke:
        return [("deterministic", 0.0), ("uniform_activity", 0.0), ("uniform_activity", .5), ("uniform_activity", 1.0), ("education_cancel", .75), ("shopping_cancel", .5)]
    return [("deterministic", 0.0)] + [(family, p) for family in ["uniform_activity", "education_cancel", "shopping_cancel"] for p in [0.0, .25, .5, .75, 1.0]]


def connection_grid(smoke=False):
    if smoke:
        return [4.0, 4.5, 5.0, 7.0]
    values = list(np.linspace(1, 7, 73))
    boundaries = [4.05, 4.55]
    for p in [.25, .5, .75]:
        # Aux education-cancellation and primary uniform-occurrence switches.
        for value in [4.05 + 1.08 * p / (3.31 * (1 - p)), 4.05 + 1.08 * (1 - p) / (3.31 * p)]:
            if 4.05 <= value <= 4.55:
                boundaries.append(value)
    for value in boundaries:
        values.extend([value - 1 / 60, value, value + 1 / 60])
    values.extend([4, 4.5, 5, 7])
    return sorted({round(float(value), 12) for value in values if 1 <= value <= 7})


def expected_route(bundle, pattern=None):
    pattern = bundle["canonical_pattern"] if pattern is None else pattern
    if pattern not in bundle["schedules"]:
        return None
    return sum(state["probability"] * state["route_km"] for state in bundle["schedules"][pattern])


def expected_waiting(bundle, pattern=None):
    pattern = bundle["canonical_pattern"] if pattern is None else pattern
    if pattern not in bundle["schedules"]:
        return None
    return sum(state["probability"] * state["waiting_hours"] for state in bundle["schedules"][pattern])


def compensation(solution, baseline):
    return (solution["minimum_disutility"] - baseline["canonical"]["minimum_disutility"]) / MONEY if solution["success"] else None


def rate(burden, expected_q):
    if burden is None:
        return None, "infeasible"
    if expected_q > TOL:
        return burden / expected_q, "defined"
    if abs(burden) <= TOL:
        return None, "no_delivery_zero_burden"
    assert burden > 0, (burden, expected_q)
    return None, "no_delivery_positive_burden"


def identities(family, p, gamma, contract, connection):
    return {"gamma": gamma, "scenario": family, "p": p, "probability_type": "occurrence" if family == "uniform_activity" else "cancellation" if family.endswith("_cancel") else "deterministic", "departure_policy": "fixed_07" if family == "uniform_activity" else "flexible", "contract": contract, "D_hours": connection}


def schedule_record(bundle, method, pattern=None):
    pattern = bundle["canonical_pattern"] if pattern is None else pattern
    solution = bundle["fixed"][pattern]
    return {**identities(bundle["family"], bundle["probability"], bundle["gamma"], bundle["contract"], bundle["D_hours"]), "method": method, "status": solution["status"], "success": solution["success"], "pattern": pattern, "minimum_disutility": solution["minimum_disutility"], "expected_delivery_kWh": bundle["expected_delivery_kWh"], "states": bundle["schedules"].get(pattern, [])}


def light_raw(bundle):
    return {key: value for key, value in bundle.items() if key != "schedules"}


def collect_solver_rows(bundle, rows):
    ids = identities(bundle["family"], bundle["probability"], bundle["gamma"], bundle["contract"], bundle["D_hours"])
    solutions = [("MILP", bundle["full"])] + [("fixed_" + pattern, bundle["fixed"][pattern]) for pattern in PATTERNS] + [("independent_" + pattern, bundle["independent"][pattern]) for pattern in PATTERNS]
    for label, solution in solutions:
        rows.append({**ids, "solver_role": label, "status": solution["status"], "success": solution["success"], "minimum_disutility": solution["minimum_disutility"], "mip_gap": solution.get("mip_gap"), "mip_dual_bound": solution.get("mip_dual_bound"), "max_primal_violation": solution.get("max_primal_violation"), "max_integrality_residual": solution.get("max_integrality_residual"), "max_complementarity_residual": solution.get("max_complementarity_residual"), "elapsed_seconds": solution["elapsed_seconds"]})


def collect_soc_rows(bundle, rows):
    ids = identities(bundle["family"], bundle["probability"], bundle["gamma"], bundle["contract"], bundle["D_hours"])
    for pattern, states in bundle["schedules"].items():
        for state in states:
            soc = state["soc"]
            rows.append({**ids, "pattern": pattern, "state": state["name"], "state_probability": state["probability"], "education_available": state["education_available"], "shopping_A_available": state["shopping_A_available"], "shopping_B_available": state["shopping_B_available"], "actual_shop": state["actual_shop"], "route_km": state["route_km"], "route_energy_kWh": state["route_energy_kWh"], "delivered_kWh": state["q_kWh"], "initial_energy_kWh": soc["initial_energy_kWh"], "home_arrival_energy_kWh": soc["home_arrival_energy_kWh"], "final_energy_kWh": soc["final_energy_kWh"], "minimum_energy_kWh": soc["minimum_energy_kWh"], "recharge_kWh": soc["recharge_kWh"], "recharge_end_h": soc["recharge_end_h"], "waiting_hours": state["waiting_hours"], "campus_waiting_hours": state["campus_waiting_hours"], "downtown_waiting_hours": state["downtown_waiting_hours"], "all_checks_pass": soc["all_checks_pass"], "failed_checks": ";".join(name for name, passed in soc["checks"].items() if not passed)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true", help="small diagnostic matrix; not the final full-grid experiment")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error(f"refusing to overwrite existing output directory: {output}")
    output.mkdir(parents=True)
    source_dir = Path(__file__).resolve().parent
    snapshot_dir = output / "source_snapshot"
    snapshot_dir.mkdir()
    source_files = ["model.py", "run.py", "analytic_checks.py", "settings_contract.md"]
    hashes = {}
    for name in source_files:
        source = source_dir / name
        data = source.read_bytes()
        (snapshot_dir / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    gammas = [0.0, .03915]
    cases, connections = case_grid(args.smoke), connection_grid(args.smoke)
    config = {"run_id": output.name, "smoke_only": args.smoke, "design_source": "source_snapshot/settings_contract.md", "source_DOI": "https://doi.org/10.1016/j.trd.2025.104911", "source_pages": {"profile": "Table 3 p. 11", "coefficients": "Table 4 p. 12; Table A.1 p. 23"}, **parameters(), "cases": [{"scenario": family, "p": p, "p_meaning": "common independent candidate occurrence probability" if family == "uniform_activity" else "cancellation probability in an auxiliary control" if family.endswith("_cancel") else "deterministic", "departure_policy": "fixed_07" if family == "uniform_activity" else "flexible"} for family, p in cases], "gamma_values": gammas, "D_hours": connections, "contracts": list(CONTRACTS), "reference_D_hours": 4.0, "reference_plan_tie_rule": "A then B then none at equal primary optimum", "continuous_timing_tie_rule": "earliest summed campus departure and shopping starts at exact fixed-plan primary optimum", "fixed_payment": "ex-ante enrollment grant retained in released states; no refund or release fee", "unit_payment": "constant CHF/kWh with risk-neutral expectation and compulsory exogenous dispatch; Eq=0 yields no finite rate, with distinct zero/positive-burden statuses", "state_structure": "uniform_activity independently realizes Education, Shopping A, Shopping B with common occurrence p; planned location remains common and unavailable selected shopping is skipped", "uniform_recourse_boundary": "fixed common planned location, order, initial departure 07:00, and education duration across realized states; scenario-contingent permitted start times, physical departure and waiting; no post-realization location substitution", "zero_probability_states": "excluded before constructing constraints", "replications_and_seed": "NA deterministic exact finite-state expectation", "source_sha256": hashes, "starting_git_revision": command_output(["git", "rev-parse", "HEAD"], source_dir), "starting_git_status": command_output(["git", "status", "--short"], source_dir), "run_command": " ".join(sys.argv)}
    # The complete settings and exact source snapshots precede the first solve.
    save_json(output / "config.json", config)
    save_json(output / "environment.json", {"python": sys.version, "executable": sys.executable, "numpy": np.__version__, "scipy": scipy.__version__, "platform": platform.platform(), "machine": platform.machine(), "thread_environment": {key: os.environ.get(key) for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]}, "solver": "HiGHS bundled with SciPy", "source_sha256": hashes})
    rows, solver_rows, soc_rows, schedule_records, reference_rows, hand_rows = [], [], [], [], [], []
    audit = {"max_fixed_independent_error_utility": 0.0, "max_MILP_enumeration_error_utility": 0.0, "max_state_objective_error_utility": 0.0, "max_analytic_error_CHF": 0.0, "max_expected_delivery_analytic_error_kWh": 0.0, "max_reference_dual_finite_difference_error_utility_per_hour": 0.0, "max_MILP_gap": 0.0, "max_primal_violation": 0.0, "analytic_values_checked": 0, "feasibility_checks": 0, "bundle_count": 0, "zero_probability_states_excluded": True}
    start = time.perf_counter()

    def accept_bundle(bundle, raw):
        audit["bundle_count"] += 1
        audit["max_fixed_independent_error_utility"] = max(audit["max_fixed_independent_error_utility"], bundle["max_fixed_independent_error_utility"])
        audit["max_MILP_enumeration_error_utility"] = max(audit["max_MILP_enumeration_error_utility"], bundle["milp_enumeration_error_utility"])
        audit["max_state_objective_error_utility"] = max(audit["max_state_objective_error_utility"], bundle["max_state_objective_error_utility"])
        audit["max_MILP_gap"] = max(audit["max_MILP_gap"], bundle["full"]["mip_gap"] or 0)
        for sol in [bundle["full"], *bundle["fixed"].values()]:
            if sol["success"]:
                audit["max_primal_violation"] = max(audit["max_primal_violation"], sol["max_primal_violation"])
        collect_solver_rows(bundle, solver_rows)
        collect_soc_rows(bundle, soc_rows)
        raw.write(json.dumps(clean(light_raw(bundle)), separators=(",", ":"), allow_nan=False) + "\n")

    with gzip.open(output / "solver_records.jsonl.gz", "wt", encoding="utf-8") as raw:
        for gamma in gammas:
            for family, p in cases:
                baseline = solve_bundle(family, p, gamma, "none", 0.0)
                accept_bundle(baseline, raw)
                schedule_records.append(schedule_record(baseline, "nonjoin"))
                baseline_route = expected_route(baseline)
                for contract in CONTRACTS:
                    reference = solve_bundle(family, p, gamma, contract, 4.0)
                    ref_pattern = reference["canonical_pattern"]
                    ref_lp = reference["fixed"][ref_pattern]
                    ref_F = compensation(ref_lp, baseline)
                    ref_dual = ref_lp["derivative_D_utility_per_hour"]
                    policy = "fixed_07" if family == "uniform_activity" else "flexible"
                    state_items = scenarios(family, p)
                    left = Problem(state_items, gamma, contract, 4 - 1 / 60, family, policy).solve(ref_pattern)
                    right = Problem(state_items, gamma, contract, 4 + 1 / 60, family, policy).solve(ref_pattern)
                    assert left["success"] and right["success"]
                    derivative = (right["minimum_disutility"] - left["minimum_disutility"]) / (2 / 60)
                    dual_error = abs(derivative - ref_dual)
                    assert dual_error < TOL, (family, p, gamma, contract, ref_dual, derivative)
                    audit["max_reference_dual_finite_difference_error_utility_per_hour"] = max(audit["max_reference_dual_finite_difference_error_utility_per_hour"], dual_error)
                    reference_rows.append({**identities(family, p, gamma, contract, 4.0), "reference_pattern": ref_pattern, "reference_tie_patterns": ";".join(reference["tie_patterns"]), "reference_compensation_CHF": ref_F, "reference_dual_utility_per_hour": ref_dual, "reference_dual_CHF_per_hour": ref_dual / MONEY, "finite_difference_utility_per_hour": derivative, "absolute_dual_error": dual_error, "B_alt_reference_is_optimal": "B" in reference["tie_patterns"]})
                    raw.write(json.dumps(clean({"record_type": "reference_dual_finite_difference", **identities(family, p, gamma, contract, 4.0), "fixed_pattern": ref_pattern, "left": left, "right": right}), separators=(",", ":"), allow_nan=False) + "\n")
                    for d in connections:
                        bundle = reference if d == 4 else solve_bundle(family, p, gamma, contract, d)
                        accept_bundle(bundle, raw)
                        b, balt, c = bundle["fixed"][ref_pattern], bundle["fixed"]["B"], bundle["canonical"]
                        comp = {"A": ref_F + ref_dual / MONEY * (d - 4), "B": compensation(b, baseline), "B_alt": compensation(balt, baseline), "C": compensation(c, baseline)}
                        expected_q = bundle["expected_delivery_kWh"]
                        expected_connection = bundle["full_service_probability"] * (1 if contract == "event_only" else d)
                        rates = {method: rate(comp[method], expected_q) for method in ["A", "B", "B_alt", "C"]}
                        expected_route_c = expected_route(bundle)
                        row = {**identities(family, p, gamma, contract, d), **{method + "_compensation_CHF": comp[method] for method in ["A", "B", "B_alt", "C"]}, "B_status": b["status"], "B_alt_status": balt["status"], "C_status": bundle["full"]["status"], "reference_pattern": ref_pattern, "reference_tie_patterns": ";".join(reference["tie_patterns"]), "B_alt_reference_is_optimal": "B" in reference["tie_patterns"], "B_pattern": ref_pattern, "B_alt_pattern": "B", "C_pattern": bundle["canonical_pattern"], "expected_delivery_kWh": expected_q, "full_service_probability": bundle["full_service_probability"], "expected_connection_hours": expected_connection, "baseline_expected_route_km": baseline_route, "C_expected_route_km": expected_route_c, "C_expected_extra_route_km": expected_route_c - baseline_route, "baseline_expected_waiting_hours": expected_waiting(baseline), "C_expected_waiting_hours": expected_waiting(bundle), "C_expected_extra_waiting_hours": expected_waiting(bundle) - expected_waiting(baseline)}
                        for method in ["A", "B", "B_alt", "C"]:
                            row[method + "_delivery_rate_CHF_per_kWh"], row[method + "_rate_status"] = rates[method]
                        rows.append(row)
                        oracle = analytic_comparison(d, probability=p, family=family, contract=contract, gamma=gamma, reference_D=4.0, reference_pattern=ref_pattern)
                        for method in ["A", "B", "B_alt", "C"]:
                            key = method + "_compensation_CHF"
                            actual, expected = comp[method], oracle[key]
                            same_feasibility = (actual is None) == (expected is None)
                            assert same_feasibility, (family, p, gamma, contract, d, method, actual, expected)
                            audit["feasibility_checks"] += 1
                            error = abs(actual - expected) if actual is not None else None
                            if error is not None:
                                assert error < TOL, (family, p, gamma, contract, d, method, actual, expected)
                                audit["max_analytic_error_CHF"] = max(audit["max_analytic_error_CHF"], error)
                                audit["analytic_values_checked"] += 1
                            hand_rows.append({**identities(family, p, gamma, contract, d), "method": method, "solver_compensation_CHF": actual, "analytic_compensation_CHF": expected, "absolute_error_CHF": error, "same_feasibility": same_feasibility})
                        q_error = abs(expected_q - oracle["expected_delivery_kWh"])
                        assert q_error < TOL
                        audit["max_expected_delivery_analytic_error_kWh"] = max(audit["max_expected_delivery_analytic_error_kWh"], q_error)
                        if d in [4, 4.5, 5, 7]:
                            for method, pattern in [("B", ref_pattern), ("B_alt", "B"), ("C", bundle["canonical_pattern"])]:
                                schedule_records.append(schedule_record(bundle, method, pattern))
                print(f"completed gamma={gamma:g} {family} p={p:g}", flush=True)
    for name in source_files:
        assert hashlib.sha256((source_dir / name).read_bytes()).hexdigest() == hashes[name], f"source changed during run: {name}"
    assert all(row["all_checks_pass"] for row in soc_rows)
    assert audit["max_MILP_gap"] < TOL
    assert audit["max_primal_violation"] < TOL
    audit.update({"status": "PASS", "smoke_only": args.smoke, "comparison_rows": len(rows), "solver_rows": len(solver_rows), "SOC_state_schedule_checks": len(soc_rows), "all_SOC_checks_pass": all(row["all_checks_pass"] for row in soc_rows), "feasible_C_count": sum(row["C_status"] == 0 for row in rows), "elapsed_seconds": time.perf_counter() - start, "source_hashes_unchanged_during_run": True, "limitations": "published-profile adaptation and finite-state mechanism diagnostic; no calibrated acceptance, external validity, unknown arrivals, emergency exit, or scalability claim"})
    write_csv(output / "compensation.csv", rows)
    write_csv(output / "solver_status.csv", solver_rows)
    write_csv(output / "soc_audit.csv", soc_rows)
    write_csv(output / "references.csv", reference_rows)
    write_csv(output / "handcheck.csv", hand_rows)
    save_json(output / "schedules.json", schedule_records)
    save_json(output / "verification.json", audit)
    print(json.dumps(clean({"output": str(output), **audit}), indent=2), flush=True)


if __name__ == "__main__":
    main()
