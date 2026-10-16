#!/usr/bin/env python3
"""Read-only bundle/theoretical-boundary verification; writes its own audit only."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

TOL = 2e-7


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key, value in row.items():
            if value == "":
                row[key] = None
            elif value in ("True", "False"):
                row[key] = value == "True"
            else:
                try:
                    row[key] = float(value)
                except ValueError:
                    pass
    return rows


def key(r):
    return tuple(r[k] for k in ("D_h", "p_cancel", "appointment_v2g_access", "fulfillment", "guarantee_kWh"))


def verify(output):
    output = Path(output).resolve()
    failures, errors, counts = [], {}, {}
    manifest = json.loads((output/"manifest.json").read_text())
    assert manifest["status"] == "PASS"
    for run in ("cancellation_01", "soc_01"):
        folder = output/run
        verification = json.loads((folder/"verification.json").read_text())
        assert verification["raw_sha256"] == hash_file(folder/"solver_records.jsonl.gz")
        assert verification["csv_sha256"] == hash_file(folder/"results.csv")
        environment = json.loads((folder/"environment.json").read_text())
        for name, digest in environment["source_sha256"].items():
            assert hash_file(folder/"source_snapshot"/name) == digest, (run, name)
        rows = read_csv(folder/"results.csv")
        assert len(rows) == verification["cases"]
        assert len({key(r) for r in rows}) == len(rows)
        assert all(r["all_checks_pass"] for r in rows)
        raw_cases, audits, baselines = 0, 0, {}
        with gzip.open(folder/"solver_records.jsonl.gz", "rt") as f:
            for line in f:
                record = json.loads(line)
                assert record["validation"]["passed"]
                if record["kind"] == "baseline":
                    baselines[tuple(record["key"])] = record["result"]["cost"]
                if record["kind"] == "case":
                    raw_cases += 1
                    result = record["C"]
                    assert result["status"] in (0, 2)
                    if result["status"] == 0:
                        z = record["case"]
                        base_key = tuple(z[k] for k in ("p_cancel", "appointment_v2g_access", "fulfillment", "guarantee_kWh"))
                        assert abs(result["cost"]-baselines[base_key]-record["summary"]["C_signed_compensation"]) < TOL
                        assert result["audit"]["passed"]
                        for state in result["audit"]["states"]:
                            audits += 1
                            assert state["delivered_kWh"] == 6
                            assert abs(state["soc_points"][-1][1]-36) < TOL
                            assert state["maximum_violation"] < TOL
                    else:
                        assert record["summary"]["C_compensation"] is None
        assert raw_cases == len(rows)
        strata = {}
        for row in rows:
            k = key(row)[1:]
            strata.setdefault(k, []).append(row)
        for values in strata.values():
            feasible = sorted([r for r in values if r["C_status"] == 0], key=lambda r: r["D_h"])
            assert all(b["C_signed_compensation"] >= a["C_signed_compensation"]-TOL
                       for a, b in zip(feasible, feasible[1:]))
        counts[run] = dict(conditions=len(rows), feasible=sum(r["C_status"] == 0 for r in rows),
                           infeasible=sum(r["C_status"] == 2 for r in rows), SOC_states_audited=audits)
    rows = read_csv(output/"cancellation_01/results.csv")
    formula_errors = []
    for row in rows:
        if abs(row["D_h"]-1.5) < 1e-10:
            p = row["p_cancel"]
            if row["appointment_v2g_access"] == 1 and row["fulfillment"] == "soft":
                predicted = 204+min(1200*p, 900-450*p)
                formula_errors.append(abs(row["C_compensation"]-predicted))
            if row["fulfillment"] == "hard":
                predicted = 204 if row["appointment_v2g_access"] == 1 and p == 0 else 1104-450*p
                formula_errors.append(abs(row["C_compensation"]-predicted))
    errors["closed_form_probability_response"] = max(formula_errors)
    assert errors["closed_form_probability_response"] < TOL
    soc = read_csv(output/"soc_01/results.csv")
    base = {key(r)[:-1]: r for r in soc if r["guarantee_kWh"] == 12}
    additive_errors = []
    for row in soc:
        access, floor = row["appointment_v2g_access"], row["guarantee_kWh"]
        limit = 33.75 if access else 34
        assert (row["C_status"] == 2) == (floor > limit+TOL)
        if row["C_status"] == 0:
            expected_charge = max(0, floor-(27.75 if access else 28))
            assert abs(row["C_precharge_kWh"]-expected_charge) < TOL
            predicted = base[key(row)[:-1]]["C_compensation"]+30*expected_charge
            additive_errors.append(abs(row["C_compensation"]-predicted))
    errors["SOC_additivity_in_feasible_domain"] = max(additive_errors)
    assert errors["SOC_additivity_in_feasible_domain"] < TOL
    figure_manifest = json.loads((output/"figure_manifest.json").read_text())
    for name, digest in figure_manifest.items():
        assert hash_file(output/name) == digest, name
    for path in output.rglob("*.md"):
        if {"source_snapshot", "presentation"} & set(path.parts):
            continue
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if target.startswith(("http:", "https:", "#")):
                continue
            assert (path.parent/target.split("#")[0]).exists(), (path, target)
    result = dict(status="PASS", counts=counts, maximum_formula_errors=errors,
                  figure_hashes_verified=len(figure_manifest), failures=failures,
                  meaning="Designed-grid correctness, exact state propagation, monetary units, support and SOC boundaries. No external-validity claim.")
    (output/"bundle_verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
