# Independent analytic oracle for the Bryan waiting experiment

This oracle is separate from `model.py` and `run.py`: it imports no optimization library and does not read solver results. `analytic_checks.py` minimizes exact per-pattern timing/energy formulas, then takes the feasible lower envelope over one common planned Shopping A/B/none choice. It is a diagnostic extension, not a replication of the published model or an estimate of real contract acceptance.

## Information structure and probability semantics

In the **primary `uniform_activity` family**, p is the common occurrence probability, consistent with the manuscript convention. Education, Shopping A and Shopping B realize independently. All eight `(xi_E, xi_A, xi_B)` combinations receive probability `p**sum(xi) * (1-p)**(3-sum(xi))`; zero-probability states and their path constraints are removed. The location choice is fixed before these realizations. If the selected shopping candidate does not realize, shopping is skipped; the other location is not substituted, even when available.

Auxiliary `education_cancel` and `shopping_cancel` families retain the earlier convention: p is the cancellation probability of that one activity. Those auxiliary p values therefore have a different meaning and must be labelled explicitly. `deterministic` has one certain state.

The primary uniform family preserves the common 07:00 first departure, together with enrollment/contract and the common planned shopping location. Education end is shared across states where education realizes. After 06:00 shopping start, waiting and the specified cancellation shortcuts may adjust. A nonempty Campus tour reaches Campus at 07:30 even if education is absent. A released A-shopping tour leaves Home at 07:00, reaches Downtown at 07:03 and waits until 16:30: **9.45h of nonhome waiting**. Every nonhome wait receives gamma. A released state with neither education nor the planned shopping activity stays home with zero tour/wait. Auxiliary single-cancellation controls keep flexible departure: without education, mandatory service reaches Campus at 12:00, a released B tour arrives at 16:30, and a released A tour can time its short direct journey to shopping. Release sets both service and connection obligations to zero; it does not authorize optional compensated discharge.

## Why education can be eliminated analytically here

Education starts at 07:30 and has desired/minimum duration 4h40, ending at E = 12:10. Its extension remains allowed in the optimization. Extending it by a small duration can replace at most the same amount of Campus waiting, saving gamma while costing alpha = 0.0783 utility/hour. For `0 <= gamma < alpha`, extension strictly increases cost. Thus an optimum ends education at 12:10, including when that endpoint is shared across all states where education realizes, and every remaining Campus hour is correctly classified as waiting or shopping. Both implemented gamma values, 0 and 0.03915, satisfy this condition. The oracle rejects larger gamma rather than claiming its formulas remain valid there.

## Exact single-state formulas

Times are decimal hours. Let a = 4.05 (4h03), a_max = 4.55 (4h33), b = 6.5 (6h30), beta = 0.993 utility/hour and mu = 0.3 utility/CHF. Shopping A travel from Campus is 0.45h; its latest start is 17:00. A surviving A visit with a Campus tour departs Campus at `max(16.05,12+D)`, starts shopping 0.45h later and is feasible only through D = 4.55. Shopping B starts at 16:30; Campus departure is `max(18.5,12+D)`. Waiting after shopping is allowed, so B need never start late. With no shopping, Campus departure is `max(E,12+D)` if education survives and `12+D` otherwise. Event-only service uses D_eff = 1 for every plotted D.

For a uniform state with absent education, the waiting anchor is Campus arrival 07:30, rather than 12:00 or 16:30. A direct released A tour instead has the 9.45h Downtown wait described above. These are charged as nonhome waiting; source/profile cancellation controls retain their separate flexible-arrival convention.

A Campus tour uses 20km = 4kWh. Without education or service, Shopping A uses 2km = 0.4kWh, Shopping B still uses 20km, and no shopping means staying home with zero driving. Service adds exactly 7kWh. Restoration charge is route energy plus service because initial/final energy coincide and efficiency is one. The state cost is

`0.3 * 0.30 * restoration_kWh + gamma * nonhome_wait_h + 0.993 * shopping_delay_h - 11.3 * actual_shopping - 17.4 * actual_education`.

The full expected nonjoining optimum is used as the compensation baseline; the baseline location is optimized under the same occurrence states and waiting flexibility. C is the lower envelope of feasible common plans. The oracle also reconstructs home charging completion and minimum energy; all configured tours remain feasible within the battery/day bounds.

## Primary uniform-occurrence free-wait formulas

Write delta = max(0,D-4.05). Nonjoining A-plan expected travel energy is `4p + 0.4p(1-p)` kWh. It weakly dominates the B-plan baseline, whose extra expected travel cost is `1.08p(1-p)` CHF.

For hard fulfillment, every state uses the Campus tour and discharges 7kWh. Therefore

- `C_hard = 3.30 - 1.32p + 0.12p^2` CHF, independent of D;
- fixed reference A adds `3.31p * delta` while feasible;
- fixed reference A is infeasible after D=4.55 if p>0, but remains feasible for all D at p=0 because shopping never realizes;
- reference B is equally optimal at D=4, and its fixed-plan curve equals C for every D;
- expected delivered energy is 7kWh and full-event probability is one.

Event-only control has the same C value, has no D dependence for any fixed plan, and also supplies 7kWh. This is a genuine null control.

For automatic release after education fails to realize,

- `K_A = 2.10p + 3.31p^2 * delta`, feasible through D=4.55 when p>0;
- `K_B = 2.10p + 1.08p(1-p)`, feasible for every D;
- C is the feasible lower envelope, with expected delivery `7p` kWh and full-event probability p;
- at p=0 the only state has no service or activities, so all D have zero burden and undefined unit payment;
- at p=1 the problem is deterministic: C=2.10 for every D, while reference A loses feasibility after 4.55.

