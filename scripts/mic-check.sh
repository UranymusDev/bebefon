#!/bin/bash
# Microphone health check - detects if USB mic is disconnected

CONFIG_FILE="/opt/babymonitor/config/config.env"
PIPE="/tmp/snapfifo"
PAUSE_FILE="/opt/babymonitor/config/paused"
MIC_STATE_FILE="/opt/babymonitor/config/mic_state"
WARNING_BEEP_FILE="/opt/babymonitor/config/warning_beep.raw"

# Load config
source "$CONFIG_FILE" 2>/dev/null

# Don't check if paused
[ -f "$PAUSE_FILE" ] && exit 0

# Check if USB mic is detected
mic_detected() {
    arecord -l 2>/dev/null | grep -q "USB"
}

# Send ntfy alert
send_alert() {
    local title="$1"
    local message="$2"
    local priority="$3"
    local tags="$4"
    curl -s -o /dev/null \
        -H "Title: $title" \
        -H "Priority: $priority" \
        -H "Tags: $tags" \
        -d "$message" \
        "${NTFY_SERVER:-https://ntfy.sh}/${NTFY_TOPIC:-babymonitor}"
}

# Generate warning beep (three short high-pitched beeps)
generate_warning_beep() {
    sox -n -r 48000 -b 16 -c 1 -t raw /tmp/beep1.raw synth 0.15 sine 1200 vol 0.4 2>/dev/null
    sox -n -r 48000 -b 16 -c 1 -t raw /tmp/silence.raw synth 0.1 sine 0 vol 0 2>/dev/null
    cat /tmp/beep1.raw /tmp/silence.raw /tmp/beep1.raw /tmp/silence.raw /tmp/beep1.raw > "$WARNING_BEEP_FILE"
    rm -f /tmp/beep1.raw /tmp/silence.raw
}

# Play warning beep
play_warning() {
    [ -p "$PIPE" ] || return
    [ -f "$WARNING_BEEP_FILE" ] || generate_warning_beep
    cat "$WARNING_BEEP_FILE" >> "$PIPE" 2>/dev/null
}

# Get previous state (1=ok, 0=failed)
prev_state=$(cat "$MIC_STATE_FILE" 2>/dev/null || echo "1")

if mic_detected; then
    # Mic is OK
    if [ "$prev_state" = "0" ]; then
        # Was failed, now recovered
        send_alert "Microphone Restored" "USB microphone is working again." "default" "green_circle,microphone"
        echo "[$(date)] Mic restored" >> /var/log/babymonitor-mic.log
    fi
    echo "1" > "$MIC_STATE_FILE"
else
    # Mic is NOT detected
    if [ "$prev_state" = "1" ]; then
        # Just failed - send alert
        send_alert "MICROPHONE DISCONNECTED!" "USB microphone not detected. Check connection!" "urgent" "red_circle,warning,microphone"
        echo "[$(date)] Mic disconnected - alert sent" >> /var/log/babymonitor-mic.log
    fi
    # Play warning beep every check while mic is down
    play_warning
    echo "0" > "$MIC_STATE_FILE"
fi
