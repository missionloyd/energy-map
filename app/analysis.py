#!/usr/bin/env python3
"""
Energy and Climate Correlation Analysis
Analyzes the relationship between energy demand and multiple climate variables

Method:
This script uses Spearman correlation coefficient to measure the monotonic
relationship between hourly energy demand and 8 climate variables:
  - Temperature (°C)
  - Relative Humidity (%)
  - Surface Pressure (hPa)
  - Cloud Cover (%)
  - Direct Solar Radiation (W/m²)
  - Precipitation (mm)
  - Wind Speed (m/s)
  - Wind Direction (°)

Timezone handling:
- Energy data (EIA): Using frequency=hourly for UTC timestamps
- Climate data (Open-Meteo): Set to timezone=UTC
- Both datasets use UTC timestamps for perfect alignment

Spearman Correlation (ρ or r):
- Measures monotonic relationships (not just linear)
- Works on ranked data, more robust to outliers and non-linear patterns
- Range: -1 to +1
  - r = +1: Perfect monotonic positive relationship
  - r = -1: Perfect monotonic negative relationship
  - r = 0: No monotonic relationship
- For temperature analysis:
  - Negative r means: colder temps = higher demand (heating load)
  - Positive r means: warmer temps = higher demand (cooling load)
- Better than Pearson for energy-climate because:
  - Captures non-linear relationships (e.g., exponential AC usage)
  - More robust to outliers and extreme weather events

R-squared (R²):
- Coefficient of determination
- Shows what percentage of variance in ranked data is explained
- Range: 0 to 1 (or 0% to 100%)
- Calculated as: R² = r²
- Interpretation:
  - R² = 0.50 means 50% of demand variation is explained by temperature ranking
  - R² = 0.10 means only 10% is explained (other factors dominate)

Strength interpretation:
- |r| < 0.3: weak correlation
- 0.3 <= |r| < 0.5: moderate correlation
- |r| >= 0.5: strong correlation

Usage:
  python3 analysis.py [--month MONTH] [--regions REGION1,REGION2,...]

  --month: Month number (01-12) or 'all' (default: 01)
  --regions: Comma-separated region codes or 'all' (default: all)

Examples:
  python3 analysis.py                           # Analyze all regions for January
  python3 analysis.py --month 07                # Analyze all regions for July
  python3 analysis.py --regions WACM,PACE,NWMT  # Analyze 3 regions for January
  python3 analysis.py --month all --regions PJM # Analyze PJM for all 12 months

Output:
  - Console summary with correlation statistics
  - data/images/{variable}_correlations.png: Scatter plots for top 6 correlations per variable
  - data/clean_data/*.json: 66 JSON files with multi-variable correlations for map visualization
  - data/stats_data/correlation_stats.csv: Correlation strength counts per variable
"""

import json
import os
import sys
import argparse
import numpy as np
from scipy.stats import spearmanr
from pathlib import Path
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # non-interactive backend
import matplotlib.pyplot as plt

# climate variables configuration
# maps variable name to Open-Meteo API parameter and display info
# colors match frontend CLIMATE_VARIABLES in energy-map.js
CLIMATE_VARIABLES = {
    'temperature': {
        'openmeteo_param': 'temperature_2m',
        'display_name': 'Temperature',
        'unit': 'C',
        'color': '#E74C3C',
        'description': 'Air temperature at 2 meters above ground'
    },
    'humidity': {
        'openmeteo_param': 'relative_humidity_2m',
        'display_name': 'Relative Humidity',
        'unit': '%',
        'color': '#3498DB',
        'description': 'Relative humidity at 2 meters'
    },
    'pressure': {
        'openmeteo_param': 'surface_pressure',
        'display_name': 'Surface Pressure',
        'unit': 'hPa',
        'color': '#9B59B6',
        'description': 'Atmospheric pressure at surface level'
    },
    'cloud_cover': {
        'openmeteo_param': 'cloud_cover',
        'display_name': 'Cloud Cover',
        'unit': '%',
        'color': '#95A5A6',
        'description': 'Total cloud cover percentage'
    },
    'solar_radiation': {
        'openmeteo_param': 'direct_radiation',
        'display_name': 'Direct Solar Radiation',
        'unit': 'W/m2',
        'color': '#F39C12',
        'description': 'Direct component of solar radiation'
    },
    'precipitation': {
        'openmeteo_param': 'precipitation',
        'display_name': 'Precipitation',
        'unit': 'mm',
        'color': '#1ABC9C',
        'description': 'Total precipitation sum'
    },
    'wind_speed': {
        'openmeteo_param': 'wind_speed_10m',
        'display_name': 'Wind Speed',
        'unit': 'm/s',
        'color': '#2ECC71',
        'description': 'Wind speed at 10 meters above ground'
    },
    'wind_direction': {
        'openmeteo_param': 'wind_direction_10m',
        'display_name': 'Wind Direction',
        'unit': 'deg',
        'color': '#E67E22',
        'description': 'Wind direction at 10 meters'
    }
}

