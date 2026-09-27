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

# Resolve the repository root from the script location, so the launcher
# works from a clone in any directory.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source .venv/bin/activate

# SEC contact details are personal data: they come from the git-ignored .env
# (SEC_USER_AGENT="<tool>/<version> <your-e-mail>"), never from this script.
# Load it when present, then fail loudly rather than running a doomed refresh.
if [ -f .env ]; then
  set -a; source .env; set +a
fi
: "${SEC_USER_AGENT:?SEC_USER_AGENT is not set — add it to .env (copy .env.example) with a real contact e-mail; the SEC refuses generic agents and github.com domains (HTTP 403)}"
export FINANCIAL_DATABASE_URL="${FINANCIAL_DATABASE_URL:-postgresql://financial@localhost:5432/financial_database}"
mkdir -p data/logs

SESSION="vi_daily_$(date +%Y%m%d_%H%M%S)"

nohup python -m scripts.daily_workflow \
  --universe all --max-refresh 200 --top 20 --resume "$@" \
  > "data/logs/daily_${SESSION}.log" 2>&1 &

echo $! > "data/logs/daily_${SESSION}.pid"
echo "Started daily workflow: PID $(cat "data/logs/daily_${SESSION}.pid")"
echo "Log: data/logs/daily_${SESSION}.log"
echo "Progress: data/reports/daily_run_state.json (run state, updated per ticker)"
