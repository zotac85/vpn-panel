#!/bin/bash
# vpn-optimize.sh — полная оптимизация сервера (мастер или нода)
LOG="/var/log/vpn-optimize.log"
echo ""
echo "⚡ ОПТИМИЗАЦИЯ СЕРВЕРА"
echo "━━━━━━━━━━━━━━━━━━━━"
echo "Старт: $(date '+%F %T')"
echo ""

WS_PORT=$(awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py 2>/dev/null | tr -dc '0-9')
[ -z "$WS_PORT" ] && WS_PORT=2052

MASTER_IP="${1:-}"
step_ok()   { echo "   ✓ $1"; }
step_fail() { echo "   ✗ $1"; }

# ─── 1. apt update + upgrade ───
do_apt() {
    echo "→ apt update && apt upgrade..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq 2>&1 | grep -v "^WARNING" | tail -2
    echo "   (может занять 3-5 минут...)"
    export DEBIAN_FRONTEND=noninteractive
    export NEEDRESTART_MODE=a
    apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade 2>&1 | tail -30
    if [ $? -eq 0 ]; then step_ok "Пакеты обновлены"; else step_fail "apt upgrade"; fi
}

# ─── 2. Отключить IPv6 ───
do_ipv6_off() {
    echo "→ Отключение IPv6..."
    cat > /etc/sysctl.d/99-disable-ipv6.conf << 'IPV6EOF'
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
IPV6EOF
    sysctl -p /etc/sysctl.d/99-disable-ipv6.conf >/dev/null 2>&1
    if grep -q "disable_ipv6 = 1" /etc/sysctl.conf 2>/dev/null; then
        step_ok "IPv6 отключён (уже был)"
    else
        echo "net.ipv6.conf.all.disable_ipv6 = 1" >> /etc/sysctl.conf
        step_ok "IPv6 отключён"
    fi
}

# ─── 3. UFW ───
do_ufw() {
    echo "→ Настройка UFW..."
    apt install -y -qq ufw >/dev/null 2>&1
    ufw --force reset >/dev/null 2>&1
    ufw default deny incoming >/dev/null 2>&1
    ufw default allow outgoing >/dev/null 2>&1
    ufw allow 22/tcp comment 'SSH' >/dev/null 2>&1
    ufw allow "$WS_PORT/tcp" comment 'WebSocket' >/dev/null 2>&1
    ufw allow 7300/tcp comment 'UDPGW' >/dev/null 2>&1
    ufw allow 53/tcp comment 'DNS TCP' >/dev/null 2>&1
    ufw allow 53/udp comment 'DNS UDP' >/dev/null 2>&1
    ufw --force enable >/dev/null 2>&1
    if ufw status | grep -q "Status: active"; then
        step_ok "UFW активен (22, $WS_PORT, 7300)"
    else
        step_fail "UFW"
    fi
}

# ─── 4. Fail2ban ───
do_fail2ban() {
    echo "→ Установка Fail2ban..."
    apt install -y -qq fail2ban >/dev/null 2>&1
    cat > /etc/fail2ban/jail.local << F2BEOF
[DEFAULT]
bantime = 10m
findtime = 10m
maxretry = 10
ignoreip = 127.0.0.1/8 ::1 ${MASTER_IP}

[sshd]
enabled = true
port = 22
F2BEOF
    systemctl enable fail2ban >/dev/null 2>&1
    systemctl restart fail2ban >/dev/null 2>&1
    if systemctl is-active --quiet fail2ban; then
        step_ok "Fail2ban активен (whitelist: $MASTER_IP)"
    else
        step_fail "Fail2ban"
    fi
}

# ─── 5. TCP BBR ───
do_bbr() {
    echo "→ Включение TCP BBR..."
    if ! grep -q "net.core.default_qdisc = fq" /etc/sysctl.conf 2>/dev/null; then
        echo "net.core.default_qdisc = fq" >> /etc/sysctl.conf
    fi
    if ! grep -q "net.ipv4.tcp_congestion_control = bbr" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv4.tcp_congestion_control = bbr" >> /etc/sysctl.conf
    fi
    modprobe tcp_bbr >/dev/null 2>&1
    sysctl -p /etc/sysctl.conf >/dev/null 2>&1
    if sysctl net.ipv4.tcp_congestion_control | grep -q bbr; then
        step_ok "TCP BBR включён"
    else
        step_fail "TCP BBR"
    fi
}

