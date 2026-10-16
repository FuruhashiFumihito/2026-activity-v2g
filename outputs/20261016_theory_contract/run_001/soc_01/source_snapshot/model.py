"""Paired, exact-scenario contract mechanism experiment (authored inputs).

The sole structural binary is planned gym participation. Work duration, charging,
and participation are common before cancellation; surviving durations/order and
connection offsets are preserved. This is not the full manuscript implementation.
"""
from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import math
import time
import warnings
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, OptimizeWarning, linprog, milp

TOL = 2e-7
OPTIONS = {"time_limit": 10.0, "presolve": True, "threads": 1}
# This is a deliberately fixed numerical mechanism model, not a generic input
# parser. Reject edited input descriptions instead of silently ignoring them.
SUPPORTED_INPUTS_SHA256 = "df33cc9fd60fb558f1046e7c45d639c924867bded0e80f1b551590ea2938a02a"


def scenarios(p_cancel):
    return [(xi, prob) for xi, prob in [(1, 1-p_cancel), (0, p_cancel)] if prob > 0]


def make_model(case, joined, fixed_g=None):
    p, d = case["p_cancel"], case["D_h"]
    access, guarantee = case["appointment_v2g_access"], case["guarantee_kWh"]
    ss = scenarios(p)
    # [work_departure, common_pre_service_charge, planned_gym,
    #  (realized_gym_start, early, late, connection_shortfall) per scenario].
    names = ["work_departure_h", "precharge_kWh", "planned_gym"]
    for xi, _ in ss:
        names += [f"gym_start_xi{xi}", f"early_xi{xi}", f"late_xi{xi}", f"shortfall_xi{xi}"]
    n = len(names)
    cost = np.zeros(n)
    cost[:3] = [1200, 30, -3000]
    lo, hi = np.zeros(n), np.full(n, np.inf)
    lo[0], hi[0], hi[1], hi[2] = 17, 20, 6, 1
    if fixed_g is not None:
        lo[2] = hi[2] = fixed_g
    q = 6.0 if joined else 0.0
    mean_xi = 1-p
    constant = -1200*17 + 30*(4+q+.5*mean_xi) + 2*(4+2*q+.5*mean_xi) - 750*mean_xi
    rows, rhs, row_names, d_rhs = [], [], [], []

    def add(name, terms, bound, derivative=0.0):
        row = np.zeros(n)
        for index, coefficient in terms.items():
            row[index] = coefficient
        rows.append(row)
        rhs.append(bound)
        row_names.append(name)
        d_rhs.append(derivative)

    # The nominal all-activities plan must remain feasible even when its state
    # has zero realized probability. No waiting or freed-duration reallocation.
    physical_states = sorted({1, *(xi for xi, _ in ss)})
    add("nominal_gym_start_deadline", {0: 1, 2: 24}, 17.5+24)
    add("work_arrival_physical_SOC", {}, 36-2-12)
    add("precharge_capacity", {1: 1}, 60-(36-2))
    for xi in physical_states:
        add(f"home_physical_SOC_xi{xi}", {1: -1}, 36-4-q-.5*xi-12)
        add(f"nonnegative_home_charge_xi{xi}", {1: 1}, 4+q+.5*xi)
        # home = work departure + .5 + .75 xi + gym; recharge at 6 kW.
        add(f"home_charge_deadline_xi{xi}", {0: 1, 2: 1, 1: -1/6},
            24-.5-.75*xi-(4+q+.5*xi)/6)
        if joined:
            add(f"work_arrival_contract_SOC_xi{xi}", {}, 36-2-guarantee)
            add(f"post_dispatch_contract_SOC_xi{xi}", {1: -1}, 36-2-q-guarantee)
            if xi and access:
                add("appointment_contract_SOC", {1: -1}, 36-2-q-.25-guarantee)
    for k, (xi, prob) in enumerate(ss):
        t, early, late, short = range(3+4*k, 7+4*k)
        cost[early], cost[late] = 300*prob, 600*prob
        hi[t], hi[early], hi[late] = 24, 24, 24
        add(f"gym_zero_if_absent_xi{xi}", {t: 1, 2: -24}, 0)
        add(f"gym_latest_xi{xi}", {t: 1, 2: -18.5}, 0)
        shift = .25+.75*xi
        add(f"gym_link_upper_xi{xi}", {t: 1, 0: -1, 2: 24}, 24+shift)
        add(f"gym_link_lower_xi{xi}", {t: -1, 0: 1, 2: 24}, 24-shift)
        add(f"gym_early_xi{xi}", {2: 18, t: -1, early: -1}, 0)
        add(f"gym_late_xi{xi}", {t: 1, 2: -18, late: -1}, 0)
        if joined:
            if case["fulfillment"] == "hard":
                hi[short] = 0
                add(f"connection_D_xi{xi}", {0: -1}, -(16+d)+xi*.5*access, -1)
            else:
                cost[short] = 2400*prob
                add(f"connection_D_xi{xi}", {0: -1, short: -1}, -(16+d)+xi*.5*access, -1)
        else:
            hi[short] = 0
    return dict(cost=cost, lo=lo, hi=hi, A=np.array(rows), rhs=np.array(rhs),
                row_names=row_names, d_rhs=np.array(d_rhs), constant=constant,
                names=names, scenarios=ss)