# region coordinates and names
REGIONS = {
    # major ISOs/RTOs
    'PJM': {'name': 'PJM Interconnection', 'lat': 40.0, 'lng': -78.0},
    'MISO': {'name': 'Midcontinent ISO', 'lat': 42.0, 'lng': -89.0},
    'CISO': {'name': 'California ISO', 'lat': 36.7, 'lng': -119.7},
    'NYIS': {'name': 'New York ISO', 'lat': 42.9, 'lng': -75.5},
    'ISNE': {'name': 'ISO New England', 'lat': 42.4, 'lng': -71.4},
    'SWPP': {'name': 'Southwest Power Pool', 'lat': 37.5, 'lng': -97.0},
    'ERCO': {'name': 'ERCOT (Texas)', 'lat': 31.0, 'lng': -100.0},

    # western
    'BPAT': {'name': 'Bonneville Power Administration', 'lat': 45.5, 'lng': -121.5},
    'PACW': {'name': 'PacifiCorp West', 'lat': 42.0, 'lng': -122.5},
    'PACE': {'name': 'PacifiCorp East', 'lat': 41.7, 'lng': -111.9},
    'WACM': {'name': 'WAPA Rocky Mountain', 'lat': 40.4, 'lng': -105.0},
    'WALC': {'name': 'WAPA Desert Southwest', 'lat': 35.5, 'lng': -112.0},
    'WAUW': {'name': 'WAPA Upper Great Plains', 'lat': 46.0, 'lng': -103.0},
    'NWMT': {'name': 'NorthWestern Montana', 'lat': 46.6, 'lng': -112.0},
    'IPCO': {'name': 'Idaho Power', 'lat': 43.6, 'lng': -116.2},
    'AVA': {'name': 'Avista', 'lat': 47.7, 'lng': -117.4},
    'PSEI': {'name': 'Puget Sound Energy', 'lat': 47.5, 'lng': -122.0},
    'SCL': {'name': 'Seattle City Light', 'lat': 47.6, 'lng': -122.3},
    'TPWR': {'name': 'Tacoma Power', 'lat': 47.3, 'lng': -122.5},
    'PGE': {'name': 'Portland General Electric', 'lat': 45.5, 'lng': -122.7},
    'CHPD': {'name': 'Chelan County PUD', 'lat': 47.9, 'lng': -120.2},
    'DOPD': {'name': 'Douglas County PUD', 'lat': 47.7, 'lng': -119.8},
    'GCPD': {'name': 'Grant County PUD', 'lat': 47.1, 'lng': -119.3},
    'BANC': {'name': 'Balancing Authority of Northern California', 'lat': 38.9, 'lng': -121.8},
    'TIDC': {'name': 'Turlock Irrigation District', 'lat': 37.5, 'lng': -120.8},
    'LDWP': {'name': 'Los Angeles DWP', 'lat': 34.1, 'lng': -118.2},
    'IID': {'name': 'Imperial Irrigation District', 'lat': 33.0, 'lng': -115.5},

    # southwest
    'AZPS': {'name': 'Arizona Public Service', 'lat': 34.5, 'lng': -112.0},
    'SRP': {'name': 'Salt River Project', 'lat': 33.4, 'lng': -111.9},
    'TEPC': {'name': 'Tucson Electric Power', 'lat': 32.2, 'lng': -110.9},
    'EPE': {'name': 'El Paso Electric', 'lat': 31.8, 'lng': -106.4},
    'PNM': {'name': 'Public Service Company of New Mexico', 'lat': 35.1, 'lng': -106.6},
    'NEVP': {'name': 'Nevada Power', 'lat': 36.2, 'lng': -115.1},
    'DEAA': {'name': 'Arlington Valley LLC', 'lat': 33.4, 'lng': -112.8},
    'HGMA': {'name': 'New Harquahala Generating', 'lat': 33.6, 'lng': -113.3},

    # central/mountain
    'PSCO': {'name': 'Public Service Company of Colorado', 'lat': 39.7, 'lng': -105.0},
    'SPA': {'name': 'Southwestern Power Administration', 'lat': 35.5, 'lng': -97.0},
    'AECI': {'name': 'Associated Electric Cooperative', 'lat': 38.5, 'lng': -92.5},
    'GWA': {'name': 'NaturEner Power Watch', 'lat': 47.0, 'lng': -109.0},
    'WWA': {'name': 'NaturEner Wind Watch', 'lat': 45.5, 'lng': -109.0},

    # southeast
    'TVA': {'name': 'Tennessee Valley Authority', 'lat': 35.5, 'lng': -86.0},
    'SOCO': {'name': 'Southern Company', 'lat': 33.0, 'lng': -84.5},
    'DUK': {'name': 'Duke Energy Carolinas', 'lat': 35.5, 'lng': -80.5},
    'CPLE': {'name': 'Duke Energy Progress East', 'lat': 35.0, 'lng': -77.5},
    'CPLW': {'name': 'Duke Energy Progress West', 'lat': 35.5, 'lng': -79.0},
    'SC': {'name': 'Santee Cooper', 'lat': 33.5, 'lng': -80.5},
    'SCEG': {'name': 'Dominion Energy South Carolina', 'lat': 34.0, 'lng': -81.0},
    'AEC': {'name': 'PowerSouth Energy Cooperative', 'lat': 31.5, 'lng': -87.0},
    'SEPA': {'name': 'Southeastern Power Administration', 'lat': 34.5, 'lng': -85.0},

    # florida
    'FPL': {'name': 'Florida Power & Light', 'lat': 27.0, 'lng': -80.5},
    'FPC': {'name': 'Duke Energy Florida', 'lat': 28.5, 'lng': -82.0},
    'TEC': {'name': 'Tampa Electric', 'lat': 27.9, 'lng': -82.5},
    'JEA': {'name': 'JEA', 'lat': 30.3, 'lng': -81.7},
    'SEC': {'name': 'Seminole Electric Cooperative', 'lat': 28.5, 'lng': -81.5},
    'FMPP': {'name': 'Florida Municipal Power Pool', 'lat': 28.5, 'lng': -81.8},
    'GVL': {'name': 'Gainesville Regional Utilities', 'lat': 29.7, 'lng': -82.3},
    'TAL': {'name': 'City of Tallahassee', 'lat': 30.4, 'lng': -84.3},
    'HST': {'name': 'City of Homestead', 'lat': 25.5, 'lng': -80.5},
    'NSB': {'name': 'New Smyrna Beach Utilities', 'lat': 29.0, 'lng': -80.9},

    # other
    'YAD': {'name': 'Alcoa Power Generating - Yadkin', 'lat': 35.8, 'lng': -80.5},
    'LGEE': {'name': 'LG&E and KU Services', 'lat': 38.0, 'lng': -85.5},
    'EEI': {'name': 'Electric Energy Inc', 'lat': 38.7, 'lng': -90.0},
    'AVRN': {'name': 'Avangrid Renewables', 'lat': 43.0, 'lng': -77.0},
    'GRIF': {'name': 'Griffith Energy', 'lat': 40.0, 'lng': -85.0},
    'GRID': {'name': 'Gridforce Energy Management', 'lat': 38.0, 'lng': -97.0},
    'GLHB': {'name': 'GridLiance', 'lat': 38.0, 'lng': -95.0},
}

