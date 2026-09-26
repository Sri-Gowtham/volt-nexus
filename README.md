# VoltNexus

### VoltNexus — EV Battery-Swapping Network Intelligence
*Connecting the signals behind EV battery-swapping performance.*

Data Analytics Hackathon 2026 | Gradient Learnings

---

## 1. Problem

VoltRelay Energy runs a battery-swapping network for electric 2- and
3-wheelers across six Indian cities. Over 18 months (Jan 2024–Jun 2025),
completed swaps and revenue grew substantially, but service failures rose
faster, new-rider retention looked flat at a worryingly narrow margin, and
per-swap profitability was under scrutiny. Over the same period VoltRelay
expanded stations in two waves, changed base pricing, piloted peak/off-peak
pricing in two cities, onboarded a new battery supplier, and renegotiated
its largest fleet contract.

## 2. Objective

Investigate what is actually driving service quality, retention, and
margin outcomes — using evidence, not assumptions. This is an open,
observational analytics exercise: there is no ground-truth answer key, no
target/label to predict, and no machine-learning model is built or
expected. Every claim is checked against the evidence that actually
supports it, with effect sizes reported alongside p-values and causal
language reserved for the one place a quasi-causal design earns it.

## 3. Dataset

Eight source CSVs in `data/raw/` (~837MB combined): `swap_events.csv`
(3.87M rows), `station_hourly_status.csv` (1.49M rows), `riders.csv`,
`batteries.csv`, `support_tickets.csv`, `stations.csv`,
`city_daily_context.csv`, `fleet_partners.csv`. Cleaned outputs are written
to `data/processed/*.parquet`.

## 4. Six Analytical Questions

| # | Question |
|---|---|
| Q1 | Network performance over time |
| Q2 [hero] | Service failures and customer experience |
| Q3 | Station and geographic patterns |
| Q4 | Battery and equipment performance |
| Q5 [hero] | Pricing and partner economics |
| Q6 [hero] | Retention root cause |

Plus five optional deep-dives, all attempted: **O1** budget decision, **O2**
expansion-wave targeting, **O3** fleet partner value, **O4** support-ticket
text signal, **O5** anomalies.

## 5. Analytical Methodology

Method is matched to each question rather than reaching for whatever looks
most advanced:

- **Q1** — monthly KPI trends, validated with a simple co-movement
  correlation check (not a time-series model).
- **Q2** — chi-square + Cramér's V across categorical splits, plus a
  targeted relative-risk check on one pre-specified high-risk segment.
- **Q3** — Pearson + Spearman correlation, checked for both magnitude and
  significance disagreement.
- **Q4** — two independent range proxies compared, plus a per-cohort
  degradation ranking.
- **Q5** — difference-in-differences (pooled + per-city + placebo
  pre-trend check) for the pricing pilot.
- **Q6** — logistic regression (binary retention) plus a negative binomial
  regression (30-day activity count) with a formally validated
  overdispersion assumption.

`swap_events.csv` and `station_hourly_status.csv` are queried via DuckDB
directly off disk and never loaded fully into pandas (RAM-constrained
environment); the other six files use plain pandas.

## 6. Data-Quality Handling

