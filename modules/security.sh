#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ БЕЗОПАСНОСТИ, СИСТЕМЫ И ОПТИМИЗАЦИИ
# ──────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────
# 🖥️  СИСТЕМА
# ──────────────────────────────────────────────────────────────

system_update() {
    header
    echo -e "${YELLOW}--- 🔄 Обновление системы ---${NC}"
    echo ""
    echo -e "${CYAN}Обновляем списки пакетов...${NC}"
    apt update -qq 2>/dev/null

    # Проверяем, есть ли что обновлять
    local upgradable=$(apt list --upgradable 2>/dev/null | grep -c upgradable)

    if [ "$upgradable" -eq 0 ]; then
        echo -e "${GREEN}✅ Система уже актуальна — обновлений нет.${NC}"
        read -p "Нажмите Enter..."
        return
    fi

    echo -e "${YELLOW}Доступно обновлений: $upgradable${NC}"
    echo ""
    apt list --upgradable 2>/dev/null | head -20
    echo ""
    read -p "Продолжить обновление? (y/n): " c
    [[ ! "$c" =~ ^[Yy]$ ]] && return

    echo ""
    apt upgrade -y
    echo -e "${GREEN}✅ Система обновлена!${NC}"
    read -p "Нажмите Enter..."
}

change_timezone() {
    header
    echo -e "${YELLOW}--- 🕒 Изменение часового пояса ---${NC}"
    echo ""
    local current=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone)
    echo -e "Текущий: ${GREEN}$current${NC}"
    echo ""
    echo -e "${CYAN}Популярные зоны:${NC}"
    echo "  1) Europe/Moscow       (Москва)"
    echo "  2) Europe/Kyiv         (Киев)"
    echo "  3) Europe/Minsk        (Минск)"
    echo "  4) Asia/Almaty         (Алматы)"
    echo "  5) Asia/Ashgabat       (Ашхабад)"
    echo "  6) Asia/Tashkent       (Ташкент)"
    echo "  7) Europe/Berlin       (Берлин)"
    echo "  8) UTC                 (UTC)"
    echo "  9) Ввести вручную"
    echo "  0) Отмена"
    echo ""
    read -p "Выбор [0-9]: " tz

    local new_tz=""
    case $tz in
        1) new_tz="Europe/Moscow" ;;
        2) new_tz="Europe/Kyiv" ;;
        3) new_tz="Europe/Minsk" ;;
        4) new_tz="Asia/Almaty" ;;
        5) new_tz="Asia/Ashgabat" ;;
        6) new_tz="Asia/Tashkent" ;;
        7) new_tz="Europe/Berlin" ;;
        8) new_tz="UTC" ;;
        9) read -p "Введите зону (пример: Europe/Paris): " new_tz ;;
        0) return ;;
        *) return ;;
    esac

    if [ -n "$new_tz" ]; then
        timedatectl set-timezone "$new_tz" 2>/dev/null
        echo "$new_tz" > /etc/timezone 2>/dev/null
        ln -fs "/usr/share/zoneinfo/$new_tz" /etc/localtime 2>/dev/null
        echo -e "${GREEN}✅ Часовой пояс: $new_tz${NC}"
        date
    fi
    read -p "Нажмите Enter..."
}