def load_energy_data(filename):
    """Load energy data from JSON file"""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        # only get actual demand values (type 'D'), not forecasts or generation
        # filter out None/null values
        values = [float(point['value']) for point in data['response']['data']
                  if point['type'] == 'D' and point['value'] is not None]
        return np.array(values)
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        return None

def load_climate_data(filename, variable='temperature'):
    """
    Load climate data from JSON file for a specific variable

    Args:
        filename: Path to climate JSON file
        variable: Climate variable key (e.g., 'temperature', 'humidity')

    Returns:
        numpy array of values or None if loading fails
    """
    try:
        with open(filename, 'r') as f:
            data = json.load(f)

        # get the Open-Meteo parameter name for this variable
        param = CLIMATE_VARIABLES[variable]['openmeteo_param']

        # extract the hourly data
        values = data['hourly'][param]

        # filter out None values and convert to float
        values = [float(v) if v is not None else np.nan for v in values]
        return np.array(values)
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        return None

def load_all_climate_data(filename):
    """
    Load all climate variables from JSON file

    Args:
        filename: Path to climate JSON file

    Returns:
        dict mapping variable names to numpy arrays, or None if loading fails
    """
    try:
        with open(filename, 'r') as f:
            data = json.load(f)

        result = {}
        for var_name, var_config in CLIMATE_VARIABLES.items():
            param = var_config['openmeteo_param']
            if param in data['hourly']:
                values = data['hourly'][param]
                values = [float(v) if v is not None else np.nan for v in values]
                result[var_name] = np.array(values)

        return result if result else None
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        return None

