#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ ЛИМИТА ТРАФИКА
# (см. подробное описание в комментариях оригинала)
# ──────────────────────────────────────────────────────────────

TRAFFIC_DIR="/etc/UDPCustom/traffic"
TRAFFIC_LIMITS_DIR="/etc/UDPCustom/traffic_limits"
TRAFFIC_CHAIN="VPN_TRAFFIC"
TRAFFIC_CHECK_SCRIPT="/usr/local/bin/vpn-traffic-check.sh"
TRAFFIC_CRON="/etc/cron.d/vpn-traffic-check"

mkdir -p "$TRAFFIC_DIR" "$TRAFFIC_LIMITS_DIR"

traffic_chain_exists() {
    iptables -L "$TRAFFIC_CHAIN" -n &>/dev/null
}

init_traffic_chain() {
    iptables -N "$TRAFFIC_CHAIN" 2>/dev/null
    iptables -C OUTPUT -j "$TRAFFIC_CHAIN" 2>/dev/null || iptables -I OUTPUT -j "$TRAFFIC_CHAIN"
}

add_traffic_rule() {
    local u="$1"
    traffic_chain_exists || return
    local uid=$(id -u "$u" 2>/dev/null)
    [ -z "$uid" ] && return
    iptables -C "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || \
    iptables -A "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN
}

remove_traffic_rule() {
    local u="$1"
    traffic_chain_exists || return
    local uid=$(id -u "$u" 2>/dev/null)
    [ -z "$uid" ] && return
    while iptables -D "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN 2>/dev/null; do :; done
}

get_traffic_counter_bytes() {
    local u="$1"
    traffic_chain_exists || { echo 0; return; }
    local uid=$(id -u "$u" 2>/dev/null)
    [ -z "$uid" ] && { echo 0; return; }
    local val
    val=$(iptables -L "$TRAFFIC_CHAIN" -v -x -n 2>/dev/null | awk -v pat="UID match $uid\$" '$0 ~ pat {print $2}' | head -1)
    [ -z "$val" ] && val=0
    echo "$val"
}

human_bytes() {
    local b="$1"
    if [ "$b" -ge 1073741824 ]; then
        awk -v b="$b" 'BEGIN{printf "%.2f GB", b/1073741824}'
    elif [ "$b" -ge 1048576 ]; then
        awk -v b="$b" 'BEGIN{printf "%.2f MB", b/1048576}'
    else
        echo "${b} B"
    fi
}

get_traffic_used() {
    local u="$1"
    local f="$TRAFFIC_DIR/$u"
    [ -f "$f" ] && cat "$f" || echo 0
}

get_traffic_limit() {
    local u="$1"
    local f="$TRAFFIC_LIMITS_DIR/$u"
    [ -f "$f" ] && cat "$f" || echo 0
}

# ── ТИХАЯ ВЕРСИЯ (для автовключения из install.sh или панели) ──
install_traffic_monitor_quiet() {
    init_traffic_chain
    while read -r u; do
        [ -z "$u" ] && continue
        id "$u" &>/dev/null && add_traffic_rule "$u"
    done < "$DB_USERS"

    cat << 'CHK_EOF' > "$TRAFFIC_CHECK_SCRIPT"
#!/bin/bash
TRAFFIC_DIR="/etc/UDPCustom/traffic"
TRAFFIC_LIMITS_DIR="/etc/UDPCustom/traffic_limits"
TRAFFIC_CHAIN="VPN_TRAFFIC"
DB_USERS="/etc/UDPCustom/users.db"

mkdir -p "$TRAFFIC_DIR"
iptables -L "$TRAFFIC_CHAIN" -n &>/dev/null || exit 0

while read -r u; do
    [ -z "$u" ] && continue
    uid=$(id -u "$u" 2>/dev/null) || continue
    cur=$(iptables -L "$TRAFFIC_CHAIN" -v -x -n 2>/dev/null | awk -v pat="UID match $uid\$" '$0 ~ pat {print $2}' | head -1)
    [ -z "$cur" ] && cur=0
    total_file="$TRAFFIC_DIR/$u"
    [ -f "$total_file" ] || echo 0 > "$total_file"
    prev_total=$(cat "$total_file")
    new_total=$((prev_total + cur))
    echo "$new_total" > "$total_file"
    iptables -D "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN 2>/dev/null
    iptables -A "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN
    limit_file="$TRAFFIC_LIMITS_DIR/$u"
    if [ -f "$limit_file" ]; then
        limit_bytes=$(cat "$limit_file")
        if [[ "$limit_bytes" =~ ^[0-9]+$ ]] && [ "$limit_bytes" -gt 0 ] && [ "$new_total" -ge "$limit_bytes" ]; then
            usermod -L "$u" 2>/dev/null
        fi
    fi
done < "$DB_USERS"
CHK_EOF
    chmod +x "$TRAFFIC_CHECK_SCRIPT"
    echo "*/5 * * * * root $TRAFFIC_CHECK_SCRIPT" > "$TRAFFIC_CRON"
    chmod 644 "$TRAFFIC_CRON"
    systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null
}

# ── ОБЫЧНАЯ ВЕРСИЯ (с UI) ──
install_traffic_monitor() {
    header
    echo -e "${YELLOW}--- ⚡ Включение мониторинга трафика ---${NC}"
    install_traffic_monitor_quiet
    echo -e "${GREEN}Мониторинг трафика включен: проверка каждые 5 минут.${NC}"
    read -p "Нажмите Enter для продолжения..."
}

