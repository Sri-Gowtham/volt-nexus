"""Cleaning pipeline for the VoltRelay hackathon dataset.

swap_events.csv and station_hourly_status.csv are handled via DuckDB
querying the CSV directly off disk (never loaded fully into pandas) and
written out as cleaned Parquet files. The other six (small) CSVs are
handled with plain pandas.

Run directly (`python src/clean.py`) to execute the full pipeline and
print before/after row counts at each step.
"""

import duckdb
import pandas as pd

from config import (
    RAW_DIR,
    PROCESSED_DIR,
    SWAP_EVENTS_CSV,
    STATION_HOURLY_STATUS_CSV,
    RIDERS_CSV,
    BATTERIES_CSV,
    SUPPORT_TICKETS_CSV,
    STATIONS_CSV,
    CITY_DAILY_CONTEXT_CSV,
    FLEET_PARTNERS_CSV,
    SWAP_EVENTS_CLEAN,
    STATION_HOURLY_STATUS_CLEAN,
    RIDERS_CLEAN,
    BATTERIES_CLEAN,
    SUPPORT_TICKETS_CLEAN,
    STATIONS_CLEAN,
    CITY_DAILY_CONTEXT_CLEAN,
    FLEET_PARTNERS_CLEAN,
    DEDUP_WINDOW_SECONDS,
    FIRMWARE_TIMESTAMP_BUG_VERSION,
    FIRMWARE_TIMESTAMP_BUG_START,
    FIRMWARE_TIMESTAMP_BUG_END,
    FIRMWARE_TIMESTAMP_BUG_OFFSET_HOURS,
    TEST_STATION_PREFIX,
    CANONICAL_CITIES,
)

# swap_events.csv has mixed \r\n / \n line endings which breaks DuckDB's
# CSV dialect auto-sniff -> must read with strict_mode disabled.
SWAP_EVENTS_READ = (
    f"read_csv('{SWAP_EVENTS_CSV.as_posix()}', delim=',', quote='\"', "
    f"header=true, strict_mode=false)"
)

# Known city-name variants -> canonical name (from inspecting real
# riders.home_city distinct values).
CITY_VARIANT_MAP = {
    "Bengaluru": "Bengaluru", "bengaluru": "Bengaluru", "Bangalore": "Bengaluru",
    "BLR": "Bengaluru",
    "Delhi NCR": "Delhi NCR", "New Delhi": "Delhi NCR", "Delhi": "Delhi NCR",
    "Gurgaon": "Delhi NCR",
    "Hyderabad": "Hyderabad", "hyderabad": "Hyderabad", "Hyd": "Hyderabad",
    "HYD": "Hyderabad",
    "Pune": "Pune", "pune": "Pune", "PUN": "Pune",
    "Mumbai": "Mumbai", "Bombay": "Mumbai", "MUM": "Mumbai",
    "Jaipur": "Jaipur", "jaipur": "Jaipur", "JAI": "Jaipur",
}


def _log_count(label, n):
    print(f"  {label}: {n:,} rows")


def clean_swap_events(con: duckdb.DuckDBPyConnection) -> None:
    print("\n[swap_events.csv] cleaning via DuckDB (never loaded fully into pandas)")
    raw_count = con.execute(f"SELECT COUNT(*) FROM {SWAP_EVENTS_READ}").fetchone()[0]
    _log_count("raw rows", raw_count)

    # Step 1: firmware timestamp fix, outlier/anomaly flags -- materialized
    # as a real DuckDB table (not a lazy Python-side Arrow reader, which
    # would self-deadlock the connection when queried again below).
    con.execute("DROP TABLE IF EXISTS swap_fixed")
    con.execute(f"""
        CREATE TABLE swap_fixed AS
        SELECT
            *,
            CASE
                WHEN station_firmware = '{FIRMWARE_TIMESTAMP_BUG_VERSION}'
                     AND event_ts BETWEEN
                         TIMESTAMP '{FIRMWARE_TIMESTAMP_BUG_START}'
                         AND TIMESTAMP '{FIRMWARE_TIMESTAMP_BUG_END} 23:59:59'
                THEN event_ts + INTERVAL '{FIRMWARE_TIMESTAMP_BUG_OFFSET_HOURS} hours'
                ELSE event_ts
            END AS event_ts_fixed,
            (km_since_last_swap < 0 OR km_since_last_swap > 500) AS is_km_outlier,
            (soc_in_pct > 100 OR soc_out_pct > 100 OR soh_in_pct > 100 OR soh_out_pct > 100)
                AS is_soc_soh_over_100,
            (station_id LIKE '{TEST_STATION_PREFIX}%') AS is_test_station
        FROM {SWAP_EVENTS_READ}
    """)
    n = con.execute("SELECT COUNT(*) FROM swap_fixed").fetchone()[0]
    _log_count("after firmware-fix + flags", n)

    # Step 2: dedup.
    # Completed swaps: key on (rider_id, station_id, battery_in_id), keep
    # first occurrence within DEDUP_WINDOW_SECONDS.
    # Non-completed attempts have null battery_in_id, so they are deduped
    # on (rider_id, station_id, event_type) instead within the same window.
    con.execute("DROP TABLE IF EXISTS swap_deduped")
    con.execute(f"""
        CREATE TABLE swap_deduped AS
        WITH ordered AS (
            SELECT *,
                CASE WHEN battery_in_id IS NOT NULL
                     THEN rider_id || '|' || station_id || '|' || battery_in_id
                     ELSE rider_id || '|' || station_id || '|' || event_type
                END AS dedup_key,
                LAG(event_ts_fixed) OVER (
                    PARTITION BY CASE WHEN battery_in_id IS NOT NULL
                        THEN rider_id || '|' || station_id || '|' || battery_in_id
                        ELSE rider_id || '|' || station_id || '|' || event_type
                    END
                    ORDER BY event_ts_fixed
                ) AS prev_ts
            FROM swap_fixed
        ),
        flagged AS (
            SELECT *,
                CASE
                    WHEN prev_ts IS NOT NULL
                         AND date_diff('second', prev_ts, event_ts_fixed) <= {DEDUP_WINDOW_SECONDS}
                    THEN 1 ELSE 0
                END AS is_dup_followup
            FROM ordered
        )
        SELECT * EXCLUDE (dedup_key, prev_ts, is_dup_followup)
        FROM flagged
        WHERE is_dup_followup = 0
    """)
    n2 = con.execute("SELECT COUNT(*) FROM swap_deduped").fetchone()[0]
    _log_count("after dedup", n2)
    print(f"  dropped as near-duplicates: {n - n2:,}")

    con.execute(f"""
        COPY (SELECT * FROM swap_deduped)
        TO '{SWAP_EVENTS_CLEAN.as_posix()}' (FORMAT PARQUET)
    """)
    print(f"  wrote {SWAP_EVENTS_CLEAN}")
    con.execute("DROP TABLE swap_fixed")
    con.execute("DROP TABLE swap_deduped")