def load_temperature_data(filename):
    """Load temperature data from JSON file (legacy support)"""
    # check if this is a new multi-variable climate file or old temp-only file
    try:
        with open(filename, 'r') as f:
            data = json.load(f)

        # try new format first (climate.json with multiple variables)
        if 'hourly' in data and 'temperature_2m' in data['hourly']:
            temps = data['hourly']['temperature_2m']
            return np.array([float(t) if t is not None else np.nan for t in temps])

        return None
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        return None

def filter_outliers(x, y, lower_pct=1, upper_pct=99):
    """
    Filter paired data to remove outliers outside the percentile range.
    applies percentile filtering independently to both variables.

    Args:
        x: first array
        y: second array (same length as x)
        lower_pct: lower percentile cutoff (default 1)
        upper_pct: upper percentile cutoff (default 99)

    Returns:
        (filtered_x, filtered_y) arrays with outliers removed
    """
    x = np.array(x)
    y = np.array(y)

    # remove NaN values first
    valid_mask = ~(np.isnan(x) | np.isnan(y))
    x = x[valid_mask]
    y = y[valid_mask]

    if len(x) == 0:
        return x, y

    # calculate percentile bounds for both variables
    x_lower, x_upper = np.percentile(x, [lower_pct, upper_pct])
    y_lower, y_upper = np.percentile(y, [lower_pct, upper_pct])

    # keep only points within bounds for both variables
    mask = (x >= x_lower) & (x <= x_upper) & (y >= y_lower) & (y <= y_upper)

    return x[mask], y[mask]


def downsample_for_plot(x, y, max_points=5000):
    """
    Randomly downsample data for visualization while preserving distribution.

    Args:
        x: first array
        y: second array
        max_points: maximum number of points to keep

    Returns:
        (downsampled_x, downsampled_y)
    """
    if len(x) <= max_points:
        return x, y

    # random sample without replacement
    indices = np.random.choice(len(x), size=max_points, replace=False)
    return x[indices], y[indices]


def calculate_correlation(energy, temp):
    """
    Calculate Spearman correlation between energy demand and temperature.
    applies 1-99th percentile filtering for outlier removal.

    Returns: (corr_coef, r_squared, n) or None if calculation fails
    """
    if energy is None or temp is None:
        return None

    if len(energy) == 0 or len(temp) == 0:
        return None

    # match up the data - trim to shortest length
    n = min(len(energy), len(temp))
    energy_subset = energy[:n]
    temp_subset = temp[:n]

    # apply outlier removal (1-99th percentile)
    energy_filtered, temp_filtered = filter_outliers(energy_subset, temp_subset)

    if len(energy_filtered) < 100:
        return None

    # calculate Spearman correlation coefficient
    corr_coef, _ = spearmanr(energy_filtered, temp_filtered)

    # calculate R-squared (coefficient of determination)
    r_squared = corr_coef ** 2

    return (corr_coef, r_squared, len(energy_filtered))

