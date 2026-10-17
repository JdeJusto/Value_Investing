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
#      methodology.md §8);
#   6. on the weekly day (Sunday by default), regenerates the peer-statistics
#      artifact the Scorecard tab reads (best-effort, non-fatal);
#   7. on the first Sunday of the month, runs the cross-source data-quality
#      audit (best-effort, non-fatal — see docs/data_gaps_investigation.md).
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
#   VI_PEER_STATS_DAY           ISO weekday (1=Mon .. 7=Sun) to rebuild the
#                               peer artifact; default 7; 0 disables it
#   VI_PEER_STATS_EXTRA_ARGS    extra args, e.g. "--limit 200"
#   VI_AUDIT_SAMPLE             default 30; 0 disables the monthly audit
#   VI_AUDIT_WEEKDAY            ISO weekday the audit runs on; default 7 (Sun)
#   VI_AUDIT_FIRST_DAY_MAX      only run within the first N days of the month;
#                               default 7 (the first Sunday of the month)
#   VI_AUDIT_EXTRA_ARGS         extra args, e.g. "--no-prices"
# =============================================================================
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
PEER_STATS_DAY="${VI_PEER_STATS_DAY:-7}"
PEER_STATS_EXTRA_ARGS="${VI_PEER_STATS_EXTRA_ARGS:-}"
AUDIT_SAMPLE="${VI_AUDIT_SAMPLE:-30}"
AUDIT_WEEKDAY="${VI_AUDIT_WEEKDAY:-7}"
AUDIT_FIRST_DAY_MAX="${VI_AUDIT_FIRST_DAY_MAX:-7}"
AUDIT_EXTRA_ARGS="${VI_AUDIT_EXTRA_ARGS:-}"

usage() {
    # Print the leading comment block, prefixed by "# " removal only. Stops at
    # the first non-comment line so the range never has to be kept in sync.
    awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
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

# Weekly (Sunday by default): rebuild the peer-statistics artifact the
# Scorecard tab reads. Additive and best-effort — a failure here never changes
# the workflow's exit status, and the artifact is a local build product.
if [[ "$PEER_STATS_DAY" != "0" && "$(date +%u)" == "$PEER_STATS_DAY" ]]; then
    log "regenerating peer statistics (weekly; day $PEER_STATS_DAY)"
    set +e
    # shellcheck disable=SC2086  # splitting VI_PEER_STATS_EXTRA_ARGS is intentional
    "$PYTHON" -m scripts.build_peer_stats $PEER_STATS_EXTRA_ARGS >>"$RUN_LOG" 2>&1
    PEER_STATUS=$?
    set -e
    log "peer statistics finished with status $PEER_STATUS"
fi

# Monthly (the first Sunday by default): the cross-source data-quality audit.
# Like the peer build it is best-effort — a DATA_ERROR_FDB finding (exit 1) is
# news for the log, never a reason to fail the day.
if [[ "$AUDIT_SAMPLE" != "0" && "$(date +%u)" == "$AUDIT_WEEKDAY" ]] &&
    ((10#$(date +%d) <= AUDIT_FIRST_DAY_MAX)); then
    log "running the monthly data-quality audit (sample $AUDIT_SAMPLE; first $AUDIT_FIRST_DAY_MAX day(s) of the month)"
    set +e
    # shellcheck disable=SC2086  # splitting VI_AUDIT_EXTRA_ARGS is intentional
    "$PYTHON" -m scripts.audit_data_quality \
        --sample "$AUDIT_SAMPLE" \
        --sources sec,yahoo \
        --out "$LOGS_DIR" \
        $AUDIT_EXTRA_ARGS >>"$RUN_LOG" 2>&1
    AUDIT_STATUS=$?
    set -e
    log "data-quality audit finished with status $AUDIT_STATUS"
fi

exit "$WORKFLOW_STATUS"
