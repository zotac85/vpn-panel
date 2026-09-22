#!/bin/bash

# ──────────────────────────────────────────────────────────────
# Утилита: синхронизация maxlogins в /etc/security/limits.conf
# ──────────────────────────────────────────────────────────────
sync_maxlogins() {
    local u="$1"
    local limit="$2"

    [ -z "$u" ] && return
    local f="/etc/security/limits.conf"

    sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" "$f" 2>/dev/null
    sed -i "/^${u}[[:space:]]\+soft[[:space:]]\+maxlogins/d" "$f" 2>/dev/null

    if ! [[ "$limit" =~ ^[0-9]+$ ]] || [ "$limit" -le 0 ]; then
        return
    fi

    echo "${u} hard maxlogins ${limit}" >> "$f"
}

# ──────────────────────────────────────────────────────────────
# ✏️  Меню редактирования пользователя (без удаления)
# ──────────────────────────────────────────────────────────────
edit_user_menu() {
    select_user "✏️ Выбор пользователя для редактирования" || return
    while true; do
        header
        echo -e "${YELLOW}--- ✏️  Редактирование: ${GREEN}$SELECTED_USER${YELLOW} ---${NC}"
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
        echo -e " 2) ⚙️  Изменить лимит устройств"
        echo -e " 3) 📶 Изменить лимит трафика"
        echo -e " 4) ⏳ Продлить срок действия"
        echo -e " 5) 📊 Детальная статистика сессий"
        echo -e " 0) ↩️  Назад к списку"
        echo -e "${CYAN}────────────────────────────────────────────${NC}"
        read -p "Выберите действие [0-5]: " action_choice

        case $action_choice in
            1) change_password ;;
            2) change_user_limit ;;
            3) change_traffic_limit_menu ;;
            4) renew_user ;;
            5) client_statistics ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

# ──────────────────────────────────────────────────────────────
# 🔒 Меню блокировки пользователя
# ──────────────────────────────────────────────────────────────
block_user_menu() {
    select_user "🔒 Выбор пользователя для блокировки" || return
    echo ""
    echo -e "${CYAN}Пользователь: ${YELLOW}$SELECTED_USER${NC}"
    if passwd -S "$SELECTED_USER" 2>/dev/null | grep -q " L "; then
        echo -e "Текущий статус: ${RED}🔒 ЗАБЛОКИРОВАН${NC}"
        echo ""
        read -p "Разблокировать? (y/n): " c
        if [[ "$c" =~ ^[Yy]$ ]]; then
            usermod -U "$SELECTED_USER"
            echo -e "${GREEN}✅ Пользователь '$SELECTED_USER' разблокирован!${NC}"
        else
            echo -e "${YELLOW}Отменено.${NC}"
        fi
    else
        echo -e "Текущий статус: ${GREEN}🟢 АКТИВЕН${NC}"
        echo ""
        read -p "Заблокировать? (y/n): " c
        if [[ "$c" =~ ^[Yy]$ ]]; then
            usermod -L "$SELECTED_USER"
            echo -e "${YELLOW}🔒 Пользователь '$SELECTED_USER' заблокирован!${NC}"
        else
            echo -e "${YELLOW}Отменено.${NC}"
        fi
    fi
    read -p "Нажмите Enter для продолжения..."
}

# ──────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────
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
        echo -e "${GREEN}Лимит трафика для '$SELECTED_USER' изменён на ${new_gb} ГБ!${NC}"
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
# # ──────────────────────────────────────────────────────────────
# Генератор случайной строки (a-z, 0-9)
# ──────────────────────────────────────────────────────────────
gen_random() {
    local len="${1:-8}"
    tr -dc 'a-z0-9' < /dev/urandom | head -c "$len"
}

# ──────────────────────────────────────────────────────────────
# Общая функция создания пользователя
# ──────────────────────────────────────────────────────────────
create_user_common() {
    local username="$1"
    local password="$2"
    local days="$3"
    local max_devices="$4"
    local traffic_gb="$5"

    if id "$username" &>/dev/null; then
        echo -e "${RED}Пользователь '$username' уже существует!${NC}"
        return 1
    fi

    useradd -M -s /bin/false "$username"
    echo "$username:$password" | chpasswd

    echo "$username" >> "$DB_USERS"
    sort -u -o "$DB_USERS" "$DB_USERS"
    echo "$max_devices" > "$LIMITS_DIR/$username"

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
    fi

    return 0
}

