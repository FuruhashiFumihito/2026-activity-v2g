# Experiment overview

Question: do Bryan A/B/C compensation and schedules survive allowing parked waiting, under multiple fulfillment/payment specifications and uncertain activities?

Authority: the current user explicitly requests waiting and uniform probability p as in the manuscript. Primary p is occurrence probability for independent Education/Shopping A/Shopping B, with common location,07:00 departure, surviving durations/order, and8 complete states. Read source_snapshot/settings_contract.md for the pre-run design and its user clarification. Published profile inputs are distinguished from added OD/windows/V2G/probabilities/gamma.

Primary design: p in0,.25,.5,.75,1; gamma in0,.03915 utility/hour; D1..7h on5-minute grid plus boundaries. Contracts hard, automatic release on educational non-realization, event-only. Risk-neutral fixed enrollment and delivered-energy payment thresholds; release reduces supply. Auxiliary one-factor cancellation runs use flexible departure and cancellation-p, separately labelled.

Comparators A conditional dual atD4, B full reference-integer fixing, C common-plan MILP. Independent known-pattern LP and independent analytic formulas; ties A/B/none in that order; alternativeB reference sensitivity. Same baseline flexibility, SOC and scenario distribution. No Monte Carlo sampling, seed NA. Budget/time/gap/thread/runtime/source hash/command are in config.json and environment.json. Existing runs are never overwritten.

Actual artifacts and quantitative results: ../report_ja.md, compensation.csv, solver_status.csv, handcheck.csv, references.csv, soc_audit.csv, schedules.json and verification.json. Every result is a model diagnostic, not estimated contract acceptance or manuscript solver validation at full scale.