def categorize_correlation(r):
    """Return correlation strength category using Cohen's guidelines"""
    abs_r = abs(r)
    if abs_r < 0.3:
        return "weak"
    elif abs_r < 0.5:
        return "moderate"
    else:
        return "strong"

def get_available_months():
    """Get list of available year-month directories in data/raw_data/"""
    data_dir = Path('data/raw_data')
    if not data_dir.exists():
        return []

    months = []
    for d in sorted(data_dir.iterdir()):
        if d.is_dir() and '-' in d.name:
            try:
                year, month = d.name.split('-')
                year = int(year)
                month = int(month)
                if 1 <= month <= 12:
                    months.append((year, month))
            except ValueError:
                continue
    return months

def get_available_regions(month_dir):
    """Get list of regions that have data files in the month directory"""
    if not os.path.exists(month_dir):
        return []

    regions = set()
    for file in os.listdir(month_dir):
        if file.endswith('-energy.json'):
            region = file.replace('-energy.json', '')
            # check if climate file exists (new format) or temp file (old format)
            climate_file = os.path.join(month_dir, f'{region}-climate.json')
            temp_file = os.path.join(month_dir, f'{region}-temp.json')
            if os.path.exists(climate_file) or os.path.exists(temp_file):
                regions.add(region.upper())

    return sorted(regions)

def get_climate_file(month_dir, region):
    """Get the climate data file path, preferring new format over old"""
    climate_file = os.path.join(month_dir, f'{region}-climate.json')
    temp_file = os.path.join(month_dir, f'{region}-temp.json')

    if os.path.exists(climate_file):
        return climate_file
    elif os.path.exists(temp_file):
        return temp_file
    return None

def analyze_region_month(region, year, month, verbose=False):
    """
    Analyze a single region for a single month

    Returns: dict with results or None if analysis fails
    """
    month_dir = f'data/raw_data/{year}-{month:02d}'
    energy_file = os.path.join(month_dir, f'{region}-energy.json')
    climate_file = get_climate_file(month_dir, region)

    energy = load_energy_data(energy_file)
    temp = load_temperature_data(climate_file) if climate_file else None

    result = calculate_correlation(energy, temp)

    if result is None:
        return None

    corr_coef, r_squared, n = result

    if verbose:
        print(f"\nRegion: {region} | Month: {year}-{month:02d}")
        print(f"Sample size: {n} hourly observations")
        print(f"Pearson correlation: {corr_coef:+.4f}")
        print(f"R² (variance explained): {r_squared:.4f} ({r_squared*100:.1f}%)")
        print(f"Strength: {categorize_correlation(corr_coef).capitalize()}")

        if corr_coef > 0:
            print("Direction: Positive (cooling load)")
        else:
            print("Direction: Negative (heating load)")

    return {
        'region': region,
        'year': year,
        'month': month,
        'r': corr_coef,
        'r2': r_squared,
        'n': n,
        'strength': categorize_correlation(corr_coef)
    }

