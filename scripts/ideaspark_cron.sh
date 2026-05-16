#!/bin/bash
# IdeaSpark cron wrapper — loads env and runs daily pipeline.
#
# Usage (crontab -e):
#   0  5 * * * /Users/hani/Box\ Sync/CLAUDE/engram/scripts/ideaspark_cron.sh generate
#   0 22 * * * /Users/hani/Box\ Sync/CLAUDE/engram/scripts/ideaspark_cron.sh feedback
#
# Or use launchd (recommended on macOS) — see scripts/launchd/ directory.

set -euo pipefail

ENGRAM_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOGFILE="${ENGRAM_DIR}/logs/ideaspark_cron.log"
mkdir -p "${ENGRAM_DIR}/logs"

# Source .env for API keys
if [ -f "${ENGRAM_DIR}/.env" ]; then
    set -a
    source "${ENGRAM_DIR}/.env"
    set +a
fi

# Use the correct Python — miniforge3 has project dependencies
if [ -f "${HOME}/miniforge3/bin/python" ]; then
    PYTHON="${HOME}/miniforge3/bin/python"
elif [ -f "${HOME}/miniconda3/bin/python" ]; then
    PYTHON="${HOME}/miniconda3/bin/python"
elif [ -f "${HOME}/anaconda3/bin/python" ]; then
    PYTHON="${HOME}/anaconda3/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON=python3
else
    echo "$(date): ERROR — python3 not found" >> "$LOGFILE"
    exit 1
fi

MODE="${1:-generate}"

{
    echo "===== $(date) — ideaspark ${MODE} ====="
    cd "${ENGRAM_DIR}"

    case "$MODE" in
        generate)
            "$PYTHON" scripts/ideaspark_daily.py --generate 2>&1
            ;;
        feedback)
            "$PYTHON" scripts/ideaspark_daily.py --feedback 2>&1
            ;;
        full)
            "$PYTHON" scripts/ideaspark_daily.py 2>&1
            ;;
        *)
            echo "Unknown mode: ${MODE}. Use generate, feedback, or full."
            exit 1
            ;;
    esac

    echo "===== done ====="
    echo ""
} >> "$LOGFILE" 2>&1
