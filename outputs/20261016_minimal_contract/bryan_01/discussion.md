# Discussion of the completed Bryan adaptation

## Observations

All 86 C MILPs solved successfully. All feasible B fixed LPs solved successfully; B is correctly infeasible for D > 4.55 h. Maximum MILP versus independent enumerated-LP objective discrepancy: 1.78e-15 utility. Maximum solver versus hand-check compensation discrepancy: 6.22e-15 CHF. Maximum primal residual violation: 3.55e-15. Maximum reported C MILP gap: 0. See verification.json.

| D (h) | A (CHF) | B (CHF) | C (CHF) | C shopping |
|---:|---:|---:|---:|---|
| 1.00 | 2.10000 | 2.10000 | 2.10000 | A |
| 4.00 | 2.10000 | 2.10000 | 2.10000 | A |
| 4.50 | 2.10000 | 3.70695 | 2.21745 | B |
| 5.00 | 2.10000 | infeasible | 2.21745 | B |
| 6.50 | 2.10000 | infeasible | 2.21745 | B |
| 7.00 | 2.10000 | infeasible | 4.00295 | B |

At D = 4 h, Shopping A is selected, education ends 16:03, and the campus promise ends 16:00. Its multiplier is 0 utility/hour because the campus departure has 3 minutes of slack. A therefore predicts CHF 2.10 throughout. B and C agree with A only through D = 4.05 h. Beyond that point, fixed Shopping A incurs education overtime and late shopping, with slope (0.0783 + 0.993)/0.3 = 3.571 CHF/hour.

C changes from Downtown Shopping A to Campus Shopping B at D = 4.082889947 h (about 244.973 minutes of connection). Compensation is continuous at this crossing. C then stays at CHF 2.21745 until D = 6.5 h, and reaches CHF 4.00295 at D = 7 h. This is a location-switch kink, not the exercise-drop jump in the separate synthetic case. B stays feasible through D = 4.55 h and becomes infeasible thereafter because the fixed A route would miss the imposed latest shopping start. C remains feasible by using same-campus shopping; it does not drop shopping on the tested range.

At D = 4.5 h, A predicts CHF 2.10, B requires CHF 3.70695, and C requires CHF 2.21745. The finite-value error therefore contains both a continuous scheduling burden and the value of the alternative location. At D = 5 h, B has no feasible schedule while C needs CHF 2.21745. A scalar linear prediction alone does not report that feasibility boundary.

All joined schedules deliver 7 kWh, reach Home at 25 kWh (41.667% SOC), and restore 36 kWh before 24:00. Their 13 kWh physical-floor margin confirms that SOC is not the switching cause in this controlled example. The differing connection quantities are waiting availability, not additional delivered energy.

## Interpretation and boundaries

The local multiplier describes the reference fixed-integer LP only. It is not a dual of the MILP and does not promise finite-change accuracy or predict the subsequent activity location. Here A differs from B after a continuous active-set change before B differs from C; their difference must not be attributed entirely to integrality.

The chosen hard 16:30–19:00 shopping window and the ban on intermediate waiting are design assumptions. They create this example's exact feasibility boundary. A long education stay until 16:03 follows from this restricted model and its coefficients, and is not observed behavior. Travel costs are set to zero, the paper's full charging-station alternative and SOC-related utility are absent, the money coefficient is an assumed common extension, and some source table units/prices require explicit interpretation. Neither the compensation amounts nor their prevalence are calibrated behavioral predictions. This run does not establish empirical contract acceptance, data-set representativeness, or general performance/scalability. External validity and uncertainty effects are NOT TESTED.

## Next discriminating checks

Allow an explicit waiting option, restore the full published activity/charging alternatives and utility terms, and vary the imposed shopping window before claiming a field-relevant burden. A larger externally grounded sample is needed to estimate how often this mechanism occurs. Do not change the present run; save any such experiment in a fresh run directory with its own settings and records.