def generate_clean_data_for_map():
    """
    Generate data/clean_data/ JSON files for map visualization
    Combines all available months for each region into correlations for all climate variables
    Also generates data/stats_data/correlation_stats.csv with strength counts per variable
    """
    os.makedirs('data/clean_data', exist_ok=True)
    os.makedirs('data/stats_data', exist_ok=True)

    available_months = get_available_months()
    if not available_months:
        print("Error: No data directories found in data/raw_data/")
        return

    print(f"\nGenerating Clean Data for Map (Multi-Variable)")
    print(f"Available data: {len(available_months)} month(s)")

    successful = 0
    failed = 0

    # track correlation strength counts per variable
    stats = {var: {'strong_negative': 0, 'strong_positive': 0, 'moderate': 0, 'weak': 0}
             for var in CLIMATE_VARIABLES.keys()}

    for region_code, region_info in sorted(REGIONS.items()):
        # combine all available months
        all_energy = []
        all_climate = {var: [] for var in CLIMATE_VARIABLES.keys()}

        for year, month in available_months:
            month_dir = f'data/raw_data/{year}-{month:02d}'
            energy_file = os.path.join(month_dir, f'{region_code}-energy.json')
            climate_file = get_climate_file(month_dir, region_code)

            energy = load_energy_data(energy_file)

            if energy is None or climate_file is None:
                continue

            # load all climate variables
            climate_data = load_all_climate_data(climate_file)

            # fallback for old temp-only files
            if climate_data is None:
                temp = load_temperature_data(climate_file)
                if temp is not None:
                    climate_data = {'temperature': temp}

            if climate_data is None:
                continue

            # determine the minimum length across energy and all available climate vars
            min_len = len(energy)
            for var_name, var_data in climate_data.items():
                if var_data is not None:
                    min_len = min(min_len, len(var_data))

            # extend the combined arrays
            all_energy.extend(energy[:min_len])
            for var_name in CLIMATE_VARIABLES.keys():
                if var_name in climate_data and climate_data[var_name] is not None:
                    all_climate[var_name].extend(climate_data[var_name][:min_len])

        # need sufficient data
        if len(all_energy) < 100:
            print(f"{region_code:8s} ... x Insufficient data")
            failed += 1
            continue

        all_energy = np.array(all_energy)

        # calculate correlations for each climate variable
        correlations = {}
        primary_r = None  # for temperature, used for display

        for var_name, var_config in CLIMATE_VARIABLES.items():
            if var_name not in all_climate or len(all_climate[var_name]) == 0:
                continue

            var_data = np.array(all_climate[var_name])

            # match lengths (should already be matched, but be safe)
            n = min(len(all_energy), len(var_data))
            energy_subset = all_energy[:n]
            var_subset = var_data[:n]

            # apply outlier removal (1-99th percentile filtering)
            energy_filtered, var_filtered = filter_outliers(energy_subset, var_subset)

            if len(energy_filtered) < 100:
                continue

            # calculate Spearman correlation on filtered data
            corr_coef, p_value = spearmanr(energy_filtered, var_filtered)
            r_squared = corr_coef ** 2
            strength = categorize_correlation(corr_coef)
            direction = "negative" if corr_coef < 0 else "positive"

            correlations[var_name] = {
                'r': round(corr_coef, 4),
                'r2': round(r_squared, 4),
                'strength': strength,
                'direction': direction,
                'n': len(energy_filtered),
                'mean': round(float(np.mean(var_filtered)), 2),
                'std': round(float(np.std(var_filtered, ddof=1)), 2)
            }

            # update stats counts
            if strength == 'strong':
                if corr_coef < 0:
                    stats[var_name]['strong_negative'] += 1
                else:
                    stats[var_name]['strong_positive'] += 1
            elif strength == 'moderate':
                stats[var_name]['moderate'] += 1
            else:
                stats[var_name]['weak'] += 1

            # keep track of temperature correlation for primary display
            if var_name == 'temperature':
                primary_r = corr_coef

        if not correlations:
            print(f"{region_code:8s} ... x No valid correlations")
            failed += 1
            continue

        # use temperature as primary if available, otherwise first available
        if primary_r is None and correlations:
            first_var = list(correlations.keys())[0]
            primary_r = correlations[first_var]['r']

        # build result JSON with new schema
        result = {
            'region': region_code,
            'name': region_info['name'],
            'lat': region_info['lat'],
            'lng': region_info['lng'],
            'last_updated': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'correlations': correlations,
            'energy_stats': {
                'mean': round(float(np.mean(all_energy)), 2),
                'std': round(float(np.std(all_energy, ddof=1)), 2)
            },
            # legacy fields for backward compatibility with existing frontend
            'r': correlations.get('temperature', {}).get('r', primary_r),
            'r2': correlations.get('temperature', {}).get('r2', primary_r ** 2 if primary_r else 0),
            'strength': correlations.get('temperature', {}).get('strength', categorize_correlation(primary_r) if primary_r else 'weak'),
            'direction': correlations.get('temperature', {}).get('direction', 'positive'),
            'n_observations': correlations.get('temperature', {}).get('n', len(all_energy)),
        }

        output_file = f'data/clean_data/{region_code}.json'
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        temp_r = correlations.get('temperature', {}).get('r', 0)
        temp_strength = correlations.get('temperature', {}).get('strength', 'N/A')
        num_vars = len(correlations)
        print(f"{region_code:8s} ... ok temp r={temp_r:+.3f} ({temp_strength}), {num_vars} variables")
        successful += 1

    print(f"\nComplete: {successful} regions processed, {failed} failed")

    # write stats CSV
    stats_file = 'data/stats_data/correlation_stats.csv'
    with open(stats_file, 'w') as f:
        f.write('variable,strong_negative,strong_positive,moderate,weak\n')
        for var_name in CLIMATE_VARIABLES.keys():
            s = stats[var_name]
            f.write(f"{var_name},{s['strong_negative']},{s['strong_positive']},{s['moderate']},{s['weak']}\n")
    print(f"Stats saved to {stats_file}")

