#!/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "Ошибка: запустите скрипт от root (sudo -i)"
  exit 1
fi

echo "🔄 Загрузка модульной VPN панели с GitHub..."

PANEL_DIR="/usr/local/share/vpn-panel"
REPO_URL="https://raw.githubusercontent.com/zotac85/vpn-panel/main"

# Создаем папки
mkdir -p "$PANEL_DIR/modules" /etc/UDPCustom/limits
touch /etc/UDPCustom/users.db

# Скачиваем ядро и модули
echo "Скачивание файлов..."
curl -s -o "$PANEL_DIR/core.sh" "$REPO_URL/core.sh"
curl -s -o "$PANEL_DIR/modules/users.sh" "$REPO_URL/modules/users.sh"
curl -s -o "$PANEL_DIR/modules/masterdns.sh" "$REPO_URL/modules/masterdns.sh"
curl -s -o "$PANEL_DIR/modules/udp.sh" "$REPO_URL/modules/udp.sh"
curl -s -o "$PANEL_DIR/modules/ws.sh" "$REPO_URL/modules/ws.sh"
curl -s -o "$PANEL_DIR/modules/security.sh" "$REPO_URL/modules/security.sh"

# Скачиваем главную точку входа
curl -s -o /usr/local/bin/vpn "$REPO_URL/vpn"
chmod +x /usr/local/bin/vpn

echo -e "\n🟢 Установка успешно завершена, Хозяин!"
echo -e "Теперь для запуска панели просто введите в консоли: ${YELLOW}vpn${NC}"