change_dns() {
    header
    echo -e "${YELLOW}--- 🌐 Изменение DNS-серверов ---${NC}"
    echo ""
    echo -e "${CYAN}Текущие DNS:${NC}"
    cat /etc/resolv.conf 2>/dev/null | grep nameserver | head -5
    echo ""
    echo -e " 1) 🟠 Cloudflare  (1.1.1.1, 1.0.0.1) — быстрый"
    echo "  2) 🔵 Google      (8.8.8.8, 8.8.4.4)"
    echo "  3) 🟣 Quad9       (9.9.9.9, 149.112.112.112) — блокирует malware"
    echo "  4) 🔴 AdGuard     (94.140.14.14, 94.140.15.15) — режет рекламу"
    echo "  5) ✏️  Ввести вручную"
    echo "  0) Отмена"
    echo ""
    read -p "Выбор [0-5]: " dns

    local dns1="" dns2=""
    case $dns in
        1) dns1="1.1.1.1"; dns2="1.0.0.1" ;;
        2) dns1="8.8.8.8"; dns2="8.8.4.4" ;;
        3) dns1="9.9.9.9"; dns2="149.112.112.112" ;;
        4) dns1="94.140.14.14"; dns2="94.140.15.15" ;;
        5) read -p "DNS #1: " dns1; read -p "DNS #2: " dns2 ;;
        0) return ;;
        *) return ;;
    esac

    if [ -n "$dns1" ]; then
        # Отключаем systemd-resolved, если есть (чтобы не перетирал)
        systemctl stop systemd-resolved 2>/dev/null
        systemctl disable systemd-resolved 2>/dev/null

        rm -f /etc/resolv.conf
        cat > /etc/resolv.conf << EOF
nameserver $dns1
nameserver $dns2
EOF
        chattr +i /etc/resolv.conf 2>/dev/null
        echo -e "${GREEN}✅ DNS обновлены: $dns1, $dns2${NC}"
    fi
    read -p "Нажмите Enter..."
}

