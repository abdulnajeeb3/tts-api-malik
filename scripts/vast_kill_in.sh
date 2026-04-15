#!/bin/bash
# Unconditional Vast instance killer.
#
# Sleeps for DELAY_SEC, then destroys INSTANCE_ID. No heartbeat, no
# cancel-on-activity — just a dumb timer. Use this when you know you'll be
# done within a fixed window and want a fire-and-forget auto-shutoff.
#
# Usage:
#   INSTANCE_ID=34960563 DELAY_SEC=1800 \
#     nohup scripts/vast_kill_in.sh > /tmp/vast_kill.log 2>&1 &
#   disown
#
# Cancel:
#   pkill -f vast_kill_in.sh

set -u

INSTANCE_ID="${INSTANCE_ID:?INSTANCE_ID must be set}"
DELAY_SEC="${DELAY_SEC:-1800}"   # 30 min default
LOG_FILE="${LOG_FILE:-/tmp/vast_kill.log}"

API_KEY="$(cat "$HOME/.config/vastai/vast_api_key")"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

log "kill timer armed pid=$$ instance=$INSTANCE_ID fires_in=${DELAY_SEC}s"
log "cancel with: pkill -f vast_kill_in.sh"

sleep "$DELAY_SEC"

log "DESTROYING instance $INSTANCE_ID"
curl -s -X DELETE \
    -H "Authorization: Bearer $API_KEY" \
    "https://console.vast.ai/api/v0/instances/$INSTANCE_ID/" \
    | tee -a "$LOG_FILE"
log "destroy request sent"
