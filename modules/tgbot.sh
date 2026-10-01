#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ TELEGRAM-БОТА
# ──────────────────────────────────────────────────────────────

TG_CONF="/etc/UDPCustom/bot.conf"
TG_SERVICE="vpn-tg-bot"
TG_BOT_SCRIPT="/usr/local/bin/vpn-tg-bot.py"
TG_LOG="/var/log/vpn-tg-bot.log"
TG_ISSUED="/etc/UDPCustom/bot_issued.db"
SG_CONF="/etc/UDPCustom/support_bot.conf"
SG_SERVICE="support-bot"
SG_LOG="/var/log/vpn-support-bot.log"
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
COOLDOWN_HOURS=8
TEST_HOURS=8
VERIFIED_MINUTES=60
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

# ──────────────────────────────────────────────────────────────
# ФУНКЦИИ БОТА ПОДДЕРЖКИ
# ──────────────────────────────────────────────────────────────
sg_get_config() {
    local field="$1"
    grep -oP "(?<=${field}=\")[^\"]*" "$SG_CONF" 2>/dev/null | head -1
}
sg_set_config() {
    local field="$1"
    local value="$2"
    if grep -q "^${field}=" "$SG_CONF" 2>/dev/null; then
        sed -i "s|^${field}=.*|${field}=\"${value}\"|" "$SG_CONF"
    else
        echo "${field}=\"${value}\"" >> "$SG_CONF"
    fi
    chmod 600 "$SG_CONF"
}
sg_edit_field() {
    local field="$1"
    local desc="$2"
    local current=$(sg_get_config "$field")
    echo ""
    echo -e "${CYAN}$desc${NC}"
    echo -e "Текущее: ${GREEN}${current:-не задано}${NC}"
    read -p "Новое значение (Enter — отмена): " new_val
    [ -z "$new_val" ] && return
    sg_set_config "$field" "$new_val"
    echo -e "${GREEN}✅  Сохранено${NC}"
    sleep 1
}
sg_install() {
    header
    echo -e "${YELLOW}--- 🚀 Установка бота поддержки ---${NC}"
    echo ""
    if [ ! -f /usr/local/bin/support-bot.py ]; then
        echo -e "${CYAN}Скачиваем support-bot.py...${NC}"
        curl -sf -o /usr/local/bin/support-bot.py "https://raw.githubusercontent.com/zotac85/vpn-panel/main/support/support-bot.py" && chmod +x /usr/local/bin/support-bot.py
    fi
    if [ ! -f /etc/systemd/system/support-bot.service ]; then
        cat > /etc/systemd/system/support-bot.service << 'SVC_EOF'
[Unit]
Description=VPN Support Telegram Bot
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /usr/local/bin/support-bot.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/vpn-support-bot.log
StandardError=append:/var/log/vpn-support-bot.log
[Install]
WantedBy=multi-user.target
SVC_EOF
        systemctl daemon-reload
    fi
    systemctl enable support-bot 2>/dev/null
    systemctl restart support-bot 2>/dev/null
    sleep 2
    if systemctl is-active --quiet support-bot; then
        echo -e "${GREEN}✅  Бот поддержки запущен${NC}"
    else
        echo -e "${RED}❌  Не запустился. Логи:${NC}"
        tail -n 10 /var/log/vpn-support-bot.log 2>/dev/null
    fi
    echo ""
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# СТАТИСТИКА
# ──────────────────────────────────────────────────────────────
tg_stats() {
    header
    echo -e "${YELLOW}📊 СТАТИСТИКА${NC}"
    echo ""
    local issued=$(wc -l < "$TG_ISSUED" 2>/dev/null || echo 0)
    echo -e " 🎁 Выдано тестов    : ${GREEN}${issued}${NC}"
    local users=$(grep -c . /etc/UDPCustom/users.db 2>/dev/null || echo 0)
    echo -e " 👥 Всего юзеров     : ${GREEN}${users}${NC}"
    local vips=$(grep -c "^vip_" /etc/UDPCustom/users.db 2>/dev/null || echo 0)
    echo -e " 💎 VIP-ключей       : ${GREEN}${vips}${NC}"
    local channels=$(grep -c '^[^#]' /etc/UDPCustom/channels.txt 2>/dev/null || echo 0)
    echo -e " 📢 Каналов          : ${GREEN}${channels}${NC}"
    local blacklist=0; [ -f "$TG_BLACKLIST" ] && blacklist=$(wc -l < "$TG_BLACKLIST" 2>/dev/null)
    echo -e " 🚫 В чёрном списке  : ${GREEN}${blacklist}${NC}"
    echo ""
    echo -e "${CYAN}Основной бот:${NC}"
    systemctl is-active --quiet "$TG_SERVICE" && echo -e "  Статус: ${GREEN}🟢 Запущен${NC}" || echo -e "  Статус: ${RED}🔴 Остановлен${NC}"
    echo -e "${CYAN}Бот поддержки:${NC}"
    systemctl is-active --quiet "$SG_SERVICE" 2>/dev/null && echo -e "  Статус: ${GREEN}🟢 Запущен${NC}" || echo -e "  Статус: ${RED}🔴 Остановлен${NC}"
    echo ""
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# ПОДМЕНЮ: ОСНОВНОЙ БОТ
# ──────────────────────────────────────────────────────────────
menu_tgbot_main() {
    while true; do
        header
        echo -e "${YELLOW}🤖 ОСНОВНОЙ БОТ${NC}"
        echo ""
        local token=$(tg_get_config "BOT_TOKEN")
        local admin=$(tg_get_config "ADMIN_ID")
        [ -n "$token" ] && echo -e " Токен    : ${GREEN}✅  настроен${NC}" || echo -e " Токен    : ${RED}❌  не задан${NC}"
        [ -n "$admin" ] && echo -e " Admin ID : ${CYAN}$admin${NC}" || echo -e " Admin ID : ${RED}❌  не задан${NC}"
        systemctl is-active --quiet "$TG_SERVICE" && echo -e " Статус   : ${GREEN}🟢 Запущен${NC}" || echo -e " Статус   : ${RED}🔴 Остановлен${NC}"
        echo ""
        echo -e " 1) 🔑 Изменить BOT_TOKEN"
        echo -e " 2) 👤 Изменить ADMIN_ID"
        echo -e " 3) 🚀 Полная установка / настройка"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-3]: " choice
        case $choice in
            1) tg_edit_field "BOT_TOKEN" "Токен бота (от @BotFather)" ;;
            2) tg_edit_field "ADMIN_ID" "Telegram ID админа (от @userinfobot)" ;;
            3) tg_install ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