cleanup_system() {
    header
    echo -e "${YELLOW}--- 🧹 Очистка системы ---${NC}"
    echo ""

    # Считаем освобождаемое место
    local apt_size=$(du -sh /var/cache/apt 2>/dev/null | awk '{print $1}')
    local journal_size=$(journalctl --disk-usage 2>/dev/null | grep -oP '[\d.]+[A-Z]+' | head -1)

    echo -e "${CYAN}Будет очищено:${NC}"
    echo -e "  • Кеш apt       : ~${apt_size:-0}"
    echo -e "  • Журнал systemd: ~${journal_size:-0}"
    echo -e "  • Временные файлы /tmp"
    echo ""
    read -p "Очистить? (y/n): " c
    [[ ! "$c" =~ ^[Yy]$ ]] && return

    echo ""
    echo -e "${CYAN}[1/3] Очистка apt...${NC}"
    apt clean -y 2>/dev/null
    apt autoremove -y 2>/dev/null

    echo -e "${CYAN}[2/3] Очистка журналов (старше 7 дней)...${NC}"
    journalctl --vacuum-time=7d 2>/dev/null

    echo -e "${CYAN}[3/3] Очистка /tmp...${NC}"
    rm -rf /tmp/* 2>/dev/null
    rm -rf /var/tmp/* 2>/dev/null

    echo ""
    echo -e "${GREEN}✅ Очистка завершена${NC}"
    df -h / | tail -1
    read -p "Нажмите Enter..."
}

disk_info() {
    header
    echo -e "${YELLOW}--- 💽 Информация о дисках ---${NC}"
    echo ""
    echo -e "${CYAN}── Общее использование ──${NC}"
    df -h | grep -v tmpfs
    echo ""
    echo -e "${CYAN}── Топ-10 папок в / ──${NC}"
    du -sh /* 2>/dev/null | sort -rh | head -10
    echo ""
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# 🛡️  БЕЗОПАСНОСТЬ
# ──────────────────────────────────────────────────────────────

ufw_manage() {
    while true; do
        header
        echo -e "${YELLOW}🧱 UFW FIREWALL — УПРАВЛЕНИЕ${NC}"
        echo ""

        if ufw status 2>/dev/null | grep -q "Status: active"; then
            echo -e " Статус: ${GREEN}🟢 Активен${NC}"
            local rules_count=$(ufw status numbered 2>/dev/null | grep -c '^\[')
            echo -e " Правил: ${CYAN}$rules_count${NC}"
        else
            echo -e " Статус: ${RED}🔴 Выключен${NC}"
        fi
        echo ""
        echo -e " 1) 📋 Просмотр правил"
        echo -e " 2) ➕ Добавить порт"
        echo -e " 3) 🗑️  Удалить правило по номеру"
        echo -e " 4) 🚀 Включить UFW (с базовой настройкой)"
        echo -e " 5) 🛑 Выключить UFW"
        echo -e " 6) 🔄 Перезапустить UFW"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-6]: " uchoice

        case $uchoice in
            1)
                header
                echo -e "${YELLOW}--- 📋 Правила UFW ---${NC}"
                echo ""
                ufw status numbered 2>/dev/null
                echo ""
                read -p "Enter..."
                ;;
            2)
                header
                echo -e "${YELLOW}--- ➕ Добавить порт ---${NC}"
                echo ""
                read -p "Порт (или диапазон, пример: 8080 или 8080:8090): " port
                [ -z "$port" ] && continue
                echo ""
                echo " 1) TCP"
                echo " 2) UDP"
                echo " 3) TCP + UDP"
                read -p "Протокол [1-3]: " proto
                local proto_str=""
                case $proto in
                    1) proto_str="tcp" ;;
                    2) proto_str="udp" ;;
                    3) proto_str="tcp,udp" ;;
                    *) continue ;;
                esac
                read -p "Комментарий (необязательно): " comment
                ufw allow $port/$proto_str comment "$comment" 2>/dev/null
                echo -e "${GREEN}✅ Правило добавлено${NC}"
                sleep 1
                ;;
            3)
                header
                echo -e "${YELLOW}--- 🗑️  Удалить правило ---${NC}"
                echo ""
                ufw status numbered 2>/dev/null
                echo ""
                read -p "Номер правила (0 = отмена): " num
                [[ "$num" == "0" || -z "$num" ]] && continue
                echo "y" | ufw delete "$num" 2>/dev/null
                echo -e "${GREEN}✅ Правило удалено${NC}"
                sleep 1
                ;;
            4)
                header
                echo -e "${YELLOW}--- 🚀 Включение UFW ---${NC}"
                echo ""
                apt install -y ufw 2>/dev/null
                ufw --force reset 2>/dev/null
                ufw default deny incoming
                ufw default allow outgoing
                ufw allow 22/tcp comment 'SSH'
                ufw allow 1:65535/udp comment 'UDP Range'
                ufw allow 7300/tcp comment 'UDPGW'
                ufw allow 36712/udp comment 'UDP Custom'
                local ws_port=$(get_ws_port 2>/dev/null)
                [[ "$ws_port" =~ ^[0-9]+$ ]] && ufw allow "$ws_port/tcp" comment 'WebSocket'
                echo "y" | ufw enable
                echo -e "${GREEN}✅ UFW включён с базовой конфигурацией${NC}"
                sleep 2
                ;;
            5)
                read -p "Выключить UFW? (y/n): " c
                if [[ "$c" =~ ^[Yy]$ ]]; then
                    ufw disable
                    echo -e "${YELLOW}UFW выключен${NC}"
                    sleep 1
                fi
                ;;
            6)
                ufw reload 2>/dev/null
                echo -e "${GREEN}✅ UFW перезагружен${NC}"
                sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

fail2ban_manage() {
    while true; do
        header
        echo -e "${YELLOW}🛡️  FAIL2BAN — УПРАВЛЕНИЕ${NC}"
        echo ""

        if systemctl is-active --quiet fail2ban 2>/dev/null; then
            echo -e " Статус: ${GREEN}🟢 Активен${NC}"
            local banned=$(fail2ban-client status sshd 2>/dev/null | grep -oP 'Currently banned:\s*\K[0-9]+')
            echo -e " В бане SSH: ${RED}${banned:-0}${NC}"
        else
            echo -e " Статус: ${RED}🔴 Выключен${NC}"
        fi
        echo ""
        echo -e " 1) ⚡ Установить Fail2ban"
        echo -e " 2) 📊 Статус (SSH + IP в бане)"
        echo -e " 3) 📜 Последние баны (лог)"
        echo -e " 4) 🔓 Разбанить IP"
        echo -e " 5) 📝 Редактировать jail.local"
        echo -e " 6) 🔄 Перезапустить Fail2ban"
        echo -e " 7) 🗑️  Удалить Fail2ban"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-7]: " fchoice

        case $fchoice in
            1)
                header
                apt update -qq 2>/dev/null
                apt install -y fail2ban 2>/dev/null
                cat << 'EOF' > /etc/fail2ban/jail.local
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
ignoreip = 127.0.0.1/8

[sshd]
enabled = true
port    = 22
logpath = %(sshd_log)s
backend = %(sshd_backend)s
EOF
                systemctl daemon-reload
                systemctl enable fail2ban 2>/dev/null
                systemctl restart fail2ban
                echo -e "${GREEN}✅ Fail2ban установлен и настроен${NC}"
                read -p "Enter..."
                ;;
            2)
                header
                echo -e "${YELLOW}--- 📊 Статус Fail2ban ---${NC}"
                echo ""
                fail2ban-client status 2>/dev/null
                echo ""
                fail2ban-client status sshd 2>/dev/null
                echo ""
                read -p "Enter..."
                ;;
            3)
                header
                echo -e "${YELLOW}--- 📜 Последние баны ---${NC}"
                echo ""
                grep "Ban " /var/log/fail2ban.log 2>/dev/null | tail -20
                [ -z "$(grep 'Ban ' /var/log/fail2ban.log 2>/dev/null)" ] && echo -e "${MAGENTA}Банов пока не было.${NC}"
                echo ""
                read -p "Enter..."
                ;;
            4)
                header
                echo -e "${YELLOW}--- 🔓 Разбанить IP ---${NC}"
                echo ""
                fail2ban-client status sshd 2>/dev/null
                echo ""
                read -p "IP для разбана (0 = отмена): " ip
                [[ "$ip" == "0" || -z "$ip" ]] && continue
                fail2ban-client set sshd unbanip "$ip" 2>/dev/null
                echo -e "${GREEN}✅ IP $ip разбанен${NC}"
                sleep 2
                ;;
            5)
                header
                if [ -f /etc/fail2ban/jail.local ]; then
                    if command -v nano &>/dev/null; then
                        nano /etc/fail2ban/jail.local
                    else
                        vi /etc/fail2ban/jail.local
                    fi
                    systemctl restart fail2ban
                    echo -e "${GREEN}✅ Сохранено и перезапущено${NC}"
                else
                    echo -e "${RED}Файл /etc/fail2ban/jail.local не найден${NC}"
                fi
                read -p "Enter..."
                ;;
            6)
                systemctl restart fail2ban 2>/dev/null
                echo -e "${GREEN}✅ Fail2ban перезапущен${NC}"
                sleep 1
                ;;
            7)
                read -p "Удалить Fail2ban? (y/n): " c
                if [[ "$c" =~ ^[Yy]$ ]]; then
                    systemctl stop fail2ban 2>/dev/null
                    systemctl disable fail2ban 2>/dev/null
                    apt remove -y fail2ban 2>/dev/null
                    echo -e "${GREEN}✅ Fail2ban удалён${NC}"
                    sleep 1
                fi
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

change_root_password() {
    header
    echo -e "${YELLOW}--- 🔑 Смена пароля root ---${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  ВНИМАНИЕ: если забудешь пароль — потеряешь доступ!${NC}"
    echo -e "${CYAN}Запиши новый пароль куда-нибудь.${NC}"
    echo ""
    read -p "Продолжить? (y/n): " c
    [[ ! "$c" =~ ^[Yy]$ ]] && return

    echo ""
    passwd root
    read -p "Нажмите Enter..."
}

change_ssh_port() {
    header
    echo -e "${YELLOW}--- 🔐 Смена порта SSH ---${NC}"
    echo ""
    local current=$(grep -E "^Port " /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}')
    [ -z "$current" ] && current="22"
    echo -e "Текущий порт: ${GREEN}$current${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  ВАЖНО:${NC}"
    echo -e " • Открой НОВЫЙ порт в UFW ДО смены"
    echo -e " • Не закрывай текущую SSH-сессию"
    echo -e " • Проверь вход по новому порту СНАЧАЛА"
    echo ""
    read -p "Новый порт (1-65535, 0 = отмена): " new_port
    [[ "$new_port" == "0" || -z "$new_port" ]] && return

    if ! [[ "$new_port" =~ ^[0-9]+$ ]] || [ "$new_port" -lt 1 ] || [ "$new_port" -gt 65535 ]; then
        echo -e "${RED}Неверный порт${NC}"
        read -p "Enter..."; return
    fi

    # Открываем новый порт в UFW
    ufw allow "$new_port/tcp" comment 'SSH new port' 2>/dev/null

    # Меняем в sshd_config
    if grep -qE "^#?Port " /etc/ssh/sshd_config; then
        sed -i "s|^#\?Port .*|Port $new_port|" /etc/ssh/sshd_config
    else
        echo "Port $new_port" >> /etc/ssh/sshd_config
    fi

    # Обновляем fail2ban, если есть
    [ -f /etc/fail2ban/jail.local ] && \
        sed -i "s|^port.*=.*22|port = $new_port|" /etc/fail2ban/jail.local

    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
    systemctl restart fail2ban 2>/dev/null

    echo ""
    echo -e "${GREEN}✅ Порт SSH изменён на $new_port${NC}"
    echo -e "${CYAN}Не закрывай текущую сессию! Проверь вход с нового порта.${NC}"
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# ⚡ ОПТИМИЗАЦИЯ
# ──────────────────────────────────────────────────────────────

toggle_ipv6() {
    header
    echo -e "${YELLOW}--- 🌐 IPv6 ---${NC}"
    echo ""
    if grep -q "net.ipv6.conf.all.disable_ipv6 = 1" /etc/sysctl.conf 2>/dev/null; then
        echo -e "Текущий статус: ${RED}🔴 Отключён${NC}"
        echo ""
        read -p "Включить IPv6? (y/n): " c
        if [[ "$c" =~ ^[Yy]$ ]]; then
            sed -i '/net.ipv6.conf.all.disable_ipv6/d' /etc/sysctl.conf
            sed -i '/net.ipv6.conf.default.disable_ipv6/d' /etc/sysctl.conf
            sysctl -p >/dev/null 2>&1
            echo -e "${GREEN}✅ IPv6 включён${NC}"
        fi
    else
        echo -e "Текущий статус: ${GREEN}🟢 Включён${NC}"
        echo ""
        read -p "Отключить IPv6? (y/n): " c
        if [[ "$c" =~ ^[Yy]$ ]]; then
            echo "net.ipv6.conf.all.disable_ipv6 = 1" >> /etc/sysctl.conf
            echo "net.ipv6.conf.default.disable_ipv6 = 1" >> /etc/sysctl.conf
            sysctl -p >/dev/null 2>&1
            echo -e "${GREEN}✅ IPv6 отключён${NC}"
        fi
    fi
    read -p "Нажмите Enter..."
}

toggle_bbr() {
    header
    echo -e "${YELLOW}--- 🚀 TCP BBR ---${NC}"
    echo ""
    if sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
        echo -e "Текущий статус: ${GREEN}🟢 Включён (BBR)${NC}"
        echo ""
        read -p "Выключить BBR (вернуть Cubic)? (y/n): " c
        if [[ "$c" =~ ^[Yy]$ ]]; then
            sed -i '/net.core.default_qdisc/d' /etc/sysctl.conf
            sed -i '/net.ipv4.tcp_congestion_control/d' /etc/sysctl.conf
            echo "net.ipv4.tcp_congestion_control = cubic" >> /etc/sysctl.conf
            sysctl -p >/dev/null 2>&1
            echo -e "${YELLOW}✅ BBR выключен, используется Cubic${NC}"
        fi
    else
        echo -e "Текущий статус: ${RED}🔴 Выключен (Cubic)${NC}"
        echo ""
        read -p "Включить BBR? (y/n): " c
        if [[ "$c" =~ ^[Yy]$ ]]; then
            modprobe tcp_bbr 2>/dev/null
            echo "tcp_bbr" > /etc/modules-load.d/bbr.conf 2>/dev/null
            sed -i '/net.core.default_qdisc/d' /etc/sysctl.conf
            sed -i '/net.ipv4.tcp_congestion_control/d' /etc/sysctl.conf
            echo "net.core.default_qdisc = fq" >> /etc/sysctl.conf
            echo "net.ipv4.tcp_congestion_control = bbr" >> /etc/sysctl.conf
            sysctl -p >/dev/null 2>&1
            echo -e "${GREEN}✅ TCP BBR включён${NC}"
        fi
    fi
    read -p "Нажмите Enter..."
}

optimize_udp_tm() {
    header
    echo -e "${YELLOW}--- ⚡ Оптимизация буферов ---${NC}"
    echo ""
    if grep -q "net.core.rmem_max" /etc/sysctl.conf 2>/dev/null; then
        echo -e "${GREEN}✅ Система уже оптимизирована.${NC}"
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
    read -p "Нажмите Enter..."
}

create_swap() {
    header
    echo -e "${YELLOW}--- 💾 Swap-файл ---${NC}"
    echo ""

    local current_swap=$(free -m | awk '/Swap:/ {print $2}')
    if [ "$current_swap" -gt 0 ]; then
        echo -e "Текущий swap: ${GREEN}${current_swap} MB${NC}"
        echo ""
        read -p "Пересоздать swap? (y/n): " c
        [[ ! "$c" =~ ^[Yy]$ ]] && return
        swapoff /swapfile 2>/dev/null
        rm -f /swapfile
        sed -i '/\/swapfile/d' /etc/fstab
    fi

    echo ""
    read -p "Размер swap в MB (например 1024 или 2048): " size
    [[ ! "$size" =~ ^[0-9]+$ ]] && { echo -e "${RED}Неверный размер${NC}"; sleep 1; return; }

    echo -e "\n${CYAN}Создаём swap ${size}MB...${NC}"
    fallocate -l ${size}M /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=$size 2>/dev/null
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null 2>&1
    swapon /swapfile 2>/dev/null

    grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab

    # Оптимизация для VPS
    sysctl vm.swappiness=10 2>/dev/null
    grep -q "vm.swappiness" /etc/sysctl.conf || echo "vm.swappiness=10" >> /etc/sysctl.conf

    echo ""
    echo -e "${GREEN}✅ Swap ${size}MB создан${NC}"
    free -m | grep Swap
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# 🔄 УПРАВЛЕНИЕ
# ──────────────────────────────────────────────────────────────

server_reboot() {
    header
    echo -e "${YELLOW}--- 🔄 Перезагрузка сервера ---${NC}"
    echo ""
    echo -e "${RED}⚠️  ВСЕ соединения будут разорваны!${NC}"
    echo -e "${CYAN}После перезагрузки сервер поднимется через 30-60 секунд.${NC}"
    echo ""
    read -p "Перезагрузить сейчас? (y/n): " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Перезагрузка через 5 секунд...${NC}"
        sleep 5
        reboot
    fi
}

server_shutdown() {
    header
    echo -e "${YELLOW}--- 🛑 Выключение сервера ---${NC}"
    echo ""
    echo -e "${RED}⚠️  Сервер выключится! Включить можно только через панель хостера.${NC}"
    echo ""
    read -p "Выключить сейчас? (y/n): " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Выключение через 5 секунд...${NC}"
        sleep 5
        shutdown -h now
    fi
}

monitoring_htop() {
    header
    echo -e "${YELLOW}--- 📊 Мониторинг ресурсов ---${NC}"
    echo ""

    if ! command -v htop &>/dev/null; then
        echo -e "${CYAN}htop не установлен. Устанавливаем...${NC}"
        apt update -qq 2>/dev/null
        apt install -y htop 2>/dev/null
    fi

    if command -v htop &>/dev/null; then
        echo -e "${CYAN}Запуск htop (выход — клавиша Q)...${NC}"
        sleep 1
        htop
    else
        echo -e "${YELLOW}htop не установлен. Показываем top (5 сек)...${NC}"
        sleep 1
        top -b -n 1 | head -20
        echo ""
        read -p "Enter..."
    fi
}

# ──────────────────────────────────────────────────────────────
# ГЛАВНОЕ МЕНЮ
# ──────────────────────────────────────────────────────────────
menu_sec() {
    while true; do
        header
        echo -e "${YELLOW}🛡️  БЕЗОПАСНОСТЬ, СИСТЕМА И ОПТИМИЗАЦИЯ${NC}"
        echo ""

        # Статусы
        local upgradable=$(apt list --upgradable 2>/dev/null | grep -c upgradable)
        [ "$upgradable" -gt 0 ] && US="${YELLOW}$upgradable обновлений${NC}" || US="${GREEN}Актуальна${NC}"
        echo -e " Обновление системы : $US"

        if grep -q "net.ipv6.conf.all.disable_ipv6 = 1" /etc/sysctl.conf 2>/dev/null; then
            echo -e " IPv6               : ${RED}🔴 Отключён${NC}"
        else
            echo -e " IPv6               : ${GREEN}🟢 Включён${NC}"
        fi

        if ufw status 2>/dev/null | grep -q "Status: active"; then
            local rules=$(ufw status numbered 2>/dev/null | grep -c '^\[')
            echo -e " UFW Firewall       : ${GREEN}🟢 Активен ($rules правил)${NC}"
        else
            echo -e " UFW Firewall       : ${RED}🔴 Выключен${NC}"
        fi

        if systemctl is-active --quiet fail2ban 2>/dev/null; then
            local banned=$(fail2ban-client status sshd 2>/dev/null | grep -oP 'Currently banned:\s*\K[0-9]+')
            echo -e " Fail2ban           : ${GREEN}🟢 Активен (${banned:-0} в бане)${NC}"
        else
            echo -e " Fail2ban           : ${RED}🔴 Выключен${NC}"
        fi

        if sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
            echo -e " TCP BBR            : ${GREEN}🟢 Включён${NC}"
        else
            echo -e " TCP BBR            : ${RED}🔴 Выключен (Cubic)${NC}"
        fi

        if grep -q "net.core.rmem_max" /etc/sysctl.conf 2>/dev/null; then
            echo -e " Буферы ядра        : ${GREEN}🟢 Оптимизированы${NC}"
        else
            echo -e " Буферы ядра        : ${RED}🔴 Стандартные${NC}"
        fi

        echo ""
        echo -e "${CYAN}─── 🖥️  Система ───${NC}"
        echo -e " 1) 🔄 Обновить систему"
        echo -e " 2) 🕒 Изменить часовой пояс"
        echo -e " 3) 🌐 Изменить DNS-серверы"
        echo -e " 4) 🧹 Очистка системы"
        echo -e " 5) 💽 Информация о дисках"
        echo ""
        echo -e "${CYAN}─── 🛡️  Безопасность ───${NC}"
        echo -e " 6) 🧱 UFW Firewall (управление)"
        echo -e " 7) 🛡️  Fail2ban (статус, логи, разбан)"
        echo -e " 8) 🔑 Сменить пароль root"
        echo -e " 9) 🔐 Сменить порт SSH"
        echo ""
        echo -e "${CYAN}─── ⚡ Оптимизация ───${NC}"
        echo -e " 10) 🟢 Отключить / Включить IPv6"
        echo -e " 11) 🚀 Включить / Выключить TCP BBR"
        echo -e " 12) ⚡ Оптимизировать буферы ядра"
        echo -e " 13) 💾 Создать / пересоздать swap"
        echo ""
        echo -e "${CYAN}─── 🔄 Управление ───${NC}"
        echo -e " 14) 📊 Мониторинг (htop)"
        echo -e " 15) 🔄 Перезагрузка сервера"
        echo -e " 16) 🛑 Выключение сервера"
        echo ""
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите раздел [0-16]: " sec_choice

        case $sec_choice in
            1) system_update ;;
            2) change_timezone ;;
            3) change_dns ;;
            4) cleanup_system ;;
            5) disk_info ;;
            6) ufw_manage ;;
            7) fail2ban_manage ;;
            8) change_root_password ;;
            9) change_ssh_port ;;
            10) toggle_ipv6 ;;
            11) toggle_bbr ;;
            12) optimize_udp_tm ;;
            13) create_swap ;;
            14) monitoring_htop ;;
            15) server_reboot ;;
            16) server_shutdown ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
