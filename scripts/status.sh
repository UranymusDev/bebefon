#!/bin/bash
# BabyMonitor Status Check Script

echo "========================================="
echo "  BabyMonitor Status"
echo "========================================="
echo ""

# Service status
echo "Services:"
echo -n "  snapserver:        "
systemctl is-active snapserver 2>/dev/null || echo "not installed"

echo -n "  babymonitor-audio: "
systemctl is-active babymonitor-audio 2>/dev/null || echo "not installed"

echo ""

# Stream status
echo "Stream:"
STREAM_INFO=$(echo '{"id":1,"jsonrpc":"2.0","method":"Server.GetStatus"}' | nc -w 2 localhost 1705 2>/dev/null)
if [ -n "$STREAM_INFO" ]; then
    echo "$STREAM_INFO" | python3 -c '
import sys,json
d=json.load(sys.stdin)
for s in d["result"]["server"]["streams"]:
    print(f"  {s[\"id\"]}: {s[\"status\"]}")
' 2>/dev/null || echo "  Unable to parse stream info"
else
    echo "  Unable to connect to snapserver"
fi

echo ""

# Connected clients
echo "Clients:"
if [ -n "$STREAM_INFO" ]; then
    echo "$STREAM_INFO" | python3 -c '
import sys,json
d=json.load(sys.stdin)
clients = [(c["host"]["name"], c["connected"], c["config"]["volume"]["percent"])
           for g in d["result"]["server"]["groups"]
           for c in g["clients"]]
if clients:
    for name, connected, vol in clients:
        status = "connected" if connected else "disconnected"
        print(f"  {name}: {status} (volume: {vol}%)")
else:
    print("  No clients registered")
' 2>/dev/null || echo "  Unable to parse client info"
fi

echo ""

# System info
echo "System:"
echo "  Uptime:      $(uptime -p)"
echo "  Temperature: $(vcgencmd measure_temp 2>/dev/null | sed 's/temp=//' || echo 'N/A')"
echo "  Memory:      $(free -h | awk '/Mem:/ {print $3 "/" $2}')"
echo "  CPU:         $(top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1)%"

echo ""

# Audio device
echo "Audio Device:"
if arecord -l 2>/dev/null | grep -q "USB"; then
    arecord -l 2>/dev/null | grep "USB" | sed 's/^/  /'
else
    echo "  No USB audio device detected!"
fi

echo ""
echo "========================================="
