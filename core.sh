cat << 'SCRIPT_EOF' > /usr/local/bin/vpn
#!/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "Ошибка: запустите скрипт от root (sudo -i)"
  exit 1
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

DOT_ON="${GREEN}🟢 Активен${NC}"
DOT_OFF="${RED}🔴 Неактивен${NC}"
USER_ON="Активен"
USER_LOCK="Заблокирован"

DB_USERS="/etc/UDPCustom/users.db"
LIMITS_DIR="/etc/UDPCustom/limits"
mkdir -p /etc/UDPCustom "$LIMITS_DIR"
touch "$DB_USERS"

get_service_status() {
    if systemctl is-active --quiet "$1" 2>/dev/null; then
        echo -e "$DOT_ON"
    else
        echo -e "$DOT_OFF"
    fi
}

get_ufw_status() {
    if ufw status 2>/dev/null | grep -q "Status: active"; then
        echo -e "$DOT_ON"
    else
        echo -e "$DOT_OFF"
    fi
}

get_bbr_status() {
    if sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
        echo -e "${GREEN}🟢 Включен (BBR)${NC}"
    else
        echo -e "${RED}🔴 Выключен (Cubic)${NC}"
    fi
}

get_ipv6_status() {
    if grep -q "net.ipv6.conf.all.disable_ipv6 = 1" /etc/sysctl.conf 2>/dev/null; then
        echo -e "${GREEN}🟢 Отключен${NC}"
    else
        echo -e "${RED}🔴 Включен${NC}"
    fi
}

get_udp_opt_status() {
    if grep -q "net.core.rmem_max" /etc/sysctl.conf 2>/dev/null; then
        echo -e "${GREEN}🟢 Оптимизировано${NC}"
    else
        echo -e "${RED}🔴 Стандарт${NC}"
    fi
}

get_ws_port() {
    if [ -f /usr/local/bin/ws-proxy.py ]; then
        local p=$(awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py | tr -dc '0-9')
        if [ -n "$p" ]; then
            echo "$p"
        else
            echo "Не установлен"
        fi
    else
        echo "Не установлен"
    fi
}

header() {
    clear
    local CPU=$(cat /proc/loadavg | awk '{print $1}')
    local RAM=$(free -m | awk 'NR==2{printf "%s/%sMB (%s%%)", $3,$2,int($3*100/$2)}')
    local DISK=$(df -h / | awk '$NF=="/"{printf "%s/%s (%s)", $3,$2,$5}')
    
    local ws_p=$(get_ws_port)
    local ws_filter=""
    if [[ "$ws_p" =~ ^[0-9]+$ ]]; then
        ws_filter="or dport = :$ws_p or sport = :$ws_p"
    fi
    local ONLINE=$(ss -H -tn state established "( dport = :36712 or sport = :36712 or dport = :7300 or sport = :7300 $ws_filter )" 2>/dev/null | awk '{print $4}' | cut -d: -f1 | grep -vE "^(127\.|0\.|10\.|192\.168\.|172\.)" | sort -u | wc -l)

    echo -e "${CYAN}==============================================${NC}"
    echo -e "        ${YELLOW}⚡ ULTIMATE VPN CONTROL PANEL ⚡${NC}"
    echo -e "${CYAN}==============================================${NC}"
    echo -e " 🖥️  CPU Нагрузка : ${GREEN}$CPU${NC}"
    echo -e " 💾 RAM Память   : ${GREEN}$RAM${NC}"
    echo -e " 💽 Диск (Root)  : ${GREEN}$DISK${NC}"
    echo -e " 🌐 Активн. сесс.: ${GREEN}$ONLINE${NC}"
    echo -e "${CYAN}==============================================${NC}"
}

get_user_connections() {
    local u="$1"
    local count_udp=0
    local count_ws=0
    local count_white=0

    # Проверяем активные сессии пользователя через систему процессов и открытых сокетов
    if pgrep -u "$u" >/dev/null 2>&1 || who | grep -q "$u"; then
        if systemctl is-active --quiet masterdnsvpn; then
            count_white=1
        elif [ -f /usr/local/bin/ws-proxy.py ] && systemctl is-active --quiet ws-proxy; then
            count_ws=1
        else
            count_udp=1
        fi
    fi

    echo "$count_udp $count_ws $count_white"
}

