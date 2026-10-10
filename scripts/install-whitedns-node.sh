#!/bin/bash
# install-whitedns-node.sh — установка MasterDnsVPN (WhiteDNS) на ноду
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
echo -e "${YELLOW}[1/4] Открываю порт 53 (TCP+UDP)...${NC}"
ufw allow 53/tcp comment 'DNS TCP' >/dev/null 2>&1 || true
ufw allow 53/udp comment 'DNS UDP' >/dev/null 2>&1 || true
echo -e "${GREEN}   ✓ Порт 53 открыт${NC}"

# 2. Установка MasterDnsVPN
echo ""
echo -e "${YELLOW}[2/4] Устанавливаю MasterDnsVPN...${NC}"
bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh) 2>&1 | tail -20

# 3. Настройка домена
echo ""
echo -e "${YELLOW}[3/4] Настраиваю домен: $DOMAIN${NC}"
CFG=""
for path in /opt/masterdnsvpn/server_config.toml /etc/masterdnsvpn/server_config.toml /root/masterdnsvpn/server_config.toml; do
    if [ -f "$path" ]; then
        CFG="$path"
        break
    fi
done

if [ -z "$CFG" ]; then
    CFG=$(find / -name "server_config.toml" -not -path "*/proc/*" 2>/dev/null | head -1)
fi

if [ -z "$CFG" ]; then
    echo -e "${RED}   ✗ Не найден server_config.toml${NC}"
    echo -e "${YELLOW}   Найди вручную: find / -name server_config.toml 2>/dev/null${NC}"
    exit 1
fi

echo -e "   Конфиг: $CFG"
# Меняем DOMAIN
if grep -q '^DOMAIN' "$CFG"; then
    sed -i "s|^DOMAIN.*|DOMAIN = [\"$DOMAIN\"]|" "$CFG"
else
    echo "DOMAIN = [\"$DOMAIN\"]" >> "$CFG"
fi
echo -e "${GREEN}   ✓ Домен установлен${NC}"

# 4. Перезапуск
echo ""
echo -e "${YELLOW}[4/4] Перезапускаю сервис...${NC}"
systemctl restart masterdnsvpn 2>/dev/null || systemctl restart masterdns 2>/dev/null || true
sleep 2

# Итог
echo ""
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}✅  WHITEDNS УСТАНОВЛЕН${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  Домен:     ${GREEN}$DOMAIN${NC}"
echo -e "  Конфиг:    $CFG"
echo -e "  Порт:      53 (TCP+UDP)"
echo ""

KEY_FILE=""
for path in /opt/masterdnsvpn/encrypt_key.txt /etc/masterdnsvpn/encrypt_key.txt; do
    if [ -f "$path" ]; then
        KEY_FILE="$path"
        break
    fi
done
if [ -z "$KEY_FILE" ]; then
    KEY_FILE=$(find / -name "encrypt_key.txt" -not -path "*/proc/*" 2>/dev/null | head -1)
fi

if [ -n "$KEY_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo -e "  ${YELLOW}Ключ шифрования (скопируй для клиента):${NC}"
    echo ""
    cat "$KEY_FILE"
    echo ""
fi

echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}DNS-настройки (сделай в Cloudflare):${NC}"
echo "  A:  ns1.$DOMAIN  →  $(hostname -I | awk '{print $1}')"
echo "  NS: $DOMAIN      →  ns1.$DOMAIN"
echo ""
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
