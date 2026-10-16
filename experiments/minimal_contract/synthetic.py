#!/usr/bin/env python3
"""Actual MILP and LP runs for the approved synthetic one-person mechanism toy."""
import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

NAMES=['work_departure_h','connection_h','gym_start_h','gym_late_h','home_arrival_h','gym_participates']
OBJ=np.array([1200.,0.,0.,600.,0.,-3000.])
BIG_M=24.
TOL=1e-6

def dump(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def csv_write(path,rows):
    with path.open('w',newline='') as f:
        out=csv.DictWriter(f,fieldnames=list(rows[0]));out.writeheader();out.writerows(rows)

def build_model(D,join):
    """One binary, gym participation. All overlap/sign expressions are linear here.

    Work ends at/after 17:00, contact starts at 16:00 and lasts at most 3 h;
    an active gym starts at/after 17:15. Thus no auxiliary integer is needed.
    """
    q=10. if join else 4.
    lower=np.array([17.,0.,0.,0.,0.,0.])
    upper=np.array([20.,3. if join else 0.,17.75,24.,24.-q/6.,1.])
    aa,bb,labels=[],[],[]
    def add(name,coeff,rhs):
        aa.append(coeff);bb.append(rhs);labels.append(name)
    if join:
        add('minimum_connection_D',[0.,-1.,0.,0.,0.,0.],-float(D))
        add('mandatory_16_to_17',[0.,-1.,0.,0.,0.,0.],-1.)
        add('contact_before_departure',[-1.,1.,0.,0.,0.,0.],-16.)
    add('gym_earliest',[0.,0.,-1.,0.,0.,17.25],0.)
    add('gym_latest_or_zero_if_absent',[0.,0.,1.,0.,0.,-17.75],0.)
    add('travel_work_to_gym',[1.,0.,-1.,0.,0.,BIG_M],BIG_M-.25)
    add('gym_delay',[0.,0.,1.,-1.,0.,-17.25],0.)
    add('home_after_direct_route',[1.,0.,0.,0.,-1.,0.],-.5)
    add('home_after_gym',[0.,0.,1.,0.,-1.,BIG_M],BIG_M-1.25)
    return dict(A=np.asarray(aa),b=np.asarray(bb),labels=labels,lower=lower,upper=upper,
                q=q,offset=-1200.*17.+30.*q)

def canonical_solution(vector,m):
    """Earliest home arrival selects a utility-equivalent display schedule."""
    v=np.asarray(vector).copy();x=int(round(float(v[5])))
    v[4]=v[2]+1.25 if x else v[0]+.5
    violation=max(float(np.max(m['A']@v-m['b'])),float(np.max(m['lower']-v)),float(np.max(v-m['upper'])))
    assert violation<=TOL,violation
    return v,max(0.,violation)

def solve_milp(D,join):
    m=build_model(D,join);start=time.perf_counter()
    res=milp(OBJ,integrality=np.array([0,0,0,0,0,1]),bounds=Bounds(m['lower'],m['upper']),
             constraints=LinearConstraint(m['A'],-np.inf,m['b']),
             options=dict(time_limit=30.,mip_rel_gap=0.,presolve=True))
    rec=dict(status=int(res.status),message=str(res.message),elapsed_s=time.perf_counter()-start,
             mip_gap=float(res.mip_gap) if getattr(res,'mip_gap',None) is not None else None,
             mip_node_count=int(res.mip_node_count) if getattr(res,'mip_node_count',None) is not None else None)
    if res.status==0:
        canon,violation=canonical_solution(res.x,m)
        rec.update(cost=float(res.fun+m['offset']),objective_without_constant=float(res.fun),
                   raw_vector=dict(zip(NAMES,map(float,res.x))),canonical_vector=dict(zip(NAMES,map(float,canon))),
                   max_canonical_constraint_violation=violation)
    return rec

def solve_fixed_lp(D,fixed_integer):
    m=build_model(D,True);bounds=list(zip(m['lower'],m['upper']));bounds[5]=(float(fixed_integer),float(fixed_integer))
    start=time.perf_counter()
    res=linprog(OBJ,A_ub=m['A'],b_ub=m['b'],bounds=bounds,method='highs',options=dict(time_limit=30.,presolve=True))
    rec=dict(status=int(res.status),message=str(res.message),elapsed_s=time.perf_counter()-start)
    if res.status==0:
        canon,violation=canonical_solution(res.x,m);idx=m['labels'].index('minimum_connection_D')
        rec.update(cost=float(res.fun+m['offset']),raw_vector=dict(zip(NAMES,map(float,res.x))),
                   canonical_vector=dict(zip(NAMES,map(float,canon))),marginal_rhs_negative_D=float(res.ineqlin.marginals[idx]),
                   derivative_cost_wrt_D=float(-res.ineqlin.marginals[idx]),max_canonical_constraint_violation=violation)
    return rec

def independent_pattern_lp(D,join,gym):
    """Separate route formulation: no M, binary, connection or delay variable."""
    q=10. if join else 4.;t_min=max(17.,16.+D) if join else 17.
    if gym:
        res=linprog([1200.,600.],A_ub=[[1.,-1.],[0.,1.]],b_ub=[-.25,24.-q/6.-1.25],
                    bounds=[(t_min,20.),(17.25,17.75)],method='highs')
        offset=-1200.*17.-600.*17.25-3000.+30.*q
    else:
        res=linprog([1200.],A_ub=[[1.]],b_ub=[24.-q/6.-.5],bounds=[(t_min,20.)],method='highs')
        offset=-1200.*17.+30.*q
    return dict(gym=bool(gym),status=int(res.status),message=str(res.message),
                cost=float(res.fun+offset) if res.status==0 else None,
                vector=list(map(float,res.x)) if res.status==0 else None)

def hand_A(D):return 180.+1800.*(D-1.)
def hand_C(D):return hand_A(D) if D<=1.5+1e-12 else 3180.+1200.*(D-1.)
def clock(h):
    minute=int(round(h*60));return f'{minute//60:02d}:{minute%60:02d}'

def schedule_row(label,record,join,D=None):
    v=record['canonical_vector'];gym=int(round(v['gym_participates']))
    return dict(case=label,D_h=D,join=bool(join),gym=gym,work_start='09:00',work_end=clock(v['work_departure_h']),
                gym_start=clock(v['gym_start_h']) if gym else None,gym_end=clock(v['gym_start_h']+1.) if gym else None,
                home_arrival=clock(v['home_arrival_h']),home_charge_end=clock(v['home_arrival_h']+(10. if join else 4.)/6.),
                cost=record['cost'],canonical_vector=v)


def validate_energy(case,record,join,config,D=None):
    """Reconstruct and assert route SOC using configured inputs and solver timing.

    The toy eliminated SOC analytically. This audit therefore also checks that
    the independently computed home charge equals the quantity used in the
    optimization time constraint. Bounds hold between these events because
    travel/dispatch deplete and home charging replenishes monotonically.
    """
    assert record['status']==0, (case,record['status'])
    v=record['canonical_vector'];gym=bool(round(v['gym_participates']))
    battery=config['battery'];travel=config['travel'];contract=config['contract'];charging=config['charging']
    eta=battery['efficiency'];initial=battery['initial_kWh'];target=battery['end_kWh']
    states=[dict(stage='home_departure',time_h=config['work']['start_h']-travel['home_work']['hours'],energy_kWh=initial)]
    energy=initial-travel['home_work']['kWh']
    states.append(dict(stage='work_arrival',time_h=config['work']['start_h'],energy_kWh=energy))
    route_energy=travel['home_work']['kWh']
    violations=[config['work']['start_h']+config['work']['min_duration_h']-v['work_departure_h']]
    dispatch_energy=0.
    if join:
        dispatch_start,dispatch_end=contract['fixed_dispatch_interval_h']
        dispatch_energy=contract['fixed_dispatch_kW']*(dispatch_end-dispatch_start)/eta
        energy-=dispatch_energy
        states.append(dict(stage='after_dispatch',time_h=dispatch_end,energy_kWh=energy))
        window_start,window_end=contract['counting_window_h']
        connection_start=contract['mandatory_interval_h'][0]
        connection_end=connection_start+v['connection_h']
        violations.extend([config['work']['start_h']-dispatch_start,dispatch_end-v['work_departure_h'],
                           connection_start-dispatch_start,dispatch_end-connection_end,
                           window_start-connection_start,connection_end-window_end,
                           connection_end-v['work_departure_h'],D-v['connection_h']])
    if gym:
        energy-=travel['work_gym']['kWh'];route_energy+=travel['work_gym']['kWh']
        gym_arrival=v['work_departure_h']+travel['work_gym']['hours']
        states.append(dict(stage='gym_arrival',time_h=gym_arrival,energy_kWh=energy))
        gym_end=v['gym_start_h']+config['gym']['duration_h']
        violations.extend([gym_arrival-v['gym_start_h'],config['gym']['earliest_start_h']-v['gym_start_h'],
                           gym_end-config['gym']['latest_end_h'],gym_end+travel['gym_home']['hours']-v['home_arrival_h']])
        energy-=travel['gym_home']['kWh'];route_energy+=travel['gym_home']['kWh']
    else:
        # The direct work-home arc is the reverse of the configured home-work arc.
        energy-=travel['home_work']['kWh'];route_energy+=travel['home_work']['kWh']
        violations.append(v['work_departure_h']+travel['home_work']['hours']-v['home_arrival_h'])
    states.append(dict(stage='home_arrival',time_h=v['home_arrival_h'],energy_kWh=energy))
    charge_grid_kWh=(target-energy)/eta
    charge_end=v['home_arrival_h']+charge_grid_kWh/charging['home_kW']
    violations.append(charge_end-charging['latest_finish_h'])
    end_energy=energy+charge_grid_kWh*eta
    states.append(dict(stage='home_charge_complete',time_h=charge_end,energy_kWh=end_energy))
    model_charge=build_model(D if D is not None else 1.,join)['q']
    residuals=dict(total_energy_balance_kWh=abs(initial-route_energy-dispatch_energy+charge_grid_kWh*eta-target),
                   final_energy_kWh=abs(end_energy-target),computed_vs_optimization_charge_kWh=abs(charge_grid_kWh-model_charge))
    min_energy=min(e['energy_kWh'] for e in states);max_energy=max(e['energy_kWh'] for e in states)
    bound_violation=max(0.,battery['minimum_kWh']-min_energy,max_energy-battery['capacity_kWh'])
    max_time_violation=max(0.,*violations)
    checks=dict(nonnegative_home_charge=charge_grid_kWh>=-TOL,
                energy_balance=max(residuals.values())<=TOL,SOC_bounds=bound_violation<=TOL,
                schedule_and_charge_completion=max_time_violation<=TOL)
    result=dict(case=case,join=bool(join),gym=gym,route_energy_kWh=route_energy,
                battery_dispatch_kWh=dispatch_energy,computed_home_grid_charge_kWh=charge_grid_kWh,
                optimization_home_grid_charge_kWh=model_charge,charge_end_h=charge_end,
                minimum_energy_kWh=min_energy,maximum_energy_kWh=max_energy,
                maximum_SOC_bound_violation_kWh=bound_violation,maximum_time_violation_h=max_time_violation,
                residuals=residuals,checks=checks,passed=all(checks.values()),states=states)
    assert result['passed'],result
    return result


def energy_audit(baseline,reference,reference_lp,finite_left,finite_right,raw,config):
    records=[validate_energy('baseline_nonjoin',baseline,False,config),
             validate_energy('reference_C',reference,True,config,1.25),
             validate_energy('reference_B',reference_lp,True,config,1.25),
             validate_energy('finite_difference_left_B',finite_left,True,config,74/60.),
             validate_energy('finite_difference_right_B',finite_right,True,config,76/60.)]
    for row in raw:
        records.append(validate_energy(f"sweep_C_D={row['D_h']:.12g}",row['C'],True,config,row['D_h']))
        if row['B']['status']==0:
            records.append(validate_energy(f"sweep_B_D={row['D_h']:.12g}",row['B'],True,config,row['D_h']))
    summary=dict(passed=all(r['passed'] for r in records),checked_solution_count=len(records),
                 maximum_energy_residual_kWh=max(max(r['residuals'].values()) for r in records),
                 maximum_SOC_bound_violation_kWh=max(r['maximum_SOC_bound_violation_kWh'] for r in records),
                 maximum_time_violation_h=max(r['maximum_time_violation_h'] for r in records),
                 minimum_energy_across_paths_kWh=min(r['minimum_energy_kWh'] for r in records),
                 latest_home_charge_end_h=max(r['charge_end_h'] for r in records))
    assert summary['passed'],summary
    return dict(summary=summary,paths=records,
                formulation='Route energies, dispatch and home charge reconstructed from config and actual canonical solver schedules; energy was analytically eliminated from this fixed-dispatch toy.',
                monotonic_between_events='Travel and dispatch deplete SOC; home charging replenishes SOC. Endpoint bounds therefore imply bounds throughout each segment.')

def make_figures(out,rows,schedules):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'savefig.dpi':180,'pdf.fonttype':42})
    xx=np.array([r['D_h'] for r in rows]);aa=np.array([r['A_compensation'] for r in rows]);cc=np.array([r['C_compensation'] for r in rows]);active=xx<=1.5+1e-12
    fig,ax=plt.subplots(figsize=(9.4,5.3))
    ax.axvspan(1.5,3.,facecolor='#e7ebee',alpha=.65,hatch='///',edgecolor='#d4dadd',label='B: infeasible')
    ax.plot(xx,aa,color='#cd5541',ls='--',lw=2.,label='A: reference LP multiplier extrapolation')
    ax.plot(xx[active],cc[active],color='#1769a1',lw=2.5,label='C: full MILP')
    ax.plot(xx[~active],cc[~active],color='#1769a1',lw=2.5)
    ax.plot(xx[active],[r['B_compensation'] for r in rows if r['D_h']<=1.5+1e-12],marker='o',ms=3.9,
            markerfacecolor='white',color='#d58a16',ls='none',label='B: all integers fixed, LP')
    ax.plot([1.5,1.5],[1080.,3780.],color='#1769a1',lw=1.,ls=':')
    ax.plot(1.5,3780.,'o',mfc='white',mec='#1769a1',ms=6);ax.plot(1.5,1080.,'o',mfc='#1769a1',mec='#1769a1',ms=5)
    ax.annotate('Gym becomes infeasible\nright-limit increase: 2,700',xy=(1.5,2450),xytext=(1.72,2000),
                arrowprops={'arrowstyle':'-','color':'#56636e'},fontsize=9,bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':3})
    ax.scatter([1.25],[630.],color='#333333',s=23,zorder=8)
    ax.annotate('Reference: D = 1.25 h',(1.25,630.),(1.07,1300.),fontsize=9,arrowprops={'arrowstyle':'-','color':'#56636e'})
    ax.set(xlim=(.98,3.02),ylim=(0,6000),xlabel='Required workplace connection D (hours)',
           ylabel='Required compensation (money-equivalent units)',title='Synthetic mechanism example: finite contract burden and a local price')
    ax.grid(axis='y',color='#d8dfe3',lw=.6);ax.legend(loc='upper left',frameon=False,fontsize=8.4);fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/f'compensation_ABC.{ext}')
    plt.close(fig)
    colors=dict(work='#8da6b4',gym='#e7a657',home='#e2e7e9',travel='#677580',connection='#5b4396',dispatch='#b53b42',charge='#5e9272')
    fig,ax=plt.subplots(figsize=(11.6,6.2))
    for i,row in enumerate(schedules):
        y=len(schedules)-1-i
        if row.get('infeasible',False):
            ax.text(16.,y,'Infeasible: gym cannot finish before 18:45',color='#9d4338',va='center',fontsize=9)
            continue
        v=row['canonical_vector'];t=v['work_departure_h'];h=v['home_arrival_h'];x=row['gym']
        ax.broken_barh([(8.,.5),(h,24.-h)],(y-.21,.43),facecolors=colors['home'])
        ax.broken_barh([(8.5,.5)],(y-.21,.43),facecolors=colors['travel'])
        ax.broken_barh([(9.,t-9.)],(y-.21,.43),facecolors=colors['work'])
        if x:
            g=v['gym_start_h'];ax.broken_barh([(t,.25),(g+1.,.25)],(y-.21,.43),facecolors=colors['travel'])
            ax.broken_barh([(g,1.)],(y-.21,.43),facecolors=colors['gym'])
            ax.text(g+.5,y,f'{clock(g)}–{clock(g+1.)}',ha='center',va='center',fontsize=7.4)
        else:ax.broken_barh([(t,.5)],(y-.21,.43),facecolors=colors['travel'])
        q=10. if row['join'] else 4.;ax.broken_barh([(h,q/6.)],(y-.21,.12),facecolors=colors['charge'])
        if row['join']:
            ax.broken_barh([(16.,v['connection_h'])],(y-.42,.12),facecolors=colors['connection'])
            ax.broken_barh([(16.,1.)],(y+.25,.08),facecolors=colors['dispatch'])
        ax.text(t,y+.26,clock(t),fontsize=7.2,color='#364552',va='bottom',ha='center')
        ax.text(h+.06,y+.02,f'Home {clock(h)}',fontsize=7.4,va='center')
    for at in (17.5,18.75):ax.axvline(at,color='#aa6e23',lw=.8,ls=':')
    ax.set_yticks(range(len(schedules)),[r['case'] for r in schedules][::-1])
    ax.set_xticks(np.arange(8,25),[f'{h:02d}:00' for h in range(8,25)])
    ax.set(xlim=(8,24),ylim=(-.7,len(schedules)-.3),xlabel='Time of day',
           title='Optimal schedules: gym visit disappears after the 17:30 departure boundary')
    ax.tick_params(axis='x',labelsize=8);ax.grid(axis='x',color='#dce2e5',lw=.6)
    ax.legend(handles=[Patch(facecolor=colors[k],label=label) for k,label in [('work','Work'),('gym','Gym'),('travel','Travel'),
              ('home','Home'),('connection','Connection'),('dispatch','6 kW dispatch'),('charge','Home charging')]],
              loc='upper center',bbox_to_anchor=(.5,-.13),ncol=7,frameon=False,fontsize=8)
    fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/f'activity_schedules.{ext}',bbox_inches='tight')
    plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output','--output-dir',dest='output_dir',type=Path,required=True);args=p.parse_args();out=args.output_dir.resolve()
    if out.exists():raise SystemExit(f'Refusing to overwrite prior run directory: {out}')
    out.mkdir(parents=True,exist_ok=True);source=Path(__file__).resolve()
    (out/'source_snapshot.py').write_bytes(source.read_bytes())
    try:
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source.parent,text=True).strip()
        git_status=subprocess.check_output(['git','status','--short'],cwd=source.parent,text=True)
    except (OSError,subprocess.CalledProcessError):revision,git_status=None,None
    minutes=sorted(set(range(60,181,5))|{74,76,89,91})
    config=dict(case_id=out.name,provenance='Authored synthetic mechanism example; not a person or observed Swiss survey schedule.',
                money='Illustrative money-equivalent units; no empirical calibration.',activity_cancellation=False,preference_noise=False,
                replications=1,seed=None,D_minutes=minutes,reference_D_h=1.25,time='continuous decimal hours',
                work=dict(start_h=9.,min_duration_h=8.,end_latest_h=20.,overtime_cost_per_h=1200.),
                gym=dict(optional=True,duration_h=1.,earliest_start_h=17.25,latest_end_h=18.75,preferred_start_h=17.25,participation_utility=3000.,late_cost_per_h=600.),
                travel=dict(home_work=dict(hours=.5,kWh=2.),work_gym=dict(hours=.25,kWh=1.),gym_home=dict(hours=.25,kWh=1.)),
                battery=dict(capacity_kWh=60.,initial_kWh=36.,minimum_kWh=12.,end_kWh=36.,efficiency=1.),
                contract=dict(mandatory_interval_h=[16.,17.],counting_window_h=[16.,19.],fixed_dispatch_kW=6.,fixed_dispatch_interval_h=[16.,17.],full_fulfillment=True,fixed_payment=0.,post_17_dispatch_kW=0.),
                charging=dict(home_kW=6.,price_per_kWh=30.,latest_finish_h=24.),
                C='MILP: gym participation and continuous schedule jointly optimized',
                B='LP: complete integer vector fixed to reference C at D=1.25; sole integer is gym participation',
                A='Reference B compensation plus actual reference B cost multiplier times change in D',
                independent_reference='Separate gym/no-gym route LPs; no big-M formulation',auxiliary_integer_variables=[],big_M=BIG_M,
                solver=dict(library='scipy.optimize',MILP='milp / HiGHS',LP='linprog / HiGHS',time_limit_s=30.,MILP_relative_gap=0.,presolve=True,thread_setting='solver default'),
                tolerance=TOL,git_revision=revision,git_status_at_run=git_status,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                home_timing_tie_break='Earliest feasible arrival and charging displayed among utility-equivalent schedules')
    dump(out/'config.json',config)
    dump(out/'environment.json',dict(python=sys.version,executable=sys.executable,numpy=np.__version__,scipy=scipy.__version__,matplotlib=matplotlib.__version__,platform=platform.platform(),machine=platform.machine(),processor=platform.processor()))
    baseline=solve_milp(1.,False);reference=solve_milp(1.25,True);assert baseline['status']==reference['status']==0
    fixed_integer=int(round(reference['canonical_vector']['gym_participates']));reference_lp=solve_fixed_lp(1.25,fixed_integer);assert reference_lp['status']==0
    alpha=reference_lp['derivative_cost_wrt_D'];reference_comp=reference_lp['cost']-baseline['cost'];rows,raw,enums_all,violations=[],[],[],[]
    for minute in minutes:
        D=minute/60.;C=solve_milp(D,True);B=solve_fixed_lp(D,fixed_integer)
        enums=[independent_pattern_lp(D,True,gym) for gym in (False,True)]
        enum_cost=min(e['cost'] for e in enums if e['status']==0)
        checks=dict(C_milp_optimal=C['status']==0,C_matches_independent_enumeration=abs(C['cost']-enum_cost)<=TOL,
                    C_matches_hand=abs(C['cost']-baseline['cost']-hand_C(D))<=TOL,
                    B_feasibility_matches_hand=(B['status']==0)==(D<=1.5+1e-12),B_valid_status=B['status'] in (0,2))
        if B['status']==0:checks['B_matches_hand']=abs(B['cost']-baseline['cost']-hand_A(D))<=TOL
        A=reference_comp+alpha*(D-1.25);checks['A_matches_hand']=abs(A-hand_A(D))<=TOL
        violations.extend([dict(D_h=D,check=k) for k,v in checks.items() if not v])
        rows.append(dict(D_minutes=minute,D_h=D,A_compensation=A,B_status=B['status'],B_compensation=B['cost']-baseline['cost'] if B['status']==0 else None,
                         C_status=C['status'],C_compensation=C['cost']-baseline['cost'],hand_A=hand_A(D),hand_C=hand_C(D),independent_enum_compensation=enum_cost-baseline['cost'],
                         gym_C=int(round(C['canonical_vector']['gym_participates'])),work_departure_C_h=C['canonical_vector']['work_departure_h'],
                         home_arrival_C_h=C['canonical_vector']['home_arrival_h'],A_underestimation=C['cost']-baseline['cost']-A,C_mip_gap=C['mip_gap'],all_checks_pass=all(checks.values())))
        raw.append(dict(D_h=D,C=C,B=B,checks=checks));enums_all.append(dict(D_h=D,patterns=enums))
    nonjoin_enum=[independent_pattern_lp(1.,False,gym) for gym in (False,True)]
    assert abs(baseline['cost']-min(e['cost'] for e in nonjoin_enum if e['status']==0))<=TOL
    assert abs(alpha-1800.)<=TOL
    key=[r for r in rows if r['D_minutes'] in (60,75,90,105,120)]
    for row,target in zip(key,[180.,630.,1080.,4080.,4380.]):assert abs(row['C_compensation']-target)<=TOL
    finite_left=solve_fixed_lp(74/60.,fixed_integer);finite_right=solve_fixed_lp(76/60.,fixed_integer)
    soc=energy_audit(baseline,reference,reference_lp,finite_left,finite_right,raw,config)
    dump(out/'soc_checks.json',soc)
    checks_report=dict(passed=(not violations and soc['summary']['passed']),soc_validation=soc['summary'],tolerance=TOL,instances=len(rows),all_milp_optimal=all(r['C_status']==0 for r in rows),
                       all_C_mip_gaps_zero=all(abs(r['C_mip_gap'])<=TOL for r in rows),
                       maximum_absolute_C_vs_hand_error=max(abs(r['C_compensation']-r['hand_C']) for r in rows),
                       maximum_absolute_C_vs_independent_LP_error=max(abs(r['C_compensation']-r['independent_enum_compensation']) for r in rows),
                       maximum_absolute_feasible_B_vs_hand_error=max(abs(r['B_compensation']-r['hand_A']) for r in rows if r['B_compensation'] is not None),
                       nonjoin_cost=baseline['cost'],nonjoin_utility=-baseline['cost'],reference_compensation=reference_comp,reference_multiplier_per_h=alpha,
                       reference_finite_difference=dict(left_per_h=(reference_lp['cost']-finite_left['cost'])*60.,
                                                        right_per_h=(finite_right['cost']-reference_lp['cost'])*60.),
                       discontinuity=dict(D_h=1.5,value_at_boundary=1080.,right_limit=3780.,right_limit_jump=2700.,right_limit_is_analytical_not_sampled=True),violations=violations,key_table=key)
    dump(out/'independent_checks.json',checks_report);dump(out/'raw_solver_results.json',dict(baseline_nonjoin=baseline,reference_C=reference,reference_fixed_LP=reference_lp,finite_difference_left_LP=finite_left,finite_difference_right_LP=finite_right,all_sweep_results=raw))
    dump(out/'independent_pattern_LPs.json',dict(nonjoin=nonjoin_enum,joined=enums_all));csv_write(out/'compensation_sweep.csv',rows);dump(out/'compensation_sweep.json',rows);csv_write(out/'hand_comparison.csv',key)
    lookup={int(round(r['D_h']*60)):r['C'] for r in raw};schedules=[schedule_row('No contract',baseline,False)]
    for minute in (75,90,91,105,120):
        if minute==91:
            schedules.append(dict(case='B, D = 1 h 31 min',D_h=minute/60.,join=True,gym=None,work_start=None,work_end=None,gym_start=None,gym_end=None,home_arrival=None,home_charge_end=None,cost=None,canonical_vector=None,infeasible=True))
        label=('B = C' if minute<=90 else 'C')+f', D = {minute//60} h {minute%60:02d} min'
        schedules.append(schedule_row(label,lookup[minute],True,minute/60.))
    dump(out/'activity_schedules.json',schedules);csv_write(out/'activity_schedules.csv',[{k:r.get(k) for k in ('case','D_h','join','gym','work_start','work_end','gym_start','gym_end','home_arrival','home_charge_end','cost','infeasible')} for r in schedules])
    make_figures(out,rows,schedules)
    command=f'{sys.executable} {source} --output {out}'
    overview=f'''# Synthetic minimal contract experiment {out.name}

This run checks whether a local fixed-integer LP multiplier captures finite contract burden when an optional fixed-duration activity loses feasibility. It is an authored deterministic one-person mechanism example, not a profile or parameter estimate from a Swiss dataset.

## Configuration and comparison

Time is continuous. Work: 09:00 start, at least eight hours, end no later than 20:00, overtime 1,200 money-equivalent units/h. Gym: optional one hour, earliest start 17:15, latest end 18:45, participation benefit 3,000, delay 600/h. H–W: 30 min and 2 kWh; W–G and G–H: each 15 min and 1 kWh. Both routes consume 4 kWh. Battery: 60 kWh capacity, 36 kWh initial/final, 12 kWh minimum. Joining: fixed 6 kW dispatch during 16:00–17:00, complete fulfillment, at least D hours of connection in 16:00–19:00. Home charging: 6 kW, 30 units/kWh. All other utilities/costs are zero.

D is swept every five minutes from one to three hours, plus one-minute neighbors of the reference and boundary ({len(rows)} instances). C is an actual one-binary MILP. B fixes the complete integer vector to C at D=1.25 h. No auxiliary integer regimes are needed. A uses the actual reference B multiplier, {alpha:g} units/h. Separate route-enumeration LPs and hand formulas independently audit the results. Primary solves use a 30 s limit; MILPs require zero relative gap. There is no random input or statistical replication.

SOC is analytically eliminated because route energy and dispatch are fixed. Executed checks reconstruct route energy, home charge and SOC from configuration and the canonical solver schedules for {soc['summary']['checked_solution_count']} solutions, covering baseline, reference, every swept C and feasible B, and both finite-difference LPs. `soc_checks.json` records each computed state, all energy balances, capacity/lower-bound checks and home charging completion; `independent_checks.json` includes the resulting gate. This elimination is equivalent for this toy, not a solver implementation of the full manuscript SOC model. Home timing has zero utility; figures select earliest home arrival and charging among tied optima.

## Saved evidence

- `config.json`: settings, source hash, revision and working status.
- `source_snapshot.py`: exact executed source, automatically preserved for this run.
- `raw_solver_results.json`: actual MILP/LP results and variable vectors.
- `independent_pattern_LPs.json`: separately formulated route LPs.
- `compensation_sweep.csv`, `hand_comparison.csv`, `independent_checks.json`: comparisons.
- `activity_schedules.csv/.json`, `soc_checks.json`: schedules and energy checks.
- `compensation_ABC.png/.pdf`, `activity_schedules.png/.pdf`: figures.
- `environment.json`: runtime and platform.

Entry point: `experiments/minimal_contract/synthetic.py`. Command:

```text
{command}
```

The entry point refuses to overwrite an existing run directory; reruns require a fresh directory. Revision at run: `{revision}`. Full manuscript experiments, empirical calibration, scalability and external validity are outside this toy's scope.
'''
    (out/'overview.md').write_text(overview)
    discussion=f'''# Observed results and interpretation

All {len(rows)} MILPs were certified optimal with zero reported MIP gap. Every feasible B LP and every C solution matched hand formulas within {TOL:g}. Maximum C discrepancy against separate route LPs: {checks_report['maximum_absolute_C_vs_independent_LP_error']:.3g}. Nonjoining utility: 2,880. Reference compensation: 630. Actual LP multiplier: 1,800 units/h, confirmed by one-minute differences on both sides.

For 1 ≤ D ≤ 1.5, A = B = C = 180 + 1,800(D − 1). At D=1.5 gym is 17:45–18:45 and remains feasible. For D>1.5 the fixed-activity B LP is infeasible and C drops the gym: C = 3,180 + 1,200(D − 1). A remains an extrapolation of the reference LP multiplier; it is not a full-MILP shadow price or an objective value of infeasible B.

C equals 1,080 at D=1.5 and has right limit 3,780, an upward jump of 2,700 (not 3,000): the disappearing gym benefit is already reduced by 300 of delay burden. The right-limit point is analytical, not a sampled solver observation. At D=1.75, A=1,530 while C=4,080: underestimation 2,550. A fixed 2,000 reward would be accepted under A's criterion but rejected under C. At D=2, A=1,980 and C=4,380.

The five hand checks 180, 630, 1,080, 4,080 and 4,380 at D=1, 1.25, 1.5, 1.75 and 2 all agree with actual solver outputs. Route energy is unchanged; dispatch adds 6 kWh and hence 180 home charging cost. Executed SOC checks cover {soc['summary']['checked_solution_count']} solver schedules and derive every state and home charge from the configuration and route. The maximum energy residual is {soc['summary']['maximum_energy_residual_kWh']:.3g} kWh, maximum bound violation {soc['summary']['maximum_SOC_bound_violation_kWh']:.3g} kWh, and maximum timing violation {soc['summary']['maximum_time_violation_h']:.3g} h. Every path stays above 12 kWh and returns to 36 kWh by day end; latest charge completion is {clock(soc['summary']['latest_home_charge_end_h'])}.

This run validates this toy and illustrates activity infeasibility. It does not demonstrate continuous-regime approximation error: A and B agree wherever B is feasible. The jump follows from a hard closing time and fixed activity duration; it is not a universal property. SOC scarcity, uncertainty, battery degradation, endogenous dispatch, empirical preferences and population behavior are untested. A literature-based named profile must distinguish source schedule fields from experimentally assumed windows, battery values, preferences and contract settings.
'''
    (out/'discussion.md').write_text(discussion)
    if violations:raise SystemExit(f'Independent checks failed: {violations}')
    print(json.dumps(dict(output_dir=str(out),checks_pass=True,instances=len(rows),reference_multiplier=alpha,
                         max_hand_error=checks_report['maximum_absolute_C_vs_hand_error'],soc_validation=soc['summary'],key_C_compensation=[r['C_compensation'] for r in key]),indent=2))

if __name__=='__main__':main()
