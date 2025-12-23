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
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
import tempfile

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
        "/update - Updates von Git laden\n"
        "/logs [service] - Logs anzeigen\n\n"
        "⚙️ *Einstellungen*\n"
        "/setup - Setup-Assistent\n"
        "/reset - Setup zuruecksetzen\n"
        "/setname <name> - Geraetename aendern",
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

    # Tailscale IP
    ok, tailscale_ip = run_command("tailscale ip -4 2>/dev/null")
    tailscale_ip = tailscale_ip.strip() if ok else "Nicht verbunden"

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
    status_text += f"🌐 Tailscale IP: {tailscale_ip}\n\n"

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

    await update.message.reply_text(text)


async def git_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update from git"""
    bot_config = load_bot_config()
    if not is_authorized(update, bot_config):
        return

    await update.message.reply_text("🔄 Suche nach Updates...")

    # Git pull
    ok, output = run_command(f"cd {REPO_DIR} && git pull", timeout=60)

    if ok:
        if "Already up to date" in output or "Bereits aktuell" in output:
            await update.message.reply_text("✅ Bereits auf dem neuesten Stand!")
        else:
            await update.message.reply_text(
                f"✅ Aktualisiert!\n\n```\n{output[:500]}\n```\n\n"
                "Mit /restart Dienste neu starten um Aenderungen anzuwenden.",
                parse_mode="Markdown"
            )
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

    await update.message.reply_text("Dienste neu gestartet:\n\n" + "\n".join(results))


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
            "   Android: https://f-droid.org/packages/de.badaix.snapcast/\n\n"
            "3️⃣ **Ntfy** (Push-Benachrichtigungen)\n"
            "   iOS: https://apps.apple.com/app/ntfy/id1625396347\n"
            "   Android: https://play.google.com/store/apps/details?id=io.heckel.ntfy\n\n"
            "Tippe auf 'Weiter' wenn alle Apps installiert sind.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
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
                f"Das Babyphone muss noch mit Tailscale verbunden werden.\n\n"
                f"Bitte wende dich an {GIFT_GIVER} fuer Hilfe bei diesem Schritt.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← Zurueck", callback_data="setup_tailscale"),
                     InlineKeyboardButton("Erneut pruefen", callback_data="setup_tailscale_link")]
                ])
            )

    elif data == "setup_snapcast":
        ok, ts_ip = run_command("tailscale ip -4 2>/dev/null")
        ts_ip = ts_ip.strip() if ok else "[TAILSCALE_IP]"

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
                [InlineKeyboardButton("← Zurueck", callback_data="setup_tailscale_link"),
                 InlineKeyboardButton("Weiter →", callback_data="setup_ntfy")]
            ])
        )

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
        ("update", "Updates laden"),
        ("logs", "Logs anzeigen"),
        ("setup", "Setup-Assistent"),
        ("reset", "Setup zuruecksetzen"),
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
