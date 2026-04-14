# scripts/

Local utility scripts that live outside the serving path.

## `vast_watchdog.sh`

Watchdog for Vast.ai GPU instances. Destroys the instance if a heartbeat
file goes stale, so a forgotten or crashed session can't burn credit.

### Why it exists

Vast.ai bills by the hour. If a Claude session dies, the terminal closes,
or the main agent loses connectivity, the rented GPU keeps charging until
someone remembers to stop it. The watchdog turns that into an
it-stops-itself problem: the main agent touches a heartbeat file after
every action, the watchdog destroys the instance if the heartbeat stops.

### Usage

```bash
# Start the watchdog (run in background, disown so it survives your shell):
INSTANCE_ID=34883373 \
  HEARTBEAT_TIMEOUT_SEC=900 \
  MAX_TOTAL_SEC=10800 \
  nohup scripts/vast_watchdog.sh > /tmp/vast_watchdog.log 2>&1 &
disown

# Refresh the heartbeat (the agent does this automatically):
touch /tmp/vast_keepalive

# Stop the watchdog *without* destroying the instance:
pkill -f vast_watchdog.sh    # leave the heartbeat file in place first
```

### Knobs

| Env var | Default | Meaning |
|---|---|---|
| `INSTANCE_ID` | required | Vast instance to destroy |
| `HEARTBEAT_FILE` | `/tmp/vast_keepalive` | mtime of this file is the heartbeat |
| `HEARTBEAT_TIMEOUT_SEC` | `900` (15 min) | stale threshold |
| `MAX_TOTAL_SEC` | `10800` (3 hr) | hard cap regardless of heartbeat |
| `POLL_INTERVAL_SEC` | `60` | how often to check |
| `LOG_FILE` | `/tmp/vast_watchdog.log` | where status lines go |

### Failure modes

- Laptop closes / sleeps → watchdog pauses with it; instance keeps burning.
  Mitigation: the hard cap still fires when the laptop wakes back up if
  enough wall clock has passed.
- API key missing / wrong → destroy call fails silently. Check the log.
- Wrong instance id → you'd destroy some other instance. The script refuses
  to run without `INSTANCE_ID` explicitly set.
