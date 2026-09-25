#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ БАННЕРА (HTML через sshd Banner)
# ──────────────────────────────────────────────────────────────

BANNER_FILE="/etc/bannerssh"

banner_ensure_hook() {
    if ! grep -qE '^[[:space:]]*Banner' /etc/ssh/sshd_config; then
        echo "Banner $BANNER_FILE" >> /etc/ssh/sshd_config
    else
        current=$(grep -E '^[[:space:]]*Banner' /etc/ssh/sshd_config | head -1 | awk '{print $2}')
        [ "$current" != "$BANNER_FILE" ] && sed -i "s|^[[:space:]]*Banner.*|Banner $BANNER_FILE|" /etc/ssh/sshd_config
    fi

    if [ -f /etc/default/dropbear ]; then
        grep -q "DROPBEAR_BANNER" /etc/default/dropbear 2>/dev/null || \
            echo "DROPBEAR_BANNER=\"$BANNER_FILE\"" >> /etc/default/dropbear
    fi

    [ ! -f "$BANNER_FILE" ] && touch "$BANNER_FILE"
}

banner_restart() {
    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
    [ -f /etc/default/dropbear ] && systemctl restart dropbear 2>/dev/null
}

banner_add_line() {
    header
    echo -e "${YELLOW}--- ➕ Добавить строку баннера ---${NC}"
    echo ""

    read -p "Введите текст строки: " msg
    [ -z "$msg" ] && { echo -e "${RED}Пустой текст — отмена.${NC}"; sleep 1; return; }

    echo ""
    echo -e "${CYAN}Размер шрифта:${NC}"
    echo " 1) Маленький (h6)"
    echo " 2) Средний (h5)"
    echo " 3) Крупный (h4)"
    echo " 4) Огромный (h3)"
    read -p "Выбор [1-4]: " sz

    case $sz in
        1) _size='6' ;;
        2) _size='5' ;;
        3) _size='4' ;;
        4) _size='3' ;;
        *) _size='6' ;;
    esac

    echo ""
    echo -e "${CYAN}Цвет:${NC}"
    echo " 1) 🔵 Синий        (blue)"
    echo " 2) 🟢 Зелёный      (green)"
    echo " 3) 🔴 Красный      (red)"
    echo " 4) 🟡 Жёлтый       (yellow)"
    echo " 5) 🌸 Розовый      (#F535AA)"
    echo " 6) 💎 Голубой      (cyan)"
    echo " 7) 🟠 Оранжевый    (#FF7F00)"
    echo " 8) 🟣 Фиолетовый   (#9932CD)"
    echo " 9) ⚫ Чёрный       (black)"
    echo " 10) ⚪ Без цвета"
    read -p "Выбор [1-10]: " col

    case $col in
        1|01) _font="<font color='blue'>" ;;
        2|02) _font="<font color='green'>" ;;
        3|03) _font="<font color='red'>" ;;
        4|04) _font="<font color='yellow'>" ;;
        5|05) _font="<font color='#F535AA'>" ;;
        6|06) _font="<font color='cyan'>" ;;
        7|07) _font="<font color='#FF7F00'>" ;;
        8|08) _font="<font color='#9932CD'>" ;;
        9|09) _font="<font color='black'>" ;;
        10)   _font="" ;;
        *)    _font="<font color='green'>" ;;
    esac

    if [ -z "$_font" ]; then
        echo "<h${_size}>${msg}</h${_size}>" >> "$BANNER_FILE"
    else
        echo "<h${_size}>${_font}${msg}</font></h${_size}>" >> "$BANNER_FILE"
    fi

    banner_restart
    echo ""
    echo -e "${GREEN}✅ Строка добавлена и применена!${NC}"
    read -p "Нажмите Enter..."
}