# ──────────────────────────────────────────────────────────────
# ПОДМЕНЮ: БОТ ПОДДЕРЖКИ
# ──────────────────────────────────────────────────────────────
menu_tgbot_support() {
    while true; do
        header
        echo -e "${YELLOW}💬 БОТ ПОДДЕРЖКИ${NC}"
        echo ""
        local token=$(sg_get_config "BOT_TOKEN")
        local admin=$(sg_get_config "ADMIN_ID")
        [ -n "$token" ] && echo -e " Токен    : ${GREEN}✅  настроен${NC}" || echo -e " Токен    : ${RED}❌  не задан${NC}"
        [ -n "$admin" ] && echo -e " Admin ID : ${CYAN}$admin${NC}" || echo -e " Admin ID : ${RED}❌  не задан${NC}"
        systemctl is-active --quiet "$SG_SERVICE" 2>/dev/null && echo -e " Статус   : ${GREEN}🟢 Запущен${NC}" || echo -e " Статус   : ${RED}🔴 Остановлен${NC}"
        echo ""
        echo -e " 1) 🔑 Изменить BOT_TOKEN"
        echo -e " 2) 👤 Изменить ADMIN_ID"
        echo -e " 3) 🚀 Установка / переустановка сервиса"
        echo -e " 4) 🛑 Отключить (disable)"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-4]: " choice
        case $choice in
            1) sg_edit_field "BOT_TOKEN" "Токен бота поддержки (от @BotFather)" ;;
            2) sg_edit_field "ADMIN_ID" "Telegram ID админа (от @userinfobot)" ;;
            3) sg_install ;;
            4)
                systemctl stop "$SG_SERVICE" 2>/dev/null
                systemctl disable "$SG_SERVICE" 2>/dev/null
                echo -e "${YELLOW}Бот поддержки отключён${NC}"
                sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

