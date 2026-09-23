#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ TELEGRAM-БОТА
# ──────────────────────────────────────────────────────────────

TG_CONF="/etc/UDPCustom/bot.conf"
TG_SERVICE="vpn-tg-bot"
TG_BOT_SCRIPT="/usr/local/bin/vpn-tg-bot.py"
TG_LOG="/var/log/vpn-tg-bot.log"
TG_ISSUED="/etc/UDPCustom/bot_issued.db"
TG_BLACKLIST="/etc/UDPCustom/bot_blacklist"

tg_bot_status() {
    if systemctl is-active --quiet "$TG_SERVICE" 2>/dev/null; then
        echo -e "${GREEN}🟢 Запущен${NC}"
    else
        echo -e "${RED}🔴 Остановлен${NC}"
    fi
}

tg_get_config() {
    local key="$1"
    grep "^${key}=" "$TG_CONF" 2>/dev/null | cut -d'=' -f2- | sed 's/^"//; s/"$//'
}

tg_set_config() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$TG_CONF" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=\"${value}\"|" "$TG_CONF"
    else
        echo "${key}=\"${value}\"" >> "$TG_CONF"
    fi
}

tg_edit_field() {
    local field="$1"
    local desc="$2"
    local current=$(tg_get_config "$field")
    echo ""
    echo -e "${CYAN}$desc${NC}"
    echo -e "Текущее: ${GREEN}${current:-не задано}${NC}"
    read -p "Новое значение (Enter — отмена): " new_val
    [ -z "$new_val" ] && return
    tg_set_config "$field" "$new_val"
    echo -e "${GREEN}✅ Сохранено${NC}"
    sleep 1
}

tg_install() {
    header
    echo -e "${YELLOW}--- ⚙️  Установка бота ---${NC}"
    echo ""

    if ! command -v python3 &>/dev/null; then
        echo -e "${CYAN}Устанавливаем Python3...${NC}"
        apt update -qq 2>/dev/null
        apt install -y python3 2>/dev/null
    fi

    if [ ! -f "$TG_CONF" ]; then
        cat > "$TG_CONF" << 'EOF'
BOT_TOKEN=""
ADMIN_ID=""
CHANNEL_ID=""
CHANNEL_ID_2=""
CHANNEL_NAME_2=""
REQUIRE_SUBSCRIPTION=0
COOLDOWN_HOURS=24
TEST_HOURS=8
TEST_DEVICES=1
TEST_TRAFFIC_GB=50
WELCOME_TEXT="🎁 Привет! Хочешь бесплатный VPN на 24 часа?\n\nНажми /test и получи доступ!"
SUCCESS_TEMPLATE="🎉 Твой тестовый доступ готов!\n\n📱 Логин : {USERNAME}\n🔑 Пароль: {PASSWORD}\n⏰ Срок   : 24 часа\n📊 Трафик: {TRAFFIC} ГБ\n💻 Устройств: {DEVICES}\n\n💬 Поддержка: @ArsenGuro\n📢 Канал: @ArsenVipKeys"
CONFIG_NAME="ArsenVipKeys"
CONNECTED_MSG="Подключено!"
PAYLOAD="CONNECT http://co.nr HTTP/1.1[crlf]Host: www.icloud.com[crlf]User-Agent: microsoft.com[crlf][crlf]AN / HTTP/1.1[lf]Host: [host][lf]Connection: Upgrade[lf]Upgrade: websocket[crlf][crlf]"
EOF
    fi

    if [ ! -f "/etc/systemd/system/${TG_SERVICE}.service" ]; then
        cat > "/etc/systemd/system/${TG_SERVICE}.service" << 'EOF'
[Unit]
Description=VPN Panel Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /usr/local/bin/vpn-tg-bot.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/vpn-tg-bot.log
StandardError=append:/var/log/vpn-tg-bot.log

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable "$TG_SERVICE" 2>/dev/null
    fi

    echo -e "${GREEN}✅ Бот установлен${NC}"
    echo ""
    echo -e "${YELLOW}Дальше настрой:${NC}"
    echo -e "  1. Введи токен (@BotFather)"
    echo -e "  2. Введи свой Telegram ID (@userinfobot)"
    echo -e "  3. Запусти бота"
    echo ""
    read -p "Нажмите Enter..."
}

tg_show_log() {
    header
    echo -e "${YELLOW}--- 📜 Логи бота (последние 30) ---${NC}"
    echo ""
    if [ -f "$TG_LOG" ]; then
        tail -n 30 "$TG_LOG"
    else
        echo -e "${MAGENTA}Логов пока нет.${NC}"
    fi
    echo ""
    read -p "Нажмите Enter..."
}