def clean_station_hourly_status(con: duckdb.DuckDBPyConnection) -> None:
    print("\n[station_hourly_status.csv] cleaning via DuckDB")
    src = f"read_csv_auto('{STATION_HOURLY_STATUS_CSV.as_posix()}')"
    raw_count = con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]
    _log_count("raw rows", raw_count)

    # telemetry_status partial/missing already yields NaN for blank numeric
    # fields when DuckDB reads the CSV (empty string -> NULL for numeric
    # columns) -- verified no coercion to 0 happens here.
    con.execute(f"""
        COPY (SELECT * FROM {src})
        TO '{STATION_HOURLY_STATUS_CLEAN.as_posix()}' (FORMAT PARQUET)
    """)
    _log_count("after cleaning (no drops; NaNs preserved)", raw_count)
    print(f"  wrote {STATION_HOURLY_STATUS_CLEAN}")


def clean_riders() -> None:
    print("\n[riders.csv] cleaning via pandas")
    df = pd.read_csv(RIDERS_CSV)
    _log_count("raw rows", len(df))

    df["home_city"] = df["home_city"].str.strip()
    unmapped = set(df["home_city"].unique()) - set(CITY_VARIANT_MAP)
    if unmapped:
        print(f"  WARNING: unmapped home_city values found: {unmapped}")
    df["home_city"] = df["home_city"].map(CITY_VARIANT_MAP).fillna(df["home_city"])
    assert set(df["home_city"].unique()) <= set(CANONICAL_CITIES), "city standardization incomplete"

    _log_count("after city standardization", len(df))
    df.to_parquet(RIDERS_CLEAN, index=False)
    print(f"  wrote {RIDERS_CLEAN}")


def clean_batteries() -> None:
    print("\n[batteries.csv] cleaning via pandas")
    df = pd.read_csv(BATTERIES_CSV)
    _log_count("raw rows", len(df))
    df["is_soh_over_100"] = df["current_soh_pct"] > 100
    _log_count("after flagging SOH>100", len(df))
    df.to_parquet(BATTERIES_CLEAN, index=False)
    print(f"  wrote {BATTERIES_CLEAN}")


def clean_support_tickets() -> None:
    print("\n[support_tickets.csv] cleaning via pandas")
    df = pd.read_csv(SUPPORT_TICKETS_CSV)
    _log_count("raw rows", len(df))
    # csat_score MNAR: leave as-is (NaN where missing), never impute/fill.
    df.to_parquet(SUPPORT_TICKETS_CLEAN, index=False)
    print(f"  wrote {SUPPORT_TICKETS_CLEAN}")


def clean_stations() -> None:
    print("\n[stations.csv] cleaning via pandas")
    df = pd.read_csv(STATIONS_CSV)
    _log_count("raw rows", len(df))
    df["is_test_station"] = df["station_id"].str.startswith(TEST_STATION_PREFIX)
    n_test = df["is_test_station"].sum()
    print(f"  flagged {n_test} test stations (station_id prefix '{TEST_STATION_PREFIX}')")
    df.to_parquet(STATIONS_CLEAN, index=False)
    print(f"  wrote {STATIONS_CLEAN}")


def clean_city_daily_context() -> None:
    print("\n[city_daily_context.csv] cleaning via pandas")
    df = pd.read_csv(CITY_DAILY_CONTEXT_CSV)
    _log_count("raw rows", len(df))
    unmapped = set(df["city"].unique()) - set(CANONICAL_CITIES)
    if unmapped:
        print(f"  NOTE: city values not in canonical list: {unmapped}")
    df.to_parquet(CITY_DAILY_CONTEXT_CLEAN, index=False)
    print(f"  wrote {CITY_DAILY_CONTEXT_CLEAN}")


def clean_fleet_partners() -> None:
    print("\n[fleet_partners.csv] cleaning via pandas")
    df = pd.read_csv(FLEET_PARTNERS_CSV)
    _log_count("raw rows", len(df))
    df.to_parquet(FLEET_PARTNERS_CLEAN, index=False)
    print(f"  wrote {FLEET_PARTNERS_CLEAN}")


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    clean_swap_events(con)
    clean_station_hourly_status(con)
    clean_riders()
    clean_batteries()
    clean_support_tickets()
    clean_stations()
    clean_city_daily_context()
    clean_fleet_partners()
    print("\nAll cleaning steps complete.")


if __name__ == "__main__":
    main()
