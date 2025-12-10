#!/usr/bin/env python3
"""
Data Fetcher for Energy-Climate Correlation Map
Fetches energy demand data from EIA API and climate data from Open-Meteo API.

Features:
- Intelligent API switching: Open-Meteo Forecast API (<92 days) vs Historical API
- Retry logic with exponential backoff
- Backfill capability for missing data gaps
- All 8 climate variables

Usage:
    python fetch_data.py                    # Fetch latest month
    python fetch_data.py --month 2024-01    # Fetch specific month
    python fetch_data.py --backfill         # Backfill all missing data

Environment Variables:
    EIA_API_KEY: API key for EIA (required)
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path

# configuration
EIA_API_KEY = os.environ.get('EIA_API_KEY')
if not EIA_API_KEY:
    # try loading from .env file
    env_file = Path(__file__).parent.parent / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith('EIA_API_KEY='):
                    EIA_API_KEY = line.strip().split('=', 1)[1]
                    break
    if not EIA_API_KEY:
        raise ValueError("EIA_API_KEY not set. Create .env file or export EIA_API_KEY")
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 0.1  # seconds between requests

# open-meteo api limits
FORECAST_API_DAYS_LIMIT = 92

# climate variables to fetch
CLIMATE_PARAMS = [
    'temperature_2m',
    'relative_humidity_2m',
    'surface_pressure',
    'cloud_cover',
    'direct_radiation',
    'precipitation',
    'wind_speed_10m',
    'wind_direction_10m'
]

# region coordinates
REGION_COORDS = {
    # major isos/rtos
    'PJM': (40.0, -78.0), 'MISO': (42.0, -89.0), 'CISO': (36.7, -119.7),
    'NYIS': (42.9, -75.5), 'ISNE': (42.4, -71.4), 'SWPP': (37.5, -97.0),
    'ERCO': (31.0, -100.0),
    # western
    'BPAT': (45.5, -121.5), 'PACW': (42.0, -122.5), 'PACE': (41.7, -111.9),
    'WACM': (40.4, -105.0), 'WALC': (35.5, -112.0), 'WAUW': (46.0, -103.0),
    'NWMT': (46.6, -112.0), 'IPCO': (43.6, -116.2), 'AVA': (47.7, -117.4),
    'PSEI': (47.5, -122.0), 'SCL': (47.6, -122.3), 'TPWR': (47.3, -122.5),
    'PGE': (45.5, -122.7), 'CHPD': (47.9, -120.2), 'DOPD': (47.7, -119.8),
    'GCPD': (47.1, -119.3), 'BANC': (38.9, -121.8), 'TIDC': (37.5, -120.8),
    'LDWP': (34.1, -118.2), 'IID': (33.0, -115.5),
    # southwest
    'AZPS': (34.5, -112.0), 'SRP': (33.4, -111.9), 'TEPC': (32.2, -110.9),
    'EPE': (31.8, -106.4), 'PNM': (35.1, -106.6), 'NEVP': (36.2, -115.1),
    'DEAA': (33.4, -112.8), 'HGMA': (33.6, -113.3),
    # central/mountain
    'PSCO': (39.7, -105.0), 'SPA': (35.5, -97.0), 'AECI': (38.5, -92.5),
    'GWA': (47.0, -109.0), 'WWA': (45.5, -109.0),
    # southeast
    'TVA': (35.5, -86.0), 'SOCO': (33.0, -84.5), 'DUK': (35.5, -80.5),
    'CPLE': (35.0, -77.5), 'CPLW': (35.5, -79.0), 'SC': (33.5, -80.5),
    'SCEG': (34.0, -81.0), 'AEC': (31.5, -87.0), 'SEPA': (34.5, -85.0),
    # florida
    'FPL': (27.0, -80.5), 'FPC': (28.5, -82.0), 'TEC': (27.9, -82.5),
    'JEA': (30.3, -81.7), 'SEC': (28.5, -81.5), 'FMPP': (28.5, -81.8),
    'GVL': (29.7, -82.3), 'TAL': (30.4, -84.3), 'HST': (25.5, -80.5),
    'NSB': (29.0, -80.9),
    # other
    'YAD': (35.8, -80.5), 'LGEE': (38.0, -85.5), 'EEI': (38.7, -90.0),
    'AVRN': (43.0, -77.0), 'GRIF': (40.0, -85.0), 'GRID': (38.0, -97.0),
    'GLHB': (38.0, -95.0),
}


def get_openmeteo_api_config(start_date, end_date):
    """
    Determine which Open-Meteo API to use and adjust dates if needed.
    - Historical API: data older than 92 days (supports any past date range)
    - Forecast API: recent data within 92 days (limited future dates)

    Returns: (base_url, adjusted_start_date, adjusted_end_date)
    """
    today = datetime.now().date()
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
    cutoff = today - timedelta(days=FORECAST_API_DAYS_LIMIT)

    # if end date is more than 92 days ago, use historical API
    if end_dt < cutoff:
        return ("https://archive-api.open-meteo.com/v1/archive", start_date, end_date)

    # if start date is more than 92 days ago, use historical API
    # (it can handle recent dates too, just slower)
    if start_dt < cutoff:
        return ("https://archive-api.open-meteo.com/v1/archive", start_date, end_date)

    # use forecast API for recent data, but cap end_date to today
    # (forecast API doesn't reliably support future dates for historical vars)
    adjusted_end = min(end_dt, today).strftime('%Y-%m-%d')

    return ("https://api.open-meteo.com/v1/forecast", start_date, adjusted_end)


def fetch_with_retry(url, params=None, max_retries=MAX_RETRIES):
    """
    Fetch URL with retry logic and exponential backoff.
    Only retries on transient errors (5xx, timeouts, connection issues).
    Does NOT retry on client errors (4xx) since those won't be fixed by retrying.
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # don't retry on 4xx client errors - request is bad
            if response.status_code < 500:
                print(f"    Client error {response.status_code}: {e}")
                return None
            # retry on 5xx server errors
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"    Server error, retry {attempt + 1}/{max_retries} in {wait_time}s")
                time.sleep(wait_time)
            else:
                print(f"    Failed after {max_retries} attempts: {e}")
                return None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            # retry on timeouts and connection errors
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"    {type(e).__name__}, retry {attempt + 1}/{max_retries} in {wait_time}s")
                time.sleep(wait_time)
            else:
                print(f"    Failed after {max_retries} attempts: {e}")
                return None
        except requests.RequestException as e:
            # other errors - don't retry
            print(f"    Request error: {e}")
            return None

    return None