set_traffic_limit() {
    select_user "📶 Установка лимита трафика" || return
    echo ""
    local cur_limit=$(get_traffic_limit "$SELECTED_USER")
    if [ "$cur_limit" -gt 0 ] 2>/dev/null; then
        echo -e "Текущий лимит для '${GREEN}$SELECTED_USER${NC}': ${YELLOW}$(human_bytes "$cur_limit")${NC}"
    else
        echo -e "Текущий лимит для '${GREEN}$SELECTED_USER${NC}': ${YELLOW}не ограничен${NC}"
    fi
    read -p "Введите лимит трафика в ГБ (0 = без лимита): " gb

    if [[ "$gb" =~ ^[0-9]+$ ]]; then
        local bytes=$((gb * 1073741824))
        echo "$bytes" > "$TRAFFIC_LIMITS_DIR/$SELECTED_USER"
        init_traffic_chain
        add_traffic_rule "$SELECTED_USER"
        if [ "$bytes" -eq 0 ]; then
            echo -e "${GREEN}Лимит трафика для '$SELECTED_USER' снят.${NC}"
        else
            echo -e "${GREEN}Лимит трафика для '$SELECTED_USER' установлен: $(human_bytes "$bytes")${NC}"
        fi
    else
        echo -e "${RED}Неверный формат числа.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

reset_traffic_usage() {
    select_user "🔄 Сброс использованного трафика" || return
    echo ""
    echo "0" > "$TRAFFIC_DIR/$SELECTED_USER"
    remove_traffic_rule "$SELECTED_USER"
    add_traffic_rule "$SELECTED_USER"

    if passwd -S "$SELECTED_USER" 2>/dev/null | grep -q " L "; then
        read -p "Аккаунт заблокирован (возможно из-за превышения лимита). Разблокировать? (y/n): " unlock
        [[ "$unlock" =~ ^[Yy]$ ]] && usermod -U "$SELECTED_USER"
    fi

    echo -e "${GREEN}Счётчик трафика для '$SELECTED_USER' обнулён.${NC}"
    read -p "Нажмите Enter для продолжения..."
}

show_traffic_table() {
    header
    echo -e "${YELLOW}--- 📶 Использование трафика ---${NC}"

    if [ ! -s "$DB_USERS" ]; then
        echo -e "${MAGENTA}Список пользователей пуст.${NC}"
        read -p "Нажмите Enter..."
        return
    fi

    printf "${BLUE}%-3s %-10s %-14s %-14s %-8s${NC}\n" "№" "Логин" "Использовано" "Лимит" "%"
    echo -e "${CYAN}──────────────────────────────────────────────────${NC}"

    local i=1
    while read -r u; do
        [ -z "$u" ] && continue
        id "$u" &>/dev/null || continue

        local used=$(get_traffic_used "$u")
        local cur=$(get_traffic_counter_bytes "$u")
        local total=$((used + cur))
        local limit=$(get_traffic_limit "$u")

        local limit_str="Без лимита"
        local pct_str="-"
        if [ "$limit" -gt 0 ] 2>/dev/null; then
            limit_str=$(human_bytes "$limit")
            local pct=$((total * 100 / limit))
            if [ "$pct" -ge 100 ]; then
                pct_str="${RED}${pct}%${NC}"
            elif [ "$pct" -ge 80 ]; then
                pct_str="${YELLOW}${pct}%${NC}"
            else
                pct_str="${GREEN}${pct}%${NC}"
            fi
        fi

        printf "%-3s %-10s %-14s %-14s %-8b\n" "$i)" "$u" "$(human_bytes "$total")" "$limit_str" "$pct_str"
        ((i++))
    done < "$DB_USERS"

    echo ""
    read -p "Нажмите Enter для продолжения..."
}

uninstall_traffic_monitor() {
    header
    echo -e "${YELLOW}--- 🗑️ Отключение мониторинга трафика ---${NC}"
    rm -f "$TRAFFIC_CRON" "$TRAFFIC_CHECK_SCRIPT"
    if traffic_chain_exists; then
        iptables -D OUTPUT -j "$TRAFFIC_CHAIN" 2>/dev/null
        iptables -F "$TRAFFIC_CHAIN" 2>/dev/null
        iptables -X "$TRAFFIC_CHAIN" 2>/dev/null
    fi
    echo -e "${GREEN}Мониторинг трафика отключен, правила iptables удалены.${NC}"
    read -p "Нажмите Enter для продолжения..."
}

menu_traffic() {
    while true; do
        header
        echo -e "${YELLOW}📶 МОДУЛЬ ЛИМИТА ТРАФИКА${NC}"
        if traffic_chain_exists; then
            echo -e " Статус: ${GREEN}🟢 Включен${NC}"
        else
            echo -e " Статус: ${RED}🔴 Выключен${NC}"
        fi
        echo ""
        echo -e " 1) ⚡ Включить мониторинг трафика"
        echo -e " 2) 📊 Таблица использования"
        echo -e " 3) ⚙️  Установить лимит пользователю"
        echo -e " 4) 🔄 Сбросить счётчик пользователя"
        echo -e " 5) 🗑️  Отключить мониторинг"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-5]: " tchoice
        case $tchoice in
            1) install_traffic_monitor ;;
            2) show_traffic_table ;;
            3) set_traffic_limit ;;
            4) reset_traffic_usage ;;
            5) uninstall_traffic_monitor ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
