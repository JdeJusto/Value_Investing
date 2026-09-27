#!/usr/bin/env bash
# Launch the Value Investing daily workflow in the background (nohup),
# equivalent to the systemd user unit but without systemd.
#
#   ./scripts/run_daily_background.sh              # full universe, 200 syncs
#   ./scripts/run_daily_background.sh --limit 100  # extra args are passed through
#
# Stop gracefully (checkpoint is flushed, exit 0):
#   kill -TERM "$(cat data/logs/vi_daily_*.pid | tail -1)"
# Resume later: the next run finds data/reports/daily_run_state.json and
# continues (--resume is the default).
set -euo pipefail

cd /home/caudillo/Value_Investing
source .venv/bin/activate
export SEC_USER_AGENT="FinancialDataBase/1.0 jaimedejusto@gmail.com"
export FINANCIAL_DATABASE_URL="postgresql://financial@localhost:5432/financial_database"
mkdir -p data/logs

SESSION="vi_daily_$(date +%Y%m%d_%H%M%S)"

nohup python -m scripts.daily_workflow \
  --universe all --max-refresh 200 --top 20 --resume "$@" \
  > "data/logs/daily_${SESSION}.log" 2>&1 &

echo $! > "data/logs/daily_${SESSION}.pid"
echo "Started daily workflow: PID $(cat "data/logs/daily_${SESSION}.pid")"
echo "Log: data/logs/daily_${SESSION}.log"
echo "Progress: data/reports/daily_run_state.json (run state, updated per ticker)"