banner_show() {
    header
    echo -e "${YELLOW}--- 👁️  Текущий баннер ---${NC}"
    echo ""
    if [ ! -s "$BANNER_FILE" ]; then
        echo -e "${MAGENTA}Баннер пуст.${NC}"
    else
        echo -e "${CYAN}HTML-содержимое ${BANNER_FILE}:${NC}"
        echo -e "${CYAN}────────────────────────────────────${NC}"
        cat "$BANNER_FILE"
        echo -e "${CYAN}────────────────────────────────────${NC}"
    fi
    echo ""
    read -p "Нажмите Enter..."
}

banner_edit_raw() {
    header
    echo -e "${YELLOW}--- ✏️  Редактирование вручную ---${NC}"
    echo -e "${CYAN}Файл: $BANNER_FILE${NC}"
    sleep 1

    if command -v nano >/dev/null 2>&1; then
        nano "$BANNER_FILE"
    elif command -v vim >/dev/null 2>&1; then
        vim "$BANNER_FILE"
    elif command -v vi >/dev/null 2>&1; then
        vi "$BANNER_FILE"
    else
        echo -e "${YELLOW}nano не найден. Устанавливаем...${NC}"
        apt-get update -qq && apt-get install -y nano
        nano "$BANNER_FILE"
    fi

    banner_restart
    echo -e "${GREEN}✅ Сохранено и применено.${NC}"
    read -p "Нажмите Enter..."
}

