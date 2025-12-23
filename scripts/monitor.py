#!/usr/bin/env python3
"""BabyMonitor Connection Monitor - Reads config from config.env"""
import json, socket, time, urllib.request, os
from datetime import datetime

# Load config
CONFIG_FILE = "/opt/babymonitor/config/config.env"
config = {}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                # Strip inline comments
                if '#' in val:
                    val = val.split('#')[0]
                config[key.strip()] = val.strip().strip('"')

# Configuration from file or defaults
SNAPSERVER_HOST = "localhost"
SNAPSERVER_PORT = 1705
CHECK_INTERVAL = int(config.get('CHECK_INTERVAL', 5))
DISCONNECT_TIMEOUT = int(config.get('DISCONNECT_TIMEOUT', 10))
ALERT_COOLDOWN = int(config.get('ALERT_COOLDOWN', 30))
NTFY_TOPIC = config.get('NTFY_TOPIC', 'babymonitor-alerts')
NTFY_SERVER = config.get('NTFY_SERVER', 'https://ntfy.sh')

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
            print(f"[{datetime.now()}] Ntfy: {title}")
        except Exception as e: print(f"[{datetime.now()}] Ntfy failed: {e}")

    def run(self):
        print(f"[{datetime.now()}] Monitor started | Topic: {NTFY_TOPIC} | Timeout: {DISCONNECT_TIMEOUT}s | Cooldown: {ALERT_COOLDOWN}s")
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
