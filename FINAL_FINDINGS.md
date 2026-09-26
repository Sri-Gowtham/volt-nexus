# VoltNexus — Final Validated Findings

VoltNexus is the internal project name for this analysis of **VoltRelay
Energy's** battery-swap network. This file is the single source of truth
for that analysis. Every number below is drawn directly from the executed
notebook
(`notebooks/voltrelay_analysis.ipynb`, 83 cells, 0 errors) and the current
`report/VoltRelay_Analysis_Report.md`. The report, video outline, LinkedIn
post, and README should all trace back to this file — if any of them
disagree with an entry here, the other document is wrong, not this one.

---

## F01 — Network Performance
**Finding:** Completed swaps and revenue grew ~3x over 18 months (3.65M
total completed swaps, ~₹23.3 crore total revenue), moving in near-perfect
lockstep. Contribution margin per swap improved from -₹6.48 (Jan 2024) to
+₹12.43 (Jun 2025). Failure rate spiked twice (mid-2024, mid-2025) with no
meaningful relationship to the growth/margin trend.
**Evidence:** Monthly KPI aggregation (`kpis.network_kpis_monthly`); monthly
co-movement check (`stats.q1_comovement`).
**Effect size / metric:** completed_swaps vs. revenue: r=0.999 (p<0.0001).
failure_rate vs. completed_swaps: r=-0.003 (p=0.99). failure_rate vs.
revenue: r=-0.025 (p=0.92). failure_rate vs. margin: r=-0.119 (p=0.64).
**Statistical status:** Descriptive KPI trend + a simple 18-point Pearson
correlation check, not a hypothesis-test family requiring correction.
**Business interpretation:** Growth and profitability are real and moving
together; failure rate is a separate, recurring operational problem that
scale alone does not resolve.
**Cannot claim:** That failure rate is "independent" of growth in a formal
statistical sense beyond this correlation check, or that this proves
causation in either direction.

---

## F02 — Service Failure Patterns
**Finding:** Failure rate is weakly associated with station, hour-of-day,
season, and vehicle class individually. One specific combination — 3-wheelers,
during summer/monsoon, in evening/night hours — fails at roughly 2x the
network rate.
**Evidence:** Chi-square test of independence x4 splits (`stats.q2_by_derived`);
relative-risk test on the pre-specified interaction segment
(`stats.q2_high_risk_interaction_segment`).
**Effect size / metric:** Cramér's V: hour_bucket=0.0162, season=0.0567,
vehicle_class=0.0649, station_id=0.0697 (all small). Interaction segment:
11.9% failure rate vs. 5.8% rest-of-network, **RR = 2.06 (95% CI 2.02–2.09,
p<0.001)**.
**Statistical status:** All 4 chi-square tests significant even after
Holm-Bonferroni correction (raw and adjusted p-values both ≈0 or
<2×10⁻²¹³). The interaction segment is a single pre-specified test, not
part of a multi-test family.
**Business interpretation:** Service quality issues are broad but shallow
on any single dimension; sharply concentrated in one specific, targetable
rider/time segment.
**Cannot claim:** That any of these factors *cause* failures — these are
observed associations. "2.06x higher failure risk," not "2.06x more
failures caused by."

---

## F03 — Station / Geographic Signals
**Finding:** Station age is associated with higher failure rate. Two other
station attributes (monthly_rent_inr, grid_tariff_inr_kwh) looked
marginally significant on Spearman correlation alone but did not survive
correction and are not treated as findings. A geographic view shows Jaipur
and Delhi NCR running higher failure rates (~8-9%) than Bengaluru (~4-5%).
**Evidence:** Pearson + Spearman correlation across 12 (attribute, outcome)
pairs with both magnitude- and significance-disagreement detection
(`stats.q3_station_correlations`); station-location map (`viz.q3b_station_map`).
**Effect size / metric:** station_age_days vs. failure_rate: Pearson
r=0.40 (raw p=3.2×10⁻⁷, **Holm p=4.0×10⁻⁶**), Spearman r=0.29 (raw
p=3.6×10⁻⁴, **Holm p=0.0043**). monthly_rent_inr and grid_tariff_inr_kwh:
raw Spearman p=0.040/0.006, but **Holm p=0.399/0.068 — not significant**.
**Statistical status:** station_age_days is the only station attribute
that survives Holm correction across all 12 pairs tested as one family.
**Business interpretation:** Station age is the one defensible, evidence-backed
correlate of failure rate among the attributes tested.
**Cannot claim:** That rent or grid tariff drive failure rate (that
apparent signal did not survive correction) or that station age causes
higher failure rates.

---