Ten known issues, each detected and handled deliberately (see
`src/clean.py` and the report's Data Quality Validation section):
firmware v3.2.0 timestamp bug, inconsistent city names, near-duplicate
swap events, negative/extreme km values, SOC/SOH >100% readings, missing
station telemetry, non-random CSAT missingness, imperfect support-ticket
categories, STN-TST internal test stations, and battery outlier flags. All
are flagged as boolean columns rather than silently dropped or clipped.
`STN-TST` stations are now consistently excluded across every KPI and
statistical function (an internal audit found this had been applied
inconsistently between Q1/Q2 and Q3/O2 — fixed).

## 7. Statistical Methods

Chi-square tests, Pearson/Spearman correlation, difference-in-differences
(OLS), logistic regression, negative binomial regression, relative risk
with Wald confidence intervals, and a validated overdispersion check
(variance/mean ratio, Poisson-vs-NB AIC and likelihood-ratio test). Every
grouped hypothesis-test family (Q2's 4 splits, Q3's 12 correlation pairs,
Q6's and Q6b's 10 coefficients each) is corrected for multiple comparisons
using Holm-Bonferroni, with raw p-values kept alongside the adjusted ones.
Purely descriptive KPIs (not hypothesis tests) are not "corrected."

## 8. Key Validated Findings

- **Growth and profitability are real and decoupled from failure rate.**
  Contribution margin improved from -Rs.6.48 to +Rs.12.43/swap; failure
  rate shows no significant monthly correlation with growth or margin
  (r=-0.003 to -0.12, all p>0.6).
- **Station age is the one station attribute that survives rigorous
  testing** (Pearson r=0.40, Holm-corrected p<0.0001) — two other
  attributes that looked marginally significant did not survive correction.
- **Three specific Kyron battery lots degrade ~4-6x faster** than every
  other cohort — confirmed stable under a SOC/SOH sensor-drift sensitivity
  check.
- **The peak/off-peak pricing pilot lifts revenue ~Rs.5.3-5.4/swap**,
  robust across both pilot cities individually, with a disclosed (not
  hidden) placebo pre-trend caveat.
- **Retention has two distinct findings, not one.** An earlier binary-model
  claim that queue wait predicts churn did **not** survive Holm correction
  and was withdrawn. The defensible finding: vehicle class and signup
  channel drive how actively an engaged rider uses the service
  (3W riders swap ~30% less; IRR=0.70, Holm p<0.001).
- **The largest fleet partner by revenue is not the most valuable** — two
  of the three largest run deeply negative contribution margin per swap.

Full findings, effect sizes, and every correction applied are in
`report/VoltRelay_Analysis_Report.md` and `notebooks/voltrelay_analysis.ipynb`.

## 9. Repository Structure

```
volt-nexus/
├── data/
│   ├── raw/                 8 source CSVs
│   └── processed/           cleaned Parquet outputs
├── src/
│   ├── config.py            locked definitions (dedup window, retention
│   │                        window, contribution-margin formula, etc.)
│   ├── clean.py              cleaning pipeline
│   ├── kpis.py                KPI aggregation
│   ├── stats.py                statistical tests + validation checks
│   └── viz.py                   chart generation
├── build_notebook.py        assembles the notebook from the modules above
├── notebooks/
│   └── voltrelay_analysis.ipynb   the executed, submittable notebook
├── outputs/figures/         14 PNG charts
├── report/
│   ├── VoltRelay_Analysis_Report.md
│   ├── video_outline.md
│   └── linkedin_post.md
└── requirements.txt
```

## 10. How to Reproduce

```bash
pip install -r requirements.txt

cd src
python clean.py      # cleans data/raw/*.csv -> data/processed/*.parquet
python kpis.py        # sanity-checks KPI aggregation
python stats.py         # sanity-checks statistical tests
python viz.py             # generates all 14 charts to outputs/figures/

cd ..
python build_notebook.py     # assembles notebooks/voltrelay_analysis.ipynb
jupyter nbconvert --to notebook --execute --inplace \
    notebooks/voltrelay_analysis.ipynb
```

All paths are relative to the repository root (`src/config.py` resolves
them via `Path(__file__).resolve().parents[1]`), so this reproduces
identically on any machine — no hardcoded local paths.

## 11. Deliverables

- `notebooks/voltrelay_analysis.ipynb` — executed Colab-compatible
  notebook, 0 errors, all cells run top-to-bottom.
- `report/VoltRelay_Analysis_Report.md` — full written analysis.
- `report/video_outline.md` — 3-minute presentation outline.
- `report/linkedin_post.md` — LinkedIn post draft.
- `outputs/figures/*.png` — 14 charts, each mapped to a specific analytical
  question (see the report's Visualization Framework Validation section).

## 12. Limitations

This is observational analysis; causal language is used only for the Q5
DiD result, which itself carries a disclosed placebo-test caveat. CSAT's
missingness pattern is documented but CSAT is not used as a primary
outcome. Multiple-testing correction is applied to every grouped
inferential test family, which materially changed one conclusion (Q6's
binary-model finding, withdrawn) — see the report's Caveats section for
the full account. O2's "equipment offset siting difficulty" hypothesis was
tested and found inconclusive at the available sample size (n=60
stations); it is reported as a hypothesis, not a proven mechanism.

## 13. AI Usage Disclosure

This project was built with Claude (Anthropic) as an AI pair-analyst:
writing the cleaning/KPI/statistics/visualization pipeline, assembling and
executing the notebook, drafting the report, and — critically — auditing
its own earlier work for methodological gaps (inconsistent test-station
filtering, unvalidated overdispersion assumptions, unhedged causal
language, missing multiple-testing correction) and fixing them, including
withdrawing a headline finding that did not survive correction. All
statistics, figures, and code were executed against the real dataset; no
numbers in this repository are fabricated.