def create_correlation_plots(results):
    """
    Create correlation scatter plots for each climate variable.
    generates one image per variable showing top 6 strongest correlations.
    uses variable-specific colors from CLIMATE_VARIABLES config.

    Args:
        results: List of result dicts with 'region', 'month', 'r', 'r2', 'strength'
    """
    # create images directory if it doesn't exist
    os.makedirs('data/images', exist_ok=True)

    # get available months for loading data
    available_months = get_available_months()
    if not available_months:
        print("No data available for plotting")
        return

    print("\nGenerating correlation plots per climate variable...")

    for var_name, var_config in CLIMATE_VARIABLES.items():
        # collect correlation data for this variable across all regions
        var_correlations = []

        for region_code in REGIONS.keys():
            # load all data for this region
            all_energy = []
            all_climate = []

            for year, month in available_months:
                month_dir = f'data/raw_data/{year}-{month:02d}'
                energy_file = os.path.join(month_dir, f'{region_code}-energy.json')
                climate_file = get_climate_file(month_dir, region_code)

                if not climate_file:
                    continue

                energy = load_energy_data(energy_file)
                climate_data = load_climate_data(climate_file, var_name)

                if energy is None or climate_data is None:
                    continue

                min_len = min(len(energy), len(climate_data))
                all_energy.extend(energy[:min_len])
                all_climate.extend(climate_data[:min_len])

            if len(all_energy) < 100:
                continue

            # apply outlier removal (1-99th percentile filtering)
            energy_arr = np.array(all_energy)
            climate_arr = np.array(all_climate)
            energy_filtered, climate_filtered = filter_outliers(energy_arr, climate_arr)

            if len(energy_filtered) < 100:
                continue

            # calculate Spearman correlation on full filtered data
            corr_coef, _ = spearmanr(energy_filtered, climate_filtered)
            r_squared = corr_coef ** 2

            var_correlations.append({
                'region': region_code,
                'r': corr_coef,
                'r2': r_squared,
                'energy': energy_filtered,
                'climate': climate_filtered
            })

        if not var_correlations:
            print(f"  {var_name}: no data")
            continue

        # sort by absolute correlation strength
        var_correlations = sorted(var_correlations, key=lambda x: abs(x['r']), reverse=True)

        # create plot with top 6 correlations
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        axes = axes.flatten()
        color = var_config['color']
        display_name = var_config['display_name']
        unit = var_config['unit']

        for idx, corr_data in enumerate(var_correlations[:6]):
            energy = corr_data['energy']
            climate = corr_data['climate']
            region_code = corr_data['region']
            r = corr_data['r']
            r2 = corr_data['r2']

            # downsample for plot (keep full data for trend line calculation)
            climate_plot, energy_plot = downsample_for_plot(climate, energy, max_points=3000)

            # scatter plot with variable color (downsampled)
            axes[idx].scatter(climate_plot, energy_plot, alpha=0.3, s=10, c=color)

            # trend line (calculated on full filtered data)
            z = np.polyfit(climate, energy, 1)
            p = np.poly1d(z)
            x_line = np.linspace(np.min(climate), np.max(climate), 100)
            axes[idx].plot(x_line, p(x_line), color='#333333', linewidth=2)

            # get region name
            region_name = REGIONS.get(region_code, {}).get('name', region_code)
            strength = categorize_correlation(r)

            axes[idx].set_xlabel(f'{display_name} ({unit})')
            axes[idx].set_ylabel('Demand (MW)')
            axes[idx].set_title(f'{region_name} ({region_code})\nr={r:+.3f}, R²={r2*100:.1f}%, {strength}')
            axes[idx].grid(True, alpha=0.3)

        # hide unused subplots
        for idx in range(len(var_correlations[:6]), 6):
            axes[idx].set_visible(False)

        fig.suptitle(f'{display_name} vs Energy Demand - Top Correlations', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(f'data/images/{var_name}_correlations.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  {var_name}: saved data/images/{var_name}_correlations.png ({len(var_correlations[:6])} regions)")

def main():
    parser = argparse.ArgumentParser(
        description='Analyze energy-temperature correlations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # All regions, January
  %(prog)s --month 07                # All regions, July
  %(prog)s --regions WACM,PACE,NWMT  # 3 regions, January
  %(prog)s --month all               # All regions, all months
        """
    )
    parser.add_argument('--month', default='01',
                        help='Month (01-12 or "all") (default: 01)')
    parser.add_argument('--regions', default='all',
                        help='Comma-separated regions or "all" (default: all)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed output for each region')

    args = parser.parse_args()

    # get available months from raw data directory
    available_months = get_available_months()
    if not available_months:
        print("Error: No data directories found in data/raw_data/")
        sys.exit(1)

    # determine months to analyze
    if args.month == 'all':
        months_to_analyze = available_months
    else:
        try:
            month = int(args.month)
            if not 1 <= month <= 12:
                print("Error: Month must be between 01 and 12")
                sys.exit(1)
            # find matching months from available data
            months_to_analyze = [(y, m) for y, m in available_months if m == month]
            if not months_to_analyze:
                print(f"Error: No data found for month {month:02d}")
                print(f"Available months: {', '.join(f'{y}-{m:02d}' for y, m in available_months)}")
                sys.exit(1)
        except ValueError:
            print("Error: Invalid month format")
            sys.exit(1)

    # determine regions to analyze
    if args.regions == 'all':
        # get regions from first available month
        first_year, first_month = months_to_analyze[0]
        regions = get_available_regions(f'data/raw_data/{first_year}-{first_month:02d}')
        if not regions:
            print(f"Error: No data found in data/raw_data/{first_year}-{first_month:02d}/")
            sys.exit(1)
    else:
        regions = [r.strip().upper() for r in args.regions.split(',')]

    print("Energy vs Temperature Correlation Analysis")
    print(f"Analyzing {len(regions)} region(s) across {len(months_to_analyze)} month(s)")
    print(f"Data periods: {', '.join(f'{y}-{m:02d}' for y, m in months_to_analyze)}")
    print()

    # collect all results
    results = []

    for year, month in months_to_analyze:
        for region in regions:
            result = analyze_region_month(region, year, month, verbose=args.verbose)
            if result:
                results.append(result)
            elif args.verbose:
                print(f"\nSkipping {region} {year}-{month:02d}: No data or error")

    # summary
    if results:
        print(f"\nSUMMARY")
        print(f"{'Region':<10} {'Month':<8} {'r':>8} {'R2':>8} {'Strength':<10}")

        for r in results:
            print(f"{r['region']:<10} {r['month']:02d}       {r['r']:+8.4f} {r['r2']*100:7.1f}% {r['strength']:<10}")

        # overall statistics
        all_r = [r['r'] for r in results]
        all_r2 = [r['r2'] for r in results]

        print(f"\nAnalyzed {len(results)} region-month combinations")
        print(f"Average |r|: {np.mean(np.abs(all_r)):.4f}")
        print(f"Average R2: {np.mean(all_r2)*100:.1f}%")

        # count by strength
        strengths = {}
        for r in results:
            s = r['strength']
            strengths[s] = strengths.get(s, 0) + 1

        print(f"\nBreakdown by strength:")
        for strength in ['weak', 'moderate', 'strong']:
            count = strengths.get(strength, 0)
            pct = count / len(results) * 100 if results else 0
            print(f"  {strength.capitalize()}: {count} ({pct:.1f}%)")

        # generate plots
        create_correlation_plots(results)

        # generate clean data for map visualization
        generate_clean_data_for_map()

    else:
        print("\nNo valid results found.")

    print()

if __name__ == '__main__':
    main()