The interior release switch is `D* = 4.05 + 1.08(1-p)/(3.31p)` for p>0, if it does not exceed 4.55. Otherwise C keeps plan A through the boundary and then jumps to plan B. The right jump is

`max(0, 1.08p(1-p) - 1.655p^2)`.

A jump occurs for `0 < p < 0.3948811700`. At p=.25 it is **0.0990625 CHF**. At p=.5 the switch is **4.3762839879h** and C moves continuously from 1.05 CHF to its 1.32 CHF plateau. The plateau differs from the auxiliary education-cancel experiment because the selected shopping candidate also realizes only with probability p.

At D=4 the conditional derivative for free waiting is zero, so A is flat at the optimal reference compensation. In the release case at interior p, reference B is more expensive at D=4 and must be described as a forced policy sensitivity, not another equally optimal reference. At hard fulfillment, A is exactly equal to C for every D: the old undercompensation result caused by forcing waiting into education disappears.

## Auxiliary single-cancellation checks

For education cancellation probability p with shopping certain, hard C and event-only C equal `2.10+1.08p` CHF. Auto-release plan A costs `(1-p)[2.10+3.31delta]`; plan B costs `2.10(1-p)+1.08p`. C takes their feasible lower envelope. At p=1, normal constraints are absent and auto-release C=0 for every D. For p=.5 its plateau is 1.59 CHF. A right jump occurs for cancellation p>0.6051188300; at p=.75 it is 0.39625 CHF.

Shopping cancellation alone, with education certain and free waiting, gives C=2.10 CHF under every contract and every D. That null is conditional on free waiting: gamma>0 makes the extra waiting after education costly when shopping is absent. It is also not a general statement about simultaneous cancellation of education and shopping.

## Positive waiting cost and fixed versus cumulative connection

The implementation solves positive gamma by the same exact state timing expressions; it does not use LP enumeration. Education remains at 12:10 by the alpha>gamma proof above. For a present education/shopping pair, the fixed-A extra cost is `(gamma+beta)*delta/mu`; the fixed-B extra cost is `gamma[0.45+max(0,D-6.5)]/mu`. Cancellation-state route and all nonhome waiting costs are evaluated separately and averaged before optimization over the common plan. In uniform states this includes early Downtown arrival after the fixed first departure; it must not be silently treated as cost-free Home time or converted to a flexible noon Campus arrival. Thus waiting disutility is not imputed from an education-duration coefficient without declaration: gamma is an added assumption.


The second independent function `uniform_strict_closed` checks the strict-arrival positive-gamma case without calling the per-state timing routine. Let w0 = 16.05-E, delta_B = max(0,D-6.5), and

`W = (1-p)[D+4.5+p(w0-9.45)]`.

For hard service, its A-plan compensation is `H0 + gamma*W/mu + (gamma+beta)*p*delta/mu`; its B-plan compensation is `H0 + gamma[W+0.45p+p*delta_B]/mu`, where `H0=3.3-1.32p+0.12p^2`. For release, its A-plan compensation is `2.1p + gamma*p(1-p)(D-1/6)/mu + (gamma+beta)*p^2*delta/mu`; its B-plan compensation is `2.1p+1.08p(1-p)+gamma[p^2(0.45+delta_B)+p(1-p)(D-1/6-0.45)]/mu`. The same feasibility boundaries apply. Event-only substitutes D=1. These expressions explicitly count the 9.45h Downtown baseline wait and the 07:30 Campus arrival after education fails to realize; flexible-arrival controls do not use these strict formulas.

With one uninterrupted Campus visit, mandatory 12:00–13:00 service implies arrival <=12:00 and departure >=13:00. For 1<=D<=7, availability for cumulative D hours in 12:00–19:00 is equivalent to departure >=12:00+D. The fixed interval `[12:00,12:00+D]` imposes the same scheduling condition. The equivalence concerns activity/service feasibility after projecting out plug-time choices; arbitrary H plug trajectories and fixed-clock plug trajectories are not literally identical sets. No assertion of a distinct flexibility value can be made from this pair in this instance.

## A/B/C, payments and interface

`analytic_comparison(D, probability, family, contract, gamma, reference_D=4.0, reference_pattern=None)` returns the requested CSV quantities: `A_compensation_CHF`, `B_compensation_CHF`, `B_alt_compensation_CHF`, `C_compensation_CHF`, feasibility flags, expected delivery, full-service probability, baseline/joined route km, rates and reference tie information. Family aliases `uniform`, `uniform_occurrence`, `education`, `shopping` and `det` are accepted. Reference ties prefer A, then B, then none. `B_alt` always fixes B, whether or not B is an optimal reference; `alternative_B_reference_is_optimal` makes that distinction explicit.

A uses the exact conditional derivative at D=4; it has no optimized schedule. B fixes the common planned pattern and allows state timings to adjust. C reoptimizes that common pattern. Fixed-integer derivatives are not full-MILP shadow prices. Infeasible B values are `None`, never artificial penalties.

A fixed grant compensates the expected burden. A constant delivered-energy price is burden divided by expected delivered kWh only because dispatch is exogenous here. The oracle distinguishes `defined`, `infeasible`, `no_delivery_zero_burden`, and `no_delivery_positive_burden` rate states. Lower expected payment under release must be read alongside lower supply; it is not a dominance claim at equal service.

`python analytic_checks.py --self-test` executed **9,492** analytic checks with no solver calls. All free-wait C values and all strict-arrival positive-gamma A/B/B-alt/C values agreed with their separate closed-form formulas to at most **1.58e-14 CHF**. Checks cover all probability levels, contracts/families, selected positive-gamma cases, exact boundaries/right limits, eight-state and endpoint support, and cumulative/fixed-clock projection equivalence. Actual solver CSV comparison is a separate pending validation; these analytic values must not be presented as solver output.
