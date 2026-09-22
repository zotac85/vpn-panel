#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ УПРАВЛЕНИЯ ДОМЕНОМ И ПРОКСИ
# ──────────────────────────────────────────────────────────────

DOMAIN_FILE="/etc/vpn-domain"
PROXY_FILE="/etc/UDPCustom/proxies.txt"

# ─── ДОМЕН ───
manage_domain() {
    while true; do
        header
        echo -e "${YELLOW}🌐 УПРАВЛЕНИЕ ДОМЕНОМ${NC}"
        echo ""

        local current=""
        [ -f "$DOMAIN_FILE" ] && current=$(cat "$DOMAIN_FILE" 2>/dev/null | tr -d '\n')

        if [ -n "$current" ]; then
            echo -e " Текущий домен: ${GREEN}$current${NC}"
        else
            echo -e " Текущий домен: ${RED}не задан${NC}"
        fi

        local ws_port=$(get_ws_port 2>/dev/null | tr -dc '0-9')
        [ -z "$ws_port" ] && ws_port="—"
        echo -e " WS-порт      : ${CYAN}$ws_port${NC}"
        echo ""
        echo -e " 1) ✏️  Изменить домен"
        echo -e " 2) 👁️  Показать текущий"
        echo -e " 3) 🧪 Проверить домен"
        echo -e " 4) 🗑️  Очистить"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-4]: " dchoice

        case $dchoice in
            1)
                echo ""
                read -p "Новый домен (без http:// и без порта): " new_domain
                [ -z "$new_domain" ] && continue
                new_domain=$(echo "$new_domain" | sed 's|https\?://||; s|/.*||; s|:.*||' | tr -d ' ')
                echo "$new_domain" > "$DOMAIN_FILE"
                echo -e "${GREEN}✅ Домен: $new_domain${NC}"
                sleep 1
                ;;
            2)
                echo ""
                cat "$DOMAIN_FILE" 2>/dev/null || echo -e "${MAGENTA}Не задан${NC}"
                echo ""
                read -p "Enter..."
                ;;
            3)
                echo ""
                if [ -z "$current" ]; then
                    echo -e "${RED}Домен не задан${NC}"
                else
                    echo -e "${CYAN}Ping $current...${NC}"
                    if ping -c 2 -W 2 "$current" >/dev/null 2>&1; then
                        echo -e "${GREEN}✅ Домен отвечает${NC}"
                        ping -c 1 -W 2 "$current" 2>/dev/null | grep -oP '\(\K[0-9.]+' | head -1
                    else
                        echo -e "${YELLOW}⚠️  ICMP не отвечает (может блокироваться)${NC}"
                    fi
                    echo ""
                    echo -e "${CYAN}DNS-резолв:${NC}"
                    getent hosts "$current" || nslookup "$current" 2>/dev/null | head -5
                fi
                echo ""
                read -p "Enter..."
                ;;
            4)
                read -p "Очистить домен? (y/n): " c
                [[ "$c" =~ ^[Yy]$ ]] && > "$DOMAIN_FILE" && echo -e "${GREEN}✅ Очищено${NC}" && sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