banner_clear() {
    header
    echo -e "${YELLOW}--- 🗑️  Очистить баннер ---${NC}"
    read -p "Удалить весь баннер? (y/n): " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        > "$BANNER_FILE"
        banner_restart
        echo -e "${GREEN}✅ Баннер очищен.${NC}"
    fi
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# ШАБЛОНЫ (русский язык, уменьшенный шрифт)
# ──────────────────────────────────────────────────────────────

banner_template_arsen() {
    header
    echo -e "${YELLOW}--- 📋 Шаблон «ArsenVipKeys Премиум» (рус) ---${NC}"
    echo ""
    echo -e "${CYAN}Установить этот шаблон? (y/n):${NC}"
    read -p "→ " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        cat > "$BANNER_FILE" << 'EOF'
<h5><font color='cyan'>🚀 ArsenVipKeys — Премиум Сервер 🚀</font></h5>
<h6><font color='red'>❌ БЕЗ DDOS ❌</font></h6>
<h6><font color='red'>❌ БЕЗ ВЗЛОМА ❌</font></h6>
<h6><font color='red'>❌ БЕЗ ТОРРЕНТОВ ❌</font></h6>
<h6><font color='red'>❌ БЕЗ СПАМА ❌</font></h6>
<h6><font color='red'>❌ БЕЗ КАРДИНГА ❌</font></h6>
<h6><font color='#F535AA'>👥 МАКС. 1 УСТРОЙСТВ 👥</font></h6>
<h6><font color='yellow'>🚫 НАРУШЕНИЕ = БАН НАВСЕГДА 🚫</font></h6>
<h5><font color='green'>💬 Поддержка: t.me/ArsenGuro</font></h5>
<h5><font color='cyan'>📢 Канал: t.me/ArsenVipKeys</font></h5>
EOF
        banner_restart
        echo -e "${GREEN}✅ Шаблон установлен!${NC}"
    fi
    read -p "Нажмите Enter..."
}

banner_template_minimal() {
    header
    echo -e "${YELLOW}--- 📋 Шаблон «Минимальный» (рус) ---${NC}"
    echo ""
    read -p "Установить этот шаблон? (y/n): " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        cat > "$BANNER_FILE" << 'EOF'
<h5><font color='cyan'>⚡ Добро пожаловать в ArsenVipKeys ⚡</font></h5>
<h6><font color='green'>🌐 Быстро • Безопасно • Анонимно</font></h6>
<h6><font color='yellow'>💬 Поддержка: t.me/ArsenGuro</font></h6>
<h6><font color='cyan'>📢 Канал: t.me/ArsenVipKeys</font></h6>
EOF
        banner_restart
        echo -e "${GREEN}✅ Установлено!${NC}"
    fi
    read -p "Нажмите Enter..."
}

banner_template_strict() {
    header
    echo -e "${YELLOW}--- 📋 Шаблон «Строгий» (только правила) ---${NC}"
    echo ""
    read -p "Установить этот шаблон? (y/n): " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        cat > "$BANNER_FILE" << 'EOF'
<h5><font color='yellow'>⚠️ ПРАВИЛА ИСПОЛЬЗОВАНИЯ СЕРВЕРА ⚠️</font></h5>
<h6><font color='red'>❌ Запрещены DDOS-атаки</font></h6>
<h6><font color='red'>❌ Запрещён взлом и брутфорс</font></h6>
<h6><font color='red'>❌ Запрещён торрент-трафик</font></h6>
<h6><font color='red'>❌ Запрещён спам и кардинг</font></h6>
<h6><font color='#F535AA'>👥 Лимит устройств: 1</font></h6>
<h6><font color='yellow'>🚫 При нарушении — бан без предупреждения</font></h6>
<h5><font color='green'>💬 @ArsenGuro</font></h5>
EOF
        banner_restart
        echo -e "${GREEN}✅ Установлено!${NC}"
    fi
    read -p "Нажмите Enter..."
}

banner_template_english() {
    header
    echo -e "${YELLOW}--- 📋 Шаблон «English Premium» ---${NC}"
    echo ""
    read -p "Установить этот шаблон? (y/n): " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        cat > "$BANNER_FILE" << 'EOF'
<h5><font color='cyan'>🚀 ArsenVipKeys Premium Server 🚀</font></h5>
<h6><font color='red'>❌ NO DDOS ❌</font></h6>
<h6><font color='red'>❌ NO HACKING ❌</font></h6>
<h6><font color='red'>❌ NO TORRENT ❌</font></h6>
<h6><font color='red'>❌ NO SPAMMING ❌</font></h6>
<h6><font color='red'>❌ NO CARDING ❌</font></h6>
<h6><font color='#F535AA'>👥 MAX LOGIN 1 DEVICE 👥</font></h6>
<h6><font color='yellow'>🚫 VIOLATE AUTO BANNED PERMANENT 🚫</font></h6>
<h5><font color='green'>💬 Support: t.me/ArsenGuro</font></h5>
<h5><font color='cyan'>📢 Channel: t.me/ArsenVipKeys</font></h5>
EOF
        banner_restart
        echo -e "${GREEN}✅ Установлено!${NC}"
    fi
    read -p "Нажмите Enter..."
}

banner_ensure_hook

menu_banner() {
    while true; do
        header
        echo -e "${YELLOW}🎨 БАННЕР ПРИ ПОДКЛЮЧЕНИИ (HTML)${NC}"
        echo ""
        local lines=$(wc -l < "$BANNER_FILE" 2>/dev/null || echo 0)
        if [ "$lines" -gt 0 ]; then
            echo -e " Статус: ${GREEN}🟢 Активен ($lines строк)${NC}"
        else
            echo -e " Статус: ${RED}🔴 Пуст${NC}"
        fi
        echo ""
        echo -e " 1) ➕ Добавить строку (текст + размер + цвет)"
        echo -e " 2) 👁️  Показать текущий баннер"
        echo -e " 3) ✏️  Редактировать вручную (nano/vi)"
        echo -e "${CYAN}── Шаблоны ──${NC}"
        echo -e " 4) 📋 «ArsenVipKeys Премиум» (рус)"
        echo -e " 5) 📋 «Минимальный» (рус)"
        echo -e " 6) 📋 «Строгий» (только правила)"
        echo -e " 7) 📋 «English Premium»"
        echo -e "${CYAN}────────────${NC}"
        echo -e " 8) 🗑️  Очистить баннер"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-8]: " bchoice

        case $bchoice in
            1) banner_add_line ;;
            2) banner_show ;;
            3) banner_edit_raw ;;
            4) banner_template_arsen ;;
            5) banner_template_minimal ;;
            6) banner_template_strict ;;
            7) banner_template_english ;;
            8) banner_clear ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
