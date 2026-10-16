"""Build inspectable scientific figures and Japanese interpretation from saved rows."""
from __future__ import annotations
import os
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/activity-v2g-theory-matplotlib")
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

COLORS = ["#253f58", "#b76530", "#277b90", "#a1842e", "#8a5978"]


def load_csv(path):
    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            for k, v in row.items():
                if v == "":
                    row[k] = None
                elif v in ("True", "False"):
                    row[k] = v == "True"
                else:
                    try:
                        row[k] = float(v)
                    except ValueError:
                        pass
            rows.append(row)
    return rows


def select(rows, **conditions):
    return sorted([r for r in rows if all(
        abs(r[k]-v) < 1e-9 if isinstance(v, (float, int)) else r[k] == v
        for k, v in conditions.items())], key=lambda r: r["D_h"])


def one(rows, **conditions):
    found = select(rows, **conditions)
    assert len(found) == 1, (conditions, len(found))
    return found[0]


def val(x):
    return "実行不能" if x is None else f"{x:,.2f}"


def save(fig, folder, name):
    for ext in ("png", "pdf"):
        fig.savefig(folder/f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def curves(rows, folder):
    probabilities = [0, .01, .25, .75, 1]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True, sharey=True, layout="constrained")
    for i, mode in enumerate(("hard", "soft")):
        for j, access in enumerate((0, 1)):
            ax = axes[i, j]
            styles = ["-", "--", "-.", ":", (0, (3, 1, 1, 1))]
            for p, color, style in zip(probabilities, COLORS, styles):
                rs = select(rows, fulfillment=mode, appointment_v2g_access=access, p_cancel=p)
                # Hard activity loss is a jump; do not draw a continuous bridge
                # between the last feasible gym point and the first no-gym point.
                breaks = [0]+[k for k in range(1, len(rs)) if mode == "hard" and rs[k]["C_gym"] != rs[k-1]["C_gym"]]+[len(rs)]
                for segment, (start, end) in enumerate(zip(breaks, breaks[1:])):
                    part = rs[start:end]
                    ax.plot([r["D_h"] for r in part], [r["C_compensation"] for r in part],
                            color=color, ls=style, lw=1.7, label=f"p = {p:g}" if segment == 0 else None)
            ax.axvline(1.5, color="#aeb6bd", ls=":", lw=1)
            if access:
                ax.axvline(2, color="#aeb6bd", ls=":", lw=1)
            ax.set_title(f"{mode.capitalize()} fulfillment | appointment V2G access = {access}", loc="left", fontsize=11)
            ax.grid(axis="y", alpha=.18)
            ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            ax.set_xlim(1, 4)
            ax.set_ylim(0, 7200)
            if i:
                ax.set_xlabel("Required connection D (h)")
            if j == 0:
                ax.set_ylabel("Minimum fixed compensation (JPY-equivalent)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    axes[0, 0].legend(handles, labels, loc="upper left", ncol=2, frameon=False, fontsize=9)
    fig.suptitle("Cancellation effects depend on connection access and fulfillment terms", fontsize=14)
    fig.supxlabel("Authored one-person instance; exact supported scenarios; fixed 6 kWh delivered in every joined scenario.", fontsize=9, color="#53606b")
    save(fig, folder, "cancellation_curves")


def decomposition(rows, folder):
    rs = select(rows, p_cancel=.25, appointment_v2g_access=0, fulfillment="soft")
    x = [r["D_h"] for r in rs]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.8), sharex=True, layout="constrained")
    for field, label, color, style in [("A_compensation", "A  reference dual extrapolation", COLORS[1], ":"),
                                      ("B_compensation", "B  gym choice fixed", COLORS[3], "--"),
                                      ("C_compensation", "C  participation reoptimized", COLORS[2], "-")]:
        axes[0].plot(x, [r[field] for r in rs], color=color, ls=style, lw=2, label=label)
    for field, label, color, style in [
        ("continuous_extrapolation_error", "B - A: continuous-face extrapolation error", COLORS[1], "--"),
        ("integer_reselection_value", "B - C: value of integer reselection", COLORS[2], "-"),
        ("C_minus_A", "C - A = (B - A) - (B - C)", COLORS[0], ":")]:
        axes[1].plot(x, [r[field] for r in rs], color=color, ls=style, lw=1.8, label=label)
    for ax in axes:
        ax.axvline(1.5, color="#aeb6bd", ls=":", lw=1)
        ax.axhline(0, color="#7c8790", lw=.7)
        ax.grid(axis="y", alpha=.18)
        ax.legend(frameon=False, loc="upper left", fontsize=9)
        ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.set_ylabel("JPY-equivalent")
    axes[1].set_xlabel("Required connection D (h)")
    axes[0].set_ylim(bottom=0)
    fig.suptitle("Separate continuous constraint changes from discrete activity adaptation", fontsize=13)
    fig.supxlabel("p = 0.25; appointment has no V2G access; soft shortfall settlement; nominal and realized plans share one gym choice.", fontsize=9, color="#53606b")
    save(fig, folder, "error_decomposition")