## F04 — Battery / Equipment Signals
**Finding:** Three specific Kyron manufacturing lots (KY-2407, KY-2408,
KY-2409) degrade ~4-6x faster than every other supplier/lot cohort.
Battery SOH is moderately associated with a delivered-range proxy once the
correct proxy is used, confirmed stable under a sensor-drift sensitivity
check.
**Evidence:** Per-lot degradation-rate ranking (`kpis.battery_degradation`);
two independent range proxies compared (`stats.q4_soh_vs_range_proxy`,
`stats.q4_soh_vs_km_proxy`); SOC/SOH>100% sensitivity check
(`stats.q4_soh_vs_km_proxy_sensitivity`).
**Effect size / metric:** Kyron worst lots: 0.142–0.143 pct-points/day vs.
median 0.021 pct-points/day across other cohorts (**~6.7x**). SOH vs. km
proxy: Pearson r=0.32, Spearman r=0.39 (both p<0.001, n=3.64M). Sensitivity
check: Δr = -0.0003 (Pearson) / -0.0004 (Spearman) after excluding
sensor-drift rows — negligible.
**Statistical status:** Degradation ranking is descriptive; correlation
is a single reported association, confirmed robust to a data-quality
sensitivity check.
**Business interpretation:** A targeted, three-lot equipment issue worth
investigating with the supplier — not a fleet-wide Kyron problem. SOH
relates to delivered range as an **observed association**, not a proven
causal mechanism (the relationship is non-monotonic, suggesting a
battery-cohort effect rather than continuous within-battery decay).
**Cannot claim:** That declining SOH directly *causes* shorter individual
trips — the non-monotonic shape argues against a simple causal story.

---

## F05 — Pricing Economics
**Finding:** The peak/off-peak pricing pilot is associated with an
estimated +₹5.35 per swap difference in the pooled difference-in-differences
analysis, holding independently in both pilot cities. A placebo/pre-trend
check found a small, opposite-signed effect in the pre-period.
**Evidence:** Pooled + per-city DiD (`stats.q5_did`, `stats.q5_did_per_city`);
placebo test (`stats.q5_placebo_test`). Pilot cities/date confirmed from
data (`tariff_code`=PEAK/OFFPEAK first appearing in Bengaluru/Pune,
2024-10-01), not assumed.
**Effect size / metric:** Pooled: +₹5.35/swap (p<0.001). Bengaluru: +₹5.43
(p<0.001). Pune: +₹5.23 (p<0.001). Placebo (pre-period, fake date
2024-06-01): -₹0.28/swap (p<0.001) — ~19x smaller than the real effect and
opposite-signed.
**Statistical status:** Quasi-causal design (DiD); the one place in this
analysis where language is somewhat stronger than "associated with," but
still qualified.
**Business interpretation:** The pricing pilot is the strongest,
most defensible case for a network-wide rollout among the budget options
considered.
**Cannot claim:** That parallel trends holds exactly (the placebo test
shows it holds only approximately) or that this is unconditional proof —
it is a DiD estimate with a disclosed pre-trend caveat, covering only 2 of
6 cities.

---

## F06 — Fleet Partner Economics
**Finding:** The largest fleet partner by revenue is not the most valuable
by margin. Two of the three largest partners by revenue run deeply
negative contribution margin per swap; several smaller partners are
solidly profitable.
**Evidence:** Per-partner margin using the same formula as F01
(`kpis.fleet_partner_value`); discount_pct correlation check.
**Effect size / metric:** FeastFly (largest, ~₹32.7M revenue): +₹0.90/swap.
ZipDrop (2nd largest, ~₹29.0M): -₹9.00/swap. ParcelNest (3rd, ~₹17.1M):
-₹4.71/swap. Smaller partners (DabbaXpress, QuickCart, RideMitra,
UrbanErrand): +₹1.2 to +₹2.9/swap. discount_pct vs. margin: r=-0.40,
**p=0.198, n=12 — not statistically significant.**
**Statistical status:** Margin figures are a deterministic financial
calculation (not a hypothesis test). The discount_pct explanation was
tested and found not significant at n=12.
**Business interpretation:** Several of VoltRelay's biggest fleet
relationships by volume are quietly loss-making per swap and warrant a
contract-level review before any exclusive long-term agreement.
**Cannot claim:** That contract discount percentage is *proven* to explain
the margin differences — that specific correlation was not significant.

---

