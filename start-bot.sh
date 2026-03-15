#!/bin/bash
# start-bot.sh — PROJECT AEGIS V4.0
# SAFE: Uses PID file to kill ONLY the previous bot instance, never a global pkill.

BOT_PID_FILE="/data/data/com.termux/files/home/farm/bot.pid"
BOT_DIR="/data/data/com.termux/files/home/farm"
DEVICE_ID="${1:-DEV_2}"

termux-wake-lock

echo "[AEGIS V4.0] Waiting 25s for Su and network to stabilize..."
sleep 25

# ── SAFE KILL: Only kill previous bot instance by saved PID ──────────────
if [ -f "$BOT_PID_FILE" ]; then
    OLD_PID=$(cat "$BOT_PID_FILE")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[AEGIS V4.0] Stopping previous bot instance (PID: $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null
        sleep 3
        # Force if still alive
        kill -9 "$OLD_PID" 2>/dev/null
    fi
    rm -f "$BOT_PID_FILE"
fi

# ── START BOT ─────────────────────────────────────────────────────────────
cd "$BOT_DIR" || exit 1
echo "[AEGIS V4.0] Starting bot for device: $DEVICE_ID"
python main.py "$DEVICE_ID" >> boot_log.txt 2>&1 &
BOT_PID=$!

# Save PID for future safe kills
echo "$BOT_PID" > "$BOT_PID_FILE"
echo "[AEGIS V4.0] Bot started. PID=$BOT_PID saved to $BOT_PID_FILE"
