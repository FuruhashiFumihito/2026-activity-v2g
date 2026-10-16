# Bryan minimum contract diagnostic

Status: completed; 86 paired D cases; deterministic, no stochastic replications.

## Evidence question and comparison

Does a marginal value from fixed activity choices predict the finite cost of a campus connection promise when two shopping locations are available? A is the actual fixed-LP multiplier at D = 4 h extrapolated to each D; B fixes both shopping binaries at that reference and resolves continuous variables; C resolves the two-binary MILP. All methods share the same utility, physical state, 7 kWh fixed service, price, and hard time windows. Infeasible B cases remain missing and are never coded as zero. This is model correctness and a mechanism diagnostic, not external validation of contract choice.

## Provenance and scope

Published input profile: Wang, Pougala and Hillel (2025), DOI https://doi.org/10.1016/j.trd.2025.104911, Table 3 (p. 11), Table 4 (p. 12), Table A.1 (p. 23). Bryan starts at Home (Downtown), has Education (Campus), desired start 07:30 and duration 4 h 40 min, and Shopping A (Downtown) / B (Campus), desired start 16:30 and duration 2 h. Education constant 17.4 and long-duration coefficient -0.0783; Shopping constant 11.3 and late-start coefficient -0.993. Source EV capacity 60 kWh, home charging power 7 kW, energy consumption 0.2 kWh/km. Timing coefficients use hours, following official OASIS documentation; Appendix A.1 itself does not print units.

All contract conditions, shopping hard windows, travel values, initial/end battery state, prices, money scale extension, eligibility rules and zeroed utility terms are added assumptions documented in config.json. The paper's positive short-shopping coefficient (+0.528) is not negated: shopping duration is held at its desired 2 h so that term is identically zero. All travel-utility, taste-error, SOC increase/anxiety, connection hassle, and degradation terms are omitted from this diagnostic. Ordinary charging is available only at Home after return; efficiency is 1. Education is mandatory, starts at 07:30, and has duration at least 4 h 40 min. No intermediate waiting is allowed; the only route order is Home–Education–optional shopping–Home. The published intermediate charging-station activity is omitted in this minimum-case restriction.

The optimum nonjoining schedule stays at Education until 16:03, then reaches Shopping A at 16:30. **This long campus stay is a model result of the restricted no-wait case, not an observed diary or a reported result from the paper.** This run must be called a published-profile adaptation, not a reproduction of the full published model or a Swiss survey respondent.

## Experimental settings contract

Unit: one adapted Bryan profile per connection requirement. D = 1 through 7 h in 5-minute steps, plus reference and threshold neighborhoods at +/- 1 minute and the exact thresholds. No random seed is needed because taste shocks and uncertain activities are absent. Reference D = 4 h. Controls: full campus connection during 12:00–13:00, fixed 7 kWh discharge then, D total hours within 12:00–19:00, no unfulfilled-service option, joining reward R = 0 while solving. Campus parking is continuous across Education and Shopping B. For display, the actual plug interval is [12, 12+D], even if the vehicle remains parked longer. Initial energy 36 kWh, floor 12 kWh, final 36 kWh, flat price CHF 0.30/kWh, utility of money 0.3 utility/CHF. These common initial/end states make joining's extra restoration cost exactly CHF 2.10. All routes take 1 h and consume 4 kWh.

Solver: scipy.optimize.milp / HiGHS for C; scipy.optimize.linprog(method='highs-ds') for B and independent three-pattern enumeration. Time limit 60 s per solve; MILP relative gap 1e-10; LP primal and dual feasibility tolerances 1e-9. No best-known incumbent is treated as optimal without the success status and saved gap. Environment and code hash are in environment.json; settings precede interpretation. Run command: `python experiments/minimal_contract/bryan.py --output /Users/furuhashikaoruichi/.codex/worktrees/minimal-contract-experiment/2026-activity-v2g/outputs/20261016_minimal_contract/bryan_01`. The script rejects an existing output directory. Starting revision: `543974b401900a7b11ec5edb28a87e8890b878d1`; script hash: `3c27494c18df07877b4efcb34b43354cec39ff7eb3de09f973eded9f70287a7e`. No parameters were changed after observing the run.

## Claim–evidence and figures

| Claim | Reviewer objection | Controlled evidence | Pass rule | Scope |
|---|---|---|---|---|
| Local price can miss finite scheduling burdens | Error could be a solver or units defect | A vs B with same integers; MILP vs enumerated LPs and hand formulas | Objective errors < 2e-7 utility; residuals < 2e-7 | Deterministic adapted case |
| Location choice changes contract value | A false jump may be imposed | B vs C with identical contract and fixed delivered kWh | Save pattern, timing, and feasibility; retain continuous crossover | Two shopping alternatives only |
| SOC is held comparable | Cost may come from different energy states | Same initial/end state and routes; exact home charge audit | Fixed 7 kWh and final 36 kWh; floor and charge deadline feasible | Efficiency 1, no degradation |

compensation.png/pdf answers how A/B/C diverge. schedules_soc.png/pdf shows the measured mechanism and battery feasibility. Solver records include every vector, residual, LP marginal, status, and MILP gap. Handcheck and enumeration discrepancies are in verification.json and handcheck.csv.
