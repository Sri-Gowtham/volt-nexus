"""KPI aggregation functions, built on the cleaned Parquet outputs from
clean.py. Large-file work stays in DuckDB; small-file work uses pandas.

All functions return small, already-aggregated pandas DataFrames safe to
plot or feed into stats.py.
"""

import duckdb
import pandas as pd

from config import (
    SWAP_EVENTS_CLEAN,
    STATION_HOURLY_STATUS_CLEAN,
    RIDERS_CLEAN,
    BATTERIES_CLEAN,
    SUPPORT_TICKETS_CLEAN,
    STATIONS_CLEAN,
    ASSUMED_CYCLE_LIFE,
    RETENTION_WINDOW_DAYS,
    FLEET_PARTNERS_CLEAN,
)


def _con():
    return duckdb.connect()


# ---------------------------------------------------------------------------
# Q1: Network performance over time
# ---------------------------------------------------------------------------
def network_kpis_monthly() -> pd.DataFrame:
    """Monthly completed swaps, completion rate, failure rate, revenue,
    and contribution margin per swap.

    contribution_margin per completed swap =
        amount_charged_inr
        - energy_to_recharge_kwh * grid_tariff_inr_kwh
        - battery_wear_cost_proxy (purchase_cost_inr / ASSUMED_CYCLE_LIFE, per battery_out_id)
        - allocated_station_cost_per_swap (station's monthly rent+maintenance
          divided across that station's completed swaps that month)
    """
    con = _con()
    df = con.execute(f"""
        WITH swaps AS (
            SELECT
                date_trunc('month', event_ts_fixed) AS month,
                event_type,
                station_id,
                battery_out_id,
                amount_charged_inr,
                energy_to_recharge_kwh
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
            WHERE NOT is_test_station
        ),
        monthly_totals AS (
            SELECT month,
                   COUNT(*) AS total_attempts,
                   SUM(CASE WHEN event_type = 'swap_completed' THEN 1 ELSE 0 END) AS completed_swaps,
                   SUM(CASE WHEN event_type != 'swap_completed' THEN 1 ELSE 0 END) AS failed_attempts,
                   SUM(CASE WHEN event_type = 'swap_completed' THEN amount_charged_inr ELSE 0 END) AS revenue_inr
            FROM swaps
            GROUP BY month
        ),
        station_month_swaps AS (
            SELECT station_id, month, COUNT(*) AS n_completed
            FROM swaps
            WHERE event_type = 'swap_completed'
            GROUP BY station_id, month
        ),
        station_costs AS (
            SELECT station_id, (monthly_rent_inr + monthly_maintenance_inr) AS monthly_cost
            FROM '{STATIONS_CLEAN.as_posix()}'
        ),
        battery_costs AS (
            SELECT battery_id, purchase_cost_inr / {ASSUMED_CYCLE_LIFE} AS wear_cost_proxy
            FROM '{BATTERIES_CLEAN.as_posix()}'
        ),
        margin_components AS (
            SELECT
                s.month,
                s.amount_charged_inr
                    - s.energy_to_recharge_kwh * st.grid_tariff_inr_kwh
                    - COALESCE(bc.wear_cost_proxy, 0)
                    - COALESCE(sc.monthly_cost / NULLIF(sms.n_completed, 0), 0) AS contribution_margin
            FROM swaps s
            JOIN '{STATIONS_CLEAN.as_posix()}' st ON s.station_id = st.station_id
            LEFT JOIN battery_costs bc ON s.battery_out_id = bc.battery_id
            LEFT JOIN station_costs sc ON s.station_id = sc.station_id
            LEFT JOIN station_month_swaps sms ON s.station_id = sms.station_id AND s.month = sms.month
            WHERE s.event_type = 'swap_completed'
        ),
        margin_monthly AS (
            SELECT month, AVG(contribution_margin) AS avg_contribution_margin_per_swap
            FROM margin_components
            GROUP BY month
        )
        SELECT
            t.month,
            t.completed_swaps,
            t.failed_attempts,
            t.total_attempts,
            t.completed_swaps::DOUBLE / NULLIF(t.total_attempts, 0) AS completion_rate,
            t.failed_attempts::DOUBLE / NULLIF(t.total_attempts, 0) AS failure_rate,
            t.revenue_inr,
            m.avg_contribution_margin_per_swap
        FROM monthly_totals t
        JOIN margin_monthly m ON t.month = m.month
        ORDER BY t.month
    """).df()
    return df