tg_show_issued() {
    header
    echo -e "${YELLOW}--- 📊 Выданные тесты ---${NC}"
    echo ""

    if [ ! -f "$TG_ISSUED" ] || [ ! -s "$TG_ISSUED" ]; then
        echo -e "${MAGENTA}Тесты ещё не выдавались.${NC}"
        echo ""
        read -p "Enter..."
        return
    fi

    printf "${BLUE}%-3s %-14s %-12s %-20s${NC}\n" "№" "Telegram ID" "Логин" "Дата"
    echo -e "${CYAN}────────────────────────────────────────────────${NC}"

    local i=1
    tail -50 "$TG_ISSUED" | tac | while IFS='|' read -r tg_id ts username; do
        [ -z "$tg_id" ] && continue
        local date_str=$(date -d "@$ts" '+%Y-%m-%d %H:%M' 2>/dev/null)
        printf "%-3s %-14s %-12s %-20s\n" "$i)" "$tg_id" "$username" "$date_str"
        ((i++))
    done
    echo ""
    read -p "Нажмите Enter..."
}

tg_blacklist() {
    while true; do
        header
        echo -e "${YELLOW}🚫 ЧЁРНЫЙ СПИСОК${NC}"
        echo ""
        if [ -f "$TG_BLACKLIST" ] && [ -s "$TG_BLACKLIST" ]; then
            echo -e "${CYAN}Заблокированные ID:${NC}"
            cat "$TG_BLACKLIST"
        else
            echo -e "${MAGENTA}Список пуст.${NC}"
        fi
        echo ""
        echo -e " 1) ➕ Добавить ID"
        echo -e " 2) 🗑️  Удалить ID"
        echo -e " 3) 🧹 Очистить список"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-3]: " bchoice

        case $bchoice in
            1)
                read -p "Telegram ID: " id
                [ -n "$id" ] && echo "$id" >> "$TG_BLACKLIST" && \
                    echo -e "${GREEN}✅ Добавлено${NC}" && sleep 1
                ;;
            2)
                read -p "Telegram ID для удаления: " id
                if [ -f "$TG_BLACKLIST" ]; then
                    sed -i "/^${id}$/d" "$TG_BLACKLIST"
                    echo -e "${GREEN}✅ Удалено${NC}"
                    sleep 1
                fi
                ;;
            3)
                read -p "Очистить весь чёрный список? (y/n): " c
                [[ "$c" =~ ^[Yy]$ ]] && > "$TG_BLACKLIST" && \
                    echo -e "${GREEN}✅ Очищено${NC}" && sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

tg_test_bot() {
    header
    echo -e "${YELLOW}--- 🧪 Тест бота ---${NC}"
    echo ""

    local token=$(tg_get_config "BOT_TOKEN")
    if [ -z "$token" ]; then
        echo -e "${RED}❌ Токен не задан${NC}"
        read -p "Enter..."
        return
    fi

    echo -e "${CYAN}Отправляем запрос к Telegram API...${NC}"
    local response=$(curl -s --max-time 10 "https://api.telegram.org/bot${token}/getMe")
    local ok=$(echo "$response" | grep -o '"ok":true')

    if [ -n "$ok" ]; then
        local username=$(echo "$response" | grep -oP '"username":"\K[^"]+')
        local name=$(echo "$response" | grep -oP '"first_name":"\K[^"]+')
        echo ""
        echo -e "${GREEN}✅ Бот работает!${NC}"
        echo -e " Имя     : ${CYAN}$name${NC}"
        echo -e " Username: ${CYAN}@$username${NC}"
    else
        echo ""
        echo -e "${RED}❌ Ошибка: неверный токен${NC}"
        echo "$response" | head -5
    fi
    echo ""
    read -p "Нажмите Enter..."
}

tg_edit_welcome_file() {
    header
    echo -e "${YELLOW}--- ✏️  Редактирование приветствия ---${NC}"
    echo -e "${CYAN}Файл: /etc/UDPCustom/welcome.txt${NC}"
    echo -e "${CYAN}Поддерживает обычные переносы строк.${NC}"
    echo ""
    sleep 1
    if command -v nano >/dev/null 2>&1; then
        nano /etc/UDPCustom/welcome.txt
    elif command -v vi >/dev/null 2>&1; then
        vi /etc/UDPCustom/welcome.txt
    else
        echo -e "${YELLOW}nano не найден. Устанавливаем...${NC}"
        apt-get update -qq && apt-get install -y nano
        nano /etc/UDPCustom/welcome.txt
    fi
    systemctl restart vpn-tg-bot 2>/dev/null
    echo -e "${GREEN}✅ Сохранено, бот перезапущен${NC}"
    read -p "Enter..."
}

