#!/bin/bash
# Vast.ai instance watchdog.
#
# Polls a heartbeat file every 60s. If the file hasn't been touched in
# HEARTBEAT_TIMEOUT_SEC, the vast instance gets destroyed to stop the
# hourly burn. Also hard-kills the instance after MAX_TOTAL_SEC regardless,
# so a forgotten watchdog can't run forever.
#
# Usage:
#   INSTANCE_ID=34883373 ./scripts/vast_watchdog.sh &
#   # Claude / you touch the heartbeat periodically:
#   touch /tmp/vast_keepalive
#
# Stop the watchdog without destroying:
#   rm /tmp/vast_keepalive_ack && kill <watchdog-pid>

set -u

INSTANCE_ID="${INSTANCE_ID:?INSTANCE_ID must be set}"
HEARTBEAT_FILE="${HEARTBEAT_FILE:-/tmp/vast_keepalive}"
HEARTBEAT_TIMEOUT_SEC="${HEARTBEAT_TIMEOUT_SEC:-900}"   # 15 min
MAX_TOTAL_SEC="${MAX_TOTAL_SEC:-10800}"                  # 3 hr hard cap
POLL_INTERVAL_SEC="${POLL_INTERVAL_SEC:-60}"
LOG_FILE="${LOG_FILE:-/tmp/vast_watchdog.log}"

API_KEY="$(cat "$HOME/.config/vastai/vast_api_key")"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

destroy_instance() {
    local reason="$1"
    log "DESTROYING instance $INSTANCE_ID — reason: $reason"
    curl -s -X DELETE \
        -H "Authorization: Bearer $API_KEY" \
        "https://console.vast.ai/api/v0/instances/$INSTANCE_ID/" \
        | tee -a "$LOG_FILE"
    log "instance destroy request sent"
    rm -f "$HEARTBEAT_FILE"
}

# Seed the heartbeat so we don't insta-kill
touch "$HEARTBEAT_FILE"

started_at=$(date +%s)
log "watchdog started pid=$$ instance=$INSTANCE_ID heartbeat=$HEARTBEAT_FILE timeout=${HEARTBEAT_TIMEOUT_SEC}s hardcap=${MAX_TOTAL_SEC}s"

while true; do
    now=$(date +%s)
    elapsed_total=$(( now - started_at ))

    if [ "$elapsed_total" -ge "$MAX_TOTAL_SEC" ]; then
        destroy_instance "hard cap reached ($MAX_TOTAL_SEC s)"
        exit 0
    fi

    if [ ! -f "$HEARTBEAT_FILE" ]; then
        destroy_instance "heartbeat file removed"
        exit 0
    fi

    last_touch=$(stat -f %m "$HEARTBEAT_FILE" 2>/dev/null || stat -c %Y "$HEARTBEAT_FILE")
    stale=$(( now - last_touch ))

    if [ "$stale" -ge "$HEARTBEAT_TIMEOUT_SEC" ]; then
        destroy_instance "heartbeat stale (${stale}s > ${HEARTBEAT_TIMEOUT_SEC}s)"
        exit 0
    fi

    # Every 5 polls (~5 min), log a status line so we can verify it is alive
    if [ $(( elapsed_total / POLL_INTERVAL_SEC % 5 )) -eq 0 ]; then
        log "alive: stale=${stale}s elapsed_total=${elapsed_total}s"
    fi

    sleep "$POLL_INTERVAL_SEC"
done
