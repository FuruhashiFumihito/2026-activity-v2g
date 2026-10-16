#!/usr/bin/env python3
"""Independent analytic checks for Bryan waiting/contracts/cancellations.

No optimization library is used. Each common ex-ante shopping pattern is solved
by closed timing/energy formulas, then C takes the feasible lower envelope.
The derivation applies to 0 <= gamma < the long-education cost 0.0783.
"""
from __future__ import annotations
import argparse
import json
import itertools
import math

MU = 0.3
PRICE = 0.30
EDUCATION_START = 7.5
EDUCATION_END = 7.5 + 4.0 + 40.0 / 60.0
ALPHA = 0.0783
BETA = 0.993
EDUCATION_UTILITY = 17.4
SHOP_UTILITY = 11.3
SHOP_START = 16.5
SHOP_LAST_START = 17.0
SHOP_DURATION = 2.0
A_TRAVEL = 0.45
A_DEPARTURE_ON_TIME = SHOP_START - A_TRAVEL
A_D_SLACK = A_DEPARTURE_ON_TIME - 12.0  # 4.05 h
A_D_MAX = SHOP_LAST_START - A_TRAVEL - 12.0  # 4.55 h
B_D_ON_TIME = SHOP_START + SHOP_DURATION - 12.0  # 6.5 h
PATTERNS = ('A', 'B', 'none')
TOL = 1e-9


def canonical_family(family):
    aliases = {'det': 'deterministic', 'none': 'deterministic',
               'education': 'education_cancel', 'edu_cancel': 'education_cancel',
               'education_cancellation': 'education_cancel', 'shopping': 'shopping_cancel',
               'uniform': 'uniform_activity', 'uniform_occurrence': 'uniform_activity',
               'shop_cancel': 'shopping_cancel', 'shopping_cancellation': 'shopping_cancel'}
    family = aliases.get(family, family)
    if family not in ('deterministic', 'education_cancel', 'shopping_cancel', 'uniform_activity'):
        raise ValueError(f'Unknown scenario family: {family}')
    return family


def canonical_contract(contract):
    aliases = {'automatic_release': 'auto_release', 'release': 'auto_release',
               'event': 'event_only', 'fixed_clock': 'hard', 'fixed_interval': 'hard'}
    contract = aliases.get(contract, contract)
    if contract not in ('hard', 'auto_release', 'event_only'):
        raise ValueError(f'Unknown contract: {contract}')
    return contract


def scenarios(probability=0.0, family='deterministic'):
    """Zero-probability branches are absent, including their constraints."""
    p = float(probability)
    if not 0 <= p <= 1:
        raise ValueError('Cancellation probability must be in [0,1].')
    family = canonical_family(family)
    if family == 'uniform_activity':
        states=[]
        for education,a,b in itertools.product((False,True),repeat=3):
            n=int(education)+int(a)+int(b)
            probability=p**n*(1-p)**(3-n)
            if probability>0.0:
                states.append(dict(name=f'E{int(education)}_A{int(a)}_B{int(b)}',probability=probability,
                                   education=education,shopping=True,shopping_A=a,shopping_B=b,strict_first_departure=True))
        return states
    if family == 'deterministic':
        return [dict(name='normal', probability=1.0, education=True, shopping=True)]
    states = [dict(name='normal', probability=1.0-p, education=True, shopping=True)]
    states.append(dict(name='education_cancelled' if family == 'education_cancel' else 'shopping_cancelled',
                       probability=p, education=family != 'education_cancel', shopping=family != 'shopping_cancel'))
    return [s for s in states if s['probability'] > 0.0]


def service_active(joined, contract, state):
    return bool(joined and not (canonical_contract(contract) == 'auto_release' and not state['education']))