# ──────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────
# ИИ-ПРОВЕРКА ЧЕКОВ (GEMINI)
# ──────────────────────────────────────────────────────────────
tg_test_gemini() {
    local key=$(tg_get_config "GEMINI_API_KEY")
    if [ -z "$key" ]; then
        echo -e "${RED}❌  GEMINI_API_KEY не задан${NC}"
        sleep 2
        return
    fi
    echo -e "${CYAN}Проверка Gemini API...${NC}"
    local resp=$(curl -s -X POST \
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key=${key}" \
        -H "Content-Type: application/json" \
        -d '{"contents":[{"parts":[{"text":"say OK"}]}]}' \
        --max-time 15 2>/dev/null)
    if echo "$resp" | grep -q '"text"\|"candidates"'; then
        echo -e "${GREEN}✅  Gemini API работает${NC}"
    else
        echo -e "${RED}❌  Ошибка Gemini${NC}"
        echo "$resp" | head -c 300
        echo ""
    fi
    sleep 2
}

menu_ai_settings() {
    while true; do
        header
        echo -e "${YELLOW}🧠 GEMINI — ИИ-ПРОВЕРКА ЧЕКОВ${NC}"
        echo ""
        local key=$(tg_get_config "GEMINI_API_KEY")
        if [ -n "$key" ]; then
            echo -e " Ключ : ${GREEN}✅  настроен${NC} (${#key} символов)"
        else
            echo -e " Ключ : ${RED}❌  не задан${NC}"
        fi
        echo ""
        echo -e "${CYAN}─── Действия ───${NC}"
        echo -e " 1) 🔑 Установить/изменить GEMINI_API_KEY"
        echo -e " 2) 🧪 Проверить API"
        echo -e " 3) 🗑  Очистить ключ"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-3]: " ai_choice
        case $ai_choice in
            1)
                echo ""
                echo -e "${CYAN}Получить ключ: https://aistudio.google.com/apikey${NC}"
                echo -e "Формат: начинается с ${YELLOW}AQ.${NC} или ${YELLOW}AIza${NC}"
                read -p "Вставь ключ (Enter — отмена): " new_key
                [ -z "$new_key" ] && continue
                tg_set_config "GEMINI_API_KEY" "$new_key"
                echo -e "${GREEN}✅  Сохранено${NC}"
                sleep 1
                ;;
            2) tg_test_gemini ;;
            3)
                tg_set_config "GEMINI_API_KEY" ""
                echo -e "${YELLOW}Ключ очищен${NC}"
                sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

# ──────────────────────────────────────────────────────────────
# ЛОГИ (SUPPORT-БОТ)
# ──────────────────────────────────────────────────────────────
menu_log_settings() {
    while true; do
        header
        echo -e "${YELLOW}📋 ЛОГИ — ОТДЕЛЬНЫЙ БОТ${NC}"
        echo ""
        local log_tok=$(tg_get_config "LOG_BOT_TOKEN")
        local log_chat=$(tg_get_config "LOG_CHAT_ID")
        if [ -n "$log_tok" ]; then
            echo -e " Токен : ${GREEN}✅  настроен${NC} (${#log_tok} символов)"
        else
            echo -e " Токен : ${RED}❌  не задан${NC}"
        fi
        if [ -n "$log_chat" ]; then
            echo -e " Chat  : ${CYAN}$log_chat${NC}"
        else
            echo -e " Chat  : ${RED}❌  не задан${NC}"
        fi
        echo ""
        echo -e "${CYAN}─── Действия ───${NC}"
        echo -e " 1) 🔑 Изменить LOG_BOT_TOKEN (токен support-бота)"
        echo -e " 2) 💬 Изменить LOG_CHAT_ID (куда шлём логи)"
        echo -e " 3) 🧪 Отправить тестовое сообщение"
        echo -e " 4) 🗑  Отключить логи (очистить оба поля)"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-4]: " lg_choice
        case $lg_choice in
            1)
                read -p "Токен support-бота (Enter — отмена): " nv
                [ -z "$nv" ] && continue
                tg_set_config "LOG_BOT_TOKEN" "$nv"
                echo -e "${GREEN}✅  Сохранено${NC}"
                sleep 1
                ;;
            2)
                read -p "Chat ID (например 1738878748): " nv
                [ -z "$nv" ] && continue
                tg_set_config "LOG_CHAT_ID" "$nv"
                echo -e "${GREEN}✅  Сохранено${NC}"
                sleep 1
                ;;
            3)
                local _t=$(tg_get_config "LOG_BOT_TOKEN")
                local _c=$(tg_get_config "LOG_CHAT_ID")
                if [ -z "$_t" ] || [ -z "$_c" ]; then
                    echo -e "${RED}❌  Заполни токен и chat_id${NC}"
                else
                    curl -s -X POST "https://api.telegram.org/bot${_t}/sendMessage" \
                        -d "chat_id=${_c}" \
                        -d "text=🧪 Тестовое сообщение из панели" \
                        --max-time 10 >/dev/null
                    echo -e "${GREEN}✅  Отправлено${NC}"
                fi
                sleep 2
                ;;
            4)
                tg_set_config "LOG_BOT_TOKEN" ""
                tg_set_config "LOG_CHAT_ID" ""
                echo -e "${YELLOW}Логи отключены${NC}"
                sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}


