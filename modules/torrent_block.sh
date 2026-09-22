#!/bin/bash

# ──────────────────────────────────────────────────────────────
# МОДУЛЬ БЛОКИРОВКИ ТОРРЕНТОВ
# Тройная защита:
#  1) Порты 6881-6889 (BitTorrent)
#  2) DPI по handshake "BitTorrent protocol" (в OUTPUT)
#  3) DNS-блокировка известных трекеров
# ──────────────────────────────────────────────────────────────

TORRENT_CHAIN="VPN_TORRENT"
TORRENT_LOG="/var/log/vpn-torrent-block.log"
HOSTS_BLOCK="/etc/hosts.vpn-torrent"

# Список популярных трекеров для блокировки (можно расширять)
TRACKERS_LIST=(
    "tracker.opentrackr.org"
    "tracker.torrent.eu.org"
    "opentracker.i2p.rocks"
    "tracker.openbittorrent.com"
    "tracker.moeking.me"
    "explodie.org"
    "tracker.dler.org"
    "open.demonii.com"
    "tracker.torrent.eu.org"
    "tracker.coppersurfer.tk"
    "tracker.leechers-paradise.org"
    "tracker.internetwarriors.net"
    "9.rarbg.to"
    "tracker.pirateparty.gr"
    "tracker.zooqle.com"
    "tracker.gbitt.info"
    "exodus.desync.com"
    "bt1.archive.org"
    "t1.pow7.com"
    "torrentclub.tech"
)

# ──────────────────────────────────────────────────────────────
# Статус — активна ли блокировка
# ──────────────────────────────────────────────────────────────
torrent_block_active() {
    iptables -L "$TORRENT_CHAIN" -n &>/dev/null
}

# ──────────────────────────────────────────────────────────────
# Создание цепочки iptables
# ──────────────────────────────────────────────────────────────
init_torrent_chain() {
    # Создаём цепочку
    iptables -N "$TORRENT_CHAIN" 2>/dev/null

    # Подключаем к OUTPUT (исходящий трафик)
    iptables -C OUTPUT -j "$TORRENT_CHAIN" 2>/dev/null || \
        iptables -I OUTPUT 1 -j "$TORRENT_CHAIN"

    # Флаг: проверяем, добавлены ли правила
    if iptables -L "$TORRENT_CHAIN" -n 2>/dev/null | grep -q "BitTorrent"; then
        return  # Уже настроено
    fi

    # ─── ПРАВИЛО 1: блокировка портов 6881-6889 (классические торрент-порты) ───
    iptables -A "$TORRENT_CHAIN" -p tcp --dport 6881:6889 \
        -m comment --comment "Torrent: classic ports" \
        -j LOG --log-prefix "VPN-TORRENT-PORT: " --log-level 4
    iptables -A "$TORRENT_CHAIN" -p tcp --dport 6881:6889 -j DROP
    iptables -A "$TORRENT_CHAIN" -p udp --dport 6881:6889 -j DROP

    # ─── ПРАВИЛО 2: блокировка DHT-портов ───
    iptables -A "$TORRENT_CHAIN" -p udp --dport 1337 -j DROP
    iptables -A "$TORRENT_CHAIN" -p udp --dport 2710 -j DROP

    # ─── ПРАВИЛО 3: DPI по строкам в пакете (BitTorrent handshake) ───
    # Handshake — "BitTorrent protocol" в открытом виде (для незашифрованных)
    iptables -A "$TORRENT_CHAIN" -p tcp -m string \
        --algo bm --string "BitTorrent protocol" \
        -m comment --comment "Torrent: handshake" \
        -j LOG --log-prefix "VPN-TORRENT-DPI: " --log-level 4
    iptables -A "$TORRENT_CHAIN" -p tcp -m string \
        --algo bm --string "BitTorrent protocol" -j DROP

    # uTP (BitTorrent over UDP)
    iptables -A "$TORRENT_CHAIN" -p udp -m string \
        --algo bm --string "BitTorrent protocol" -j DROP

    # ─── ПРАВИЛО 4: DNS-запросы к трекерам (текстовое совпадение) ───
    # (работает как страховка, если hosts уже обойдён через DoH/DoT)
    iptables -A "$TORRENT_CHAIN" -p udp --dport 53 -m string \
        --algo bm --string ".torrent" -j DROP

    # Разрешаем всё остальное
    iptables -A "$TORRENT_CHAIN" -j RETURN
}

# ──────────────────────────────────────────────────────────────
# DNS-блокировка трекеров через /etc/hosts
# ──────────────────────────────────────────────────────────────
apply_dns_block() {
    # Убираем старую секцию, если есть
    remove_dns_block

    # Создаём файл со списком
    : > "$HOSTS_BLOCK"
    for tracker in "${TRACKERS_LIST[@]}"; do
        echo "0.0.0.0 $tracker" >> "$HOSTS_BLOCK"
        echo "0.0.0.0 www.$tracker" >> "$HOSTS_BLOCK"
    done

    # Добавляем маркеры в /etc/hosts
    echo "" >> /etc/hosts
    echo "# ─── VPN PANEL: TORRENT BLOCK ───" >> /etc/hosts
    cat "$HOSTS_BLOCK" >> /etc/hosts
    echo "# ─── END VPN PANEL: TORRENT BLOCK ───" >> /etc/hosts
}