def scenario_path(pattern, state, *, joined, D, contract, gamma):
    """Exact minimum cost for one pattern/scenario, in utility disutility units.

    Uniform activity states preserve the common 07:00 first departure and charge
    every nonhome wait: a Campus tour arrives at 07:30; a direct A tour arrives
    Downtown at 07:03 and waits until 16:30. Empty released states stay home.
    Auxiliary cancellation controls retain flexible first departure: mandatory
    service reaches Campus at 12:00; a released B tour arrives at 16:30.
    """
    if pattern not in PATTERNS:
        raise ValueError(pattern)
    if not 0.0 <= gamma < ALPHA:
        raise ValueError('Analytic elimination of education extension requires 0 <= gamma < 0.0783.')
    contract = canonical_contract(contract)
    active = service_active(joined, contract, state)
    effective_D = 1.0 if contract == 'event_only' else float(D)
    lower_departure = 12.0 + effective_D if active else -math.inf
    available=state.get('shopping_'+pattern,state['shopping']) if pattern!='none' else False
    actual_shop = pattern if available else 'none'
    campus_required = bool(state['education'] or active or actual_shop == 'B')
    strict_first_departure=bool(state.get('strict_first_departure',False))
    campus_arrival = (EDUCATION_START if state['education'] or (strict_first_departure and campus_required)
                      else 12.0 if active else SHOP_START if actual_shop == 'B' else None)
    ready = EDUCATION_END if state['education'] else campus_arrival
    late = 0.0
    shopping_start = None
    departure = None
    waiting = 0.0
    if actual_shop == 'A' and campus_required:
        departure = max(A_DEPARTURE_ON_TIME, ready, lower_departure)
        shopping_start = departure + A_TRAVEL
        if shopping_start > SHOP_LAST_START + TOL:
            return dict(feasible=False, pattern=pattern, scenario=state['name'], reason='Downtown shopping hard finish window')
        waiting = departure - ready
        late = shopping_start - SHOP_START
        route_km = 20.0
        home = shopping_start + SHOP_DURATION + 0.05
    elif actual_shop == 'A':
        # Education cancelled and no service: direct H--A--H, 2 km.
        shopping_start = SHOP_START
        if strict_first_departure:
            waiting=SHOP_START-(7.0+0.05)
        route_km = 2.0
        home = shopping_start + SHOP_DURATION + 0.05
    elif actual_shop == 'B':
        shopping_start = SHOP_START
        departure = max(SHOP_START + SHOP_DURATION, lower_departure)
        waiting = departure - ready - SHOP_DURATION
        route_km = 20.0
        home = departure + 0.5
    elif campus_required:
        departure = max(ready, lower_departure)
        waiting = departure - ready
        route_km = 20.0
        home = departure + 0.5
    else:
        route_km = 0.0
        home = 6.0  # stays home, not a new physical tour
    if departure is not None and departure > 19.0 + TOL:
        return dict(feasible=False, pattern=pattern, scenario=state['name'], reason='Campus departure after 19:00')
    assert waiting >= -TOL
    waiting = max(0.0, waiting)
    service = 7.0 if active else 0.0
    travel_kWh = route_km * 0.2
    charging_kWh = travel_kWh + service
    home_charge_end = home + charging_kWh / 7.0
    assert home_charge_end <= 24.0 + TOL
    # Common initial/final SOC is 36 kWh; all discharges/travel precede recovery.
    minimum_energy = 36.0 - charging_kWh
    assert minimum_energy >= 12.0 - TOL
    cost = (MU * PRICE * charging_kWh + gamma * waiting + BETA * late
            - SHOP_UTILITY * (actual_shop != 'none') - EDUCATION_UTILITY * state['education'])
    # One-sided analytic derivative of this pattern's cost w.r.t. D.
    slope = 0.0
    if active and contract != 'event_only':
        if actual_shop == 'A':
            slope = gamma + BETA if lower_departure > A_DEPARTURE_ON_TIME + TOL else 0.0
        elif actual_shop == 'B':
            slope = gamma if lower_departure > SHOP_START + SHOP_DURATION + TOL else 0.0
        else:
            slope = gamma if lower_departure > ready + TOL else 0.0
    return dict(feasible=True, pattern=pattern, scenario=state['name'], actual_shopping=actual_shop,
                disutility=cost, waiting_h=waiting,
                waiting_location='Campus' if campus_required else 'Downtown' if waiting>0 else None,
                strict_first_departure=strict_first_departure,
                first_departure_h=(7.0 if strict_first_departure and route_km>0 else campus_arrival-.5 if campus_arrival is not None else SHOP_START-.05 if route_km>0 else None),
                campus_waiting_h=waiting if campus_required else 0.0,
                downtown_waiting_h=waiting if not campus_required else 0.0,late_shopping_h=late,
                education_end_h=EDUCATION_END if state['education'] else None,
                campus_arrival_h=campus_arrival, campus_departure_h=departure,
                shopping_start_h=shopping_start, home_arrival_h=home,
                route_km=route_km, travel_kWh=travel_kWh, service_kWh=service,
                home_charging_kWh=charging_kWh, home_charging_end_h=home_charge_end,
                minimum_energy_kWh=minimum_energy, derivative_utility_per_D_h=slope)