# ---------------------------------------------------------------------------
# Q3: Station segmentation / ranking table
# ---------------------------------------------------------------------------
def station_segmentation() -> pd.DataFrame:
    """charger_generation x location_type x expansion_wave ranking by
    failure rate, avg_charge_minutes, complaint rate."""
    con = _con()
    df = con.execute(f"""
        WITH swap_agg AS (
            SELECT station_id,
                   COUNT(*) AS total_attempts,
                   SUM(CASE WHEN event_type != 'swap_completed' THEN 1 ELSE 0 END) AS failed_attempts
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
            GROUP BY station_id
        ),
        charge_agg AS (
            SELECT station_id, AVG(avg_charge_minutes) AS avg_charge_minutes
            FROM '{STATION_HOURLY_STATUS_CLEAN.as_posix()}'
            GROUP BY station_id
        ),
        complaint_agg AS (
            SELECT station_id, COUNT(*) AS n_tickets
            FROM '{SUPPORT_TICKETS_CLEAN.as_posix()}'
            WHERE station_id IS NOT NULL
            GROUP BY station_id
        )
        SELECT
            st.charger_generation,
            st.location_type,
            st.expansion_wave,
            COUNT(*) AS n_stations,
            SUM(sa.failed_attempts)::DOUBLE / NULLIF(SUM(sa.total_attempts), 0) AS failure_rate,
            AVG(ca.avg_charge_minutes) AS avg_charge_minutes,
            SUM(COALESCE(co.n_tickets, 0))::DOUBLE / NULLIF(SUM(sa.total_attempts), 0) AS complaint_rate
        FROM '{STATIONS_CLEAN.as_posix()}' st
        LEFT JOIN swap_agg sa ON st.station_id = sa.station_id
        LEFT JOIN charge_agg ca ON st.station_id = ca.station_id
        LEFT JOIN complaint_agg co ON st.station_id = co.station_id
        WHERE NOT st.is_test_station
        GROUP BY st.charger_generation, st.location_type, st.expansion_wave
        ORDER BY failure_rate DESC
    """).df()
    return df


# ---------------------------------------------------------------------------
# Q2: Service KPIs (queue wait / abandonment / cancellation / system error)
# ---------------------------------------------------------------------------
def service_kpis(group_cols=("station_id",)) -> pd.DataFrame:
    """Queue wait stats and failure-type rates, grouped by the given
    swap_events columns (e.g. station_id, hour bucket, season, vehicle_class
    via rider join)."""
    con = _con()
    group_sql = ", ".join(group_cols)
    df = con.execute(f"""
        WITH base AS (
            SELECT
                s.*,
                extract(hour FROM s.event_ts_fixed) AS hour_of_day,
                CASE
                    WHEN extract(month FROM s.event_ts_fixed) IN (12, 1, 2) THEN 'winter'
                    WHEN extract(month FROM s.event_ts_fixed) IN (3, 4, 5) THEN 'summer'
                    WHEN extract(month FROM s.event_ts_fixed) IN (6, 7, 8, 9) THEN 'monsoon'
                    ELSE 'post_monsoon'
                END AS season,
                r.vehicle_class
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
            LEFT JOIN '{RIDERS_CLEAN.as_posix()}' r ON s.rider_id = r.rider_id
            WHERE NOT s.is_test_station
        )
        SELECT
            {group_sql},
            COUNT(*) AS total_attempts,
            AVG(queue_wait_sec) AS avg_queue_wait_sec,
            MEDIAN(queue_wait_sec) AS median_queue_wait_sec,
            SUM(CASE WHEN event_type = 'failed_no_charged_battery' THEN 1 ELSE 0 END)::DOUBLE
                / COUNT(*) AS failed_no_battery_rate,
            SUM(CASE WHEN event_type = 'abandoned_queue' THEN 1 ELSE 0 END)::DOUBLE
                / COUNT(*) AS abandoned_rate,
            SUM(CASE WHEN event_type = 'cancelled_by_rider' THEN 1 ELSE 0 END)::DOUBLE
                / COUNT(*) AS cancelled_rate,
            SUM(CASE WHEN event_type = 'failed_system_error' THEN 1 ELSE 0 END)::DOUBLE
                / COUNT(*) AS system_error_rate
        FROM base
        GROUP BY {group_sql}
        ORDER BY {group_sql}
    """).df()
    return df


