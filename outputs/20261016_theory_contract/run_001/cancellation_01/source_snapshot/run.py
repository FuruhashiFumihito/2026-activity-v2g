#!/usr/bin/env python3
"""Execute the preregistered theoretical mechanism study into a fresh run tree."""
from __future__ import annotations

import os
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/activity-v2g-theory-matplotlib")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import argparse
import csv
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy as np
import scipy
import matplotlib

from model import SUPPORTED_INPUTS_SHA256, TOL, analytical_oracle, independent_lp, solve


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, cwd):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def case_grid(design):
    for minutes, p, access, fulfillment, floor in itertools.product(
            design["D_minutes"], design["probabilities"], design["appointment_v2g_access"],
            design["fulfillment"], design["guarantee_kWh"]):
        yield dict(D_h=minutes/60, p_cancel=p, appointment_v2g_access=access,
                   fulfillment=fulfillment, guarantee_kWh=floor)


def independent_check(case, joined, result):
    routes = [independent_lp(case, joined, g) for g in (0, 1)]
    feasible = [r["cost"] for r in routes if r["status"] == 0]
    expected_status = 0 if feasible else 2
    oracle = analytical_oracle(case, joined)
    checks = {
        "solver_status_supported": result["status"] in (0, 2),
        "status_matches_independent_LPs": result["status"] == expected_status,
        "status_matches_analytical_oracle": result["status"] == oracle["status"],
        "route_LP_statuses_supported": all(r["status"] in (0, 2) for r in routes)
    }
    errors = dict(enumeration=0.0, analytical=0.0)
    if result["status"] == 0 and feasible and oracle["cost"] is not None:
        errors = dict(enumeration=abs(result["cost"]-min(feasible)),
                      analytical=abs(result["cost"]-oracle["cost"]))
        checks.update(objective_matches_route_LPs=errors["enumeration"] <= TOL,
                      objective_matches_analytical_oracle=errors["analytical"] <= TOL,
                      residuals=result["max_primal_violation"] <= TOL,
                      integrality=result["max_integrality_residual"] <= TOL,
                      physical_and_utility_audit=result["audit"]["passed"],
                      optimality_certificate=result["mip_gap"] <= TOL)
    return dict(checks=checks, passed=all(checks.values()), errors=errors,
                independent_routes=routes, analytical_oracle=oracle)