def solve(case, joined=True, fixed_g=None):
    m = make_model(case, joined, fixed_g)
    start = time.perf_counter()
    # SciPy forwards this explicit backend option to HiGHS. Suppress only the
    # expected forwarding notice, not numerical or solver warnings.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unrecognized options detected:.*threads.*", category=RuntimeWarning)
        warnings.filterwarnings("ignore", message="Unrecognized options detected:.*threads.*", category=OptimizeWarning)
        if fixed_g is None:
            integrality = np.zeros(len(m["names"]), dtype=int)
            integrality[2] = 1
            result = milp(m["cost"], integrality=integrality,
                          bounds=Bounds(m["lo"], m["hi"]),
                          constraints=LinearConstraint(m["A"], -np.inf, m["rhs"]),
                          options={**OPTIONS, "mip_rel_gap": 0.0})
        else:
            result = linprog(m["cost"], A_ub=m["A"], b_ub=m["rhs"],
                             bounds=list(zip(m["lo"], m["hi"])), method="highs-ds",
                             options={**OPTIONS, "primal_feasibility_tolerance": 1e-9,
                                      "dual_feasibility_tolerance": 1e-9})
    record = dict(status=int(result.status), message=result.message,
                  elapsed_s=time.perf_counter()-start, cost=None, vector=None,
                  mip_gap=getattr(result, "mip_gap", None),
                  mip_dual_bound=getattr(result, "mip_dual_bound", None),
                  mip_node_count=getattr(result, "mip_node_count", None),
                  objective_constant=m["constant"], method="MILP" if fixed_g is None else "fixed_LP")
    if result.status == 0:
        x = result.x
        slack = m["rhs"]-m["A"] @ x
        record.update(cost=float(result.fun+m["constant"]),
                      vector=dict(zip(m["names"], map(float, x))),
                      max_primal_violation=float(max(0, max(-slack), max(m["lo"]-x), max(x-m["hi"]))),
                      max_integrality_residual=float(abs(x[2]-round(x[2]))),
                      constraint_slack=dict(zip(m["row_names"], map(float, slack))))
        if fixed_g is not None:
            marginals = result.ineqlin.marginals
            record["constraint_marginals"] = dict(zip(m["row_names"], map(float, marginals)))
            record["d_cost_d_D"] = float(np.dot(marginals, m["d_rhs"]))
        record["audit"] = audit(case, joined, record)
    return record


