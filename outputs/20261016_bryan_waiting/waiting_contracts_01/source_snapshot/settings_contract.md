# Bryan waiting, contract, and cancellation experiment: pre-run specification

## Authority and scope

The user requested a rerun with intermediate waiting, multiple contracts, and uncertain activities. This is a new diagnostic extension of `experiments/minimal_contract/bryan.py`, not a change to the manuscript formulation. Local paper_contract/claims/decisions are placeholders; the source audit and prior run remain the provenance of published profile inputs. No shared supervisor rules are applied.

## Evidence questions and controls

| Question | Strong objection | Paired comparison | Required evidence |
|---|---|---|---|
| Does the compensation gap survive intermediate waiting? | Extended education was absorbing forbidden waiting | Previous no-wait run versus Campus waiting before and after shopping | A/B/C curves, education endpoints, physical parking endpoints, reference-plan ties |
| Does the conclusion depend on free waiting? | Zero waiting cost makes parking free | waiting cost gamma = 0 and 0.03915 utility/hour | Same inputs; explicitly assumed waiting coefficient, below education over-duration cost 0.0783 |
| Do activity cancellations create a contract burden? | Removed activity utility is counted as a contract loss | Education cancellation versus shopping cancellation | Matched scenario baselines and common ex-ante activity location; separate extra travel energy |
| Does a release contract reduce cost at equal supply? | Lower payment simply buys less energy | Hard fulfillment versus automatic release after education cancellation | Expected compensation, delivered kWh, full-event delivery probability, extra km, and unit payment |
| Does the payment basis itself change risk-neutral burden? | Fixed grants and delivered-energy payments are conflated with obligations | Fixed enrollment grant versus delivered-energy payment with the same mandatory dispatch policy | Identical expected break-even payment; unit rate undefined when expected delivery is zero |

## Added behavior and information structure

Published Education starts at 07:30 with desired duration 4h40; published late-shopping and long-education utility coefficients and EV specifications are retained. Education may extend with the original over-duration penalty. Campus waiting is an explicit variable separate from Education, both before and after Campus shopping. Campus departure may be as late as 19:00. Waiting is available to joined and nonjoined users. No intermediate return home, additional tour, new activity, or alternate order is introduced.

The enrollment decision, contract, and planned Shopping A/B/none choice are common across scenarios. At 06:00 the availability of a known candidate is revealed; after that, departure times, waiting, and permitted cancellation shortcuts adjust. This is a limited recourse extension of the manuscript's fixed-first-departure and no-wait assumptions. Surviving activity order, desired duration, and time-window definitions remain common; actual shopping start may adjust inside its existing hard window. Unknown activity arrival and emergency exit are not tested.

Main uncertainty: Education alone is cancelled with probability p. Shopping remains available. A null control cancels Shopping alone while Education remains certain. Cancellation is of an activity, not closure of Campus. Scenarios of probability zero impose no path constraints. p in {0, .25, .5, .75, 1}; these probabilities are design factors, not estimates. Deterministic finite-scenario optimization, no Monte Carlo sampling or confidence interval.

If Education is cancelled, no-service Shopping A can be reached directly from home; Home–Shopping A is assumed symmetric to the previous A–Home leg (0.05h, 1km), so the round trip uses 2km, 0.4kWh. This is an added OD assumption, not a published distance. A Campus visit uses the same 20km, 4kWh tour as before. Without Education, mandatory service reaches Campus at 12:00; a no-service Campus-shopping tour arrives at 16:30. Staying home before departure is allowed and has no added time penalty. Campus waiting remains possible if the educational candidate is cancelled.

## Contracts and money

- Hard minimum connection: 7kWh is discharged at 7kW during 12:00–13:00 in every positive-probability scenario, with at least D Campus-connection hours counted in 12:00–19:00.
- Automatic release: identical in normal scenarios; if Education is cancelled, both discharge and connection obligations are automatically removed. This is a stipulated event, not an endogenous release option. Delivered energy is fixed to zero in that state; optional discharge and performance payment are not allowed even if planned Shopping B still brings the user to Campus.
- Event-only control: 12:00–13:00 discharge obligation with no extra connection beyond that hour.

Each obligation is evaluated with a fixed ex-ante enrollment grant, retained in released states with no refund or release fee, and with a constant payment per delivered kWh. Risk neutrality is assumed. Dispatch under each contract is exogenous to the activity decision, so the minimum unit payment is exactly expected uncompensated burden / expected delivered kWh in this diagnostic. This division is not valid for an endogenous fulfillment decision. Zero delivery and zero burden yield an irrelevant/undefined unit rate; zero delivery with positive burden cannot be compensated by any finite delivered-energy unit rate. Neither is described as supply success.

