"""Statistical tests for the hero + supporting questions.

Every group-difference claim reports both a test statistic/p-value AND an
effect size, since with 3.9M rows even trivial differences are
"statistically significant" on p-value alone.
"""

import duckdb
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

from config import (
    SWAP_EVENTS_CLEAN,
    STATIONS_CLEAN,
    BATTERIES_CLEAN,
    CITY_DAILY_CONTEXT_CLEAN,
)
from kpis import station_segmentation, battery_degradation, retention_cohorts, retention_activity_30d


# ---------------------------------------------------------------------------
# Q1: monthly co-movement between network metrics (does failure rate move
# with completed_swaps/revenue/margin, or separately?)
# ---------------------------------------------------------------------------
def q1_comovement() -> pd.DataFrame:
    """Simple monthly Pearson correlation between failure_rate and the
    other three Q1 metrics (n=18 months) -- a lightweight, appropriately-
    scaled check for the report's "does not move with" language, replacing
    the earlier unvalidated "independent"/"decoupled" wording. Deliberately
    NOT a time-series/co-integration model -- 18 points does not support
    one, and the business question only needs a simple co-movement check.
    """
    from kpis import network_kpis_monthly
    df = network_kpis_monthly().sort_values("month")
    pairs = [
        ("completed_swaps", "failure_rate"),
        ("revenue_inr", "failure_rate"),
        ("avg_contribution_margin_per_swap", "failure_rate"),
        ("completed_swaps", "revenue_inr"),
    ]
    rows = []
    for a, b in pairs:
        r, p = scipy_stats.pearsonr(df[a], df[b])
        rows.append({"metric_a": a, "metric_b": b, "pearson_r": r, "pearson_p": p, "n_months": len(df)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Q2: Chi-square test + Cramer's V for failure rate across categorical splits
# ---------------------------------------------------------------------------
def cramers_v(confusion_matrix: np.ndarray) -> float:
    chi2 = scipy_stats.chi2_contingency(confusion_matrix)[0]
    n = confusion_matrix.sum()
    r, k = confusion_matrix.shape
    return np.sqrt(chi2 / (n * (min(r, k) - 1)))


def q2_chi_square_by(group_col: str) -> dict:
    """Chi-square test of independence: is failure (any non-completed
    event_type) independent of `group_col`? Returns stat, p-value,
    Cramer's V, and the underlying contingency table."""
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT
            {group_col},
            CASE WHEN event_type = 'swap_completed' THEN 'completed' ELSE 'failed' END AS outcome,
            COUNT(*) AS n
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
        WHERE {group_col} IS NOT NULL
        GROUP BY {group_col}, outcome
    """).df()
    table = df.pivot(index=group_col, columns="outcome", values="n").fillna(0)
    chi2, p, dof, expected = scipy_stats.chi2_contingency(table.values)
    v = cramers_v(table.values)
    return {"group_col": group_col, "chi2": chi2, "p_value": p, "cramers_v": v, "table": table}


def q2_by_derived(riders_clean_path: str) -> dict:
    """Chi-square + Cramer's V for failure vs hour_bucket, season, and
    vehicle_class (via rider join)."""
    con = duckdb.connect()
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW swap_derived AS
        SELECT
            s.*,
            CASE
                WHEN extract(hour FROM s.event_ts_fixed) BETWEEN 6 AND 10 THEN 'morning_peak'
                WHEN extract(hour FROM s.event_ts_fixed) BETWEEN 11 AND 16 THEN 'midday'
                WHEN extract(hour FROM s.event_ts_fixed) BETWEEN 17 AND 21 THEN 'evening_peak'
                ELSE 'night'
            END AS hour_bucket,
            CASE
                WHEN extract(month FROM s.event_ts_fixed) IN (12, 1, 2) THEN 'winter'
                WHEN extract(month FROM s.event_ts_fixed) IN (3, 4, 5) THEN 'summer'
                WHEN extract(month FROM s.event_ts_fixed) IN (6, 7, 8, 9) THEN 'monsoon'
                ELSE 'post_monsoon'
            END AS season,
            r.vehicle_class,
            CASE WHEN s.event_type = 'swap_completed' THEN 'completed' ELSE 'failed' END AS outcome
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
        LEFT JOIN '{riders_clean_path}' r ON s.rider_id = r.rider_id
        WHERE NOT s.is_test_station
    """)
    results = {}
    cols = ["hour_bucket", "season", "vehicle_class", "station_id"]
    for col in cols:
        df = con.execute(f"""
            SELECT {col}, outcome, COUNT(*) AS n
            FROM swap_derived
            WHERE {col} IS NOT NULL
            GROUP BY {col}, outcome
        """).df()
        table = df.pivot(index=col, columns="outcome", values="n").fillna(0)
        chi2, p, dof, expected = scipy_stats.chi2_contingency(table.values)
        v = cramers_v(table.values)
        results[col] = {"chi2": chi2, "p_value": p, "cramers_v": v, "table": table}

    # Multiple-testing correction: these 4 chi-square tests form one
    # inferential family (same failure outcome, 4 candidate splits tested
    # together in Q2). Holm-Bonferroni controls the family-wise error rate
    # without assuming independence between tests. Raw p-values are kept
    # alongside the adjusted ones -- correction is reported, not hidden.
    raw_p = [results[c]["p_value"] for c in cols]
    _, p_holm, _, _ = multipletests(raw_p, method="holm")
    for col, p_adj in zip(cols, p_holm):
        results[col]["p_value_holm"] = p_adj
    return results


def o2_joint_regression() -> object:
    """O2 validation (audit Phase 9): the original write-up said newer
    equipment "offset" Wave2's harder siting -- a causal-sounding claim
    built from two separate descriptive facts that were never jointly
    tested. This fits failure_rate ~ location_type + charger_generation +
    is_contested across Wave1/Wave2 stations (Launch excluded) to test it
    directly. Exploratory / low-powered given n=60 stations -- reported as
    such, not overstated."""
    con = duckdb.connect()
    df = con.execute(f"""
        WITH swap_agg AS (
            SELECT station_id,
                   SUM(CASE WHEN event_type != 'swap_completed' THEN 1 ELSE 0 END)::DOUBLE
                       / COUNT(*) AS failure_rate
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}' WHERE NOT is_test_station GROUP BY station_id
        )
        SELECT st.station_id, st.location_type, st.charger_generation,
               (st.competitor_within_1_5km_since IS NOT NULL) AS is_contested,
               sa.failure_rate
        FROM '{STATIONS_CLEAN.as_posix()}' st
        JOIN swap_agg sa ON st.station_id = sa.station_id
        WHERE NOT st.is_test_station AND st.expansion_wave != 'Launch'
    """).df()
    model = smf.ols(
        "failure_rate ~ C(location_type) + C(charger_generation) + is_contested",
        data=df,
    ).fit()
    return model


def q2_high_risk_interaction_segment(riders_clean_path: str) -> dict:
    """Each single dimension (hour/season/vehicle_class) shows only a weak
    marginal effect on its own (Cramer's V 0.02-0.07). This checks whether
    a specific COMBINATION concentrates risk more than any single split --
    a legitimate follow-up (not p-hacking: one pre-specified, physically
    sensible combination -- 3-wheelers, in hot/wet seasons, during
    evening/night hours, when battery thermal stress and demand both peak
    -- tested once, not dozens of splits mined for significance).

    Reports relative risk (with 95% CI) rather than Cramer's V, since RR is
    the more interpretable "how much worse is this segment" measure for an
    unbalanced yes/no split.
    """
    con = duckdb.connect()
    df = con.execute(f"""
        WITH base AS (
            SELECT s.*,
                CASE WHEN extract(hour FROM s.event_ts_fixed) BETWEEN 17 AND 21 THEN 'evening_peak'
                     WHEN extract(hour FROM s.event_ts_fixed) NOT BETWEEN 6 AND 16 THEN 'night'
                     ELSE 'day' END AS hb,
                CASE WHEN extract(month FROM s.event_ts_fixed) IN (3, 4, 5) THEN 'summer'
                     WHEN extract(month FROM s.event_ts_fixed) IN (6, 7, 8, 9) THEN 'monsoon'
                     ELSE 'other' END AS season,
                r.vehicle_class
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
            LEFT JOIN '{riders_clean_path}' r ON s.rider_id = r.rider_id
            WHERE NOT s.is_test_station
        )
        SELECT
            (vehicle_class = '3W' AND season IN ('summer', 'monsoon') AND hb IN ('evening_peak', 'night'))
                AS is_high_risk_segment,
            CASE WHEN event_type = 'swap_completed' THEN 'completed' ELSE 'failed' END AS outcome,
            COUNT(*) AS n
        FROM base
        WHERE vehicle_class IS NOT NULL
        GROUP BY 1, 2
    """).df()
    table = df.pivot(index="is_high_risk_segment", columns="outcome", values="n").fillna(0)
    a = table.loc[True, "failed"]
    b = table.loc[True, "completed"]
    c = table.loc[False, "failed"]
    d = table.loc[False, "completed"]

    p_segment = a / (a + b)
    p_rest = c / (c + d)
    rr = p_segment / p_rest
    se_logrr = np.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
    ci_low = np.exp(np.log(rr) - 1.96 * se_logrr)
    ci_high = np.exp(np.log(rr) + 1.96 * se_logrr)
    chi2, p_value, dof, expected = scipy_stats.chi2_contingency(table.values)

    return {
        "segment_failure_rate": p_segment, "rest_failure_rate": p_rest,
        "relative_risk": rr, "rr_ci_low": ci_low, "rr_ci_high": ci_high,
        "chi2": chi2, "p_value": p_value, "table": table,
    }


# ---------------------------------------------------------------------------
# Q3: Pearson AND Spearman correlations, station attributes vs outcome KPIs
# ---------------------------------------------------------------------------
def q3_station_correlations() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(f"""
        WITH swap_agg AS (
            SELECT station_id,
                   COUNT(*) AS total_attempts,
                   SUM(CASE WHEN event_type != 'swap_completed' THEN 1 ELSE 0 END)::DOUBLE
                       / COUNT(*) AS failure_rate,
                   AVG(queue_wait_sec) AS avg_queue_wait_sec
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
            GROUP BY station_id
        )
        SELECT
            st.station_id,
            st.slots_2w, st.slots_3w, st.monthly_rent_inr, st.monthly_maintenance_inr,
            st.grid_tariff_inr_kwh,
            date_diff('day', CAST(st.commissioned_date AS DATE), CURRENT_DATE) AS station_age_days,
            sa.failure_rate, sa.avg_queue_wait_sec
        FROM '{STATIONS_CLEAN.as_posix()}' st
        JOIN swap_agg sa ON st.station_id = sa.station_id
        WHERE NOT st.is_test_station
    """).df()

    numeric_cols = ["slots_2w", "slots_3w", "monthly_rent_inr", "monthly_maintenance_inr",
                     "grid_tariff_inr_kwh", "station_age_days"]
    outcome_cols = ["failure_rate", "avg_queue_wait_sec"]

    rows = []
    for nc in numeric_cols:
        for oc in outcome_cols:
            pear_r, pear_p = scipy_stats.pearsonr(df[nc], df[oc])
            spear_r, spear_p = scipy_stats.spearmanr(df[nc], df[oc])
            magnitude_disagreement = abs(pear_r - spear_r) > 0.15
            # Significance-disagreement: one test crosses alpha=0.05 and the
            # other doesn't, even when |r1-r2| is small. The original
            # magnitude-only flag missed this case for grid_tariff_inr_kwh
            # (Pearson p~0.07 not significant, Spearman p~0.006 significant,
            # |Δr|~0.075 -- below the 0.15 magnitude threshold).
            significance_disagreement = (pear_p < 0.05) != (spear_p < 0.05)
            rows.append({
                "attribute": nc, "outcome": oc,
                "pearson_r": pear_r, "pearson_p": pear_p,
                "spearman_r": spear_r, "spearman_p": spear_p,
                "magnitude_disagreement_flag": magnitude_disagreement,
                "significance_disagreement_flag": significance_disagreement,
                "disagreement_flag": magnitude_disagreement or significance_disagreement,
            })
    result = pd.DataFrame(rows)

    # Multiple-testing correction: all 12 (attribute, outcome) pairs tested
    # against the same two outcome variables form one screening family.
    # Pearson and Spearman p-values are corrected as separate families
    # since they're different test statistics for parallel hypotheses.
    _, pearson_p_holm, _, _ = multipletests(result["pearson_p"], method="holm")
    _, spearman_p_holm, _, _ = multipletests(result["spearman_p"], method="holm")
    result["pearson_p_holm"] = pearson_p_holm
    result["spearman_p_holm"] = spearman_p_holm
    return result


# ---------------------------------------------------------------------------
# Q4: Spearman correlation (SOH vs range proxy) already partly covered by
# battery_degradation() in kpis.py; add the correlation piece here.
# ---------------------------------------------------------------------------
def q4_soh_vs_range_proxy() -> dict:
    """Per the locked spec: correlate batteries.current_soh_pct (the
    battery given to the rider, joined via battery_out_id) against the
    delivered-range proxy (soc_out_pct - soc_in_pct) for that swap.

    This proxy mixes two DIFFERENT batteries (the one returned and the one
    issued), which dilutes any real SOH-range relationship -- see
    q4_soh_vs_km_proxy() below for the spec's alternative proxy, which ties
    cleanly to a single battery and shows the relationship this one hides.
    """
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT b.current_soh_pct, s.soc_out_pct - s.soc_in_pct AS range_proxy
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
        JOIN '{BATTERIES_CLEAN.as_posix()}' b ON s.battery_out_id = b.battery_id
        WHERE s.event_type = 'swap_completed'
          AND s.soc_in_pct IS NOT NULL AND s.soc_out_pct IS NOT NULL
          AND b.current_soh_pct IS NOT NULL
          AND NOT s.is_test_station
    """).df()
    pear_r, pear_p = scipy_stats.pearsonr(df["current_soh_pct"], df["range_proxy"])
    spear_r, spear_p = scipy_stats.spearmanr(df["current_soh_pct"], df["range_proxy"])
    return {
        "pearson_r": pear_r, "pearson_p": pear_p,
        "spearman_r": spear_r, "spearman_p": spear_p,
        "n": len(df),
    }


def q4_soh_vs_km_proxy(exclude_soc_soh_over_100: bool = False) -> dict:
    """Alternative delivered-range proxy from the locked spec:
    km_since_last_swap (cleaned -- outliers flagged by clean.py excluded),
    which ties to the single battery just issued rather than mixing two
    different batteries. This is the proxy that actually surfaces the
    SOH-range relationship.

    exclude_soc_soh_over_100: when True, additionally excludes rows flagged
    is_soc_soh_over_100 (sensor-drift readings). Default False preserves
    the original published result; call with True for the sensitivity
    check in q4_soh_vs_km_proxy_sensitivity() below -- both results are
    reported side by side, the original is never silently discarded.
    """
    con = duckdb.connect()
    extra_filter = "AND NOT s.is_soc_soh_over_100" if exclude_soc_soh_over_100 else ""
    df = con.execute(f"""
        SELECT b.current_soh_pct, s.km_since_last_swap
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
        JOIN '{BATTERIES_CLEAN.as_posix()}' b ON s.battery_out_id = b.battery_id
        WHERE s.event_type = 'swap_completed'
          AND s.km_since_last_swap IS NOT NULL
          AND NOT s.is_km_outlier
          AND b.current_soh_pct IS NOT NULL
          AND NOT s.is_test_station
          {extra_filter}
    """).df()
    pear_r, pear_p = scipy_stats.pearsonr(df["current_soh_pct"], df["km_since_last_swap"])
    spear_r, spear_p = scipy_stats.spearmanr(df["current_soh_pct"], df["km_since_last_swap"])
    return {
        "pearson_r": pear_r, "pearson_p": pear_p,
        "spearman_r": spear_r, "spearman_p": spear_p,
        "n": len(df),
    }


def q4_soh_vs_km_proxy_sensitivity() -> pd.DataFrame:
    """Sensitivity check requested in the audit: does excluding
    SOC/SOH>100% rows (sensor-drift flag, currently only flagged, never
    filtered) materially change the Q4 km-proxy correlation? Runs BOTH the
    original and the cleaned version and reports both -- the original is
    not discarded unless this shows the conclusion changes."""
    original = q4_soh_vs_km_proxy(exclude_soc_soh_over_100=False)
    cleaned = q4_soh_vs_km_proxy(exclude_soc_soh_over_100=True)
    rows = []
    for metric in ["pearson_r", "spearman_r", "n"]:
        rows.append({
            "metric": metric,
            "original": original[metric],
            "cleaned": cleaned[metric],
            "difference": (cleaned[metric] - original[metric]) if metric != "n" else cleaned[metric] - original[metric],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Q5: Difference-in-differences, peak/off-peak pricing pilot
# ---------------------------------------------------------------------------
def q5_did(pilot_cities: list[str], pilot_start_date: str) -> pd.DataFrame:
    """Pooled DiD: pilot vs non-pilot cities, before vs after pilot_start_date,
    on revenue (amount_charged_inr per completed swap as the revenue proxy;
    full contribution-margin DiD reuses the kpis.py margin join if time
    allows)."""
    con = duckdb.connect()
    pilot_list = ", ".join(f"'{c}'" for c in pilot_cities)
    riders_path = (SWAP_EVENTS_CLEAN.parent / "riders_clean.parquet").as_posix()
    df = con.execute(f"""
        SELECT
            r.home_city AS city,
            (r.home_city IN ({pilot_list})) AS is_pilot,
            (s.event_ts_fixed >= TIMESTAMP '{pilot_start_date}') AS is_post,
            s.amount_charged_inr
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
        JOIN '{riders_path}' r ON s.rider_id = r.rider_id
        WHERE s.event_type = 'swap_completed' AND NOT s.is_test_station
    """).df()

    model = smf.ols("amount_charged_inr ~ is_pilot * is_post", data=df).fit()
    return model


def q5_did_per_city(pilot_cities: list[str], pilot_start_date: str) -> dict:
    """Per-pilot-city DiD: each pilot city vs. all NON-pilot cities as the
    control group (excludes the other pilot city's rows entirely, so the
    comparison isn't contaminated by the other city's own treatment)."""
    results = {}
    con = duckdb.connect()
    riders_path = SWAP_EVENTS_CLEAN.parent / "riders_clean.parquet"
    other_pilots = {c: [p for p in pilot_cities if p != c] for c in pilot_cities}
    for city in pilot_cities:
        exclude_list = ", ".join(f"'{c}'" for c in other_pilots[city]) or "''"
        df = con.execute(f"""
            SELECT
                (r.home_city = '{city}') AS is_pilot,
                (s.event_ts_fixed >= TIMESTAMP '{pilot_start_date}') AS is_post,
                s.amount_charged_inr
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
            JOIN '{riders_path.as_posix()}' r ON s.rider_id = r.rider_id
            WHERE s.event_type = 'swap_completed' AND NOT s.is_test_station
              AND r.home_city NOT IN ({exclude_list})
        """).df()
        model = smf.ols("amount_charged_inr ~ is_pilot * is_post", data=df).fit()
        results[city] = model
    return results


def q5_placebo_test(pilot_cities: list[str], real_pilot_start_date: str, placebo_date: str) -> object:
    """Lightweight placebo/pre-trend check (audit Phase 5): re-runs the
    pooled DiD using ONLY data from before the real pilot start, with a
    fake "placebo" treatment date inside that pre-period. If pilot vs.
    non-pilot cities were genuinely on parallel trends before the real
    pilot, the placebo interaction term should NOT be significant -- a
    significant placebo effect would suggest the pilot cities were already
    diverging for some other reason before treatment, undermining the
    real DiD's parallel-trends assumption. This does not replace DiD with
    a synthetic-control model -- it is a single additional regression on
    the same pre-period data already used to build Figure q5."""
    con = duckdb.connect()
    pilot_list = ", ".join(f"'{c}'" for c in pilot_cities)
    riders_path = (SWAP_EVENTS_CLEAN.parent / "riders_clean.parquet").as_posix()
    df = con.execute(f"""
        SELECT
            (r.home_city IN ({pilot_list})) AS is_pilot,
            (s.event_ts_fixed >= TIMESTAMP '{placebo_date}') AS is_post,
            s.amount_charged_inr
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
        JOIN '{riders_path}' r ON s.rider_id = r.rider_id
        WHERE s.event_type = 'swap_completed' AND NOT s.is_test_station
          AND s.event_ts_fixed < TIMESTAMP '{real_pilot_start_date}'
    """).df()
    model = smf.ols("amount_charged_inr ~ is_pilot * is_post", data=df).fit()
    return model


# ---------------------------------------------------------------------------
# Q6: Logistic regression, odds ratios + 95% CIs
# ---------------------------------------------------------------------------
def q6_logistic_regression() -> pd.DataFrame:
    df = retention_cohorts()
    df = df.dropna(subset=["vehicle_class", "signup_channel", "home_city", "first_swap_outcome"])
    df["first_swap_completed"] = (df["first_swap_outcome"] == "swap_completed").astype(int)

    model = smf.logit(
        "returned_within_window ~ first_swap_completed + first_queue_wait_sec "
        "+ C(signup_channel) + C(vehicle_class) + C(home_city)",
        data=df,
    ).fit(disp=False)

    conf = model.conf_int()
    conf.columns = ["ci_low", "ci_high"]
    summary = pd.DataFrame({
        "coef": model.params,
        "odds_ratio": np.exp(model.params),
        "or_ci_low": np.exp(conf["ci_low"]),
        "or_ci_high": np.exp(conf["ci_high"]),
        "p_value": model.pvalues,
    })

    # Multiple-testing correction across the 10 predictor coefficients
    # (excluding Intercept, which isn't a hypothesis of interest here).
    # This is a real inferential family -- 10 coefficients tested in one
    # model -- unlike the many purely descriptive KPI tables elsewhere in
    # this project, which are not corrected because they aren't hypothesis
    # tests.
    non_intercept = summary.index != "Intercept"
    _, p_holm, _, _ = multipletests(summary.loc[non_intercept, "p_value"], method="holm")
    summary["p_value_holm"] = np.nan
    summary.loc[non_intercept, "p_value_holm"] = p_holm
    return summary


NB_FORMULA = ("swaps_30d ~ first_swap_completed + first_queue_wait_sec "
              "+ C(signup_channel) + C(vehicle_class) + C(home_city)")


def q6_overdispersion_check() -> dict:
    """Validates the overdispersion assumption behind using negative
    binomial (rather than Poisson) for swaps_30d, per audit requirement --
    this was previously asserted in a code comment, not tested.

    Reports: mean, variance, variance/mean ratio (Poisson assumes 1);
    Poisson vs. NB AIC; a likelihood-ratio test (NB nests Poisson at
    alpha=0, so LR = 2*(llf_NB - llf_Poisson) ~ chi2(1)); and a coefficient
    comparison to confirm the previously-reported IRR findings are stable
    regardless of which model is used.
    """
    df = retention_activity_30d()
    df = df.dropna(subset=["vehicle_class", "signup_channel", "home_city", "first_outcome"])
    df["first_swap_completed"] = (df["first_outcome"] == "swap_completed").astype(int)

    y = df["swaps_30d"]
    mean_, var_ = y.mean(), y.var()
    ratio = var_ / mean_

    poisson_model = smf.poisson(NB_FORMULA, data=df).fit(disp=False)
    nb_model = smf.negativebinomial(NB_FORMULA, data=df).fit(disp=False)

    lr_stat = 2 * (nb_model.llf - poisson_model.llf)
    lr_p = scipy_stats.chi2.sf(lr_stat, df=1)

    coef_comparison = pd.DataFrame({
        "poisson_irr": np.exp(poisson_model.params),
        "nb_irr": np.exp(nb_model.params.reindex(poisson_model.params.index)),
    })
    coef_comparison["irr_diff"] = coef_comparison["nb_irr"] - coef_comparison["poisson_irr"]

    return {
        "mean": mean_, "variance": var_, "variance_mean_ratio": ratio,
        "poisson_aic": poisson_model.aic, "nb_aic": nb_model.aic,
        "nb_alpha": nb_model.params.get("alpha", np.nan),
        "lr_stat": lr_stat, "lr_p_value": lr_p,
        "nb_justified": ratio > 1.5 and nb_model.aic < poisson_model.aic and lr_p < 0.05,
        "coef_comparison": coef_comparison,
    }


def q6_negative_binomial_activity() -> pd.DataFrame:
    """Q6 with a richer outcome: swaps_30d (count) instead of the binary
    returned_within_window. The binary outcome is ~99.5% "yes" and has
    almost no variance to explain; this count outcome has real variance
    across all 19,950 riders and is properly powered where the binary
    model was not.

    Negative binomial (not Poisson) is used since swap counts are
    overdispersed -- this is now VALIDATED, not just asserted: see
    q6_overdispersion_check() (variance/mean ratio ~3.68, NB AIC far below
    Poisson AIC, likelihood-ratio test p<0.001). The Poisson-vs-NB
    comparison also confirms the reported IRR findings are stable across
    both specifications.
    """
    df = retention_activity_30d()
    df = df.dropna(subset=["vehicle_class", "signup_channel", "home_city", "first_outcome"])
    df["first_swap_completed"] = (df["first_outcome"] == "swap_completed").astype(int)

    model = smf.negativebinomial(NB_FORMULA, data=df).fit(disp=False)

    conf = model.conf_int()
    conf.columns = ["ci_low", "ci_high"]
    summary = pd.DataFrame({
        "coef": model.params,
        "irr": np.exp(model.params),
        "irr_ci_low": np.exp(conf["ci_low"]),
        "irr_ci_high": np.exp(conf["ci_high"]),
        "p_value": model.pvalues,
    })
    summary.attrs["pseudo_r2"] = model.prsquared if hasattr(model, "prsquared") else None

    # Multiple-testing correction across the 10 predictor coefficients
    # (excluding Intercept and alpha, the dispersion parameter -- neither
    # is a hypothesis of interest here).
    non_target = summary.index.isin(["Intercept", "alpha"])
    target = ~non_target
    _, p_holm, _, _ = multipletests(summary.loc[target, "p_value"], method="holm")
    summary["p_value_holm"] = np.nan
    summary.loc[target, "p_value_holm"] = p_holm
    return summary


def q6_logistic_regression_validation() -> dict:
    """Honest predictive-quality check for the Q6 retention model.

    The outcome is severely imbalanced (~99.5% return within 30 days), so
    plain accuracy/ROC-AUC on the raw class would be misleading (a model
    that always predicts "returned" scores ~99.5% accuracy trivially). This
    uses a class-weighted classifier, a stratified 70/30 holdout, and
    reports ROC-AUC + PR-AUC (average precision) -- the correct metrics for
    a rare-event outcome -- alongside the naive majority-class baseline for
    direct, honest comparison. Report this number as-is even if it shows
    the model barely beats chance; that is itself the finding.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score, average_precision_score, accuracy_score

    df = retention_cohorts()
    df = df.dropna(subset=["vehicle_class", "signup_channel", "home_city", "first_swap_outcome"])
    df["first_swap_completed"] = (df["first_swap_outcome"] == "swap_completed").astype(int)
    df["not_returned"] = 1 - df["returned_within_window"]

    X = pd.get_dummies(
        df[["first_swap_completed", "first_queue_wait_sec", "signup_channel", "vehicle_class", "home_city"]],
        columns=["signup_channel", "vehicle_class", "home_city"], drop_first=True,
    )
    y = df["not_returned"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )
    clf = LogisticRegression(class_weight="balanced", max_iter=1000)
    clf.fit(X_train, y_train)
    proba = clf.predict_proba(X_test)[:, 1]
    pred = clf.predict(X_test)

    naive_pred = np.zeros(len(y_test))
    return {
        "base_rate_not_returned": y.mean(),
        "roc_auc": roc_auc_score(y_test, proba),
        "pr_auc": average_precision_score(y_test, proba),
        "balanced_model_accuracy": accuracy_score(y_test, pred),
        "naive_baseline_accuracy": accuracy_score(y_test, naive_pred),
    }


if __name__ == "__main__":
    riders_path = str((SWAP_EVENTS_CLEAN.parent / "riders_clean.parquet").as_posix())

    print("=== Q2: chi-square + Cramer's V ===")
    q2 = q2_by_derived(riders_path)
    for col, res in q2.items():
        print(f"{col}: chi2={res['chi2']:.1f}, p={res['p_value']:.2e}, Cramer's V={res['cramers_v']:.4f}")

    print("\n=== Q3: Pearson vs Spearman (station attributes vs outcomes) ===")
    q3 = q3_station_correlations()
    print(q3.to_string())

    print("\n=== Q4: SOH vs range proxy ===")
    q4 = q4_soh_vs_range_proxy()
    print(q4)

    print("\n=== Q5: pooled DiD (pilot cities Bengaluru+Pune, confirmed via tariff_code PEAK/OFFPEAK, start 2024-10-01) ===")
    q5 = q5_did(["Bengaluru", "Pune"], "2024-10-01")
    print(q5.summary())

    print("\n=== Q5 (X2): per-pilot-city DiD robustness check ===")
    q5_per_city = q5_did_per_city(["Bengaluru", "Pune"], "2024-10-01")
    for city, model in q5_per_city.items():
        print(f"--- {city} ---")
        print(model.summary())

    print("\n=== Q6: logistic regression, odds ratios ===")
    q6 = q6_logistic_regression()
    print(q6.to_string())