def pattern_solution(pattern, *, D, probability=0.0, family='deterministic', contract='hard', gamma=0.0, joined=True):
    results = []
    for state in scenarios(probability, family):
        r = scenario_path(pattern, state, joined=joined, D=D, contract=contract, gamma=gamma)
        r['probability'] = state['probability']
        results.append(r)
    if not all(r['feasible'] for r in results):
        return dict(feasible=False, pattern=pattern, scenarios=results, disutility=None)
    def mean(key):
        return sum(r['probability'] * r[key] for r in results)
    return dict(feasible=True, pattern=pattern, scenarios=results, disutility=mean('disutility'),
                expected_delivery_kWh=mean('service_kWh'), expected_route_km=mean('route_km'),
                expected_waiting_h=mean('waiting_h'),
                full_service_probability=sum(r['probability'] for r in results if r['service_kWh'] > 0.0),
                derivative_utility_per_D_h=mean('derivative_utility_per_D_h'))


def select_solution(solutions):
    feasible = [s for s in solutions if s['feasible']]
    if not feasible:
        raise ValueError('No feasible pattern.')
    minimum = min(s['disutility'] for s in feasible)
    ties = [p for p in PATTERNS if any(s['pattern'] == p and abs(s['disutility'] - minimum) <= TOL for s in feasible)]
    chosen = next(s for s in feasible if s['pattern'] == ties[0])
    return chosen, ties


def rate_info(compensation, delivery):
    if compensation is None:
        return None, 'infeasible'
    if delivery > TOL:
        return max(0.0, compensation) / delivery, 'defined'
    if abs(compensation) <= TOL:
        return None, 'no_delivery_zero_burden'
    return None, 'no_delivery_positive_burden'


def analytic_comparison(D, probability=0.0, family='deterministic', contract='hard', gamma=0.0,
                        reference_D=4.0, reference_pattern=None):
    """Independent A/B/C, plus forced-reference-B policy sensitivity.

    A uses the exact reference conditional derivative. B fixes the complete
    common planned-location choice; scenario times may adjust. A forced B plan
    need not be an optimal reference for automatic release at p>0.
    """
    if not 1.0 - TOL <= D <= 7.0 + TOL:
        raise ValueError('D must be in [1,7].')
    family = canonical_family(family); contract = canonical_contract(contract)
    args = dict(probability=float(probability), family=family, contract=contract, gamma=float(gamma))
    baseline, baseline_ties = select_solution([pattern_solution(p, D=D, joined=False, **args) for p in PATTERNS])
    C, C_ties = select_solution([pattern_solution(p, D=D, joined=True, **args) for p in PATTERNS])
    ref_opt, ref_ties = select_solution([pattern_solution(p, D=reference_D, joined=True, **args) for p in PATTERNS])
    ref_pattern = ref_opt['pattern'] if reference_pattern is None else reference_pattern
    ref = pattern_solution(ref_pattern, D=reference_D, joined=True, **args)
    if not ref['feasible']:
        raise ValueError('Specified reference pattern is infeasible at reference D.')
    B = pattern_solution(ref_pattern, D=D, joined=True, **args)
    alt_ref = pattern_solution('B', D=reference_D, joined=True, **args)
    alt = pattern_solution('B', D=D, joined=True, **args)
    reference_comp = (ref['disutility'] - baseline['disutility']) / MU
    derivative = ref['derivative_utility_per_D_h'] / MU
    A_comp = reference_comp + derivative * (D-reference_D)
    B_comp = (B['disutility'] - baseline['disutility']) / MU if B['feasible'] else None
    alt_comp = (alt['disutility'] - baseline['disutility']) / MU if alt['feasible'] else None
    C_comp = (C['disutility'] - baseline['disutility']) / MU
    expected_delivery = C['expected_delivery_kWh']
    ans = dict(D_hours=float(D), p=float(probability), scenario=family, contract=contract, gamma=float(gamma),
               A_compensation_CHF=A_comp, B_compensation_CHF=B_comp, B_alt_compensation_CHF=alt_comp,
               C_compensation_CHF=C_comp, B_feasible=B['feasible'], B_alt_feasible=alt['feasible'],
               reference_pattern=ref_pattern, reference_tie_patterns=ref_ties,
               reference_is_optimal=abs(ref['disutility']-ref_opt['disutility']) <= TOL,
               alternative_B_reference_is_optimal=abs(alt_ref['disutility']-ref_opt['disutility']) <= TOL,
               reference_compensation_CHF=reference_comp, reference_multiplier_CHF_per_hour=derivative,
               B_pattern=ref_pattern, B_alt_pattern='B', C_pattern=C['pattern'], C_tie_patterns=C_ties,
               baseline_pattern=baseline['pattern'], baseline_tie_patterns=baseline_ties,
               expected_delivery_kWh=expected_delivery, full_service_probability=C['full_service_probability'],
               baseline_expected_route_km=baseline['expected_route_km'], C_expected_route_km=C['expected_route_km'],
               C_expected_extra_route_km=C['expected_route_km']-baseline['expected_route_km'],
               baseline=baseline, C=C, B=B, B_alt=alt)
    for label, comp in [('A', A_comp), ('B', B_comp), ('B_alt', alt_comp), ('C', C_comp)]:
        rate, status = rate_info(comp, expected_delivery)
        ans[f'{label}_delivery_rate_CHF_per_kWh'] = rate
        ans[f'{label}_rate_status'] = status
    return ans


