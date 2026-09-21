#!/bin/bash

# ──────────────────────────────────────────────────────────────
# Утилита: синхронизация maxlogins в /etc/security/limits.conf
# Используется при создании / изменении лимита / удалении юзера.
# ──────────────────────────────────────────────────────────────
sync_maxlogins() {
    local u="$1"
    local limit="$2"

    [ -z "$u" ] && return
    local f="/etc/security/limits.conf"

    # Удаляем старые записи для этого юзера (любые: hard/soft/maxlogins)
    sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" "$f" 2>/dev/null
    sed -i "/^${u}[[:space:]]\+soft[[:space:]]\+maxlogins/d" "$f" 2>/dev/null

    # Если limit <= 0 или не число — просто снимаем ограничение (запись удалена)
    if ! [[ "$limit" =~ ^[0-9]+$ ]] || [ "$limit" -le 0 ]; then
        return
    fi

    # Добавляем новую запись
    echo "${u} hard maxlogins ${limit}" >> "$f"
}

# ──────────────────────────────────────────────────────────────
# Персональное меню управления конкретным пользователем
# ──────────────────────────────────────────────────────────────
manage_single_user() {
    select_user "⚙️ Выбор пользователя для управления" || return
    while true; do
        header
        echo -e "${YELLOW}--- 👤 Настройка клиента: ${GREEN}$SELECTED_USER${YELLOW} ---${NC}"
        echo -e "${CYAN}────────────────────────────────────────────${NC}"

        local user_limit=3
        [ -f "$LIMITS_DIR/$SELECTED_USER" ] && user_limit=$(cat "$LIMITS_DIR/$SELECTED_USER")

        local traffic_info="Без лимита"
        if declare -f get_traffic_limit &>/dev/null; then
            local limit=$(get_traffic_limit "$SELECTED_USER")
            if [ "$limit" -gt 0 ] 2>/dev/null; then
                local used=0
                declare -f get_traffic_used &>/dev/null && used=$(get_traffic_used "$SELECTED_USER")
                local cur=0
                declare -f get_traffic_counter_bytes &>/dev/null && cur=$(get_traffic_counter_bytes "$SELECTED_USER")
                traffic_info="$(human_bytes "$((used + cur))") / $(human_bytes "$limit")"
            fi
        fi

        local exp=$(chage -l "$SELECTED_USER" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
        [ "$exp" == "never" ] && exp="Бессрочно"

        if passwd -S "$SELECTED_USER" 2>/dev/null | grep -q " L "; then
            status_str="${RED}${USER_LOCK}${NC}"
        else
            status_str="${GREEN}${USER_ON}${NC}"
        fi

        echo -e " 🔒 Статус учетки    : $status_str"
        echo -e " 📅 Срок действия    : ${CYAN}$exp${NC}"
        echo -e " 📱 Лимит устройств  : ${CYAN}$user_limit${NC}"
        echo -e " 📶 Трафик           : ${CYAN}$traffic_info${NC}"
        echo -e "${CYAN}────────────────────────────────────────────${NC}"
        echo -e " 1) 🔑 Изменить пароль"
        echo -e " 2) ⚙️ Изменить лимит устройств"
        echo -e " 3) 📶 Изменить лимит трафика"
        echo -e " 4) 🔒 Блокировать / Разблокировать"
        echo -e " 5) ⏳ Продлить срок действия"
        echo -e " 6) 📊 Детальная статистика сессий"
        echo -e " 7) 🗑️ Удалить пользователя"
        echo -e " 0) ↩️ Назад к списку"
        echo -e "${CYAN}────────────────────────────────────────────${NC}"
        read -p "Выберите действие [0-7]: " action_choice

        case $action_choice in
            1) change_password ;;
            2) change_user_limit ;;
            3) change_traffic_limit_menu ;;
            4) toggle_lock ;;
            5) renew_user ;;
            6) client_statistics ;;
            7) delete_user; return ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

