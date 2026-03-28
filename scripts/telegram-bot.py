#!/usr/bin/env python3
"""
BabyMonitor Telegram Bot
- Setup wizard for new users
- Control commands: status, pause, resume, beep
- Git update functionality
- Runs on each Pi with its own bot token
"""

import os
import sys
import json
import asyncio
import subprocess
import logging
import urllib.request
import tempfile
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters, ConversationHandler
)

# WiFi conversation states
WIFI_MENU = 0
WIFI_PASSWORD = 1

# Paths
CONFIG_DIR = Path("/opt/babymonitor/config")
SCRIPTS_DIR = Path("/opt/babymonitor/scripts")
CONFIG_FILE = CONFIG_DIR / "config.env"
BOT_CONFIG_FILE = CONFIG_DIR / "bot_config.json"
PAUSE_FILE = CONFIG_DIR / "paused"
REPO_DIR = Path("/opt/babymonitor")

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def load_config():
    """Load config.env as dict"""
    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    # Strip inline comments
                    if '#' in val:
                        val = val.split('#')[0]
                    config[key.strip()] = val.strip().strip('"')
    return config


# Load config once at startup
CONFIG = load_config()
DEVICE_NAME = CONFIG.get('DEVICE_NAME', 'Bebefon')
OWNER_NAME = CONFIG.get('OWNER_NAME', '')
GIFT_GIVER = CONFIG.get('GIFT_GIVER', 'den Schenker')


def load_bot_config():
    """Load bot-specific config"""
    if BOT_CONFIG_FILE.exists():
        with open(BOT_CONFIG_FILE) as f:
            return json.load(f)
    return {"authorized_users": [], "setup_complete": False, "device_name": "Bebefon"}


