#!/bin/bash
# restart.sh — PROJECT AEGIS V4.0 Hot-Reload
# SAFE: Kills ONLY the bot process by PID file. Never uses global pkill/killall.

BOT_PID_FILE="/data/data/com.termux/files/home/farm/bot.pid"
BOT_DIR="/data/data/com.termux/files/home/farm"
DEVICE_ID="${1:-DEV_2}"

echo "[AEGIS V4.0] Hot-Reload initiated for: $DEVICE_ID"

# ── SAFE KILL: Only kill the specific bot PID ─────────────────────────────
if [ -f "$BOT_PID_FILE" ]; then
    OLD_PID=$(cat "$BOT_PID_FILE")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[AEGIS V4.0] Stopping bot (PID: $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null
        sleep 3
        kill -9 "$OLD_PID" 2>/dev/null
        echo "[AEGIS V4.0] Bot stopped."
    else
        echo "[AEGIS V4.0] No active bot found at PID $OLD_PID."
    fi
    rm -f "$BOT_PID_FILE"
else
    echo "[AEGIS V4.0] No PID file found. Bot may not be running."
fi

sleep 2

# ── RESTART ───────────────────────────────────────────────────────────────
cd "$BOT_DIR" || exit 1
echo "[AEGIS V4.0] Starting bot for device: $DEVICE_ID"
python main.py "$DEVICE_ID" >> boot_log.txt 2>&1 &
BOT_PID=$!

echo "$BOT_PID" > "$BOT_PID_FILE"
echo "[AEGIS V4.0] ✅ Bot restarted. PID=$BOT_PID"
