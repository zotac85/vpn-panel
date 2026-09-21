#!/bin/bash

install_udp() {
    header
    echo -e "${YELLOW}--- ⚡ Установка UDP Custom & UDPGW ---${NC}"
    apt update -y && apt install -y wget curl iptables dos2unix iptables-persistent

    mkdir -p /root/udp /etc/UDPCustom "$LIMITS_DIR"
    touch "$DB_USERS"
    ARCH=$(uname -m)

    if [ "$ARCH" = "x86_64" ]; then
        wget -q -O /root/udp/udp-custom "https://raw.githubusercontent.com/http-custom/udp-custom/main/bin/udp-custom-linux-amd64"
    elif [ "$ARCH" = "aarch64" ]; then
        wget -q -O /root/udp/udp-custom "https://raw.githubusercontent.com/http-custom/udp-custom/main/bin/udp-custom-linux-arm64"
    fi

    if [ ! -s /root/udp/udp-custom ]; then
        echo -e "${RED}Ошибка загрузки бинарного файла.${NC}"
        read -p "Нажмите Enter для возврата..."; return
    fi
    chmod +x /root/udp/udp-custom

    wget -q -O /bin/udpgw "https://raw.githubusercontent.com/http-custom/udp-custom/main/module/udpgw"
    chmod +x /bin/udpgw

    cat << 'CONF_EOF' > /root/udp/config.json
{
  "listen": ":36712",
  "stream_buffer": 33554432,
  "receive_buffer": 83886080,
  "auth": {
    "mode": "passwords"
  }
}
CONF_EOF

    iptables -t nat -D PREROUTING -p udp --dport 1:65535 -j REDIRECT --to-ports 36712 2>/dev/null
    iptables -t nat -A PREROUTING -p udp --dport 1:65535 -j REDIRECT --to-ports 36712
    netfilter-persistent save 2>/dev/null

    cat << 'SVC_EOF' > /etc/systemd/system/udp-custom.service
[Unit]
Description=UDP Custom Tunnel Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/udp
ExecStart=/root/udp/udp-custom server -c /root/udp/config.json
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SVC_EOF

    cat << 'GW_EOF' > /etc/systemd/system/udpgw.service
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
GW_EOF

    systemctl daemon-reload
    systemctl enable udpgw udp-custom
    systemctl restart udpgw udp-custom

    sleep 1
    if systemctl is-active --quiet udp-custom && systemctl is-active --quiet udpgw; then
        echo -e "${GREEN}Установка завершена, службы успешно работают!${NC}"
    else
        echo -e "${RED}Ошибка запуска.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

menu_service() {
    while true; do
        header
        echo -e "${YELLOW}⚙️  УПРАВЛЕНИЕ UDP CUSTOM СЕРВИСОМ${NC}"
        echo -e " UDP-Custom : $(get_service_status udp-custom)"
        echo -e " UDPGW      : $(get_service_status udpgw)"
        echo ""
        echo -e " 1) ⚡ Установить / Обновить UDP Custom"
        echo -e " 2) 🔄 Перезапустить службы"
        echo -e " 3) ⏸️  Остановить службы"
        echo -e " 4) 📜 Посмотреть логи UDP"
        echo -e " 5) 🗑️  Удалить UDP Custom"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-5]: " sochoice
        case $sochoice in
            1) install_udp ;;
            2) systemctl restart udpgw udp-custom; echo -e "${GREEN}Перезапущено.${NC}"; sleep 1 ;;
            3) systemctl stop udpgw udp-custom; echo -e "${YELLOW}Остановлено.${NC}"; sleep 1 ;;
            4) header; journalctl -u udp-custom -n 25 --no-pager; echo ""; read -p "Enter..." ;;
            5) 
                read -p "Точно удалить? (y/n): " confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    systemctl stop udp-custom udpgw 2>/dev/null
                    systemctl disable udp-custom udpgw 2>/dev/null
                    rm -f /etc/systemd/system/udp-custom.service /etc/systemd/system/udpgw.service
                    rm -rf /root/udp /bin/udpgw
                    iptables -t nat -D PREROUTING -p udp --dport 1:65535 -j REDIRECT --to-ports 36712 2>/dev/null
                    echo -e "${GREEN}Удалено.${NC}"; sleep 1
                fi ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
