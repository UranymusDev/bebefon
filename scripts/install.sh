#!/bin/bash
# BabyMonitor Installation Script
# Run on a fresh Raspberry Pi OS installation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  BabyMonitor Installation Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please do not run as root. Run as your normal user.${NC}"
    exit 1
fi

# Configuration
INSTALL_DIR="/opt/babymonitor"
AUDIO_DEVICE="hw:2,0"  # May need adjustment based on USB port

echo -e "${YELLOW}Step 1: Updating system packages...${NC}"
sudo apt update
sudo apt upgrade -y

echo -e "${YELLOW}Step 2: Installing dependencies...${NC}"
sudo apt install -y snapserver alsa-utils netcat-openbsd python3 python3-venv python3-pip

echo -e "${YELLOW}Step 3: Creating project directory...${NC}"
sudo mkdir -p ${INSTALL_DIR}/{config,scripts,bot,systemd}
sudo chown -R $USER:$USER ${INSTALL_DIR}

echo -e "${YELLOW}Step 4: Detecting USB microphone...${NC}"
if arecord -l 2>/dev/null | grep -q "USB"; then
    echo -e "${GREEN}USB microphone detected!${NC}"
    arecord -l | grep -A1 "USB"

    # Try to find the card number
    CARD_NUM=$(arecord -l | grep "USB" | head -1 | sed 's/card \([0-9]*\):.*/\1/')
    if [ -n "$CARD_NUM" ]; then
        AUDIO_DEVICE="hw:${CARD_NUM},0"
        echo -e "${GREEN}Using audio device: ${AUDIO_DEVICE}${NC}"
    fi
else
    echo -e "${RED}WARNING: No USB microphone detected!${NC}"
    echo "Please connect your USB microphone and run this script again."
    echo "Or manually configure the audio device in the service file."
fi

echo -e "${YELLOW}Step 5: Configuring Snapserver...${NC}"
sudo tee /etc/snapserver.conf > /dev/null << 'EOF'
###############################################################################
#  BabyMonitor Snapserver Configuration
###############################################################################

[server]
# threads = -1

[http]
doc_root = /usr/share/snapserver/snapweb

[tcp]
# port = 1705

[stream]
# Audio source from named pipe
source = pipe:///tmp/snapfifo?name=BabyMonitor&sampleformat=48000:16:1

# Default codec
#codec = flac

# Buffer [ms]
#buffer = 1000

[logging]
#filter = *:info
EOF

echo -e "${YELLOW}Step 6: Adding _snapserver to audio group...${NC}"
sudo usermod -a -G audio _snapserver

echo -e "${YELLOW}Step 7: Creating audio capture service...${NC}"
sudo tee /etc/systemd/system/babymonitor-audio.service > /dev/null << EOF
[Unit]
Description=BabyMonitor Audio Capture
After=sound.target snapserver.service
Requires=snapserver.service

[Service]
Type=simple
ExecStartPre=/bin/sleep 5
ExecStart=/bin/bash -c 'while ! arecord -l 2>/dev/null | grep -q USB; do sleep 2; done; sleep 2; exec arecord -D ${AUDIO_DEVICE} -f S16_LE -r 48000 -c 1 -t raw > /tmp/snapfifo'
Restart=always
RestartSec=5
User=_snapserver
Group=audio

[Install]
WantedBy=multi-user.target
EOF

echo -e "${YELLOW}Step 8: Installing monitor script...${NC}"
cat > ${INSTALL_DIR}/scripts/monitor.py << 'MONITOR_EOF'
#!/usr/bin/env python3
"""BabyMonitor Connection Monitor - Sends Ntfy alerts when Snapcast client disconnects"""
import json, socket, time, urllib.request, os
from datetime import datetime

SNAPSERVER_HOST, SNAPSERVER_PORT = "localhost", 1705
CHECK_INTERVAL, DISCONNECT_TIMEOUT, ALERT_COOLDOWN = 5, 10, 30
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "babymonitor-alerts")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")

class Monitor:
    def __init__(self):
        self.last_client_seen = self.last_alert_time = None
        self.alert_sent = False

    def get_connected_clients(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((SNAPSERVER_HOST, SNAPSERVER_PORT))
            sock.send((json.dumps({"id":1,"jsonrpc":"2.0","method":"Server.GetStatus"})+"\n").encode())
            data = json.loads(sock.recv(8192).decode())
            sock.close()
            return sum(1 for g in data["result"]["server"]["groups"] for c in g["clients"] if c["connected"])
        except: return 0

    def send_ntfy(self, title, message, priority="high", tags=None):
        try:
            headers = {"Title": title, "Priority": priority}
            if tags: headers["Tags"] = tags
            req = urllib.request.Request(f"{NTFY_SERVER}/{NTFY_TOPIC}", data=message.encode(), headers=headers)
            urllib.request.urlopen(req, timeout=10)
            print(f"[{datetime.now()}] Ntfy sent: {title}")
        except Exception as e: print(f"[{datetime.now()}] Ntfy failed: {e}")

    def run(self):
        print(f"[{datetime.now()}] BabyMonitor watchdog started - Topic: {NTFY_TOPIC}")
        self.send_ntfy("BabyMonitor Online", "Monitoring started.", priority="low", tags="white_check_mark,baby")
        while True:
            clients, now = self.get_connected_clients(), time.time()
            if clients > 0:
                if self.alert_sent:
                    self.send_ntfy("Connection Restored", f"Reconnected after {int(now-self.last_client_seen)}s", priority="default", tags="green_circle,baby")
                    self.alert_sent = False
                self.last_client_seen = now
            elif self.last_client_seen:
                secs = int(now - self.last_client_seen)
                if secs >= DISCONNECT_TIMEOUT and not self.alert_sent and (not self.last_alert_time or now - self.last_alert_time >= ALERT_COOLDOWN):
                    self.send_ntfy("CONNECTION LOST!", f"No client for {secs}s. Check app!", priority="urgent", tags="red_circle,warning,baby")
                    self.alert_sent, self.last_alert_time = True, now
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__": Monitor().run()
MONITOR_EOF
chmod +x ${INSTALL_DIR}/scripts/monitor.py

echo -e "${YELLOW}Step 9: Installing control script...${NC}"
cat > ${INSTALL_DIR}/scripts/babymonitor-ctl << 'CTL_EOF'
#!/bin/bash
PAUSE_FILE="/opt/babymonitor/config/paused"
HC_URLS=$(cat /opt/babymonitor/config/healthchecks_urls 2>/dev/null)

ping_healthchecks() {
    for url in $HC_URLS; do curl -fsS -m 10 "$url$1" > /dev/null 2>&1; done
}

case "$1" in
    pause)
        touch "$PAUSE_FILE"
        sudo systemctl stop babymonitor-monitor
        ping_healthchecks "/0"
        echo "BabyMonitor PAUSED - no alerts will be sent"
        ;;
    resume)
        rm -f "$PAUSE_FILE"
        sudo systemctl start babymonitor-monitor
        ping_healthchecks ""
        echo "BabyMonitor RESUMED - alerts active"
        ;;
    status)
        [ -f "$PAUSE_FILE" ] && echo "Status: PAUSED" || echo "Status: ACTIVE"
        systemctl is-active babymonitor-monitor babymonitor-audio snapserver
        ;;
    *) echo "Usage: babymonitor {pause|resume|status}"; exit 1 ;;