def probability(rows, folder):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), layout="constrained")
    for mode, color, style in [("hard", COLORS[0], "--"), ("soft", COLORS[2], "-")]:
        rs = sorted(select(rows, D_h=1.5, appointment_v2g_access=1, fulfillment=mode), key=lambda r: r["p_cancel"])
        x = [r["p_cancel"] for r in rs]
        if mode == "hard":
            positive = [r for r in rs if r["p_cancel"] > 0]
            axes[0].plot([r["p_cancel"] for r in positive], [r["C_compensation"] for r in positive],
                         marker="o", ms=3, color=color, ls=style, label=mode)
            axes[0].scatter([0], [rs[0]["C_compensation"]], color=color, s=22, zorder=4)
            axes[0].scatter([0], [1104], facecolor="white", edgecolor=color, s=35, zorder=4)
            axes[1].plot([r["p_cancel"] for r in positive], [r["C_work_departure_h"] for r in positive],
                         marker="o", ms=3, color=color, ls=style, label=mode)
            axes[1].scatter([0], [17], color=color, s=22, zorder=4)
            axes[1].scatter([0], [17.5], facecolor="white", edgecolor=color, s=35, zorder=4)
        else:
            axes[0].plot(x, [r["C_compensation"] for r in rs], marker="o", ms=3, color=color, ls=style, label=mode)
            axes[1].scatter(x, [r["C_work_departure_h"] for r in rs], s=15, color=color, label=mode)
            axes[1].plot([0, 6/11], [17, 17], color=color, lw=1.5)
            axes[1].plot([6/11, 1], [17.5, 17.5], color=color, lw=1.5)
            axes[1].plot([6/11, 6/11], [17, 17.5], color="#a1842e", lw=1.5, ls=":")
    threshold = 6/11
    for ax in axes:
        ax.axvline(threshold, color="#a1842e", lw=1, ls=":")
        ax.set_xlim(-.02, 1.02)
        ax.set_xlabel("Appointment cancellation probability p")
        ax.grid(axis="y", alpha=.18)
        ax.legend(frameon=False)
    axes[0].set_ylabel("Minimum compensation (JPY-equivalent)")
    axes[0].set_ylim(0, 1250)
    axes[0].annotate("hard: open point is right limit 1104", xy=(0, 1104), xytext=(.18, 1160),
                     fontsize=9, arrowprops=dict(arrowstyle="-", color="#6e7780"))
    axes[1].set_yticks([17, 17.25, 17.5], ["17:00", "17:15", "17:30"])
    axes[1].set_ylim(16.96, 17.54)
    axes[1].set_ylabel("Common planned work departure")
    axes[1].text(.58, 17.08, "soft threshold p = 6/11\nboth plans optimal at equality", fontsize=9)
    fig.suptitle("Risk-neutral expected settlement and all-support fulfillment are different mechanisms", fontsize=12)
    fig.supxlabel("D = 1.5 h; appointment has V2G access; all-activities nominal plan remains feasible at p = 1.", fontsize=9, color="#53606b")
    save(fig, folder, "probability_boundary")