def free_wait_C(D, probability=0.0, family='deterministic', contract='hard'):
    """Second, concise closed formula used to self-audit the route calculations."""
    p = float(probability); family=canonical_family(family); contract=canonical_contract(contract)
    if family == 'uniform_activity':
        if contract != 'auto_release':
            return 3.30-1.32*p+.12*p*p
        if p == 0.0:
            return 0.0
        plan_B=2.10*p+1.08*p*(1-p)
        if D>A_D_MAX+TOL:
            return plan_B
        plan_A=2.10*p+(BETA/MU)*p*p*max(0.0,D-A_D_SLACK)
        return min(plan_A,plan_B)
    if family != 'education_cancel':
        return 2.10
    if contract != 'auto_release':
        return 2.10 + 1.08*p
    if p == 1.0:
        return 0.0
    plan_B = 2.10*(1-p) + 1.08*p
    if D > A_D_MAX + TOL:
        return plan_B
    plan_A = (1-p)*(2.10+(BETA/MU)*max(0.0,D-A_D_SLACK))
    return min(plan_A, plan_B)



def uniform_strict_closed(D, probability, contract='hard', gamma=0.0):
    """Second closed oracle including strict first departure and all waiting."""
    p=float(probability);contract=canonical_contract(contract)
    effective_D=1.0 if contract=='event_only' else float(D)
    delta=max(0.0,effective_D-A_D_SLACK)
    delta_B=max(0.0,effective_D-B_D_ON_TIME)
    feasible_A=p==0.0 or effective_D<=A_D_MAX+TOL
    if contract!='auto_release':
        h0=3.30-1.32*p+.12*p*p
        w0=A_DEPARTURE_ON_TIME-EDUCATION_END
        base_wait=(1-p)*(effective_D+4.5+p*(w0-9.45))
        A_comp=h0+gamma*base_wait/MU
        plan_A=A_comp+(gamma+BETA)*p*delta/MU
        plan_B=h0+gamma*(base_wait+.45*p+p*delta_B)/MU
        slope=0.0 if contract=='event_only' else gamma*(1-p)/MU
    else:
        A_comp=2.10*p+gamma*p*(1-p)*(effective_D-1./6.)/MU
        plan_A=A_comp+(gamma+BETA)*p*p*delta/MU
        plan_B=(2.10*p+1.08*p*(1-p)
                +gamma*(p*p*(.45+delta_B)+p*(1-p)*(effective_D-1./6.-.45))/MU)
        slope=gamma*p*(1-p)/MU
    C_comp=min(plan_A,plan_B) if feasible_A else plan_B
    return dict(A_compensation_CHF=A_comp,B_compensation_CHF=plan_A if feasible_A else None,
                B_alt_compensation_CHF=plan_B,C_compensation_CHF=C_comp,
                reference_multiplier_CHF_per_hour=slope)

