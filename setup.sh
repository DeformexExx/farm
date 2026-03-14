#!/bin/bash
# AEGIS v6 - FULL INSTALLATION & AUTO-BOOT SETUP
# Это основной скрипт для первой установки Aegis на новое устройство.
# Использование: ./setup.sh DEV_X

if [ -z "$1" ]; then
    echo "❌ Ошибка: Укажите ID устройства (например: DEV_1, DEV_2)"
    echo "Пример: ./setup.sh DEV_1"
    exit 1
fi

DEVICE_ID=$1
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/aegis_start.sh"

echo "------------------------------------------------"
echo "🚀 Начинаем установку Aegis OS v6 [$DEVICE_ID]"
echo "------------------------------------------------"

# 1. Обновление пакетов и установка системных зависимостей
echo "📦 [1/4] Установка системных пакетов..."
pkg update && pkg upgrade -y
pkg install python git tsu sqlite ntpdate -y

# 2. Установка Python зависимостей
echo "🐍 [2/4] Установка Python библиотек..."
pip install requests python-telegram-bot psutil gspread google-auth oauth2client

# 3. Настройка Termux:Boot (Автозапуск при включении)
echo "🔌 [3/4] Настройка автозапуска (Termux:Boot)..."
mkdir -p "$BOOT_DIR"

cat <<EOF > "$BOOT_SCRIPT"
#!/bin/bash
# Aegis Autonomous Boot Script v7
# Wake lock (не дает системе усыпить Termux)
termux-wake-lock

# Синхронизация времени (критично для Google Sheets JWT)
echo "[AEGIS] Синхронизация времени..."
ntpdate -u pool.ntp.org || true

cd ~/farm
echo "[AEGIS] Синхронизация с GitHub..."
git pull

echo "[AEGIS] Запуск Aegis OS v6 как $DEVICE_ID..."
tsu -c "python main.py $DEVICE_ID"
EOF

chmod +x "$BOOT_SCRIPT"

# 4. Проверка репозитория и финальные шаги
echo "✅ [4/4] Финализация..."
if [ ! -d "$HOME/farm" ]; then
    echo "⚠️ Внимание: Папка ~/farm не найдена. Клонируем репо..."
    git clone https://github.com/DeformexExx/farm.git ~/farm
fi

echo "------------------------------------------------"
echo "✨ УСТАНОВКА ЗАВЕРШЕНА!"
echo "🤖 Device ID: $DEVICE_ID"
echo "------------------------------------------------"
echo "ПОСЛЕДНИЕ ШАГИ:"
echo "1. Убедитесь, что приложение 'Termux:Boot' установлено."
echo "2. Положите файл 'creds.json' в папку ~/farm/"
echo "3. Перезагрузите телефон."
echo "------------------------------------------------"
