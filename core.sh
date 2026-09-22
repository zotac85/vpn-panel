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

declare -gA SESS_SSH_BY_USER
declare -gA SESS_WS_BY_USER
SESS_SSH_TOTAL=0
SESS_WS_TOTAL=0
SESS_BUILT=0

get_ssh_ports_filter() {
    local ws_p=$(get_ws_port)
    local filter="( sport = :22 or sport = :36712 or sport = :7300"
    if [[ "$ws_p" =~ ^[0-9]+$ ]]; then
        filter="$filter or sport = :$ws_p"
    fi
    filter="$filter )"
    echo "$filter"
}

build_session_stats() {
    SESS_SSH_BY_USER=()
    SESS_WS_BY_USER=()
    SESS_SSH_TOTAL=0
    SESS_WS_TOTAL=0

    local filter
    filter=$(get_ssh_ports_filter)

    local data
    data=$(ss -H -tnp state established "$filter" 2>/dev/null)

    while IFS= read -r line; do
        [ -z "$line" ] && continue
        local head peer
        head="${line%%users:(*}"
        peer=$(echo "$head" | awk '{print $NF}')
        [[ "$peer" == *:* ]] || continue

        local pids p owner u
        pids=$(echo "$line" | grep -oP 'pid=\K[0-9]+')
        u=""
        for p in $pids; do
            owner=$(ps -o user= -p "$p" 2>/dev/null | tr -d ' ')
            if [ -n "$owner" ] && [ "$owner" != "root" ]; then
                u="$owner"
                break
            fi
        done
        [ -z "$u" ] && continue

        if [[ "$peer" == 127.0.0.1:* || "$peer" == \[::1\]:* ]]; then
            SESS_WS_BY_USER["$u"]=$(( ${SESS_WS_BY_USER["$u"]:-0} + 1 ))
            ((SESS_WS_TOTAL++))
        else
            SESS_SSH_BY_USER["$u"]=$(( ${SESS_SSH_BY_USER["$u"]:-0} + 1 ))
            ((SESS_SSH_TOTAL++))
        fi
    done <<< "$data"

    SESS_BUILT=1
}

get_user_connections() {
    local u="$1"

    if [ "$SESS_BUILT" -ne 1 ]; then
        build_session_stats
    fi

    local count_ssh=${SESS_SSH_BY_USER["$u"]:-0}
    local count_ws=${SESS_WS_BY_USER["$u"]:-0}
    local count_white=0

    if systemctl is-active --quiet masterdnsvpn 2>/dev/null; then
        if pgrep -u "$u" -f masterdns &>/dev/null; then
            count_white=1
        fi
    fi

    echo "$count_ssh $count_ws $count_white"
}

header() {
    printf '\033[2J\033[3J\033[H'
    local CPU=$(cat /proc/loadavg | awk '{print $1}')
    local RAM=$(free -m | awk 'NR==2{printf "%s/%sMB (%s%%)", $3,$2,int($3*100/$2)}')
    local DISK=$(df -h / | awk '$NF=="/"{printf "%s/%s (%s)", $3,$2,$5}')

    build_session_stats

    echo -e "${CYAN}==============================================${NC}"
    echo -e "        ${YELLOW}⚡ ULTIMATE VPN CONTROL PANEL ⚡${NC}"
    echo -e "${CYAN}==============================================${NC}"
    echo -e " 🖥️  CPU Нагрузка : ${GREEN}$CPU${NC}"
    echo -e " 💾 RAM Память   : ${GREEN}$RAM${NC}"
    echo -e " 💽 Диск (Root)  : ${GREEN}$DISK${NC}"
    echo -e " 🔑 SSH онлайн   : ${GREEN}${SESS_SSH_TOTAL}${NC}"
    echo -e " 🕸️  WS онлайн    : ${GREEN}${SESS_WS_TOTAL}${NC}"
    echo -e "${CYAN}==============================================${NC}"
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

    build_session_stats

    USER_LIST=()
    local i=1
    printf "${BLUE}%-3s %-10s %-11s %-4s %-4s %-4s %-6s %-10s${NC}\n" "№" "Логин" "Срок" "SSH" "WS" "Wh" "Лимит" "Статус"
    echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"

    while read -r u; do
        [ -z "$u" ] && continue
        if id "$u" &>/dev/null; then
            USER_LIST+=("$u")
            exp=$(chage -l "$u" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
            [ "$exp" == "never" ] && exp="Бессрочно"

            local user_limit=3
            [ -f "$LIMITS_DIR/$u" ] && user_limit=$(cat "$LIMITS_DIR/$u")

            read c_ssh c_ws c_white <<< $(get_user_connections "$u")

            if passwd -S "$u" 2>/dev/null | grep -q " L "; then
                status_str="${RED}${USER_LOCK}${NC}"
            else
                status_str="${GREEN}${USER_ON}${NC}"
            fi

            printf "%-3s %-10s %-11s %-4s %-4s %-4s %-6s %-12b\n" "$i)" "$u" "$exp" "$c_ssh" "$c_ws" "$c_white" "$user_limit" "$status_str"
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
