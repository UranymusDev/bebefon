https://github.com/snapcast/snapdroid/releases/download/v0.29.0.2/Snapcast_v0.29.0.2.apk

. New Telegram bot from @BotFather (e.g., @josepha_bebefon_bot)
  2. New Ntfy topic (e.g., bebefon-josepha-xxxxx)
  3. New Healthchecks.io checks
  4. Her own Tailscale account (or invite her to yours)

  Quick setup on new Pi:
  # Clone repo
  cd /opt && sudo git clone https://github.com/UranymusDev/bebefon babymonitor
  sudo chown -R bebefon:bebefon /opt/babymonitor

  # Copy and edit config
  cp config/config.env.example config/config.env
  nano config/config.env  # Fill in Josepha's values

  # Run install script
  ./scripts/install.sh