select_user() {
    header
    echo -e "${YELLOW}--- $1 ---${NC}"
    
    if [ ! -s "$DB_USERS" ]; then
        echo -e "${MAGENTA}Список пользователей пуст.${NC}"
        echo ""
        read -p "Нажмите Enter для возврата..."
        return 1
    fi

    USER_LIST=()
    local i=1
    printf "${BLUE}%-3s %-10s %-11s %-4s %-4s %-4s %-6s %-10s${NC}\n" "№" "Логин" "Срок" "UDP" "WS" "Wh" "Лимит" "Статус"
    echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"

    while read -r u; do
        [ -z "$u" ] && continue
        if id "$u" &>/dev/null; then
            USER_LIST+=("$u")
            exp=$(chage -l "$u" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
            [ "$exp" == "never" ] && exp="Бессрочно"
            
            local user_limit=3
            [ -f "$LIMITS_DIR/$u" ] && user_limit=$(cat "$LIMITS_DIR/$u")

            read c_udp c_ws c_white <<< $(get_user_connections "$u")

            if passwd -S "$u" 2>/dev/null | grep -q " L "; then
                status_str="${RED}${USER_LOCK}${NC}"
            else
                status_str="${GREEN}${USER_ON}${NC}"
            fi

            printf "%-3s %-10s %-11s %-4s %-4s %-4s %-6s %-12b\n" "$i)" "$u" "$exp" "$c_udp" "$c_ws" "$c_white" "$user_limit" "$status_str"
            ((i++))
        fi
    done < "$DB_USERS"

    if [ ${#USER_LIST[@]} -eq 0 ]; then
        echo -e "${MAGENTA}Нет активных пользователей.${NC}"
        read -p "Нажмите Enter для возврата..."
        return 1
    fi

    echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
    echo -e " 0) ↩️  Отмена"
    echo ""
    read -p "Выберите номер [1-${#USER_LIST[@]}]: " user_idx

    if [[ "$user_idx" == "0" || -z "$user_idx" ]]; then
        return 1
    fi

    if ! [[ "$user_idx" =~ ^[0-9]+$ ]] || [ "$user_idx" -lt 1 ] || [ "$user_idx" -gt "${#USER_LIST[@]}" ]; then
        echo -e "${RED}Неверный номер.${NC}"
        sleep 1
        return 1
    fi

    SELECTED_USER="${USER_LIST[$((user_idx-1))]}"
    return 0
}

add_user() {
    header
    echo -e "${YELLOW}--- 👤 Создание нового пользователя ---${NC}"
    read -p "Логин: " username
    [ -z "$username" ] && { echo -e "${RED}Логин не может быть пустым.${NC}"; sleep 1; return; }

    if id "$username" &>/dev/null; then
        echo -e "${RED}Пользователь '$username' уже существует!${NC}"
        read -p "Нажмите Enter для возврата..."
        return
    fi

    read -p "Пароль: " password
    [ -z "$password" ] && { echo -e "${RED}Пароль не может быть пустым.${NC}"; sleep 1; return; }

    read -p "Срок в днях (Enter = бессрочно): " days
    read -p "Лимит устройств (Enter = по умолчанию 3): " max_devices
    if ! [[ "$max_devices" =~ ^[0-9]+$ ]] || [ "$max_devices" -lt 1 ]; then
        max_devices=3
    fi

    useradd -M -s /bin/false "$username"
    echo "$username:$password" | chpasswd

    echo "$username" >> "$DB_USERS"
    sort -u -o "$DB_USERS" "$DB_USERS"
    echo "$max_devices" > "$LIMITS_DIR/$username"

    if [ -n "$days" ] && [ "$days" -gt 0 ] 2>/dev/null; then
        exp_date=$(date -d "+$days days" +%Y-%m-%d)
        chage -E "$exp_date" "$username"
        exp_info="$exp_date"
    else
        exp_info="Бессрочно"
    fi

    SERVER_IP=$(curl -s4 ifconfig.me || hostname -I | awk '{print $1}')
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}         ${YELLOW}🎉 ПОЛЬЗОВАТЕЛЬ СОЗДАН 🎉${NC}          ${GREEN}║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC} Сервер : ${CYAN}$SERVER_IP${NC}"
    echo -e "${GREEN}║${NC} Логин  : ${CYAN}$username${NC}"
    echo -e "${GREEN}║${NC} Пароль : ${CYAN}$password${NC}"
    echo -e "${GREEN}║${NC} Срок   : ${CYAN}$exp_info${NC}"
    echo -e "${GREEN}║${NC} Лимит  : ${CYAN}Макс. $max_devices устройства${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    echo ""
    read -p "Нажмите Enter для продолжения..."
}

delete_user() {
    select_user "🗑️  Удаление пользователя" || return
    echo ""
    read -p "Удалить пользователя '$SELECTED_USER'? (y/n): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        userdel -f "$SELECTED_USER" 2>/dev/null
        sed -i "/^${SELECTED_USER}$/d" "$DB_USERS" 2>/dev/null
        rm -f "$LIMITS_DIR/$SELECTED_USER" 2>/dev/null
        echo -e "${GREEN}Пользователь '$SELECTED_USER' удален!${NC}"
    else
        echo -e "${YELLOW}Удаление отменено.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

change_password() {
    select_user "🔑 Смена пароля" || return
    echo ""
    read -p "Новый пароль для '$SELECTED_USER': " password
    [ -z "$password" ] && { echo -e "${RED}Пароль не может быть пустым.${NC}"; sleep 1; return; }

    echo "$SELECTED_USER:$password" | chpasswd
    echo -e "${GREEN}Пароль для '$SELECTED_USER' обновлен!${NC}"
    read -p "Нажмите Enter для продолжения..."
}

change_user_limit() {
    select_user "⚙️ Изменение лимита устройств" || return
    echo ""
    local current_limit=3
    [ -f "$LIMITS_DIR/$SELECTED_USER" ] && current_limit=$(cat "$LIMITS_DIR/$SELECTED_USER")
    echo -e "Текущий лимит для '${GREEN}$SELECTED_USER${NC}': ${YELLOW}$current_limit${NC}"
    read -p "Введите новый лимит устройств (1-99): " new_limit
    if [[ "$new_limit" =~ ^[0-9]+$ ]] && [ "$new_limit" -ge 1 ]; then
        echo "$new_limit" > "$LIMITS_DIR/$SELECTED_USER"
        echo -e "${GREEN}Лимит устройств для '$SELECTED_USER' успешно изменен на $new_limit!${NC}"
    else
        echo -e "${RED}Неверный формат числа.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

toggle_lock() {
    select_user "🔒 Блокировка / Разблокировка" || return
    echo ""
    if passwd -S "$SELECTED_USER" 2>/dev/null | grep -q " L "; then
        usermod -U "$SELECTED_USER"
        echo -e "${GREEN}Пользователь '$SELECTED_USER' разблокирован!${NC}"
    else
        usermod -L "$SELECTED_USER"
        echo -e "${YELLOW}Пользователь '$SELECTED_USER' заблокирован!${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

renew_user() {
    select_user "⏳ Продление срока действия" || return
    echo ""
    read -p "Добавить дней (0 = сделать бессрочным): " days

    if [ "$days" -eq 0 ] 2>/dev/null; then
        chage -E -1 "$SELECTED_USER"
        echo -e "${GREEN}Срок действия для '$SELECTED_USER': бессрочно.${NC}"
    elif [ "$days" -gt 0 ] 2>/dev/null; then
        exp_date=$(date -d "+$days days" +%Y-%m-%d)
        chage -E "$exp_date" "$SELECTED_USER"
        echo -e "${GREEN}Срок для '$SELECTED_USER' продлен до $exp_date.${NC}"
    else
        echo -e "${RED}Неверное число дней.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

client_statistics() {
    select_user "📊 Статистика и устройства клиента" || return
    header
    echo -e "${YELLOW}--- 📊 Клиент: $SELECTED_USER ---${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    
    local exp=$(chage -l "$SELECTED_USER" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
    [ "$exp" == "never" ] && exp="Бессрочно"
    
    if passwd -S "$SELECTED_USER" 2>/dev/null | grep -q " L "; then
        status_str="${RED}${USER_LOCK}${NC}"
    else
        status_str="${GREEN}${USER_ON}${NC}"
    fi

    local user_limit=3
    [ -f "$LIMITS_DIR/$SELECTED_USER" ] && user_limit=$(cat "$LIMITS_DIR/$SELECTED_USER")

    read count_udp count_ws count_white <<< $(get_user_connections "$SELECTED_USER")
    local total_count=$((count_udp + count_ws + count_white))
    
    echo -e " 👤 Логин аккаунта : ${GREEN}$SELECTED_USER${NC}"
    echo -e " 📅 Срок действия  : ${CYAN}$exp${NC}"
    echo -e " 🔒 Статус учетки  : $status_str"
    echo -e " ⚙️  Лимит устройств : ${CYAN}$user_limit${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo -e " ⚡ UDP Custom активных : ${GREEN}$count_udp${NC}"
    echo -e " 🕸️ SSH WS активных    : ${GREEN}$count_ws${NC}"
    echo -e " 🌐 White активных     : ${GREEN}$count_white${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    
    if [ "$total_count" -gt "$user_limit" ]; then
        echo -e " 📱 Всего устройств: ${RED}$total_count / $user_limit (ПРЕВЫШЕН ЛИМИТ!)${NC}"
    else
        echo -e " 📱 Всего устройств: ${GREEN}$total_count / $user_limit${NC}"
    fi
    
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    read -p "Нажмите Enter для возврата..."
}

list_users() {
    header
    echo -e "${YELLOW}--- 📋 Список всех пользователей ---${NC}"

    if [ ! -s "$DB_USERS" ]; then
        echo -e "${MAGENTA}Список пуст. Вы еще не создавали пользователей.${NC}"
        echo ""
        read -p "Нажмите Enter для продолжения..."
        return
    fi

    printf "${BLUE}%-3s %-10s %-11s %-4s %-4s %-4s %-6s %-10s${NC}\n" "№" "Логин" "Срок" "UDP" "WS" "Wh" "Лимит" "Статус"
    echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"

    local i=1
    while read -r u; do
        [ -z "$u" ] && continue
        if id "$u" &>/dev/null; then
            exp=$(chage -l "$u" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
            [ "$exp" == "never" ] && exp="Бессрочно"
            
            local user_limit=3
            [ -f "$LIMITS_DIR/$u" ] && user_limit=$(cat "$LIMITS_DIR/$u")

            read c_udp c_ws c_white <<< $(get_user_connections "$u")

            if passwd -S "$u" 2>/dev/null | grep -q " L "; then
                status_str="${RED}${USER_LOCK}${NC}"
            else
                status_str="${GREEN}${USER_ON}${NC}"
            fi

            printf "%-3s %-10s %-11s %-4s %-4s %-4s %-6s %-12b\n" "$i)" "$u" "$exp" "$c_udp" "$c_ws" "$c_white" "$user_limit" "$status_str"
            ((i++))
        fi
    done < "$DB_USERS"

    echo ""
    read -p "Нажмите Enter для продолжения..."
}

menu_users() {
    while true; do
        header
        echo -e "${YELLOW}👥 УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ${NC}"
        echo ""
        echo -e " 1) ➕ Добавить пользователя"
        echo -e " 2) 📋 Список пользователей"
        echo -e " 3) 🔑 Изменить пароль"
        echo -e " 4) ⏳ Продлить срок"
        echo -e " 5) 🔒 Блок / Разблок"
        echo -e " 6) 🗑️  Удалить пользователя"
        echo -e " 7) 📊 Статистика и устройства клиента"
        echo -e " 8) ⚙️ Изменить лимит устройств"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-8]: " uchoice
        case $uchoice in
            1) add_user ;;
            2) list_users ;;
            3) change_password ;;
            4) renew_user ;;
            5) toggle_lock ;;
            6) delete_user ;;
            7) client_statistics ;;
            8) change_user_limit ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