change_traffic_limit_menu() {
    echo ""
    read -p "Введите новый лимит трафика в ГБ (0 = без лимита): " new_gb
    if [[ "$new_gb" =~ ^[0-9]+$ ]]; then
        local bytes=$((new_gb * 1073741824))
        mkdir -p "$TRAFFIC_LIMITS_DIR" 2>/dev/null
        echo "$bytes" > "$TRAFFIC_LIMITS_DIR/$SELECTED_USER"
        if declare -f init_traffic_chain &>/dev/null && declare -f add_traffic_rule &>/dev/null; then
            init_traffic_chain
            add_traffic_rule "$SELECTED_USER"
        fi
        echo -e "${GREEN}Лимит трафика для '$SELECTED_USER' успешно изменен на ${new_gb} ГБ!${NC}"
    else
        echo -e "${RED}Неверный формат числа.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

general_restrictions_stats() {
    header
    echo -e "${YELLOW}--- 📊 Общая статистика ограничений и лимитов ---${NC}"

    if [ ! -s "$DB_USERS" ]; then
        echo -e "${MAGENTA}Список пользователей пуст.${NC}"
        echo ""
        read -p "Нажмите Enter для возврата..."
        return
    fi

    printf "${BLUE}%-3s %-12s %-8s %-18s %-12s${NC}\n" "№" "Логин" "Устр." "Трафик (Исп/Лимит)" "Срок"
    echo -e "${CYAN}─────────────────────────────────────────────────────────────────${NC}"

    local i=1
    while read -r u; do
        [ -z "$u" ] && continue
        if id "$u" &>/dev/null; then
            local user_limit=3
            [ -f "$LIMITS_DIR/$u" ] && user_limit=$(cat "$LIMITS_DIR/$u")

            local exp=$(chage -l "$u" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
            [ "$exp" == "never" ] && exp="Бессрочно"

            local traffic_summary="Без лимита"
            if declare -f get_traffic_limit &>/dev/null; then
                local limit=$(get_traffic_limit "$u")
                if [ "$limit" -gt 0 ] 2>/dev/null; then
                    local used=$(get_traffic_used "$u")
                    local cur=0
                    declare -f get_traffic_counter_bytes &>/dev/null && cur=$(get_traffic_counter_bytes "$u")
                    traffic_summary="$(human_bytes "$((used + cur))")/$(human_bytes "$limit")"
                fi
            fi

            printf "%-3s %-12s %-8s %-18s %-12s\n" "$i)" "$u" "$user_limit" "$traffic_summary" "$exp"
            ((i++))
        fi
    done < "$DB_USERS"

    echo -e "${CYAN}─────────────────────────────────────────────────────────────────${NC}"
    echo ""
    read -p "Нажмите Enter для возврата..."
}

# ──────────────────────────────────────────────────────────────
# add_user — создание пользователя + maxlogins (схема A)
# ──────────────────────────────────────────────────────────────
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

    read -p "Лимит трафика в ГБ (Enter = без лимита): " traffic_gb
    if ! [[ "$traffic_gb" =~ ^[0-9]+$ ]]; then
        traffic_gb=0
    fi

    useradd -M -s /bin/false "$username"
    echo "$username:$password" | chpasswd

    echo "$username" >> "$DB_USERS"
    sort -u -o "$DB_USERS" "$DB_USERS"
    echo "$max_devices" > "$LIMITS_DIR/$username"

    # ── СХЕМА A: maxlogins в limits.conf ──
    sync_maxlogins "$username" "$max_devices"

    local traffic_bytes=$((traffic_gb * 1073741824))
    mkdir -p "$TRAFFIC_LIMITS_DIR" "$TRAFFIC_DIR" 2>/dev/null
    echo "$traffic_bytes" > "$TRAFFIC_LIMITS_DIR/$username" 2>/dev/null
    echo "0" > "$TRAFFIC_DIR/$username" 2>/dev/null
    if declare -f add_traffic_rule &>/dev/null; then
        add_traffic_rule "$username"
    fi

    if [ -n "$days" ] && [ "$days" -gt 0 ] 2>/dev/null; then
        exp_date=$(date -d "+$days days" +%Y-%m-%d)
        chage -E "$exp_date" "$username"
        exp_info="$exp_date"
    else
        exp_info="Бессрочно"
    fi

    SERVER_IP=$(curl -s4 ifconfig.me || hostname -I | awk '{print $1}')
    local traffic_info="Без лимита"
    [ "$traffic_gb" -gt 0 ] && traffic_info="${traffic_gb} ГБ"

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}         ${YELLOW}🎉 ПОЛЬЗОВАТЕЛЬ СОЗДАН 🎉${NC}          ${GREEN}║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC} Сервер : ${CYAN}$SERVER_IP${NC}"
    echo -e "${GREEN}║${NC} Логин  : ${CYAN}$username${NC}"
    echo -e "${GREEN}║${NC} Пароль : ${CYAN}$password${NC}"
    echo -e "${GREEN}║${NC} Срок   : ${CYAN}$exp_info${NC}"
    echo -e "${GREEN}║${NC} Устройства : ${CYAN}Макс. $max_devices${NC}"
    echo -e "${GREEN}║${NC} Трафик : ${CYAN}$traffic_info${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    echo ""
    read -p "Нажмите Enter для продолжения..."
}

