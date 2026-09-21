#!/bin/bash

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
    local active_ips=$(ss -H -tn state established 2>/dev/null | awk '{print $4}' | cut -d: -f1 | grep -vE "^(127\.|0\.|10\.|192\.168\.|172\.)" | sort -u)
    
    if [ -z "$active_ips" ]; then
        echo "0 0 0"
        return
    fi

    local count_udp=0
    local count_ws=0
    local count_white=0

    local user_ips_udp=$(journalctl -u udp-custom --no-pager -n 100 2>/dev/null | grep "$u" | grep -oE "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b" | sort -u)
    for ip in $user_ips_udp; do
        if echo "$active_ips" | grep -qx "$ip"; then
            ((count_udp++))
        fi
    done

    local user_ips_ws=$(journalctl -u ssh -u ws-proxy --no-pager -n 100 2>/dev/null | grep "$u" | grep -oE "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b" | sort -u)
    for ip in $user_ips_ws; do
        if echo "$active_ips" | grep -qx "$ip"; then
            ((count_ws++))
        fi
    done

    local user_ips_white=$(journalctl -u masterdnsvpn --no-pager -n 100 2>/dev/null | grep "$u" | grep -oE "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b" | sort -u)
    for ip in $user_ips_white; do
        if echo "$active_ips" | grep -qx "$ip"; then
            ((count_white++))
        fi
    done

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
