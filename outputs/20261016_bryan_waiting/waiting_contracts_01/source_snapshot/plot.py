#!/usr/bin/env python3
"""Static export figures from saved Bryan waiting experiment results."""
from __future__ import annotations
import argparse
import csv
import json
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/activity-v2g-waiting-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np

COLORS = {'A':'#c38a20', 'B':'#bb4d4f', 'C':'#137f78', 'alt':'#5975a0'}
ACTIVITY = {'Home':'#e8e8e8', 'Travel':'#8293a0', 'Education':'#d7ad65', 'Waiting':'#f1dba7', 'Campus waiting':'#f1dba7', 'Shopping A':'#9e8cc1', 'Shopping B':'#55aaa0'}

def number(v):
    if v is None or v == '': return None
    try: return float(v)
    except (TypeError, ValueError): return v

def read_rows(path):
    with path.open(newline='') as f: return [{k:number(v) for k,v in r.items()} for r in csv.DictReader(f)]

def select(rows, **kwargs):
    def match(r):
        for k,v in kwargs.items():
            if isinstance(v,(int,float)):
                if r.get(k) is None or abs(r[k]-v)>1e-8: return False
            elif r.get(k)!=v: return False
        return True
    return sorted([r for r in rows if match(r)], key=lambda r:r.get('D_hours',0) or 0)

def save(fig, out, stem):
    fig.savefig(out/(stem+'.png'), dpi=180, bbox_inches='tight')
    fig.savefig(out/(stem+'.pdf'), bbox_inches='tight')
    plt.close(fig)

def curves(ax, rows, title, alt=False, jump=False):
    x=np.array([r['D_hours'] for r in rows])
    for method,label in [('B','B: fixed reference plan'),('C','C: common-plan MILP'),('A','A: local extrapolation')]:
        y=np.array([np.nan if r.get(method+'_compensation_CHF') is None else r[method+'_compensation_CHF'] for r in rows])
        if jump and method=='C':
            leftmask=x<=4.55+1e-8; rightmask=x>4.55+1e-8
            ax.plot(x[leftmask],y[leftmask],color=COLORS[method],lw=2.2,label=label,zorder=3)
            ax.plot(x[rightmask],y[rightmask],color=COLORS[method],lw=2.2,zorder=3)
        else:
            ax.plot(x,y, color=COLORS[method], ls='--' if method=='A' else '-', lw=2.2 if method=='C' else 1.6, label=label,zorder=4 if method=='A' else 3)
    if alt:
        y=[np.nan if r.get('B_alt_compensation_CHF') is None else r['B_alt_compensation_CHF'] for r in rows]
        ax.plot(x,y,color=COLORS['alt'],ls=':',lw=2.3,label='B with tied Campus reference',zorder=5)
    if jump:
        p=rows[0]['p']; left=p*2.1+3.31*p*p*.5; right=p*2.1+1.08*p*(1-p)
        ax.plot([4.55],[left],'o',color=COLORS['C'],ms=5,zorder=7)
        ax.plot([4.55],[right],'o',mfc='white',mec=COLORS['C'],ms=6,zorder=7)
        ax.annotate(f'Right-limit jump: {right-left:.5f} CHF',xy=(4.55,(left+right)/2),xytext=(.06,.78),textcoords='axes fraction',fontsize=8,arrowprops={'arrowstyle':'->','color':'#444444'})
    ax.axvline(4.55,color='#999999',ls=':',lw=.8)
    ax.text(.99,.96,'Fixed-A B infeasible for D > 4.55 h',transform=ax.transAxes,ha='right',va='top',fontsize=7,color=COLORS['B'])
    ax.set(title=title,xlim=(1,7),xlabel='Required connection D (hours)',ylabel='Required expected payment (CHF)')
    ax.grid(alpha=.18)