# ──────────────────────────────────────────────────────────────
# 🧪 Тестовый аккаунт (одной кнопкой)
# ──────────────────────────────────────────────────────────────
add_test_user() {
    header
    echo -e "${YELLOW}--- 🧪 Создание тестового аккаунта ---${NC}"
    echo ""
    echo -e "${CYAN}Параметры:${NC}"
    echo -e "  • Логин     : 8 символов (случайно)"
    echo -e "  • Пароль    : 8 символов (случайно)"
    echo -e "  • Лимит     : 10 устройств"
    echo -e "  • Срок      : 1 день"
    echo -e "  • Трафик    : 100 ГБ"
    echo ""

    # Генерируем уникальное имя
    local username=""
    local attempts=0
    while [ -z "$username" ] || id "$username" &>/dev/null; do
        username=$(gen_random 8)
        attempts=$((attempts + 1))
        if [ "$attempts" -gt 20 ]; then
            echo -e "${RED}Не удалось сгенерировать уникальное имя.${NC}"
            read -p "Enter..."
            return
        fi
    done

    local password=$(gen_random 8)
    local max_devices=10
    local days=1
    local traffic_gb=100

    create_user_common "$username" "$password" "$days" "$max_devices" "$traffic_gb" || {
        read -p "Enter..."
        return
    }

    SERVER_IP=$(curl -s4 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    local exp_date=$(date -d "+1 day" +%Y-%m-%d)

    clear
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}      ${YELLOW}🧪 ТЕСТОВЫЙ АККАУНТ СОЗДАН 🧪${NC}      ${GREEN}║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC} Сервер     : ${CYAN}$SERVER_IP${NC}"
    echo -e "${GREEN}║${NC} Срок       : ${CYAN}1 день (до $exp_date)${NC}"
    echo -e "${GREEN}║${NC} Устройства : ${CYAN}до $max_devices${NC}"
    echo -e "${GREEN}║${NC} Трафик     : ${CYAN}$traffic_gb ГБ${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}📋 Ссылка для DarkTunnel (скопируй):${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo -e "${GREEN}${username}:${password}${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo ""
    echo -e "${MAGENTA}Совет: нажми и удерживай на строке выше → копировать${NC}"
    echo ""
    read -p "Нажмите Enter для продолжения..."
}

# ──────────────────────────────────────────────────────────────
# 👑 VIP аккаунт (ручной ввод)
# ──────────────────────────────────────────────────────────────
add_vip_user() {
    header
    echo -e "${YELLOW}--- 👑 Создание VIP аккаунта ---${NC}"
    echo ""
    read -p "Логин (3-20 символов): " username
    [ -z "$username" ] && { echo -e "${RED}Логин не может быть пустым.${NC}"; sleep 1; return; }

    if ! [[ "$username" =~ ^[a-zA-Z0-9_-]{3,20}$ ]]; then
        echo -e "${RED}Логин: только a-z, A-Z, 0-9, _ и -, длина 3-20.${NC}"
        read -p "Enter..."; return
    fi

    if id "$username" &>/dev/null; then
        echo -e "${RED}Пользователь '$username' уже существует!${NC}"
        read -p "Enter..."; return
    fi

    read -p "Пароль (Enter = сгенерировать): " password
    [ -z "$password" ] && password=$(gen_random 10)

    read -p "Срок в днях (Enter = бессрочно): " days
    if ! [[ "$days" =~ ^[0-9]+$ ]]; then
        days=0
    fi

    read -p "Лимит устройств (Enter = 5): " max_devices
    if ! [[ "$max_devices" =~ ^[0-9]+$ ]] || [ "$max_devices" -lt 1 ]; then
        max_devices=5
    fi

    read -p "Лимит трафика в ГБ (Enter = без лимита): " traffic_gb
    if ! [[ "$traffic_gb" =~ ^[0-9]+$ ]]; then
        traffic_gb=0
    fi

    create_user_common "$username" "$password" "$days" "$max_devices" "$traffic_gb" || {
        read -p "Enter..."
        return
    }

    SERVER_IP=$(curl -s4 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    if [ "$days" -gt 0 ] 2>/dev/null; then
        exp_info=$(date -d "+$days days" +%Y-%m-%d)
    else
        exp_info="Бессрочно"
    fi
    local traffic_info="Без лимита"
    [ "$traffic_gb" -gt 0 ] && traffic_info="${traffic_gb} ГБ"

    clear
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}        ${YELLOW}👑 VIP АККАУНТ СОЗДАН 👑${NC}          ${GREEN}║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC} Сервер     : ${CYAN}$SERVER_IP${NC}"
    echo -e "${GREEN}║${NC} Логин      : ${CYAN}$username${NC}"
    echo -e "${GREEN}║${NC} Пароль     : ${CYAN}$password${NC}"
    echo -e "${GREEN}║${NC} Срок       : ${CYAN}$exp_info${NC}"
    echo -e "${GREEN}║${NC} Устройства : ${CYAN}до $max_devices${NC}"
    echo -e "${GREEN}║${NC} Трафик     : ${CYAN}$traffic_info${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}📋 Ссылка для DarkTunnel (скопируй):${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo -e "${GREEN}${username}:${password}${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo ""
    read -p "Нажмите Enter для продолжения..."
}