def fetch_energy_data(region, start_date, end_date):
    """
    Fetch energy demand data from EIA API.
    """
    url = "https://api.eia.gov/v2/electricity/rto/region-data/data/"

    params = {
        'frequency': 'hourly',
        'data[0]': 'value',
        'facets[respondent][]': region,
        'start': f"{start_date}T00",
        'end': f"{end_date}T23",
        'sort[0][column]': 'period',
        'sort[0][direction]': 'asc',
        'offset': 0,
        'length': 5000,
        'api_key': EIA_API_KEY
    }

    return fetch_with_retry(url, params)


def fetch_climate_data(lat, lng, start_date, end_date):
    """
    Fetch climate data from Open-Meteo API.
    Automatically switches between Historical and Forecast APIs.
    Adjusts date range to avoid requesting future dates.
    """
    base_url, adj_start, adj_end = get_openmeteo_api_config(start_date, end_date)

    # skip if adjusted dates result in invalid range
    if adj_start > adj_end:
        print(f"    Skipping - date range not yet available")
        return None

    params = {
        'latitude': lat,
        'longitude': lng,
        'start_date': adj_start,
        'end_date': adj_end,
        'hourly': ','.join(CLIMATE_PARAMS),
        'timezone': 'GMT'  # use GMT as per Open-Meteo docs
    }

    return fetch_with_retry(base_url, params)


def validate_json_file(filepath):
    """
    Check if file exists and contains valid JSON.
    """
    try:
        if not os.path.exists(filepath):
            return False
        with open(filepath, 'r') as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, IOError):
        return False


def fetch_month_data(year, month, data_dir='data/raw_data'):
    """
    Fetch all data for a specific month.
    """
    month_str = f"{year}-{month:02d}"
    month_dir = Path(data_dir) / month_str
    month_dir.mkdir(parents=True, exist_ok=True)

    # calculate date range
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year}-12-31"
    else:
        next_month = datetime(year, month + 1, 1) - timedelta(days=1)
        end_date = next_month.strftime('%Y-%m-%d')

    print(f"\nFetching data for {month_str}")
    print(f"Date range: {start_date} to {end_date}")

    energy_success = 0
    energy_skip = 0
    climate_success = 0
    climate_skip = 0

    for region, (lat, lng) in REGION_COORDS.items():
        # fetch energy data
        energy_file = month_dir / f"{region}-energy.json"
        if validate_json_file(energy_file):
            energy_skip += 1
        else:
            print(f"  Fetching {region} energy...", end='', flush=True)
            data = fetch_energy_data(region, start_date, end_date)
            if data:
                with open(energy_file, 'w') as f:
                    json.dump(data, f)
                print(" OK")
                energy_success += 1
            else:
                print(" FAILED")
            time.sleep(RATE_LIMIT_DELAY)

        # fetch climate data
        climate_file = month_dir / f"{region}-climate.json"
        if validate_json_file(climate_file):
            climate_skip += 1
        else:
            print(f"  Fetching {region} climate...", end='', flush=True)
            data = fetch_climate_data(lat, lng, start_date, end_date)
            if data:
                with open(climate_file, 'w') as f:
                    json.dump(data, f)
                print(" OK")
                climate_success += 1
            else:
                print(" FAILED")
            time.sleep(RATE_LIMIT_DELAY)

    print(f"\nSummary for {month_str}:")
    print(f"  Energy: {energy_success} fetched, {energy_skip} skipped")
    print(f"  Climate: {climate_success} fetched, {climate_skip} skipped")


def fetch_all_historical(data_dir='data/raw_data', start_year=2020):
    """
    Fetch all data from start_year to present.
    """
    now = datetime.now()
    current_year = now.year
    current_month = now.month

    for year in range(start_year, current_year + 1):
        # for current year, only fetch up to current month
        end_month = current_month if year == current_year else 12
        for month in range(1, end_month + 1):
            fetch_month_data(year, month, data_dir)


def main():
    parser = argparse.ArgumentParser(description='Fetch energy and climate data')
    parser.add_argument('--month', help='Month to fetch (YYYY-MM format)')
    parser.add_argument('--all', action='store_true', help='Fetch all data from 2020 to present')
    parser.add_argument('--start-year', type=int, default=2020, help='Start year for --all (default: 2020)')
    parser.add_argument('--data-dir', default='data/raw_data', help='Raw data directory')

    args = parser.parse_args()

    if args.all:
        fetch_all_historical(args.data_dir, args.start_year)
    elif args.month:
        try:
            year, month = map(int, args.month.split('-'))
            fetch_month_data(year, month, args.data_dir)
        except ValueError:
            print("Error: Invalid month format. Use YYYY-MM")
            sys.exit(1)
    else:
        # default: fetch current month
        now = datetime.now()
        fetch_month_data(now.year, now.month, args.data_dir)


if __name__ == '__main__':
    main()