def audit(case, joined, record):
    """Physical and utility reconstruction, independent of constraint matrices."""
    v = record["vector"]
    w, charge, g = v["work_departure_h"], v["precharge_kWh"], round(v["planned_gym"])
    q = 6 if joined else 0
    expected_cost = 1200*(w-17)-3000*g+60*charge
    states, max_violation = [], 0.0
    for xi in sorted({1, *(xi for xi, _ in scenarios(case["p_cancel"]))}, reverse=True):
        gym_start = w+.25+.75*xi if g else None
        home = w+.5+.75*xi+g
        home_energy = 36-4+charge-q-.5*xi
        recovery = 36-home_energy
        points = [[0, 36], [8.5, 36], [9, 34],
                  [16-charge/6, 34], [16, 34+charge], [17, 34+charge-q], [w, 34+charge-q]]
        segments = [dict(activity="home", start=0, end=8.5),
                    dict(activity="travel", start=8.5, end=9),
                    dict(activity="work", start=9, end=w)]
        if xi:
            u_start = w+.125
            points += [[u_start, 33.75+charge-q], [u_start+.5, 33.75+charge-q]]
            segments += [dict(activity="travel", start=w, end=u_start),
                         dict(activity="appointment", start=u_start, end=u_start+.5)]
        previous = w+.625 if xi else w
        if g:
            points += [[gym_start, 33.5+charge-q-.5*xi],
                       [gym_start+1, 33.5+charge-q-.5*xi]]
            segments += [dict(activity="travel", start=previous, end=gym_start),
                         dict(activity="gym", start=gym_start, end=gym_start+1)]
            previous = gym_start+1
        segments += [dict(activity="travel", start=previous, end=home),
                     dict(activity="home", start=home, end=24)]
        points += [[home, home_energy], [home+recovery/6, 36], [24, 36]]
        connected = w-16+xi*.5*case["appointment_v2g_access"] if joined else 0
        short = max(0, case["D_h"]-connected) if joined else 0
        probability = (1-case["p_cancel"]) if xi else case["p_cancel"]
        early = max(0, 18-gym_start) if g else 0
        late = max(0, gym_start-18) if g else 0
        physical = max(0, 12-min(z[1] for z in points), max(z[1] for z in points)-60,
                       home+recovery/6-24, -recovery, 17-w, w-20, -charge, charge-6)
        if g:
            physical = max(physical, gym_start-18.5)
        if joined:
            guarantee_values = [34, 34+charge-q]
            if xi and case["appointment_v2g_access"]:
                guarantee_values += [33.75+charge-q]
            physical = max(physical, case["guarantee_kWh"]-min(guarantee_values))
        realized = xi in {a for a, _ in scenarios(case["p_cancel"])}
        if realized:
            if joined and case["fulfillment"] == "hard":
                physical = max(physical, short)
            if g:
                physical = max(physical, abs(v[f"gym_start_xi{xi}"]-gym_start))
            physical = max(physical, abs(v[f"early_xi{xi}"]-early), abs(v[f"late_xi{xi}"]-late))
            if joined and case["fulfillment"] == "soft":
                physical = max(physical, abs(v[f"shortfall_xi{xi}"]-short))
            expected_cost += probability*(300*early+600*late-750*xi+30*recovery+
                                         2*(charge+q+recovery)+
                                         (2400*short if joined and case["fulfillment"] == "soft" else 0))
        max_violation = max(max_violation, physical)
        states.append(dict(xi=xi, probability=probability, nominal_plan_check=True,
                           realized=realized, work_departure_h=w, gym_start_h=gym_start,
                           gym=g, precharge_kWh=charge, home_arrival_h=home,
                           home_charge_end_h=home+recovery/6, recovery_kWh=recovery,
                           route_energy_kWh=4+.5*xi, delivered_kWh=q,
                           connection_h=connected, shortfall_h=short,
                           fulfilled=(short <= TOL) if joined else None,
                           maximum_violation=max(0, physical), soc_points=points, segments=segments))
    return dict(passed=max_violation <= TOL and abs(expected_cost-record["cost"]) <= TOL,
                maximum_violation=max(0, max_violation),
                reconstructed_cost=expected_cost,
                objective_error=abs(expected_cost-record["cost"]), states=states)