# ─── ПРОКСИ ───
manage_proxy() {
    while true; do
        header
        echo -e "${YELLOW}🔒 УПРАВЛЕНИЕ ПРОКСИ${NC}"
        echo ""

        local count=0
        [ -f "$PROXY_FILE" ] && count=$(grep -cve '^\s*$' "$PROXY_FILE" 2>/dev/null || echo 0)
        echo -e " Всего прокси: ${GREEN}$count${NC}"
        echo ""

        if [ "$count" -gt 0 ]; then
            echo -e "${CYAN}Список:${NC}"
            local i=1
            while IFS= read -r line; do
                [ -z "$line" ] && continue
                [ "${line:0:1}" == "#" ] && continue
                printf " ${GREEN}%2d)${NC} %s\n" "$i" "$line"
                ((i++))
            done < "$PROXY_FILE"
        else
            echo -e "${MAGENTA}Список пуст.${NC}"
        fi
        echo ""
        echo -e " 1) ➕ Добавить прокси"
        echo -e " 2) ➕ Массовый импорт (по одному на строку)"
        echo -e " 3) 🗑️  Удалить по номеру"
        echo -e " 4) 🧹 Очистить всё"
        echo -e " 5) 🎲 Показать случайный"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-5]: " pchoice

        case $pchoice in
            1)
                echo ""
                read -p "IP прокси (без порта): " ip
                [ -z "$ip" ] && continue
                ip=$(echo "$ip" | tr -d ' ')
                echo "$ip" >> "$PROXY_FILE"
                sort -u "$PROXY_FILE" -o "$PROXY_FILE"
                echo -e "${GREEN}✅ Добавлен: $ip${NC}"
                sleep 1
                ;;
            2)
                echo ""
                echo -e "${CYAN}Вставь список, по одному IP на строку.${NC}"
                echo -e "${CYAN}Когда закончишь — введи пустую строку и Enter.${NC}"
                echo ""
                local tmp=$(mktemp)
                while IFS= read -r line; do
                    [ -z "$line" ] && break
                    echo "$line" >> "$tmp"
                done
                cat "$tmp" >> "$PROXY_FILE"
                sort -u "$PROXY_FILE" -o "$PROXY_FILE"
                local added=$(wc -l < "$tmp")
                rm -f "$tmp"
                echo -e "${GREEN}✅ Добавлено строк: $added${NC}"
                sleep 2
                ;;
            3)
                echo ""
                read -p "Номер для удаления (0 = отмена): " num
                [[ "$num" == "0" || -z "$num" ]] && continue
                if ! [[ "$num" =~ ^[0-9]+$ ]]; then
                    echo -e "${RED}Неверный номер${NC}"; sleep 1; continue
                fi
                sed -i "${num}d" "$PROXY_FILE"
                sed -i '/^\s*$/d' "$PROXY_FILE"
                echo -e "${GREEN}✅ Удалено${NC}"
                sleep 1
                ;;
            4)
                read -p "Очистить весь список? (y/n): " c
                [[ "$c" =~ ^[Yy]$ ]] && > "$PROXY_FILE" && echo -e "${GREEN}✅ Очищено${NC}" && sleep 1
                ;;
            5)
                echo ""
                local random=$(grep -ve '^\s*$' "$PROXY_FILE" 2>/dev/null | shuf -n 1)
                if [ -n "$random" ]; then
                    echo -e "${GREEN}🎲 Случайный: $random:80${NC}"
                else
                    echo -e "${MAGENTA}Список пуст${NC}"
                fi
                echo ""
                read -p "Enter..."
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}

# ─── PAYLOAD ───
PAYLOAD_FILE="/etc/UDPCustom/payload.txt"

manage_payload() {
    while true; do
        header
        echo -e "${YELLOW}📦 УПРАВЛЕНИЕ PAYLOAD${NC}"
        echo ""

        local pl=""
        [ -f "$PAYLOAD_FILE" ] && pl=$(cat "$PAYLOAD_FILE" 2>/dev/null)
        local pl_len=${#pl}

        if [ -n "$pl" ]; then
            echo -e " Статус: ${GREEN}🟢 Задан${NC} (${CYAN}${pl_len}${NC} символов)"
            echo ""
            echo -e "${CYAN}Текущий payload:${NC}"
            echo -e "${GREEN}${pl}${NC}"
        else
            echo -e " Статус: ${RED}🔴 Не задан${NC}"
        fi
        echo ""
        echo -e " 1) ✏️  Изменить payload"
        echo -e " 2) 👁️  Показать текущий"
        echo -e " 3) 🔄 Сбросить на стандартный"
        echo -e " 4) 🗑️  Очистить"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-4]: " pchoice

        case $pchoice in
            1)
                echo ""
                echo -e "${CYAN}Вставь новый payload (в одну строку, Enter для сохранения):${NC}"
                read -r new_pl
                if [ -n "$new_pl" ]; then
                    echo "$new_pl" > "$PAYLOAD_FILE"
                    echo -e "${GREEN}✅ Payload сохранён (${#new_pl} символов)${NC}"
                else
                    echo -e "${RED}Пусто — отмена${NC}"
                fi
                sleep 2
                ;;
            2)
                echo ""
                cat "$PAYLOAD_FILE" 2>/dev/null || echo -e "${MAGENTA}Не задан${NC}"
                echo ""
                read -p "Enter..."
                ;;
            3)
                cat > "$PAYLOAD_FILE" << 'PL_EOF'
CONNECT http://co.nr HTTP/1.1[crlf]Host: www.icloud.com[crlf]User-Agent: microsoft.com[crlf][crlf]AN / HTTP/1.1[lf]Host: [host][lf]Connection: Upgrade[lf]Upgrade: websocket[crlf][crlf]
PL_EOF
                echo -e "${GREEN}✅ Сброшено на стандартный${NC}"
                sleep 1
                ;;
            4)
                read -p "Очистить payload? (y/n): " c
                [[ "$c" =~ ^[Yy]$ ]] && > "$PAYLOAD_FILE" && echo -e "${GREEN}✅ Очищено${NC}" && sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
