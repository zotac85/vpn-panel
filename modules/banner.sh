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
    echo " 2) Средний (h4)"
    echo " 3) Крупный (h3)"
    echo " 4) Огромный (h1)"
    read -p "Выбор [1-4]: " sz

    case $sz in
        1) _size='6' ;;
        2) _size='4' ;;
        3) _size='3' ;;
        4) _size='1' ;;
        *) _size='4' ;;
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
    echo -e "${YELLOW}--- ✏️  Редактирование вручную (nano) ---${NC}"
    echo -e "${CYAN}Открывается $BANNER_FILE${NC}"
    sleep 1
    nano "$BANNER_FILE"
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

banner_template_arsen() {
    header
    echo -e "${YELLOW}--- 📋 Шаблон «ArsenVipKeys Premium» ---${NC}"
    read -p "Установить этот шаблон? (y/n): " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        cat > "$BANNER_FILE" << 'EOF'
<h4><font color='cyan'>🚀 ArsenVipKeys Premium Server 🚀</font></h4>
<h6><font color='red'>❌ NO DDOS ❌</font></h6>
<h6><font color='red'>❌ NO HACKING ❌</font></h6>
<h6><font color='red'>❌ NO TORRENT ❌</font></h6>
<h6><font color='red'>❌ NO SPAMMING ❌</font></h6>
<h6><font color='red'>❌ NO CARDING ❌</font></h6>
<h6><font color='#F535AA'>👥 MAX LOGIN 2 DEVICE 👥</font></h6>
<h6><font color='yellow'>🚫 VIOLATE AUTO BANNED PERMANENT 🚫</font></h6>
<h4><font color='green'>💬 Support: t.me/ArsenGuro</font></h4>
<h4><font color='cyan'>📢 Channel: t.me/ArsenVipKeys</font></h4>
EOF
        banner_restart
        echo -e "${GREEN}✅ Шаблон установлен!${NC}"
    fi
    read -p "Нажмите Enter..."
}

banner_template_minimal() {
    header
    echo -e "${YELLOW}--- 📋 Шаблон «Минимальный» ---${NC}"
    read -p "Установить этот шаблон? (y/n): " c
    if [[ "$c" =~ ^[Yy]$ ]]; then
        cat > "$BANNER_FILE" << 'EOF'
<h3><font color='cyan'>⚡ Welcome to ArsenVipKeys ⚡</font></h3>
<h6><font color='green'>🌐 Fast • Secure • Anonymous</font></h6>
<h6><font color='yellow'>💬 Support: t.me/ArsenGuro</font></h6>
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
        echo -e " 3) ✏️  Редактировать вручную (nano)"
        echo -e " 4) 🎨 Шаблон «ArsenVipKeys Premium»"
        echo -e " 5) 🎨 Шаблон «Минимальный»"
        echo -e " 6) 🗑️  Очистить баннер"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-6]: " bchoice

        case $bchoice in
            1) banner_add_line ;;
            2) banner_show ;;
            3) banner_edit_raw ;;
            4) banner_template_arsen ;;
            5) banner_template_minimal ;;
            6) banner_clear ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
