#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ БАННЕРА ПРИ ПОДКЛЮЧЕНИИ
# Позволяет менять текст, цвета и параметры баннера,
# который показывается клиенту при подключении.
# ──────────────────────────────────────────────────────────────

BANNER_CONFIG="/etc/UDPCustom/banner.conf"
BANNER_SCRIPT="/usr/local/bin/show-welcome"

# Значения по умолчанию
banner_default_config() {
    cat << 'EOF' > "$BANNER_CONFIG"
# Настройки баннера при подключении
# 1 = включено, 0 = выключено
ENABLED=1
USE_COLORS=1
SHOW_USER=1
SHOW_LIMIT=1
SHOW_ONLINE=1

# Текст баннера (поддерживает $USER, $LIMIT, $COUNT)
TITLE="⚡ ULTIMATE VPN CONTROL PANEL ⚡"
WELCOME="Добро пожаловать на защищённый сервер!"
LINE1="🌐  Быстро • Безопасно • Анонимно"
LINE2="📞  Поддержка: @your_telegram"
EOF
}

# Создаём конфиг если нет
[ ! -f "$BANNER_CONFIG" ] && banner_default_config

# Загружаем конфиг
load_banner_config() {
    source "$BANNER_CONFIG"
    ENABLED="${ENABLED:-1}"
    USE_COLORS="${USE_COLORS:-1}"
    SHOW_USER="${SHOW_USER:-1}"
    SHOW_LIMIT="${SHOW_LIMIT:-1}"
    SHOW_ONLINE="${SHOW_ONLINE:-1}"
    TITLE="${TITLE:-⚡ ULTIMATE VPN CONTROL PANEL ⚡}"
    WELCOME="${WELCOME:-Добро пожаловать!}"
    LINE1="${LINE1:-Быстро • Безопасно • Анонимно}"
    LINE2="${LINE2:-Поддержка: @your_telegram}"
}

# Генерация скрипта show-welcome на основе конфига
generate_banner_script() {
    load_banner_config

    cat << 'BANNER_EOF' > "$BANNER_SCRIPT"
#!/bin/bash
# Автоматически сгенерировано панелью VPN
USER="$PAM_USER"
CONFIG="/etc/UDPCustom/banner.conf"

[ "$USER" == "root" ] && exit 0
[ -z "$USER" ] && exit 0

[ ! -f "$CONFIG" ] && exit 0
source "$CONFIG"

[ "$ENABLED" != "1" ] && exit 0

# Считаем лимит
LIMITS_DIR="/etc/UDPCustom/limits"
LIMIT=3
[ -f "$LIMITS_DIR/$USER" ] && LIMIT=$(cat "$LIMITS_DIR/$USER")

# Считаем онлайн
WS_P=""
[ -f /usr/local/bin/ws-proxy.py ] && \
    WS_P=$(awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py | tr -dc '0-9')

FILTER="( sport = :22 or sport = :36712 or sport = :7300"
[[ "$WS_P" =~ ^[0-9]+$ ]] && FILTER="$FILTER or sport = :$WS_P"
FILTER="$FILTER )"

COUNT=0
while IFS= read -r line; do
    [ -z "$line" ] && continue
    pids=$(echo "$line" | grep -oP 'pid=\K[0-9]+' 2>/dev/null)
    [ -z "$pids" ] && continue
    for p in $pids; do
        owner=$(ps -o user= -p "$p" 2>/dev/null | tr -d ' ')
        if [ -n "$owner" ] && [ "$owner" != "root" ]; then
            [ "$owner" == "$USER" ] && COUNT=$((COUNT + 1))
            break
        fi
    done
done <<< "$(ss -H -tnp state established "$FILTER" 2>/dev/null)"

# Цвета
if [ "$USE_COLORS" == "1" ]; then
    G='\033[1;32m'; Y='\033[1;33m'; C='\033[1;36m'
    W='\033[1;37m'; M='\033[1;35m'; N='\033[0m'
else
    G=''; Y=''; C=''; W=''; M=''; N=''
fi

echo ""
echo -e "${G}${TITLE}${N}"
echo ""
echo -e "${C}${WELCOME}${N}"
echo ""

[ "$SHOW_USER" == "1" ] && echo -e "${W}👤  Пользователь   : ${Y}${USER}${N}"
[ "$SHOW_LIMIT" == "1" ] && echo -e "${W}📱  Лимит устройств : ${Y}${LIMIT}${N}"
[ "$SHOW_ONLINE" == "1" ] && echo -e "${W}🔗  Сейчас онлайн   : ${Y}${COUNT}${N}"

echo ""
[ -n "$LINE1" ] && echo -e "${G}${LINE1}${N}"
[ -n "$LINE2" ] && echo -e "${M}${LINE2}${N}"
echo ""
exit 0
BANNER_EOF

    chmod +x "$BANNER_SCRIPT"
}

# ──────────────────────────────────────────────────────────────
# UI меню
# ──────────────────────────────────────────────────────────────