tg_channels_menu() {
    local CH_FILE="/etc/UDPCustom/channels.txt"
    [ ! -f "$CH_FILE" ] && touch "$CH_FILE"
    while true; do
        header
        echo -e "${YELLOW}📢 УПРАВЛЕНИЕ КАНАЛАМИ${NC}"
        echo ""
        local count=$(grep -c '^[^#]' "$CH_FILE" 2>/dev/null || echo 0)
        [ -z "$count" ] && count=0
        echo -e " Всего каналов: ${GREEN}$count${NC}"
        echo ""
        if [ "$count" -gt 0 ]; then
            echo -e "${CYAN}Список:${NC}"
            local i=1
            while IFS= read -r line; do
                [ -z "$line" ] && continue
                [ "${line:0:1}" == "#" ] && continue
                printf " ${GREEN}%2d)${NC} %s\n" "$i" "$line"
                ((i++))
            done < "$CH_FILE"
        else
            echo -e "${MAGENTA}Список пуст.${NC}"
        fi
        echo ""
        echo -e " 1) ➕ Добавить канал"
        echo -e " 2) 🗑️  Удалить по номеру"
        echo -e " 3) 🧹 Очистить всё"
        echo -e " 4) 🔄 Вкл/выкл проверку подписки"
        echo -e " 5) 👁️  Показать текущий файл"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-5]: " chchoice
        case $chchoice in
            1)
                echo ""
                read -p "Username канала (например @MyChannel): " newch
                [ -z "$newch" ] && continue
                newch=$(echo "$newch" | tr -d ' ')
                # Добавляем @ если нет
                [[ "$newch" != @* ]] && newch="@$newch"
                echo "$newch" >> "$CH_FILE"
                sort -u "$CH_FILE" -o "$CH_FILE"
                echo -e "${GREEN}✅ Добавлено: $newch${NC}"
                sleep 1
                ;;
            2)
                echo ""
                read -p "Номер для удаления (0 = отмена): " num
                [[ "$num" == "0" || -z "$num" ]] && continue
                if ! [[ "$num" =~ ^[0-9]+$ ]]; then
                    echo -e "${RED}Неверный номер${NC}"; sleep 1; continue
                fi
                sed -i "${num}d" "$CH_FILE"
                sed -i '/^\s*$/d' "$CH_FILE"
                echo -e "${GREEN}✅ Удалено${NC}"
                sleep 1
                ;;
            3)
                read -p "Очистить весь список? (y/n): " cfm
                [[ "$c" =~ ^[Yy]$ ]] || [[ "$cfm" =~ ^[Yy]$ ]] && > "$CH_FILE" && \
                    echo -e "${GREEN}✅ Очищено${NC}" && sleep 1
                ;;
            4)
                local cur=$(tg_get_config "REQUIRE_SUBSCRIPTION")
                if [ "$cur" == "1" ]; then
                    tg_set_config "REQUIRE_SUBSCRIPTION" "0"
                    echo -e "${YELLOW}Проверка подписки выключена${NC}"
                else
                    tg_set_config "REQUIRE_SUBSCRIPTION" "1"
                    echo -e "${GREEN}Проверка подписки включена${NC}"
                fi
                sleep 1
                ;;
            5)
                echo ""
                cat "$CH_FILE"
                echo ""
                read -p "Enter..."
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

