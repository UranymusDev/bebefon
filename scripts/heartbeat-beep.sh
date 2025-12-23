#!/bin/bash
# Heartbeat beep - reads config from config.env

CONFIG_FILE="/opt/babymonitor/config/config.env"
BEEP_FILE="/opt/babymonitor/config/beep.raw"
PIPE="/tmp/snapfifo"
PAUSE_FILE="/opt/babymonitor/config/paused"

# Load config
source "$CONFIG_FILE" 2>/dev/null

# Check if beep is enabled
[ "$BEEP_ENABLED" != "true" ] && exit 0

# Don't beep if paused
[ -f "$PAUSE_FILE" ] && exit 0

# Don't beep if pipe doesn't exist
[ -p "$PIPE" ] || exit 0

# Regenerate beep if settings changed (check by comparing params)
BEEP_PARAMS="${BEEP_FREQUENCY:-800}_${BEEP_DURATION:-0.3}_${BEEP_VOLUME:-0.3}"
BEEP_PARAMS_FILE="/opt/babymonitor/config/beep_params"

if [ ! -f "$BEEP_FILE" ] || [ ! -f "$BEEP_PARAMS_FILE" ] || [ "$(cat $BEEP_PARAMS_FILE 2>/dev/null)" != "$BEEP_PARAMS" ]; then
    sox -n -r 48000 -b 16 -c 1 -t raw "$BEEP_FILE" synth ${BEEP_DURATION:-0.3} sine ${BEEP_FREQUENCY:-800} vol ${BEEP_VOLUME:-0.3} 2>/dev/null
    echo "$BEEP_PARAMS" > "$BEEP_PARAMS_FILE"
fi

# Write beep to pipe
cat "$BEEP_FILE" >> "$PIPE" 2>/dev/null
