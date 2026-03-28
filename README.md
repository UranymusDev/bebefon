# Bebefon - Raspberry Pi Baby Monitor

A DIY audio baby monitor using a Raspberry Pi with real-time streaming, push notifications, and Telegram bot control.

**Cost: ~45€** (Pi + USB mic) — no subscription, no cloud, no compromises.

## Features

### Audio Streaming
- **Real-time audio** via Snapcast to iOS & Android
- Works with **screen locked** / in background
- **Remote access** via Tailscale VPN — works from anywhere (home WiFi, LTE, any network)
- Heartbeat beep every 5 minutes for peace of mind

### Alerts & Notifications
- **Disconnect alerts** via Ntfy push notifications (within 10 seconds)
- **Pi-down alerts** via Healthchecks.io (if Raspberry Pi crashes)
- **Microphone unplugged** alert + continuous warning beeps
- All alerts are **instant** with high priority

### Telegram Bot Control (German UI)
- Setup wizard for easy first-time configuration
- Sends Snapcast APK directly (Android — no F-Droid needed)
- Status monitoring (`/status`, `/temp`, `/uptime`)
- Alert control (`/pause`, `/resume`, `/beep`)
- Service management (`/restart`, `/reboot`)
- WiFi management (`/wifi` — status, scan, connect, toggle)
- Tailscale management (`/tailscale` — connect, switch account, disconnect)
- Remote updates (`/update` — pulls from git)
- Multi-user access via invite codes (`/join`, `/leave`)
- Startup messages when Pi boots

### Easy Configuration
- **Single config file** (`config.env`) for all settings
- Fully customizable: device name, owner, notification topics
- Support for multiple devices (one bot per device)

## Requirements

### Hardware
- Raspberry Pi (tested on Pi 4/5 with Debian 13 Trixie, 64-bit)
- USB Microphone (tested with Texas Instruments PCM2902 Audio Codec)

