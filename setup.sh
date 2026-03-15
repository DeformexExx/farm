#!/bin/bash
# AEGIS v7.1 - JSON REVOLUTION INSTALLER
# Основной скрипт установки Aegis Overlord.
# ./setup.sh DEV_X

if [ -z "$1" ]; then
    echo "❌ Ошибка: Укажите ID устройства (например: DEV_2)"
    exit 1
fi

DEVICE_ID=$1
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/aegis_start.sh"

echo "------------------------------------------------"
echo "🚀 Установка Aegis Overlord v7.1 [$DEVICE_ID]"
echo "------------------------------------------------"

# 1. Системные пакеты
echo "📦 [1/4] Установка системных пакетов..."
pkg update && pkg upgrade -y
pkg install python git tsu sqlite ntpdate -y

# 2. Python зависимости (Google SDK REMOVED)
echo "🐍 [2/4] Установка Python библиотек..."
pip install requests python-telegram-bot psutil

# 3. Настройка автозапуска
echo "🔌 [3/4] Настройка автозапуска (Termux:Boot)..."
mkdir -p "$BOOT_DIR"

cat <<EOF > "$BOOT_SCRIPT"
#!/bin/bash
# Aegis Overlord Boot v7.1
termux-wake-lock
ntpdate -u pool.ntp.org || true

cd ~/farm
git pull
tsu -c "python main.py $DEVICE_ID"
EOF

chmod +x "$BOOT_SCRIPT"

# 4. Финализация
echo "✅ [4/4] Финализация..."
if [ ! -d "$HOME/farm" ]; then
    git clone https://github.com/DeformexExx/farm.git ~/farm
fi

echo "------------------------------------------------"
echo "✨ УСТАНОВКА ЗАВЕРШЕНА!"
echo "🤖 Device ID: $DEVICE_ID (JSON Source)"
echo "------------------------------------------------"
echo "ПОСЛЕДНИЕ ШАГИ:"
echo "1. Убедитесь, что файл '$DEVICE_ID.json' есть в папке ~/farm/"
echo "2. Перезагрузите телефон."
echo "------------------------------------------------"