# ──────────────────────────────────────────────────────────────
# delete_user — удаление пользователя + чистка maxlogins
# ──────────────────────────────────────────────────────────────
delete_user() {
    select_user "🗑️ Удаление пользователя" || return
    echo ""
    read -p "Удалить пользователя '$SELECTED_USER'? (y/n): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        userdel -f "$SELECTED_USER" 2>/dev/null
        sed -i "/^${SELECTED_USER}$/d" "$DB_USERS" 2>/dev/null
        rm -f "$LIMITS_DIR/$SELECTED_USER" "$TRAFFIC_LIMITS_DIR/$SELECTED_USER" "$TRAFFIC_DIR/$SELECTED_USER" 2>/dev/null

        # ── СХЕМА A: убираем maxlogins ──
        sync_maxlogins "$SELECTED_USER" 0

        if declare -f remove_traffic_rule &>/dev/null; then
            remove_traffic_rule "$SELECTED_USER"
        fi
        echo -e "${GREEN}Пользователь '$SELECTED_USER' удален!${NC}"
    else
        echo -e "${YELLOW}Удаление отменено.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

change_password() {
    echo ""
    read -p "Новый пароль для '$SELECTED_USER': " password
    [ -z "$password" ] && { echo -e "${RED}Пароль не может быть пустым.${NC}"; sleep 1; return; }
    echo "$SELECTED_USER:$password" | chpasswd
    echo -e "${GREEN}Пароль для '$SELECTED_USER' обновлен!${NC}"
    read -p "Нажмите Enter для продолжения..."
}

# ──────────────────────────────────────────────────────────────
# change_user_limit — обновление лимита + maxlogins (схема A)
# ──────────────────────────────────────────────────────────────
change_user_limit() {
    echo ""
    local current_limit=3
    [ -f "$LIMITS_DIR/$SELECTED_USER" ] && current_limit=$(cat "$LIMITS_DIR/$SELECTED_USER")
    echo -e "Текущий лимит устройств для '${GREEN}$SELECTED_USER${NC}': ${YELLOW}$current_limit${NC}"
    read -p "Введите новый лимит (1-99): " new_limit
    if [[ "$new_limit" =~ ^[0-9]+$ ]] && [ "$new_limit" -ge 1 ]; then
        echo "$new_limit" > "$LIMITS_DIR/$SELECTED_USER"

        # ── СХЕМА A: обновляем maxlogins ──
        sync_maxlogins "$SELECTED_USER" "$new_limit"

        echo -e "${GREEN}Лимит устройств для '$SELECTED_USER' изменен на $new_limit!${NC}"
        echo -e "${CYAN}PAM-лимит (maxlogins) обновлён — новые подключения сверх лимита будут отклоняться.${NC}"
    else
        echo -e "${RED}Неверный формат числа.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

toggle_lock() {
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
    header
    echo -e "${YELLOW}--- 📊 Статистика клиента: $SELECTED_USER ---${NC}"
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

    read count_ssh count_ws count_white <<< $(get_user_connections "$SELECTED_USER")
    local total_count=$((count_ssh + count_ws + count_white))

    echo -e " 👤 Логин аккаунта : ${GREEN}$SELECTED_USER${NC}"
    echo -e " 📅 Срок действия  : ${CYAN}$exp${NC}"
    echo -e " 🔒 Статус учетки  : $status_str"
    echo -e " ⚙️ Лимит устройств : ${CYAN}$user_limit${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo -e " 🔑 SSH активных       : ${GREEN}$count_ssh${NC}"
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
    echo -e "${YELLOW}--- 📋 Список текущего онлайна ---${NC}"

    if [ ! -s "$DB_USERS" ]; then
        echo -e "${MAGENTA}Список пуст. Вы еще не создавали пользователей.${NC}"
        echo ""
        read -p "Нажмите Enter для продолжения..."
        return
    fi

    build_session_stats

    printf "${BLUE}%-3s %-10s %-11s %-4s %-4s %-4s %-6s %-10s${NC}\n" "№" "Логин" "Срок" "SSH" "WS" "Wh" "Лимит" "Статус"
    echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"

    local i=1
    while read -r u; do
        [ -z "$u" ] && continue
        if id "$u" &>/dev/null; then
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

    echo ""
    read -p "Нажмите Enter для продолжения..."
}

menu_users() {
    while true; do
        header
        echo -e "${YELLOW}👥 УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ И ОГРАНИЧЕНИЯМИ${NC}"
        echo ""
        echo -e " 1) ⚙️ Управление конкретным пользователем (пароль, лимиты, трафик, блок)"
        echo -e " 2) 📋 Список пользователей и текущий онлайн"
        echo -e " 3) 📊 Общая статистика ограничений по всем пользователям"
        echo -e " 4) ➕ Добавить пользователя"
        echo -e " 5) 🗑️ Удалить пользователя"
        echo -e " 6) 🚦 Контроль лимита устройств"
        echo -e " 7) 📶 Мониторинг и лимит трафика"
        echo -e " 0) ↩️ Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-7]: " uchoice
        case $uchoice in
            1) manage_single_user ;;
            2) list_users ;;
            3) general_restrictions_stats ;;
            4) add_user ;;
            5) delete_user ;;
            6) menu_devicelimit ;;
            7) menu_traffic ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
