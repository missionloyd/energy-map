#!/bin/bash

# energy-climate correlation map - docker runner
# usage:
#   ./run.sh              - start web server (production)
#   ./run.sh dev          - start with live reload (development)
#   ./run.sh fetch        - fetch all data (2020-present)
#   ./run.sh analyze      - run correlation analysis
#   ./run.sh update       - one-time data update (fetch + analyze)
#   ./run.sh scheduler    - start scheduled updater (daily)
#   ./run.sh stop         - stop all services
#   ./run.sh clean        - stop and remove all containers

set -e

# load .env if exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

MODE=${1:-web}

case $MODE in
    web)
        echo "Starting production web server..."
        docker compose down 2>/dev/null || true
        docker compose up -d web
        echo ""
        echo "Web server running at: http://localhost:${WEB_PORT:-8080}"
        echo "Use './run.sh stop' to stop"
        ;;

    dev)
        echo "Starting development server with live reload..."
        docker compose down 2>/dev/null || true
        docker compose --profile dev up -d web-dev
        echo ""
        echo "Dev server running at: http://localhost:${WEB_DEV_PORT:-8081}"
        echo "Use './run.sh stop' to stop"
        docker compose --profile dev logs -f web-dev
        ;;

    fetch)
        echo "Fetching all energy and climate data (2020-present)..."
        echo "This may take a while..."
        docker compose --profile tools build analysis
        docker compose --profile tools run --rm analysis python fetch_data.py --all
        echo ""
        echo "Data fetch complete!"
        ;;

    analyze)
        echo "Running correlation analysis for all months..."
        docker compose --profile tools build analysis
        docker compose --profile tools run --rm analysis python analysis.py --month all
        echo ""
        echo "Analysis complete! Check app/data/ for results."
        ;;

    update)
        echo "Running one-time data update (fetch + analyze)..."
        docker compose --profile tools build analysis
        echo ""
        echo "[1/2] Fetching latest data..."
        docker compose --profile tools run --rm analysis python fetch_data.py
        echo ""
        echo "[2/2] Running correlation analysis..."
        docker compose --profile tools run --rm analysis python analysis.py --month all
        echo ""
        echo "Update complete!"
        ;;

    scheduler)
        echo "Starting scheduled data updater..."
        echo "Updates will run every ${UPDATE_INTERVAL:-86400} seconds (default: daily)"
        docker compose --profile scheduler up -d scheduler
        echo ""
        echo "Scheduler running. Use './run.sh stop' to stop"
        docker compose --profile scheduler logs -f scheduler
        ;;

    stop)
        echo "Stopping all services..."
        docker compose --profile dev --profile tools --profile scheduler down
        echo "All services stopped."
        ;;

    clean)
        echo "Stopping and removing all containers..."
        docker compose --profile dev --profile tools --profile scheduler down -v --rmi local
        echo "Cleanup complete."
        ;;

    logs)
        docker compose logs -f
        ;;

    *)
        echo "Energy-Climate Correlation Map - Docker Runner"
        echo ""
        echo "Usage: ./run.sh [command]"
        echo ""
        echo "Commands:"
        echo "  web        Start production web server (default)"
        echo "  dev        Start development server with live reload"
        echo "  fetch      Fetch all data from 2020 to present"
        echo "  analyze    Run correlation analysis"
        echo "  update     One-time data update (fetch + analyze)"
        echo "  scheduler  Start scheduled daily updater"
        echo "  stop       Stop all services"
        echo "  clean      Stop and remove all containers"
        echo "  logs       View container logs"
        echo ""
        echo "Environment Variables:"
        echo "  EIA_API_KEY       - EIA API key (required)"
        echo "  UPDATE_INTERVAL   - Scheduler interval in seconds (default: 86400)"
        echo "  WEB_PORT          - Production web server port (default: 8080)"
        echo "  WEB_DEV_PORT      - Development server port (default: 8081)"
        ;;
esac