edit_field() {
    local field_name="$1"
    local field_desc="$2"
    load_banner_config
    local current=$(grep "^${field_name}=" "$BANNER_CONFIG" | cut -d'=' -f2- | tr -d '"')

    echo ""
    echo -e "${CYAN}Редактирование: ${YELLOW}$field_desc${NC}"
    echo -e "${CYAN}Текущее значение: ${GREEN}$current${NC}"
    echo ""
    read -p "Новое значение (Enter — оставить): " new_val
    [ -z "$new_val" ] && return

    # Экранируем кавычки
    new_val=$(echo "$new_val" | sed 's/"/\\"/g')
    sed -i "s|^${field_name}=.*|${field_name}=\"${new_val}\"|" "$BANNER_CONFIG"
    generate_banner_script
    echo -e "${GREEN}✅ Сохранено.${NC}"
    sleep 1
}

toggle_option() {
    local field_name="$1"
    local field_desc="$2"
    load_banner_config
    local current=$(grep "^${field_name}=" "$BANNER_CONFIG" | cut -d'=' -f2)
    [ -z "$current" ] && current=0

    if [ "$current" == "1" ]; then
        sed -i "s|^${field_name}=.*|${field_name}=0|" "$BANNER_CONFIG"
        echo -e "${YELLOW}⏸️  ${field_desc}: ВЫКЛЮЧЕНО${NC}"
    else
        sed -i "s|^${field_name}=.*|${field_name}=1|" "$BANNER_CONFIG"
        echo -e "${GREEN}▶️  ${field_desc}: ВКЛЮЧЕНО${NC}"
    fi
    generate_banner_script
    sleep 1
}

preview_banner() {
    header
    echo -e "${YELLOW}--- 👁️  Предпросмотр баннера ---${NC}"
    echo ""
    echo -e "${CYAN}────────────────────────────────────────────────────${NC}"
    # Симулируем вывод
    PAM_USER="preview_user" bash "$BANNER_SCRIPT"
    echo -e "${CYAN}────────────────────────────────────────────────────${NC}"
    echo ""
    read -p "Нажмите Enter для продолжения..."
}

menu_banner() {
    while true; do
        header
        load_banner_config

        echo -e "${YELLOW}🎨 УПРАВЛЕНИЕ БАННЕРОМ ПРИ ПОДКЛЮЧЕНИИ${NC}"
        echo ""
        if [ "$ENABLED" == "1" ]; then
            echo -e " Статус         : ${GREEN}🟢 Включен${NC}"
        else
            echo -e " Статус         : ${RED}🔴 Выключен${NC}"
        fi
        [ "$USE_COLORS" == "1" ] && CS="${GREEN}🟢 Да${NC}" || CS="${RED}🔴 Нет${NC}"
        [ "$SHOW_USER" == "1" ] && US="${GREEN}🟢 Да${NC}" || US="${RED}🔴 Нет${NC}"
        [ "$SHOW_LIMIT" == "1" ] && LS="${GREEN}🟢 Да${NC}" || LS="${RED}🔴 Нет${NC}"
        [ "$SHOW_ONLINE" == "1" ] && OS="${GREEN}🟢 Да${NC}" || OS="${RED}🔴 Нет${NC}"

        echo -e " Цвета ANSI     : $CS"
        echo -e " Показ юзера    : $US"
        echo -e " Показ лимита   : $LS"
        echo -e " Показ онлайна  : $OS"
        echo ""
        echo -e "${CYAN}── Текущий текст ──${NC}"
        echo -e "  ${GREEN}Заголовок${NC} : $TITLE"
        echo -e "  ${GREEN}Приветствие${NC}: $WELCOME"
        echo -e "  ${GREEN}Строка 1${NC}  : $LINE1"
        echo -e "  ${GREEN}Строка 2${NC}  : $LINE2"
        echo -e "${CYAN}───────────────────${NC}"
        echo ""
        echo -e " 1) 🔛 Включить / Выключить баннер"
        echo -e " 2) 🎨 Включить / Выключить ANSI-цвета"
        echo -e " 3) ✏️  Изменить заголовок"
        echo -e " 4) ✏️  Изменить приветствие"
        echo -e " 5) ✏️  Изменить строку 1"
        echo -e " 6) ✏️  Изменить строку 2"
        echo -e " 7) 👤 Показ юзера   : Вкл/Выкл"
        echo -e " 8) 📱 Показ лимита  : Вкл/Выкл"
        echo -e " 9) 🔗 Показ онлайна : Вкл/Выкл"
        echo -e " 10) 👁️  Предпросмотр баннера"
        echo -e " 11) 🔄 Сброс к значениям по умолчанию"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-11]: " bchoice

        case $bchoice in
            1) toggle_option "ENABLED" "Баннер" ;;
            2) toggle_option "USE_COLORS" "ANSI-цвета" ;;
            3) edit_field "TITLE" "Заголовок" ;;
            4) edit_field "WELCOME" "Приветствие" ;;
            5) edit_field "LINE1" "Строка 1" ;;
            6) edit_field "LINE2" "Строка 2" ;;
            7) toggle_option "SHOW_USER" "Показ юзера" ;;
            8) toggle_option "SHOW_LIMIT" "Показ лимита" ;;
            9) toggle_option "SHOW_ONLINE" "Показ онлайна" ;;
            10) preview_banner ;;
            11)
                read -p "Сбросить баннер к значениям по умолчанию? (y/n): " c
                if [[ "$c" =~ ^[Yy]$ ]]; then
                    banner_default_config
                    generate_banner_script
                    echo -e "${GREEN}✅ Сброшено.${NC}"
                    sleep 1
                fi
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
