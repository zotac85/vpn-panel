#!/bin/bash

system_update() {
    header
    echo -e "${YELLOW}--- 🔄 Обновление системы ---${NC}"
    apt update && apt upgrade -y
    echo -e "${GREEN}Система успешно обновлена!${NC}"
    read -p "Нажмите Enter..."
}

disable_ipv6() {
    header
    echo -e "${YELLOW}--- 🟢 Отключение IPv6 ---${NC}"
    if grep -q "net.ipv6.conf.all.disable_ipv6 = 1" /etc/sysctl.conf; then
        echo -e "${GREEN}IPv6 уже отключен!${NC}"
    else
        echo "net.ipv6.conf.all.disable_ipv6 = 1" >> /etc/sysctl.conf
        echo "net.ipv6.conf.default.disable_ipv6 = 1" >> /etc/sysctl.conf
        sysctl -p
        echo -e "${GREEN}IPv6 успешно отключен!${NC}"
    fi
    read -p "Нажмите Enter..."
}

install_ufw() {
    header
    echo -e "${YELLOW}--- 🧱 Настройка UFW Firewall ---${NC}"
    apt update -y && apt install -y ufw
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp comment 'SSH'
    ufw allow 1:65535/udp comment 'UDP Custom Range'
    ufw allow 7300/tcp comment 'UDPGW'
    ufw allow 36712/udp comment 'UDP Custom Main'
    local ws_port=$(get_ws_port)
    [[ "$ws_port" != "Не установлен" ]] && ufw allow $ws_port/tcp comment 'WebSocket Proxy'
    echo "y" | ufw enable
    echo -e "${GREEN}UFW успешно включен!${NC}"; read -p "Enter..."
}

install_fail2ban() {
    header
    apt update -y && apt install -y fail2ban
    cat << 'F2B_EOF' > /etc/fail2ban/jail.local
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = 22
F2B_EOF
    systemctl daemon-reload && systemctl enable fail2ban && systemctl restart fail2ban
    echo -e "${GREEN}Fail2ban установлен!${NC}"; read -p "Enter..."
}

optimize_udp_tm() {
    header
    echo -e "${YELLOW}--- ⚡ Оптимизация сети и буферов ---${NC}"
    if grep -q "net.core.rmem_max" /etc/sysctl.conf; then
        echo -e "${GREEN}✅ Система уже оптимизирована!${NC}"
    else
        cat << 'SYS_EOF' >> /etc/sysctl.conf
fs.file-max = 1000000
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.core.rmem_default = 33554432
net.core.wmem_default = 33554432
net.core.netdev_max_backlog = 10000
net.ipv4.udp_mem = 65536 131072 262144
SYS_EOF
        sysctl -p >/dev/null 2>&1
        echo -e "${GREEN}🎉 Буферы увеличены!${NC}"
    fi
    read -p "Enter..."
}

enable_bbr() {
    header
    modprobe tcp_bbr 2>/dev/null
    echo "tcp_bbr" > /etc/modules-load.d/bbr.conf 2>/dev/null
    sed -i '/net.core.default_qdisc/d' /etc/sysctl.conf
    sed -i '/net.ipv4.tcp_congestion_control/d' /etc/sysctl.conf
    echo "net.core.default_qdisc = fq" >> /etc/sysctl.conf
    echo "net.ipv4.tcp_congestion_control = bbr" >> /etc/sysctl.conf
    sysctl -p >/dev/null 2>&1
    echo -e "${GREEN}🎉 TCP BBR включен!${NC}"; read -p "Enter..."
}

menu_sec() {
    while true; do
        header
        echo -e "${YELLOW}🛡️  БЕЗОПАСНОСТЬ, СИСТЕМА И ОПТИМИЗАЦИЯ${NC}"
        echo -e " Обновление системы: Доступно"
        echo -e " Отключение IPv6    : $(get_ipv6_status)"
        echo -e " UFW Firewall       : $(get_ufw_status)"
        echo -e " Fail2ban           : $(get_service_status fail2ban)"
        echo -e " TCP BBR            : $(get_bbr_status)"
        echo -e " Буферы ядра        : $(get_udp_opt_status)"
        echo ""
        echo -e " 1) 🔄 Обновить систему (apt update && upgrade)"
        echo -e " 2) 🟢 Отключить IPv6"
        echo -e " 3) 🧱 Включить UFW Firewall"
        echo -e " 4) 🛡️  Включить Fail2ban (Антиспам/Брутфорс)"
        echo -e " 5) 🚀 Включить TCP BBR"
        echo -e " 6) ⚡ Оптимизировать буферы ядра"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите раздел [0-6]: " sec_choice
        case $sec_choice in
            1) system_update ;;
            2) disable_ipv6 ;;
            3) install_ufw ;;
            4) install_fail2ban ;;
            5) enable_bbr ;;
            6) optimize_udp_tm ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