menu_masterdns() {
    while true; do
        header
        echo -e "${YELLOW}🌐 УПРАВЛЕНИЕ MASTERDNSVPN${NC}"
        echo -e " Статус службы : $(get_service_status masterdnsvpn)"
        echo ""
        echo -e " 1) ⚡ Установить / Обновить MasterDnsVPN"
        echo -e " 2) 🔄 Перезапустить MasterDnsVPN"
        echo -e " 3) 🛑 Остановить MasterDnsVPN"
        echo -e " 4) ⚙️  Редактировать конфигурацию (/root/server_config.toml)"
        echo -e " 5) 🗑️  Удалить MasterDnsVPN"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-5]: " mds_choice
        case $mds_choice in
            1)
                bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh)
                read -p "Нажмите Enter..."
                ;;
            2)
                systemctl restart masterdnsvpn
                echo -e "${GREEN}MasterDnsVPN перезапущен!${NC}"
                sleep 1
                ;;
            3)
                systemctl stop masterdnsvpn
                echo -e "${YELLOW}MasterDnsVPN остановлен!${NC}"
                sleep 1
                ;;
            4)
                if [ -f /root/server_config.toml ]; then
                    nano /root/server_config.toml
                else
                    echo -e "${RED}Файл /root/server_config.toml не найден!${NC}"
                    sleep 2
                fi
                ;;
            5)
                read -p "Точно удалить MasterDnsVPN? (y/n): " confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    systemctl stop masterdnsvpn 2>/dev/null
                    bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh) --uninstall
                    echo -e "${GREEN}Удалено.${NC}"
                fi
                sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

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

