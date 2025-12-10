# Energy-Temperature Correlation Map

Spearman correlation analysis between electricity demand and temperature for 66 US balancing authorities (2020 - Present).

**Live Demo:** https://missionloyd.github.io/energy-map/app/

## Usage

```bash
# View map
./run.sh
# Open http://localhost:8080
```

## What's Inside

- **66 balancing authorities** across all US interconnections
- **Spearman correlation** (Cohen's guidelines: weak <0.3, moderate <0.5, strong ≥0.5)
- **Interactive Leaflet map** with colorblind-friendly markers
- **Scatter plots** for strongest and weakest correlations

## Data Sources

- Energy: [EIA Form 930](https://www.eia.gov/electricity/gridmonitor/) (hourly demand, UTC)
- Temperature: [Open-Meteo](https://open-meteo.com/) (hourly at region centers, UTC)