def plot_comparison(rows,out):
    fig,axs=plt.subplots(2,2,figsize=(12,7.6),layout='constrained')
    cases=[(dict(gamma=0,scenario='uniform_activity',p=1,contract='hard'),'Normal day: free waiting',True,False),
           (dict(gamma=.03915,scenario='uniform_activity',p=1,contract='hard'),'Normal day: assumed waiting cost 0.1305 CHF/h',False,False),
           (dict(gamma=0,scenario='uniform_activity',p=.5,contract='hard'),'Uniform activity realization p=0.5: hard fulfillment',True,False),
           (dict(gamma=0,scenario='uniform_activity',p=.25,contract='auto_release'),'Uniform activity realization p=0.25: automatic release',False,True)]
    for ax,(case,title,alt,jump) in zip(axs.flat,cases): curves(ax,select(rows,**case),title,alt,jump)
    handles,labels=axs[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='outside lower center',ncol=2,frameon=False,fontsize=9)
    fig.suptitle('Bryan: free waiting removes the normal-day A–C gap',fontsize=15)
    save(fig,out,'compensation_ABC')

def plot_contracts(rows,out):
    fig,axs=plt.subplots(1,3,figsize=(13,4.5),layout='constrained')
    for contract,label,color,marker in [('hard','Hard fulfillment','#137f78','o'),('auto_release','Automatic release','#a060a4','s')]:
        r=select(rows,gamma=0,scenario='uniform_activity',contract=contract,D_hours=5)
        r.sort(key=lambda z:z['p'])
        x=[z['p'] for z in r]
        axs[0].plot(x,[z['C_compensation_CHF'] for z in r],marker=marker,color=color,label=label)
        axs[1].plot(x,[z['expected_delivery_kWh'] for z in r],marker=marker,color=color)
        axs[2].plot(x,[np.nan if z.get('C_delivery_rate_CHF_per_kWh') is None else z['C_delivery_rate_CHF_per_kWh'] for z in r],marker=marker,color=color)
    axs[2].annotate('p=0: release supplies no energy;\nunit rate is undefined',xy=(.03,.44),xytext=(.12,.455),fontsize=8)
    for ax,title,ylabel in zip(axs,['Break-even expected payment','Expected delivered energy','Minimum delivered-energy rate'],['CHF','kWh','CHF/kWh']):
        ax.set(title=title,xlabel='Common activity realization probability p',ylabel=ylabel,xticks=[0,.25,.5,.75,1],xlim=(-.03,1.03)); ax.grid(alpha=.18)
    fig.legend(*axs[0].get_legend_handles_labels(),loc='outside lower center',ncol=2,frameon=False)
    fig.suptitle('Contract comparison at D=5 h, free waiting\nFixed grants and delivery payments have equal break-even expected payment under risk neutrality',fontsize=12)
    save(fig,out,'contracts_uncertainty')

def choose(records,method,scenario='uniform_activity',p=.5,contract='hard',D=4.5):
    found=[]
    for r in records:
        if r.get('method')!=method or abs(float(r.get('gamma',-1)))>1e-8 or r.get('scenario')!=scenario or abs(float(r.get('p',-1))-p)>1e-8: continue
        if method!='nonjoin' and (r.get('contract')!=contract or r.get('D_hours') is None or abs(r['D_hours']-D)>1e-8): continue
        found.append(r)
    if not found: raise ValueError(f'Missing schedule {method,scenario,p,contract,D}')
    return found[0]

def state(record,available):
    for s in record['states']:
        if bool(s['education_available'])==available and bool(s.get('shopping_A_available',s.get('shopping_available',True))) and bool(s.get('shopping_B_available',s.get('shopping_available',True))): return s
    raise ValueError('Missing state')

def activity_key(name):
    n=name.lower()
    if 'wait' in n:return 'Waiting'
    if 'education' in n:return 'Education'
    if 'shopping' in n and 'a'==n[-1]:return 'Shopping A'
    if 'shopping' in n and 'b'==n[-1]:return 'Shopping B'
    if 'travel' in n or 'home-campus' in n or 'campus-home' in n:return 'Travel'
    if 'home' in n:return 'Home'
    return name