def uniform_release_thresholds(probability):
    """Uniform independent occurrence-p: auto-release threshold and right jump."""
    p=float(probability)
    if not 0.0<=p<=1.0:
        raise ValueError('Probability must be in [0,1].')
    if p==0.0:
        return dict(p=p,service_state_present=False,switch_D_hours=None,at_A_boundary_CHF=0.0,right_limit_CHF=0.0,right_jump_CHF=0.0)
    switch=A_D_SLACK+MU*1.08*(1-p)/(BETA*p)
    A_boundary=2.10*p+.5*(BETA/MU)*p*p
    B_boundary=2.10*p+1.08*p*(1-p)
    at_boundary=min(A_boundary,B_boundary)
    return dict(p=p,service_state_present=True,switch_D_hours=switch if switch<=A_D_MAX+TOL else None,
                A_feasible_through_D_hours=A_D_MAX,at_A_boundary_CHF=at_boundary,right_limit_CHF=B_boundary,
                right_jump_CHF=max(0.,B_boundary-at_boundary),critical_occurrence_probability=1.08/(1.08+.5*BETA/MU))


def release_thresholds(probability, gamma=0.0):
    """Education-cancel release switch, boundary values and genuine right jump."""
    p=float(probability)
    if not 0 <= p <= 1 or not 0 <= gamma < ALPHA:
        raise ValueError('Unsupported p/gamma.')
    if p == 1.0:
        return dict(p=p,gamma=gamma,normal_state_present=False,switch_D_hours=None,
                    at_A_boundary_CHF=0.0,right_limit_CHF=0.0,right_jump_CHF=0.0)
    base=2.10*(1-p)
    switch=A_D_SLACK+(.45*gamma+MU*1.08*p/(1-p))/(gamma+BETA)
    A_boundary=base+(1-p)*(gamma+BETA)/MU*.5
    B_boundary=base+1.08*p+(1-p)*gamma*.45/MU
    at_boundary=min(A_boundary,B_boundary)
    right_limit=B_boundary
    return dict(p=p,gamma=gamma,normal_state_present=True,
                switch_D_hours=switch if switch <= A_D_MAX+TOL else None,
                A_feasible_through_D_hours=A_D_MAX,at_A_boundary_CHF=at_boundary,
                right_limit_CHF=right_limit,right_jump_CHF=max(0.,right_limit-at_boundary),
                critical_probability=(.5*BETA+.05*gamma)/(MU*1.08+.5*BETA+.05*gamma))


def fixed_clock_projection_equivalent(arrival,departure,D):
    """Compare scheduling feasibility, not identity of plug-time trajectories."""
    if not 1 <= D <= 7:
        raise ValueError('D must be in [1,7].')
    pulse_ok=arrival<=12.+TOL and departure>=13.-TOL
    max_counted=max(0.,min(departure,19.)-max(arrival,12.))
    cumulative=pulse_ok and max_counted>=D-TOL
    clock=arrival<=12.+TOL and departure>=12.+D-TOL
    return dict(cumulative_feasible=cumulative,fixed_clock_feasible=clock,equivalent=cumulative==clock)


