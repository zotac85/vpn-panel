#!/bin/bash
# install-whitedns-node.sh — установка WhiteDNS (MasterDnsVPN) через официальный установщик
# Использование: bash install-whitedns-node.sh <домен>
# Пример: bash install-whitedns-node.sh ff.26central.asia

set -e
DOMAIN="$1"
if [ -z "$DOMAIN" ]; then
    echo "ERROR: укажите домен (например: ff.26central.asia)"
    exit 1
fi

GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[1;33m"; CYAN="\033[0;36m"; NC="\033[0m"

[ "$(id -u)" -eq 0 ] || { echo -e "${RED}Запускать от root${NC}"; exit 1; }

clear
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e "${CYAN}   УСТАНОВКА WHITEDNS (MasterDnsVPN)${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  Домен: ${GREEN}$DOMAIN${NC}"
echo ""

# 1. Открываем порт 53
echo -e "${YELLOW}[1/2] Открываю порт 53 (TCP+UDP)...${NC}"
ufw allow 53/tcp comment 'DNS TCP' >/dev/null 2>&1 || true
ufw allow 53/udp comment 'DNS UDP' >/dev/null 2>&1 || true
echo -e "${GREEN}   ✓ Порт 53 открыт${NC}"

# 2. Запуск официального установщика
echo ""
echo -e "${YELLOW}[2/2] Запускаю официальный установщик...${NC}"
echo -e "${CYAN}   (домен будет передан автоматически)${NC}"
echo ""

# Используем expect для передачи домена
if ! command -v expect &>/dev/null; then
    apt-get install -y expect >/dev/null 2>&1
fi

expect << EXPECT_EOF
set timeout 600
spawn bash -c "bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh)"
expect {
    -re ".*[Dd]omain.*:" {
        send "$DOMAIN\r"
        exp_continue
    }
    -re ".*[Ee]nter.*:" {
        send "$DOMAIN\r"
        exp_continue
    }
    timeout {
        puts "\nTimeout ожидания запроса домена."
    }
    eof
}
EXPECT_EOF

echo ""
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}✅  УСТАНОВКА ЗАВЕРШЕНА${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Проверь статус сервиса:${NC}"
systemctl status masterdnsvpn --no-pager 2>&1 | head -5 || true
echo ""
echo -e "${YELLOW}Ключ шифрования (скопируй для клиента):${NC}"
echo ""
for path in /root/encrypt_key.txt /opt/masterdnsvpn/encrypt_key.txt /etc/masterdnsvpn/encrypt_key.txt; do
    if [ -f "$path" ]; then
        echo -e "${GREEN}Найден: $path${NC}"
        cat "$path"
        break
    fi
done
echo ""
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
