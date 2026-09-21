#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ ПРИНУДИТЕЛЬНОГО КОНТРОЛЯ ЛИМИТА УСТРОЙСТВ
#
# Логика проверки (cron, раз в минуту):
#  - собираем ESTABLISHED-сессии sshd (те же порты, что в core.sh);
#  - группируем PID'ы подключений по владельцу;
#  - если у юзера подключений больше, чем LIMITS_DIR/<user> —
#    сортируем по времени старта процесса и убиваем САМЫЕ НОВЫЕ
#    подключения сверх лимита. Старые сессии не трогаем.
# ──────────────────────────────────────────────────────────────

LIMIT_CHECK_SCRIPT="/usr/local/bin/vpn-limit-check.sh"
LIMIT_CRON="/etc/cron.d/vpn-device-limit"
LIMIT_LOG="/var/log/vpn-limit-check.log"

limit_enforcement_active() {
    [ -f "$LIMIT_CRON" ]
}

# ── ТИХАЯ ВЕРСИЯ (для автовключения из install.sh или панели) ──
install_limit_enforcement_quiet() {
    cat << 'CHK_EOF' > "$LIMIT_CHECK_SCRIPT"
#!/bin/bash
DB_USERS="/etc/UDPCustom/users.db"
LIMITS_DIR="/etc/UDPCustom/limits"
LOG_FILE="/var/log/vpn-limit-check.log"

get_ws_port() {
    if [ -f /usr/local/bin/ws-proxy.py ]; then
        awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py | tr -dc '0-9'
    fi
}

ws_p=$(get_ws_port)
filter="( sport = :22 or sport = :36712 or sport = :7300"
[[ "$ws_p" =~ ^[0-9]+$ ]] && filter="$filter or sport = :$ws_p"
filter="$filter )"

data=$(ss -H -tnp state established "$filter" 2>/dev/null)

declare -A CONN_USER CONN_PIDS CONN_TIME
idx=0
while IFS= read -r line; do
    [ -z "$line" ] && continue
    head="${line%%users:(*}"
    peer=$(echo "$head" | awk '{print $NF}')
    [[ "$peer" == *:* ]] || continue
    pids=$(echo "$line" | grep -oP 'pid=\K[0-9]+')
    [ -z "$pids" ] && continue
    u=""
    for p in $pids; do
        owner=$(ps -o user= -p "$p" 2>/dev/null | tr -d ' ')
        if [ -n "$owner" ] && [ "$owner" != "root" ]; then u="$owner"; break; fi
    done
    [ -z "$u" ] && continue
    reftime=0
    for p in $pids; do
        t=$(stat -c %Y "/proc/$p" 2>/dev/null)
        [ -n "$t" ] && { reftime=$t; break; }
    done
    CONN_USER[$idx]="$u"; CONN_PIDS[$idx]="$pids"; CONN_TIME[$idx]="$reftime"
    ((idx++))
done <<< "$data"

declare -A USER_INDICES
for ((i=0; i<idx; i++)); do
    u="${CONN_USER[$i]}"
    USER_INDICES[$u]="${USER_INDICES[$u]} $i"
done

for u in "${!USER_INDICES[@]}"; do
    limit=3
    [ -f "$LIMITS_DIR/$u" ] && limit=$(cat "$LIMITS_DIR/$u")
    [[ "$limit" =~ ^[0-9]+$ ]] || limit=3
    [ "$limit" -le 0 ] && continue
    idxs=(${USER_INDICES[$u]}); count=${#idxs[@]}
    [ "$count" -le "$limit" ] && continue
    sorted_idxs=($(for i in "${idxs[@]}"; do echo "${CONN_TIME[$i]} $i"; done | sort -n | awk '{print $2}'))
    to_kill=$(( count - limit ))
    for ((k=count-to_kill; k<count; k++)); do
        conn_i=${sorted_idxs[$k]}
        for p in ${CONN_PIDS[$conn_i]}; do kill -9 "$p" 2>/dev/null; done
        echo "$(date '+%Y-%m-%d %H:%M:%S') Отключён лишний сеанс: user=$u count=$count limit=$limit" >> "$LOG_FILE"
    done
done
CHK_EOF
    chmod +x "$LIMIT_CHECK_SCRIPT"
    echo "* * * * * root $LIMIT_CHECK_SCRIPT" > "$LIMIT_CRON"
    chmod 644 "$LIMIT_CRON"
    systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null
}

# ── ОБЫЧНАЯ ВЕРСИЯ (с UI, для ручного включения) ──
install_limit_enforcement() {
    header
    echo -e "${YELLOW}--- ⚡ Включение контроля лимита устройств ---${NC}"
    install_limit_enforcement_quiet
    echo -e "${GREEN}Контроль лимита устройств включен: проверка каждую минуту.${NC}"
    echo -e "${CYAN}Лишние (самые новые) подключения будут автоматически отключаться.${NC}"
    read -p "Нажмите Enter для продолжения..."
}

uninstall_limit_enforcement() {
    header
    echo -e "${YELLOW}--- 🗑️ Отключение контроля лимита устройств ---${NC}"
    rm -f "$LIMIT_CRON" "$LIMIT_CHECK_SCRIPT"
    echo -e "${GREEN}Контроль лимита устройств отключен.${NC}"
    read -p "Нажмите Enter для продолжения..."
}

show_limit_log() {
    header
    echo -e "${YELLOW}--- 📜 Журнал отключений за превышение лимита ---${NC}"
    if [ -f "$LIMIT_LOG" ]; then
        tail -n 30 "$LIMIT_LOG"
    else
        echo -e "${MAGENTA}Журнал пуст — отключений ещё не было.${NC}"
    fi
    echo ""
    read -p "Нажмите Enter для продолжения..."
}

menu_devicelimit() {
    while true; do
        header
        echo -e "${YELLOW}🚦 КОНТРОЛЬ ЛИМИТА УСТРОЙСТВ${NC}"
        if limit_enforcement_active; then
            echo -e " Статус: ${GREEN}🟢 Включен (авто-отключение лишних сессий)${NC}"
        else
            echo -e " Статус: ${RED}🔴 Выключен (лимит только отображается, не применяется)${NC}"
        fi
        echo ""
        echo -e " 1) ⚡ Включить авто-отключение лишних устройств"
        echo -e " 2) 📜 Журнал отключений"
        echo -e " 3) 🗑️  Отключить контроль"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-3]: " dchoice
        case $dchoice in
            1) install_limit_enforcement ;;
            2) show_limit_log ;;
            3) uninstall_limit_enforcement ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
