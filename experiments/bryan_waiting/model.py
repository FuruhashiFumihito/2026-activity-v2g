"""Bryan waiting and limited-recourse diagnostic model.

Two common planned-location binaries and scenario-contingent continuous times.
Published profile provenance and all added assumptions are frozen by run.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import itertools
import math
import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

ALPHA = 0.0783
BETA = 0.993
EDUCATION_CONSTANT = 17.4
SHOPPING_CONSTANT = 11.3
MONEY = 0.3
PRICE = 0.3
EDUCATION_START = 7.5
EDUCATION_MIN_END = 7.5 + 4 + 40 / 60
SHOP_DESIRED = 16.5
SHOP_LATEST = 17.0
SHOP_DURATION = 2.0
CAPACITY = 60.0
INITIAL_ENERGY = 36.0
FINAL_ENERGY = 36.0
ENERGY_FLOOR = 12.0
HOME_CHARGE_KW = 7.0
CONSUMPTION = 0.2
SERVICE_START = 12.0
SERVICE_END = 13.0
SERVICE_KW = 7.0
TOL = 2e-7
TIE_TOL = 2e-8
PATTERNS = ("A", "B", "none")
PATTERN_BITS = {"A": (1, 0), "B": (0, 1), "none": (0, 0)}
CONTRACTS = ("hard", "auto_release", "event_only")
OD = {
    "Home-Campus": {"hours": .5, "km": 10.0},
    "Campus-Shopping_A": {"hours": .45, "km": 9.0},
    "Shopping_A-Home": {"hours": .05, "km": 1.0},
    "Campus-Shopping_B": {"hours": 0.0, "km": 0.0},
    "Shopping_B-Home": {"hours": .5, "km": 10.0},
    "Home-Shopping_A_added_symmetric": {"hours": .05, "km": 1.0},
}


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


@dataclass(frozen=True)
class State:
    name: str
    probability: float
    education_available: bool
    shopping_A_available: bool
    shopping_B_available: bool


def scenarios(family, probability):
    if family == "deterministic":
        assert probability == 0
        return [State("normal", 1.0, True, True, True)]
    if family == "uniform_activity":
        items = [State(f"E{e}_A{a}_B{b}", probability ** (e + a + b) * (1 - probability) ** (3 - e - a - b), bool(e), bool(a), bool(b)) for e, a, b in itertools.product([0, 1], repeat=3)]
        assert 0 <= probability <= 1
        return [state for state in items if state.probability > 0]
    if family == "education_cancel":
        items = [State("normal", 1 - probability, True, True, True), State("education_cancelled", probability, False, True, True)]
    elif family == "shopping_cancel":
        items = [State("normal", 1 - probability, True, True, True), State("shopping_cancelled", probability, True, False, False)]
    else:
        raise ValueError(f"unknown family: {family}")
    assert 0 <= probability <= 1
    return [state for state in items if state.probability > 0]


def has_service(state, contract):
    if contract == "none":
        return False
    if contract == "auto_release" and not state.education_available:
        return False
    assert contract in CONTRACTS
    return True


def campus_required(state, contract):
    return state.education_available or has_service(state, contract)


def required_departure(state, contract, connection):
    if not has_service(state, contract):
        return None
    return 12 + (1.0 if contract == "event_only" else connection)


class Problem:
    def __init__(self, states, gamma, contract, connection, family="deterministic", departure_policy="flexible"):
        assert 0 <= gamma < ALPHA
        self.states = list(states)
        self.gamma, self.contract, self.connection = gamma, contract, connection
        self.family, self.departure_policy = family, departure_policy
        self.names = ["planned_A", "planned_B"]
        self.lower, self.upper = [0.0, 0.0], [1.0, 1.0]
        self.cost = [0.0, 0.0]
        self.constant = 0.0
        self.state_variables = {}
        self.inequalities, self.equalities = [], []
        self.row_names, self.eq_names = [], []
        self.rhs, self.eq_rhs = [], []
        for state in states:
            indices = {}
            for name, lower, upper in [("departure", 0, 19), ("shopping_start", 0, 17), ("waiting", 0, 19), ("downtown_waiting", 0, 17), ("lateness", 0, 17)]:
                indices[name] = self.add_variable(state.name + ":" + name, lower, upper)
            if state.education_available:
                indices["education_end"] = self.add_variable(state.name + ":education_end", EDUCATION_MIN_END, 19)
            self.state_variables[state.name] = indices
        self.add_ineq({0: 1, 1: 1}, 1, "mutually_exclusive_common_location")
        for state in states:
            self.add_state(state)
        if family == "uniform_activity":
            education_ends = [self.state_variables[state.name]["education_end"] for state in states if state.education_available]
            for index in education_ends[1:]:
                self.add_eq({index: 1, education_ends[0]: -1}, 0, "uniform_shared_education_duration:" + self.names[index])

    def add_variable(self, name, lower, upper):
        index = len(self.names)
        self.names.append(name)
        self.lower.append(float(lower))
        self.upper.append(float(upper))
        self.cost.append(0.0)
        return index

    def row(self, coefficients):
        row = np.zeros(len(self.names))
        for index, coefficient in coefficients.items():
            row[index] += coefficient
        return row

    def add_ineq(self, coefficients, bound, name):
        self.inequalities.append(self.row(coefficients))
        self.rhs.append(float(bound))
        self.row_names.append(name)

    def add_eq(self, coefficients, bound, name):
        self.equalities.append(self.row(coefficients))
        self.eq_rhs.append(float(bound))
        self.eq_names.append(name)

    def add_state(self, state):
        prob = state.probability
        indices = self.state_variables[state.name]
        d, x, w, h = [indices[name] for name in ["departure", "shopping_start", "waiting", "lateness"]]
        wd = indices["downtown_waiting"]
        av_a, av_b = int(state.shopping_A_available), int(state.shopping_B_available)
        forced = campus_required(state, self.contract)
        service = has_service(state, self.contract)
        prefix = state.name + ":"
        self.add_ineq({x: -1, 0: SHOP_DESIRED * av_a, 1: SHOP_DESIRED * av_b}, 0, prefix + "shopping_earliest")
        self.add_ineq({x: 1, 0: -SHOP_LATEST * av_a, 1: -SHOP_LATEST * av_b}, 0, prefix + "shopping_latest")
        self.add_ineq({x: 1, h: -1, 0: -SHOP_DESIRED * av_a, 1: -SHOP_DESIRED * av_b}, 0, prefix + "lateness_hinge")
        if forced:
            self.upper[d] = 19
        else:
            # An unneeded campus visit is excluded for A/none; a planned B
            # shopping visit remains mandatory when that activity survives.
            self.add_ineq({d: 1, 1: -19 * av_b}, 0, prefix + "departure_zero_without_campus")
        waiting = {w: 1, d: -1, 1: SHOP_DURATION * av_b}
        if state.education_available:
            e = indices["education_end"]
            waiting[e] = 1
            self.add_eq(waiting, 0, prefix + "campus_waiting_balance")
            self.cost[e] += prob * ALPHA
            self.constant += prob * (-EDUCATION_CONSTANT - ALPHA * EDUCATION_MIN_END)
        elif service:
            campus_arrival = EDUCATION_START if self.departure_policy == "fixed_07" else SERVICE_START
            self.add_eq(waiting, -campus_arrival, prefix + "campus_waiting_balance")
        else:
            # B follows the scenario's departure policy; A/none never visit.
            campus_arrival = EDUCATION_START if self.departure_policy == "fixed_07" else SHOP_DESIRED
            waiting[1] += campus_arrival * av_b
            self.add_eq(waiting, 0, prefix + "campus_waiting_balance")
        big_m = 24.0
        if av_a and forced:
            self.add_ineq({d: 1, x: -1, 0: big_m}, big_m - .45, prefix + "A_departure_link_upper")
            self.add_ineq({d: -1, x: 1, 0: big_m}, big_m + .45, prefix + "A_departure_link_lower")
        if av_b:
            self.add_ineq({x: 1, d: -1, 1: big_m + SHOP_DURATION}, big_m, prefix + "B_shopping_precedes_departure")
            if state.education_available:
                self.add_ineq({indices["education_end"]: 1, x: -1, 1: big_m}, big_m, prefix + "education_precedes_B_shopping")
        if self.departure_policy == "fixed_07" and not forced and av_a:
            # A-only direct tour: 07:00 departure, 07:03 arrival, waiting
            # outside Home is charged by the same gamma as campus waiting.
            downtown_arrival = 7 + OD["Home-Shopping_A_added_symmetric"]["hours"]
            self.add_ineq({wd: 1, 0: -17}, 0, prefix + "downtown_wait_zero_without_A")
            self.add_ineq({wd: 1, x: -1, 0: big_m}, big_m - downtown_arrival, prefix + "downtown_wait_link_upper")
            self.add_ineq({wd: -1, x: 1, 0: big_m}, big_m + downtown_arrival, prefix + "downtown_wait_link_lower")
        else:
            self.upper[wd] = 0
        if service:
            self.add_ineq({d: -1}, -required_departure(state, self.contract, self.connection), prefix + "contract_departure")
        self.cost[w] += prob * self.gamma
        self.cost[wd] += prob * self.gamma
        self.cost[h] += prob * BETA
        self.cost[0] -= prob * SHOPPING_CONSTANT * av_a
        self.cost[1] -= prob * SHOPPING_CONSTANT * av_b
        if forced:
            self.constant += prob * MONEY * PRICE * (4 + (7 if service else 0))
        else:
            self.cost[0] += prob * MONEY * PRICE * .4 * av_a
            self.cost[1] += prob * MONEY * PRICE * 4 * av_b

    def matrices(self):
        n = len(self.names)
        return (np.array(self.inequalities, float).reshape((-1, n)), np.array(self.rhs), np.array(self.equalities, float).reshape((-1, n)), np.array(self.eq_rhs))

    def solve(self, pattern=None):
        c = np.array(self.cost)
        lower, upper = np.array(self.lower), np.array(self.upper)
        a, b, ae, be = self.matrices()
        start = time.perf_counter()
        if pattern is None:
            integrality = np.zeros(len(c), int)
            integrality[:2] = 1
            constraints = [LinearConstraint(a, -np.inf, b), LinearConstraint(ae, be, be)]
            result = milp(c, integrality=integrality, bounds=Bounds(lower, upper), constraints=constraints, options={"time_limit": 60, "mip_rel_gap": 1e-10, "presolve": True})
            method = "common_plan_MILP"
        else:
            lower[:2] = PATTERN_BITS[pattern]
            upper[:2] = PATTERN_BITS[pattern]
            result = linprog(c, A_ub=a, b_ub=b, A_eq=ae, b_eq=be, bounds=list(zip(lower, upper)), method="highs-ds", options={"time_limit": 60, "primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9})
            method = "fixed_common_pattern_LP"
        refinement = None
        primary_vector = None
        if pattern is not None and result.success:
            # Free waiting creates continuous timing ties. Preserve the exact
            # primary optimum, then choose earliest departure/start times for
            # display; primary LP duals remain those used for comparator A.
            tie_cost = np.zeros(len(c))
            for indices in self.state_variables.values():
                tie_cost[indices["departure"]] = 1
                tie_cost[indices["shopping_start"]] = 1
            primary_vector = result.x.copy()
            refined = linprog(tie_cost, A_ub=a, b_ub=b, A_eq=np.vstack([ae, c]), b_eq=np.append(be, result.fun), bounds=list(zip(lower, upper)), method="highs-ds", options={"time_limit": 60, "primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9})
            assert refined.success, refined
            primary_error = abs(float(c @ refined.x) - result.fun)
            assert primary_error < TOL
            result.x = refined.x
            refinement = {"status": int(refined.status), "success": bool(refined.success), "message": refined.message, "rule": "minimize sum of physical campus departures and realized shopping starts at fixed primary LP optimum", "primary_objective_error": primary_error}
        record = {"method": method, "fixed_pattern": pattern, "status": int(result.status), "success": bool(result.success), "message": result.message, "elapsed_seconds": time.perf_counter() - start, "objective_linear": result.fun, "objective_constant": self.constant, "minimum_disutility": float(result.fun + self.constant) if result.success else None, "vector": result.x, "variable_names": self.names, "max_primal_violation": None, "max_integrality_residual": None, "mip_gap": getattr(result, "mip_gap", None), "mip_dual_bound": getattr(result, "mip_dual_bound", None), "mip_node_count": getattr(result, "mip_node_count", None), "max_complementarity_residual": None}
        record["canonical_timing_refinement"] = refinement
        record["primary_LP_vector_before_timing_refinement"] = primary_vector
        if result.success:
            z = result.x
            slack, eq_residual = b - a @ z, be - ae @ z
            record.update({"pattern": "A" if z[0] > .5 else "B" if z[1] > .5 else "none", "inequality_names": self.row_names, "equality_names": self.eq_names, "inequality_residuals": slack, "equality_residuals": eq_residual, "lower_residuals": z - lower, "upper_residuals": upper - z, "max_primal_violation": float(max(0, np.max(-slack), np.max(np.abs(eq_residual)), np.max(lower - z), np.max(z - upper))), "max_integrality_residual": float(np.max(np.abs(z[:2] - np.round(z[:2]))))})
            assert record["max_primal_violation"] < TOL, record
            if pattern is not None:
                record.update({"inequality_marginals": result.ineqlin.marginals, "equality_marginals": result.eqlin.marginals, "lower_marginals": result.lower.marginals, "upper_marginals": result.upper.marginals, "max_complementarity_residual": float(np.max(np.abs(result.ineqlin.marginals * slack)))})
                if self.contract in ["hard", "auto_release"]:
                    record["derivative_D_utility_per_hour"] = float(-sum(result.ineqlin.marginals[i] for i, name in enumerate(self.row_names) if name.endswith(":contract_departure")))
                else:
                    record["derivative_D_utility_per_hour"] = 0.0
        return clean(record)


def independent_pattern_lp(states, gamma, contract, connection, pattern, departure_policy="flexible"):
    """Three-variable state LP with known pattern and e eliminated.

