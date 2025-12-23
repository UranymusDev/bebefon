# BabyMonitor Setup Documentation

## Project Overview

Audio-streaming baby monitor using Raspberry Pi with Snapcast for reliable background audio playback on smartphones.

**Hardware:**
- Raspberry Pi (tested on Pi with Debian 13 Trixie, 64-bit)
- USB Microphone (Texas Instruments PCM2902 Audio Codec / "USB PnP Sound Device")

**Software Stack:**
- Snapserver 0.31.0 for audio streaming
- Snapcast client apps (Android & iOS)
- Tailscale for remote access (works from any network)
- Ntfy for instant disconnect alerts
- Healthchecks.io for Pi-down monitoring
- systemd for service management

---

## Current Setup Status

| Feature | Status | Description |
|---------|--------|-------------|
| Audio Streaming | ✅ Complete | Snapcast audio to iOS & Android |
| Auto-start | ✅ Complete | All services start on boot |
| Disconnect Alerts | ✅ Complete | Ntfy alerts when app disconnects |
| Pi-down Alerts | ✅ Complete | Healthchecks.io alerts if Pi is down |
| Heartbeat Beep | ✅ Complete | Gentle beep every 5 min for peace of mind |
| Central Config | ✅ Complete | All settings in one file |
| Pause/Resume | ✅ Complete | Easy control via `babymonitor` command |
| Remote Access | ✅ Complete | Tailscale VPN - works from any network |
| Mic Health Check | ✅ Complete | Alert + warning beep if mic disconnects |

---

## Quick Commands

```bash
babymonitor status   # Show full system status
babymonitor pause    # Pause all alerts (for maintenance)
babymonitor resume   # Resume alerts
babymonitor config   # Edit configuration file
babymonitor beep     # Send test beep
```

---

## Network Configuration

| Setting | Value |
|---------|-------|
| Pi Hostname | bebefon |
| Pi User | bebefon |
| Pi Local IP | YOUR_LOCAL_IP |
| **Pi Tailscale IP** | **YOUR_TAILSCALE_IP** |
| Snapcast Stream Port | 1704 |
| Snapcast Control Port | 1705 |
| Snapcast Web UI | http://[PI_IP]:1780 |

**Remote Access:** Phone connects via Tailscale IP from any network (home WiFi, LTE, anywhere).

---

## Configuration File

All settings are in `/opt/babymonitor/config/config.env`:

```bash
# === Audio Settings ===
AUDIO_DEVICE="hw:2,0"
SAMPLE_RATE=48000
CHANNELS=1

# === Ntfy Alerts ===
NTFY_SERVER="https://ntfy.sh"
NTFY_TOPIC="your-ntfy-topic-here"

# === Monitor Settings ===
CHECK_INTERVAL=5          # Seconds between connection checks
DISCONNECT_TIMEOUT=10     # Seconds before disconnect alert
ALERT_COOLDOWN=30         # Seconds between repeat alerts

# === Healthchecks.io ===
HEALTHCHECK_URLS="https://hc-ping.com/xxx https://hc-ping.com/yyy"

# === Heartbeat Beep ===
BEEP_ENABLED=true
BEEP_INTERVAL=5           # Minutes between beeps
BEEP_FREQUENCY=800        # Hz
BEEP_DURATION=0.3         # Seconds
BEEP_VOLUME=0.3           # 0.0 to 1.0

# === Future: Telegram Bot ===
# TELEGRAM_BOT_TOKEN=""
# TELEGRAM_CHAT_IDS=""
```

**To edit:** `babymonitor config` or `nano /opt/babymonitor/config/config.env`

**After editing:** `sudo systemctl restart babymonitor-monitor`

---

## File Locations

| Path | Description |
|------|-------------|
| `/opt/babymonitor/config/config.env` | **Central configuration file** |
| `/opt/babymonitor/scripts/monitor.py` | Connection monitor script |
| `/opt/babymonitor/scripts/babymonitor-ctl` | Control script (pause/resume/status) |
| `/opt/babymonitor/scripts/heartbeat-beep.sh` | Heartbeat beep script |
| `/opt/babymonitor/scripts/mic-check.sh` | Microphone health check (runs every minute) |
| `/etc/snapserver.conf` | Snapserver configuration |
| `/etc/systemd/system/babymonitor-audio.service` | Audio capture service |
| `/etc/systemd/system/babymonitor-monitor.service` | Monitor service |
| `/tmp/snapfifo` | Audio pipe (created by snapserver) |

---

## Tailscale Setup (Remote Access)

Tailscale creates a secure VPN so the phone can connect from anywhere (LTE, different WiFi, etc).

