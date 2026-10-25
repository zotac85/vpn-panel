#!/bin/bash
# install-udpgw-node.sh — установка UDPGW на ноду (порт 7300)
set -e
GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[1;33m"; NC="\033[0m"

[ "$(id -u)" -eq 0 ] || { echo -e "${RED}Запускать от root${NC}"; exit 1; }

echo -e "${YELLOW}--- Установка UDPGW (порт 7300) ---${NC}"
apt update -y -qq >/dev/null 2>&1
apt install -y -qq wget >/dev/null 2>&1

mkdir -p /bin
wget -q -O /bin/udpgw "https://raw.githubusercontent.com/http-custom/udp-custom/main/module/udpgw"
if [ ! -s /bin/udpgw ]; then
    echo -e "${RED}Ошибка загрузки udpgw${NC}"
    exit 1
fi
chmod +x /bin/udpgw

cat > /etc/systemd/system/udpgw.service << 'GWEOF'
[Unit]
Description=UDPGW BadVPN Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/bin/udpgw --listen-addr 127.0.0.1:7300 --max-clients 1024 --max-connections-for-client 512
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
GWEOF

systemctl daemon-reload
systemctl enable udpgw >/dev/null 2>&1
systemctl restart udpgw
sleep 1

if systemctl is-active --quiet udpgw; then
    echo -e "${GREEN}✅ UDPGW запущен на 127.0.0.1:7300${NC}"
    ss -tlnp 2>/dev/null | grep 7300 || true
else
    echo -e "${RED}❌ Ошибка запуска UDPGW${NC}"
    journalctl -u udpgw -n 10 --no-pager 2>/dev/null | tail -10
    exit 1
fi
