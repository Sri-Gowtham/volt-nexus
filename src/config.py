"""Locked definitions for the VoltRelay hackathon analysis.

Every module must import these rather than re-deriving them inline.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (relative to repo root; Colab-safe — no absolute Windows paths)
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
FIGURES_DIR = ROOT_DIR / "outputs" / "figures"
REPORT_DATA_DIR = ROOT_DIR / "outputs" / "report_data"

SWAP_EVENTS_CSV = RAW_DIR / "swap_events.csv"
STATION_HOURLY_STATUS_CSV = RAW_DIR / "station_hourly_status.csv"
RIDERS_CSV = RAW_DIR / "riders.csv"
BATTERIES_CSV = RAW_DIR / "batteries.csv"
SUPPORT_TICKETS_CSV = RAW_DIR / "support_tickets.csv"
STATIONS_CSV = RAW_DIR / "stations.csv"
CITY_DAILY_CONTEXT_CSV = RAW_DIR / "city_daily_context.csv"
FLEET_PARTNERS_CSV = RAW_DIR / "fleet_partners.csv"

SWAP_EVENTS_CLEAN = PROCESSED_DIR / "swap_events_clean.parquet"
STATION_HOURLY_STATUS_CLEAN = PROCESSED_DIR / "station_hourly_status_clean.parquet"
RIDERS_CLEAN = PROCESSED_DIR / "riders_clean.parquet"
BATTERIES_CLEAN = PROCESSED_DIR / "batteries_clean.parquet"
SUPPORT_TICKETS_CLEAN = PROCESSED_DIR / "support_tickets_clean.parquet"
STATIONS_CLEAN = PROCESSED_DIR / "stations_clean.parquet"
CITY_DAILY_CONTEXT_CLEAN = PROCESSED_DIR / "city_daily_context_clean.parquet"
FLEET_PARTNERS_CLEAN = PROCESSED_DIR / "fleet_partners_clean.parquet"

# ---------------------------------------------------------------------------
# Dedup rule
# ---------------------------------------------------------------------------
# Same rider_id + station_id + battery_in_id, timestamps within this many
# seconds of each other -> treat as one attempt, keep the first occurrence.
# Only applies to rows with a non-null battery_in_id (i.e. completed swaps).
# Non-completed attempts (failed/abandoned/cancelled, battery_in_id is null)
# are deduped on (rider_id, station_id, event_type) within the same window
# instead, since they have no battery_in_id to key on.
DEDUP_WINDOW_SECONDS = 120

# ---------------------------------------------------------------------------
# Retention window
# ---------------------------------------------------------------------------
# New rider = first swap event (any event_type, including failed/abandoned
# attempts) in the dataset. "Returned" = >=1 completed swap within this many
# days after that first event.
RETENTION_WINDOW_DAYS = 30

# ---------------------------------------------------------------------------
# Firmware timestamp bug fix
# ---------------------------------------------------------------------------
# swap_events at stations on firmware v3.2.0 between these dates have
# event_ts ~5h30m earlier than true local time -> add 5.5h to event_ts.
# Window is treated as inclusive on both ends.
FIRMWARE_TIMESTAMP_BUG_VERSION = "v3.2.0"
FIRMWARE_TIMESTAMP_BUG_START = "2025-03-10"
FIRMWARE_TIMESTAMP_BUG_END = "2025-04-14"
FIRMWARE_TIMESTAMP_BUG_OFFSET_HOURS = 5.5

# ---------------------------------------------------------------------------
# Contribution margin
# ---------------------------------------------------------------------------
# CONTRIBUTION_MARGIN = amount_charged_inr
#                       - (energy_to_recharge_kwh * grid_tariff_inr_kwh)
#                       - battery_wear_cost_proxy
#                       - allocated_station_cost_per_swap
#
# battery_wear_cost_proxy = purchase_cost_inr / ASSUMED_CYCLE_LIFE
# No cycle-life column exists in batteries.csv; 1500 cycles is a standard
# assumption for LFP swap-network packs. Override here if a better number
# becomes available.
ASSUMED_CYCLE_LIFE = 1500

# allocated_station_cost_per_swap = (monthly_rent_inr + monthly_maintenance_inr)
#   for the station, divided across that station's completed swaps in the
#   same calendar month (computed in kpis.py via a station<->swap_events
#   monthly join — not a raw column).

# ---------------------------------------------------------------------------
# STN-TST internal test stations
# ---------------------------------------------------------------------------
# stations.csv has no boolean flag column; test stations are identified by
# a station_id prefix. Verified against real data in clean.py's first run.
TEST_STATION_PREFIX = "STN-TST"

# ---------------------------------------------------------------------------
# Canonical city names (riders.home_city has spelling variants to map to
# these six; the actual variant->canonical mapping is built in clean.py
# after inspecting the real distinct values)
# ---------------------------------------------------------------------------
CANONICAL_CITIES = [
    "Bengaluru",
    "Delhi NCR",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Jaipur",
]