def independent_lp(case, joined, g):
    """Separate route LP: eliminate gym start and all binary/big-M rows."""
    ss, q = scenarios(case["p_cancel"]), 6 if joined else 0
    # Variables: w, charge, then early/late/shortfall for each realized state.
    n = 2+3*len(ss)
    c = np.zeros(n)
    c[:2] = [1200, 30]
    lb, ub = np.zeros(n), np.full(n, np.inf)
    lb[0], ub[0], ub[1] = 17, (17.5 if g else 20), min(6, 60-34)
    physical = sorted({1, *(xi for xi, _ in ss)})
    lb[1] = max([0]+[12-(36-4-q-.5*xi) for xi in physical])
    ub[1] = min(ub[1], min(4+q+.5*xi for xi in physical))
    if 34 < 12 or (joined and case["guarantee_kWh"] > 34+1e-12):
        return dict(status=2, cost=None, gym=g, method="independent_route_LP")
    if joined:
        lb[1] = max(lb[1], case["guarantee_kWh"]-(34-q))
        if case["appointment_v2g_access"]:
            lb[1] = max(lb[1], case["guarantee_kWh"]-(33.75-q))
    if lb[1] > ub[1]+1e-12:
        return dict(status=2, cost=None, gym=g, method="independent_route_LP")
    rows, rhs = [], []
    def add(terms, bound):
        row = np.zeros(n)
        for i, z in terms.items():
            row[i] = z
        rows.append(row)
        rhs.append(bound)
    for xi in physical:
        add({0: 1, 1: -1/6}, 24-.5-.75*xi-g-(4+q+.5*xi)/6)
    for k, (xi, prob) in enumerate(ss):
        early, late, short = range(2+3*k, 5+3*k)
        if g:
            add({0: -1, early: -1}, .25+.75*xi-18)
            add({0: 1, late: -1}, 18-.25-.75*xi)
            c[early], c[late] = 300*prob, 600*prob
        else:
            ub[early] = ub[late] = 0
        if joined and case["fulfillment"] == "hard":
            lb[0] = max(lb[0], 16+case["D_h"]-.5*xi*case["appointment_v2g_access"])
            ub[short] = 0
        elif joined:
            add({0: -1, short: -1}, -(16+case["D_h"])+.5*xi*case["appointment_v2g_access"])
            c[short] = 2400*prob
        else:
            ub[short] = 0
    if np.any(lb > ub+1e-12):
        return dict(status=2, cost=None, gym=g, method="independent_route_LP")
    mean_xi = 1-case["p_cancel"]
    constant = -20400-3000*g-750*mean_xi + 30*(4+q+.5*mean_xi)+2*(4+2*q+.5*mean_xi)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unrecognized options detected:.*threads.*", category=OptimizeWarning)
        result = linprog(c, A_ub=np.array(rows), b_ub=np.array(rhs), bounds=list(zip(lb, ub)),
                         method="highs-ds", options={**OPTIONS, "primal_feasibility_tolerance": 1e-9,
                                                    "dual_feasibility_tolerance": 1e-9})
    return dict(status=int(result.status), cost=float(result.fun+constant) if result.status == 0 else None,
                gym=g, method="independent_route_LP", vector=result.x.tolist() if result.x is not None else None)


def analytical_oracle(case, joined):
    """Third check: enumerate kink/end points of each one-dimensional route cost.

    Over this predeclared domain, home recharging finishes by 24 even for w=20,
    so expensive work precharge is exactly the minimum required by SOC.
    """
    q = 6 if joined else 0
    floor = case["guarantee_kWh"]
    charge = max(0, 12-(36-4-q-.5))
    if joined:
        if floor > 34+1e-12:
            return dict(cost=None, status=2, patterns=[])
        charge = max(charge, floor-(34-q))
        if case["appointment_v2g_access"]:
            charge = max(charge, floor-(33.75-q))
    if charge > 6+1e-12:
        return dict(cost=None, status=2, patterns=[])
    patterns = []
    for g in (0, 1):
        low, high = 17, 17.5 if g else 20
        ss = scenarios(case["p_cancel"])
        if joined and case["fulfillment"] == "hard":
            low = max([low]+[16+case["D_h"]-.5*xi*case["appointment_v2g_access"] for xi, _ in ss])
        if low > high+1e-12:
            patterns.append(dict(gym=g, cost=None, status=2))
            continue
        candidates = [low, high]
        for xi, _ in ss:
            candidates += [18-.25-.75*xi, 16+case["D_h"]-.5*xi*case["appointment_v2g_access"]]
        outcomes = []
        for w in sorted({min(high, max(low, z)) for z in candidates}):
            total = 1200*(w-17)-3000*g+60*charge
            for xi, prob in ss:
                t = w+.25+.75*xi
                home = w+.5+.75*xi+g
                recovery = 4+q+.5*xi-charge
                if home+recovery/6 > 24+1e-10:
                    raise AssertionError("oracle domain prerequisite violated")
                conn = w-16+.5*xi*case["appointment_v2g_access"]
                short = max(0, case["D_h"]-conn) if joined else 0
                total += prob*((300*max(0, 18-t)+600*max(0, t-18))*g-750*xi+
                               30*recovery+2*(charge+q+recovery)+
                               (2400*short if joined and case["fulfillment"] == "soft" else 0))
            outcomes.append(dict(work_departure_h=w, cost=total))
        best = min(outcomes, key=lambda z: z["cost"])
        patterns.append(dict(gym=g, status=0, precharge_kWh=charge, **best))
    feasible = [z for z in patterns if z["status"] == 0]
    return dict(cost=min(z["cost"] for z in feasible) if feasible else None,
                status=0 if feasible else 2, patterns=patterns)
