#!/system/bin/sh
# aegis_anchor.sh — Project Aegis V9.0 System Immortal
# Persistent Ghost Daemon — Auto-restarts bot if killed
# This script runs as root via nohup

BOT_DIR="/data/data/com.termux/files/home/FarmOS"
DEVICE_ID="$1"
CHECK_INTERVAL=10

echo "🔱 V9.0 AEGIS ANCHOR: Ghost Daemon started"
echo "🔱 Monitoring: $BOT_DIR/main.py"
echo "🔱 Device ID: $DEVICE_ID"

while true; do
    # Check if main.py is running
    PID=$(pgrep -f "python.*main.py.*$DEVICE_ID" 2>/dev/null)
    
    if [ -z "$PID" ]; then
        echo "⚠️ V9.0 ANCHOR: Bot not found! Restarting..."
        
        # Kill any leftover python processes for this device
        pkill -f "python.*main.py.*$DEVICE_ID" 2>/dev/null
        sleep 2
        
        # Restart the bot
        cd "$BOT_DIR" 2>/dev/null || cd /data/data/com.termux/files/home/FarmOS
        nohup su -c "python main.py $DEVICE_ID" > /dev/null 2>&1 &
        
        echo "✅ V9.0 ANCHOR: Bot restarted"
        
        # Wait for bot to initialize
        sleep 15
        
        # Apply OOM protection to new bot process
        NEW_PID=$(pgrep -f "python.*main.py.*$DEVICE_ID" 2>/dev/null)
        if [ -n "$NEW_PID" ]; then
            echo "🔱 V9.0 ANCHOR: Protecting new bot PID $NEW_PID"
            echo -1000 > /proc/$NEW_PID/oom_score_adj 2>/dev/null
            
            # Protect children
            for CHILD in $(pgrep -P $NEW_PID 2>/dev/null); do
                echo -1000 > /proc/$CHILD/oom_score_adj 2>/dev/null
            done
        fi
    fi
    
    # Periodic OOM re-protection (in case new children spawned)
    if [ -n "$PID" ]; then
        CURRENT_SCORE=$(cat /proc/$PID/oom_score_adj 2>/dev/null)
        if [ "$CURRENT_SCORE" != "-1000" ]; then
            echo -1000 > /proc/$PID/oom_score_adj 2>/dev/null
        fi
    fi
    
    sleep $CHECK_INTERVAL
done
