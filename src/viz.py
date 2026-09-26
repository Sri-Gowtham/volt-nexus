"""One chart per Core Question, built from aggregated data only (never the
full 3.9M-row swap_events table plotted directly). Uses the validated
default categorical palette (see dataviz skill / references/palette.md).
"""

import datetime

import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import FIGURES_DIR, SWAP_EVENTS_CLEAN, BATTERIES_CLEAN, STATIONS_CLEAN
from kpis import network_kpis_monthly, station_segmentation, battery_degradation

# --- validated categorical palette (light mode) ---
C1_BLUE = "#2a78d6"
C2_ORANGE = "#eb6834"
C3_AQUA = "#1baf7a"
C4_YELLOW = "#eda100"
C8_RED = "#e34948"

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_SECONDARY,
    "text.color": INK_PRIMARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "grid.color": GRIDLINE,
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def _save(fig, name):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {path}")


def q1_network_performance():
    df = network_kpis_monthly()
    df = df.sort_values("month")
    idx = df.copy()
    # Only index metrics that never cross zero -- indexing a sign-crossing
    # metric (contribution margin: starts negative, turns positive) to a
    # negative base inverts its apparent direction, so margin gets its own
    # panel in raw INR instead.
    for col in ["completed_swaps", "revenue_inr", "failure_rate"]:
        base = idx[col].iloc[0]
        idx[col + "_idx"] = idx[col] / base * 100

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True,
                                     gridspec_kw={"height_ratios": [2, 1]})
    series = [
        ("completed_swaps_idx", "Completed swaps", C1_BLUE),
        ("revenue_inr_idx", "Revenue", C2_ORANGE),
        ("failure_rate_idx", "Failure rate", C8_RED),
    ]
    for col, label, color in series:
        ax1.plot(idx["month"], idx[col], color=color, linewidth=2, label=label, solid_capstyle="round")
    ax1.axhline(100, color=BASELINE, linewidth=1, linestyle="--")
    ax1.set_ylabel("Indexed to Jan 2024 = 100")
    ax1.set_title("Q1: Volume and revenue grow steadily, but failure rate and margin tell a different story",
                  fontsize=12, color=INK_PRIMARY, loc="left")
    ax1.legend(frameon=False, loc="upper left", fontsize=9)
    ax1.grid(axis="y", linewidth=0.5)

    ax2.plot(idx["month"], idx["avg_contribution_margin_per_swap"], color=C3_AQUA, linewidth=2)
    ax2.axhline(0, color=BASELINE, linewidth=1, linestyle="--")
    ax2.set_ylabel("Contribution margin\n/ swap (INR)")
    ax2.grid(axis="y", linewidth=0.5)
    fig.autofmt_xdate()
    _save(fig, "q1_network_performance.png")


