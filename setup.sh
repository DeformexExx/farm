#!/bin/bash
# AEGIS OVERLORD v15 - ULTIMATE FLEET CONTROL INSTALLER
# ./setup.sh DEV_2

if [ -z "$1" ]; then
    echo "❌ Ошибка: Укажите ID устройства (например: DEV_2)"
    exit 1
fi

DEVICE_ID=$1
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/aegis_start.sh"

echo "------------------------------------------------"
echo "🚀 Установка Aegis Overlord v15: Ultimate Fleet Control [$DEVICE_ID]"
echo "------------------------------------------------"

# 1. Системные пакеты (TSU + SQLITE)
echo "📦 [1/4] Установка системных пакетов (tsu, sqlite, git)..."
pkg update && pkg upgrade -y
pkg install python git tsu sqlite ntpdate -y

# 2. Python зависимости
echo "🐍 [2/4] Установка Python библиотек..."
pip install requests python-telegram-bot psutil

# 3. Настройка автозапуска
echo "🔌 [3/4] Настройка автозапуска (Termux:Boot)..."
mkdir -p "$BOOT_DIR"

cat <<EOF > "$BOOT_SCRIPT"
#!/bin/bash
# Aegis Overlord Boot v15
termux-wake-lock
ntpdate -u pool.ntp.org || true

cd ~/farm
git reset --hard origin/main
git pull

tsu -c "python main.py $DEVICE_ID"
EOF

chmod +x "$BOOT_SCRIPT"

# 4. Финализация
echo "✅ [4/4] Финализация (Farm directory)..."
if [ ! -d "$HOME/farm" ]; then
    git clone https://github.com/DeformexExx/farm.git ~/farm
fi

echo "------------------------------------------------"
echo "✨ УСТАНОВКА ЗАВЕРШЕНА!"
echo "🤖 Device ID: $DEVICE_ID"
echo "------------------------------------------------"
echo "ПОСЛЕДНИЕ ШАГИ:"
echo "1. Убедитесь, что файл '$DEVICE_ID.json' есть в ~/farm/"
echo "2. Убедитесь, что 'config.json' с токеном бота есть в ~/farm/"
echo "3. Введите: sh setup_boot.sh если нужно обновить Termux:Boot руками"
echo "------------------------------------------------"