# ─── 6. TCP Brutal ───
do_brutal() {
    echo "→ Установка TCP Brutal..."
    if command -v brutalctl >/dev/null 2>&1; then
        brutalctl add 0.0.0.0/0 20 >/dev/null 2>&1
        echo "@reboot sleep 30 && brutalctl add 0.0.0.0/0 20" > /etc/cron.d/vpn-brutal
        chmod 644 /etc/cron.d/vpn-brutal
        step_ok "TCP Brutal уже установлен (правило 20 Mbps)"
        return
    fi
    KMAJ=$(uname -r | cut -d. -f1)
    KMIN=$(uname -r | cut -d. -f2)
    if [ "$KMAJ" -lt 5 ] || { [ "$KMAJ" -eq 5 ] && [ "$KMIN" -lt 10 ]; }; then
        step_fail "TCP Brutal: нужно ядро 5.10+ (у вас $(uname -r))"
        return
    fi
    bash <(curl -fsSL https://tcp.hy2.sh/) 2>&1 | tail -5
    if command -v brutalctl >/dev/null 2>&1; then
        brutalctl add 0.0.0.0/0 20 >/dev/null 2>&1
        echo "@reboot sleep 30 && brutalctl add 0.0.0.0/0 20" > /etc/cron.d/vpn-brutal
        chmod 644 /etc/cron.d/vpn-brutal
        step_ok "TCP Brutal установлен (20 Мбит/с + автозагрузка)"
    else
        step_fail "TCP Brutal"
    fi
}


# ─── 7.5. PerSourcePenalties off (фикс WS-прокси) ───
do_persource_penalties() {
    echo "→ Проверка PerSourcePenalties..."
    SSH_VER=$(ssh -V 2>&1 | grep -oP 'OpenSSH_\K[0-9]+\.[0-9]+' | head -1)
    SSH_MAJOR=$(echo "$SSH_VER" | cut -d. -f1)
    SSH_MINOR=$(echo "$SSH_VER" | cut -d. -f2)
    if [ -n "$SSH_MAJOR" ] && { [ "$SSH_MAJOR" -gt 9 ] || { [ "$SSH_MAJOR" -eq 9 ] && [ "$SSH_MINOR" -ge 8 ]; }; }; then
        cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak_$(date +%F_%H%M)
        if grep -q "^PerSourcePenalties" /etc/ssh/sshd_config; then
            sed -i 's/^PerSourcePenalties.*/PerSourcePenalties no/' /etc/ssh/sshd_config
        else
            echo "PerSourcePenalties no" >> /etc/ssh/sshd_config
        fi
        if sshd -t 2>/dev/null; then
            systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
            sleep 1
            step_ok "PerSourcePenalties отключён (OpenSSH $SSH_VER)"
        else
            step_fail "Ошибка синтаксиса, откат"
            cp $(ls -t /etc/ssh/sshd_config.bak_* | head -1) /etc/ssh/sshd_config
            systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
        fi
    else
        step_ok "Пропущено (OpenSSH $SSH_VER < 9.8)"
    fi
}

# ─── 7. Буферы ядра ───
do_buffers() {
    echo "→ Оптимизация буферов ядра..."
    cat > /etc/sysctl.d/99-vpn-buffers.conf << 'BUFEOF'
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_fastopen = 3
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_mtu_probing = 1
net.ipv4.tcp_slow_start_after_idle = 0
BUFEOF
    sysctl -p /etc/sysctl.d/99-vpn-buffers.conf >/dev/null 2>&1
    if grep -q "net.core.rmem_max" /etc/sysctl.conf 2>/dev/null || [ -f /etc/sysctl.d/99-vpn-buffers.conf ]; then
        step_ok "Буферы ядра оптимизированы"
    else
        step_fail "Буферы ядра"
    fi
}

# ─── 8. Swap 1 GB ───
do_swap() {
    echo "→ Настройка Swap 1 GB..."
    SWAP_TOTAL=$(free -m | awk '/Swap:/ {print $2}')
    if [ "$SWAP_TOTAL" -gt 0 ]; then
        step_ok "Swap уже есть ($SWAP_TOTAL MB)"
        return
    fi
    if [ -f /swapfile ]; then
        step_ok "Файл /swapfile уже существует"
        return
    fi
    fallocate -l 1G /swapfile >/dev/null 2>&1 || dd if=/dev/zero of=/swapfile bs=1M count=1024 >/dev/null 2>&1
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null 2>&1
    swapon /swapfile >/dev/null 2>&1
    if ! grep -q "/swapfile" /etc/fstab; then
        echo "/swapfile none swap sw 0 0" >> /etc/fstab
    fi
    if [ "$(free -m | awk '/Swap:/ {print $2}')" -gt 0 ]; then
        step_ok "Swap 1 GB создан"
    else
        step_fail "Swap"
    fi
}

# ─── Итог ───
print_footer() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━"
    echo "✅ ОПТИМИЗАЦИЯ ЗАВЕРШЕНА"
    echo "━━━━━━━━━━━━━━━━━━━━"
    echo "Завершено: $(date '+%F %T')"
    echo ""
    if [ -f /var/run/reboot-required ]; then
        echo "⚠️  Требуется ПЕРЕЗАГРУЗКА (обновилось ядро)"
        echo ""
        read -p "Перезагрузить сейчас? (y/n): " _r
        if [ "$_r" = "y" ] || [ "$_r" = "Y" ]; then
            echo "Перезагрузка через 5 сек..."
            nohup bash -c 'sleep 5 && reboot' >/dev/null 2>&1 &
        fi
        echo ""
    fi
}

# ─── Запуск ───
main() {
    echo "WS-порт: $WS_PORT"
    [ -n "$MASTER_IP" ] && echo "Мастер IP (whitelist fail2ban): $MASTER_IP"
    echo ""
    echo "Начинаю оптимизацию..."
    echo ""

    do_apt
    do_ipv6_off
    do_ufw
    do_fail2ban
    do_bbr
    do_brutal
    do_persource_penalties
    do_buffers
    do_swap

    print_footer
}

main
