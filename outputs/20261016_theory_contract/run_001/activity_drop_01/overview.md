# Synthetic minimal contract experiment activity_drop_01

This run checks whether a local fixed-integer LP multiplier captures finite contract burden when an optional fixed-duration activity loses feasibility. It is an authored deterministic one-person mechanism example, not a profile or parameter estimate from a Swiss dataset.

## Configuration and comparison

Time is continuous. Work: 09:00 start, at least eight hours, end no later than 20:00, overtime 1,200 money-equivalent units/h. Gym: optional one hour, earliest start 17:15, latest end 18:45, participation benefit 3,000, delay 600/h. H–W: 30 min and 2 kWh; W–G and G–H: each 15 min and 1 kWh. Both routes consume 4 kWh. Battery: 60 kWh capacity, 36 kWh initial/final, 12 kWh minimum. Joining: fixed 6 kW dispatch during 16:00–17:00, complete fulfillment, at least D hours of connection in 16:00–19:00. Home charging: 6 kW, 30 units/kWh. All other utilities/costs are zero.

D is swept every five minutes from one to three hours, plus one-minute neighbors of the reference and boundary (29 instances). C is an actual one-binary MILP. B fixes the complete integer vector to C at D=1.25 h. No auxiliary integer regimes are needed. A uses the actual reference B multiplier, 1800 units/h. Separate route-enumeration LPs and hand formulas independently audit the results. Primary solves use a 30 s limit; MILPs require zero relative gap. There is no random input or statistical replication.

SOC is analytically eliminated because route energy and dispatch are fixed. Executed checks reconstruct route energy, home charge and SOC from configuration and the canonical solver schedules for 44 solutions, covering baseline, reference, every swept C and feasible B, and both finite-difference LPs. `soc_checks.json` records each computed state, all energy balances, capacity/lower-bound checks and home charging completion; `independent_checks.json` includes the resulting gate. This elimination is equivalent for this toy, not a solver implementation of the full manuscript SOC model. Home timing has zero utility; figures select earliest home arrival and charging among tied optima.

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
/private/tmp/activity-v2g-runtime/bin/python /Users/furuhashikaoruichi/.codex/worktrees/theory-contract-study/2026-activity-v2g/experiments/minimal_contract/synthetic.py --output /Users/furuhashikaoruichi/.codex/worktrees/theory-contract-study/2026-activity-v2g/outputs/20261016_theory_contract/run_001/activity_drop_01
```

The entry point refuses to overwrite an existing run directory; reruns require a fresh directory. Revision at run: `7d25187f9756691a434d69e6e8f9f742e3b83803`. Full manuscript experiments, empirical calibration, scalability and external validity are outside this toy's scope.