# ---------------------------------------------------------------------------
# Q6: Customer KPIs (new rider counts, 30-day return rate)
# ---------------------------------------------------------------------------
def retention_cohorts() -> pd.DataFrame:
    """Per-rider first swap event and whether they returned (>=1 completed
    swap) within RETENTION_WINDOW_DAYS after that first event."""
    con = _con()
    df = con.execute(f"""
        WITH first_events AS (
            SELECT rider_id,
                   MIN(event_ts_fixed) AS first_event_ts
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
            WHERE NOT is_test_station
            GROUP BY rider_id
        ),
        first_event_detail AS (
            SELECT s.rider_id, s.event_ts_fixed AS first_event_ts, s.event_type AS first_swap_outcome,
                   s.queue_wait_sec AS first_queue_wait_sec, s.station_id AS first_station_id
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
            JOIN first_events f ON s.rider_id = f.rider_id AND s.event_ts_fixed = f.first_event_ts
        ),
        returns AS (
            SELECT fe.rider_id,
                   MAX(CASE
                       WHEN s2.event_type = 'swap_completed'
                            AND NOT s2.is_test_station
                            AND s2.event_ts_fixed > fe.first_event_ts
                            AND s2.event_ts_fixed <= fe.first_event_ts + INTERVAL '{RETENTION_WINDOW_DAYS} days'
                       THEN 1 ELSE 0 END) AS returned_within_window
            FROM first_event_detail fe
            LEFT JOIN '{SWAP_EVENTS_CLEAN.as_posix()}' s2 ON fe.rider_id = s2.rider_id
            GROUP BY fe.rider_id
        )
        SELECT fe.*, r.vehicle_class, r.signup_channel, r.home_city,
               ret.returned_within_window
        FROM first_event_detail fe
        JOIN returns ret ON fe.rider_id = ret.rider_id
        LEFT JOIN '{RIDERS_CLEAN.as_posix()}' r ON fe.rider_id = r.rider_id
    """).df()
    return df


def retention_activity_30d() -> pd.DataFrame:
    """Richer Q6 outcome than the binary returned_within_window: total
    completed swaps in the 30 days after a rider's first event. The binary
    metric is ~99.5% "yes" (almost no variance to explain); this count
    outcome has real variance across all riders and surfaces effects
    (vehicle_class, signup_channel) the binary model couldn't detect."""
    con = _con()
    df = con.execute(f"""
        WITH first_events AS (
            SELECT rider_id, MIN(event_ts_fixed) AS first_ts
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
            WHERE NOT is_test_station
            GROUP BY rider_id
        ),
        first_detail AS (
            SELECT s.rider_id, s.event_ts_fixed AS first_ts, s.event_type AS first_outcome,
                   s.queue_wait_sec AS first_queue_wait_sec
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
            JOIN first_events f ON s.rider_id = f.rider_id AND s.event_ts_fixed = f.first_ts
        ),
        activity AS (
            SELECT fd.*,
                SUM(CASE WHEN s2.event_type = 'swap_completed'
                         AND NOT s2.is_test_station
                         AND s2.event_ts_fixed > fd.first_ts
                         AND s2.event_ts_fixed <= fd.first_ts + INTERVAL '{RETENTION_WINDOW_DAYS} days'
                    THEN 1 ELSE 0 END) AS swaps_30d
            FROM first_detail fd
            LEFT JOIN '{SWAP_EVENTS_CLEAN.as_posix()}' s2 ON fd.rider_id = s2.rider_id
            GROUP BY fd.rider_id, fd.first_outcome, fd.first_ts, fd.first_queue_wait_sec
        )
        SELECT a.*, r.vehicle_class, r.signup_channel, r.home_city
        FROM activity a
        LEFT JOIN '{RIDERS_CLEAN.as_posix()}' r ON a.rider_id = r.rider_id
    """).df()
    return df


