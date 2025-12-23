# BabyMonitor - Product Requirements Document

**Audio-Streaming Baby Monitor mit Telegram-Steuerung**

---

| Feld | Wert |
|------|------|
| **Version** | 1.0 |
| **Datum** | 14. Dezember 2024 |
| **Hardware** | Raspberry Pi 3B + KISEER USB Mikrofon |
| **Zielplattform** | Raspberry Pi OS (Bookworm, 64-bit) |

---

## Inhaltsverzeichnis

1. [Executive Summary](#1-executive-summary)
2. [Projektziele](#2-projektziele)
3. [System-Architektur](#3-system-architektur)
4. [Funktionale Anforderungen](#4-funktionale-anforderungen)
5. [Nicht-Funktionale Anforderungen](#5-nicht-funktionale-anforderungen)
6. [Telegram Bot Spezifikation](#6-telegram-bot-spezifikation)
7. [Dateistruktur & Konfiguration](#7-dateistruktur--konfiguration)
8. [Implementierungs-Roadmap](#8-implementierungs-roadmap)
9. [Testkriterien & Akzeptanztests](#9-testkriterien--akzeptanztests)
10. [Installationsanleitung](#10-installationsanleitung)
11. [Risiken & Mitigationen](#11-risiken--mitigationen)
12. [Glossar](#12-glossar)

---

## 1. Executive Summary

Dieses Dokument beschreibt die Entwicklung eines Audio-Baby-Monitors basierend auf einem Raspberry Pi 3B. Das System streamt Audio über das lokale Netzwerk zu einer nativen App auf dem Smartphone, die auch bei gesperrtem Bildschirm zuverlässig funktioniert. Zusätzlich ermöglicht ein Telegram-Bot die Fernsteuerung und Statusüberwachung des Systems.

**Kernprinzip:** Zuverlässigkeit vor Features. Das System muss verlässlich Verbindungsverluste erkennen und melden.

**Warum Snapcast statt Browser-Streaming:**
- Browser-basierte Lösungen pausieren bei gesperrtem Bildschirm
- Snapcast App läuft zuverlässig im Hintergrund (Android/iOS)
- Eingebautes Connection-Status Monitoring
- Aktiv maintained (Stand 2024)

---

## 2. Projektziele

### 2.1 Primäre Ziele (MUST)

- Zuverlässiges Audio-Streaming vom Kinderzimmer zum Smartphone
- Funktioniert auch bei gesperrtem Smartphone-Bildschirm
- Verlässliche Erkennung und Alarmierung bei Verbindungsverlust
- Betrieb im lokalen Netzwerk (optional über VPN erreichbar)
- Fernsteuerung und Monitoring via Telegram Bot

### 2.2 Sekundäre Ziele (SHOULD)

- Konfigurierbare Mikrofon-Lautstärke
- Mute/Unmute Funktion
- Temperatur-Monitoring des Pi
- Automatischer Reconnect nach Netzwerk-Ausfall

### 2.3 Nicht-Ziele (Explizit ausgeschlossen)

- ❌ Video-Streaming (keine Kamera)
- ❌ Cry Detection / KI-basierte Geräuscherkennung
- ❌ Cloud-basierte Dienste oder externe Server
- ❌ Temperatur-/Feuchtigkeitssensoren im Kinderzimmer
- ❌ Multi-Room Audio Sync (nur ein Empfänger nötig)

---

## 3. System-Architektur

### 3.1 Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│                  Raspberry Pi 3B (Server)                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌─────────────────────────────────┐   │
│  │ USB Mikrofon │───▶│ ALSA (arecord)                  │   │
│  │ (KISEER)     │    │ Sample: 48kHz, Mono, S16_LE     │   │
│  └──────────────┘    └───────────────┬─────────────────┘   │
│                                      │                      │
│                                      ▼                      │
│                      ┌─────────────────────────────────┐   │
│                      │ Named Pipe / FIFO               │   │
│                      │ /tmp/snapfifo                   │   │
│                      └───────────────┬─────────────────┘   │
│                                      │                      │
│                                      ▼                      │
│                      ┌─────────────────────────────────┐   │
│                      │ Snapserver                      │   │
│                      │ Stream Port: 1704               │   │
│                      │ Control Port: 1705 (JSON-RPC)   │   │
│                      └───────────────┬─────────────────┘   │
│                                      │                      │
│  ┌─────────────────────────────────┐ │                      │
│  │ Python Telegram Bot             │ │                      │
│  │ - Command Handler               │◀┘ (Client Monitoring)  │
│  │ - Heartbeat Monitor             │                        │
│  │ - Alert System                  │                        │
│  └───────────────┬─────────────────┘                        │
│                  │                                          │
└──────────────────┼──────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
┌───────────────┐    ┌───────────────┐
│ Snapcast App  │    │ Telegram App  │
│ (Android/iOS) │    │               │
│               │    │ /status       │
│ 🔊 Audio      │    │ /restart      │
│ Background ✓  │    │ /reboot       │
│ Lock Screen ✓ │    │ 🔔 Alerts     │
└───────────────┘    └───────────────┘
```

### 3.2 Komponenten-Beschreibung

| Komponente | Beschreibung | Verantwortlichkeit |
|------------|--------------|---------------------|
| **USB Mikrofon** | KISEER Mini USB Mic | Audio-Aufnahme |
| **ALSA/arecord** | Linux Audio System | Audio-Capture, Format-Konvertierung |
| **Named Pipe** | /tmp/snapfifo | Puffer zwischen Capture und Server |
| **Snapserver** | Audio-Streaming Server | Stream-Distribution, Client-Management |
| **Telegram Bot** | Python Async Bot | Fernsteuerung, Monitoring, Alerts |
| **Snapcast App** | Native Mobile App | Audio-Wiedergabe, Hintergrund-Betrieb |
| **systemd** | Service Manager | Auto-Start, Restart bei Crash |

### 3.3 Technologie-Stack

| Bereich | Technologie | Version/Details |
|---------|-------------|-----------------|
| Betriebssystem | Raspberry Pi OS | Bookworm (Debian 12), 64-bit |
| Audio Streaming | Snapcast | >=0.27.0 |
| Audio Capture | ALSA + arecord | System-Pakete |
| Bot Framework | python-telegram-bot | >=20.0 (async) |
| Python | Python 3 | >=3.11 (Bookworm default) |
| Service Manager | systemd | System-Default |
| Konfiguration | YAML | PyYAML |

### 3.4 Netzwerk-Ports

| Port | Protokoll | Dienst | Richtung |
|------|-----------|--------|----------|
| 1704 | TCP | Snapcast Stream | Inbound (LAN) |
| 1705 | TCP | Snapcast Control | Inbound (LAN) |
| 443 | TCP | Telegram API | Outbound (Internet) |
| 22 | TCP | SSH | Inbound (optional) |

---

## 4. Funktionale Anforderungen

### 4.1 Audio-Streaming (F-AUD)

| ID | Anforderung | Priorität | Akzeptanzkriterium |
|----|-------------|-----------|---------------------|
| F-AUD-01 | System nimmt Audio vom USB-Mikrofon kontinuierlich auf | MUST | `arecord -l` zeigt Gerät, Audio in Pipe sichtbar |
| F-AUD-02 | Audio wird mit <500ms Latenz gestreamt | MUST | Gemessen mit Klatschen/Echo-Test |
| F-AUD-03 | Stream ist im lokalen Netzwerk erreichbar | MUST | Snapcast App kann verbinden |
| F-AUD-04 | Audio spielt bei gesperrtem Bildschirm weiter | MUST | 5 Min Test mit gesperrtem Phone |
| F-AUD-05 | Audio spielt nach App-Wechsel im Hintergrund | MUST | Andere App öffnen, Audio läuft |
| F-AUD-06 | Mikrofon-Gain ist konfigurierbar (0-100%) | SHOULD | amixer Befehl funktioniert |
| F-AUD-07 | Stream ist über VPN von extern erreichbar | COULD | Bei aktivem VPN verbindbar |

### 4.2 Verbindungs-Monitoring (F-CON)

| ID | Anforderung | Priorität | Akzeptanzkriterium |
|----|-------------|-----------|---------------------|
| F-CON-01 | Snapcast App zeigt Verbindungsstatus visuell an | MUST | Grün/Rot Indikator in App |
| F-CON-02 | Bei Verbindungsverlust >10s wird Telegram-Alert gesendet | MUST | Alert kommt innerhalb 15s |
| F-CON-03 | Server prüft Client-Verbindung via Heartbeat | MUST | Log zeigt Heartbeat alle 5s |
| F-CON-04 | Bei Wiederverbindung wird Entwarnung gesendet | SHOULD | "Verbindung wiederhergestellt" Message |
| F-CON-05 | Alert-Timeout ist konfigurierbar | SHOULD | config.yaml Änderung wirkt |
| F-CON-06 | Mehrfach-Alerts werden unterdrückt (Debounce) | SHOULD | Max 1 Alert pro Disconnect-Event |

### 4.3 Telegram Bot (F-BOT)

| ID | Anforderung | Priorität | Akzeptanzkriterium |
|----|-------------|-----------|---------------------|
| F-BOT-01 | `/status` zeigt System-Status | MUST | Antwort mit CPU, Temp, Uptime, Clients |
| F-BOT-02 | `/restart` startet Audio-Stream neu | MUST | Stream unterbricht kurz, dann OK |
| F-BOT-03 | `/reboot` startet Raspberry Pi neu | MUST | Pi bootet, Stream nach ~60s wieder da |
| F-BOT-04 | `/mute` pausiert Audio-Capture | SHOULD | Stille im Stream |
| F-BOT-05 | `/unmute` startet Audio-Capture | SHOULD | Audio wieder hörbar |
| F-BOT-06 | `/volume [0-100]` setzt Mikrofon-Gain | SHOULD | Lautstärke ändert sich |
| F-BOT-07 | `/ping` einfacher Health-Check | SHOULD | "Pong!" Antwort |
| F-BOT-08 | `/help` zeigt Befehlsübersicht | SHOULD | Liste aller Commands |
| F-BOT-09 | Bot akzeptiert nur autorisierte Chat-IDs | MUST | Fremde Chats werden ignoriert |
| F-BOT-10 | Proaktive Alerts bei Verbindungsverlust | MUST | Alert ohne User-Interaktion |
| F-BOT-11 | Proaktive Alerts bei Überhitzung (>70°C) | SHOULD | Temperatur-Warning |
| F-BOT-12 | Proaktive Alerts bei Mikrofon-Fehler | MUST | USB-Disconnect wird erkannt |

### 4.4 System-Stabilität (F-SYS)

| ID | Anforderung | Priorität | Akzeptanzkriterium |
|----|-------------|-----------|---------------------|
| F-SYS-01 | Alle Services starten automatisch bei Boot | MUST | Nach Reboot alles funktional |
| F-SYS-02 | Services starten nach Crash automatisch neu | MUST | `kill -9` führt zu Restart |
| F-SYS-03 | System läuft 24h stabil ohne Intervention | MUST | Keine manuellen Eingriffe nötig |
| F-SYS-04 | Logs sind via journald einsehbar | MUST | `journalctl -u babymonitor*` funktioniert |

---

## 5. Nicht-Funktionale Anforderungen

### 5.1 Zuverlässigkeit (NFR-REL)

| ID | Anforderung | Messung |
|----|-------------|---------|
| NFR-REL-01 | Verfügbarkeit >99.5% (exkl. geplante Wartung) | Max 3.5h Ausfall/Monat |
| NFR-REL-02 | MTTR (Mean Time To Recovery) <2 Min | Zeit von Crash bis Stream wieder da |
| NFR-REL-03 | Kein Datenverlust bei Stromausfall | Stateless Design, keine persistenten Daten |
| NFR-REL-04 | Graceful Degradation bei Teilausfall | Bot funktioniert auch wenn Stream down |

### 5.2 Performance (NFR-PERF)

| ID | Anforderung | Messung |
|----|-------------|---------|
| NFR-PERF-01 | Audio-Latenz End-to-End <500ms | Klatschen-Test |
| NFR-PERF-02 | CPU-Auslastung im Normalbetrieb <30% | `top` / `htop` |
| NFR-PERF-03 | RAM-Verbrauch <256MB | `free -h` |
| NFR-PERF-04 | Telegram-Bot Antwortzeit <2s | Stoppuhr |
| NFR-PERF-05 | Boot-to-Stream Zeit <90s | Zeit von Power-On bis Audio |

### 5.3 Sicherheit (NFR-SEC)

| ID | Anforderung | Implementation |
|----|-------------|----------------|
| NFR-SEC-01 | Bot Token nicht im Code | Environment Variable / .env File |
| NFR-SEC-02 | Nur autorisierte Telegram-Chats | Whitelist von Chat-IDs |
| NFR-SEC-03 | Minimale offene Ports | Nur 1704, 1705 im LAN |
| NFR-SEC-04 | SSH nur via Key-Auth | PasswordAuthentication no |
| NFR-SEC-05 | .env Datei nicht in Git | .gitignore Entry |
| NFR-SEC-06 | Regelmäßige OS-Updates | unattended-upgrades |

### 5.4 Wartbarkeit (NFR-MAIN)

| ID | Anforderung | Implementation |
|----|-------------|----------------|
| NFR-MAIN-01 | Zentrale Konfiguration | Eine config.yaml Datei |
| NFR-MAIN-02 | Strukturiertes Logging | Python logging + journald |
| NFR-MAIN-03 | Code in Git versioniert | GitHub/GitLab Repository |
| NFR-MAIN-04 | Einfaches Update-Verfahren | git pull + systemctl restart |
| NFR-MAIN-05 | Dokumentierter Code | Docstrings, README |

---

## 6. Telegram Bot Spezifikation

### 6.1 Bot-Befehle Detail

#### `/status`
```
🟢 BabyMonitor Online

📊 System:
   Uptime: 2d 14h 32m
   CPU: 12% | RAM: 180MB
   Temp: 45°C

🔊 Audio:
   Stream: Active
   Volume: 80%
   
📱 Clients:
   Connected: 1
   Last seen: just now
```

#### `/restart`
```
🔄 Snapserver wird neugestartet...

✅ Neustart erfolgreich
   Stream wieder verfügbar
```

#### `/reboot`
```
⚠️ System-Neustart in 5 Sekunden...

[Nach Reboot automatisch:]
✅ BabyMonitor wieder online
   Boot-Zeit: 47s
```

#### `/mute`
```
🔇 Audio stumm geschaltet

Mikrofon-Capture pausiert.
Nutze /unmute zum Reaktivieren.
```

#### `/unmute`
```
🔊 Audio aktiviert

Mikrofon-Capture läuft wieder.
```

#### `/volume 80`
```
🎚️ Lautstärke angepasst

Neuer Wert: 80%
Vorheriger Wert: 65%
```

#### `/ping`
```
🏓 Pong!

Latenz: 12ms
Server: OK
```

#### `/help`
```
📖 BabyMonitor Befehle

/status  - System-Status anzeigen
/restart - Audio-Stream neustarten
/reboot  - Raspberry Pi neustarten
/mute    - Audio stumm schalten
/unmute  - Audio aktivieren
/volume  - Lautstärke setzen (0-100)
/ping    - Verbindungstest
/help    - Diese Hilfe anzeigen
```

### 6.2 Proaktive Alerts

| Event | Trigger | Nachricht | Cooldown |
|-------|---------|-----------|----------|
| Client Disconnect | Kein Client für >10s | 🔴 **Verbindung verloren!**<br>Letzter Client: vor 12s<br>Prüfe Snapcast App! | 5 min |
| Client Reconnect | Client verbindet nach Disconnect | 🟢 **Verbindung wiederhergestellt**<br>Downtime: 45s | - |
| Überhitzung Warning | CPU Temp >70°C | 🌡️ **Temperatur-Warnung**<br>Aktuelle Temp: 72°C<br>Schwellwert: 70°C | 15 min |
| Überhitzung Critical | CPU Temp >80°C | 🔥 **KRITISCHE TEMPERATUR**<br>Aktuelle Temp: 82°C<br>System könnte drosseln! | 5 min |
| Mikrofon Fehler | USB Device nicht erkannt | 🎤 **Mikrofon nicht gefunden!**<br>USB-Gerät prüfen | 5 min |
| Service Crash | systemd restart triggered | ⚠️ **Service neugestartet**<br>Dienst: snapserver<br>Grund: Unexpected exit | 5 min |
| Boot Complete | System hochgefahren | ✅ **BabyMonitor gestartet**<br>Boot-Zeit: 47s<br>Alle Services: OK | - |

### 6.3 Authorisierung

```python
# Nur diese Chat-IDs dürfen Commands senden
ALLOWED_CHAT_IDS = [
    123456789,  # Deine Telegram User ID
    987654321,  # Partner/in
]

# Alle anderen werden ignoriert (kein Error, kein Log)
```

**Chat-ID herausfinden:**
1. Bot starten
2. `/start` an Bot senden
3. Log zeigt: `Unauthorized access attempt from chat_id: XXXXXXX`
4. Diese ID zur Whitelist hinzufügen

---

## 7. Dateistruktur & Konfiguration

### 7.1 Projektstruktur

```
/opt/babymonitor/
├── config/
│   ├── config.yaml           # Zentrale Konfiguration
│   └── .env                   # Secrets (NICHT in Git!)
├── bot/
│   ├── __init__.py
│   ├── main.py               # Entry Point
│   ├── handlers.py           # Command Handlers
│   ├── monitoring.py         # Heartbeat & Alerts
│   └── system.py             # System Commands
├── scripts/
│   ├── install.sh            # Installation Script
│   ├── audio-capture.sh      # Audio Pipeline
│   └── health-check.sh       # Systemd Health Check
├── systemd/
│   ├── babymonitor-audio.service
│   ├── babymonitor-bot.service
│   └── snapserver.service.d/
│       └── override.conf
├── requirements.txt
├── README.md
└── .gitignore
```

### 7.2 Konfigurationsdatei (config.yaml)

```yaml
# /opt/babymonitor/config/config.yaml

# Audio Capture Settings
audio:
  device: "hw:1,0"            # ALSA device (via arecord -l ermitteln)
  sample_rate: 48000          # Hz
  channels: 1                 # Mono
  format: "S16_LE"            # 16-bit Little Endian
  volume: 80                  # Default Gain (0-100)
  pipe_path: "/tmp/snapfifo"  # Named Pipe für Snapserver

# Snapserver Settings
snapserver:
  stream_port: 1704
  control_port: 1705
  buffer_ms: 300              # Audio Buffer
  codec: "flac"               # flac, opus, pcm, vorbis

# Monitoring Settings
monitoring:
  heartbeat_interval: 5       # Sekunden zwischen Checks
  disconnect_timeout: 10      # Sekunden bis Disconnect-Alert
  reconnect_grace: 3          # Sekunden Reconnect-Toleranz
  temp_warning: 70            # °C - Warning Schwelle
  temp_critical: 80           # °C - Critical Schwelle
  alert_cooldown: 300         # Sekunden zwischen gleichen Alerts

# Telegram Bot Settings (Secrets in .env!)
telegram:
  parse_mode: "HTML"
  disable_notification: false # Alerts mit Sound

# Logging
logging:
  level: "INFO"               # DEBUG, INFO, WARNING, ERROR
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: null                  # null = nur journald
```

### 7.3 Environment-Variablen (.env)

```bash
# /opt/babymonitor/config/.env
# ACHTUNG: Diese Datei NIEMALS in Git committen!

# Telegram Bot Token (von @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Erlaubte Telegram Chat-IDs (komma-separiert)
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321

# Optional: Alert Chat (falls anders als Command Chat)
TELEGRAM_ALERT_CHAT_ID=123456789
```

### 7.4 Systemd Service Files

#### babymonitor-audio.service
```ini
[Unit]
Description=BabyMonitor Audio Capture
After=sound.target
Wants=snapserver.service

[Service]
Type=simple
ExecStart=/opt/babymonitor/scripts/audio-capture.sh
Restart=always
RestartSec=3
User=pi

[Install]
WantedBy=multi-user.target
```

#### babymonitor-bot.service
```ini
[Unit]
Description=BabyMonitor Telegram Bot
After=network-online.target snapserver.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/babymonitor
ExecStart=/opt/babymonitor/venv/bin/python -m bot.main
Restart=always
RestartSec=5
User=pi
EnvironmentFile=/opt/babymonitor/config/.env

[Install]
WantedBy=multi-user.target
```

#### snapserver.service.d/override.conf
```ini
[Service]
ExecStart=
ExecStart=/usr/bin/snapserver -c /opt/babymonitor/config/snapserver.conf
```

### 7.5 .gitignore

```gitignore
# Secrets
config/.env
*.env

# Python
__pycache__/
*.py[cod]
venv/
.venv/

# IDE
.vscode/
.idea/

# Logs
*.log

# OS
.DS_Store
Thumbs.db
```

---

## 8. Implementierungs-Roadmap

### Phase 1: Basis Audio-Streaming (Tag 1)

**Ziel:** Audio vom Mikrofon ist in Snapcast App hörbar

**Tasks:**

1. **Raspberry Pi OS installieren**
   ```bash
   # Raspberry Pi Imager: Raspberry Pi OS Lite (64-bit) Bookworm
   # Hostname: babymonitor
   # SSH aktivieren
   # WLAN konfigurieren
   ```

2. **System aktualisieren**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo reboot
   ```

3. **USB-Mikrofon verifizieren**
   ```bash
   # Mikrofon anschließen
   arecord -l
   # Erwartete Ausgabe: card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
   
   # Test-Aufnahme
   arecord -D hw:1,0 -f S16_LE -r 48000 -c 1 -d 5 test.wav
   aplay test.wav
   ```

4. **Snapserver installieren**
   ```bash
   sudo apt install snapserver -y
   ```

5. **Named Pipe erstellen**
   ```bash
   mkfifo /tmp/snapfifo
   ```

6. **Snapserver konfigurieren**
   ```bash
   sudo nano /etc/snapserver.conf
   ```
   ```ini
   [stream]
   source = pipe:///tmp/snapfifo?name=BabyMonitor&sampleformat=48000:16:1
   ```

7. **Audio-Capture starten (manueller Test)**
   ```bash
   arecord -D hw:1,0 -f S16_LE -r 48000 -c 1 -t raw | \
     tee /tmp/snapfifo > /dev/null
   ```

8. **Snapcast App testen**
   - App installieren (Android/iOS)
   - Server-IP eingeben
   - Verbinden und Audio prüfen

**Akzeptanzkriterium Phase 1:**
- [ ] Audio vom Mikrofon ist in Snapcast App hörbar
- [ ] Latenz <1s subjektiv

---

### Phase 2: Systemd Services (Tag 1-2)

**Ziel:** System startet nach Reboot automatisch

**Tasks:**

1. **Projektverzeichnis erstellen**
   ```bash
   sudo mkdir -p /opt/babymonitor/{config,scripts,systemd}
   sudo chown -R pi:pi /opt/babymonitor
   ```

2. **Audio-Capture Script erstellen**
   ```bash
   nano /opt/babymonitor/scripts/audio-capture.sh
   ```
   ```bash
   #!/bin/bash
   
   DEVICE="hw:1,0"
   PIPE="/tmp/snapfifo"
   
   # Pipe erstellen falls nicht vorhanden
   [ -p "$PIPE" ] || mkfifo "$PIPE"
   
   # Audio capture starten
   exec arecord -D "$DEVICE" -f S16_LE -r 48000 -c 1 -t raw 2>/dev/null | \
     tee "$PIPE" > /dev/null
   ```
   ```bash
   chmod +x /opt/babymonitor/scripts/audio-capture.sh
   ```

3. **Systemd Services installieren**
   ```bash
   # Audio Service
   sudo nano /etc/systemd/system/babymonitor-audio.service
   # (Inhalt von 7.4)
   
   # Services aktivieren
   sudo systemctl daemon-reload
   sudo systemctl enable snapserver babymonitor-audio
   sudo systemctl start snapserver babymonitor-audio
   ```

4. **Reboot-Test**
   ```bash
   sudo reboot
   # Nach Boot: Snapcast App verbinden
   ```

**Akzeptanzkriterium Phase 2:**
- [ ] Nach Reboot ist Audio automatisch in App verfügbar
- [ ] `systemctl status babymonitor-audio` zeigt "active (running)"

---

### Phase 3: Telegram Bot Basis (Tag 2-3)

**Ziel:** Bot antwortet auf /status Command

**Tasks:**

1. **Telegram Bot erstellen**
   - @BotFather in Telegram öffnen
   - `/newbot` senden
   - Name: "BabyMonitor Bot"
   - Username: `dein_babymonitor_bot`
   - Token speichern!

2. **Python Environment einrichten**
   ```bash
   sudo apt install python3-venv python3-pip -y
   cd /opt/babymonitor
   python3 -m venv venv
   source venv/bin/activate
   pip install python-telegram-bot pyyaml python-dotenv
   pip freeze > requirements.txt
   ```

3. **Bot-Grundgerüst erstellen**
   ```bash
   mkdir -p /opt/babymonitor/bot
   touch /opt/babymonitor/bot/__init__.py
   ```

4. **main.py erstellen**
   ```python
   # /opt/babymonitor/bot/main.py
   
   import asyncio
   import logging
   import os
   from dotenv import load_dotenv
   from telegram import Update
   from telegram.ext import Application, CommandHandler, ContextTypes
   
   # Logging
   logging.basicConfig(
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
       level=logging.INFO
   )
   logger = logging.getLogger(__name__)
   
   # Environment laden
   load_dotenv('/opt/babymonitor/config/.env')
   TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
   ALLOWED_IDS = [int(x) for x in os.getenv('TELEGRAM_ALLOWED_CHAT_IDS', '').split(',') if x]
   
   def authorized(func):
       """Decorator für Authorisierung"""
       async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
           if update.effective_chat.id not in ALLOWED_IDS:
               logger.warning(f"Unauthorized: {update.effective_chat.id}")
               return
           return await func(update, context)
       return wrapper
   
   @authorized
   async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
       """System-Status anzeigen"""
       import subprocess
       
       # CPU Temp
       temp = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, text=True)
       temp = temp.stdout.strip().replace("temp=", "").replace("'C", "°C")
       
       # Uptime
       uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
       uptime = uptime.stdout.strip().replace("up ", "")
       
       # CPU Usage
       cpu = subprocess.run(['grep', 'cpu ', '/proc/stat'], capture_output=True, text=True)
       
       msg = f"""🟢 <b>BabyMonitor Online</b>
   
   📊 <b>System:</b>
      Uptime: {uptime}
      Temp: {temp}
   
   🔊 <b>Audio:</b>
      Stream: Active
   """
       await update.message.reply_text(msg, parse_mode='HTML')
   
   @authorized
   async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
       """Snapserver neustarten"""
       import subprocess
       await update.message.reply_text("🔄 Snapserver wird neugestartet...")
       subprocess.run(['sudo', 'systemctl', 'restart', 'snapserver', 'babymonitor-audio'])
       await update.message.reply_text("✅ Neustart erfolgreich")
   
   @authorized
   async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):
       """System neustarten"""
       import subprocess
       await update.message.reply_text("⚠️ System-Neustart in 5 Sekunden...")
       subprocess.run(['sudo', 'shutdown', '-r', '+0'])
   
   @authorized
   async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
       """Health Check"""
       await update.message.reply_text("🏓 Pong!")
   
   @authorized
   async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
       """Hilfe anzeigen"""
       msg = """📖 <b>BabyMonitor Befehle</b>
   
   /status  - System-Status anzeigen
   /restart - Audio-Stream neustarten
   /reboot  - Raspberry Pi neustarten
   /ping    - Verbindungstest
   /help    - Diese Hilfe
   """
       await update.message.reply_text(msg, parse_mode='HTML')
   
   def main():
       app = Application.builder().token(TOKEN).build()
       
       app.add_handler(CommandHandler("status", cmd_status))
       app.add_handler(CommandHandler("restart", cmd_restart))
       app.add_handler(CommandHandler("reboot", cmd_reboot))
       app.add_handler(CommandHandler("ping", cmd_ping))
       app.add_handler(CommandHandler("help", cmd_help))
       
       logger.info("Bot starting...")
       app.run_polling(allowed_updates=Update.ALL_TYPES)
   
   if __name__ == '__main__':
       main()
   ```

5. **.env Datei erstellen**
   ```bash
   nano /opt/babymonitor/config/.env
   ```
   ```
   TELEGRAM_BOT_TOKEN=dein_token_hier
   TELEGRAM_ALLOWED_CHAT_IDS=deine_chat_id
   ```

6. **Bot testen**
   ```bash
   cd /opt/babymonitor
   source venv/bin/activate
   python -m bot.main
   ```

7. **Systemd Service für Bot**
   ```bash
   sudo nano /etc/systemd/system/babymonitor-bot.service
   # (Inhalt von 7.4)
   
   sudo systemctl daemon-reload
   sudo systemctl enable babymonitor-bot
   sudo systemctl start babymonitor-bot
   ```

**Akzeptanzkriterium Phase 3:**
- [ ] `/status` zeigt korrekten System-Status
- [ ] `/restart` startet Stream neu
- [ ] Unauthorized Chat-IDs werden ignoriert

---

### Phase 4: Monitoring & Alerts (Tag 3-4)

**Ziel:** Verbindungsverlust wird erkannt und gemeldet

**Tasks:**

1. **Snapserver JSON-RPC API verstehen**
   ```bash
   # Client-Status abfragen
   echo '{"id":1,"jsonrpc":"2.0","method":"Server.GetStatus"}' | \
     nc localhost 1705
   ```

2. **monitoring.py erstellen**
   ```python
   # /opt/babymonitor/bot/monitoring.py
   
   import asyncio
   import json
   import socket
   import logging
   from datetime import datetime, timedelta
   
   logger = logging.getLogger(__name__)
   
   class ClientMonitor:
       def __init__(self, bot, chat_ids, config):
           self.bot = bot
           self.chat_ids = chat_ids
           self.config = config
           self.last_client_seen = None
           self.alert_sent = False
           self.last_alert_time = None
           
       def get_snapserver_status(self):
           """Snapserver Status via JSON-RPC abfragen"""
           try:
               sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
               sock.settimeout(2)
               sock.connect(('localhost', 1705))
               
               request = json.dumps({
                   "id": 1,
                   "jsonrpc": "2.0", 
                   "method": "Server.GetStatus"
               })
               sock.send((request + '\n').encode())
               
               response = sock.recv(4096).decode()
               sock.close()
               
               return json.loads(response)
           except Exception as e:
               logger.error(f"Snapserver query failed: {e}")
               return None
               
       def get_connected_clients(self):
           """Anzahl verbundener Clients ermitteln"""
           status = self.get_snapserver_status()
           if not status:
               return 0
               
           try:
               groups = status.get('result', {}).get('server', {}).get('groups', [])
               count = 0
               for group in groups:
                   for client in group.get('clients', []):
                       if client.get('connected', False):
                           count += 1
               return count
           except Exception as e:
               logger.error(f"Parse error: {e}")
               return 0
               
       async def send_alert(self, message):
           """Alert an alle Chat-IDs senden"""
           for chat_id in self.chat_ids:
               try:
                   await self.bot.send_message(
                       chat_id=chat_id,
                       text=message,
                       parse_mode='HTML'
                   )
               except Exception as e:
                   logger.error(f"Alert send failed: {e}")
                   
       async def check_loop(self):
           """Hauptschleife für Monitoring"""
           disconnect_timeout = self.config.get('disconnect_timeout', 10)
           heartbeat_interval = self.config.get('heartbeat_interval', 5)
           cooldown = self.config.get('alert_cooldown', 300)
           
           while True:
               try:
                   clients = self.get_connected_clients()
                   now = datetime.now()
                   
                   if clients > 0:
                       # Client verbunden
                       if self.alert_sent:
                           # Reconnect nach Disconnect
                           downtime = (now - self.last_client_seen).seconds if self.last_client_seen else 0
                           await self.send_alert(
                               f"🟢 <b>Verbindung wiederhergestellt</b>\n"
                               f"Downtime: {downtime}s"
                           )
                           self.alert_sent = False
                       self.last_client_seen = now
                       
                   else:
                       # Kein Client
                       if self.last_client_seen:
                           seconds_since = (now - self.last_client_seen).seconds
                           
                           if seconds_since >= disconnect_timeout and not self.alert_sent:
                               # Cooldown prüfen
                               if self.last_alert_time is None or \
                                  (now - self.last_alert_time).seconds >= cooldown:
                                   await self.send_alert(
                                       f"🔴 <b>Verbindung verloren!</b>\n"
                                       f"Letzter Client: vor {seconds_since}s\n"
                                       f"Prüfe Snapcast App!"
                                   )
                                   self.alert_sent = True
                                   self.last_alert_time = now
                                   
               except Exception as e:
                   logger.error(f"Monitor error: {e}")
                   
               await asyncio.sleep(heartbeat_interval)
   ```

3. **main.py erweitern (Monitoring integrieren)**
   ```python
   # In main.py ergänzen:
   
   from bot.monitoring import ClientMonitor
   
   async def post_init(application):
       """Nach Bot-Init: Monitoring starten"""
       monitor = ClientMonitor(
           bot=application.bot,
           chat_ids=ALLOWED_IDS,
           config={
               'disconnect_timeout': 10,
               'heartbeat_interval': 5,
               'alert_cooldown': 300
           }
       )
       asyncio.create_task(monitor.check_loop())
   
   def main():
       app = Application.builder().token(TOKEN).post_init(post_init).build()
       # ... rest
   ```

4. **Zusätzliche Commands implementieren**
   - `/mute` - Audio-Capture stoppen
   - `/unmute` - Audio-Capture starten
   - `/volume` - amixer Integration

5. **Temperatur-Monitoring hinzufügen**
   ```python
   def get_cpu_temp():
       with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
           return int(f.read()) / 1000
   ```

**Akzeptanzkriterium Phase 4:**
- [ ] Bei WLAN-Disconnect am Handy kommt Alert nach 10-15s
- [ ] Bei Reconnect kommt Entwarnung
- [ ] `/mute` und `/unmute` funktionieren
- [ ] Temperatur-Warning bei >70°C

---

### Phase 5: Härtung & Dokumentation (Tag 4-5)

**Ziel:** System ist produktionsreif und dokumentiert

**Tasks:**

1. **SSH absichern**
   ```bash
   # SSH Key generieren (auf deinem PC)
   ssh-keygen -t ed25519 -C "babymonitor"
   ssh-copy-id -i ~/.ssh/id_ed25519.pub pi@babymonitor.local
   
   # Password-Auth deaktivieren
   sudo nano /etc/ssh/sshd_config
   # PasswordAuthentication no
   sudo systemctl restart sshd
   ```

2. **Firewall konfigurieren**
   ```bash
   sudo apt install ufw -y
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow ssh
   sudo ufw allow 1704/tcp  # Snapcast Stream
   sudo ufw allow 1705/tcp  # Snapcast Control
   sudo ufw enable
   ```

3. **Unattended Upgrades**
   ```bash
   sudo apt install unattended-upgrades -y
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```

4. **Logging optimieren**
   ```bash
   # Log-Rotation prüfen
   journalctl --disk-usage
   sudo journalctl --vacuum-size=100M
   ```

5. **README.md erstellen**
   - Installationsanleitung
   - Konfiguration
   - Troubleshooting

6. **24h Stabilitätstest**
   - System laufen lassen
   - Mehrfach Disconnect/Reconnect testen
   - Logs auf Fehler prüfen

7. **Backup erstellen**
   ```bash
   tar -czvf babymonitor-backup.tar.gz /opt/babymonitor
   ```

**Akzeptanzkriterium Phase 5:**
- [ ] SSH nur mit Key möglich
- [ ] Firewall aktiv
- [ ] System läuft 24h ohne Fehler
- [ ] Dokumentation vollständig

---

## 9. Testkriterien & Akzeptanztests

### 9.1 Audio-Streaming Tests

| ID | Testfall | Schritte | Erwartetes Ergebnis | Status |
|----|----------|----------|---------------------|--------|
| T-A01 | Verbindung herstellen | Snapcast App öffnen, Server-IP eingeben | Verbindung wird hergestellt | ☐ |
| T-A02 | Audio hörbar | In Mikrofon sprechen | Audio in App verständlich | ☐ |
| T-A03 | Latenz prüfen | Klatschen-Test | Verzögerung <1s subjektiv | ☐ |
| T-A04 | Bildschirm sperren | Phone sperren, warten | Audio läuft weiter | ☐ |
| T-A05 | App-Wechsel | Andere App öffnen | Audio im Hintergrund | ☐ |
| T-A06 | Nach Reboot | Pi rebooten | Audio nach ~60s verfügbar | ☐ |
| T-A07 | Dauerbetrieb | 1h laufen lassen | Keine Aussetzer | ☐ |
| T-A08 | 24h Test | Über Nacht laufen | Stabil, keine Crashes | ☐ |

### 9.2 Verbindungs-Monitoring Tests

| ID | Testfall | Schritte | Erwartetes Ergebnis | Status |
|----|----------|----------|---------------------|--------|
| T-C01 | WLAN deaktivieren | WLAN am Handy aus | Alert nach 10-15s | ☐ |
| T-C02 | WLAN reaktivieren | WLAN wieder ein | Entwarnung kommt | ☐ |
| T-C03 | App schließen | Snapcast App beenden | Alert nach 10-15s | ☐ |
| T-C04 | App neustarten | Snapcast App öffnen | Entwarnung kommt | ☐ |
| T-C05 | Pi Netzwerk trennen | Kabel ziehen (falls LAN) | Alert nach 10-15s | ☐ |
| T-C06 | Mikrofon abziehen | USB Mic entfernen | Mikrofon-Fehler Alert | ☐ |
| T-C07 | Alert Cooldown | 2x schnell disconnecten | Nur 1 Alert | ☐ |

### 9.3 Telegram Bot Tests

| ID | Testfall | Schritte | Erwartetes Ergebnis | Status |
|----|----------|----------|---------------------|--------|
| T-B01 | /status | Command senden | Status-Nachricht <2s | ☐ |
| T-B02 | /restart | Command senden | Stream kurz unterbrochen, dann OK | ☐ |
| T-B03 | /reboot | Command senden | Pi bootet, meldet sich nach ~60s | ☐ |
| T-B04 | /ping | Command senden | "Pong!" Antwort | ☐ |
| T-B05 | /help | Command senden | Befehlsliste | ☐ |
| T-B06 | /mute | Command senden | Stille im Stream | ☐ |
| T-B07 | /unmute | Command senden | Audio wieder da | ☐ |
| T-B08 | /volume 50 | Command senden | Lautstärke ändert sich | ☐ |
| T-B09 | Unauthorized User | Von fremder Chat-ID | Keine Antwort, kein Fehler | ☐ |
| T-B10 | Bot nach Reboot | Pi rebooten | Bot automatisch aktiv | ☐ |

### 9.4 System-Stabilitäts Tests

| ID | Testfall | Schritte | Erwartetes Ergebnis | Status |
|----|----------|----------|---------------------|--------|
| T-S01 | Service Kill | `sudo kill -9 $(pgrep snapserver)` | Automatischer Restart <10s | ☐ |
| T-S02 | Bot Kill | `sudo kill -9 $(pgrep python)` | Automatischer Restart <10s | ☐ |
| T-S03 | Reboot | `sudo reboot` | Alles nach ~60s funktional | ☐ |
| T-S04 | Power Cycle | Strom aus/ein | Alles nach ~90s funktional | ☐ |
| T-S05 | Speicher-Check | `free -h` | <256MB verwendet | ☐ |
| T-S06 | CPU-Check | `top` | <30% im Normalbetrieb | ☐ |
| T-S07 | Temperatur-Check | `vcgencmd measure_temp` | <60°C im Normalbetrieb | ☐ |

---

## 10. Installationsanleitung

### 10.1 Voraussetzungen

**Hardware:**
- Raspberry Pi 3B (oder neuer)
- MicroSD Karte (min. 8GB)
- KISEER USB Mikrofon
- Netzteil 5V/2.5A
- Netzwerk (LAN oder WLAN)

**Software:**
- Raspberry Pi Imager
- SSH Client (Terminal/PuTTY)
- Telegram Account
- Snapcast App (Android/iOS)

### 10.2 Schnellinstallation

```bash
# 1. Als pi User einloggen
ssh pi@babymonitor.local

# 2. Repository klonen
git clone https://github.com/dein-user/babymonitor.git /opt/babymonitor

# 3. Installer ausführen
cd /opt/babymonitor
chmod +x scripts/install.sh
./scripts/install.sh

# 4. Konfiguration anpassen
nano /opt/babymonitor/config/.env
# TELEGRAM_BOT_TOKEN=dein_token
# TELEGRAM_ALLOWED_CHAT_IDS=deine_id

# 5. Services starten
sudo systemctl start babymonitor-audio babymonitor-bot

# 6. Testen
# - Snapcast App verbinden
# - /status an Bot senden
```

### 10.3 Manuelle Installation (Schritt für Schritt)

Siehe [Phase 1-5 in Kapitel 8](#8-implementierungs-roadmap)

### 10.4 Troubleshooting

#### Audio nicht hörbar

```bash
# Mikrofon prüfen
arecord -l
# Sollte "USB Audio Device" zeigen

# Audio-Service Status
sudo systemctl status babymonitor-audio

# Snapserver Status
sudo systemctl status snapserver

# Pipe prüfen
ls -la /tmp/snapfifo
# Sollte "prw-r--r--" zeigen (Pipe)

# Manueller Test
arecord -D hw:1,0 -f S16_LE -r 48000 -c 1 -d 5 test.wav
aplay test.wav
```

#### Bot antwortet nicht

```bash
# Bot-Service Status
sudo systemctl status babymonitor-bot

# Logs prüfen
journalctl -u babymonitor-bot -f

# Token prüfen
cat /opt/babymonitor/config/.env

# Manuell starten zum Debuggen
cd /opt/babymonitor
source venv/bin/activate
python -m bot.main
```

#### Verbindung instabil

```bash
# WLAN Signal prüfen
iwconfig wlan0

# Netzwerk-Qualität
ping -c 100 192.168.1.1 | tail -3

# Bei schlechtem WLAN: LAN-Kabel nutzen
```

---

## 11. Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| WLAN-Ausfall | Mittel | Hoch | Alert bei Disconnect, LAN als Backup |
| Mikrofon-Defekt | Niedrig | Hoch | USB-Device Check, Alert bei Fehler |
| SD-Karten-Korruption | Niedrig | Hoch | Read-Only Root (optional), Backup |
| Pi Überhitzung | Niedrig | Mittel | Temperatur-Monitoring, Gehäuse mit Lüftung |
| Telegram API Ausfall | Sehr niedrig | Mittel | Snapcast App zeigt Connection-Status |
| Stromausfall | Mittel | Mittel | Auto-Start nach Boot |
| Bot Token kompromittiert | Sehr niedrig | Hoch | Chat-ID Whitelist, Token in .env |

---

## 12. Glossar

| Begriff | Erklärung |
|---------|-----------|
| **ALSA** | Advanced Linux Sound Architecture - Linux Audio-System |
| **Snapcast** | Multi-Room Audio Streaming Software |
| **Snapserver** | Server-Komponente von Snapcast |
| **Named Pipe / FIFO** | Inter-Process Communication Mechanismus |
| **systemd** | Linux Service Manager |
| **JSON-RPC** | Remote Procedure Call Protokoll |
| **Heartbeat** | Regelmäßiger Verbindungstest |
| **Cooldown** | Wartezeit zwischen wiederholten Alerts |
| **Bookworm** | Debian 12 Codename (aktuelle Pi OS Basis) |
| **JWT** | JSON Web Token (nicht verwendet, nur Info) |

---

## Changelog

| Version | Datum | Änderungen |
|---------|-------|------------|
| 1.0 | 2024-12-14 | Initial Release |

---

*Erstellt für Claude Code Übergabe*
