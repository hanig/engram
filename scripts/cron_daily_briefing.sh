#!/bin/bash
# Cron wrapper for daily briefing
# Add to crontab: 0 6 * * * /path/to/engram/scripts/cron_daily_briefing.sh

cd /path/to/engram

# Load environment (for API keys)
source .env 2>/dev/null || true

# Run briefing and send to Slack
/usr/bin/python3 scripts/daily_briefing.py --slack --quiet >> logs/daily_briefing.log 2>&1
