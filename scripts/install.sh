#!/bin/bash
# BabyMonitor Installation Script
# Run on a fresh Raspberry Pi OS installation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  BabyMonitor Installation Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please do not run as root. Run as your normal user.${NC}"
    exit 1
fi

INSTALL_DIR="/opt/babymonitor"
CONFIG_FILE="${INSTALL_DIR}/config/config.env"

# Check if config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}ERROR: config.env not found!${NC}"
    echo "Please copy config.env.example to config.env and fill in your values:"
    echo "  cp ${INSTALL_DIR}/config/config.env.example ${INSTALL_DIR}/config/config.env"
    echo "  nano ${INSTALL_DIR}/config/config.env"
    exit 1
fi

# Load config
source "$CONFIG_FILE"

echo -e "${YELLOW}Device: ${DEVICE_NAME}${NC}"
echo ""

# Step 1: Update system
echo -e "${YELLOW}Step 1: Updating system packages...${NC}"
sudo apt update
sudo apt upgrade -y

# Step 2: Install dependencies
echo -e "${YELLOW}Step 2: Installing dependencies...${NC}"
sudo apt install -y snapserver alsa-utils netcat-openbsd python3 python3-pip sox ffmpeg curl

# Step 3: Install Python packages
echo -e "${YELLOW}Step 3: Installing Python packages...${NC}"
pip3 install python-telegram-bot --break-system-packages

# Step 4: Install Tailscale
echo -e "${YELLOW}Step 4: Installing Tailscale...${NC}"
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    echo -e "${YELLOW}Run 'sudo tailscale up' after installation to authenticate${NC}"
else
    echo -e "${GREEN}Tailscale already installed${NC}"
fi

# Step 5: Detect USB microphone
echo -e "${YELLOW}Step 5: Detecting USB microphone...${NC}"
if arecord -l 2>/dev/null | grep -q "USB"; then
    echo -e "${GREEN}USB microphone detected!${NC}"
    arecord -l | grep -A1 "USB"
    CARD_NUM=$(arecord -l | grep "USB" | head -1 | sed 's/card \([0-9]*\):.*/\1/')
    DETECTED_DEVICE="hw:${CARD_NUM},0"
    echo -e "${GREEN}Detected audio device: ${DETECTED_DEVICE}${NC}"

    # Update config if different
    if [ "$AUDIO_DEVICE" != "$DETECTED_DEVICE" ]; then
        echo -e "${YELLOW}Updating config with detected device...${NC}"
        sed -i "s/AUDIO_DEVICE=.*/AUDIO_DEVICE=\"${DETECTED_DEVICE}\"/" "$CONFIG_FILE"
        AUDIO_DEVICE="$DETECTED_DEVICE"
    fi
else
    echo -e "${RED}WARNING: No USB microphone detected!${NC}"
    echo "Using configured device: ${AUDIO_DEVICE}"
fi

# Step 6: Add _snapserver to audio group
echo -e "${YELLOW}Step 6: Adding _snapserver to audio group...${NC}"
sudo usermod -a -G audio _snapserver

# Step 7: Configure Snapserver
echo -e "${YELLOW}Step 7: Configuring Snapserver...${NC}"
sudo cp ${INSTALL_DIR}/config/snapserver.conf /etc/snapserver.conf

# Step 8: Install systemd services
echo -e "${YELLOW}Step 8: Installing systemd services...${NC}"

# Audio capture service
sudo tee /etc/systemd/system/babymonitor-audio.service > /dev/null << EOF
[Unit]
Description=BabyMonitor Audio Capture
After=sound.target snapserver.service
Requires=snapserver.service

[Service]
Type=simple
ExecStartPre=/bin/sleep 5
ExecStart=/bin/bash -c 'while ! arecord -l 2>/dev/null | grep -q USB; do sleep 2; done; sleep 2; exec arecord -D ${AUDIO_DEVICE} -f S16_LE -r ${SAMPLE_RATE:-48000} -c ${CHANNELS:-1} -t raw > /tmp/snapfifo'
Restart=always
RestartSec=5
User=_snapserver
Group=audio

[Install]
WantedBy=multi-user.target
EOF

# Monitor service
sudo tee /etc/systemd/system/babymonitor-monitor.service > /dev/null << EOF
[Unit]
Description=BabyMonitor Connection Monitor
After=network-online.target snapserver.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/scripts/monitor.py
Restart=always
RestartSec=10
User=$USER
EnvironmentFile=${CONFIG_FILE}

[Install]
WantedBy=multi-user.target
EOF

# Mic alert service
sudo tee /etc/systemd/system/babymonitor-mic-alert.service > /dev/null << EOF
[Unit]
Description=BabyMonitor Mic Alert Loop
After=snapserver.service

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/scripts/mic-alert-loop.sh
Restart=always
RestartSec=5
User=_snapserver

[Install]
WantedBy=multi-user.target
EOF

# Telegram bot service
sudo tee /etc/systemd/system/babymonitor-telegram.service > /dev/null << EOF
[Unit]
Description=BabyMonitor Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/scripts/telegram-bot.py
Restart=always
RestartSec=10
User=$USER
WorkingDirectory=${INSTALL_DIR}

[Install]
WantedBy=multi-user.target
EOF

# Step 9: Create mic-alert-loop script
echo -e "${YELLOW}Step 9: Creating mic-alert-loop script...${NC}"
cat > ${INSTALL_DIR}/scripts/mic-alert-loop.sh << 'EOF'
#!/bin/bash
# Continuous warning beep while mic is disconnected

CONFIG_FILE="/opt/babymonitor/config/config.env"
PIPE="/tmp/snapfifo"
PAUSE_FILE="/opt/babymonitor/config/paused"
WARNING_BEEP_FILE="/opt/babymonitor/config/warning_beep.raw"