### Phone Apps
| App | Purpose | iOS | Android |
|-----|---------|-----|---------|
| **Tailscale** | VPN for remote access | [App Store](https://apps.apple.com/app/tailscale/id1470499037) | [Play Store](https://play.google.com/store/apps/details?id=com.tailscale.ipn) |
| **Snapcast** | Audio streaming | [App Store](https://apps.apple.com/us/app/snapcast-client/id1552559653) | APK via bot or [F-Droid](https://f-droid.org/packages/de.badaix.snapcast/) |
| **Ntfy** | Push notifications | [App Store](https://apps.apple.com/app/ntfy/id1625396347) | [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy) |

## Before You Start

You need accounts/tokens from these free services:

### 1. Telegram Bot Token
1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `1234567890:ABCdef...`)

### 2. Ntfy Topic
Just pick any unique string — e.g. `babymonitor-yourname-abc123`. No account needed for basic use.

### 3. Tailscale (optional but recommended)
Create a free account at [tailscale.com](https://tailscale.com) — enables remote access from anywhere. Can also be set up later via the Telegram bot.

### 4. Healthchecks.io (optional)
Create a free account at [healthchecks.io](https://healthchecks.io), add two checks (one for the monitor, one for audio), copy the ping URLs. This alerts you if the Pi itself crashes.

## Quick Start

### 1. Clone the repository
```bash
cd /opt
sudo git clone https://github.com/UranymusDev/bebefon babymonitor
sudo chown -R $USER:$USER /opt/babymonitor
cd /opt/babymonitor
```

### 2. Create your config
```bash
cp config/config.env.example config/config.env
nano config/config.env
```

Fill in your values:
```bash
DEVICE_NAME="Baby's Bebefon"
OWNER_NAME="Name"
GIFT_GIVER="Gifter"
TELEGRAM_BOT_TOKEN="your-bot-token"   # from @BotFather
INVITE_CODE="your-invite-code"        # for additional users
NTFY_TOPIC="your-unique-topic"
HEALTHCHECK_URLS=""                   # optional, from healthchecks.io
```

### 3. Run the installer
```bash
./scripts/install.sh
```

The installer will:
- Install all dependencies (snapserver, Python packages, etc.)
- Auto-detect your USB microphone
- Set up all systemd services
- Configure cron jobs

### 4. Setup Tailscale
```bash
sudo tailscale up
# Visit the URL shown to authenticate
```

Or skip this and do it later via `/tailscale` in the Telegram bot.

### 5. Open Telegram
Message your bot — the first user to send `/start` is automatically authorized. Follow the setup wizard!

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Start bot / show help |
| `/status` | Full system status |
| `/pause` | Pause all alerts |
| `/resume` | Resume alerts |
| `/beep` | Send test beep |
| `/temp` | CPU temperature |
| `/uptime` | System uptime |
| `/config` | Show current config |
| `/restart` | Restart all services |
| `/reboot` | Reboot Raspberry Pi |
| `/update` | Pull updates from git |
| `/wifi` | WiFi management |
| `/tailscale` | Tailscale management |
| `/setup` | Run setup wizard |
| `/reset` | Reset setup wizard |
| `/join <code>` | Join with invite code |
| `/leave` | Remove your own access |
| `/setcode <code>` | Set new invite code |
| `/logs` | Show recent logs |
| `/help` | All commands |

## Configuration

All settings are in `config/config.env`:

| Setting | Description |
|---------|-------------|
| `DEVICE_NAME` | Display name (e.g., "Karo's Bebefon") |
| `OWNER_NAME` | Owner's name |
| `GIFT_GIVER` | Gift giver's name (shown in messages) |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `INVITE_CODE` | Code for additional users to join |
| `NTFY_TOPIC` | Unique Ntfy topic for alerts |
| `HEALTHCHECK_URLS` | Healthchecks.io ping URLs (space-separated) |
| `AUDIO_DEVICE` | USB mic device (auto-detected by installer) |
| `BEEP_INTERVAL` | Minutes between heartbeat beeps |
| `BEEP_FREQUENCY` | Heartbeat beep frequency in Hz |
| `BEEP_VOLUME` | Heartbeat beep volume (0.0–1.0) |

## Architecture

```
USB Mic → arecord → /tmp/snapfifo → Snapserver → Phone/Laptop (Snapcast App)
                                         ↓
                              monitor.py → Ntfy (disconnect alerts)
                                         ↓
                           Telegram Bot → Remote control
                                         ↓
                          Healthchecks.io → Pi-down alerts (cron)
```

### Services
| Service | Purpose |
|---------|---------|
| `snapserver` | Audio streaming server |
| `babymonitor-audio` | Mic capture to Snapserver |
| `babymonitor-monitor` | Connection monitoring + Ntfy alerts |
| `babymonitor-mic-alert` | Mic disconnect detection + warning beeps |
| `babymonitor-telegram` | Telegram bot |

## Multiple Devices

Each device needs:
1. Its own Telegram bot (from @BotFather)
2. Unique Ntfy topic
3. Unique Healthchecks.io checks
4. Tailscale on same account (or shared)

Just create a new `config.env` with different values for each device.

## Troubleshooting

### No audio
```bash
babymonitor status
arecord -l                                    # Check if mic is detected
journalctl -u babymonitor-audio -f
```

### Not getting alerts
```bash
systemctl status babymonitor-monitor
curl -d "Test" https://ntfy.sh/YOUR_TOPIC     # Test Ntfy manually
```

### Bot not responding
```bash
systemctl status babymonitor-telegram
journalctl -u babymonitor-telegram -f
```

### WiFi disabled and Pi unreachable
Connect a LAN cable — the ethernet adapter works automatically via DHCP.

## License

MIT

## Credits

Built with:
- [Snapcast](https://github.com/badaix/snapcast) - Multi-room audio streaming
- [Tailscale](https://tailscale.com) - Zero-config VPN
- [Ntfy](https://ntfy.sh) - Push notifications
- [python-telegram-bot](https://python-telegram-bot.org) - Telegram Bot API
- [Healthchecks.io](https://healthchecks.io) - Uptime monitoring