install_ws() {
    header
    echo -e "${YELLOW}--- 🕸️ Установка WebSocket Proxy ---${NC}"
    apt update -y && apt install -y python3 ufw

    read -p "Введите порт для WebSocket (по умолчанию 80): " ws_port
    if ! [[ "$ws_port" =~ ^[0-9]+$ ]] || [ "$ws_port" -lt 1 ] || [ "$ws_port" -gt 65535 ]; then
        ws_port=80
        echo -e "${CYAN}Используется порт по умолчанию: 80${NC}"
    fi

    cat << PY_EOF > /usr/local/bin/ws-proxy.py
import socket, threading

def handle_connection(client_socket):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.connect(('127.0.0.1', 22))
        initial_data = client_socket.recv(8192)
        if b"HTTP" in initial_data:
            response = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n"
            client_socket.send(response)
        else:
            server_socket.send(initial_data)

        def forward(src, dst):
            try:
                while True:
                    data = src.recv(8192)
                    if not data: break
                    dst.send(data)
            except: pass
            finally:
                src.close()
                dst.close()

        threading.Thread(target=forward, args=(client_socket, server_socket)).start()
        threading.Thread(target=forward, args=(server_socket, client_socket)).start()
    except:
        client_socket.close()

def main():
    listen_port = $ws_port
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', listen_port))
    server.listen(100)
    while True:
        client_socket, addr = server.accept()
        threading.Thread(target=handle_connection, args=(client_socket,)).start()

if __name__ == '__main__':
    main()
PY_EOF

    chmod +x /usr/local/bin/ws-proxy.py

    cat << 'WS_SVC_EOF' > /etc/systemd/system/ws-proxy.service
[Unit]
Description=WebSocket Proxy Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /usr/local/bin/ws-proxy.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
WS_SVC_EOF

    systemctl daemon-reload
    systemctl enable ws-proxy
    systemctl restart ws-proxy
    ufw allow $ws_port/tcp comment 'WebSocket Proxy Port' 2>/dev/null

    echo -e "${GREEN}WebSocket Proxy успешно запущен на порту $ws_port!${NC}"
    read -p "Нажмите Enter для продолжения..."
}

