AEGIS FLEET CONTROL v5 - SETUP GUIDE (Termux/Android)
=====================================================

Aegis v5 is a multi-device Roblox farm orchestrator designed for Cloud phones (ugPhone).
This guide helps you set up a new device in your fleet.

1. PREREQUISITES (Clean Termux)
-------------------------------
Open Termux and run these commands to install required tools:

pkg update && pkg upgrade -y
pkg install python git tsu -y
pkg install libandroid-spawn-static -y (optional for some features)

2. CLONE & INSTALL DEPENDENCIES
--------------------------------
git clone https://github.com/DeformexExx/farm.git
cd farm
pip install requests python-telegram-bot psutil

3. DEVICE CONFIGURATION
-----------------------
Every device MUST have a unique DEVICE_ID in its local 'config.json'.

Edit config.json:
{
  "DEVICE_ID": "DEV_1",  <-- Change this for each phone (e.g., DEV_2, DEV_3)
  "bot_token": "YOUR_BOT_TOKEN",
  "admin_ids": [6961471062],
  "clones": ["com.roblox.clienb", "..."],
  "global_auto_start": true
}

4. GRANTING ROOT ACCESS
-----------------------
Aegis requires root to control the screen and processes. 
Run the bot once and grant 'su' permission when prompted:

tsu
python main.py

5. AUTO-BOOT SETUP (Recommended)
--------------------------------
To make Aegis start automatically when Termux opens, add this to your ~/.bashrc:

cd ~/farm && tsu -c "python main.py"

6. MULTI-DEVICE OPERATION
-------------------------
- Start all bots with the SAME bot_token.
- Use '/start' in Telegram.
- Select your device from the inline menu [📱 DEV X] to control it specifically.
- Use '⚡ GLOBAL ACTIONS' to control the entire fleet at once.

TECHNICAL SUPPORT
-----------------
Logs are located at: ~/farm/aegis.log
Watchdog mode: Multi-Layer (L1 Thread + L2 Process)
Optimization: 10s stagger, renice -20, trim-caches.

=====================================================
Aegis FarmOS - Ultimate Reliability & Scale.