source "$CONFIG_FILE" 2>/dev/null

# Generate warning beep if not exists
if [ ! -f "$WARNING_BEEP_FILE" ]; then
    sox -n -r 48000 -b 16 -c 1 -t raw /tmp/beep1.raw synth 0.15 sine 1200 vol 0.4 2>/dev/null
    sox -n -r 48000 -b 16 -c 1 -t raw /tmp/silence.raw synth 0.1 sine 0 vol 0 2>/dev/null
    cat /tmp/beep1.raw /tmp/silence.raw /tmp/beep1.raw /tmp/silence.raw /tmp/beep1.raw > "$WARNING_BEEP_FILE"
    rm -f /tmp/beep1.raw /tmp/silence.raw
fi

while true; do
    if [ -f "$PAUSE_FILE" ]; then
        sleep 5
        continue
    fi

    if ! arecord -l 2>/dev/null | grep -q "USB"; then
        if [ -p "$PIPE" ]; then
            cat "$WARNING_BEEP_FILE" >> "$PIPE" 2>/dev/null
        fi
        sleep 3
    else
        sleep 5
    fi
done
EOF
chmod +x ${INSTALL_DIR}/scripts/mic-alert-loop.sh

# Step 9b: Pre-generate warning beep file with correct permissions
echo -e "${YELLOW}Step 9b: Generating warning beep audio file...${NC}"
sox -n -r 48000 -b 16 -c 1 -t raw /tmp/beep1.raw synth 0.15 sine 1200 vol 0.4 2>/dev/null
sox -n -r 48000 -b 16 -c 1 -t raw /tmp/silence.raw synth 0.1 sine 0 vol 0 2>/dev/null
cat /tmp/beep1.raw /tmp/silence.raw /tmp/beep1.raw /tmp/silence.raw /tmp/beep1.raw > ${INSTALL_DIR}/config/warning_beep.raw
rm -f /tmp/beep1.raw /tmp/silence.raw
sudo chown _snapserver:audio ${INSTALL_DIR}/config/warning_beep.raw
echo -e "${GREEN}Warning beep file created${NC}"

# Step 10: Set up cron jobs
echo -e "${YELLOW}Step 10: Setting up cron jobs...${NC}"

# Heartbeat beep cron (as _snapserver user)
sudo -u _snapserver crontab -l 2>/dev/null | grep -v heartbeat-beep > /tmp/snapserver_cron || true
echo "*/5 * * * * ${INSTALL_DIR}/scripts/heartbeat-beep.sh" >> /tmp/snapserver_cron
sudo -u _snapserver crontab /tmp/snapserver_cron
rm /tmp/snapserver_cron

# Mic check cron
(crontab -l 2>/dev/null | grep -v mic-check; echo "* * * * * ${INSTALL_DIR}/scripts/mic-check.sh") | crontab -

# Healthchecks.io ping cron
if [ -n "$HEALTHCHECK_URLS" ]; then
    PING_CMD="[ ! -f ${INSTALL_DIR}/config/paused ]"
    for url in $HEALTHCHECK_URLS; do
        PING_CMD="$PING_CMD && curl -fsS -m 10 --retry 3 '$url' > /dev/null 2>&1"
    done
    (crontab -l 2>/dev/null | grep -v hc-ping; echo "* * * * * $PING_CMD") | crontab -
    echo -e "${GREEN}Healthchecks.io configured${NC}"
fi

# Step 11: Create symlink for babymonitor command
echo -e "${YELLOW}Step 11: Creating babymonitor command...${NC}"
sudo ln -sf ${INSTALL_DIR}/scripts/babymonitor-ctl /usr/local/bin/babymonitor

# Step 12: Initialize bot config
echo -e "${YELLOW}Step 12: Initializing bot config...${NC}"
cat > ${INSTALL_DIR}/config/bot_config.json << EOF
{
  "authorized_users": [],
  "setup_complete": false
}
EOF

# Step 13: Enable and start services
echo -e "${YELLOW}Step 13: Enabling and starting services...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable snapserver babymonitor-audio babymonitor-monitor babymonitor-mic-alert babymonitor-telegram
sudo systemctl restart snapserver
sleep 3
sudo systemctl start babymonitor-audio babymonitor-monitor babymonitor-mic-alert babymonitor-telegram

# Step 14: Wait and check status
echo -e "${YELLOW}Step 14: Checking service status...${NC}"
sleep 5

echo ""
echo "Service Status:"
for svc in snapserver babymonitor-audio babymonitor-monitor babymonitor-mic-alert babymonitor-telegram tailscaled; do
    STATUS=$(systemctl is-active $svc 2>/dev/null || echo "not installed")
    if [ "$STATUS" = "active" ]; then
        echo -e "  ${GREEN}✓${NC} $svc: $STATUS"
    else
        echo -e "  ${RED}✗${NC} $svc: $STATUS"
    fi
done

# Get IPs
PI_IP=$(hostname -I | awk '{print $1}')
TS_IP=$(tailscale ip -4 2>/dev/null || echo "not connected")

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Device Name: ${GREEN}${DEVICE_NAME}${NC}"
echo -e "Local IP: ${PI_IP}"
echo -e "Tailscale IP: ${TS_IP}"
echo -e "Ntfy Topic: ${NTFY_TOPIC}"
echo ""
echo "Next steps:"
echo "1. Run 'sudo tailscale up' if Tailscale not yet authenticated"
echo "2. Open Telegram and message your bot"
echo "3. Follow the setup wizard"
echo ""
echo "Commands:"
echo "  babymonitor status  - Check system status"
echo "  babymonitor pause   - Pause all alerts"
echo "  babymonitor resume  - Resume alerts"
echo ""