### Pi Setup (Already Done)
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Visit the URL to authenticate
tailscale ip -4  # Shows your Pi's Tailscale IP
```

### Phone Setup

**Install Tailscale:**

| Platform | Download |
|----------|----------|
| Android | [Google Play](https://play.google.com/store/apps/details?id=com.tailscale.ipn) |
| iOS | [App Store](https://apps.apple.com/app/tailscale/id1470499037) |

**Steps:**
1. Install Tailscale app on phone
2. Sign in with the **same account** used for Pi
3. Phone joins your Tailscale network automatically
4. In **Snapcast app**, use Tailscale IP: `YOUR_TAILSCALE_IP` (instead of local IP)

**Test:** Turn off WiFi on phone (use LTE), verify Snapcast still connects.

---

## Client Setup

### Snapcast App (Audio Streaming)

**Android:**
- F-Droid: https://f-droid.org/packages/de.badaix.snapcast/
- GitHub: https://github.com/snapcast/snapdroid/releases

**iOS:**
- App Store: https://apps.apple.com/us/app/snapcast-client/id1552559653
- Developer: Stijn Van der Borght
- Supports background audio (works with locked screen)

**Setup:**
1. Install the app
2. Add server: `[PI_IP_ADDRESS]` (port 1704 default)
3. Connect and verify audio

### Ntfy App (Alerts)

**Android:**
- F-Droid: https://f-droid.org/packages/io.heckel.ntfy/
- Play Store: https://play.google.com/store/apps/details?id=io.heckel.ntfy

**iOS:**
- App Store: https://apps.apple.com/app/ntfy/id1625396347

**Setup:**
1. Install the app
2. Subscribe to topic: `your-ntfy-topic-here` (or your custom topic)
3. Enable notifications with **high priority** for urgent alerts
4. Test by disconnecting Snapcast - you should get an alert within ~15 seconds

---

## Alert System

### Alert Types

| Source | Event | Priority | Message |
|--------|-------|----------|---------|
| Pi (monitor.py) | Startup | Low | "BabyMonitor Online" |
| Pi (monitor.py) | Disconnect | **Urgent** | "CONNECTION LOST!" |
| Pi (monitor.py) | Reconnect | Default | "Connection Restored" |
| Pi (mic-check.sh) | Mic unplugged | **Urgent** | "MICROPHONE DISCONNECTED!" + warning beeps |
| Pi (mic-check.sh) | Mic restored | Default | "Microphone Restored" |
| Healthchecks.io | Pi down 3+ min | **Urgent** | "Pi is DOWN!" |
| Healthchecks.io | Pi back up | Default | "Pi is UP" |

### Healthchecks.io Setup

1. Create account at https://healthchecks.io
2. Create new check with:
   - Period: 1 minute
   - Grace: 3 minutes (first alert) / 5 minutes (backup alert)
3. Add **Ntfy integration** with your topic
4. Add ping URL(s) to config file

---

## Heartbeat Beep

A gentle beep plays through the audio stream every 5 minutes so parents know the connection is working.

**Settings in config.env:**
```bash
BEEP_ENABLED=true
BEEP_INTERVAL=5      # Minutes
BEEP_FREQUENCY=800   # Hz (800 = gentle tone)
BEEP_DURATION=0.3    # Seconds
BEEP_VOLUME=0.3      # 0.0 to 1.0
```

**Test beep:** `babymonitor beep`

---

## Services

| Service | Purpose | User |
|---------|---------|------|
| `snapserver` | Audio streaming server | _snapserver |
| `babymonitor-audio` | Mic → Snapserver pipe | _snapserver |
| `babymonitor-monitor` | Connection monitoring + Ntfy | bebefon |

**Check status:**
```bash
babymonitor status
# or
systemctl status snapserver babymonitor-audio babymonitor-monitor
```

**Restart all:**
```bash
sudo systemctl restart snapserver babymonitor-audio babymonitor-monitor
```

---

## Troubleshooting

### No Audio in App

1. Check services: `babymonitor status`
2. Check stream status (should be "playing", not "idle")
3. Check if mic is detected: `arecord -l`
4. Check logs: `journalctl -u babymonitor-audio -n 50`

### Not Getting Alerts

1. Check monitor is running: `systemctl is-active babymonitor-monitor`
2. Check Ntfy topic is correct in config
3. Check you're subscribed to the topic in Ntfy app
4. Test manually: `curl -d "Test" https://ntfy.sh/YOUR_TOPIC`

### Stream Status "idle"

Audio data isn't reaching snapserver:
- USB mic not detected (check `arecord -l`)
- Audio capture service not running
- Permission issue on pipe

### Service Keeps Restarting

```bash
journalctl -u babymonitor-audio --no-pager -n 30
journalctl -u babymonitor-monitor --no-pager -n 30
```

### Phone Can't Connect

**With Tailscale (recommended):**
- Ensure Tailscale is running on phone (check Tailscale app)
- Use Tailscale IP: `YOUR_TAILSCALE_IP`
- Tailscale works from any network (WiFi, LTE, etc)

**Without Tailscale (local only):**
- Phone must be on same WiFi as Pi
- Use local IP: `YOUR_LOCAL_IP`
- Check Pi IP: `hostname -I`
- Test port: `nc -zv [PI_IP] 1704`

---

## Maintenance

### Pause Alerts (for maintenance)
```bash
babymonitor pause
# Do your maintenance...
babymonitor resume
```

### Update Config
```bash
babymonitor config
# Edit values, save, then:
sudo systemctl restart babymonitor-monitor
```

### View Logs
```bash
journalctl -u snapserver -f
journalctl -u babymonitor-audio -f
journalctl -u babymonitor-monitor -f
```

### Test Microphone
```bash
arecord -l  # List devices
arecord -D hw:2,0 -f S16_LE -r 48000 -c 1 -d 5 test.wav
aplay test.wav
```

---

## Future Enhancements

- [x] ~~Tailscale for remote access (outside home network)~~ ✅ Done!
- [ ] Telegram bot for remote control
- [ ] Temperature monitoring
- [ ] Flutter app (single app for audio + alerts)
- [ ] Firewall hardening