change_ws_port() {
    header
    echo -e "${YELLOW}--- ⚙️ Смена порта WebSocket Proxy ---${NC}"
    local old_port=$(get_ws_port)
    if [[ "$old_port" == "Не установлен" ]]; then
        echo -e "${RED}Служба не установлена! Сначала установите её (пункт 1).${NC}"
        read -p "Нажмите Enter..."
        return
    fi
    
    echo -e "Текущий порт: ${GREEN}$old_port${NC}"
    read -p "Введите новый порт (1-65535): " new_port
    
    if [[ "$new_port" =~ ^[0-9]+$ ]] && [ "$new_port" -ge 1 ] && [ "$new_port" -le 65535 ]; then
        ufw delete allow $old_port/tcp 2>/dev/null
        sed -i "s/listen_port[[:space:]]*=[[:space:]]*[0-9]*/listen_port = $new_port/" /usr/local/bin/ws-proxy.py
        ufw allow $new_port/tcp comment 'WebSocket Proxy Port' 2>/dev/null
        systemctl restart ws-proxy
        echo -e "${GREEN}Порт успешно изменен на $new_port! Служба перезапущена.${NC}"
    else
        echo -e "${RED}Неверный формат порта.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

menu_ws() {
    while true; do
        header
        local cur_port=$(get_ws_port)
        
        echo -e "${YELLOW}🕸️  МОДУЛЬ WEBSOCKET PROXY (ОБХОД DPI)${NC}"
        echo -e " WS Proxy : $(get_service_status ws-proxy)"
        echo -e " Порт     : ${GREEN}${cur_port} (TCP)${NC}"
        echo ""
        echo -e " 1) ⚡ Установить / Запустить WebSocket Proxy"
        echo -e " 2) 🔄 Перезапустить"
        echo -e " 3) ⏸️  Остановить"
        echo -e " 4) ⚙️  Изменить порт WS"
        echo -e " 5) 📜 Посмотреть логи работы"
        echo -e " 6) 🗑️  Удалить с сервера"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-6]: " ws_choice
        case $ws_choice in
            1) install_ws ;;
            2) systemctl restart ws-proxy; echo -e "${GREEN}Перезапущено.${NC}"; sleep 1 ;;
            3) systemctl stop ws-proxy; echo -e "${YELLOW}Остановлено.${NC}"; sleep 1 ;;
            4) change_ws_port ;;
            5) header; journalctl -u ws-proxy -n 25 --no-pager; echo ""; read -p "Enter..." ;;
            6) 
                local dp=$(get_ws_port)
                systemctl stop ws-proxy 2>/dev/null
                systemctl disable ws-proxy 2>/dev/null
                [[ "$dp" != "Не установлен" ]] && ufw delete allow $dp/tcp 2>/dev/null
                rm -f /etc/systemd/system/ws-proxy.service /usr/local/bin/ws-proxy.py
                echo -e "${GREEN}Удалено.${NC}"; sleep 1 ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

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

while true; do
    header
    echo -e " MasterDnsVPN : $(get_service_status masterdnsvpn)"
    echo -e " UDP-Custom   : $(get_service_status udp-custom)"
    echo -e " WS Proxy     : $(get_service_status ws-proxy)"
    echo -e " Firewall     : $(get_ufw_status)"
    echo -e " IPv6         : $(get_ipv6_status)"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo -e " 1) 👥 Управление пользователями"
    echo -e " 2) 🌐 MasterDnsVPN"
    echo -e " 3) ⚡ UDP Custom (Управление)"
    echo -e " 4) 🕸️  WebSocket Proxy (Кастомный)"
    echo -e " 5) 🛡️  Безопасность, IPv6 и Оптимизация"
    echo -e " 0) 🚪 Выход"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    read -p "Выберите раздел [0-5]: " main_choice

    case $main_choice in
        1) menu_users ;;
        2) menu_masterdns ;;
        3) menu_service ;;
        4) menu_ws ;;
        5) menu_sec ;;
        0) clear; exit 0 ;;
        *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
    esac
done
SCRIPT_EOF

chmod +x /usr/local/bin/vpn