remove_dns_block() {
    # Удаляем блок между маркерами
    sed -i '/# ─── VPN PANEL: TORRENT BLOCK ───/,/# ─── END VPN PANEL: TORRENT BLOCK ───/d' /etc/hosts
    rm -f "$HOSTS_BLOCK"
}

# ──────────────────────────────────────────────────────────────
# Удаление цепочки iptables
# ──────────────────────────────────────────────────────────────
remove_torrent_chain() {
    if torrent_block_active; then
        while iptables -D OUTPUT -j "$TORRENT_CHAIN" 2>/dev/null; do :; done
        iptables -F "$TORRENT_CHAIN" 2>/dev/null
        iptables -X "$TORRENT_CHAIN" 2>/dev/null
    fi
}

# ──────────────────────────────────────────────────────────────
# Включить блокировку
# ──────────────────────────────────────────────────────────────
enable_torrent_block() {
    header
    echo -e "${YELLOW}--- 🚫 Включение блокировки торрентов ---${NC}"
    echo ""

    # Проверяем наличие модуля string
    if ! modprobe xt_string 2>/dev/null; then
        echo -e "${RED}❌ Модуль xt_string недоступен — DPI не будет работать${NC}"
        echo -e "${YELLOW}Продолжаем только с блокировкой портов...${NC}"
    fi

    init_torrent_chain
    apply_dns_block

    echo -e "${GREEN}✅ Блокировка торрентов включена:${NC}"
    echo -e "  • Порты 6881-6889 (TCP + UDP)"
    echo -e "  • DHT-порты 1337, 2710"
    echo -e "  • DPI: 'BitTorrent protocol' (handshake)"
    echo -e "  • DNS-блокировка трекеров (${#TRACKERS_LIST[@]} шт.)"
    echo ""
    echo -e "${CYAN}Что НЕ блокируется:${NC}"
    echo -e "  • Торрент внутри SSH/WS-туннеля (шифрован)"
    echo ""
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# Выключить блокировку
# ──────────────────────────────────────────────────────────────
disable_torrent_block() {
    header
    echo -e "${YELLOW}--- 🔓 Отключение блокировки торрентов ---${NC}"
    echo ""

    remove_torrent_chain
    remove_dns_block

    echo -e "${GREEN}✅ Блокировка торрентов выключена${NC}"
    read -p "Нажмите Enter..."
}

# ──────────────────────────────────────────────────────────────
# Статистика блокировок
# ──────────────────────────────────────────────────────────────
show_torrent_stats() {
    header
    echo -e "${YELLOW}--- 📊 Статистика блокировки торрентов ---${NC}"
    echo ""

    if ! torrent_block_active; then
        echo -e "${MAGENTA}Блокировка торрентов не активна.${NC}"
        read -p "Enter..."
        return
    fi

    echo -e "${CYAN}── Счётчики iptables ──${NC}"
    iptables -L "$TORRENT_CHAIN" -v -n --line-numbers 2>/dev/null | head -20
    echo ""

    echo -e "${CYAN}── Последние блокировки ──${NC}"
    if [ -f /var/log/kern.log ]; then
        grep "VPN-TORRENT-" /var/log/kern.log 2>/dev/null | tail -10
    fi
    grep "VPN-TORRENT-" /var/log/syslog 2>/dev/null | tail -10
    echo ""
    read -p "Enter..."
}

# ──────────────────────────────────────────────────────────────
# Меню
# ──────────────────────────────────────────────────────────────
menu_torrent_block() {
    while true; do
        header
        echo -e "${YELLOW}🚫 БЛОКИРОВКА ТОРРЕНТОВ${NC}"
        echo ""

        if torrent_block_active; then
            echo -e " Статус: ${GREEN}🟢 Включена${NC}"
            # Считаем заблокированные пакеты
            local pkts=$(iptables -L "$TORRENT_CHAIN" -v -n 2>/dev/null | awk 'NR>2 {sum+=$1} END {print sum}')
            echo -e " Заблокировано пакетов: ${RED}${pkts:-0}${NC}"
        else
            echo -e " Статус: ${RED}🔴 Выключена${NC}"
        fi
        echo ""
        echo -e " 1) ⚡ Включить блокировку"
        echo -e " 2) 📊 Статистика и правила"
        echo -e " 3) 📜 Последние блокировки"
        echo -e " 4) 🗑️  Отключить блокировку"
        echo -e " 5) 📝 Редактировать список трекеров"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-5]: " tbchoice

        case $tbchoice in
            1) enable_torrent_block ;;
            2)
                header
                echo -e "${YELLOW}--- 📊 Правила блокировки ---${NC}"
                echo ""
                iptables -L "$TORRENT_CHAIN" -v -n --line-numbers 2>/dev/null
                echo ""
                echo -e "${CYAN}Активных трекеров в DNS-блоке:${NC}"
                grep -c "0.0.0.0" /etc/hosts 2>/dev/null || echo 0
                echo ""
                read -p "Enter..."
                ;;
            3) show_torrent_stats ;;
            4) disable_torrent_block ;;
            5)
                header
                echo -e "${YELLOW}--- 📝 Список трекеров ---${NC}"
                echo ""
                local i=1
                for t in "${TRACKERS_LIST[@]}"; do
                    echo " $i) $t"
                    ((i++))
                done
                echo ""
                echo -e "${CYAN}Файл для редактирования:${NC} /usr/local/share/vpn-panel/modules/torrent_block.sh"
                echo -e "${CYAN}Меняй массив TRACKERS_LIST, потом пересобери панель.${NC}"
                echo ""
                read -p "Enter..."
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