# ──────────────────────────────────────────────────────────────
# ➕ Меню «Добавить пользователя»
# ──────────────────────────────────────────────────────────────
add_user() {
    while true; do
        header
        echo -e "${YELLOW}➕ ДОБАВИТЬ ПОЛЬЗОВАТЕЛЯ${NC}"
        echo ""
        echo -e " 1) 🧪 Создать ТЕСТОВЫЙ аккаунт (одной кнопкой)"
        echo -e "    8 симв. логин/пароль • 10 устройств • 1 день • 100 ГБ"
        echo ""
        echo -e " 2) 👑 Создать VIP аккаунт (ручной ввод)"
        echo -e "    Бессрочно • 5 устройств • без лимита трафика"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-2]: " achoice

        case $achoice in
            1) add_test_user ;;
            2) add_vip_user ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}



# ──────────────────────────────────────────────────────────────
# 🗑️  Удалить пользователя
# ──────────────────────────────────────────────────────────────
delete_user() {
    select_user "🗑️ Удаление пользователя" || return
    echo ""
    read -p "Удалить пользователя '$SELECTED_USER'? (y/n): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        userdel -f "$SELECTED_USER" 2>/dev/null
        sed -i "/^${SELECTED_USER}$/d" "$DB_USERS" 2>/dev/null
        rm -f "$LIMITS_DIR/$SELECTED_USER" "$TRAFFIC_LIMITS_DIR/$SELECTED_USER" "$TRAFFIC_DIR/$SELECTED_USER" 2>/dev/null

        # Убираем maxlogins
        sync_maxlogins "$SELECTED_USER" 0

        if declare -f remove_traffic_rule &>/dev/null; then
            remove_traffic_rule "$SELECTED_USER"
        fi
        echo -e "${GREEN}Пользователь '$SELECTED_USER' удалён!${NC}"
    else
        echo -e "${YELLOW}Удаление отменено.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

# ──────────────────────────────────────────────────────────────
# Действия с пользователем
# ──────────────────────────────────────────────────────────────
change_password() {
    echo ""
    read -p "Новый пароль для '$SELECTED_USER': " password
    [ -z "$password" ] && { echo -e "${RED}Пароль не может быть пустым.${NC}"; sleep 1; return; }
    echo "$SELECTED_USER:$password" | chpasswd
    echo -e "${GREEN}Пароль для '$SELECTED_USER' обновлён!${NC}"
    read -p "Нажмите Enter для продолжения..."
}

change_user_limit() {
    echo ""
    local current_limit=3
    [ -f "$LIMITS_DIR/$SELECTED_USER" ] && current_limit=$(cat "$LIMITS_DIR/$SELECTED_USER")
    echo -e "Текущий лимит устройств для '${GREEN}$SELECTED_USER${NC}': ${YELLOW}$current_limit${NC}"
    read -p "Введите новый лимит (1-99): " new_limit
    if [[ "$new_limit" =~ ^[0-9]+$ ]] && [ "$new_limit" -ge 1 ]; then
        echo "$new_limit" > "$LIMITS_DIR/$SELECTED_USER"

        # Схема A
        sync_maxlogins "$SELECTED_USER" "$new_limit"

        echo -e "${GREEN}Лимит устройств для '$SELECTED_USER' изменён на $new_limit!${NC}"
        echo -e "${CYAN}PAM-лимит (maxlogins) обновлён.${NC}"
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
        echo -e "${GREEN}Срок для '$SELECTED_USER' продлён до $exp_date.${NC}"
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
    echo -e " ⚙️  Лимит устройств : ${CYAN}$user_limit${NC}"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo -e " 🔑 SSH активных       : ${GREEN}$count_ssh${NC}"
    echo -e " 🕸️  SSH WS активных    : ${GREEN}$count_ws${NC}"
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
        echo -e "${MAGENTA}Список пуст. Вы ещё не создавали пользователей.${NC}"
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

# ──────────────────────────────────────────────────────────────
# 👥 ГЛАВНОЕ МЕНЮ ПОЛЬЗОВАТЕЛЕЙ
# ──────────────────────────────────────────────────────────────
menu_users() {
    while true; do
        header
        echo -e "${YELLOW}👥 УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ И ОГРАНИЧЕНИЯМИ${NC}"
        echo ""
        echo -e " 1) ➕ Добавить пользователя"
        echo -e " 2) ✏️  Редактировать пользователя"
        echo -e " 3) 🔒 Блокировать / Разблокировать"
        echo -e " 4) 🗑️  Удалить пользователя"
        echo -e " 5) 📋 Список пользователей и текущий онлайн"
        echo -e " 6) 🚦 Контроль лимита устройств"
        echo -e " 7) 🧹 Обслуживание (трафик, бэкап, истёкшие)"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-7]: " uchoice
        case $uchoice in
            1) add_user ;;
            2) edit_user_menu ;;
            3) block_user_menu ;;
            4) delete_user ;;
            5) list_users ;;
            6) menu_devicelimit ;;
            7) menu_maintenance ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