# ГЛАВНОЕ МЕНЮ TELEGRAM-БОТ
# ──────────────────────────────────────────────────────────────
menu_tgbot() {
    while true; do
        header
        echo -e "${YELLOW}🤖 TELEGRAM-БОТ${NC}"
        echo ""
        echo -e " Статус   : $(tg_bot_status)"
        local token=$(tg_get_config "BOT_TOKEN")
        local admin=$(tg_get_config "ADMIN_ID")
        local require_sub=$(tg_get_config "REQUIRE_SUBSCRIPTION")
        local cooldown=$(tg_get_config "COOLDOWN_HOURS")
        [ -n "$token" ] && echo -e " Токен    : ${GREEN}✅  настроен${NC}" || echo -e " Токен    : ${RED}❌  не задан${NC}"
        [ -n "$admin" ] && echo -e " Admin ID : ${CYAN}$admin${NC}" || echo -e " Admin ID : ${RED}❌  не задан${NC}"
        [ "$require_sub" == "1" ] && RS="${GREEN}🟢 Да${NC}" || RS="${RED}🔴 Нет${NC}"
        echo -e " Проверка : $RS"
        echo -e " Кулдаун  : ${CYAN}${cooldown} ч${NC}"
        echo ""
        echo -e "${CYAN}─── 📊 Управление ───${NC}"
        echo -e " 1) 🚀 Запустить бота"
        echo -e " 2) 🔄 Перезапустить"
        echo -e " 3) 🛑 Остановить"
        echo -e " 4) 🧪 Тест (проверка токена)"
        echo -e " 5) 📜 Логи бота"
        echo ""
        echo -e "${CYAN}─── ⚙️  Настройки ───${NC}"
        echo -e " 6) 🤖 Основной бот"
        echo -e " 7) 💬 Бот поддержки"
        echo -e " 8) 🔄 Вкл/выкл проверку подписки"
        echo -e " 9) ⏰ Кулдаун / срок / лимиты"
        echo -e " 11) 🧠 Gemini — ИИ-проверка чеков"
        echo ""
        echo -e "${CYAN}─── 📋 Просмотр ───${NC}"
        echo -e " 10) 📊 Статистика"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-11]: " tg_choice
        case $tg_choice in
            1) systemctl restart "$TG_SERVICE" 2>/dev/null; sleep 1; systemctl is-active --quiet "$TG_SERVICE" && echo -e "${GREEN}✅  Бот запущен${NC}" || echo -e "${RED}❌  Ошибка${NC}"; sleep 1 ;;
            2) systemctl restart "$TG_SERVICE" 2>/dev/null; echo -e "${GREEN}Бот перезапущен${NC}"; sleep 1 ;;
            3) systemctl stop "$TG_SERVICE" 2>/dev/null; echo -e "${YELLOW}Бот остановлен${NC}"; sleep 1 ;;
            4) tg_test_bot ;;
            5) tg_show_log ;;
            6) menu_tgbot_main ;;
            7) menu_tgbot_support ;;
            8)
                local cur=$(tg_get_config "REQUIRE_SUBSCRIPTION")
                if [ "$cur" == "1" ]; then
                    tg_set_config "REQUIRE_SUBSCRIPTION" "0"
                    echo -e "${YELLOW}Проверка подписки выключена${NC}"
                else
                    tg_set_config "REQUIRE_SUBSCRIPTION" "1"
                    echo -e "${GREEN}Проверка подписки включена${NC}"
                fi
                systemctl restart "$TG_SERVICE" 2>/dev/null
                sleep 1
                ;;
            9)
                tg_edit_field "COOLDOWN_HOURS" "Кулдаун между тестами (часы)"
                tg_edit_field "TEST_HOURS" "Срок тестового (часы)"
                tg_edit_field "VERIFIED_MINUTES" "Срок verified (минуты)"
                tg_edit_field "TEST_DEVICES" "Лимит устройств (шт)"
                tg_edit_field "TEST_TRAFFIC_GB" "Лимит трафика (ГБ)"
                systemctl restart "$TG_SERVICE" 2>/dev/null
                ;;
            10) tg_stats ;;
            11) menu_ai_settings ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
