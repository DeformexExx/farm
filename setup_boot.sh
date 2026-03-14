#!/bin/bash
# AEGIS v5.2 - Automated Boot Setup Utility
# Usage: ./setup_boot.sh [DEVICE_ID]

if [ -z "$1" ]; then
    echo "Error: Please provide a Device ID (e.g., DEV_1, DEV_2)"
    echo "Usage: ./setup_boot.sh DEV_X"
    exit 1
fi

DEVICE_ID=$1
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/aegis_start.sh"

echo "[AEGIS] Initializing Termux:Boot setup for $DEVICE_ID..."

# 1. Create boot directory if missing
mkdir -p "$BOOT_DIR"

# 2. Create the boot script
cat <<EOF > "$BOOT_SCRIPT"
#!/bin/bash
# Aegis Autonomous Boot Script
# Generated for: $DEVICE_ID

# Wake lock to prevent Android from killing Termux
termux-wake-lock

cd ~/farm
echo "[AEGIS] Syncing with GitHub..."
git pull

# Launch with root privileges and the specified ID
echo "[AEGIS] Starting Aegis OS v5.2 as $DEVICE_ID..."
tsu -c "python main.py $DEVICE_ID"
EOF

# 3. Set permissions
chmod +x "$BOOT_SCRIPT"

echo "------------------------------------------------"
echo "✅ SUCCESS: Boot script created at $BOOT_SCRIPT"
echo "🤖 Device ID set to: $DEVICE_ID"
echo "------------------------------------------------"
echo "IMPORTANT: Make sure you have the 'Termux:Boot' app installed from F-Droid."
echo "Then, restart your phone to test the autonomous launch!"
