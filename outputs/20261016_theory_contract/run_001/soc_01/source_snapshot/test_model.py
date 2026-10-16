"""Scientific parity tests, not snapshots of the implementation."""
import unittest
from model import TOL, analytical_oracle, independent_lp, solve


def case(**overrides):
    result = dict(D_h=1.25, p_cancel=.25, appointment_v2g_access=0,
                  guarantee_kWh=12, fulfillment="hard")
    result.update(overrides)
    return result


class ModelParity(unittest.TestCase):
    def specification(self, **overrides):
        z = case()
        z.update(overrides)
        return z

    def test_three_formulations_agree(self):
        designs = [self.specification(D_h=d, p_cancel=p, appointment_v2g_access=a,
                                     guarantee_kWh=f, fulfillment=k)
                   for d, p, a, f, k in [(1.25, .25, 0, 12, "hard"),
                    (1.25, .25, 1, 12, "soft"), (1.75, .25, 0, 12, "hard"),
                    (3.9, .75, 1, 29, "soft"), (1.25, 0, 1, 34, "soft"),
                    (1.25, .25, 0, 34.25, "hard"), (3.5, 1, 0, 30, "soft")]]
        for z in designs:
            for joined in (False, True):
                with self.subTest(case=z, joined=joined):
                    full = solve(z, joined)
                    routes = [independent_lp(z, joined, g) for g in (0, 1)]
                    oracle = analytical_oracle(z, joined)
                    feasible = [r["cost"] for r in routes if r["status"] == 0]
                    self.assertEqual(full["status"], 0 if feasible else 2)
                    self.assertEqual(full["status"], oracle["status"])
                    if feasible:
                        self.assertAlmostEqual(full["cost"], min(feasible), places=7)
                        self.assertAlmostEqual(full["cost"], oracle["cost"], places=7)
                        self.assertTrue(full["audit"]["passed"])

    def test_local_dual_sign_and_money_conversion(self):
        z = self.specification()
        ref = solve(z)
        fixed = round(ref["vector"]["planned_gym"])
        lp = solve(z, fixed_g=fixed)
        eps = 1e-4
        left = solve({**z, "D_h": z["D_h"]-eps}, fixed_g=fixed)
        right = solve({**z, "D_h": z["D_h"]+eps}, fixed_g=fixed)
        finite = (right["cost"]-left["cost"])/(2*eps)
        self.assertAlmostEqual(finite, lp["d_cost_d_D"], places=4)
        # For this face: work 1200 + 600(1-p) - 300p = 1575.
        self.assertAlmostEqual(lp["d_cost_d_D"], 1575, places=7)

    def test_optional_activity_disappears_but_joining_stays_feasible(self):
        left = solve(self.specification(D_h=1.5))
        right = solve(self.specification(D_h=1.5+1e-4))
        self.assertEqual(round(left["vector"]["planned_gym"]), 1)
        self.assertEqual(round(right["vector"]["planned_gym"]), 0)
        fixed = solve(self.specification(D_h=1.5+1e-4), fixed_g=1)
        self.assertEqual(fixed["status"], 2)
        # Left activity net value at w=17.5 is 3000-.75*300-.25*75.
        jump = right["cost"]-left["cost"]-1200*1e-4
        self.assertAlmostEqual(jump, 2756.25, places=6)

    def test_SOC_marginal_and_infeasibility(self):
        z = self.specification(guarantee_kWh=29)
        low = solve(z)
        high = solve({**z, "guarantee_kWh": 30})
        self.assertAlmostEqual(high["cost"]-low["cost"], 30, places=7)
        self.assertAlmostEqual(low["vector"]["precharge_kWh"], 1, places=7)
        self.assertEqual(solve({**z, "guarantee_kWh": 34.25})["status"], 2)

    def test_nominal_plan_preserved_at_probability_one(self):
        z = self.specification(D_h=1.75, p_cancel=1)
        # Although realized cancellation frees time, the all-activities nominal
        # plan still imposes w<=17.5 for gym, and cannot be silently discarded.
        self.assertEqual(round(solve(z)["vector"]["planned_gym"]), 0)

    def test_information_and_energy_shared_across_states(self):
        z = self.specification(appointment_v2g_access=1, fulfillment="soft", guarantee_kWh=30)
        r = solve(z)
        states = r["audit"]["states"]
        self.assertEqual(len({s["work_departure_h"] for s in states}), 1)
        self.assertEqual(len({s["precharge_kWh"] for s in states}), 1)
        self.assertEqual(len({s["gym"] for s in states}), 1)
        for state in states:
            self.assertEqual(state["delivered_kWh"], 6)
            self.assertAlmostEqual(state["soc_points"][-1][1], 36)


if __name__ == "__main__":
    unittest.main()