Since gamma < alpha, replacing any education overtime by campus waiting
strictly lowers the objective; hence e = its published minimum endpoint.
This formulation has no binary links or big-M rows.
"""
    c, bounds, rows, rhs, eqs, eqrhs = [], [], [], [], [], []
    const = 0.0
    per_state = []
    n = 3 * len(states)
    for i, state in enumerate(states):
        d, x, h = 3 * i, 3 * i + 1, 3 * i + 2
        available = state.shopping_A_available if pattern == "A" else state.shopping_B_available if pattern == "B" else False
        selected = available and pattern != "none"
        b_shop = selected and pattern == "B"
        service = has_service(state, contract)
        campus = campus_required(state, contract) or b_shop
        start = EDUCATION_MIN_END if state.education_available else EDUCATION_START if campus and departure_policy == "fixed_07" else SERVICE_START if service else SHOP_DESIRED if b_shop else 0.0
        downtown_wait = departure_policy == "fixed_07" and not campus and selected and pattern == "A"
        c.extend([state.probability * gamma if campus else 0, state.probability * gamma if downtown_wait else 0, state.probability * BETA])
        bounds.extend([(start + SHOP_DURATION * b_shop if campus else 0, 19 if campus else 0), (SHOP_DESIRED if selected else 0, SHOP_LATEST if selected else 0), (0, None if selected else 0)])
        if selected:
            row = np.zeros(n); row[x], row[h] = 1, -1
            rows.append(row); rhs.append(SHOP_DESIRED)
        if campus and selected and pattern == "A":
            row = np.zeros(n); row[d], row[x] = 1, -1
            eqs.append(row); eqrhs.append(-.45)
        if b_shop:
            row = np.zeros(n); row[x], row[d] = 1, -1
            rows.append(row); rhs.append(-SHOP_DURATION)
        if service:
            row = np.zeros(n); row[d] = -1
            rows.append(row); rhs.append(-required_departure(state, contract, connection))
        route = 4 if campus else .4 if selected and pattern == "A" else 0
        q = 7 if service else 0
        state_constant = -EDUCATION_CONSTANT * state.education_available - SHOPPING_CONSTANT * selected + MONEY * PRICE * (route + q) - (gamma * (start + SHOP_DURATION * b_shop) if campus else 0)
        if downtown_wait:
            state_constant -= gamma * (7 + OD["Home-Shopping_A_added_symmetric"]["hours"])
        const += state.probability * state_constant
        per_state.append({"state": state.name, "campus": campus, "start_or_education_end_h": start, "actual_shop": pattern if selected else "none", "route_energy_kWh": route, "q_kWh": q})
    begin = time.perf_counter()
    result = linprog(c, A_ub=np.array(rows) if rows else None, b_ub=np.array(rhs) if rows else None, A_eq=np.array(eqs) if eqs else None, b_eq=np.array(eqrhs) if eqs else None, bounds=bounds, method="highs-ds", options={"time_limit": 60, "primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9})
    return clean({"method": "independent_known_pattern_LP", "pattern": pattern, "success": bool(result.success), "status": int(result.status), "message": result.message, "elapsed_seconds": time.perf_counter() - begin, "minimum_disutility": float(result.fun + const) if result.success else None, "objective_constant": const, "vector_departure_shopping_lateness_per_state": result.x, "state_map": per_state, "inequality_residuals": result.ineqlin.residual if result.success else None, "equality_residuals": result.eqlin.residual if result.success else None})


def state_schedule(problem, solution, state):
    """Decode a solved schedule, then independently integrate travel and energy."""
    assert solution["success"]
    z = solution["vector"]
    p = solution["pattern"]
    indices = problem.state_variables[state.name]
    d, x, w, h = [z[indices[name]] for name in ["departure", "shopping_start", "waiting", "lateness"]]
    wd = z[indices["downtown_waiting"]]
    edu = state.education_available
    available = state.shopping_A_available if p == "A" else state.shopping_B_available if p == "B" else False
    actual = p if available and p != "none" else "none"
    b_shop = actual == "B"
    svc = has_service(state, problem.contract)
    campus = edu or svc or b_shop
    arrival = EDUCATION_START if edu or campus and problem.departure_policy == "fixed_07" else SERVICE_START if svc else SHOP_DESIRED if b_shop else None
    e = z[indices["education_end"]] if edu else None
    legs, activities = [], []
    if campus:
        departure_home = arrival - OD["Home-Campus"]["hours"]
        legs.append((departure_home, arrival, OD["Home-Campus"]["km"], "Home-Campus"))
        if edu:
            activities.append((arrival, e, "Education"))
        if actual == "A":
            legs.append((d, x, OD["Campus-Shopping_A"]["km"], "Campus-Shopping A"))
            activities.append((x, x + SHOP_DURATION, "Shopping A"))
            home = x + SHOP_DURATION + OD["Shopping_A-Home"]["hours"]
            legs.append((x + SHOP_DURATION, home, OD["Shopping_A-Home"]["km"], "Shopping A-Home"))
        elif actual == "B":
            activities.append((x, x + SHOP_DURATION, "Shopping B"))
            home = d + OD["Shopping_B-Home"]["hours"]
            legs.append((d, home, OD["Shopping_B-Home"]["km"], "Campus-Home"))
        else:
            home = d + OD["Home-Campus"]["hours"]
            legs.append((d, home, OD["Home-Campus"]["km"], "Campus-Home"))
        station_start = e if edu else arrival
        if b_shop:
            if x > station_start + 1e-10:
                activities.append((station_start, x, "Campus waiting"))
            if d > x + SHOP_DURATION + 1e-10:
                activities.append((x + SHOP_DURATION, d, "Campus waiting"))
        elif d > station_start + 1e-10:
            activities.append((station_start, d, "Campus waiting"))
    elif actual == "A":
        departure_home = 7.0 if problem.departure_policy == "fixed_07" else x - OD["Home-Shopping_A_added_symmetric"]["hours"]
        downtown_arrival = departure_home + OD["Home-Shopping_A_added_symmetric"]["hours"]
        legs.append((departure_home, downtown_arrival, OD["Home-Shopping_A_added_symmetric"]["km"], "Home-Shopping A"))
        if x > downtown_arrival + 1e-10:
            activities.append((downtown_arrival, x, "Downtown waiting"))
        activities.append((x, x + SHOP_DURATION, "Shopping A"))
        home = x + SHOP_DURATION + OD["Shopping_A-Home"]["hours"]
        legs.append((x + SHOP_DURATION, home, OD["Shopping_A-Home"]["km"], "Shopping A-Home"))
    else:
        departure_home, home = None, None
    segments = []
    for start, end, name in activities:
        if end - start > 1e-10:
            waiting = name in ["Campus waiting", "Downtown waiting"]
            segments.append({"activity": "Waiting" if waiting else name, "location": "Campus" if name == "Campus waiting" else "Downtown" if name == "Downtown waiting" else None, "start_h": start, "end_h": end})
    for start, end, _, _ in legs:
        if end - start > 1e-10:
            segments.append({"activity": "Travel", "start_h": start, "end_h": end})
    if departure_home is not None:
        segments += [{"activity": "Home", "start_h": 6.0, "end_h": departure_home}, {"activity": "Home", "start_h": home, "end_h": 24.0}]
    else:
        segments.append({"activity": "Home", "start_h": 6.0, "end_h": 24.0})
    segments.sort(key=lambda v: (v["start_h"], v["end_h"]))
    q = (SERVICE_END - SERVICE_START) * SERVICE_KW if svc else 0.0
    events = [{"kind": name, "start_h": start, "end_h": end, "delta_energy_kWh": -km * CONSUMPTION, "km": km} for start, end, km, name in legs]
    if svc:
        events.append({"kind": "V2G service", "start_h": SERVICE_START, "end_h": SERVICE_END, "delta_energy_kWh": -q, "km": 0.0})
    events.sort(key=lambda v: (v["start_h"], v["end_h"]))
    energy = INITIAL_ENERGY
    points = [{"time_h": 6.0, "energy_kWh": energy}]
    previous_end = 6.0
    no_overlap = True
    for event in events:
        no_overlap = no_overlap and event["start_h"] >= previous_end - TOL
        points.append({"time_h": event["start_h"], "energy_kWh": energy})
        energy += event["delta_energy_kWh"]
        points.append({"time_h": event["end_h"], "energy_kWh": energy})
        event["energy_after_kWh"] = energy
        previous_end = event["end_h"]
    energy_home = energy
    grid_charge = FINAL_ENERGY - energy
    charge_start = home if home is not None else 6.0
    charge_end = charge_start + grid_charge / HOME_CHARGE_KW
    energy += grid_charge
    if grid_charge > 1e-10:
        events.append({"kind": "Home recharge", "start_h": charge_start, "end_h": charge_end, "delta_energy_kWh": grid_charge, "energy_after_kWh": energy, "km": 0.0})
    points.extend([{"time_h": charge_end, "energy_kWh": energy}, {"time_h": 24.0, "energy_kWh": energy}])
    waiting_from_segments = sum(segment["end_h"] - segment["start_h"] for segment in segments if segment["activity"] == "Waiting")
    route_km = sum(km for _, _, km, _ in legs)
    route_energy = route_km * CONSUMPTION
    energy_cost = grid_charge * PRICE
    utility = EDUCATION_CONSTANT * edu + SHOPPING_CONSTANT * (actual != "none") - ALPHA * (e - EDUCATION_MIN_END if edu else 0) - BETA * h - problem.gamma * (w + wd) - MONEY * energy_cost
    activity_coverage = sum(segment["end_h"] - segment["start_h"] for segment in segments)
    minimum = min(point["energy_kWh"] for point in points)
    maximum = max(point["energy_kWh"] for point in points)
    required = required_departure(state, problem.contract, problem.connection)
    checks = {"nonoverlapping_energy_events": no_overlap, "SOC_floor": minimum >= ENERGY_FLOOR - TOL, "SOC_capacity": maximum <= CAPACITY + TOL, "final_energy_equality": abs(energy - FINAL_ENERGY) < TOL, "charge_completed_by_24": charge_end <= 24 + TOL, "nonnegative_recharge": grid_charge >= -TOL, "travel_charge_mass_balance": abs(grid_charge - route_energy - q) < TOL, "waiting_matches_solved_variable": abs(waiting_from_segments - w - wd) < TOL, "timeline_covers_day": abs(activity_coverage - 18) < TOL, "education_minimum": not edu or e >= EDUCATION_MIN_END - TOL, "shopping_window": actual == "none" or SHOP_DESIRED - TOL <= x <= SHOP_LATEST + TOL, "late_variable": abs(h - max(0, x - SHOP_DESIRED)) < TOL if actual != "none" else abs(h) < TOL, "contract_departure": required is None or d >= required - TOL, "event_on_campus": not svc or arrival <= SERVICE_START + TOL and d >= SERVICE_END - TOL, "zero_service_after_release": not (problem.contract == "auto_release" and not edu) or q == 0, "education_ends_at_minimum_when_gamma_below_alpha": not edu or abs(e - EDUCATION_MIN_END) < TOL, "first_departure_policy": problem.departure_policy != "fixed_07" or departure_home is None or abs(departure_home - 7) < TOL}
    result = {**asdict(state), "shopping_available": available, "departure_policy": problem.departure_policy, "planned_pattern": p, "actual_shop": actual, "campus_visit": bool(campus), "campus_arrival_h": arrival, "education_start_h": EDUCATION_START if edu else None, "education_end_h": e, "shopping_start_h": x if actual != "none" else None, "shopping_end_h": x + SHOP_DURATION if actual != "none" else None, "campus_departure_h": d if campus else None, "home_departure_h": departure_home, "home_arrival_h": home, "waiting_hours": w + wd, "campus_waiting_hours": w, "downtown_waiting_hours": wd, "late_start_hours": h, "q_kWh": q, "route_km": route_km, "route_energy_kWh": route_energy, "energy_cost_CHF": energy_cost, "utility": utility, "disutility_utility": -utility, "segments": segments, "plug_start_h": SERVICE_START if svc else None, "plug_end_h": required if svc else None, "soc": {"points": points, "events": events, "initial_energy_kWh": INITIAL_ENERGY, "home_arrival_energy_kWh": energy_home, "final_energy_kWh": energy, "minimum_energy_kWh": minimum, "physical_floor_margin_kWh": minimum - ENERGY_FLOOR, "recharge_kWh": grid_charge, "recharge_start_h": charge_start, "recharge_end_h": charge_end, "checks": checks, "all_checks_pass": all(checks.values())}}
    assert result["soc"]["all_checks_pass"], result
    return clean(result)


def solve_bundle(family, probability, gamma, contract, connection):
    states = scenarios(family, probability)
    departure_policy = "fixed_07" if family == "uniform_activity" else "flexible"
    problem = Problem(states, gamma, contract, connection, family, departure_policy)
    full = problem.solve()
    fixed = {pattern: problem.solve(pattern) for pattern in PATTERNS}
    independent = {pattern: independent_pattern_lp(states, gamma, contract, connection, pattern, departure_policy) for pattern in PATTERNS}
    assert full["success"], full
    pattern_errors = []
    for pattern in PATTERNS:
        assert fixed[pattern]["success"] == independent[pattern]["success"], (family, probability, gamma, contract, connection, pattern, fixed[pattern], independent[pattern])
        if fixed[pattern]["success"]:
            error = abs(fixed[pattern]["minimum_disutility"] - independent[pattern]["minimum_disutility"])
            pattern_errors.append(error)
            assert error < TOL, (pattern, error)
    best = min(solution["minimum_disutility"] for solution in fixed.values() if solution["success"])
    milp_error = abs(full["minimum_disutility"] - best)
    assert milp_error < TOL, (milp_error, full)
    ties = [pattern for pattern in PATTERNS if fixed[pattern]["success"] and abs(fixed[pattern]["minimum_disutility"] - best) <= TIE_TOL]
    # A->B->none is an explicit secondary rule among primary-optimal plans.
    chosen = ties[0]
    schedule_by_pattern = {}
    state_objective_errors = []
    for pattern in PATTERNS:
        if fixed[pattern]["success"]:
            decoded = [state_schedule(problem, fixed[pattern], state) for state in states]
            state_objective = sum(state["probability"] * state["disutility_utility"] for state in decoded)
            error = abs(state_objective - fixed[pattern]["minimum_disutility"])
            state_objective_errors.append(error)
            assert error < TOL, (pattern, error, decoded)
            schedule_by_pattern[pattern] = decoded
    expected_q = sum(state.probability * (7 if has_service(state, contract) else 0) for state in states)
    return {"family": family, "probability": probability, "gamma": gamma, "contract": contract, "D_hours": connection, "full": full, "fixed": fixed, "independent": independent, "canonical_pattern": chosen, "tie_patterns": ties, "canonical": fixed[chosen], "schedules": schedule_by_pattern, "expected_delivery_kWh": expected_q, "full_service_probability": expected_q / 7, "max_fixed_independent_error_utility": max(pattern_errors, default=0), "milp_enumeration_error_utility": milp_error, "max_state_objective_error_utility": max(state_objective_errors, default=0)}


def parameters():
    return {"published_inputs": {"profile": "Bryan", "home_location": "Downtown", "education_location": "Campus", "education_start_h": EDUCATION_START, "education_duration_h": 4 + 40 / 60, "education_constant": EDUCATION_CONSTANT, "education_long_duration_coefficient_per_hour": -ALPHA, "shopping_locations": {"A": "Downtown", "B": "Campus"}, "shopping_desired_start_h": SHOP_DESIRED, "shopping_duration_h": SHOP_DURATION, "shopping_constant": SHOPPING_CONSTANT, "shopping_late_start_coefficient_per_hour": -BETA, "shopping_short_duration_coefficient_not_used_at_fixed_duration": .528, "battery_capacity_kWh": CAPACITY, "home_charge_kW": HOME_CHARGE_KW, "consumption_kWh_per_km": CONSUMPTION}, "added_inputs": {"OD": OD, "initial_energy_kWh": INITIAL_ENERGY, "final_energy_kWh": FINAL_ENERGY, "floor_energy_kWh": ENERGY_FLOOR, "efficiency": 1, "price_CHF_per_kWh": PRICE, "money_utility_per_CHF": MONEY, "hard_shopping_start_window_h": [SHOP_DESIRED, SHOP_LATEST], "campus_departure_latest_h": 19, "waiting_cost_utility_per_hour": [0, .03915], "service_window_h": [SERVICE_START, SERVICE_END], "service_power_kW": SERVICE_KW, "service_kWh": 7, "timing_unit": "hours", "taste_errors_and_omitted_costs": 0}, "solver": {"MILP": "SciPy milp / HiGHS", "LP": "SciPy linprog highs-ds", "time_limit_seconds": 60, "mip_relative_gap": 1e-10, "LP_primal_dual_tolerance": 1e-9, "verification_tolerance": TOL, "primary_objective_tie_tolerance": TIE_TOL, "lexicographic_tie_order": list(PATTERNS)}}