def soc(rows, folder):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7), layout="constrained")
    for access, color in [(0, COLORS[0]), (1, COLORS[2])]:
        rs = sorted(select(rows, D_h=1.25, p_cancel=.25, fulfillment="hard", appointment_v2g_access=access), key=lambda r: r["guarantee_kWh"])
        for ax, field in zip(axes, ("C_compensation", "C_precharge_kWh")):
            ax.plot([r["guarantee_kWh"] for r in rs], [np.nan if r[field] is None else r[field] for r in rs],
                    marker="o", ms=4, color=color, ls="-" if access == 0 else "--",
                    markerfacecolor=color if access == 0 else "white", label=f"appointment access = {access}")
            infeasible = [r["guarantee_kWh"] for r in rs if r["C_status"] == 2]
            # x positions are true guarantee values; crosses are status markers,
            # not invented cost or charging amounts.
            ax.scatter(infeasible, [1.02]*len(infeasible), transform=ax.get_xaxis_transform(),
                       marker="x", color=color, s=25, clip_on=False)
    for ax in axes:
        ax.set_xlim(24, 35.2)
        ax.axvline(27.75, color="#abb4bb", lw=.8, ls=":")
        ax.axvline(28, color="#abb4bb", lw=.8, ls=":")
        ax.set_xlabel("Contract battery guarantee (kWh)")
        ax.grid(axis="y", alpha=.18)
        ax.legend(frameon=False, fontsize=9, loc="upper left")
    axes[0].set_ylabel("Minimum compensation (JPY-equivalent)")
    axes[0].set_ylim(0, 1000)
    axes[1].set_ylabel("Common pre-service charging (kWh)")
    axes[1].set_ylim(0, 6.5)
    fig.suptitle("SOC guarantees change precharging cost, then become infeasible", fontsize=13)
    fig.supxlabel("D = 1.25 h; p = 0.25; hard fulfillment. Crosses above panels denote infeasible guarantees, not numerical costs.", fontsize=9, color="#53606b")
    save(fig, folder, "soc_boundary")


def schedule_figure(output, folder):
    wanted = []
    with gzip.open(output/"cancellation_01/solver_records.jsonl.gz", "rt") as f:
        for line in f:
            record = json.loads(line)
            if record["kind"] == "case":
                z = record["case"]
                if z["D_h"] == 1.5 and z["p_cancel"] == .25 and z["appointment_v2g_access"] == 1:
                    wanted.append(record)
    assert len(wanted) == 2
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), height_ratios=[1.7, 1], layout="constrained")
    colors = dict(home="#e4e8eb", travel="#aab5bd", work="#d7bc8c", appointment="#829aa7", gym="#348897")
    labels = []
    y = 3
    for record in sorted(wanted, key=lambda r: r["case"]["fulfillment"]):
        mode = record["case"]["fulfillment"]
        for state in record["C"]["audit"]["states"]:
            labels.append((y, f"{mode} | " + ("appointment occurs" if state["xi"] else "appointment cancelled")))
            for s in state["segments"]:
                axes[0].barh(y, s["end"]-s["start"], left=s["start"], height=.62,
                             color=colors[s["activity"]], edgecolor="white", lw=.6)
                if s["activity"] in ("gym", "appointment"):
                    axes[0].text((s["start"]+s["end"])/2, y, "Gym" if s["activity"] == "gym" else "Appt.",
                                 ha="center", va="center", fontsize=8, color="white")
            axes[0].plot([16, 17], [y+.24]*2, color=COLORS[1], lw=2.5)
            text = f"connection {state['connection_h']:.2f} h | shortfall {state['shortfall_h']:.2f} h"
            axes[0].text(20.5, y, text, va="center", fontsize=8)
            pts = np.array(state["soc_points"])
            axes[1].plot(pts[:, 0], pts[:, 1], lw=1.5,
                         ls="-" if state["xi"] else "--", color=COLORS[0] if mode == "hard" else COLORS[2],
                         label=f"{mode}, xi={state['xi']}")
            y -= 1
    axes[0].set_yticks([z[0] for z in labels], [z[1] for z in labels], fontsize=9)
    axes[0].set_xlim(15, 24)
    axes[0].set_xticks([15,16,17,18,19,20,21,22,23,24], [f"{t:02}:00" for t in range(15,25)])
    axes[1].set_xlim(15, 24)
    axes[1].set_ylim(10, 39)
    axes[1].axhline(12, color="#87939b", ls=":", lw=1)
    axes[1].set_ylabel("Battery energy (kWh)")
    axes[1].set_xlabel("Time (h)")
    axes[1].legend(ncol=2, frameon=False, fontsize=8)
    axes[1].grid(axis="y", alpha=.18)
    fig.suptitle("Realized schedules preserve one common pre-realization plan", fontsize=13)
    fig.supxlabel("Orange line: fixed 6 kWh discharge, 16:00--17:00. Common work duration and gym participation are not reselected after cancellation.", fontsize=9, color="#53606b")
    save(fig, folder, "schedules_soc")


