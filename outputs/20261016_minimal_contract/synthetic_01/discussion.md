# Observed results and interpretation

All 29 MILPs were certified optimal with zero reported MIP gap. Every feasible B LP and every C solution matched hand formulas within 1e-06. Maximum C discrepancy against separate route LPs: 0. Nonjoining utility: 2,880. Reference compensation: 630. Actual LP multiplier: 1,800 units/h, confirmed by one-minute differences on both sides.

For 1 ≤ D ≤ 1.5, A = B = C = 180 + 1,800(D − 1). At D=1.5 gym is 17:45–18:45 and remains feasible. For D>1.5 the fixed-activity B LP is infeasible and C drops the gym: C = 3,180 + 1,200(D − 1). A remains an extrapolation of the reference LP multiplier; it is not a full-MILP shadow price or an objective value of infeasible B.

C equals 1,080 at D=1.5 and has right limit 3,780, an upward jump of 2,700 (not 3,000): the disappearing gym benefit is already reduced by 300 of delay burden. The right-limit point is analytical, not a sampled solver observation. At D=1.75, A=1,530 while C=4,080: underestimation 2,550. A fixed 2,000 reward would be accepted under A's criterion but rejected under C. At D=2, A=1,980 and C=4,380.

The five hand checks 180, 630, 1,080, 4,080 and 4,380 at D=1, 1.25, 1.5, 1.75 and 2 all agree with actual solver outputs. Route energy is unchanged; dispatch adds 6 kWh and hence 180 home charging cost. Every reconstructed SOC path stays above 12 kWh and returns to 36 kWh before day end.

This run validates this toy and illustrates activity infeasibility. It does not demonstrate continuous-regime approximation error: A and B agree wherever B is feasible. The jump follows from a hard closing time and fixed activity duration; it is not a universal property. SOC scarcity, uncertainty, battery degradation, endogenous dispatch, empirical preferences and population behavior are untested. A literature-based named profile must distinguish source schedule fields from experimentally assumed windows, battery values, preferences and contract settings.