def expansion_wave_targeting() -> pd.DataFrame:
    """O2: did Wave2 target harder-to-serve locations than Wave1, or easier
    ones? Compares siting-difficulty proxies (competitor proximity,
    residential/"easy" location share) against resulting failure and
    complaint rate, per wave (Launch excluded -- it's not an expansion)."""
    con = _con()
    df = con.execute(f"""
        WITH swap_agg AS (
            SELECT station_id,
                   COUNT(*) AS total_attempts,
                   SUM(CASE WHEN event_type != 'swap_completed' THEN 1 ELSE 0 END)::DOUBLE
                       / COUNT(*) AS failure_rate
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}'
            GROUP BY station_id
        ),
        complaint_agg AS (
            SELECT station_id, COUNT(*) AS n_tickets
            FROM '{SUPPORT_TICKETS_CLEAN.as_posix()}'
            WHERE station_id IS NOT NULL
            GROUP BY station_id
        )
        SELECT
            st.expansion_wave,
            COUNT(*) AS n_stations,
            AVG(CASE WHEN st.competitor_within_1_5km_since IS NOT NULL THEN 1 ELSE 0 END) AS pct_contested_site,
            SUM(CASE WHEN st.location_type = 'residential' THEN 1 ELSE 0 END)::DOUBLE
                / COUNT(*) AS pct_easy_residential_site,
            AVG(sa.failure_rate) AS avg_failure_rate,
            SUM(COALESCE(co.n_tickets, 0))::DOUBLE / SUM(sa.total_attempts) AS complaint_rate
        FROM '{STATIONS_CLEAN.as_posix()}' st
        LEFT JOIN swap_agg sa ON st.station_id = sa.station_id
        LEFT JOIN complaint_agg co ON st.station_id = co.station_id
        WHERE NOT st.is_test_station AND st.expansion_wave != 'Launch'
        GROUP BY st.expansion_wave
        ORDER BY st.expansion_wave
    """).df()
    return df


def fleet_partner_value() -> pd.DataFrame:
    """O3: per-partner revenue, swap count, and contribution margin/swap --
    reuses the exact CONTRIBUTION_MARGIN formula from network_kpis_monthly()
    (Q1), grouped by partner_id instead of month, to check whether the
    largest partner by revenue is also the most valuable by margin."""
    con = _con()
    df = con.execute(f"""
        WITH swaps AS (
            SELECT
                r.partner_id,
                s.station_id, s.battery_out_id,
                s.amount_charged_inr, s.energy_to_recharge_kwh,
                date_trunc('month', s.event_ts_fixed) AS month
            FROM '{SWAP_EVENTS_CLEAN.as_posix()}' s
            JOIN '{RIDERS_CLEAN.as_posix()}' r ON s.rider_id = r.rider_id
            WHERE s.event_type = 'swap_completed' AND r.partner_id IS NOT NULL
                AND NOT s.is_test_station
        ),
        station_month_swaps AS (
            SELECT station_id, month, COUNT(*) AS n_completed
            FROM swaps GROUP BY station_id, month
        ),
        station_costs AS (
            SELECT station_id, (monthly_rent_inr + monthly_maintenance_inr) AS monthly_cost
            FROM '{STATIONS_CLEAN.as_posix()}'
        ),
        battery_costs AS (
            SELECT battery_id, purchase_cost_inr / {ASSUMED_CYCLE_LIFE} AS wear_cost_proxy
            FROM '{BATTERIES_CLEAN.as_posix()}'
        ),
        margin_components AS (
            SELECT
                s.partner_id,
                s.amount_charged_inr
                    - s.energy_to_recharge_kwh * st.grid_tariff_inr_kwh
                    - COALESCE(bc.wear_cost_proxy, 0)
                    - COALESCE(sc.monthly_cost / NULLIF(sms.n_completed, 0), 0) AS contribution_margin,
                s.amount_charged_inr AS revenue
            FROM swaps s
            JOIN '{STATIONS_CLEAN.as_posix()}' st ON s.station_id = st.station_id
            LEFT JOIN battery_costs bc ON s.battery_out_id = bc.battery_id
            LEFT JOIN station_costs sc ON s.station_id = sc.station_id
            LEFT JOIN station_month_swaps sms ON s.station_id = sms.station_id AND s.month = sms.month
        )
        SELECT
            fp.partner_id, fp.partner_name, fp.partner_segment, fp.discount_pct,
            COUNT(*) AS n_swaps,
            SUM(mc.revenue) AS total_revenue,
            AVG(mc.contribution_margin) AS avg_contribution_margin_per_swap
        FROM margin_components mc
        JOIN '{FLEET_PARTNERS_CLEAN.as_posix()}' fp ON mc.partner_id = fp.partner_id
        GROUP BY fp.partner_id, fp.partner_name, fp.partner_segment, fp.discount_pct
        ORDER BY total_revenue DESC
    """).df()
    return df