def plot_schedules(records,out):
    specs=[('Nonjoin / normal',choose(records,'nonjoin'),True),
           ('B / normal / D=4.5 h',choose(records,'B'),True),
           ('C / normal / D=4.5 h',choose(records,'C'),True),
           ('C / normal / D=7 h',choose(records,'C',D=7),True),
           ('Nonjoin / education cancelled',choose(records,'nonjoin'),False),
           ('Hard C / cancelled / D=7 h',choose(records,'C',D=7),False),
           ('Release C / cancelled / D=7 h',choose(records,'C',contract='auto_release',D=7),False)]
    fig,(ax,socax)=plt.subplots(2,1,figsize=(13,7.7),gridspec_kw={'height_ratios':[3.2,1.2]},layout='constrained',sharex=True)
    for i,(label,rec,avail) in enumerate(specs):
        s=state(rec,avail)
        for seg in s['segments']:
            st,en=seg['start_h'],seg['end_h']; key=activity_key(seg['activity'])
            if en>st+1e-8:ax.barh(i,en-st,left=st,height=.5,color=ACTIVITY.get(key,'#cccccc'),edgecolor='white',lw=.6)
        q=s['q_kWh']
        if q>0:
            d=rec['D_hours']; span=1 if rec['contract']=='event_only' else d
            ax.plot([12,12+span],[i+.34]*2,color='#333333',lw=2)
            ax.plot([12,13],[i-.02]*2,color='#be4d4c',lw=4,solid_capstyle='butt')
        if s.get('education_end_h') is not None:
            ax.text(s['education_end_h']+.06,i+.1,'12:10',fontsize=7,va='bottom')
        if i in [0,2,5,6]:
            points=s['soc']['points']; t=[v['time_h'] for v in points]; e=[v['energy_kWh'] for v in points]
            socax.plot(t,e,lw=1.7,label=label)
    ax.set_yticks(range(len(specs)),[x[0] for x in specs],fontsize=9);ax.invert_yaxis();ax.set_xlim(6,24)
    ax.set_title('Education ends at 12:10; Campus parking is separate from the activity',fontsize=14)
    ax.grid(axis='x',alpha=.2)
    handles=[Patch(facecolor=ACTIVITY[k],label=k) for k in ['Home','Travel','Education','Waiting','Shopping A','Shopping B']]
    ax.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,-.02),ncol=6,frameon=False,fontsize=8)
    socax.axhline(12,color='#999999',ls=':',lw=.8,label='SOC floor')
    socax.set(ylim=(10,40),ylabel='Battery energy (kWh)',xlabel='Time of day')
    socax.set_xticks(range(6,25,2),[f'{v:02}:00' for v in range(6,25,2)]);socax.grid(alpha=.18)
    socax.legend(loc='upper left',ncol=2,fontsize=7,frameon=False)
    socax.set_xlabel('Time of day\nBlack bar: counted connection; red bar: fixed 7 kWh discharge\nUniform p=0.5; both shopping candidates available in shown states; free waiting',fontsize=8)
    save(fig,out,'activity_schedules_soc')

def plot_waiting_impact(rows,out,root):
    old=read_rows(root/'outputs/20261016_minimal_contract/bryan_01/compensation.csv')
    fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained')
    # Inherit column names from the archived run rather than recalculate it.
    xkey='D_hours'; ckey='C_compensation_CHF'
    if old and ckey not in old[0]:
        candidates=[k for k in old[0] if k.startswith('C') and 'CHF' in k]
        if not candidates: raise ValueError(f'Unknown archived columns: {list(old[0])}')
        ckey=candidates[0]
    ax.plot([r[xkey] for r in old],[r[ckey] for r in old],color='#999999',ls=':',lw=2,label='Previous: no intermediate waiting')
    for gamma,label,color in [(0,'Waiting allowed: free','#137f78'),(.03915,'Waiting allowed: 0.1305 CHF/h','#b77b22')]:
        rs=select(rows,gamma=gamma,scenario='uniform_activity',p=1,contract='hard')
        ax.plot([r['D_hours'] for r in rs],[r['C_compensation_CHF'] for r in rs],color=color,lw=2,label=label)
    ax.set(title='Normal-day C: the earlier increase depends on the no-wait assumption',xlabel='Required connection D (hours)',ylabel='Required compensation (CHF)',xlim=(1,7))
    ax.grid(alpha=.2);ax.legend(frameon=False,fontsize=9)
    save(fig,out,'waiting_impact')

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[2];out=a.run/'figures';out.mkdir(exist_ok=False)
    rows=read_rows(a.run/'compensation.csv'); records=json.loads((a.run/'schedules.json').read_text())
    if isinstance(records,dict):records=records.get('records',records.get('schedules'))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    plot_comparison(rows,out);plot_contracts(rows,out);plot_schedules(records,out);plot_waiting_impact(rows,out,root)
    print(json.dumps({'figures':sorted(v.name for v in out.iterdir())}))
if __name__=='__main__': main()
