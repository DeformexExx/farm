#!/bin/bash
# AEGIS SYSTEM ANCHOR v7.0 - ULTIMATE FLEET CONTROL INSTALLER
# Использование: ./setup.sh DEV_2

if [ -z "$1" ]; then
    echo "❌ Ошибка: Укажите ID устройства (например: DEV_2)"
    exit 1
fi

DEVICE_ID=$1
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/aegis_start.sh"

echo "------------------------------------------------"
echo "⚓ Установка Aegis System Anchor v7.0 [$DEVICE_ID]"
echo "------------------------------------------------"

# 1. Системные пакеты (TSU + SQLITE)
echo "📦 [1/4] Установка системных пакетов (python, tsu, sqlite, git, termux-api)..."
pkg update && pkg upgrade -y
pkg install python git tsu sqlite ntpdate termux-tools -y

# 2. Python зависимости
echo "🐍 [2/4] Установка Python библиотек..."
pip install requests "python-telegram-bot>=20.0" psutil

# 3. Настройка автозапуска
echo "🔌 [3/4] Настройка автозапуска (Termux:Boot)..."
mkdir -p "$BOOT_DIR"

cat <<EOF > "$BOOT_SCRIPT"
#!/bin/bash
# Aegis V7.0 System Anchor Boot Script
cd ~/farm
git reset --hard origin/main
git pull

# Use python -u (unbuffered) for V7.0 System Anchor Mode
tsu -c "python -u main.py $DEVICE_ID"
EOF

chmod +x "$BOOT_SCRIPT"

# 4. Финализация
echo "✅ [4/4] Финализация (Farm directory)..."
if [ ! -d "$HOME/farm" ]; then
    echo "🔗 Введите URL вашего приватного Git репозитория (FarmOS):"
    read -rp "> " GIT_REPO
    git clone "$GIT_REPO" ~/farm
fi

echo "------------------------------------------------"
echo "✨ УСТАНОВКА ЗАВЕРШЕНА!"
echo "🤖 Device ID: $DEVICE_ID"
echo "------------------------------------------------"
echo "ПОСЛЕДНИЕ ШАГИ:"
echo "1. Убедитесь, что файл '$DEVICE_ID.json' есть в ~/farm/"
echo "2. Убедитесь, что 'config.json' с токеном бота есть в ~/farm/"
echo "3. Запустите приложение Termux:Boot один раз вручную, чтобы дать ему права автозапуска."
echo "------------------------------------------------"
