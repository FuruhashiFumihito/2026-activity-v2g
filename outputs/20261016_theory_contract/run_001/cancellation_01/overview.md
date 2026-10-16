# cancellation_01: experiment overview

The question, complete numerical inputs, grid and stopping rules were saved in
`config.json` before solving. This run contains 2236 deliberately designed
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
Execution gate: **PASS**. Software and revision: `environment.json`.