def save_bot_config(config):
    """Save bot-specific config"""
    with open(BOT_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def run_command(cmd, timeout=30):
    """Run shell command and return output"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def get_service_status(service):
    """Get systemd service status"""
    ok, output = run_command(f"systemctl is-active {service}")
    return output.strip()


def fetch_snapcast_apk_info():
    """Fetch latest Snapcast APK info from F-Droid API. Returns (version, url) or (None, None)."""
    try:
        req = urllib.request.Request(
            "https://f-droid.org/api/v1/packages/de.badaix.snapcast",
            headers={"User-Agent": "bebefon-bot"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        pkg = data["packages"][0]
        version = pkg["versionName"]
        version_code = pkg["versionCode"]
        url = f"https://f-droid.org/repo/de.badaix.snapcast_{version_code}.apk"
        return version, url
    except Exception:
        return None, None


def is_authorized(update: Update, bot_config: dict) -> bool:
    """Check if user is authorized"""
    user_id = update.effective_user.id
    # First user to interact becomes authorized if no users exist
    if not bot_config.get("authorized_users"):
        return True
    return user_id in bot_config["authorized_users"]


# ============== Command Handlers ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - welcome and setup wizard"""
    bot_config = load_bot_config()
    user = update.effective_user
    user_id = user.id

    # Auto-authorize first user
    if not bot_config.get("authorized_users"):
        bot_config["authorized_users"] = [user_id]
        save_bot_config(bot_config)
        logger.info(f"Auto-authorized first user: {user_id} ({user.first_name})")

    if not is_authorized(update, bot_config):
        invite_code = load_config().get('INVITE_CODE', '')
        if invite_code:
            await update.message.reply_text(
                f"Kein Zugriff.\n\nFalls du einen Einladungscode hast, tippe:\n/join {invite_code.replace(invite_code, '<code>')}"
            )
        else:
            await update.message.reply_text("Du bist leider nicht berechtigt, diesen Bot zu nutzen.")
        return

    device_name = DEVICE_NAME

    if bot_config.get("setup_complete"):
        await update.message.reply_text(
            f"Willkommen zurueck bei {device_name}!\n\n"
            "Befehle:\n"
            "/status - Systemstatus anzeigen\n"
            "/pause - Alle Benachrichtigungen pausieren\n"
            "/resume - Benachrichtigungen fortsetzen\n"
            "/beep - Test-Piep senden\n"
            "/config - Aktuelle Konfiguration\n"
            "/update - Updates von Git laden\n"
            "/setup - Setup-Assistent erneut starten\n"
            "/help - Diese Hilfe anzeigen"
        )
    else:
        await update.message.reply_text(
            f"Willkommen beim {device_name} Setup!\n\n"
            "Ich helfe dir, dein Babyphone einzurichten.\n\n"
            "Lass uns loslegen:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Setup starten", callback_data="setup_start")]
            ])
        )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Join with invite code"""
    bot_config = load_bot_config()
    user = update.effective_user
    user_id = user.id

    if user_id in bot_config.get("authorized_users", []):
        await update.message.reply_text("Du hast bereits Zugriff!")
        return

    invite_code = load_config().get('INVITE_CODE', '')
    if not invite_code:
        await update.message.reply_text("Kein Einladungscode konfiguriert.")
        return

    provided = " ".join(context.args) if context.args else ""
    if provided == invite_code:
        bot_config.setdefault("authorized_users", []).append(user_id)
        save_bot_config(bot_config)
        logger.info(f"User {user_id} ({user.first_name}) joined via invite code")
        await update.message.reply_text(
            f"✅ Willkommen bei {DEVICE_NAME}!\n\nDu hast jetzt Zugriff. Tippe /start."
        )
    else:
        await update.message.reply_text("❌ Falscher Einladungscode.")


async def set_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set invite code via Telegram"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    if not context.args:
        current = load_config().get('INVITE_CODE', '(nicht gesetzt)')
        await update.message.reply_text(
            f"Aktueller Code: {current}\n\nNeuen Code setzen:\n/setcode <neuer-code>"
        )
        return

    new_code = context.args[0]
    config_path = str(CONFIG_FILE)

    with open(config_path, 'r') as f:
        content = f.read()

    if 'INVITE_CODE=' in content:
        import re
        content = re.sub(r'INVITE_CODE=.*', f'INVITE_CODE={new_code}', content)
    else:
        content += f'\nINVITE_CODE={new_code}\n'

    with open(config_path, 'w') as f:
        f.write(content)

    await update.message.reply_text(f"✅ Einladungscode gesetzt: {new_code}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    await update.message.reply_text(
        f"{DEVICE_NAME} Befehle:\n\n"
        "📊 *Status & Info*\n"
        "/status - Vollstaendiger Systemstatus\n"
        "/temp - CPU Temperatur anzeigen\n"
        "/uptime - Laufzeit anzeigen\n"
        "/config - Aktuelle Konfiguration\n\n"
        "🔔 *Benachrichtigungen*\n"
        "/pause - Alarme pausieren\n"
        "/resume - Alarme fortsetzen\n"
        "/beep - Test-Piep senden\n\n"
        "🔧 *Verwaltung*\n"
        "/restart - Dienste neu starten\n"
        "/reboot - Raspberry Pi neu starten\n"
        "/wifi - WiFi Status / Netzwerk wechseln / ein-aus\n"
        "/tailscale - Tailscale Status / verbinden / trennen\n"
        "/tailscale reauth - Account wechseln\n"
        "/tailscale disconnect - Tailscale trennen\n"
        "/update - Updates von Git laden\n"
        "/logs [service] - Logs anzeigen\n\n"
        "⚙️ *Einstellungen*\n"
        "/setup - Setup-Assistent\n"
        "/reset - Setup zuruecksetzen\n"
        "/setname <name> - Geraetename aendern\n"
        "/setcode <code> - Einladungscode setzen\n"
        "/join <code> - Mit Einladungscode beitreten",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system status"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    device_name = DEVICE_NAME
    config = load_config()

    # Service statuses
    services = {
        "snapserver": get_service_status("snapserver"),
        "babymonitor-audio": get_service_status("babymonitor-audio"),
        "babymonitor-monitor": get_service_status("babymonitor-monitor"),
        "babymonitor-mic-alert": get_service_status("babymonitor-mic-alert"),
        "tailscaled": get_service_status("tailscaled"),
    }

    # Tailscale IP + account
    ok, tailscale_ip = run_command("tailscale ip -4 2>/dev/null")
    tailscale_ip = tailscale_ip.strip() if ok else "Nicht verbunden"
    ok, ts_account = run_command("tailscale whois $(tailscale ip -4 2>/dev/null) 2>/dev/null | grep 'Name:' | tail -1")
    tailscale_account = ts_account.strip().replace("Name:", "").strip() if ok else ""

    # Mic status
    ok, mic_output = run_command("arecord -l 2>/dev/null | grep -c USB")
    mic_status = "Verbunden" if ok and mic_output.strip() != "0" else "NICHT ERKANNT"

    # Alerts paused?
    paused = PAUSE_FILE.exists()

    # Format status
    status_icons = {"active": "✅", "inactive": "⚪", "failed": "❌"}

    status_text = f"📊 {device_name} Status\n\n"
    status_text += f"🔔 Benachrichtigungen: {'⏸️ PAUSIERT' if paused else '✅ Aktiv'}\n"
    status_text += f"🎤 Mikrofon: {'✅' if mic_status == 'Verbunden' else '❌'} {mic_status}\n"
    ts_line = f"🌐 Tailscale: {tailscale_ip}"
    if tailscale_account:
        ts_line += f" ({tailscale_account})"
    status_text += ts_line + "\n\n"

    status_text += "Dienste:\n"
    for service, state in services.items():
        icon = status_icons.get(state, "❓")
        status_text += f"  {icon} {service}: {state}\n"

    status_text += f"\n📢 Ntfy Topic: {config.get('NTFY_TOPIC', 'nicht gesetzt')}"

    await update.message.reply_text(status_text)


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause alerts"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    PAUSE_FILE.touch()
    run_command("sudo systemctl stop babymonitor-monitor")

    # Ping healthchecks with /0 to prevent false alarms
    config = load_config()
    for url in config.get("HEALTHCHECK_URLS", "").split():
        run_command(f"curl -fsS -m 10 '{url}/0' > /dev/null 2>&1")

    await update.message.reply_text(
        "⏸️ Benachrichtigungen PAUSIERT\n\n"
        "Es werden keine Verbindungsalarme gesendet.\n"
        "Mit /resume wieder aktivieren."
    )


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume alerts"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    if PAUSE_FILE.exists():
        PAUSE_FILE.unlink()
    run_command("sudo systemctl start babymonitor-monitor")

    # Ping healthchecks to resume monitoring
    config = load_config()
    for url in config.get("HEALTHCHECK_URLS", "").split():
        run_command(f"curl -fsS -m 10 '{url}' > /dev/null 2>&1")

    await update.message.reply_text("▶️ Benachrichtigungen AKTIV\n\nUeberwachung laeuft.")


async def beep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send test beep"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    ok, output = run_command("sudo -u _snapserver /opt/babymonitor/scripts/heartbeat-beep.sh")
    if ok:
        await update.message.reply_text("🔔 Piep gesendet! Du solltest ihn im Stream hoeren.")
    else:
        await update.message.reply_text(f"❌ Piep fehlgeschlagen: {output}")


async def show_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current config"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    config = load_config()

    text = "⚙️ Aktuelle Konfiguration:\n\n"
    text += f"🎤 Audio-Geraet: {config.get('AUDIO_DEVICE', 'hw:2,0')}\n"
    text += f"📢 Ntfy Topic: {config.get('NTFY_TOPIC', 'nicht gesetzt')}\n"
    text += f"⏱️ Pruefintervall: {config.get('CHECK_INTERVAL', '5')}s\n"
    text += f"⏱️ Verbindungs-Timeout: {config.get('DISCONNECT_TIMEOUT', '10')}s\n"
    text += f"⏱️ Alarm-Cooldown: {config.get('ALERT_COOLDOWN', '30')}s\n"
    text += f"\n🔔 Piep aktiviert: {config.get('BEEP_ENABLED', 'true')}\n"
    text += f"🔔 Piep-Intervall: {config.get('BEEP_INTERVAL', '5')} Min\n"
    if config.get('INVITE_CODE'):
        text += f"\n🔑 Einladungscode: {config.get('INVITE_CODE')}\n"
        text += f"   Teilen mit: /join {config.get('INVITE_CODE')}\n"

    await update.message.reply_text(text)


async def git_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update from git"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    await update.message.reply_text("🔄 Suche nach Updates...")

    _, before = run_command(f"cd {REPO_DIR} && git rev-parse HEAD")
    ok, output = run_command(f"cd {REPO_DIR} && git fetch origin && git reset --hard origin/main", timeout=60)
    _, after = run_command(f"cd {REPO_DIR} && git rev-parse HEAD")

    if ok:
        if before.strip() != after.strip():
            await update.message.reply_text(
                "✅ Update war erfolgreich!\n\nMit /restart Dienste neu starten."
            )
        else:
            await update.message.reply_text("✅ Bereits auf dem neuesten Stand!")
    else:
        await update.message.reply_text(f"❌ Update fehlgeschlagen:\n{output[:500]}")


async def restart_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart all services"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    await update.message.reply_text("🔄 Starte Dienste neu...")

    services = ["snapserver", "babymonitor-audio", "babymonitor-monitor", "babymonitor-mic-alert"]
    results = []

    for service in services:
        ok, _ = run_command(f"sudo systemctl restart {service}")
        results.append(f"{'✅' if ok else '❌'} {service}")
    results.append("🔄 babymonitor-telegram (startet neu...)")

    await update.message.reply_text("Dienste neu gestartet:\n\n" + "\n".join(results))

    async def self_restart():
        await asyncio.sleep(2)
        run_command("sudo systemctl restart babymonitor-telegram")
    asyncio.create_task(self_restart())


async def tailscale_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Connect Tailscale - sends auth URL via Telegram"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    arg = context.args[0] if context.args else ""

    # Disconnect / logout
    if arg == "disconnect":
        ok, output = run_command("sudo tailscale logout")
        if ok:
            await update.message.reply_text(
                "🔌 Tailscale abgemeldet.\n\nMit /tailscale neu verbinden und anderem Account anmelden."
            )
        else:
            await update.message.reply_text(f"❌ Fehler: {output}")
        return

    # Check current status
    ok, ts_ip = run_command("tailscale ip -4 2>/dev/null")
    if ok and ts_ip.strip():
        ok2, ts_account = run_command("tailscale whois $(tailscale ip -4 2>/dev/null) 2>/dev/null | grep 'Name:' | tail -1")
        account = ts_account.strip().replace("Name:", "").strip() if ok2 else "unbekannt"
        await update.message.reply_text(
            f"✅ Tailscale verbunden\n\nIP: {ts_ip.strip()}\nAccount: {account}\n\n"
            "Optionen:\n/tailscale reauth - Account wechseln\n/tailscale disconnect - Trennen"
        )
        if arg != "reauth":
            return

    await update.message.reply_text("🔄 Starte Tailscale-Anmeldung...")

    try:
        cmd = ["sudo", "tailscale", "up", "--force-reauth"] if arg == "reauth" else ["sudo", "tailscale", "up"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        # Read output looking for auth URL (timeout 10s)
        auth_url = None
        try:
            async with asyncio.timeout(10):
                async for line in proc.stdout:
                    text_line = line.decode().strip()
                    for word in text_line.split():
                        if word.startswith("https://login.tailscale.com"):
                            auth_url = word
                            break
                    if auth_url:
                        break
        except asyncio.TimeoutError:
            pass

        if auth_url:
            await update.message.reply_text(
                f"🔑 Tailscale-Anmeldung\n\nOeffne diesen Link um dich anzumelden:\n{auth_url}\n\n"
                "Nach der Anmeldung verbindet sich der Pi automatisch."
            )
            # Wait in background for connection and notify
            async def notify_when_connected():
                for _ in range(60):  # max 5 min
                    await asyncio.sleep(5)
                    ok, ip = run_command("tailscale ip -4 2>/dev/null")
                    if ok and ip.strip():
                        ok2, acc = run_command("tailscale whois $(tailscale ip -4 2>/dev/null) 2>/dev/null | grep 'Name:' | tail -1")
                        account = acc.strip().replace("Name:", "").strip() if ok2 else ""
                        msg = f"✅ Tailscale verbunden!\n\nIP: {ip.strip()}"
                        if account:
                            msg += f"\nAccount: {account}"
                        await update.message.reply_text(msg)
                        return
            asyncio.create_task(notify_when_connected())
        else:
            # Maybe already connected without needing auth
            ok, ts_ip = run_command("tailscale ip -4 2>/dev/null")
            if ok and ts_ip.strip():
                await update.message.reply_text(f"✅ Tailscale verbunden! IP: {ts_ip.strip()}")
            else:
                await update.message.reply_text("❌ Kein Auth-Link erhalten. Versuche es nochmal mit /tailscale")

    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show logs"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    service = context.args[0] if context.args else "babymonitor-monitor"
    valid_services = ["snapserver", "babymonitor-audio", "babymonitor-monitor", "babymonitor-mic-alert"]

    if service not in valid_services:
        await update.message.reply_text(f"Gueltige Dienste: {', '.join(valid_services)}")
        return

    ok, output = run_command(f"journalctl -u {service} -n 20 --no-pager")

    if ok and output:
        # Truncate if too long
        if len(output) > 3000:
            output = output[-3000:]
        await update.message.reply_text(f"📋 Logs fuer {service}:\n\n```\n{output}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text("Keine Logs gefunden.")


async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set device name"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    if not context.args:
        await update.message.reply_text("Verwendung: /setname <Geraetename>\nBeispiel: /setname Babyzimmer")
        return

    new_name = " ".join(context.args)
    bot_config["device_name"] = new_name
    save_bot_config(bot_config)

    await update.message.reply_text(f"✅ Geraetename gesetzt: {new_name}")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset setup wizard"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    bot_config["setup_complete"] = False
    save_bot_config(bot_config)

    await update.message.reply_text(
        "🔄 Setup zurueckgesetzt!\n\n"
        "Sende /start um den Setup-Assistenten erneut zu starten."
    )


async def reboot_pi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reboot the Pi"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    await update.message.reply_text("🔄 Neustart wird ausgefuehrt...\n\nDas Babyphone ist in ca. 1 Minute wieder online.")
    run_command("sudo reboot")


async def temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Pi temperature"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    ok, temp = run_command("vcgencmd measure_temp 2>/dev/null || cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")

    if "temp=" in temp:
        # vcgencmd format: temp=45.0'C
        temp_str = temp.strip()
    elif temp.strip().isdigit():
        # /sys format: 45000 (millidegrees)
        temp_c = int(temp.strip()) / 1000
        temp_str = f"temp={temp_c:.1f}'C"
    else:
        temp_str = "Nicht verfuegbar"

    await update.message.reply_text(f"🌡️ CPU Temperatur: {temp_str}")


async def uptime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system uptime"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    ok, output = run_command("uptime -p")
    await update.message.reply_text(f"⏱️ Laufzeit: {output.strip()}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages - play them in baby's room"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    await update.message.reply_text("🎤 Sprachnachricht empfangen, wird abgespielt...")

    try:
        # Download voice message
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            temp_path = f.name

        await file.download_to_drive(temp_path)

        # Convert to WAV and play through speaker
        wav_path = temp_path.replace(".ogg", ".wav")
        ok, output = run_command(f"ffmpeg -y -i {temp_path} -ar 48000 -ac 1 {wav_path} 2>/dev/null")

        if ok:
            # Play through default audio output (speaker)
            ok, output = run_command(f"aplay {wav_path} 2>&1")
            if ok:
                await update.message.reply_text("✅ Nachricht wurde im Babyzimmer abgespielt!")
            else:
                await update.message.reply_text(f"❌ Abspielen fehlgeschlagen: {output[:200]}")
        else:
            await update.message.reply_text("❌ Audio-Konvertierung fehlgeschlagen")

        # Cleanup
        run_command(f"rm -f {temp_path} {wav_path}")

    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {str(e)}")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle audio files - play them in baby's room"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    await update.message.reply_text("🎵 Audio empfangen, wird abgespielt...")

    try:
        # Download audio file
        audio = update.message.audio or update.message.document
        file = await context.bot.get_file(audio.file_id)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
            temp_path = f.name

        await file.download_to_drive(temp_path)

        # Convert to WAV and play
        wav_path = temp_path + ".wav"
        ok, output = run_command(f"ffmpeg -y -i {temp_path} -ar 48000 -ac 1 {wav_path} 2>/dev/null")

        if ok:
            ok, output = run_command(f"aplay {wav_path} 2>&1")
            if ok:
                await update.message.reply_text("✅ Audio wurde im Babyzimmer abgespielt!")
            else:
                await update.message.reply_text(f"❌ Abspielen fehlgeschlagen: {output[:200]}")
        else:
            await update.message.reply_text("❌ Audio-Konvertierung fehlgeschlagen")

        # Cleanup
        run_command(f"rm -f {temp_path} {wav_path}")

    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {str(e)}")


# ============== Setup Wizard ==============

async def setup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle setup wizard callbacks"""
    query = update.callback_query
    await query.answer()

    bot_config = load_bot_config()
    data = query.data

    if data == "setup_start":
        await query.edit_message_text(
            "📱 Schritt 1: Apps installieren\n\n"
            "Installiere diese 3 Apps auf deinem Handy:\n\n"
            "1️⃣ **Tailscale** (VPN fuer Fernzugriff)\n"
            "   iOS: https://apps.apple.com/app/tailscale/id1470499037\n"
            "   Android: https://play.google.com/store/apps/details?id=com.tailscale.ipn\n\n"
            "2️⃣ **Snapcast** (Audio-Streaming)\n"
            "   iOS: https://apps.apple.com/us/app/snapcast-client/id1552559653\n"
            "   Android: APK direkt herunterladen (Button unten) oder F-Droid\n\n"
            "3️⃣ **Ntfy** (Push-Benachrichtigungen)\n"
            "   iOS: https://apps.apple.com/app/ntfy/id1625396347\n"
            "   Android: https://play.google.com/store/apps/details?id=io.heckel.ntfy\n\n"
            "Tippe auf 'Weiter' wenn alle Apps installiert sind.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Snapcast APK senden (Android)", callback_data="setup_send_apk")],
                [InlineKeyboardButton("Weiter →", callback_data="setup_tailscale")]
            ])
        )

    elif data == "setup_tailscale":
        # Get Tailscale status
        ok, ts_status = run_command("tailscale status --json 2>/dev/null")

        await query.edit_message_text(
            "🌐 Schritt 2: Tailscale verbinden\n\n"
            "Tailscale erstellt ein sicheres Netzwerk, damit du dich von ueberall verbinden kannst (auch unterwegs mit mobilen Daten).\n\n"
            "1. Oeffne die Tailscale App auf deinem Handy\n"
            "2. Erstelle ein Konto oder melde dich an\n"
            "3. Aktiviere Tailscale\n\n"
            "Sobald du verbunden bist, tippe auf 'Weiter'.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("← Zurueck", callback_data="setup_start"),
                 InlineKeyboardButton("Weiter →", callback_data="setup_tailscale_link")]
            ])
        )

    elif data == "setup_tailscale_link":
        # Check if we need to generate auth URL for the Pi
        ok, ts_ip = run_command("tailscale ip -4 2>/dev/null")
        ts_ip = ts_ip.strip() if ok else None

        if ts_ip:
            await query.edit_message_text(
                "🌐 Schritt 2b: Tailscale Verbindung\n\n"
                "✅ Das Babyphone ist bereits mit Tailscale verbunden!\n\n"
                f"📍 {DEVICE_NAME} Tailscale IP: `{ts_ip}`\n\n"
                "Stelle sicher, dass dein Handy auch mit Tailscale verbunden ist.\n"
                "Du findest dein Handy dann in der Tailscale App.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← Zurueck", callback_data="setup_tailscale"),
                     InlineKeyboardButton("Weiter →", callback_data="setup_snapcast")]
                ])
            )
        else:
            # Need to set up Tailscale on Pi first
            await query.edit_message_text(
                f"🌐 Schritt 2b: Tailscale auf {DEVICE_NAME} einrichten\n\n"
                f"⚠️ Das Babyphone ist noch nicht mit Tailscale verbunden.\n\n"
                f"Tippe auf 'Anmeldelink generieren' — du bekommst dann einen Link zum Einloggen.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔑 Anmeldelink generieren", callback_data="setup_tailscale_auth")],
                    [InlineKeyboardButton("← Zurueck", callback_data="setup_tailscale"),
                     InlineKeyboardButton("🔄 Erneut pruefen", callback_data="setup_tailscale_link")]
                ])
            )

    elif data == "setup_tailscale_auth":
        await query.edit_message_text("🔄 Verbindung wird vorbereitet...")

        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "tailscale", "up",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )

            auth_url = None
            try:
                async with asyncio.timeout(10):
                    async for line in proc.stdout:
                        text_line = line.decode().strip()
                        for word in text_line.split():
                            if word.startswith("https://login.tailscale.com"):
                                auth_url = word
                                break
                        if auth_url:
                            break
            except asyncio.TimeoutError:
                pass

            if auth_url:
                await query.edit_message_text(
                    f"🔑 Tailscale-Anmeldung\n\n"
                    f"Oeffne diesen Link in deinem Browser und melde dich an:\n\n"
                    f"{auth_url}\n\n"
                    f"Nach der Anmeldung verbindet sich {DEVICE_NAME} automatisch.\n"
                    f"Du bekommst hier eine Bestaetigung.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Verbindung pruefen", callback_data="setup_tailscale_link")]
                    ])
                )

                # Notify in background when connected
                chat_id = query.message.chat_id
                async def notify_setup_connected():
                    for _ in range(60):
                        await asyncio.sleep(5)
                        ok, ip = run_command("tailscale ip -4 2>/dev/null")
                        if ok and ip.strip():
                            await query.get_bot().send_message(
                                chat_id,
                                f"✅ {DEVICE_NAME} ist jetzt mit Tailscale verbunden!\n\n"
                                f"IP: {ip.strip()}\n\n"
                                f"Tippe auf 'Weiter' im Setup-Wizard um fortzufahren.",
                            )
                            return
                asyncio.create_task(notify_setup_connected())

            else:
                # Check if already connected
                ok, ts_ip = run_command("tailscale ip -4 2>/dev/null")
                if ok and ts_ip.strip():
                    await query.edit_message_text(
                        f"✅ {DEVICE_NAME} ist bereits mit Tailscale verbunden!\n\nIP: {ts_ip.strip()}",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Weiter →", callback_data="setup_snapcast")]
                        ])
                    )
                else:
                    await query.edit_message_text(
                        "❌ Konnte keinen Anmeldelink generieren.\n\n"
                        "Stelle sicher dass der Pi eine Internetverbindung hat.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("← Zurueck", callback_data="setup_tailscale_link")]
                        ])
                    )

        except Exception as e:
            await query.edit_message_text(
                f"❌ Fehler: {str(e)[:200]}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← Zurueck", callback_data="setup_tailscale_link")]
                ])
            )

    elif data == "setup_snapcast":
        ok, ts_ip = run_command("tailscale ip -4 2>/dev/null")
        ts_ip = ts_ip.strip() if ok and ts_ip.strip() else None

        if not ts_ip:
            await query.edit_message_text(
                "⚠️ Schritt 3: Snapcast verbinden\n\n"
                "Tailscale ist noch nicht verbunden — die IP des Babyphones fehlt.\n\n"
                "Bitte zuerst Tailscale einrichten (Schritt 2).",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← Zurueck zu Tailscale", callback_data="setup_tailscale_link")]
                ])
            )
        else:
            await query.edit_message_text(
                "🎵 Schritt 3: Snapcast verbinden\n\n"
                "1. Oeffne die Snapcast App\n"
                f"2. Fuege Server hinzu: `{ts_ip}`\n"
                "3. Port: 1704 (Standard)\n"
                "4. Verbinden - du solltest jetzt Audio hoeren!\n\n"
                "💡 Tipp: Die App funktioniert auch im Hintergrund bei gesperrtem Bildschirm.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔔 Test-Piep senden", callback_data="setup_test_beep")],
                    [InlineKeyboardButton("📦 Snapcast APK senden (Android)", callback_data="setup_send_apk")],
                    [InlineKeyboardButton("← Zurueck", callback_data="setup_tailscale_link"),
                     InlineKeyboardButton("Weiter →", callback_data="setup_ntfy")]
                ])
            )

    elif data == "setup_send_apk":
        await query.answer("📦 APK wird gesucht...", show_alert=False)
        chat_id = query.message.chat_id

        version, apk_url = fetch_snapcast_apk_info()
        if not apk_url:
            await query.get_bot().send_message(chat_id, "❌ Snapcast APK nicht gefunden. Bitte manuell von F-Droid laden.")
            return

        await query.get_bot().send_message(chat_id, f"📦 Lade Snapcast {version} herunter...")

        try:
            with tempfile.NamedTemporaryFile(suffix=".apk", delete=False) as tmp:
                tmp_path = tmp.name
                req = urllib.request.Request(apk_url, headers={"User-Agent": "bebefon-bot"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    tmp.write(resp.read())

            with open(tmp_path, "rb") as f:
                await query.get_bot().send_document(
                    chat_id,
                    document=f,
                    filename=f"snapcast_{version}.apk",
                    caption=f"📦 Snapcast {version} fuer Android\n\nAPK oeffnen und installieren. Falls 'Unbekannte Quellen' gefragt wird: einmal erlauben."
                )
            os.unlink(tmp_path)
        except Exception as e:
            await query.get_bot().send_message(chat_id, f"❌ Fehler beim Herunterladen: {str(e)[:200]}")

    elif data == "setup_test_beep":
        run_command("sudo -u _snapserver /opt/babymonitor/scripts/heartbeat-beep.sh")
        await query.answer("🔔 Piep gesendet! Hast du ihn gehoert?", show_alert=True)

    elif data == "setup_ntfy":
        config = load_config()
        topic = config.get("NTFY_TOPIC", "babymonitor-alerts")

        await query.edit_message_text(
            "🔔 Schritt 4: Benachrichtigungen einrichten\n\n"
            "1. Oeffne die Ntfy App\n"
            f"2. Abonniere das Topic: `{topic}`\n"
            "3. Aktiviere Benachrichtigungen (hohe Prioritaet!)\n\n"
            "Du bekommst Alarme wenn:\n"
            "• Handy-Verbindung zum Stream abbricht\n"
            "• Mikrofon getrennt wird\n"
            "• Babyphone offline geht",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📲 Test-Alarm senden", callback_data="setup_test_alert")],
                [InlineKeyboardButton("← Zurueck", callback_data="setup_snapcast"),
                 InlineKeyboardButton("Fertig →", callback_data="setup_complete")]
            ])
        )

    elif data == "setup_test_alert":
        config = load_config()
        topic = config.get("NTFY_TOPIC", "babymonitor-alerts")
        server = config.get("NTFY_SERVER", "https://ntfy.sh")

        run_command(
            f'curl -s -H "Title: Test Alarm" -H "Priority: high" '
            f'-H "Tags: baby,white_check_mark" -d "Setup-Test erfolgreich!" '
            f'"{server}/{topic}"'
        )
        await query.answer("📲 Test-Alarm gesendet! Pruefe deine Ntfy App.", show_alert=True)

    elif data == "setup_complete":
        bot_config["setup_complete"] = True
        save_bot_config(bot_config)

        device_name = DEVICE_NAME

        await query.edit_message_text(
            f"✅ {device_name} Setup abgeschlossen!\n\n"
            "Dein Babyphone ist einsatzbereit.\n\n"
            "Schnellbefehle:\n"
            "/status - Pruefen ob alles funktioniert\n"
            "/pause - Alarme pausieren (Wartung)\n"
            "/resume - Alarme fortsetzen\n"
            "/beep - Audio-Verbindung testen\n"
            "/help - Alle Befehle anzeigen\n\n"
            "💡 Alle 5 Minuten ertönt ein sanfter Piep, damit du weisst, dass alles funktioniert.\n\n"
            f"Viel Freude mit {device_name}! 👶"
        )


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger setup wizard"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    await update.message.reply_text(
        "🔧 Setup-Assistent\n\nLass uns dein Babyphone einrichten:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Setup starten", callback_data="setup_start")]
        ])
    )