menu_tgbot() {
    while true; do
        header
        echo -e "${YELLOW}🤖 TELEGRAM-БОТ${NC}"
        echo ""
        echo -e " Статус   : $(tg_bot_status)"

        local token=$(tg_get_config "BOT_TOKEN")
        local admin=$(tg_get_config "ADMIN_ID")
        local channel=$(tg_get_config "CHANNEL_ID")
        local require_sub=$(tg_get_config "REQUIRE_SUBSCRIPTION")
        local cooldown=$(tg_get_config "COOLDOWN_HOURS")

        if [ -n "$token" ]; then
            echo -e " Токен    : ${GREEN}✅ настроен${NC}"
        else
            echo -e " Токен    : ${RED}❌ не задан${NC}"
        fi

        if [ -n "$admin" ]; then
            echo -e " Admin ID : ${CYAN}$admin${NC}"
        else
            echo -e " Admin ID : ${RED}❌ не задан${NC}"
        fi

        local ch_count=0
        [ -f "/etc/UDPCustom/channels.txt" ] && ch_count=$(grep -c '^[^#]' /etc/UDPCustom/channels.txt 2>/dev/null)
        [ -z "$ch_count" ] && ch_count=0
        echo -e " Каналов  : ${CYAN}$ch_count${NC}"

        [ "$require_sub" == "1" ] && RS="${GREEN}🟢 Да${NC}" || RS="${RED}🔴 Нет${NC}"
        echo -e " Проверка : $RS"
        echo -e " Кулдаун  : ${CYAN}${cooldown} ч${NC}"

        local issued_count=0
        [ -f "$TG_ISSUED" ] && issued_count=$(wc -l < "$TG_ISSUED" 2>/dev/null || echo 0)
        echo -e " Выдано   : ${GREEN}$issued_count${NC}"
        echo ""
        echo -e "${CYAN}─── 📊 Управление ───${NC}"
        echo -e " 1) 🚀 Запустить бота"
        echo -e " 2) 🔄 Перезапустить"
        echo -e " 3) 🛑 Остановить"
        echo -e " 4) 🧪 Тест (проверка токена)"
        echo -e " 5) 📜 Логи бота"
        echo ""
        echo -e "${CYAN}─── ⚙️  Настройки ───${NC}"
        echo -e " 6) ⚙️  Установка / первичная настройка"
        echo -e " 7) 🔑 Изменить BOT_TOKEN"
        echo -e " 8) 👤 Изменить ADMIN_ID"
        echo -e " 9) 📢 Управление каналами (список)"
        echo -e " 10) 🔄 Вкл/выкл проверку подписки"
        echo ""
        echo -e "${CYAN}─── ✏️  Тексты ───${NC}"
        echo -e " 11) ✏️  Текст /start (nano)"
        echo -e " 12) ✏️  Текст «Подпишись» (nano)"
        echo -e " 13) ✏️  Шаблон выдачи"
        echo -e " 14) ⏰ Кулдаун / срок / лимиты"
        echo ""
        echo -e "${CYAN}─── 📋 Просмотр ───${NC}"
        echo -e " 15) 📊 Выданные тесты"
        echo -e " 16) 🚫 Чёрный список"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-16]: " tg_choice

        case $tg_choice in
            1) systemctl restart "$TG_SERVICE" 2>/dev/null; sleep 1; systemctl is-active --quiet "$TG_SERVICE" && echo -e "${GREEN}✅ Бот запущен${NC}" || echo -e "${RED}❌ Ошибка${NC}"; sleep 1 ;;
            2) systemctl restart "$TG_SERVICE" 2>/dev/null; echo -e "${GREEN}Бот перезапущен${NC}"; sleep 1 ;;
            3) systemctl stop "$TG_SERVICE" 2>/dev/null; echo -e "${YELLOW}Бот остановлен${NC}"; sleep 1 ;;
            4) tg_test_bot ;;
            5) tg_show_log ;;
            6) tg_install ;;
            7) tg_edit_field "BOT_TOKEN" "Токен бота (от @BotFather)" ;;
            8) tg_edit_field "ADMIN_ID" "Telegram ID админа (от @userinfobot)" ;;
            9) tg_channels_menu ;;
            10)
                local cur=$(tg_get_config "REQUIRE_SUBSCRIPTION")
                if [ "$cur" == "1" ]; then
                    tg_set_config "REQUIRE_SUBSCRIPTION" "0"
                    echo -e "${YELLOW}Проверка подписки выключена${NC}"
                else
                    tg_set_config "REQUIRE_SUBSCRIPTION" "1"
                    echo -e "${GREEN}Проверка подписки включена${NC}"
                fi
                sleep 1
                ;;
            11) tg_edit_start_file ;;
            12) tg_edit_welcome_file ;;
            13) tg_edit_field "SUCCESS_TEMPLATE" "Шаблон выдачи" ;;
            14)
                tg_edit_field "COOLDOWN_HOURS" "Кулдаун между тестами (часы)"
                tg_edit_field "TEST_HOURS" "Срок тестового (часы)"
                tg_edit_field "TEST_DEVICES" "Лимит устройств (шт)"
                tg_edit_field "TEST_TRAFFIC_GB" "Лимит трафика (ГБ)"
                ;;
            15) tg_show_issued ;;
            16) tg_blacklist ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
