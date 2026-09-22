#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ ОБСЛУЖИВАНИЯ (бэкап, истёкшие, автоочистка)
# ──────────────────────────────────────────────────────────────

BACKUP_DIR="/root/vpn-backups"
AUTO_CLEANUP_SCRIPT="/usr/local/bin/vpn-auto-cleanup.sh"
AUTO_CLEANUP_CRON="/etc/cron.d/vpn-auto-cleanup"
AUTO_CLEANUP_LOG="/var/log/vpn-auto-cleanup.log"

auto_cleanup_active() {
    [ -f "$AUTO_CLEANUP_CRON" ]
}

# ──────────────────────────────────────────────────────────────
# Получить список истёкших (формат: user|exp_date|days_ago)
# ──────────────────────────────────────────────────────────────
get_expired_users() {
    [ ! -s "$DB_USERS" ] && return
    local today=$(date +%s)
    while read -r u; do
        [ -z "$u" ] && continue
        id "$u" &>/dev/null || continue
        local exp_raw=$(chage -l "$u" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
        [ "$exp_raw" == "never" ] && continue
        [ -z "$exp_raw" ] && continue
        local exp_epoch=$(date -d "$exp_raw" +%s 2>/dev/null)
        [ -z "$exp_epoch" ] && continue
        if [ "$exp_epoch" -lt "$today" ]; then
            local days_ago=$(( (today - exp_epoch) / 86400 ))
            echo "$u|$exp_raw|$days_ago"
        fi
    done < "$DB_USERS"
}

# ──────────────────────────────────────────────────────────────
# Удаление одного пользователя (все следы)
# ──────────────────────────────────────────────────────────────
purge_user() {
    local u="$1"
    [ -z "$u" ] && return

    # iptables rule — ДО userdel (пока uid известен)
    local uid=$(id -u "$u" 2>/dev/null)
    if [ -n "$uid" ]; then
        while iptables -D VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null; do :; done
    fi

    userdel -f "$u" 2>/dev/null
    sed -i "/^${u}$/d" "$DB_USERS" 2>/dev/null
    rm -f "$LIMITS_DIR/$u" "$TRAFFIC_LIMITS_DIR/$u" "$TRAFFIC_DIR/$u" 2>/dev/null
    sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
    sed -i "/^${u}[[:space:]]\+soft[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
}

# ──────────────────────────────────────────────────────────────
# 📋 Список истёкших
# ──────────────────────────────────────────────────────────────
show_expired_users() {
    header
    echo -e "${YELLOW}--- 📋 Список истёкших аккаунтов ---${NC}"
    echo ""

    local data=$(get_expired_users)
    if [ -z "$data" ]; then
        echo -e "${GREEN}✅ Истёкших аккаунтов нет.${NC}"
        echo ""
        read -p "Нажмите Enter..."
        return
    fi

    printf "${BLUE}%-3s %-12s %-14s %-12s${NC}\n" "№" "Логин" "Истёк" "Дней назад"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    local i=1
    while IFS='|' read -r u exp days; do
        printf "%-3s %-12s %-14s %-12s\n" "$i)" "$u" "$exp" "$days"
        ((i++))
    done <<< "$data"
    echo -e "${CYAN}────────────────────────────────────────────${NC}"
    echo ""
    echo -e "${YELLOW}Всего: $(echo "$data" | wc -l) истёкших${NC}"
    echo ""
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# 🗑️ Удалить всех истёкших
# ──────────────────────────────────────────────────────────────
delete_expired_users() {
    header
    echo -e "${YELLOW}--- 🗑️  Удаление истёкших аккаунтов ---${NC}"
    echo ""

    local data=$(get_expired_users)
    if [ -z "$data" ]; then
        echo -e "${GREEN}✅ Истёкших аккаунтов нет — нечего удалять.${NC}"
        read -p "Нажмите Enter..."
        return
    fi

    local count=$(echo "$data" | wc -l)
    echo -e "${YELLOW}Найдено истёкших: ${RED}$count${NC}"
    echo ""
    echo -e "${CYAN}Список:${NC}"
    while IFS='|' read -r u exp days; do
        echo -e "  • $u (истёк $exp, $days дн. назад)"
    done <<< "$data"
    echo ""

    read -p "Удалить ВСЕХ истёкших? (y/n): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Отменено.${NC}"
        read -p "Enter..."
        return
    fi

    echo ""
    local deleted=0
    while IFS='|' read -r u exp days; do
        purge_user "$u"
        echo -e "  ${RED}✗${NC} Удалён: $u"
        ((deleted++))
    done <<< "$data"

    echo ""
    echo -e "${GREEN}✅ Удалено: $deleted аккаунтов${NC}"
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# 💾 Бэкап
# ──────────────────────────────────────────────────────────────
create_backup() {
    header
    echo -e "${YELLOW}--- 💾 Создание бэкапа ---${NC}"
    echo ""

    mkdir -p "$BACKUP_DIR"
    local file="$BACKUP_DIR/vpn-backup-$(date +%Y%m%d-%H%M%S).tar.gz"

    echo -e "${CYAN}Создаём архив...${NC}"
    tar -czf "$file" \
        /etc/UDPCustom \
        /etc/bannerssh \
        /etc/pam.d/sshd \
        /etc/security/limits.conf \
        /etc/cron.d/vpn-device-limit \
        /etc/cron.d/vpn-traffic-check \
        /etc/cron.d/vpn-auto-cleanup \
        2>/dev/null

    if [ -f "$file" ]; then
        local size=$(du -h "$file" | awk '{print $1}')
        echo ""
        echo -e "${GREEN}✅ Бэкап создан!${NC}"
        echo -e " 📁 Файл: ${CYAN}$file${NC}"
        echo -e " 📦 Размер: ${CYAN}$size${NC}"
        echo ""
        echo -e "${YELLOW}Скачать на ПК:${NC}"
        echo -e " scp root@$(hostname -I | awk '{print $1}'):$file ."
    else
        echo -e "${RED}❌ Ошибка создания бэкапа${NC}"
    fi
    echo ""
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# 📂 Восстановление из бэкапа
# ──────────────────────────────────────────────────────────────
restore_backup() {
    header
    echo -e "${YELLOW}--- 📂 Восстановление из бэкапа ---${NC}"
    echo ""

    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A $BACKUP_DIR 2>/dev/null)" ]; then
        echo -e "${MAGENTA}Нет бэкапов в $BACKUP_DIR${NC}"
        read -p "Enter..."
        return
    fi

    echo -e "${CYAN}Доступные бэкапы:${NC}"
    local i=1
    local files=()
    while IFS= read -r f; do
        files+=("$f")
        local size=$(du -h "$f" | awk '{print $1}')
        local date_str=$(basename "$f" | sed 's/vpn-backup-//; s/.tar.gz//')
        echo -e " $i) $(basename "$f") (${size})"
        ((i++))
    done < <(ls -t "$BACKUP_DIR"/*.tar.gz 2>/dev/null)
    echo ""

    read -p "Выберите номер (0 = отмена): " choice
    [[ "$choice" == "0" || -z "$choice" ]] && return

    if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "${#files[@]}" ]; then
        echo -e "${RED}Неверный выбор${NC}"
        read -p "Enter..."
        return
    fi

    local file="${files[$((choice-1))]}"
    echo ""
    echo -e "${RED}⚠️  ВНИМАНИЕ: текущие настройки будут ПЕРЕЗАПИСАНЫ!${NC}"
    read -p "Продолжить? (y/n): " c
    [[ ! "$c" =~ ^[Yy]$ ]] && return

    echo ""
    echo -e "${CYAN}Распаковка...${NC}"
    tar -xzf "$file" -C / 2>/dev/null

    echo -e "${GREEN}✅ Восстановлено из $file${NC}"
    echo ""
    echo -e "${YELLOW}Перезапуск sshd...${NC}"
    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
    read -p "Enter..."
}

# ──────────────────────────────────────────────────────────────
# 📜 Журнал автоочистки
# ──────────────────────────────────────────────────────────────
show_cleanup_log() {
    header
    echo -e "${YELLOW}--- 📜 Журнал автоочистки ---${NC}"
    echo ""
    if [ -f "$AUTO_CLEANUP_LOG" ] && [ -s "$AUTO_CLEANUP_LOG" ]; then
        tail -n 30 "$AUTO_CLEANUP_LOG"
    else
        echo -e "${MAGENTA}Журнал пуст — автоочистка ещё ничего не удаляла.${NC}"
    fi
    echo ""
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# 🧹 Главное меню обслуживания
# ──────────────────────────────────────────────────────────────
menu_maintenance() {
    while true; do
        header
        echo -e "${YELLOW}🧹 ОБСЛУЖИВАНИЕ И АВТОМАТИЗАЦИЯ${NC}"
        echo ""

        # Статус автоочистки
        if auto_cleanup_active; then
            echo -e " Автоочистка истёкших : ${GREEN}🟢 Включена (ежедневно)${NC}"
        else
            echo -e " Автоочистка истёкших : ${RED}🔴 Выключена${NC}"
        fi

        # Количество истёкших
        local expired_count=$(get_expired_users | wc -l)
        if [ "$expired_count" -gt 0 ]; then
            echo -e " Истёкших аккаунтов   : ${RED}$expired_count${NC}"
        else
            echo -e " Истёкших аккаунтов   : ${GREEN}0${NC}"
        fi

        # Количество бэкапов
        local backup_count=0
        [ -d "$BACKUP_DIR" ] && backup_count=$(ls -1 "$BACKUP_DIR"/*.tar.gz 2>/dev/null | wc -l)
        echo -e " Бэкапов              : ${CYAN}$backup_count${NC}"

        # Мониторинг трафика
        if declare -f traffic_chain_exists &>/dev/null && traffic_chain_exists; then
            echo -e " Мониторинг трафика   : ${GREEN}🟢 Включен${NC}"
        else
            echo -e " Мониторинг трафика   : ${RED}🔴 Выключен${NC}"
        fi

        echo ""
        echo -e "${CYAN}── Пользователи ──${NC}"
        echo -e " 1) 📋 Список истёкших аккаунтов"
        echo -e " 2) 🗑️  Удалить всех истёкших"
        echo ""
        echo -e "${CYAN}── Бэкап ──${NC}"
        echo -e " 3) 💾 Создать бэкап базы"
        echo -e " 4) 📂 Восстановить из бэкапа"
        echo ""
        echo -e "${CYAN}── Трафик ──${NC}"
        echo -e " 5) 📊 Таблица использования трафика"
        echo -e " 6) ⚙️  Установить лимит трафика пользователю"
        echo -e " 7) 🔄 Сбросить счётчик пользователя"
        echo -e " 8) ⚡ Включить / обновить мониторинг"
        echo ""
        echo -e "${CYAN}── Журналы ──${NC}"
        echo -e " 9) 📜 Журнал автоочистки"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-9]: " mchoice

        case $mchoice in
            1) show_expired_users ;;
            2) delete_expired_users ;;
            3) create_backup ;;
            4) restore_backup ;;
            5) declare -f show_traffic_table &>/dev/null && show_traffic_table ;;
            6) declare -f set_traffic_limit &>/dev/null && set_traffic_limit ;;
            7) declare -f reset_traffic_usage &>/dev/null && reset_traffic_usage ;;
            8) declare -f install_traffic_monitor &>/dev/null && install_traffic_monitor ;;
            9) show_cleanup_log ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
    
