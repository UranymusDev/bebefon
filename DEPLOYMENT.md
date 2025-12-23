# BabyMonitor Deployment Guide

This guide covers how to deploy BabyMonitor to new Raspberry Pi devices.

---

## Option 1: Fresh Install via Script

### Prerequisites
- Raspberry Pi with Raspberry Pi OS (Debian 12/13, 64-bit recommended)
- USB Microphone connected
- Network connection (WiFi or Ethernet)
- SSH access enabled

### Installation Steps

1. **Flash Raspberry Pi OS** using Raspberry Pi Imager:
   - Choose: Raspberry Pi OS Lite (64-bit)
   - Configure hostname, user, WiFi, SSH in advanced settings

2. **SSH into the Pi**:
   ```bash
   ssh [user]@[hostname].local
   # or
   ssh [user]@[ip-address]
   ```

3. **Download and run install script**:
   ```bash
   # Option A: Clone from git (if you have a repo)
   git clone https://github.com/[your-repo]/babymonitor.git
   cd babymonitor
   chmod +x scripts/install.sh
   ./scripts/install.sh

   # Option B: Download script directly
   curl -O https://raw.githubusercontent.com/[your-repo]/babymonitor/main/scripts/install.sh
   chmod +x install.sh
   ./install.sh
   ```

4. **Install Snapdroid** on your phone and connect

---

## Option 2: Clone SD Card Image

This is the fastest method for deploying to multiple Pis.

### Creating the Image (from your working Pi)

**On Windows (using Win32DiskImager or Raspberry Pi Imager):**

1. Shut down the Pi: `sudo shutdown -h now`
2. Remove SD card and insert into Windows PC
3. Use **Win32DiskImager**:
   - Select the SD card as the device
   - Choose a filename for the image (e.g., `babymonitor-v1.img`)
   - Click "Read" to create the image
4. Optionally compress: `7z a babymonitor-v1.img.7z babymonitor-v1.img`

**On Linux/Mac:**
```bash
# Find the SD card device
lsblk

# Create image (replace sdX with your device)
sudo dd if=/dev/sdX of=babymonitor-v1.img bs=4M status=progress

# Compress
gzip babymonitor-v1.img
```

### Deploying the Image

1. Flash the image to a new SD card using Raspberry Pi Imager or Etcher
2. Before first boot, customize for the new Pi:

**Mount the boot partition and edit:**

```bash
# On Linux/Mac, mount the boot partition
# Edit /boot/cmdline.txt or use raspi-config after first boot
```

3. **After first boot**, change the hostname:
   ```bash
   sudo raspi-config
   # System Options > Hostname > Set new hostname
   sudo reboot
   ```

4. **Update SSH keys** (important for security):
   ```bash
   sudo rm /etc/ssh/ssh_host_*
   sudo dpkg-reconfigure openssh-server
   sudo systemctl restart ssh
   ```

### Post-Clone Checklist

- [ ] Change hostname (to distinguish from original)
- [ ] Regenerate SSH host keys
- [ ] Update WiFi credentials if different network
- [ ] Verify USB mic is detected (`arecord -l`)
- [ ] Check services are running (`./scripts/status.sh`)
- [ ] Test audio in Snapdroid app

---

## Option 3: Using PiShrink (Recommended for Images)

PiShrink reduces image size by shrinking the filesystem.

```bash
# Install PiShrink
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh

# Shrink the image
sudo ./pishrink.sh babymonitor-v1.img babymonitor-v1-shrunk.img

# Compress
gzip babymonitor-v1-shrunk.img
```

---

## Configuration Customization

### Different WiFi Network

Edit before first boot (on boot partition):
```
# /boot/wpa_supplicant.conf
country=DE
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="YourNetworkName"
    psk="YourPassword"
    key_mgmt=WPA-PSK
}
```

### Different USB Microphone

If the mic is detected on a different card number:

1. Check device: `arecord -l`
2. Update service:
   ```bash
   sudo nano /etc/systemd/system/babymonitor-audio.service
   # Change hw:2,0 to the correct device
   sudo systemctl daemon-reload
   sudo systemctl restart babymonitor-audio
   ```

### Static IP Address

Edit `/etc/dhcpcd.conf`:
```
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

---

## Updating Existing Installation

### Pull Latest Scripts

```bash
cd /opt/babymonitor
git pull origin main
```

### Update System Packages

```bash
sudo apt update && sudo apt upgrade -y
sudo systemctl restart snapserver babymonitor-audio
```

### Update Snapserver

```bash
sudo apt update
sudo apt install --only-upgrade snapserver
sudo systemctl restart snapserver
```

---

## Backup & Restore

### Backup Configuration

```bash
# On the Pi
tar -czvf babymonitor-backup.tar.gz \
    /etc/snapserver.conf \
    /etc/systemd/system/babymonitor-audio.service \
    /opt/babymonitor/
```

### Restore Configuration

```bash
# On new Pi (after base install)
tar -xzvf babymonitor-backup.tar.gz -C /
sudo systemctl daemon-reload
sudo systemctl restart snapserver babymonitor-audio
```

---

## Troubleshooting Deployment

### Services Don't Start After Clone

```bash
# Check logs
journalctl -u snapserver -n 50
journalctl -u babymonitor-audio -n 50

# Common fix: reload systemd
sudo systemctl daemon-reload
sudo systemctl restart snapserver babymonitor-audio
```

### USB Mic Not Detected

```bash
# Check USB devices
lsusb

# Check ALSA
arecord -l

# Might need different card number
# Update service file accordingly
```

### Network Issues

```bash
# Check IP
hostname -I

# Check WiFi
iwconfig wlan0

# Restart networking
sudo systemctl restart dhcpcd
```