def csat_by_resolution_bucket() -> pd.DataFrame:
    """Minimal descriptive CSAT analysis (audit Phase 8): CSAT is missing
    not-at-random, so this deliberately does NOT report an overall average
    as representative. Instead it compares CSAT *coverage* (response rate)
    and average score-among-responders across resolution-time buckets, to
    make the MNAR pattern concrete rather than just asserted. Descriptive
    only -- no causal claim about resolution speed affecting satisfaction,
    since responders and non-responders may differ in other unobserved
    ways too."""
    con = _con()
    df = con.execute(f"""
        SELECT
            CASE WHEN resolution_hours <= 2 THEN 'fast (<=2h)'
                 WHEN resolution_hours <= 24 THEN 'medium (2-24h)'
                 ELSE 'slow (>24h)' END AS resolution_bucket,
            COUNT(*) AS n_tickets,
            SUM(CASE WHEN csat_score IS NOT NULL THEN 1 ELSE 0 END) AS n_with_csat,
            AVG(CASE WHEN csat_score IS NOT NULL THEN 1.0 ELSE 0 END) AS csat_coverage_rate,
            AVG(csat_score) AS avg_csat_among_responders
        FROM '{SUPPORT_TICKETS_CLEAN.as_posix()}'
        GROUP BY 1
        ORDER BY 1
    """).df()
    return df


def ticket_text_keyword_check() -> dict:
    """O4 (lightweight, not NLP modeling): does rider_comment free text add
    signal beyond category/resolution_status?

    First attempt was a keyword-mismatch flag (comment mentions battery but
    category isn't battery-related) -- dropped after it produced two false
    findings: "charge" matched "surcharge"/"charged extra amount" (billing
    language, not battery language), and `low_range` (the network's own
    battery-range category, just named differently) was wrongly flagged
    against itself. After fixing both, the mismatch rate was genuinely
    zero -- category assignment shows clean vocabulary separation, no
    evidence of mislabeling from this check.

    The honest, useful finding instead: per-category word frequency shows
    each category has its own rich, distinguishing vocabulary (e.g.
    "surcharge"/"charged extra" within billing_dispute vs. "range"/
    "battery" within low_range) -- free text does carry additional signal
    beyond the categorical field, even though the field itself checks out.
    """
    import re
    from collections import Counter

    con = _con()
    df = con.execute(f"""
        SELECT category, rider_comment
        FROM '{SUPPORT_TICKETS_CLEAN.as_posix()}'
        WHERE rider_comment IS NOT NULL
    """).df()

    stopwords = set(
        "the a an is are was were i my me to of and or in on at for with hai ka ki ke "
        "ho gaya nahi bhi se bohot kam mil raha aaj usual bina bataye than extra amount "
        "this but sab since not".split()
    )

    top_words_by_category = {}
    for cat in df["category"].unique():
        texts = df.loc[df["category"] == cat, "rider_comment"].str.lower()
        counts = Counter()
        for t in texts.dropna():
            toks = re.findall(r"[a-z]+", t)
            counts.update(w for w in toks if w not in stopwords and len(w) > 2)
        top_words_by_category[cat] = counts.most_common(6)

    return {
        "top_words_by_category": top_words_by_category,
        "n_total": len(df),
    }


# ---------------------------------------------------------------------------
# Q4: Asset KPIs (battery SOH stats, degradation rate by supplier/lot)
# ---------------------------------------------------------------------------
def battery_degradation() -> pd.DataFrame:
    con = _con()
    df = con.execute(f"""
        SELECT
            supplier,
            manufacturing_lot,
            COUNT(*) AS n_batteries,
            AVG(initial_soh_pct) AS avg_initial_soh,
            AVG(current_soh_pct) AS avg_current_soh,
            AVG(
                (initial_soh_pct - current_soh_pct)
                / NULLIF(date_diff('day', CAST(manufacture_date AS DATE), COALESCE(CAST(retired_date AS DATE), CURRENT_DATE)), 0)
            ) AS avg_degradation_rate_per_day
        FROM '{BATTERIES_CLEAN.as_posix()}'
        GROUP BY supplier, manufacturing_lot
        ORDER BY avg_degradation_rate_per_day DESC
    """).df()
    return df


if __name__ == "__main__":
    print("Q1 network_kpis_monthly:")
    q1 = network_kpis_monthly()
    print(q1.to_string())

    print("\nQ3 station_segmentation:")
    q3 = station_segmentation()
    print(q3.to_string())

    print("\nQ2 service_kpis (by station_id, first 5):")
    q2 = service_kpis(group_cols=("station_id",))
    print(q2.head().to_string())

    print("\nQ6 retention_cohorts (shape + return rate):")
    q6 = retention_cohorts()
    print("rows:", len(q6), "overall return rate:", q6["returned_within_window"].mean())

    print("\nQ4 battery_degradation:")
    q4 = battery_degradation()
    print(q4.to_string())
