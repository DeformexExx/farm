#!/bin/bash
termux-wake-lock
sleep 25 # Wait for Su and Network to stabilize
pkill -9 -f python
cd /data/data/com.termux/files/home/farm
python main.py DEV_2 >> boot_log.txt 2>&1
