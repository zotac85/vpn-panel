#!/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "Ошибка: запустите скрипт от root (sudo -i)"
  exit 1
fi

PANEL_DIR="/usr/local/share/vpn-panel"
REPO_URL="https://raw.githubusercontent.com/zotac85/vpn-panel/main"

echo -e "\033[0;36m==============================================\033[0m"
echo -e "        \033[1;33m⚡ VPN PANEL INSTALLER / UPDATER ⚡\033[0m"
echo -e "\033[0;36m==============================================\033[0m"

# Проверяем, установлена ли панель ранее
if [ -d "$PANEL_DIR" ] || [ -f "/usr/local/bin/vpn" ]; then
    echo -e "\033[1;33mОбнаружена ранее установленная панель.\033[0m"
    echo ""
    echo " 1) 🔄 Обновить скрипты и модули (базы и настройки сохранятся)"
    echo " 2) ⚙️ Переустановить полностью (сброс конфигурации)"
    echo " 0) 🚪 Отмена"
    echo ""
    read -p "Выберите действие [0-2]: " choice

    case $choice in
        1)
            echo -e "\n🔄 Обновление компонентов панели..."
            ;;
        2)
            echo -e "\n⚠️ Полная переустановка..."
            rm -rf "$PANEL_DIR"
            rm -f /usr/local/bin/vpn
            ;;
        *)
            echo -e "\n❌ Операция отменена."
            exit 0
            ;;
    esac
fi

# Создаем необходимые папки и файлы, если их нет
mkdir -p "$PANEL_DIR/modules" /etc/UDPCustom/limits /etc/UDPCustom/traffic /etc/UDPCustom/traffic_limits
touch /etc/UDPCustom/users.db

# Автоматическая установка или обновление защитной оболочки лимитов
echo -e "\n🛡️ Настройка защитной оболочки проверки лимита устройств..."
cat << 'EOF' > /usr/local/bin/vpn-limit-shell
#!/bin/bash
username="$USER"
limits_dir="/etc/UDPCustom/limits"
max_limit=3
[ -f "$limits_dir/$username" ] && max_limit=$(cat "$limits_dir/$username")

active_pids=$(pgrep -u "$username")
count=0
for pid in $active_pids; do
    if ss -tp state established 2>/dev/null | grep -q "pid=$pid"; then
        ((count++))
    fi
done

if [ "$count" -gt "$max_limit" ]; then
    echo "Превышено максимальное количество устройств!"
    exit 1
fi

exec sleep infinity
EOF

chmod +x /usr/local/bin/vpn-limit-shell

# Обновляем оболочку для существующих пользователей из базы
if [ -f "/etc/UDPCustom/users.db" ]; then
    while read -r u; do
        [ -z "$u" ] && continue
        if id "$u" &>/dev/null; then
            chsh -s /usr/local/bin/vpn-limit-shell "$u" 2>/dev/null
        fi
    done < "/etc/UDPCustom/users.db"
fi

# Скачивание ядра и модулей с GitHub
echo -e "\n📥 Скачивание актуальных файлов с GitHub..."
curl -s -o "$PANEL_DIR/core.sh" "$REPO_URL/core.sh"
curl -s -o "$PANEL_DIR/modules/users.sh" "$REPO_URL/modules/users.sh"
curl -s -o "$PANEL_DIR/modules/masterdns.sh" "$REPO_URL/modules/masterdns.sh"
curl -s -o "$PANEL_DIR/modules/udp.sh" "$REPO_URL/modules/udp.sh"
curl -s -o "$PANEL_DIR/modules/ws.sh" "$REPO_URL/modules/ws.sh"
curl -s -o "$PANEL_DIR/modules/security.sh" "$REPO_URL/modules/security.sh"
curl -s -o "$PANEL_DIR/modules/traffic.sh" "$REPO_URL/modules/traffic.sh" 2>/dev/null
curl -s -o "$PANEL_DIR/modules/devicelimit.sh" "$REPO_URL/modules/devicelimit.sh" 2>/dev/null

# Скачивание главного исполняемого файла (точки входа)
curl -s -o /usr/local/bin/vpn "$REPO_URL/vpn"
chmod +x /usr/local/bin/vpn

echo -e "\n\033[0;32m🟢 Операция успешно завершена, Хозяин[span_1](start_span)[span_1](end_span)!\033[0m"
echo -e "Теперь для запуска панели просто введите в консоли: \033[1;33mvpn\033[0m[span_2](start_span)[span_2](end_span)"