def self_test():
    checked=0;max_error=0.
    D_values=sorted(set([1.+i/12. for i in range(73)]+[4.05-1/60.,4.05,4.05+1/60.,4.55-1/60.,4.55,4.55+1/60.]))
    for family in ('deterministic','education_cancel','shopping_cancel','uniform_activity'):
        for contract in ('hard','auto_release','event_only'):
            for p in (0.,.25,.5,.75,1.):
                for D in D_values:
                    result=analytic_comparison(D,p,family,contract,0.)
                    error=abs(result['C_compensation_CHF']-free_wait_C(D,p,family,contract))
                    max_error=max(max_error,error)
                    assert error<1e-9,(family,contract,p,D,result['C_compensation_CHF'])
                    if contract=='auto_release' and family=='education_cancel':
                        assert abs(result['expected_delivery_kWh']-7.*(1.-p))<TOL
                    elif contract=='auto_release' and family=='uniform_activity':
                        assert abs(result['expected_delivery_kWh']-7.*p)<TOL
                    else:
                        assert abs(result['expected_delivery_kWh']-7.)<TOL
                    checked+=1
    for p in (.25,.5,.75):
        t=release_thresholds(p)
        at=analytic_comparison(A_D_MAX,p,'education_cancel','auto_release')['C_compensation_CHF']
        right=analytic_comparison(A_D_MAX+1e-6,p,'education_cancel','auto_release')['C_compensation_CHF']
        assert abs(at-t['at_A_boundary_CHF'])<TOL and abs(right-t['right_limit_CHF'])<TOL
    for p in (.25,.5,.75):
        t=uniform_release_thresholds(p)
        at=analytic_comparison(A_D_MAX,p,'uniform_activity','auto_release')['C_compensation_CHF']
        right=analytic_comparison(A_D_MAX+1e-6,p,'uniform_activity','auto_release')['C_compensation_CHF']
        assert abs(at-t['at_A_boundary_CHF'])<TOL and abs(right-t['right_limit_CHF'])<TOL
    assert len(scenarios(.5,'uniform_activity'))==8
    assert len(scenarios(0.,'uniform_activity'))==1 and len(scenarios(1.,'uniform_activity'))==1
    for gamma in (0.,.03915):
        for family in ('deterministic','education_cancel','shopping_cancel','uniform_activity'):
            for contract in ('hard','auto_release','event_only'):
                for p in (0.,.25,.5,.75,1.):
                    for D in (1.,4.,4.05,4.5,4.55,5.,6.5,7.):
                        result=analytic_comparison(D,p,family,contract,gamma)
                        assert result['C_compensation_CHF']>=-TOL
                        assert result['C_expected_extra_route_km']>=-TOL
                        if result['B_feasible']:
                            assert result['B_compensation_CHF']+TOL>=result['C_compensation_CHF']
                        assert result['B_alt_compensation_CHF']+TOL>=result['C_compensation_CHF']
                        checked+=1
    maximum_strict_gamma_error=0.0
    for gamma in (0.,.03915):
        for contract in ('hard','auto_release','event_only'):
            for p in (0.,.25,.5,.75,1.):
                for D in D_values:
                    actual=analytic_comparison(D,p,'uniform_activity',contract,gamma)
                    closed=uniform_strict_closed(D,p,contract,gamma)
                    for key,value in closed.items():
                        if value is None:
                            assert actual[key] is None,(key,actual[key])
                        else:
                            error=abs(actual[key]-value)
                            maximum_strict_gamma_error=max(maximum_strict_gamma_error,error)
                            assert error<1e-9,(gamma,contract,p,D,key,actual[key],value)
                    checked+=1
    strict_states=scenarios(.5,'uniform_activity')
    state_A=next(s for s in strict_states if not s['education'] and s['shopping_A'])
    direct=scenario_path('A',state_A,joined=False,D=4.,contract='hard',gamma=.03915)
    assert abs(direct['waiting_h']-9.45)<TOL and direct['waiting_location']=='Downtown'
    campus=scenario_path('A',state_A,joined=True,D=4.,contract='hard',gamma=.03915)
    assert abs(campus['campus_arrival_h']-7.5)<TOL and abs(campus['waiting_h']-8.55)<TOL
    for state in strict_states:
        if not state['education'] and not state['shopping_A']:
            home=scenario_path('A',state,joined=True,D=4.,contract='auto_release',gamma=.03915)
            assert home['route_km']==0.0 and home['waiting_h']==0.0
    for arrival in (7.5,12.,12.1):
        for departure in (12.5,13.,16.05,18.5,19.,19.5):
            for D in D_values:
                assert fixed_clock_projection_equivalent(arrival,departure,D)['equivalent']
                checked+=1
    return dict(passed=True,checked_analytic_cases=checked,maximum_free_wait_closed_formula_error_CHF=max_error,
                maximum_strict_gamma_closed_formula_error_CHF=maximum_strict_gamma_error,
                probability_075_release_right_jump_CHF=release_thresholds(.75)['right_jump_CHF'],
                uniform_probability_025_release_right_jump_CHF=uniform_release_thresholds(.25)['right_jump_CHF'],
                probability_050_release_switch_D_hours=release_thresholds(.5)['switch_D_hours'],
                pure_analytic=True,solver_calls=0)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--D',type=float,default=4.0)
    parser.add_argument('--p',type=float,default=0.5)
    parser.add_argument('--family',default='education_cancel')
    parser.add_argument('--contract',default='auto_release')
    parser.add_argument('--gamma',type=float,default=0.0)
    args=parser.parse_args()
    result=self_test() if args.self_test else analytic_comparison(args.D,args.p,args.family,args.contract,args.gamma)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':
    main()