def build_report(output):
    output = Path(output)
    manifest = json.loads((output/"manifest.json").read_text())
    assert manifest["status"] == "PASS", "withhold report when execution gate fails"
    rows = load_csv(output/"cancellation_01/results.csv")
    soc_rows = load_csv(output/"soc_01/results.csv")
    figdir = output/"figures"
    figdir.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    curves(rows, figdir)
    decomposition(rows, figdir)
    probability(rows, figdir)
    soc(soc_rows, figdir)
    schedule_figure(output, figdir)
    samples = []
    for p in (0, .01, .25, .75, 1):
        for access in (0, 1):
            for mode in ("hard", "soft"):
                r = one(rows, D_h=1.5, p_cancel=p, appointment_v2g_access=access, fulfillment=mode)
                samples.append(f"| {p:g} | {access} | {mode} | {val(r['C_compensation'])} | {r['C_work_departure_h']:.2f} | {r['expected_shortfall_h']:.4f} | {r['fulfillment_probability']:.2f} |")
    critical = 6/11
    exact = one(rows, D_h=1.5, p_cancel=critical, appointment_v2g_access=1, fulfillment="soft")
    just_below = one(rows, D_h=1.5, p_cancel=critical-.001, appointment_v2g_access=1, fulfillment="soft")
    just_above = one(rows, D_h=1.5, p_cancel=critical+.001, appointment_v2g_access=1, fulfillment="soft")
    hard_zero = one(rows, D_h=1.5, p_cancel=0, appointment_v2g_access=1, fulfillment="hard")
    hard_small = one(rows, D_h=1.5, p_cancel=.01, appointment_v2g_access=1, fulfillment="hard")
    mismatch = {}
    for reward in (500,1000,2000,3000,5000,7000):
        eligible = [r for r in rows if r[f"decision_mismatch_R{reward}"] is not None]
        mismatch[reward] = dict(comparable_conditions=len(eligible),
                                mismatched_conditions=sum(r[f"decision_mismatch_R{reward}"] for r in eligible))
    decomp = [r for r in rows if r["decomposition_error"] is not None]
    stats = dict(designed_conditions=manifest["designed_conditions"],
                 maximum_C_minus_A=max(r["C_minus_A"] for r in decomp),
                 minimum_C_minus_A=min(r["C_minus_A"] for r in decomp),
                 maximum_continuous_error=max(r["continuous_extrapolation_error"] for r in decomp),
                 maximum_integer_reselection_value=max(r["integer_reselection_value"] for r in decomp),
                 maximum_decomposition_residual=max(r["decomposition_error"] for r in decomp),
                 reward_decision_comparisons=mismatch, critical_probability=critical,
                 critical_compensation=exact["C_compensation"],
                 SOC_infeasible_conditions=sum(r["C_status"] == 2 for r in soc_rows))
    (output/"summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2)+"\n")
    gates = []
    for claim in ("C1", "C2", "C3", "C4"):
        for gate in ("G0_OBJECT_VALIDITY", "G1_EXECUTION_CORRECTNESS", "G2_INTERNAL_FAIRNESS", "G3_QUANTIFIED_EFFECT", "G4_MECHANISM", "G5_BOUNDARY_FAILURE", "G6_EXTERNAL_VALIDITY", "G7_CONDITIONAL_DECISION"):
            external = gate == "G6_EXTERNAL_VALIDITY"
            gates.append(dict(claim=claim, gate=gate,
                              applicability="OPTIONAL" if external else "REQUIRED",
                              status="UNOBSERVED" if external else "PASS",
                              evidence="No population or acceptance observations" if external else "config.json; results.csv; solver_records.jsonl.gz; verification.json",
                              scope="No empirical/predictive population claim" if external else "Authored exact-scenario mechanism instance",
                              remediation="Fukushima activity data and observed acceptance/held-out validation" if external else "none"))
    (output/"claim_gate_audit.json").write_text(json.dumps(gates, ensure_ascii=False, indent=2)+"\n")
    legacy = ""
    if manifest["legacy_reruns"]:
        bryan = json.loads((output/"bryan_continuous_01/verification.json").read_text())
        gym = json.loads((output/"activity_drop_01/independent_checks.json").read_text())
        assert bryan["status"] == "PASS" and gym["passed"]
        legacy = """## 1. 既存例の再現：連続的な場所変更と不連続な活動断念

最新の既定ブランチに保存されていたBryanと合成例を、新しい出力先で再実行した。BryanはWang et al. (2025)の公開入力にV2G・硬い窓等を加えた縮約例で、原論文全体や実測日誌の再現ではない。[出典・追加仮定](../../../experiments/minimal_contract/source_provenance.md)を参照。

- Bryan：参照D=4hの影価格は0。D=4.05hから固定場所の遅れが生じ、約4.08289hで買物場所を変更。補償額は連続。D=4.5hでA=2.10、B=3.70695、C=2.21745 CHF。固定場所Bは4.55hを超えると実行不能。
- 合成例：D=1.5hを超えると任意運動を断念。境界の補償増加は2700円相当。D=1.75hではA=1530、C=4080で、Bは実行不能。

![Bryanの連続的な切替](bryan_continuous_01/compensation.png)

![合成例の活動断念](activity_drop_01/compensation_ABC.png)

同じ「離散選択あり」でも、連続な切替と不連続な断念の双方を保持した。両例の完全な設定、求解状態、独立照合、SOCは各サブフォルダに保存している。
"""
    text = f"""# 理論的基礎づけに基づく契約数値実験（2026-10-16）

**新しい取消・SOCの{manifest['designed_conditions']:,}条件を実行し、全条件を別定式化LPと解析計算で照合した。** 判定はモデル内の機会費用・受諾条件であり、実際の日本の契約受諾を推定した結果ではない。既存の掲載人物・合成例の再実行を含む4実験を保存した。

## 比較する量

加入と非加入をそれぞれ最適化し、追加報酬を除く期待費用差を符号付き機会費用、その正の部分を必要固定補償とした。新モデルの金銭限界効用は1、単位は設計した円相当。BryanのCHFとは集計しない。

Aは参照D=1.25hの固定整数LPの双対を外挿する。Bはその運動参加を固定して連続変数だけを再最適化。Cは運動参加も含むMILPを解く。Bが有限の条件では、`C-A=(B-A)-(B-C)`を検算した。最大恒等式残差は{stats['maximum_decomposition_residual']:.3g}。Aは活動計画ではなく価格予測である。

{legacy}

## 2. 取消と契約履行：同じ活動・同じ6kWhでも必要補償が変わる

新モデルは勤務→予定1件→任意運動→自宅の共通計画を作る。予定が取消された場合はその活動を削除し、残存所要時間・順序・勤務終了・接続計画を維持する。同じ活動場所でV2G設備アクセスだけを変えた。勤務終了後の予定の取消は移動と滞在を短縮するが、設備がある場合は接続0.5時間も失わせる。

全加入状態で16–17時に6kWhを実際に放電する。累積接続義務は別にD時間で、hardは全支持状態で不足禁止、softは不足1時間あたり2400の有限精算である。期待供給量と物理的SOC条件を揃え、契約の可用性義務と実際の供給を混同していない。

![取消確率・アクセス・義務の比較](figures/cancellation_curves.png)

D=1.5hの測定値は以下。履行確率は接続D時間の達成確率で、6kWhの供給確率とは異なる。

| 取消確率p | 予定場所の設備 | 仕様 | 必要補償（円相当） | 共通勤務終了（時） | 期待不足（h） | 履行確率 |
|---:|---:|---|---:|---:|---:|---:|
{chr(10).join(samples)}

アクセスあり・hardでは、p=0の必要補償{hard_zero['C_compensation']:.2f}に対し、p=0.01では{hard_small['C_compensation']:.2f}になった。取消状態を完全履行の支持集合に含めると、共通勤務を17:30まで延ばす必要がある。これは小さな確率に対するリスク回避の推定ではなく、全支持履行制約による境界である。

アクセスあり・soft・D=1.5hでは、勤務延長の限界費用`1800-900p`と不足精算の期待限界額`2400p`がp=6/11={critical:.6f}で一致する。直前p={critical-.001:.6f}の勤務終了は{just_below['C_work_departure_h']:.2f}時、直後p={critical+.001:.6f}では{just_above['C_work_departure_h']:.2f}時だった。等号では複数の最適な勤務終了があり、一つのソルバー選択を一意な予測としない。境界の必要補償は{exact['C_compensation']:.2f}。この例の補償額は取消確率に単調増加しない。

![確率境界](figures/probability_boundary.png)

![活動とSOCの実現状態](figures/schedules_soc.png)

## 3. 局所近似の誤差と活動再選択を分ける

![A/B/Cと誤差分解](figures/error_decomposition.png)

同じ活動を維持しても、接続不足の精算や時刻の制約面が変わればBとAは乖離する。Cは活動を断念・維持する選択も比較するためB以下の期待費用になる。Bが実行不能な条件で、この二つの有限値の差を作っていない。有限Bの条件で観測された最大の連続外挿誤差B-Aは{stats['maximum_continuous_error']:.2f}、最大の整数再選択価値B-Cは{stats['maximum_integer_reselection_value']:.2f}だった。

所与の固定報酬での受諾は、同じCの必要補償から判定できる。例えば報酬1000では、Aの比較が可能な{mismatch[1000]['comparable_conditions']}条件中、{mismatch[1000]['mismatched_conditions']}条件でAとCの判定が異なった。これは事前に指定した条件格子上の件数であり、母集団の誤判定率ではない。全報酬水準と条件別の判定はCSVと`summary.json`に残した。

## 4. SOC保証：限界費用の発生と物理的な実行不能

![SOC保証の境界](figures/soc_boundary.png)

勤務到着時SOCは34kWh、6kWh放電後は事前充電なしで28kWhとなる。予定場所にも保証が適用される場合は、移動消費0.25kWhによって27.75kWhから事前充電が必要になる。事前の勤務内充電は家庭より30円相当/kWh高いため、実行可能域で保証1kWhの増加につき必要補償が30円相当増える。

予定場所にも設備がある場合、保証33.75kWh超は事前充電6kWh上限で実行不能。設備なしの場合、34kWhまでは実行可能で、それを超えると到着時保証にも違反する。SOC実験の{stats['SOC_infeasible_conditions']}条件の実行不能を保持した。これは高い有限補償では解消できない。

この設計では、実行可能域のSOC保証の費用は時間条件に加算される形であり、活動取消との非加法的効果を常に生むわけではなかった。この帰無的な範囲も保持する。SOCを後から描いただけでなく、事前充電と実行可能性を決める制約として求解し、全イベント残量を独立に再計算した。

## 検証と主張の範囲

各実験の`verification.json`はPASS。新モデルの全条件を、二つの独立な経路LPと、費用の折れ点を列挙する解析計算で確認した。参照LPの双対は左右0.0001時間の差分に照合した。全シナリオの活動時刻・固定計画・SOC・日末残量・供給・精算・目的値を再計算した。MIPは相対ギャップ0、1スレッド、1求解10秒上限で実行した。タイムアウトを最適値と扱わない。

この結果が支持するのは、指定したモデルでの、局所価格の成立域、活動変更・取消・SOC保証による境界と受諾判定の差である。全原稿モデル、未知の緊急活動や事後解除権のオプション価値、実際の補償額、福島の母集団への外的妥当性はUNOBSERVED。原稿本文・科学的主張台帳は変更していない。共有知識IDの適用はない。

- [全体設定](settings.json) / [環境・版・ソースハッシュ](environment.json) / [集計](summary.json)
- [取消の全条件CSV](cancellation_01/results.csv) / [検証](cancellation_01/verification.json) / [原始記録](cancellation_01/solver_records.jsonl.gz)
- [SOCの全条件CSV](soc_01/results.csv) / [検証](soc_01/verification.json) / [原始記録](soc_01/solver_records.jsonl.gz)
- [主張と検証条件の監査](claim_gate_audit.json)

各サブ実験に設定・原始結果・ソース・overview・discussionを保存した。図はPNGとPDFの両方を`figures/`に保存している。
"""
    (output/"report_ja.md").write_text(text)
    (output/"overview.md").write_text("# Study overview\n\nFour experiments, preserved prior runs, exact-scenario model comparisons.\n\nSee settings.json, environment.json and report_ja.md.\n")
    (output/"discussion.md").write_text("# Study discussion\n\nObserved results, mechanisms, null effects, infeasible cases and external-validity limits are documented in report_ja.md.\n")
    presentation = output/"presentation"
    presentation.mkdir(exist_ok=True)
    (presentation/"report.py").write_bytes(Path(__file__).read_bytes())
    hashes = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(figdir.iterdir()) if p.suffix in (".png", ".pdf")}
    hashes["presentation/report.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/"figure_manifest.json").write_text(json.dumps(hashes, indent=2)+"\n")
    print(f"Report and figures saved: {output/'report_ja.md'}", flush=True)


if __name__ == "__main__":
    build_report(Path(sys.argv[1]).resolve())