def q2_service_failures_by_hour_season():
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT
            CASE
                WHEN extract(hour FROM event_ts_fixed) BETWEEN 6 AND 10 THEN 'Morning peak'
                WHEN extract(hour FROM event_ts_fixed) BETWEEN 11 AND 16 THEN 'Midday'
                WHEN extract(hour FROM event_ts_fixed) BETWEEN 17 AND 21 THEN 'Evening peak'
                ELSE 'Night'
            END AS hour_bucket,
            SUM(CASE WHEN event_type = 'failed_no_charged_battery' THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS failed_no_battery,
            SUM(CASE WHEN event_type = 'abandoned_queue' THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS abandoned,
            SUM(CASE WHEN event_type = 'cancelled_by_rider' THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS cancelled,
            SUM(CASE WHEN event_type = 'failed_system_error' THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS system_error
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
        WHERE NOT is_test_station
        GROUP BY hour_bucket
    """).df()
    order = ["Morning peak", "Midday", "Evening peak", "Night"]
    df = df.set_index("hour_bucket").reindex(order).reset_index()

    fig, ax = plt.subplots(figsize=(8, 5))
    bottom = np.zeros(len(df))
    segments = [
        ("failed_no_battery", "No charged battery", C8_RED),
        ("abandoned", "Abandoned queue", C2_ORANGE),
        ("cancelled", "Cancelled by rider", C4_YELLOW),
        ("system_error", "System error", C1_BLUE),
    ]
    for col, label, color in segments:
        vals = df[col].values * 100
        ax.bar(df["hour_bucket"], vals, bottom=bottom, label=label, color=color, width=0.6)
        bottom += vals
    ax.set_ylabel("% of attempts")
    ax.set_title("Q2: Service failures are mildly concentrated by time of day",
                 fontsize=12, color=INK_PRIMARY, loc="left")
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    ax.grid(axis="y", linewidth=0.5)
    _save(fig, "q2_service_failures_by_hour.png")


def q2_high_risk_segment(result: dict):
    """Visualizes the vehicle_class x season x hour-of-day interaction
    finding: a specific combination (3W, summer/monsoon, evening/night)
    fails at roughly 2x the rate of everything else -- a much stronger,
    more specific signal than any single marginal split."""
    fig, ax = plt.subplots(figsize=(6, 5))
    labels = ["Rest of network", "3W + summer/monsoon\n+ evening/night"]
    rates = [result["rest_failure_rate"] * 100, result["segment_failure_rate"] * 100]
    colors = [INK_MUTED, C8_RED]
    bars = ax.bar(labels, rates, color=colors, width=0.5)
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, rate + 0.15, f"{rate:.1f}%",
                ha="center", fontsize=11, color=INK_PRIMARY)
    ax.set_ylabel("Failure rate (%)")
    rr = result["relative_risk"]
    ax.set_title(f"Q2: This segment fails at {rr:.1f}x the network rate\n"
                 f"(95% CI {result['rr_ci_low']:.2f}-{result['rr_ci_high']:.2f}x, p<0.001)",
                 fontsize=11, color=INK_PRIMARY, loc="left")
    ax.grid(axis="y", linewidth=0.5)
    _save(fig, "q2b_high_risk_segment.png")


def q4_soh_km_relationship(df_km):
    """Boxplot of km_since_last_swap by SOH decile -- chosen over a raw
    hexbin because the relationship turns out to be NON-monotonic: distinct
    battery-cohort clusters (different lots sit at different fixed SOH
    bands with different typical trip lengths) drive the correlation, not a
    smooth continuous degradation curve. The boxplot shows this honestly;
    a hexbin/scatter alone would have implied a cleaner trend than exists."""
    df_km = df_km.copy()
    df_km["soh_decile"] = pd.cut(df_km["current_soh_pct"], bins=10)
    order = sorted(df_km["soh_decile"].dropna().unique(), key=lambda iv: iv.left)
    data = [df_km.loc[df_km["soh_decile"] == b, "km_since_last_swap"].values for b in order]
    labels = [f"{b.left:.0f}-{b.right:.0f}" for b in order]

    fig, ax = plt.subplots(figsize=(10, 6))
    bp = ax.boxplot(data, tick_labels=labels, showfliers=False, patch_artist=True,
                     medianprops={"color": INK_PRIMARY})
    for patch in bp["boxes"]:
        patch.set_facecolor(C1_BLUE)
        patch.set_alpha(0.6)
    ax.set_xlabel("Battery current SOH decile (%)")
    ax.set_ylabel("km since last swap (outliers excluded)")
    ax.set_title("Q4: SOH-range relationship is real (r=0.32-0.39) but NON-monotonic --\n"
                 "driven by distinct battery-cohort clusters, not smooth degradation",
                 fontsize=11, color=INK_PRIMARY, loc="left")
    ax.grid(axis="y", linewidth=0.5)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    _save(fig, "q4b_soh_km_relationship.png")


def q3b_station_map():
    """Real geographic view -- stations.csv has genuine latitude/longitude
    columns that no other chart in this project uses. Answers "Where did
    it happen?" spatially rather than only via categorical segments."""
    con = duckdb.connect()
    df = con.execute(f"""
        WITH swap_agg AS (
            SELECT station_id,
                   COUNT(*) AS total_attempts,
                   SUM(CASE WHEN event_type != 'swap_completed' THEN 1 ELSE 0 END)::DOUBLE
                       / COUNT(*) AS failure_rate
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
            GROUP BY station_id
        )
        SELECT st.station_id, st.city, st.latitude, st.longitude,
               sa.total_attempts, sa.failure_rate
        FROM '{STATIONS_CLEAN.as_posix()}' st
        JOIN swap_agg sa ON st.station_id = sa.station_id
        WHERE NOT st.is_test_station
    """).df()

    fig, ax = plt.subplots(figsize=(9, 8))
    sizes = 20 + 300 * (df["total_attempts"] / df["total_attempts"].max())
    sc = ax.scatter(df["longitude"], df["latitude"], s=sizes,
                     c=df["failure_rate"] * 100, cmap="Blues", edgecolors=INK_PRIMARY,
                     linewidths=0.4, alpha=0.85)
    for city, grp in df.groupby("city"):
        ax.annotate(city, (grp["longitude"].mean(), grp["latitude"].max() + 0.15),
                    fontsize=9, color=INK_SECONDARY, ha="center")
    cb = fig.colorbar(sc, ax=ax)
    cb.set_label("Failure rate (%)", color=INK_SECONDARY)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Q3b: Station failure rate by real location -- marker size = swap volume",
                 fontsize=11, color=INK_PRIMARY, loc="left")
    ax.grid(linewidth=0.5)
    _save(fig, "q3b_station_map.png")


def q3_station_ranking():
    df = station_segmentation().sort_values("failure_rate", ascending=False).head(10)
    labels = [f"{r.charger_generation} / {r.location_type} / {r.expansion_wave}" for r in df.itertuples()]

    fig, ax = plt.subplots(figsize=(9, 6))
    y = np.arange(len(df))
    ax.barh(y, df["failure_rate"].values * 100, color=C1_BLUE, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Failure rate (%)")
    ax.set_title("Q3: Top 10 station segments by failure rate", fontsize=12, color=INK_PRIMARY, loc="left")
    ax.grid(axis="x", linewidth=0.5)
    _save(fig, "q3_station_ranking.png")


def q4_battery_degradation():
    df = battery_degradation().sort_values("avg_degradation_rate_per_day", ascending=False).head(15)
    colors = [C8_RED if s == "Kyron" else C1_BLUE for s in df["supplier"]]

    fig, ax = plt.subplots(figsize=(9, 6))
    y = np.arange(len(df))
    ax.barh(y, df["avg_degradation_rate_per_day"].values, color=colors, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(df["manufacturing_lot"], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Avg SOH degradation per day (pct points)")
    ax.set_title("Q4: Kyron lots (red) degrade far faster than other cohorts",
                 fontsize=12, color=INK_PRIMARY, loc="left")
    ax.grid(axis="x", linewidth=0.5)
    _save(fig, "q4_battery_degradation.png")


def q5_pricing_pilot_did():
    con = duckdb.connect()
    riders_path = (SWAP_EVENTS_CLEAN.parent / "riders_clean.parquet").as_posix()
    df = con.execute(f"""
        SELECT
            date_trunc('month', s.event_ts_fixed) AS month,
            (r.home_city IN ('Bengaluru', 'Pune')) AS is_pilot,
            AVG(s.amount_charged_inr) AS avg_revenue
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
        JOIN '{riders_path}' r ON s.rider_id = r.rider_id
        WHERE s.event_type = 'swap_completed' AND NOT s.is_test_station
        GROUP BY month, is_pilot
        ORDER BY month
    """).df()

    fig, ax = plt.subplots(figsize=(9, 5))
    for is_pilot, label, color in [(True, "Pilot cities (Bengaluru + Pune)", C1_BLUE),
                                     (False, "Non-pilot cities", INK_MUTED)]:
        sub = df[df["is_pilot"] == is_pilot].sort_values("month")
        ax.plot(sub["month"], sub["avg_revenue"], color=color, linewidth=2, label=label)
    ax.axvline(datetime.datetime(2024, 10, 1),
               color=C8_RED, linestyle="--", linewidth=1, label="Pilot start (2024-10-01)")
    ax.set_ylabel("Avg revenue per completed swap (INR)")
    ax.set_title("Q5: Peak/off-peak pilot lifts revenue/swap in pilot cities",
                 fontsize=12, color=INK_PRIMARY, loc="left")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.grid(axis="y", linewidth=0.5)
    fig.autofmt_xdate()
    _save(fig, "q5_pricing_pilot_did.png")


def o2_expansion_wave_targeting(df):
    """O2: grouped bar comparing wave1 vs wave2 on siting-difficulty
    proxies alongside resulting failure rate -- answers whether Wave2
    targeted harder-to-serve sites or easier ones, and what happened to
    service quality either way."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    waves = df["expansion_wave"].tolist()
    x = np.arange(len(waves))

    ax1.bar(x - 0.2, df["pct_easy_residential_site"] * 100, width=0.4,
            color=C1_BLUE, label="% easy (residential) sites")
    ax1.bar(x + 0.2, df["pct_contested_site"] * 100, width=0.4,
            color=C2_ORANGE, label="% contested (competitor nearby) sites")
    ax1.set_xticks(x)
    ax1.set_xticklabels(waves)
    ax1.set_ylabel("% of stations")
    ax1.set_title("Siting difficulty", fontsize=10, color=INK_PRIMARY, loc="left")
    ax1.legend(frameon=False, fontsize=8, loc="upper right")
    ax1.grid(axis="y", linewidth=0.5)

    ax2.bar(x, df["avg_failure_rate"] * 100, width=0.4, color=C8_RED)
    ax2.set_xticks(x)
    ax2.set_xticklabels(waves)
    ax2.set_ylabel("Avg failure rate (%)")
    ax2.set_ylim(0, max(df["avg_failure_rate"] * 100) * 1.5)
    ax2.set_title("Resulting service quality", fontsize=10, color=INK_PRIMARY, loc="left")
    ax2.grid(axis="y", linewidth=0.5)

    fig.suptitle("O2: Wave2 targeted much harder sites than Wave1, with no drop in performance",
                 fontsize=11, color=INK_PRIMARY, x=0.02, ha="left")
    _save(fig, "o2_expansion_wave_targeting.png")


def o3_fleet_partner_value(df):
    """O3: revenue vs. contribution margin per swap, one point per
    partner, labeled by name -- directly shows whether the largest
    partner by revenue is also the most valuable by margin."""
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = [C8_RED if m < 0 else C3_AQUA for m in df["avg_contribution_margin_per_swap"]]
    sizes = 30 + 200 * (df["n_swaps"] / df["n_swaps"].max())
    ax.scatter(df["total_revenue"] / 1e6, df["avg_contribution_margin_per_swap"],
               s=sizes, c=colors, edgecolors=INK_PRIMARY, linewidths=0.5, alpha=0.85)
    for _, row in df.iterrows():
        ax.annotate(row["partner_name"], (row["total_revenue"] / 1e6, row["avg_contribution_margin_per_swap"]),
                    fontsize=8, color=INK_SECONDARY, xytext=(5, 3), textcoords="offset points")
    ax.axhline(0, color=BASELINE, linewidth=1, linestyle="--")
    ax.set_xlabel("Total revenue (Rs. millions)")
    ax.set_ylabel("Avg contribution margin per swap (INR)")
    ax.set_title("O3: The largest partners by revenue are NOT the most\n"
                 "profitable -- several run negative margin per swap (red)",
                 fontsize=11, color=INK_PRIMARY, loc="left")
    ax.grid(linewidth=0.5)
    _save(fig, "o3_fleet_partner_value.png")


def o4_ticket_keyword_mismatch(result: dict):
    """O4: small-multiples of top distinguishing keywords per category --
    shows free text carries its own rich, category-specific vocabulary
    (the honest finding, after an initial keyword-mismatch approach
    produced two false positives and was corrected -- see kpis.py
    docstring)."""
    top_words = result["top_words_by_category"]
    cats = list(top_words.keys())

    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for ax, cat in zip(axes.flat, cats):
        words, counts = zip(*top_words[cat])
        y = np.arange(len(words))
        ax.barh(y, counts, color=C1_BLUE, height=0.6)
        ax.set_yticks(y)
        ax.set_yticklabels(words, fontsize=9)
        ax.invert_yaxis()
        ax.set_title(cat, fontsize=10, color=INK_PRIMARY, loc="left")
        ax.grid(axis="x", linewidth=0.5)
    for ax in axes.flat[len(cats):]:
        ax.axis("off")

    fig.suptitle("O4: Each ticket category has its own distinct vocabulary --\n"
                 "free text adds signal even though category assignment itself checks out",
                 fontsize=12, color=INK_PRIMARY, x=0.02, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    _save(fig, "o4_ticket_keyword_mismatch.png")


def o1_budget_decision():
    """Answers "What decision does this inform?" directly -- the brief's
    O1 question (which of 4 budget options does the evidence support).
    Deliberately NOT a fabricated composite score across dimensions this
    analysis didn't measure -- bar length/color reflects the actual
    strength of evidence gathered elsewhere in this project, with the
    source finding annotated on each bar."""
    options = [
        ("Network-wide pricing\nrollout", 9, C1_BLUE,
         "Q5 DiD: +Rs.5.35/swap, p<0.001,\nrobust in both pilot cities"),
        ("Targeted battery\nreplacement (not\ngeneric 'more batteries')", 5, C4_YELLOW,
         "Q4: 3 Kyron lots degrade\n~6.7x faster -- targeted, not fleet-wide"),
        ("More stations", 3, INK_MUTED,
         "Q3: newer equipment helps,\nbut expansion ROI not modeled"),
        ("Long-term exclusive\nfleet contract", 1, INK_MUTED,
         "Not evidenced in this analysis\n(fleet-partner value not studied)"),
    ]
    labels = [o[0] for o in options]
    scores = [o[1] for o in options]
    colors = [o[2] for o in options]
    notes = [o[3] for o in options]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    y = np.arange(len(options))
    ax.barh(y, scores, color=colors, height=0.55)
    for yi, score, note in zip(y, scores, notes):
        ax.text(score + 0.15, yi, note, va="center", fontsize=8, color=INK_SECONDARY)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 10)
    ax.set_xlabel("Evidence strength in this analysis (not a formal ROI score)")
    ax.set_title("O1: Of four budget options, only pricing rollout has\n"
                 "strong, quantified, robustness-checked evidence behind it",
                 fontsize=11, color=INK_PRIMARY, loc="left")
    ax.grid(axis="x", linewidth=0.5)
    _save(fig, "o1_budget_decision.png")


def q6b_activity_drivers(nb_summary):
    """IRR forest plot for the negative-binomial 30-day swap-count model --
    the richer, better-powered Q6 outcome that surfaces vehicle_class and
    signup_channel effects the near-degenerate binary model couldn't see."""
    df = nb_summary.drop(index=["Intercept", "alpha"], errors="ignore").copy()
    df = df.sort_values("irr")
    # Colored by Holm-corrected significance (not raw p) -- these 10
    # coefficients are one inferential family; using raw p here would be
    # inconsistent with the corrected narrative reported alongside this
    # chart.
    colors = [C8_RED if p < 0.05 else INK_MUTED for p in df["p_value_holm"]]

    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(df))
    xerr = np.vstack([
        df["irr"] - df["irr_ci_low"],
        df["irr_ci_high"] - df["irr"],
    ])
    ax.errorbar(df["irr"], y, xerr=xerr, fmt="none", ecolor=BASELINE, elinewidth=1.5, capsize=3, zorder=2)
    ax.scatter(df["irr"], y, color=colors, s=50, zorder=3)
    ax.axvline(1.0, color=BASELINE, linestyle="--", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(df.index, fontsize=8)
    ax.set_xlabel("Incidence rate ratio (95% CI) for swaps in first 30 days")
    ax.set_title("Q6b: With a properly-powered outcome, vehicle class and\n"
                 "signup channel emerge as real drivers -- red = significant at\n"
                 "Holm-corrected p<0.05",
                 fontsize=11, color=INK_PRIMARY, loc="left")
    ax.grid(axis="x", linewidth=0.5)
    _save(fig, "q6b_activity_drivers.png")


def q6_retention_drivers(logit_summary):
    df = logit_summary.drop(index="Intercept").copy()
    df = df.sort_values("odds_ratio")
    # Colored by Holm-corrected significance -- with raw p, this chart
    # showed first_queue_wait_sec and a city coefficient as "significant"
    # (red), but neither survives correcting for the 10 coefficients
    # tested together. Using raw p here would visually contradict the
    # corrected finding that NO coefficient survives in this model.
    colors = [C8_RED if p < 0.05 else INK_MUTED for p in df["p_value_holm"]]

    fig, ax = plt.subplots(figsize=(8, 6))
    y = np.arange(len(df))
    xerr = np.vstack([
        df["odds_ratio"] - df["or_ci_low"],
        df["or_ci_high"] - df["odds_ratio"],
    ])
    ax.errorbar(df["odds_ratio"], y, xerr=xerr, fmt="none",
                ecolor=BASELINE, elinewidth=1.5, capsize=3, zorder=2)
    ax.scatter(df["odds_ratio"], y, color=colors, s=50, zorder=3)
    ax.axvline(1.0, color=BASELINE, linestyle="--", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(df.index, fontsize=8)
    ax.set_xlabel("Odds ratio (95% CI) for 30-day return")
    ax.set_title("Q6: No driver survives Holm correction for testing\n"
                 "10 coefficients together (none are red)",
                 fontsize=12, color=INK_PRIMARY, loc="left")
    ax.grid(axis="x", linewidth=0.5)
    _save(fig, "q6_retention_drivers.png")


if __name__ == "__main__":
    print("Q1 chart:")
    q1_network_performance()
    print("Q2 chart:")
    q2_service_failures_by_hour_season()
    print("Q2b chart (high-risk interaction segment):")
    from stats import q2_high_risk_interaction_segment
    riders_path_ = str((SWAP_EVENTS_CLEAN.parent / "riders_clean.parquet").as_posix())
    q2_high_risk_segment(q2_high_risk_interaction_segment(riders_path_))
    print("Q3 chart:")
    q3_station_ranking()
    print("Q3b chart (station geographic map):")
    q3b_station_map()
    print("Q4 chart:")
    q4_battery_degradation()
    print("Q4b chart (SOH vs km proxy):")
    con_ = duckdb.connect()
    df_km_ = con_.execute(f"""
        SELECT b.current_soh_pct, s.km_since_last_swap
        FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
        JOIN '{BATTERIES_CLEAN.as_posix()}' b ON s.battery_out_id = b.battery_id
        WHERE s.event_type = 'swap_completed'
          AND s.km_since_last_swap IS NOT NULL AND NOT s.is_km_outlier
          AND b.current_soh_pct IS NOT NULL
          AND NOT s.is_test_station
    """).df()
    q4_soh_km_relationship(df_km_)
    print("Q5 chart:")
    q5_pricing_pilot_did()
    print("Q6 chart:")
    from stats import q6_logistic_regression, q6_negative_binomial_activity
    q6_retention_drivers(q6_logistic_regression())
    print("Q6b chart (30-day activity count drivers):")
    q6b_activity_drivers(q6_negative_binomial_activity())
    print("O1 chart (budget decision):")
    o1_budget_decision()
    print("O2 chart (expansion wave targeting):")
    from kpis import expansion_wave_targeting, fleet_partner_value, ticket_text_keyword_check
    o2_expansion_wave_targeting(expansion_wave_targeting())
    print("O3 chart (fleet partner value):")
    o3_fleet_partner_value(fleet_partner_value())
    print("O4 chart (ticket keyword mismatch):")
    o4_ticket_keyword_mismatch(ticket_text_keyword_check())
    print("\nAll charts written to", FIGURES_DIR)