esac
CTL_EOF
chmod +x ${INSTALL_DIR}/scripts/babymonitor-ctl
sudo ln -sf ${INSTALL_DIR}/scripts/babymonitor-ctl /usr/local/bin/babymonitor

echo -e "${YELLOW}Step 10: Creating monitor service...${NC}"
read -p "Enter your Ntfy topic name (e.g., babymonitor-abc123): " NTFY_TOPIC
sudo tee /etc/systemd/system/babymonitor-monitor.service > /dev/null << EOF
[Unit]
Description=BabyMonitor Connection Monitor
After=network-online.target snapserver.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/babymonitor/scripts/monitor.py
Restart=always
RestartSec=10
User=$USER
Environment=NTFY_TOPIC=${NTFY_TOPIC}
Environment=NTFY_SERVER=https://ntfy.sh

[Install]
WantedBy=multi-user.target
EOF

echo -e "${YELLOW}Step 11: Setting up Healthchecks.io heartbeat...${NC}"
read -p "Enter Healthchecks.io ping URL(s) (space-separated, or press Enter to skip): " HC_URLS
if [ -n "$HC_URLS" ]; then
    echo "$HC_URLS" > ${INSTALL_DIR}/config/healthchecks_urls
    # Add cron job
    (crontab -l 2>/dev/null | grep -v hc-ping
    echo "* * * * * [ ! -f /opt/babymonitor/config/paused ] && for url in $HC_URLS; do curl -fsS -m 10 --retry 3 \"\$url\" > /dev/null 2>&1; done") | crontab -
    echo -e "${GREEN}Healthchecks configured!${NC}"
fi

echo -e "${YELLOW}Step 12: Enabling and starting services...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable snapserver babymonitor-audio babymonitor-monitor
sudo systemctl restart snapserver
sleep 3
sudo systemctl start babymonitor-audio babymonitor-monitor

echo -e "${YELLOW}Step 13: Waiting for services to start...${NC}"
sleep 10

echo -e "${YELLOW}Step 14: Checking service status...${NC}"
echo ""
echo "Snapserver status:"
systemctl is-active snapserver && echo -e "${GREEN}Running${NC}" || echo -e "${RED}Not running${NC}"
echo ""
echo "Audio capture status:"
systemctl is-active babymonitor-audio && echo -e "${GREEN}Running${NC}" || echo -e "${RED}Not running${NC}"
echo ""

# Check stream status
echo "Stream status:"
STREAM_STATUS=$(echo '{"id":1,"jsonrpc":"2.0","method":"Server.GetStatus"}' | nc -w 2 localhost 1705 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["result"]["server"]["streams"][0]["status"])' 2>/dev/null || echo "unknown")
if [ "$STREAM_STATUS" = "playing" ]; then
    echo -e "${GREEN}Stream is playing!${NC}"
else
    echo -e "${YELLOW}Stream status: ${STREAM_STATUS}${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
PI_IP=$(hostname -I | awk '{print $1}')
echo "Next steps:"
echo ""
echo "1. Install Snapcast app on your phone:"
echo "   - Android: https://f-droid.org/packages/de.badaix.snapcast/"
echo "   - iOS: https://apps.apple.com/us/app/snapcast-client/id1552559653"
echo ""
echo "2. Install Ntfy app for alerts:"
echo "   - Android: https://f-droid.org/packages/io.heckel.ntfy/"
echo "   - iOS: https://apps.apple.com/app/ntfy/id1625396347"
echo "   - Subscribe to topic: ${NTFY_TOPIC}"
echo ""
echo "3. Add this server in Snapcast app:"
echo "   IP Address: ${PI_IP}"
echo "   Port: 1704 (default)"
echo ""
echo "4. Connect and test audio!"
echo ""
echo "Commands:"
echo "  babymonitor status  - Check system status"
echo "  babymonitor pause   - Pause all alerts"
echo "  babymonitor resume  - Resume alerts"
echo ""
echo "Web UI: http://${PI_IP}:1780"
echo ""