The single uninterrupted Campus visit means a fixed interval [12:00,12:00+D] and the hard cumulative D constraint have the same feasibility set here. They are an equivalence check, not distinct contract treatments.

## Comparators and reproducibility

A is the fixed-integer LP dual extrapolation at D=4h. B fixes all common planned-location binaries at that reference optimum. C optimizes common planned-location binaries with scenario-contingent continuous timings. Reference ties prefer Shopping A, then B, then none. With free waiting, an equally optimal reference B may produce a different fixed-plan B curve; report the B-reference sensitivity, and do not call its gap a unique property of the person.

Use the same nonjoining scenario optimization for compensation, including the same departure and waiting flexibility. Initial/final energy 36kWh, lower bound 12kWh, capacity 60kWh, home charging 7kW, efficiency 1, price 0.30 CHF/kWh, money scale 0.3 utility/CHF. Energy service, route, and SOC are audited for each solved scenario. Parameters are inherited or explicitly added above; no behavioral calibration is claimed.

D ranges 1–7h on a five-minute grid, plus boundary values around 4.05h and 4.55h and D=4.5,5,7. Waiting costs gamma in {0,0.03915}. Retain null outcomes and infeasible B values as missing, never substitute penalties. Compare actual MILP with independent three-pattern LP enumeration and analytic free-wait formulas. Verify the local dual with one-minute differences. Save source snapshots, environment, configuration, solver status/gap/residual, schedules, SOC, overview and discussion in a fresh output directory; preserve prior runs.

## Analytic predictions for verification, not substituted solver outputs

With free waiting, hard-contract C under Education cancellation has expected burden 2.10 + 1.08 p CHF. The 1.08 p term is extra travel electricity, not lost educational utility. For automatic release with a common planned shopping location, the A-plan burden is (1-p)[2.10 + 3.31 max(0,D-4.05)] and is feasible up to D=4.55 when p<1. The B-plan burden is (1-p)2.10+1.08p. C takes the feasible lower envelope. At p=1 all service is removed and the A plan has zero burden for every D. These predictions must be checked against solved values.

## User clarification and primary-design amendment (before execution)

The user clarified: 「論文に書いてある通り、一律の確率p」. The primary uncertainty is therefore **uniform_activity**: Education, Shopping A, and Shopping B each independently follow Bernoulli(p), where p is the probability of realization, not cancellation. Dawn/dusk remain certain. Enumerate all 8 candidate states with q = p^(number realized) (1-p)^(number cancelled), dropping zero-probability states. Candidate alternatives are independent, as in current manuscript decision-002; the planned chosen alternative cannot be replaced after realization.

Current manuscript authority was read from the active methodology worktree (not the placeholder main-branch text): `sections/03_methodology.tex` lines 275–290 and `paper/decisions.yaml` decisions 002–003, in `/Users/furuhashikaoruichi/.codex/worktrees/methodology-paragraph-draft/2026-activity-v2g`. The manuscript has local changes and is not altered by this experiment.

This amendment supersedes the earlier specification's flexible-first-departure rule **for the primary uniform_activity experiment**. Keep the common first departure at 07:00. A Campus tour arrives at 07:30 even when Education is cancelled; direct Home–Shopping A arrives at 07:03 and waits Downtown until shopping. A state with no remaining activity and no service is entirely at home with zero physical travel. Education duration is shared across states in which it survives. All nonhome waiting, including Downtown waiting, is charged the assumed gamma; home time is not. Shopping start and waiting can adjust after realization; location, activity participation realization, ordinary duration, relative order, and first departure remain planned/common. Waiting is the authorized extension to the original no-wait formulation.

The education_cancel and shopping_cancel families remain mechanism controls with their earlier flexible-departure policy and cancellation-probability convention; they must never be pooled with the primary uniform occurrence-p results or presented as the requested main experiment.

For the primary free-waiting hard contract, the analytic prediction is C = 3.30 - 1.32p + 0.12p^2 CHF. Under automatic release, the planned A branch is 2.10p + 3.31p^2 max(0,D-4.05), feasible through D=4.55 when p>0; the planned B branch is 2.10p + 1.08p(1-p). C is the feasible lower envelope and expected delivery is 7p kWh. At p=.25 the boundary jump is .0990625 CHF. At p=0 all service is automatically stopped and C=0. These are independent verification predictions, not hard-coded solver results.
