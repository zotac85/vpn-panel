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
TEST_DAYS=1
TEST_DEVICES=10
TEST_TRAFFIC_GB=100
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

        if [ -n "$channel" ]; then
            echo -e " Канал    : ${CYAN}$channel${NC}"
        else
            echo -e " Канал    : ${MAGENTA}не задан${NC}"
        fi

        [ "$require_sub" == "1" ] && RS="${GREEN}🟢 Да${NC}" || RS="${RED}🔴 Нет${NC}"
        echo -e " Проверка подписки : $RS"
        echo -e " Кулдаун  : ${CYAN}${cooldown} ч${NC}"

        local issued_count=0
        [ -f "$TG_ISSUED" ] && issued_count=$(wc -l < "$TG_ISSUED" 2>/dev/null || echo 0)
        echo -e " Выдано тестов : ${GREEN}$issued_count${NC}"
        echo ""
        echo -e "${CYAN}─── Настройки ───${NC}"
        echo -e " 1) ⚙️  Установка / первичная настройка"
        echo -e " 2) 🔑 Изменить BOT_TOKEN"
        echo -e " 3) 👤 Изменить ADMIN_ID"
        echo -e " 4) 📢 Изменить CHANNEL_ID"
        echo -e " 5) 🔄 Вкл/выкл проверку подписки"
        echo -e " 6) ✏️  Изменить текст приветствия"
        echo -e " 7) ✏️  Изменить шаблон выдачи"
        echo -e " 8) ⏰ Изменить кулдаун / срок / лимиты"
        echo ""
        echo -e "${CYAN}─── Управление ───${NC}"
        echo -e " 9) 🚀 Запустить бота"
        echo -e " 10) 🛑 Остановить"
        echo -e " 11) 🔄 Перезапустить"
        echo -e " 12) 🧪 Тест (проверка токена)"
        echo ""
        echo -e "${CYAN}─── Просмотр ───${NC}"
        echo -e " 13) 📜 Логи бота"
        echo -e " 14) 📊 Выданные тесты"
        echo -e " 15) 🚫 Чёрный список"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-15]: " tg_choice

        case $tg_choice in
            1) tg_install ;;
            2) tg_edit_field "BOT_TOKEN" "Токен бота (от @BotFather)" ;;
            3) tg_edit_field "ADMIN_ID" "Telegram ID админа (от @userinfobot)" ;;
            4) tg_edit_field "CHANNEL_ID" "Канал для подписки (например @ArsenVipKeys)" ;;
            5)
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
            6) tg_edit_field "WELCOME_TEXT" "Текст приветствия" ;;
            7) tg_edit_field "SUCCESS_TEMPLATE" "Шаблон выдачи" ;;
            8)
                tg_edit_field "COOLDOWN_HOURS" "Кулдаун между тестами (часы)"
                tg_edit_field "TEST_DAYS" "Срок тестового (дни)"
                tg_edit_field "TEST_DEVICES" "Лимит устройств (шт)"
                tg_edit_field "TEST_TRAFFIC_GB" "Лимит трафика (ГБ)"
                ;;
            9)
                systemctl restart "$TG_SERVICE" 2>/dev/null
                sleep 1
                systemctl is-active --quiet "$TG_SERVICE" && \
                    echo -e "${GREEN}✅ Бот запущен${NC}" || \
                    echo -e "${RED}❌ Ошибка — проверь логи${NC}"
                sleep 1
                ;;
            10)
                systemctl stop "$TG_SERVICE" 2>/dev/null
                echo -e "${YELLOW}Бот остановлен${NC}"
                sleep 1
                ;;
            11)
                systemctl restart "$TG_SERVICE" 2>/dev/null
                echo -e "${GREEN}Бот перезапущен${NC}"
                sleep 1
                ;;
            12) tg_test_bot ;;
            13) tg_show_log ;;
            14) tg_show_issued ;;
            15) tg_blacklist ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