## F07 — Retention / Churn Findings
**Finding:** No individual factor in the binary "did this rider return
within 30 days" model survives correction for multiple comparisons. A
reframed, properly-powered outcome (swaps in the first 30 days) shows real,
corrected-significant associations between vehicle class / signup channel
and how actively an engaged rider uses the service.
**Evidence:** Binary logistic regression with Holm correction
(`stats.q6_logistic_regression`); predictive-quality validation
(`stats.q6_logistic_regression_validation`); negative binomial activity
model with formally validated overdispersion
(`stats.q6_negative_binomial_activity`, `stats.q6_overdispersion_check`).
**Effect size / metric:** Binary model: `first_queue_wait_sec` raw
p=0.0105 but **Holm p=0.115 — does NOT survive correction**; no other
coefficient survives either. Predictive check: ROC-AUC ≈0.49–0.54 (chance
level), PR-AUC only marginally above base rate. Activity model:
variance/mean ratio=3.68, NB AIC=149,736 vs. Poisson AIC=174,582, LR
test p<0.001 (NB formally justified). 3W vehicle class: IRR=0.70 (Holm
p<0.001). Field-agent signup: IRR=1.18 (Holm p<0.001). Partner-onboarding
signup: IRR=1.25 (Holm p<0.001).
**Statistical status:** The original "queue wait predicts churn" claim is
**withdrawn**, not softened — it does not survive Holm correction. This is
reported as a positive analytical-integrity signal (a caught false
positive), not hidden.
**Business interpretation:** This dataset does not support a confident
claim about what drives full churn. What it does support: vehicle class
and signup channel are associated with how actively an engaged rider
keeps using the service.
**MUST NOT CLAIM (verified violations found and required fixing across the
repository):**
- Queue wait causes churn
- Queue wait drives rider disappearance
- Reducing queue wait will necessarily improve retention
- First queue wait is a proven churn driver
- Any binary-model coefficient is a reliable churn predictor

---

## F08 — O2: Expansion Wave / Equipment Analysis
**Finding:** Wave 2 stations were deployed in a markedly different, harder
location mix than Wave 1, while maintaining similar observed failure
rates. A joint regression testing whether newer equipment "offset" the
harder siting came back **inconclusive**.
**Evidence:** Descriptive siting-difficulty comparison
(`kpis.expansion_wave_targeting`); joint regression
(`stats.o2_joint_regression`).
**Effect size / metric:** Wave1 "easy" residential sites: 43.3%; Wave2:
6.7%. Failure rate: Wave1 4.91%, Wave2 4.96% (essentially flat). Joint
regression (`failure_rate ~ location_type + charger_generation +
is_contested`, n=60): **F=0.563, p=0.782** (not significant);
charger_generation specifically: **p=0.673** (not significant); adjusted
R²=-0.055.
**Statistical status:** Inconclusive / insufficient evidence — the model
as a whole and the equipment term specifically are not significant at this
sample size.
**Business interpretation:** Wave 2 targeted harder sites without a
performance penalty; this is consistent with, but does not prove, an
equipment-related explanation.
**Cannot claim:** That newer equipment generation was proven to cause or
offset the harder siting. This is explicitly not established.

---

## F09 — O3: Partner Economics Deep-Dive
See F06 for the primary finding. The discount_pct correlation (r=-0.40,
p=0.198, n=12) is explicitly **not statistically significant** and must
not be presented as an explanation for partner margin differences — only
the margin differences themselves are the confirmed finding.

---

## F10 — Key Limitations
- This is observational analysis; causal language is used only for F05
  (Q5 DiD), and even there it carries a disclosed placebo caveat.
- CSAT (`csat_score`) is missing not-at-random; its coverage varies
  11%-44% by resolution-time bucket (confirmed directly, not assumed) and
  it is not used as a primary outcome anywhere in this analysis.
- STN-TST internal test stations are now consistently excluded across
  every KPI and statistical function (previously inconsistent between
  Q1/Q2 and Q3/O2 — fixed). Excluded volume: ~1.6% of attempts, ~1.7% of
  revenue — small but not negligible; headline Q1/Q2 figures in this file
  and the report reflect production stations only (STN-TST excluded).
- All grouped hypothesis-test families (Q2's 4 splits, Q3's 12 correlation
  pairs, Q6's and Q6b's 10 coefficients each) are Holm-corrected, with raw
  p-values preserved alongside adjusted ones.
- O2 (n=60) and O3's discount check (n=12) are both explicitly
  underpowered and inconclusive — reported as such, not as confident
  findings.
- The near-duplicate swap-event dedup rule (120-second window,
  rider+station+battery) found **zero** candidate duplicates when run
  against the actual data. This was independently re-verified during this
  consistency pass with a direct query against the raw CSV, checked
  separately by `sync_mode` (591,114 `offline_batch` rows, 3,285,899
  `realtime` rows) — genuinely zero rows anywhere in the dataset match the
  near-duplicate pattern the rule is designed to catch. The rule itself is
  logically sound and correctly implemented; this specific dataset simply
  does not contain near-duplicates of this kind. Not an artifact of a
  broken rule.