# ============== Main ==============

async def post_init(application):
    """Set up bot commands menu and send startup message"""
    # Set commands menu
    commands = [
        ("start", "Bot starten / Setup"),
        ("status", "Systemstatus anzeigen"),
        ("pause", "Alarme pausieren"),
        ("resume", "Alarme fortsetzen"),
        ("beep", "Test-Piep senden"),
        ("temp", "CPU Temperatur"),
        ("uptime", "Laufzeit anzeigen"),
        ("config", "Konfiguration anzeigen"),
        ("restart", "Dienste neu starten"),
        ("reboot", "Pi neu starten"),
        ("wifi", "WiFi Status / Netzwerk wechseln / ein-aus"),
        ("tailscale", "Tailscale verbinden / Account wechseln / trennen"),
        ("update", "Updates laden"),
        ("logs", "Logs anzeigen"),
        ("setup", "Setup-Assistent"),
        ("reset", "Setup zuruecksetzen"),
        ("setcode", "Einladungscode setzen"),
        ("join", "Mit Einladungscode beitreten"),
        ("help", "Alle Befehle"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands menu set")

    # Send startup message to authorized users
    bot_config = load_bot_config()
    authorized_users = bot_config.get("authorized_users", [])

    if not authorized_users:
        logger.info("No authorized users yet - waiting for first /start")
        return

    device_name = DEVICE_NAME

    if bot_config.get("setup_complete"):
        # Already set up - send status check
        # Wait a bit for services to fully start
        import asyncio
        await asyncio.sleep(10)

        config = load_config()

        # Check services (active or activating counts as OK)
        services_ok = all(
            get_service_status(s) in ["active", "activating"]
            for s in ["snapserver", "babymonitor-audio", "babymonitor-monitor"]
        )

        # Check mic
        ok, mic_output = run_command("arecord -l 2>/dev/null | grep -c USB")
        mic_ok = ok and mic_output.strip() != "0"

        # Check Tailscale
        ok, ts_ip = run_command("tailscale ip -4 2>/dev/null")
        ts_ok = ok and ts_ip.strip()

        if services_ok and mic_ok and ts_ok:
            message = (
                f"✅ *{device_name} ist online!*\n\n"
                f"Alle Systeme laufen einwandfrei.\n\n"
                f"🎤 Mikrofon: OK\n"
                f"🌐 Tailscale: `{ts_ip.strip()}`\n"
                f"🔔 Benachrichtigungen: Aktiv\n\n"
                f"Tippe /status fuer Details."
            )
        else:
            issues = []
            if not services_ok:
                issues.append("⚠️ Einige Dienste laufen nicht")
            if not mic_ok:
                issues.append("⚠️ Mikrofon nicht erkannt")
            if not ts_ok:
                issues.append("⚠️ Tailscale nicht verbunden")

            message = (
                f"⚠️ *{device_name} ist online, aber es gibt Probleme:*\n\n"
                + "\n".join(issues) + "\n\n"
                f"Tippe /status fuer Details."
            )
    else:
        # Not set up yet - send welcome message
        message = (
            f"🎄 *Frohe Weihnachten!* 🎁\n\n"
            f"Dein *{device_name}* ist jetzt online und bereit zur Einrichtung!\n\n"
            f"*So geht's:*\n"
            f"1️⃣ Tippe auf /setup\n"
            f"2️⃣ Folge dem Assistenten\n"
            f"3️⃣ In 5 Minuten ist alles fertig!\n\n"
            f"Bei Fragen wende dich an {GIFT_GIVER} 😊"
        )

    # Send to all authorized users
    for user_id in authorized_users:
        try:
            await application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"Startup message sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send startup message to {user_id}: {e}")


## ============== WiFi ==============

async def wifi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """WiFi Hauptmenü"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return ConversationHandler.END
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("📊 Status", callback_data="wifi_status")],
        [InlineKeyboardButton("🔍 Netzwerke scannen", callback_data="wifi_scan")],
        [InlineKeyboardButton("📴 WiFi ein/aus", callback_data="wifi_toggle")],
    ]
    await update.message.reply_text("📡 WiFi Steuerung:", reply_markup=InlineKeyboardMarkup(keyboard))
    return WIFI_MENU


async def wifi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """WiFi Callback Handler"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "wifi_status":
        ok, out = run_command("nmcli -t -f DEVICE,STATE,CONNECTION device status | grep '^wlan0:'")
        ok2, ip = run_command("ip addr show wlan0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1")
        ok3, signal = run_command("nmcli -t -f IN-USE,SSID,SIGNAL device wifi list | grep '^\\*'")

        if ok and "connected" in out:
            parts = out.strip().split(":")
            ssid = parts[2] if len(parts) > 2 else "unbekannt"
            sig = signal.strip().split(":")[-1] if ok3 else "?"
            ip_addr = ip.strip() if ok2 else "?"
            text = f"📡 WiFi verbunden\n\nNetzwerk: {ssid}\nSignal: {sig}%\nIP: {ip_addr}"
        else:
            ok4, radio = run_command("nmcli radio wifi")
            text = f"📴 WiFi {'deaktiviert' if ok4 and 'disabled' in radio else 'getrennt'}"

        keyboard = [[InlineKeyboardButton("🔙 Zurück", callback_data="wifi_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return WIFI_MENU

    if data == "wifi_toggle":
        ok, radio = run_command("nmcli radio wifi")
        enabled = ok and "enabled" in radio
        keyboard = [
            [InlineKeyboardButton("✅ Ja", callback_data="wifi_toggle_confirm")],
            [InlineKeyboardButton("🔙 Zurück", callback_data="wifi_back")],
        ]
        action = "deaktivieren" if enabled else "aktivieren"
        await query.edit_message_text(
            f"WiFi {'aktiviert' if enabled else 'deaktiviert'}.\nWiFi wirklich {action}?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WIFI_MENU

    if data == "wifi_toggle_confirm":
        ok, radio = run_command("nmcli radio wifi")
        if ok and "enabled" in radio:
            ok2, out = run_command("sudo nmcli radio wifi off")
            if ok2:
                await query.edit_message_text("📴 WiFi deaktiviert.")
            else:
                await query.edit_message_text(f"❌ Fehler: {out[:200]}")
        else:
            ok2, out = run_command("sudo nmcli radio wifi on")
            if ok2:
                await query.edit_message_text("📶 WiFi aktiviert.")
            else:
                await query.edit_message_text(f"❌ Fehler: {out[:200]}")
        return ConversationHandler.END

    if data == "wifi_scan":
        await query.edit_message_text("🔍 Suche Netzwerke...")
        ok, out = run_command("nmcli -t -f SSID,SECURITY device wifi list")
        if not ok or not out.strip():
            await query.edit_message_text("❌ Keine Netzwerke gefunden.")
            return ConversationHandler.END
        seen = set()
        keyboard = []
        for line in out.strip().splitlines():
            parts = line.split(":")
            ssid = parts[0].strip()
            secured = len(parts) > 1 and parts[1].strip() not in ("", "--")
            if ssid and ssid not in seen:
                seen.add(ssid)
                icon = "🔒" if secured else "🔓"
                keyboard.append([InlineKeyboardButton(f"{icon} {ssid}", callback_data=f"wifi_connect_{ssid}")])
        keyboard.append([InlineKeyboardButton("🔙 Zurück", callback_data="wifi_back")])
        await query.edit_message_text("📶 Verfügbare Netzwerke:", reply_markup=InlineKeyboardMarkup(keyboard))
        return WIFI_MENU

    if data.startswith("wifi_connect_"):
        ssid = data.replace("wifi_connect_", "")
        context.user_data["wifi_ssid"] = ssid
        # Check if already saved
        ok, saved = run_command(f"nmcli -t -f NAME connection show | grep -Fx '{ssid}'")
        if ok and saved.strip():
            await query.edit_message_text(f"🔄 Verbinde mit {ssid}...")
            ok2, out = run_command(f"sudo nmcli device wifi connect '{ssid}'", timeout=20)
            if ok2 or "successfully" in out.lower():
                ok3, ip = run_command("ip addr show wlan0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1")
                await query.edit_message_text(f"✅ Verbunden mit {ssid}\nIP: {ip.strip() if ok3 else '?'}")
            else:
                await query.edit_message_text(f"❌ Verbindung fehlgeschlagen:\n{out[:200]}")
            return ConversationHandler.END
        else:
            await query.edit_message_text(
                f"🔑 Passwort für *{ssid}*:\n\nBitte eingeben oder /cancel zum Abbrechen.",
                parse_mode="Markdown"
            )
            return WIFI_PASSWORD

    if data == "wifi_back":
        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="wifi_status")],
            [InlineKeyboardButton("🔍 Netzwerke scannen", callback_data="wifi_scan")],
            [InlineKeyboardButton("📴 WiFi ein/aus", callback_data="wifi_toggle")],
        ]
        await query.edit_message_text("📡 WiFi Steuerung:", reply_markup=InlineKeyboardMarkup(keyboard))
        return WIFI_MENU


async def wifi_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passwort entgegennehmen und verbinden"""
    ssid = context.user_data.get("wifi_ssid")
    password = update.message.text
    if not ssid:
        await update.message.reply_text("❌ Fehler: kein Netzwerk gewählt.")
        return ConversationHandler.END
    await update.message.reply_text(f"🔄 Verbinde mit {ssid}...")
    ok, out = run_command(f"sudo nmcli device wifi connect '{ssid}' password '{password}'", timeout=20)
    if ok or "successfully" in out.lower():
        ok2, ip = run_command("ip addr show wlan0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1")
        await update.message.reply_text(f"✅ Verbunden mit {ssid}\nIP: {ip.strip() if ok2 else '?'}")
    else:
        await update.message.reply_text(f"❌ Verbindung fehlgeschlagen. Passwort falsch?\n{out[:200]}")
    return ConversationHandler.END


async def wifi_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ WiFi abgebrochen.")
    return ConversationHandler.END


wifi_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("wifi", wifi_cmd)],
    states={
        WIFI_MENU: [CallbackQueryHandler(wifi_callback, pattern="^wifi_")],
        WIFI_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, wifi_password)],
    },
    fallbacks=[CommandHandler("cancel", wifi_cancel)],
    conversation_timeout=300,
    per_user=True,
    per_chat=True,
)


def main():
    """Start the bot"""
    # Load bot token from config.env or environment
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or CONFIG.get("TELEGRAM_BOT_TOKEN")

    if not token:
        print("Error: No bot token found!")
        print("Add TELEGRAM_BOT_TOKEN to config.env")
        sys.exit(1)

    # Create application
    app = Application.builder().token(token).post_init(post_init).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(wifi_conv_handler)
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("setcode", set_invite_code))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("beep", beep))
    app.add_handler(CommandHandler("config", show_config))
    app.add_handler(CommandHandler("update", git_update))
    app.add_handler(CommandHandler("restart", restart_services))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("setname", set_name))
    app.add_handler(CommandHandler("setup", setup_command))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("reboot", reboot_pi))
    app.add_handler(CommandHandler("tailscale", tailscale_cmd))
    app.add_handler(CommandHandler("temp", temperature))
    app.add_handler(CommandHandler("uptime", uptime_cmd))
    app.add_handler(CallbackQueryHandler(setup_callback, pattern="^setup_"))

    # Voice/audio message handlers (for future: play in baby's room)
    # app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    # app.add_handler(MessageHandler(filters.AUDIO, handle_audio))

    # Start polling
    logger.info(f"Starting bot: {DEVICE_NAME}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
