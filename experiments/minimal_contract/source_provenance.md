# Source provenance for the minimal contract experiment

Audit date: 2026-10-16. Mode: evidence audit. The source PDF, its extracted text, and the Appendix A image were checked. This record distinguishes published inputs from the additional assumptions of the diagnostic experiment. It is not a replication of the complete published model.

## Source identifiers

- **J2025:** Wang, S., Pougala, J., and Hillel, T. (2025). *Joint modelling of electric vehicle charging and daily activity scheduling*. Transportation Research Part D, 147, 104911. DOI: https://doi.org/10.1016/j.trd.2025.104911 .
- Audited local PDF: `/Users/furuhashikaoruichi/Documents/Codex/2026-10-14/joint-shapp-pdf/sources/1-s2.0-S1361920925003219-main(1).pdf`.
- SHA256: `81f4dcaf6798dd17d6c4bdc66e98ce3f4278ee9fbf8d6b36d7a2ad0564c04988` (recomputed for this audit).
- Page locators below refer to the printed PDF pages, which also match the PDF page indices plus one. No complete source PDF is included in this experiment or committed to the repository.
- **OASIS-DOC:** Official OASIS 1.0.0 documentation, linked by the authors' repository https://github.com/transp-or/oasis . Data definitions: https://oasis-abm.readthedocs.io/en/latest/input_data.html ; utility implementation: https://oasis-abm.readthedocs.io/en/latest/_modules/activity.html . Consulted 2026-10-16. This supplements the unit interpretation; it does not verify the unpublished J2025 implementation.

## Published Bryan inputs

J2025 Section 4.1 (p.11) uses Swiss Mobility and Transport Microcensus data for Lausanne residents and constructs operational preferences and feasible inputs heuristically. Tables 3–4 list activity candidates and **desired** times; they are not an observed completed diary and do not report the hard windows used below. Figure 1 (p.15) presents generated schedules.

| Activity | Published location | Published desired start | Published desired duration | Published charging choices | Locator |
|---|---|---|---|---|---|
| Home | Downtown | Not tabulated | Not tabulated | None or home slow | J2025 Table 3, p.11 |
| Education | Campus | 07:30 | 04:40 | None, slow, or fast | Tables 3–4, pp.11–12 |
| Shopping A | Downtown | 16:30 | 02:00 | None, slow, or fast | Tables 3–4, pp.11–12 |
| Shopping B | Campus | 16:30 | 02:00 | None, slow, or fast | Tables 3–4, pp.11–12 |
| Service station | Service station | 11:00 | 00:00 | None or rapid in Table 3 | Tables 3–4, pp.11–12 |

Shopping A and B are alternatives for one shopping opportunity, not two errands to be added together. Section 3.3 (p.7) explains the mutual exclusion of duplicate activities at different locations. Equal place labels do not establish measured zero OD distance. Table 6 (p.14) describes Bryan as a student in a single-family dwelling with home and public charging access; public includes education locations. Charging access does not establish bidirectional/V2G capability. For a selected station visit, the formal station constraints link activity participation and charging; its desired duration of zero does not require an actual zero-duration visit.

| Activity coefficient | Education | Shopping | Locator |
|---|---:|---:|---|
| Participation constant | 17.4 | 11.3 | J2025 Table A.1, p.23 |
| Early start | -2.56 | -2.51 | Same |
| Late start | -1.54 | -0.993 | Same |
| Short duration | -0.783 | **+0.528** | Same; positive Shopping sign visually verified |
| Long duration | -0.0783 | -0.133 | Same |

The positive Shopping short-duration coefficient is retained as published. It conflicts with the nonpositive-sign condition stated around Eq.4 (p.6). The diagnostic experiment fixes both shopping durations to two hours, so their short/long deviations are exactly zero and this inconsistency is inactive. Education has minimum duration equal to its desired duration, so its short-duration term is also inactive. No coefficient clipping, sign repair, or re-estimation is implied.

**Time-unit certainty:** Table A.1 and the model notation table do not explicitly label these activity coefficients as per hour or per minute. The diagnostic implementation uses hours, consistent with OASIS-DOC: `ActivityData` defines desired and feasible times in hours, and the documented activity implementation multiplies directly computed deviations by the penalty coefficients without a factor of 60. J2025 Section 4.2 (p.12), Eq.39 also defines charging rate per hour through kW/kWh. These are supporting grounds for the convention, not a claim that Table A.1 explicitly states its units. If time is stored in minutes, divide the hourly coefficients by 60.

