#!/usr/bin/env bash
# =============================================================================
# run_daily_on_boot.sh — Run the daily workflow once per calendar day, at boot.
#
# Started by the systemd user unit deploy/systemd/value-investing-daily-boot
# .service (or by hand). It:
#
#   1. takes an exclusive lock so two boots never run it at once;
#   2. refuses to run twice in the same calendar day (logs/.last_daily_run);
#   3. waits up to 10 minutes for the network (a desktop is often online a
#      few seconds after login, but not always);
#   4. runs `python -m scripts.daily_workflow --resume`;
#   5. runs a small data-sample validation (non-fatal — see docs/validation_
#      methodology.md §8).
#
# It needs NO sudo and never touches a database directly; the daily workflow
# keeps its usual contract (prices are fetched, never persisted).
#
# Usage:
#   scripts/run_daily_on_boot.sh           # no-op if it already ran today
#   scripts/run_daily_on_boot.sh --force   # ignore the "already ran today" stamp
#   scripts/run_daily_on_boot.sh --help
#
# Environment overrides (mainly for tests and ad-hoc runs):
#   VI_PYTHON                   default <repo>/.venv/bin/python
#   VI_LOGS_DIR                 default <repo>/logs
#   VI_UNIVERSE                 default all
#   VI_MAX_REFRESH              default 200
#   VI_NETWORK_TIMEOUT_SECONDS  default 600 (10 minutes)
#   VI_SKIP_NETWORK_WAIT        default 0; set to 1 to skip the wait
#   VI_WORKFLOW_EXTRA_ARGS      extra args, e.g. "--dry-run --limit 5"
#   VI_VALIDATION_SAMPLE        default 10; 0 disables the post-run validation
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${VI_PYTHON:-$REPO_ROOT/.venv/bin/python}"
LOGS_DIR="${VI_LOGS_DIR:-$REPO_ROOT/logs}"
UNIVERSE="${VI_UNIVERSE:-all}"
MAX_REFRESH="${VI_MAX_REFRESH:-200}"
NETWORK_TIMEOUT_SECONDS="${VI_NETWORK_TIMEOUT_SECONDS:-600}"
SKIP_NETWORK_WAIT="${VI_SKIP_NETWORK_WAIT:-0}"
WORKFLOW_EXTRA_ARGS="${VI_WORKFLOW_EXTRA_ARGS:-}"
VALIDATION_SAMPLE="${VI_VALIDATION_SAMPLE:-10}"

usage() {
    sed -n '2,38p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

FORCE=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            printf 'run_daily_on_boot.sh: unknown argument: %s\n' "$arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

mkdir -p "$LOGS_DIR"
TODAY="$(date +%Y-%m-%d)"
STAMP_FILE="$LOGS_DIR/.last_daily_run"
LOCK_FILE="$LOGS_DIR/.run_daily_on_boot.lock"
RUN_LOG="$LOGS_DIR/run_${TODAY}.log"

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" | tee -a "$RUN_LOG"; }

# Exclusive lock (fd 9) so a second boot never starts a concurrent run.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "another daily-boot run holds the lock; exiting"
    exit 0
fi

# Per-day, not per-hour: a reboot later today is a no-op.
if [[ "$FORCE" -eq 0 && -f "$STAMP_FILE" && "$(cat "$STAMP_FILE" 2>/dev/null)" == "$TODAY" ]]; then
    log "daily workflow already ran today ($TODAY); nothing to do (use --force to rerun)"
    exit 0
fi

# True once a TCP connection to the SEC host succeeds (the same host the
# refresh talks to), so we do not start a run that will only see timeouts.
network_up() {
    "$PYTHON" - <<'PY' >/dev/null 2>&1
import socket

socket.setdefaulttimeout(10)
try:
    socket.create_connection(("data.sec.gov", 443)).close()
except OSError:
    raise SystemExit(1)
PY
}

if [[ "$SKIP_NETWORK_WAIT" != "1" ]]; then
    log "waiting for the network (up to ${NETWORK_TIMEOUT_SECONDS}s)..."
    deadline=$((SECONDS + NETWORK_TIMEOUT_SECONDS))
    until network_up; do
        if ((SECONDS >= deadline)); then
            log "network still down after ${NETWORK_TIMEOUT_SECONDS}s; skipping this boot"
            exit 0
        fi
        sleep 10
    done
    log "network is up"
fi

log "running daily workflow (universe=$UNIVERSE, max-refresh=$MAX_REFRESH)"
set +e
# shellcheck disable=SC2086  # splitting VI_WORKFLOW_EXTRA_ARGS is intentional
"$PYTHON" -m scripts.daily_workflow \
    --universe "$UNIVERSE" \
    --max-refresh "$MAX_REFRESH" \
    --resume \
    $WORKFLOW_EXTRA_ARGS >>"$RUN_LOG" 2>&1
WORKFLOW_STATUS=$?
set -e
log "daily workflow finished with status $WORKFLOW_STATUS"

# Stamp the day even when the run failed: re-running every boot would only
# repeat the same failure. The failure is in the run log and the workflow's
# own checkpoint (--resume) picks up where it stopped if it is relaunched.
printf '%s\n' "$TODAY" >"$STAMP_FILE"

if [[ "$VALIDATION_SAMPLE" != "0" ]]; then
    log "validating a ${VALIDATION_SAMPLE}-ticker data sample (non-fatal)"
    if ! "$PYTHON" -m scripts.validate_data_sample \
        --sample "$VALIDATION_SAMPLE" \
        --out "$LOGS_DIR" >>"$RUN_LOG" 2>&1; then
        log "data-sample validation flagged discrepancies (see $LOGS_DIR)"
    fi
fi

exit "$WORKFLOW_STATUS"
