#!/bin/bash
# AEGIS V2.0 Hot-Reload Script
echo "🔄 Reloading PROJECT AEGIS..."
pkill -9 python
sleep 2
# Assume active device is passed or derived
DEVICE_ID=$1
if [ -z "$DEVICE_ID" ]; then
    DEVICE_ID="DEV_2"
fi
python main.py $DEVICE_ID &
echo "✅ AEGIS V2.0 Started in background."