| Published EV/charging input | Value | Locator and qualification |
|---|---:|---|
| Battery capacity | 60 kWh | J2025 Table 5, p.13 |
| Driving energy consumption | 0.2 kWh/km | Same |
| Slow / fast / rapid charging power | 7 / 22 / 50 kW | Same; Sections 4.2–4.3, pp.12–13 |
| Comfort SOC threshold | 30% | Same; comfort preference in Eq.8, not a published 20% hard reserve |
| Charging cost coefficient | -0.3 utility/CHF | Table A.3, p.23 |
| Work / other charging inconvenience | -3.59 / -4.34 | Same; disabled in diagnostic experiment |
| Low-SOC / charged-SOC coefficients | -80 / +25 | Same; disabled in diagnostic experiment |
| AC / DC energy price in prose | 0.56 / 0.79 CHF/kWh | Section 4.3, p.13 |
| Home price as printed in Table 5 | 30, labelled CHF/kWh | Table 5, p.13; numerical scale inconsistent with AC/DC prose |

The experimental home price **0.30 CHF/kWh** is an explicit centime-scale interpretation of the table's 30, not an independently verified home-price statement in the prose. Table 5 also swaps the peak/mid-peak factors relative to Section 4.4; TOU is not used in this diagnostic case. The J2025 model is for charging and does not supply the V2G contract or a discharge calibration.

## Added diagnostic assumptions for the Bryan case

The following are experiment design inputs, not recovered MTMC observations or published person-specific constraints.

| Component | Assumption |
|---|---|
| Candidate set | Dawn/home, Education, Shopping A/B, dusk/home; service-station candidate excluded |
| Sequence and participation | Education required; at most one shopping alternative; education precedes any shopping; no standalone waiting activity |
| Education | Fixed start 07:30; minimum duration 04:40; end no later than 19:00 |
| Shopping A/B | Duration fixed at 02:00; start no earlier than 16:30 and finish no later than 19:00 |
| OD: home–Campus | 0.50 h and 10 km each way |
| OD: Campus–Shopping A | 0.45 h and 9 km |
| OD: Shopping A–home | 0.05 h and 1 km |
| OD: Campus–Shopping B | Zero time and distance by the designed common-Campus assumption |
| Eligible V2G activities | Education and Shopping B at Campus; added V2G access, beyond published charging access |
| Fixed dispatch | Discharge 7 kW during 12:00–13:00; fixed 7 kWh across contract-duration cases |
| Connection obligation | Cumulative eligible connection duration D from 1 to 7 hours inside 12:00–19:00; full dispatch and obligation required for enrolled solutions |
| Battery | Initial and terminal energy 36 kWh; hard reserve 20%; charge/discharge efficiency one |
| Recovery charging | Home only after return, at 7 kW and 0.30 CHF/kWh |
| Disabled terms | Other SOC preferences, charged-energy preference, charging/plug inconvenience, travel utility, degradation, and random utility terms set to zero |
| Monetary normalization | Contract payments use +0.3 utility/CHF, extending the published charging-cost marginal utility to a common money coefficient; required compensation is the utility loss divided by 0.3 |

The hard shopping window creates the investigated boundary and is not attributed to J2025. The fixed education start, required participation, route, excluded station/waiting, and duration bounds restrict the published choice space. Equal total travel and driving energy across designed shopping routes are controlled features, not measured facts.

## Scope of supported claims

A/B/C results describe this deterministic diagnostic optimization. A is the local dual-price extrapolation conditional on the reference integer pattern, B reoptimizes continuous variables with that pattern fixed, and C reoptimizes the allowed discrete patterns. Fixed-integer LP duals are not full-MILP shadow prices. A/B/C differences, activity switches, and compensation amounts are model outputs under the added assumptions; they do not establish empirical contract acceptance, population frequencies, or the magnitude of Swiss users' real willingness to accept. The synthetic four-activity hand-check case is separate and its JPY parameters are not derived from Bryan.
