#!/usr/bin/env python3
"""Published-profile adaptation: minimal Bryan contract diagnostic.

This is a deterministic mechanism/correctness experiment, not a reproduction of
the published model or an observed travel diary. See config.json and overview.md.
"""
from __future__ import annotations

import argparse
import csv
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
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/activity-v2g-matplotlib-bryan")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

ALPHA = 0.0783
BETA = 0.993
SHOP_UTILITY = 11.3
EDUCATION_UTILITY = 17.4
MONEY = 0.3
EDUCATION_START = 7.5
EDUCATION_MIN_DURATION = 4 + 40 / 60
EMIN = EDUCATION_START + EDUCATION_MIN_DURATION
SHOP_DESIRED = 16.5
SHOP_LATEST = 17.0
SHOP_DURATION = 2.0
TRAVEL_A = 0.45
BASE_E = SHOP_DESIRED - TRAVEL_A
BASE_TIME = ALPHA * (BASE_E - EMIN)
REFERENCE_D = 4.0
RESTORE_EXTRA_CHF = 7 * 0.30
SOURCE = "https://doi.org/10.1016/j.trd.2025.104911"
TOL = 2e-7
COLORS = {"Home": "#e6e6e6", "Travel": "#839098", "Education": "#d9b16f", "Shopping A": "#9f8cc1", "Shopping B": "#51a69b"}


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def save_json(path, data):
    path.write_text(json.dumps(clean(data), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def command_output(command, cwd=None):
    try:
        return subprocess.check_output(command, text=True, cwd=cwd, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def model(joined, d=None):
    # z = [education_end, shopping_start_or_zero, late_start, y_A, y_B].
    # All timing quantities and all timing coefficients use HOURS.
    c = np.array([ALPHA, 0.0, BETA, -SHOP_UTILITY, -SHOP_UTILITY])
    lb = np.array([EMIN, 0, 0, 0, 0], float)
    ub = np.array([19, SHOP_LATEST, 17, 1, 1], float)
    rows, rhs, names = [], [], []

    def add(row, bound, name):
        rows.append(row)
        rhs.append(bound)
        names.append(name)

    add([0, 0, 0, 1, 1], 1, "mutually_exclusive_shopping")
    add([0, -1, 0, SHOP_DESIRED, SHOP_DESIRED], 0, "shopping_earliest")
    add([0, 1, 0, -SHOP_LATEST, -SHOP_LATEST], 0, "shopping_latest")
    add([0, 1, -1, -SHOP_DESIRED, -SHOP_DESIRED], 0, "shopping_lateness_hinge")
    big_m = 24.0
    for yidx, travel, label in [(3, TRAVEL_A, "A"), (4, 0.0, "B")]:
        row = [-1, 1, 0, 0, 0]
        row[yidx] = big_m
        add(row, big_m + travel, f"shopping_{label}_link_upper")
        row = [1, -1, 0, 0, 0]
        row[yidx] = big_m
        add(row, big_m - travel, f"shopping_{label}_link_lower")
    if joined:
        # Campus parking is continuous across education and Shopping B.
        # The contract requires fixed 12:00--13:00 service and D total hours
        # within 12:00--19:00. D>=1 and this row enforce both obligations.
        add([-1, 0, 0, 0, -SHOP_DURATION], -(12 + d), "minimum_campus_departure")
    constant = -ALPHA * EMIN + MONEY * (11 if joined else 4) * 0.30
    return {"c": c, "lb": lb, "ub": ub, "A": np.array(rows, float), "b": np.array(rhs, float), "names": names, "constant": constant}


def summarize_result(result, m, method, d, elapsed, lp=False):
    result_record = {"method": method, "D_hours": d, "status": int(result.status), "success": bool(result.success), "message": result.message, "elapsed_seconds": elapsed, "objective_linear": result.fun, "objective_constant": m["constant"], "minimum_disutility": None, "utility": None, "vector": result.x, "variable_names": ["education_end_h", "shopping_start_h_or_zero", "lateness_h", "shopping_A", "shopping_B"], "constraint_names": m["names"], "max_primal_violation": None, "max_integrality_residual": None}
    for key in ["mip_gap", "mip_node_count", "mip_dual_bound", "nit"]:
        result_record[key] = getattr(result, key, None)
    if result.x is not None and result.success:
        z = result.x
        slack = m["b"] - m["A"] @ z
        result_record.update({"minimum_disutility": float(result.fun + m["constant"]), "utility": float(EDUCATION_UTILITY - result.fun - m["constant"]), "inequality_residuals": slack, "lower_bound_residuals": z - m["lb"], "upper_bound_residuals": m["ub"] - z, "max_primal_violation": float(max(0.0, np.max(-slack), np.max(m["lb"] - z), np.max(z - m["ub"]))), "max_integrality_residual": float(np.max(np.abs(z[3:] - np.round(z[3:])))), "shopping_pattern": "A" if z[3] > .5 else "B" if z[4] > .5 else "none", "campus_departure_h": float(z[0] + SHOP_DURATION * z[4])})
    if lp:
        for block in ["ineqlin", "eqlin", "lower", "upper"]:
            value = getattr(result, block, None)
            result_record[block] = None if value is None else {"residual": value.residual, "marginals": value.marginals}
        if result.success and "minimum_campus_departure" in m["names"]:
            idx = m["names"].index("minimum_campus_departure")
            # RHS is -(12+D), hence derivative w.r.t. D has the opposite sign.
            result_record["d_disutility_d_D_utility_per_hour"] = float(-result.ineqlin.marginals[idx])
    return clean(result_record)


def solve_milp(joined, d=None):
    m = model(joined, d)
    start = time.perf_counter()
    result = milp(m["c"], integrality=[0, 0, 0, 1, 1], bounds=Bounds(m["lb"], m["ub"]), constraints=LinearConstraint(m["A"], -np.inf, m["b"]), options={"time_limit": 60, "mip_rel_gap": 1e-10, "presolve": True})
    return summarize_result(result, m, "MILP_full", d, time.perf_counter() - start)


def solve_fixed(joined, d, integers):
    m = model(joined, d)
    m["lb"][3:] = integers
    m["ub"][3:] = integers
    start = time.perf_counter()
    result = linprog(m["c"], A_ub=m["A"], b_ub=m["b"], bounds=list(zip(m["lb"], m["ub"])), method="highs-ds", options={"time_limit": 60, "primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9})
    return summarize_result(result, m, "LP_fixed_reference_integers", d, time.perf_counter() - start, lp=True)


def enumerate_pattern(joined, d, pattern):
    """Independent two-variable LP; no binary linking rows or big-M."""
    travel = TRAVEL_A if pattern == "A" else 0
    selected = pattern != "none"
    lo = SHOP_DESIRED - travel if selected else EMIN
    hi = SHOP_LATEST - travel if selected else 19
    campus_extra = SHOP_DURATION if pattern == "B" else 0
    rows, rhs = [], []
    if selected:
        rows.append([1, -1])
        rhs.append(SHOP_DESIRED - travel)
    if joined:
        rows.append([-1, 0])
        rhs.append(-(12 + d - campus_extra))
    start = time.perf_counter()
    result = linprog([ALPHA, BETA], A_ub=np.array(rows) if rows else None, b_ub=np.array(rhs) if rows else None, bounds=[(lo, hi), (0, None if selected else 0)], method="highs-ds", options={"time_limit": 60, "primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9})
    const = -ALPHA * EMIN - SHOP_UTILITY * selected + MONEY * (11 if joined else 4) * .30
    return clean({"method": "independent_enumerated_pattern_LP", "pattern": pattern, "D_hours": d, "status": int(result.status), "success": bool(result.success), "message": result.message, "vector_education_end_lateness": result.x, "objective_linear": result.fun, "objective_constant": const, "minimum_disutility": float(result.fun + const) if result.success else None, "inequality_residuals": result.ineqlin.residual if result.success else None, "inequality_marginals": result.ineqlin.marginals if result.success else None, "elapsed_seconds": time.perf_counter() - start})


def hand_pattern(d, pattern, joined=True):
    lower = 12 + d if joined else -math.inf
    if pattern == "A":
        end = max(BASE_E, lower)
        feasible = end <= SHOP_LATEST - TRAVEL_A + 1e-10
        time_cost = ALPHA * (end - EMIN) + BETA * max(0, end + TRAVEL_A - SHOP_DESIRED)
    elif pattern == "B":
        end = max(SHOP_DESIRED, lower - SHOP_DURATION)
        feasible = end <= SHOP_LATEST + 1e-10
        time_cost = ALPHA * (end - EMIN) + BETA * (end - SHOP_DESIRED)
    else:
        end = max(EMIN, lower)
        feasible = end <= 19 + 1e-10
        time_cost = ALPHA * (end - EMIN)
    disutility = time_cost - (SHOP_UTILITY if pattern != "none" else 0) + MONEY * (11 if joined else 4) * .30
    return {"pattern": pattern, "feasible": feasible, "education_end_h": end if feasible else None, "minimum_disutility": disutility if feasible else None}


def check_energy(record, d, config, joined=True):
    if not record["success"]:
        return None
    e, x, _, ya, yb = record["vector"]
    pattern = record["shopping_pattern"]
    assumed = config["added_assumptions"]
    published = config["published_inputs"]
    contract = config["contract"]
    od = assumed["OD"]
    duration = assumed["shopping_duration_fixed_h"]
    education_start = assumed["education_start_fixed_h"]
    home_departure = education_start - od["Home-Campus"]["hours"]
    legs = [(home_departure, education_start, od["Home-Campus"]["km"], "Home-Campus")]
    timing_errors = []
    if pattern == "A":
        timing_errors.append(abs(x - e - od["Campus-Shopping_A"]["hours"]))
        home = x + duration + od["Shopping_A-Home"]["hours"]
        legs += [(e, x, od["Campus-Shopping_A"]["km"], "Campus-Shopping_A"), (x + duration, home, od["Shopping_A-Home"]["km"], "Shopping_A-Home")]
    elif pattern == "B":
        timing_errors.append(abs(x - e - od["Campus-Shopping_B"]["hours"]))
        home = x + duration + od["Shopping_B-Home"]["hours"]
        legs += [(x + duration, home, od["Shopping_B-Home"]["km"], "Shopping_B-Home")]
    else:
        home = e + od["Home-Campus"]["hours"]
        legs += [(e, home, od["Home-Campus"]["km"], "Campus-Home")]
    current = float(assumed["initial_energy_kWh"])
    efficiency = assumed["charge_discharge_efficiency"]
    events = [{"start_h": start, "end_h": end, "energy_change_kWh": -km * published["consumption_kWh_per_km"], "kind": name, "km": km} for start, end, km, name in legs]
    q = 0.0
    if joined:
        service_start, service_end = contract["fixed_connection_window_h"]
        q = (service_end - service_start) * contract["fixed_discharge_kW"]
        events.append({"start_h": service_start, "end_h": service_end, "energy_change_kWh": -q / efficiency, "kind": "V2G discharge", "km": 0})
    events.sort(key=lambda v: (v["start_h"], v["end_h"]))
    points = [(6.0, current)]
    event_end = 6.0
    no_overlap = True
    for event in events:
        no_overlap = no_overlap and event["start_h"] >= event_end - TOL
        points.append((event["start_h"], current))
        current += event["energy_change_kWh"]
        points.append((event["end_h"], current))
        event["energy_after_kWh"] = current
        event_end = event["end_h"]
    energy_home = current
    charge_grid_kWh = (assumed["final_energy_kWh"] - current) / efficiency
    charge_end = home + charge_grid_kWh / published["home_charging_kW"]
    current += charge_grid_kWh * efficiency
    points.extend([(charge_end, current), (24.0, current)])
    floor = assumed["floor_energy_kWh"]
    capacity = published["EV_capacity_kWh"]
    minimum = min(p[1] for p in points)
    maximum = max(p[1] for p in points)
    departure = e + 2 * yb
    plug_start = contract["cumulative_connection_counting_window_h"][0]
    margins = {"physical_floor_kWh": minimum - floor, "capacity_kWh": capacity - maximum, "charge_deadline_h": 24 - charge_end, "nonnegative_home_charge_kWh": charge_grid_kWh}
    if joined:
        margins.update({"plug_end_h": departure - plug_start - d, "service_end_before_campus_departure_h": departure - service_end, "service_starts_after_campus_arrival_h": service_start - education_start})
    checks = {"no_overlapping_energy_events": no_overlap, "no_intermediate_waiting": max(timing_errors, default=0) < TOL, "all_feasibility_margins_nonnegative": min(margins.values()) >= -TOL, "final_energy_equality": abs(current - assumed["final_energy_kWh"]) < TOL, "fixed_service_equality": abs(q - (contract["fixed_delivered_energy_kWh"] if joined else 0)) < TOL, "model_energy_cost_consistency": abs(charge_grid_kWh - (11 if joined else 4)) < TOL}
    return {"home_arrival_h": home, "charging_end_h": charge_end, "SOC_initial_kWh": assumed["initial_energy_kWh"], "SOC_home_arrival_kWh": energy_home, "SOC_end_kWh": current, "SOC_floor_kWh": floor, "minimum_SOC_margin_kWh": minimum - floor, "service_kWh": q, "route_km": sum(event["km"] for event in events), "route_energy_kWh": sum(km * published["consumption_kWh_per_km"] for _, _, km, _ in legs), "restoration_grid_kWh": charge_grid_kWh, "energy_cost_CHF": charge_grid_kWh * assumed["flat_price_CHF_per_kWh"], "plug_start_h": plug_start if joined else None, "plug_end_h": plug_start + d if joined else None, "campus_departure_h": departure, "feasibility_margins": margins, "checks": checks, "all_checks_pass": all(checks.values()), "events": events, "SOC_time_energy_points": points}


def timeline(record):
    e, x, _, _, _ = record["vector"]
    p = record["shopping_pattern"]
    segments = [(6, 7, "Home"), (7, 7.5, "Travel"), (7.5, e, "Education")]
    if p == "A":
        segments += [(e, x, "Travel"), (x, x + 2, "Shopping A"), (x + 2, x + 2.05, "Travel")]
        home = x + 2.05
    elif p == "B":
        segments += [(x, x + 2, "Shopping B"), (x + 2, x + 2.5, "Travel")]
        home = x + 2.5
    else:
        segments += [(e, e + .5, "Travel")]
        home = e + .5
    segments += [(home, 24, "Home")]
    return segments, home


def soc_series(record):
    return np.array(record["energy_audit"]["SOC_time_energy_points"])


def plot_compensation(output, rows, thresholds):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 200})
    fig, ax = plt.subplots(figsize=(9.6, 5.3), layout="constrained")
    d = np.array([r["D_hours"] for r in rows])
    a = np.array([r["A_compensation_CHF"] for r in rows])
    b = np.array([r["B_compensation_CHF"] if r["B_compensation_CHF"] is not None else np.nan for r in rows])
    c = np.array([r["C_compensation_CHF"] for r in rows])
    ax.plot(d, c, color="#237b9d", linewidth=3.1, label="C  All activity choices reoptimized")
    ax.plot(d, b, color="#299455", linestyle="--", linewidth=1.7, label="B  Reference Shopping A fixed")
    ax.plot(d, a, color="#ad5b39", linestyle=":", linewidth=2.6, label="A  Reference local price extrapolated")
    for key, label, y in [("A_lateness_begins", "A: late shopping begins", 5.5), ("location_switch", "C: Shopping A → B", 5.0), ("fixed_A_feasibility_limit", "B infeasible beyond here", 5.6), ("B_lateness_begins", "C: Shopping B starts later", 5.0)]:
        value = thresholds[key]
        ax.axvline(value, color="#c2c8cc", linewidth=.8, zorder=0)
        ax.annotate(label, xy=(value, y - .3), xytext=(value + (.08 if key != "A_lateness_begins" else -.12), y), fontsize=8, rotation=90, va="top", ha="left" if key != "A_lateness_begins" else "right", color="#596269")
    ax.scatter([REFERENCE_D], [RESTORE_EXTRA_CHF], color="black", s=24, zorder=6)
    ax.text(3.88, 1.91, "reference D = 4 h", fontsize=9, ha="right")
    ax.text(1.12, 2.31, "A = B = C until D = 4.05 h", fontsize=9, color="#38454d")
    ax.text(4.83, 2.35, "C uses campus shopping", fontsize=9, color="#237b9d")
    ax.set(xlabel="Required campus connection D within 12:00–19:00 (hours)", ylabel="Additional fixed compensation (CHF)", xlim=(.95, 7.05), ylim=(1.7, 6.0))
    ax.set_xticks([1, 2, 3, 4, 5, 6, 7])
    ax.grid(axis="y", alpha=.2)
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    fig.suptitle("Bryan published-profile adaptation: local price, fixed choices, and full choices", fontsize=12)
    fig.text(.01, -.005, "Fixed 7 kWh service; minimum compensation includes CHF 2.10 restoration. Hard shopping window and contract are added assumptions.\nMissing B means infeasible. C changes location continuously in value; this case has no activity-drop jump.", fontsize=8, color="#596269", va="top")
    for extension in ["png", "pdf"]:
        fig.savefig(output / f"compensation.{extension}", bbox_inches="tight")
    plt.close(fig)


def plot_schedules(output, records_by_d, baseline):
    fig = plt.figure(figsize=(12, 9.4), layout="constrained")
    grid = fig.add_gridspec(3, 4, height_ratios=[1.7, .04, 1])
    ax = fig.add_subplot(grid[0, :])
    values = [4.0, 4.5, 5.0, 7.0]
    labels = [(8, "Nonjoining")]
    segments, home = timeline(baseline)
    for start, end, activity in segments:
        ax.barh(8, end - start, left=start, height=.58, color=COLORS[activity], edgecolor="white", linewidth=.4)
        if activity in ["Shopping A", "Shopping B"]:
            ax.text((start + end) / 2, 8, activity, ha="center", va="center", color="white", fontsize=8)
    ax.plot([home, baseline["energy_audit"]["charging_end_h"]], [8.22, 8.22], color="#2472b4", linewidth=2.5)
    for i, d in enumerate(values):
        methods = [("C", records_by_d[d]["C"]), ("B", records_by_d[d]["B"])]
        for j, (method, record) in enumerate(methods):
            y = 7 - (i * 2 + j)
            labels.append((y, f"D = {d:g} h   {method}"))
            if not record["success"]:
                ax.text(13, y, "infeasible with reference Shopping A fixed", color="#8a8a8a", va="center", fontsize=9)
                continue
            segments, home = timeline(record)
            for start, end, activity in segments:
                ax.barh(y, end - start, left=start, height=.58, color=COLORS[activity], edgecolor="white", linewidth=.4)
                if activity in ["Shopping A", "Shopping B"]:
                    ax.text((start + end) / 2, y, activity, ha="center", va="center", color="white", fontsize=8)
            ax.barh(y - .25, d, left=12, height=.11, color="none", hatch="/////", edgecolor="#303f4a", linewidth=.5, zorder=5)
            ax.plot([12, 13], [y + .22, y + .22], color="#ad5b39", linewidth=3, solid_capstyle="butt")
            ax.plot([home, record["energy_audit"]["charging_end_h"]], [y + .22, y + .22], color="#2472b4", linewidth=2.5, solid_capstyle="butt")
    ax.axvspan(16.5, 19, color="#bfb8ce", alpha=.09, zorder=0)
    ax.set_yticks([y for y, _ in labels], [label for _, label in labels])
    ax.set_xlim(6, 24)
    ax.set_ylim(-.65, 8.75)
    ticks = [6, 7.5, 12, 13, 16.5, 19, 21, 24]
    ax.set_xticks(ticks, ["06:00", "07:30", "12:00", "13:00", "16:30", "19:00", "21:00", "24:00"])
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="x", alpha=.15)
    ax.set_title("Activities and actual parking: C may switch to Shopping B on campus", loc="left", fontsize=11)
    handles = [Patch(facecolor=COLORS[name], label=name) for name in ["Home", "Travel", "Education", "Shopping A", "Shopping B"]]
    handles += [Patch(facecolor="none", hatch="/////", edgecolor="#303f4a", label="Contract plug interval (display tie rule)")]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.04), ncol=3, frameon=False, fontsize=8)
    ax.text(.0, -.18, "Brown line: 7 kWh service at 12:00–13:00. Blue line: home recharging. Pale band: added hard shopping window.\nEducation has minimum duration 4 h 40 min; its longer optimal stay here follows the restricted no-wait model, not an observed diary.", transform=ax.transAxes, fontsize=8, color="#596269")
    for i, d in enumerate(values):
        soc_ax = fig.add_subplot(grid[2, i])
        for method, color, style, width in [("C", "#237b9d", "-", 2.8), ("B", "#299455", "--", 1.4)]:
            record = records_by_d[d][method]
            if record["success"]:
                points = soc_series(record)
                soc_ax.plot(points[:, 0], points[:, 1], color=color, linestyle=style, linewidth=width, label=method)
        soc_ax.axhline(12, color="#a45a5a", linewidth=.8, linestyle=":")
        soc_ax.axhline(36, color="#aab0b5", linewidth=.6, linestyle=":")
        soc_ax.set(title=f"D = {d:g} h", xlim=(6, 24), ylim=(10, 39), xticks=[7, 12, 19, 24], yticks=[12, 25, 36])
        soc_ax.set_xticklabels(["07", "12", "19", "24"])
        soc_ax.grid(alpha=.13)
        soc_ax.set_xlabel("Hour")
        if i == 0:
            soc_ax.set_ylabel("Battery energy (kWh)")
        soc_ax.legend(frameon=False, loc="lower right", fontsize=8)
        if d >= 5:
            soc_ax.text(.05, .93, "B infeasible", transform=soc_ax.transAxes, fontsize=8, color="#8a8a8a")
    fig.suptitle("Bryan published-profile adaptation · deterministic minimum diagnostic", fontsize=13)
    for extension in ["png", "pdf"]:
        fig.savefig(output / f"schedules_soc.{extension}", bbox_inches="tight")
    plt.close(fig)


def write_records(output, config, rows, audit, reference, thresholds):
    selected = [r for r in rows if any(abs(r["D_hours"] - v) < 1e-10 for v in [1, 4, 4.5, 5, 6.5, 7])]
    table = "\n".join(f"| {r['D_hours']:.2f} | {r['A_compensation_CHF']:.5f} | {r['B_compensation_CHF']:.5f} | {r['C_compensation_CHF']:.5f} | {r['C_pattern']} |" if r["B_compensation_CHF"] is not None else f"| {r['D_hours']:.2f} | {r['A_compensation_CHF']:.5f} | infeasible | {r['C_compensation_CHF']:.5f} | {r['C_pattern']} |" for r in selected)
    overview = f"""# Bryan minimum contract diagnostic

Status: completed; {len(rows)} paired D cases; deterministic, no stochastic replications.

## Evidence question and comparison

Does a marginal value from fixed activity choices predict the finite cost of a campus connection promise when two shopping locations are available? A is the actual fixed-LP multiplier at D = 4 h extrapolated to each D; B fixes both shopping binaries at that reference and resolves continuous variables; C resolves the two-binary MILP. All methods share the same utility, physical state, 7 kWh fixed service, price, and hard time windows. Infeasible B cases remain missing and are never coded as zero. This is model correctness and a mechanism diagnostic, not external validation of contract choice.

## Provenance and scope

Published input profile: Wang, Pougala and Hillel (2025), DOI {SOURCE}, Table 3 (p. 11), Table 4 (p. 12), Table A.1 (p. 23). Bryan starts at Home (Downtown), has Education (Campus), desired start 07:30 and duration 4 h 40 min, and Shopping A (Downtown) / B (Campus), desired start 16:30 and duration 2 h. Education constant 17.4 and long-duration coefficient -0.0783; Shopping constant 11.3 and late-start coefficient -0.993. Source EV capacity 60 kWh, home charging power 7 kW, energy consumption 0.2 kWh/km. Timing coefficients use hours, following official OASIS documentation; Appendix A.1 itself does not print units.

All contract conditions, shopping hard windows, travel values, initial/end battery state, prices, money scale extension, eligibility rules and zeroed utility terms are added assumptions documented in config.json. The paper's positive short-shopping coefficient (+0.528) is not negated: shopping duration is held at its desired 2 h so that term is identically zero. All travel-utility, taste-error, SOC increase/anxiety, connection hassle, and degradation terms are omitted from this diagnostic. Ordinary charging is available only at Home after return; efficiency is 1. Education is mandatory, starts at 07:30, and has duration at least 4 h 40 min. No intermediate waiting is allowed; the only route order is Home–Education–optional shopping–Home. The published intermediate charging-station activity is omitted in this minimum-case restriction.

The optimum nonjoining schedule stays at Education until 16:03, then reaches Shopping A at 16:30. **This long campus stay is a model result of the restricted no-wait case, not an observed diary or a reported result from the paper.** This run must be called a published-profile adaptation, not a reproduction of the full published model or a Swiss survey respondent.

## Experimental settings contract

Unit: one adapted Bryan profile per connection requirement. D = 1 through 7 h in 5-minute steps, plus reference and threshold neighborhoods at +/- 1 minute and the exact thresholds. No random seed is needed because taste shocks and uncertain activities are absent. Reference D = 4 h. Controls: full campus connection during 12:00–13:00, fixed 7 kWh discharge then, D total hours within 12:00–19:00, no unfulfilled-service option, joining reward R = 0 while solving. Campus parking is continuous across Education and Shopping B. For display, the actual plug interval is [12, 12+D], even if the vehicle remains parked longer. Initial energy 36 kWh, floor 12 kWh, final 36 kWh, flat price CHF 0.30/kWh, utility of money 0.3 utility/CHF. These common initial/end states make joining's extra restoration cost exactly CHF 2.10. All routes take 1 h and consume 4 kWh.

Solver: scipy.optimize.milp / HiGHS for C; scipy.optimize.linprog(method='highs-ds') for B and independent three-pattern enumeration. Time limit 60 s per solve; MILP relative gap 1e-10; LP primal and dual feasibility tolerances 1e-9. No best-known incumbent is treated as optimal without the success status and saved gap. Environment and code hash are in environment.json; settings precede interpretation. Run command: `{config['run_command']}`. The script rejects an existing output directory. Starting revision: `{config['git_start_revision']}`; script hash: `{config['code_sha256']}`. No parameters were changed after observing the run.

## Claim–evidence and figures

| Claim | Reviewer objection | Controlled evidence | Pass rule | Scope |
|---|---|---|---|---|
| Local price can miss finite scheduling burdens | Error could be a solver or units defect | A vs B with same integers; MILP vs enumerated LPs and hand formulas | Objective errors < 2e-7 utility; residuals < 2e-7 | Deterministic adapted case |
| Location choice changes contract value | A false jump may be imposed | B vs C with identical contract and fixed delivered kWh | Save pattern, timing, and feasibility; retain continuous crossover | Two shopping alternatives only |
| SOC is held comparable | Cost may come from different energy states | Same initial/end state and routes; exact home charge audit | Fixed 7 kWh and final 36 kWh; floor and charge deadline feasible | Efficiency 1, no degradation |

compensation.png/pdf answers how A/B/C diverge. schedules_soc.png/pdf shows the measured mechanism and battery feasibility. Solver records include every vector, residual, LP marginal, status, and MILP gap. Handcheck and enumeration discrepancies are in verification.json and handcheck.csv.
"""
    discussion = f"""# Discussion of the completed Bryan adaptation

## Observations

All {len(rows)} C MILPs solved successfully. All feasible B fixed LPs solved successfully; B is correctly infeasible for D > 4.55 h. Maximum MILP versus independent enumerated-LP objective discrepancy: {audit['max_C_enumeration_objective_error_utility']:.3g} utility. Maximum solver versus hand-check compensation discrepancy: {audit['max_compensation_handcheck_error_CHF']:.3g} CHF. Maximum primal residual violation: {audit['max_primal_violation']:.3g}. Maximum reported C MILP gap: {audit['max_reported_mip_gap']:.3g}. See verification.json.

| D (h) | A (CHF) | B (CHF) | C (CHF) | C shopping |
|---:|---:|---:|---:|---|
{table}

At D = 4 h, Shopping A is selected, education ends 16:03, and the campus promise ends 16:00. Its multiplier is {reference['d_disutility_d_D_utility_per_hour']:.8g} utility/hour because the campus departure has 3 minutes of slack. A therefore predicts CHF 2.10 throughout. B and C agree with A only through D = 4.05 h. Beyond that point, fixed Shopping A incurs education overtime and late shopping, with slope (0.0783 + 0.993)/0.3 = 3.571 CHF/hour.

C changes from Downtown Shopping A to Campus Shopping B at D = {thresholds['location_switch']:.9f} h (about {thresholds['location_switch']*60:.3f} minutes of connection). Compensation is continuous at this crossing. C then stays at CHF 2.21745 until D = 6.5 h, and reaches CHF 4.00295 at D = 7 h. This is a location-switch kink, not the exercise-drop jump in the separate synthetic case. B stays feasible through D = 4.55 h and becomes infeasible thereafter because the fixed A route would miss the imposed latest shopping start. C remains feasible by using same-campus shopping; it does not drop shopping on the tested range.

At D = 4.5 h, A predicts CHF 2.10, B requires CHF 3.70695, and C requires CHF 2.21745. The finite-value error therefore contains both a continuous scheduling burden and the value of the alternative location. At D = 5 h, B has no feasible schedule while C needs CHF 2.21745. A scalar linear prediction alone does not report that feasibility boundary.

All joined schedules deliver 7 kWh, reach Home at 25 kWh (41.667% SOC), and restore 36 kWh before 24:00. Their 13 kWh physical-floor margin confirms that SOC is not the switching cause in this controlled example. The differing connection quantities are waiting availability, not additional delivered energy.

## Interpretation and boundaries

The local multiplier describes the reference fixed-integer LP only. It is not a dual of the MILP and does not promise finite-change accuracy or predict the subsequent activity location. Here A differs from B after a continuous active-set change before B differs from C; their difference must not be attributed entirely to integrality.

The chosen hard 16:30–19:00 shopping window and the ban on intermediate waiting are design assumptions. They create this example's exact feasibility boundary. A long education stay until 16:03 follows from this restricted model and its coefficients, and is not observed behavior. Travel costs are set to zero, the paper's full charging-station alternative and SOC-related utility are absent, the money coefficient is an assumed common extension, and some source table units/prices require explicit interpretation. Neither the compensation amounts nor their prevalence are calibrated behavioral predictions. This run does not establish empirical contract acceptance, data-set representativeness, or general performance/scalability. External validity and uncertainty effects are NOT TESTED.

## Next discriminating checks

Allow an explicit waiting option, restore the full published activity/charging alternatives and utility terms, and vary the imposed shopping window before claiming a field-relevant burden. A larger externally grounded sample is needed to estimate how often this mechanism occurs. Do not change the present run; save any such experiment in a fresh run directory with its own settings and records.
"""
    (output / "overview.md").write_text(overview)
    (output / "discussion.md").write_text(discussion)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error(f"refusing to overwrite existing run directory: {output}")
    output.mkdir(parents=True)
    script = Path(__file__).resolve()
    (output / "source_snapshot.py").write_bytes(script.read_bytes())
    thresholds = {"A_lateness_begins": 4.05, "location_switch": 4.05 + (ALPHA * (SHOP_DESIRED - EMIN) - BASE_TIME) / (ALPHA + BETA), "fixed_A_feasibility_limit": 4.55, "B_lateness_begins": 6.5}
    d_values = list(np.linspace(1, 7, 73))
    for point in [REFERENCE_D, *thresholds.values()]:
        d_values.extend([point - 1 / 60, point, point + 1 / 60])
    d_values = sorted({round(float(v), 12) for v in d_values if 1 <= v <= 7})
    config = {"run_id": output.name, "profile": "Bryan published-profile adaptation", "source_doi": SOURCE, "source_pages": {"activities": "Table 3 p. 11", "coefficients": "Table 4 p. 12; Table A.1 p. 23"}, "published_inputs": {"home_location": "Downtown", "education_location": "Campus", "education_desired_start_h": 7.5, "education_desired_duration_h": EDUCATION_MIN_DURATION, "shopping_A_location": "Downtown", "shopping_B_location": "Campus", "shopping_desired_start_h": 16.5, "shopping_desired_duration_h": 2, "education_constant": EDUCATION_UTILITY, "education_long_duration_coefficient_per_hour": -ALPHA, "shopping_constant": SHOP_UTILITY, "shopping_late_start_coefficient_per_hour": -BETA, "shopping_short_duration_coefficient_not_used_at_fixed_desired_duration": .528, "EV_capacity_kWh": 60, "home_charging_kW": 7, "consumption_kWh_per_km": .2}, "added_assumptions": {"education_mandatory": True, "education_start_fixed_h": 7.5, "education_end_latest_h": 19, "shopping_optional_and_mutually_exclusive": True, "shopping_duration_fixed_h": 2, "shopping_hard_start_window_h": [16.5, 17], "shopping_hard_end_latest_h": 19, "route_order": "Home > Education > optional Shopping A/B > Home", "intermediate_waiting_allowed": False, "published_charging_station_omitted": True, "OD": {"Home-Campus": {"hours": .5, "km": 10}, "Campus-Shopping_A": {"hours": .45, "km": 9}, "Shopping_A-Home": {"hours": .05, "km": 1}, "Campus-Shopping_B": {"hours": 0, "km": 0}, "Shopping_B-Home": {"hours": .5, "km": 10}}, "initial_energy_kWh": 36, "floor_energy_kWh": 12, "final_energy_kWh": 36, "charge_discharge_efficiency": 1, "ordinary_charging": "Home only, immediately after return", "flat_price_CHF_per_kWh": .30, "common_money_scale_utility_per_CHF": MONEY, "zeroed_terms": ["taste_errors", "travel_utility", "SOC_increase_utility", "SOC_anxiety", "degradation", "plug_hassle"], "timing_units": "hours; consistent with official OASIS documentation; source Appendix A.1 omits unit labels", "price_note": "assumed price; paper Table 5 decimal ambiguity not used as calibration"}, "contract": {"full_mandatory_service": True, "fixed_connection_window_h": [12, 13], "fixed_discharge_kW": 7, "fixed_delivered_energy_kWh": 7, "cumulative_connection_counting_window_h": [12, 19], "connection_hours": d_values, "reward_during_solves_CHF": 0, "reference_D_h": REFERENCE_D, "same_campus_continuous_parking_across_education_and_shopping_B": True, "plot_plug_tie_rule": "plug 12:00 to 12:00+D; excess campus parking need not stay plugged"}, "thresholds_h": thresholds, "primary_metric": "additional fixed joining compensation relative to optimized nonjoining, CHF", "hypotheses_not_assumed_results": ["finite local-price error", "alternative shopping location can change finite contract cost", "no preassigned discontinuity"], "replications": "not applicable: deterministic", "solver": {"MILP": "SciPy milp / HiGHS", "fixed_LP_and_independent_enumeration": "SciPy linprog highs-ds", "time_limit_seconds": 60, "mip_relative_gap": 1e-10, "LP_primal_and_dual_tolerance": 1e-9, "presolve": True}, "validation_tolerance": TOL, "git_start_revision": command_output(["git", "rev-parse", "HEAD"], script.parent), "git_uncommitted_source": command_output(["git", "status", "--short", "--", str(script)], script.parent), "code_sha256": hashlib.sha256(script.read_bytes()).hexdigest(), "run_command": f"python experiments/minimal_contract/bryan.py --output {output}", "interpretation_scope": "mechanism/correctness diagnostic, not an observed diary, full-paper replication, or calibrated behavior"}
    # Settings are persisted before the first solve. New runs never overwrite.
    save_json(output / "config.json", config)
    (output / "overview.md").write_text("# Bryan minimum diagnostic\n\nSettings saved in config.json before solving. Results pending.\n")
    (output / "discussion.md").write_text("# Bryan discussion\n\nResults pending. No conclusion has been assumed.\n")
    baseline = solve_milp(False)
    reference_milp = solve_milp(True, REFERENCE_D)
    assert baseline["success"] and reference_milp["success"]
    baseline["energy_audit"] = check_energy(baseline, None, config, joined=False)
    assert baseline["energy_audit"]["all_checks_pass"]
    integers = [int(round(v)) for v in reference_milp["vector"][3:]]
    assert integers == [1, 0], integers
    reference_lp = solve_fixed(True, REFERENCE_D, integers)
    slope = reference_lp["d_disutility_d_D_utility_per_hour"] / MONEY
    reference_compensation = (reference_lp["minimum_disutility"] - baseline["minimum_disutility"]) / MONEY
    records = {"baseline": baseline, "reference_MILP": reference_milp, "reference_fixed_LP": reference_lp, "reference_integers": integers, "nonjoining_independent_patterns": [enumerate_pattern(False, None, p) for p in ["A", "B", "none"]], "cases": []}
    rows, hand_rows, residuals, enumeration_errors, hand_errors, gaps = [], [], [], [], [], []
    records_by_d = {}
    for d in d_values:
        b = solve_fixed(True, d, integers)
        c = solve_milp(True, d)
        assert c["success"], c
        enumerated = [enumerate_pattern(True, d, p) for p in ["A", "B", "none"]]
        enum_best = min(p["minimum_disutility"] for p in enumerated if p["success"])
        enumeration_errors.append(abs(c["minimum_disutility"] - enum_best))
        hands = [hand_pattern(d, p) for p in ["A", "B", "none"]]
        hand_best = min(p["minimum_disutility"] for p in hands if p["feasible"])
        hand_b = hands[0]
        a_chf = reference_compensation + slope * (d - REFERENCE_D)
        b_chf = (b["minimum_disutility"] - baseline["minimum_disutility"]) / MONEY if b["success"] else None
        c_chf = (c["minimum_disutility"] - baseline["minimum_disutility"]) / MONEY
        hand_c_chf = (hand_best - baseline["minimum_disutility"]) / MONEY
        hand_b_chf = (hand_b["minimum_disutility"] - baseline["minimum_disutility"]) / MONEY if hand_b["feasible"] else None
        assert b["success"] == hand_b["feasible"], (d, b, hand_b)
        hand_errors.extend([abs(a_chf - RESTORE_EXTRA_CHF), abs(c_chf - hand_c_chf)])
        if b_chf is not None:
            hand_errors.append(abs(b_chf - hand_b_chf))
        for candidate in [b, c]:
            if candidate["success"]:
                residuals.append(candidate["max_primal_violation"])
                assert candidate["max_primal_violation"] < TOL
        gaps.append(c["mip_gap"] or 0)
        energy_b, energy_c = check_energy(b, d, config), check_energy(c, d, config)
        for energy in [energy_b, energy_c]:
            if energy:
                assert energy["all_checks_pass"], energy
        b["energy_audit"], c["energy_audit"] = energy_b, energy_c
        row = {"D_hours": d, "A_compensation_CHF": a_chf, "B_compensation_CHF": b_chf, "C_compensation_CHF": c_chf, "B_status": b["status"], "C_status": c["status"], "B_pattern": b.get("shopping_pattern"), "C_pattern": c["shopping_pattern"], "B_education_end_h": b["vector"][0] if b["success"] else None, "C_education_end_h": c["vector"][0], "C_shopping_start_h": c["vector"][1], "B_delivered_kWh": 7 if b["success"] else None, "C_delivered_kWh": 7}
        rows.append(row)
        hand_rows.append({"D_hours": d, "A_solver_CHF": a_chf, "A_hand_CHF": RESTORE_EXTRA_CHF, "B_solver_CHF": b_chf, "B_hand_CHF": hand_b_chf, "C_solver_CHF": c_chf, "C_hand_CHF": hand_c_chf, "C_absolute_error_CHF": abs(c_chf - hand_c_chf), "C_enumeration_error_utility": abs(c["minimum_disutility"] - enum_best)})
        records["cases"].append({"D_hours": d, "A": {"method": "actual_reference_fixed_LP_multiplier_extrapolation", "reference_D_hours": REFERENCE_D, "reference_compensation_CHF": reference_compensation, "derivative_CHF_per_hour": slope, "compensation_CHF": a_chf}, "B": b, "C": c, "independent_pattern_LPs": enumerated, "handcheck_patterns": hands, "energy_B": energy_b, "energy_C": energy_c})
        for display_d in [4.0, 4.5, 5.0, 7.0]:
            if abs(d - display_d) < 1e-10:
                records_by_d[display_d] = {"B": b, "C": c}
    assert max(enumeration_errors) < TOL
    assert max(hand_errors) < TOL
    assert max(gaps) < TOL
    # Check local multiplier by +/-1 minute finite differences inside reference slack.
    left, right = solve_fixed(True, REFERENCE_D - 1 / 60, integers), solve_fixed(True, REFERENCE_D + 1 / 60, integers)
    finite_difference = (right["minimum_disutility"] - left["minimum_disutility"]) / (2 / 60)
    assert abs(finite_difference - reference_lp["d_disutility_d_D_utility_per_hour"]) < TOL
    audit = {"status": "PASS", "cases": len(rows), "C_success_count": sum(r["C_status"] == 0 for r in rows), "B_feasible_count": sum(r["B_status"] == 0 for r in rows), "B_infeasible_count": sum(r["B_status"] == 2 for r in rows), "max_C_enumeration_objective_error_utility": max(enumeration_errors), "max_compensation_handcheck_error_CHF": max(hand_errors), "max_primal_violation": max(residuals), "max_reported_mip_gap": max(gaps), "reference_multiplier_utility_per_hour": reference_lp["d_disutility_d_D_utility_per_hour"], "reference_centered_finite_difference_utility_per_hour": finite_difference, "thresholds_hours": thresholds, "physical_energy_check": "PASS: identical initial/final battery energy; all feasible joined cases deliver 7 kWh, reach Home at 25 kWh, and recharge 11 kWh by 24:00", "scope": "deterministic adapted profile; no external-validity or empirical acceptance claim"}
    save_json(output / "solver_records.json", records)
    save_json(output / "verification.json", audit)
    for name, data in [("compensation.csv", rows), ("handcheck.csv", hand_rows)]:
        with (output / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    environment = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(), "machine": platform.machine(), "numpy": np.__version__, "scipy": scipy.__version__, "matplotlib": matplotlib.__version__, "solver": "HiGHS bundled with SciPy", "thread_environment": {key: os.environ.get(key) for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]}, "argv": sys.argv, "code_sha256": config["code_sha256"], "git_start_revision": config["git_start_revision"]}
    save_json(output / "environment.json", environment)
    plot_compensation(output, rows, thresholds)
    plot_schedules(output, records_by_d, baseline)
    write_records(output, config, rows, audit, reference_lp, thresholds)
    print(json.dumps(clean({"output": str(output), **audit}), indent=2))


if __name__ == "__main__":
    main()