def study(output, label, design, settings, source, environment):
    out = output/label
    out.mkdir()
    cases = list(case_grid(design))
    dump(out/"config.json", dict(study=label, settings=settings, design=design,
                                  exact_case_count=len(cases), source_sha256=environment["source_sha256"],
                                  source_revision=environment["git_revision"]))
    dump(out/"environment.json", environment)
    snapshots = out/"source_snapshot"
    snapshots.mkdir()
    for path in source.iterdir():
        if path.suffix in (".py", ".json", ".md"):
            (snapshots/path.name).write_bytes(path.read_bytes())
    (out/"overview.md").write_text(f"# {label}\n\nSettings saved before solving; {len(cases)} designed conditions.\nResults pending.\n")
    (out/"discussion.md").write_text("# Discussion\n\nResults pending.\n")
    reference_cache, baseline_cache = {}, {}
    rows, failures, max_errors = [], [], dict(enumeration=0.0, analytical=0.0,
                                               objective=0.0, primal=0.0, dual_finite_difference=0.0,
                                               decomposition=0.0, max_mip_gap=0.0)
    start = time.perf_counter()
    with gzip.open(out/"solver_records.jsonl.gz", "wt", encoding="utf-8") as raw:
        for index, case in enumerate(cases):
            key = tuple(case[k] for k in ("p_cancel", "appointment_v2g_access", "fulfillment", "guarantee_kWh"))
            if key not in baseline_cache:
                baseline = solve(case, False)
                baseline_check = independent_check(case, False, baseline)
                baseline_cache[key] = baseline
                raw.write(json.dumps(dict(kind="baseline", key=key, case=case,
                                          result=baseline, validation=baseline_check), allow_nan=False)+"\n")
                if not baseline_check["passed"]:
                    failures.append(dict(kind="baseline", case=case, checks=baseline_check["checks"]))
            baseline = baseline_cache[key]
            if key not in reference_cache:
                ref_case = {**case, "D_h": settings["comparison"]["reference_D_h"]}
                ref = solve(ref_case)
                validation = independent_check(ref_case, True, ref)
                entry = dict(result=ref, validation=validation)
                if ref["status"] == 0:
                    fixed = round(ref["vector"]["planned_gym"])
                    lp = solve(ref_case, fixed_g=fixed)
                    eps = settings["comparison"]["finite_difference_h"]
                    left = solve({**ref_case, "D_h": ref_case["D_h"]-eps}, fixed_g=fixed)
                    right = solve({**ref_case, "D_h": ref_case["D_h"]+eps}, fixed_g=fixed)
                    assert left["status"] == right["status"] == lp["status"] == 0
                    finite = (right["cost"]-left["cost"])/(2*eps)
                    error = abs(finite-lp["d_cost_d_D"])
                    max_errors["dual_finite_difference"] = max(max_errors["dual_finite_difference"], error)
                    entry.update(fixed_g=fixed, fixed_LP=lp, left=left, right=right,
                                 finite_difference=finite, dual_error=error)
                    if error > 2e-5 or abs(lp["cost"]-ref["cost"]) > TOL:
                        failures.append(dict(kind="reference_dual", case=case, error=error))
                if not validation["passed"]:
                    failures.append(dict(kind="reference", case=case, checks=validation["checks"]))
                reference_cache[key] = entry
                raw.write(json.dumps(dict(kind="reference", key=key, case=ref_case, **entry), allow_nan=False)+"\n")
            reference = reference_cache[key]
            full = solve(case)
            validation = independent_check(case, True, full)
            if not validation["passed"]:
                failures.append(dict(kind="case", case=case, checks=validation["checks"]))
            row = dict(case_id=index, **case, baseline_status=baseline["status"],
                       C_status=full["status"], C_signed_compensation=None, C_compensation=None,
                       C_gym=None, C_work_departure_h=None, C_precharge_kWh=None,
                       expected_connection_h=None, expected_shortfall_h=None,
                       fulfillment_probability=None, expected_delivered_kWh=None,
                       A_signed_compensation=None, A_compensation=None, reference_gym=None,
                       reference_slope_per_h=None, B_status=None, B_compensation=None,
                       continuous_extrapolation_error=None, integer_reselection_value=None,
                       C_minus_A=None, decomposition_error=None,
                       all_checks_pass=validation["passed"])
            if full["status"] == 0:
                signed = full["cost"]-baseline["cost"]
                v = full["vector"]
                realized = [s for s in full["audit"]["states"] if s["realized"]]
                row.update(C_signed_compensation=signed, C_compensation=max(0, signed),
                           C_gym=round(v["planned_gym"]), C_work_departure_h=v["work_departure_h"],
                           C_precharge_kWh=v["precharge_kWh"],
                           expected_connection_h=sum(s["probability"]*s["connection_h"] for s in realized),
                           expected_shortfall_h=sum(s["probability"]*s["shortfall_h"] for s in realized),
                           fulfillment_probability=sum(s["probability"]*s["fulfilled"] for s in realized),
                           expected_delivered_kWh=sum(s["probability"]*s["delivered_kWh"] for s in realized))
                for name in ("enumeration", "analytical"):
                    max_errors[name] = max(max_errors[name], validation["errors"][name])
                max_errors["primal"] = max(max_errors["primal"], full["max_primal_violation"], full["audit"]["maximum_violation"])
                max_errors["objective"] = max(max_errors["objective"], full["audit"]["objective_error"])
                max_errors["max_mip_gap"] = max(max_errors["max_mip_gap"], full["mip_gap"])
            fixed = None
            if reference["result"]["status"] == 0:
                slope = reference["fixed_LP"]["d_cost_d_D"]
                pred_cost = reference["fixed_LP"]["cost"]+slope*(case["D_h"]-settings["comparison"]["reference_D_h"])
                a_signed = pred_cost-baseline["cost"]
                fixed = solve(case, fixed_g=reference["fixed_g"])
                row.update(A_signed_compensation=a_signed, A_compensation=max(0, a_signed),
                           B_status=fixed["status"], reference_gym=reference["fixed_g"], reference_slope_per_h=slope)
                if fixed["status"] == 0 and full["status"] == 0:
                    row["B_compensation"] = max(0, fixed["cost"]-baseline["cost"])
                    ec = fixed["cost"]-pred_cost
                    gain = fixed["cost"]-full["cost"]
                    actual = full["cost"]-pred_cost
                    err = abs(actual-(ec-gain))
                    row.update(continuous_extrapolation_error=ec, integer_reselection_value=gain,
                               C_minus_A=actual, decomposition_error=err)
                    max_errors["decomposition"] = max(max_errors["decomposition"], err)
                    if min(ec, gain) < -TOL or err > TOL or not fixed["audit"]["passed"]:
                        failures.append(dict(kind="decomposition_or_fixed_audit", case=case, continuous_error=ec, reselection=gain, error=err))
                elif fixed["status"] not in (0, 2):
                    failures.append(dict(kind="fixed_solver_status", case=case, status=fixed["status"]))
            for reward in settings["comparison"]["reward_levels_JPY_equivalent"]:
                actual = full["status"] == 0 and row["C_compensation"] <= reward+TOL
                predicted = None if row["A_compensation"] is None else row["A_compensation"] <= reward+TOL
                row[f"C_accept_R{reward}"] = actual
                row[f"A_accept_R{reward}"] = predicted
                row[f"decision_mismatch_R{reward}"] = None if predicted is None else predicted != actual
            if failures and failures[-1].get("case") == case:
                row["all_checks_pass"] = False
            rows.append(row)
            raw.write(json.dumps(dict(kind="case", case_id=index, case=case,
                                      C=full, B=fixed, validation=validation, summary=row), allow_nan=False)+"\n")
            if (index+1) % 250 == 0:
                print(f"{label}: {index+1}/{len(cases)} conditions; failures={len(failures)}", flush=True)
    with (out/"results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    verification = dict(status="PASS" if not failures else "FAIL", cases=len(cases),
                        feasible_C=sum(r["C_status"] == 0 for r in rows),
                        infeasible_C=sum(r["C_status"] == 2 for r in rows),
                        B_infeasible=sum(r["B_status"] == 2 for r in rows),
                        references=len(reference_cache), maximum_errors=max_errors,
                        elapsed_seconds=time.perf_counter()-start, failures=failures,
                        raw_sha256=sha(out/"solver_records.jsonl.gz"), csv_sha256=sha(out/"results.csv"))
    dump(out/"verification.json", verification)
    (out/"overview.md").write_text(f"""# {label}: experiment overview

The question, complete numerical inputs, grid and stopping rules were saved in
`config.json` before solving. This run contains {len(cases)} deliberately designed
conditions; these are not independent people or random replications. All positive
probability states are enumerated. The full nominal plan is also checked.

A extrapolates the actual reference LP multiplier at D=1.25 h. B fixes only the
single structural gym binary, with no auxiliary integers in this experiment.
C solves the one-binary MILP. Independent route LPs remove all big-M constraints;
an analytical breakpoint enumeration supplies a third reference. D is continuous
inside the model; the plotted sweep is a parameter grid, not a time discretization.

Contract guarantees, source scope, shared pre-realization choices, costs and
physical settings are identical across paired A/B/C and joining/nonjoining
comparisons except for the stated treatment. Every joining case delivers 6 kWh
during 16:00--17:00; cumulative availability shortfall can be penalized (soft) or
prohibited in every supported state (hard). Fulfillment probability is computed
from actual connection, not a free achievement indicator.

Each optimal solution is audited against reconstructed activity times, SOC events,
charging completion, exact final energy and utility. Nominal feasibility, remaining
durations, first departure, order, precharge and connection plans are preserved.
Scenario-dependent optimized plans or emergency opt-out rights are not introduced.

Results: `results.csv`. Full primal/dual/status/SOC records and independent
references: `solver_records.jsonl.gz`. Saved sources: `source_snapshot/`.
Execution gate: **{verification['status']}**. Software and revision: `environment.json`.
""")
    (out/"discussion.md").write_text(f"""# {label}: observed results and limits

The execution gate is **{verification['status']}**. {verification['feasible_C']} conditions
have certified feasible optimal C solutions and {verification['infeasible_C']} are
infeasible. {verification['B_infeasible']} fixed-pattern B comparisons are infeasible;
their costs are missing, not zero. See `verification.json` for numerical errors.

Maximum compensation underestimation, overestimation, decision mismatches and
measured activity/SOC mechanisms are summarized in the parent `report_ja.md`.
All infeasible cases, null differences, probability endpoints and nominal-plan
restrictions remain in the CSV and compressed records.

Only the synthesized mechanism instance is supported. The parameters are authored
JPY-equivalent inputs, not estimated Japanese preferences. This does not establish
empirical acceptance, Fukushima population frequencies, full-paper model validity,
algorithm scalability, or emergency flexibility/option value. Soft and hard are
different contractual treatments, not equal-reliability alternatives.
""")
    print(json.dumps({"run": label, **verification}, ensure_ascii=False), flush=True)
    return verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-legacy", action="store_true", help="Omit source-baseline reruns; recorded in manifest")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    repo = source.parents[1]
    output = args.output.resolve()
    if output.exists():
        parser.error("refusing to overwrite an existing run")
    settings = json.loads((source/"settings.json").read_text())
    input_hash = hashlib.sha256(json.dumps(settings["authored_inputs"], sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
    if input_hash != SUPPORTED_INPUTS_SHA256:
        parser.error("authored_inputs description differs from the implemented fixed model")
    output.mkdir(parents=True)
    dump(output/"settings.json", settings)
    environment = dict(started_UTC=datetime.now(timezone.utc).isoformat(),
                       python=sys.version, executable=sys.executable, numpy=np.__version__,
                       scipy=scipy.__version__, matplotlib=matplotlib.__version__,
                       hardware=platform.uname()._asdict(), threads=1,
                       git_revision=command(["git", "rev-parse", "HEAD"], repo),
                       git_status=command(["git", "status", "--short"], repo),
                       source_sha256={p.name: sha(p) for p in source.iterdir() if p.suffix in (".py", ".json", ".md")},
                       source_baseline_sha256={name: sha(repo/"experiments/minimal_contract"/name)
                                              for name in ("bryan.py", "synthetic.py", "source_provenance.md")})
    dump(output/"environment.json", environment)
    if not args.skip_legacy:
        for script, run in [("bryan.py", "bryan_continuous_01"), ("synthetic.py", "activity_drop_01")]:
            print(f"Rerunning existing source baseline: {run}", flush=True)
            with (output/f"{run}.log").open("w") as log:
                subprocess.run([sys.executable, str(repo/"experiments/minimal_contract"/script),
                                "--output", str(output/run)], cwd=repo, check=True,
                               stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())
    checks = []
    for key, label in [("cancellation", "cancellation_01"), ("soc", "soc_01")]:
        checks.append(study(output, label, settings[key], settings, source, environment))
    dump(output/"manifest.json", dict(status="PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
                                     legacy_reruns=not args.skip_legacy,
                                     designed_conditions=sum(c["cases"] for c in checks),
                                     studies=checks, environment=environment))
    if any(c["status"] != "PASS" for c in checks):
        raise SystemExit("One or more correctness gates failed; results retained")
    from report import build_report
    build_report(output)


if __name__ == "__main__":
    main()
