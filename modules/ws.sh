#!/bin/bash

install_ws() {
    header
    echo -e "${YELLOW}--- 🕸️ Установка WebSocket Proxy ---${NC}"
    apt update -y && apt install -y python3 ufw

    read -p "Введите порт для WebSocket (по умолчанию 80): " ws_port
    if ! [[ "$ws_port" =~ ^[0-9]+$ ]] || [ "$ws_port" -lt 1 ] || [ "$ws_port" -gt 65535 ]; then
        ws_port=80
        echo -e "${CYAN}Используется порт по умолчанию: 80${NC}"
    fi

    cat << PY_EOF > /usr/local/bin/ws-proxy.py
import socket, threading

def handle_connection(client_socket):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.connect(('127.0.0.1', 22))
        initial_data = client_socket.recv(8192)
        if b"HTTP" in initial_data:
            response = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n"
            client_socket.send(response)
        else:
            server_socket.send(initial_data)

        def forward(src, dst):
            try:
                while True:
                    data = src.recv(8192)
                    if not data: break
                    dst.send(data)
            except: pass
            finally:
                src.close()
                dst.close()

        threading.Thread(target=forward, args=(client_socket, server_socket)).start()
        threading.Thread(target=forward, args=(server_socket, client_socket)).start()
    except:
        client_socket.close()

def main():
    listen_port = $ws_port
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', listen_port))
    server.listen(100)
    while True:
        client_socket, addr = server.accept()
        threading.Thread(target=handle_connection, args=(client_socket,)).start()

if __name__ == '__main__':
    main()
PY_EOF

    chmod +x /usr/local/bin/ws-proxy.py

    cat << 'WS_SVC_EOF' > /etc/systemd/system/ws-proxy.service
[Unit]
Description=WebSocket Proxy Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /usr/local/bin/ws-proxy.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
WS_SVC_EOF

    systemctl daemon-reload
    systemctl enable ws-proxy
    systemctl restart ws-proxy
    ufw allow $ws_port/tcp comment 'WebSocket Proxy Port' 2>/dev/null

    echo -e "${GREEN}WebSocket Proxy успешно запущен на порту $ws_port!${NC}"
    read -p "Нажмите Enter для продолжения..."
}

change_ws_port() {
    header
    echo -e "${YELLOW}--- ⚙️ Смена порта WebSocket Proxy ---${NC}"
    local old_port=$(get_ws_port)
    if [[ "$old_port" == "Не установлен" ]]; then
        echo -e "${RED}Служба не установлена! Сначала установите её (пункт 1).${NC}"
        read -p "Нажмите Enter..."
        return
    fi

    echo -e "Текущий порт: ${GREEN}$old_port${NC}"
    read -p "Введите новый порт (1-65535): " new_port

    if [[ "$new_port" =~ ^[0-9]+$ ]] && [ "$new_port" -ge 1 ] && [ "$new_port" -le 65535 ]; then
        ufw delete allow $old_port/tcp 2>/dev/null
        sed -i "s/listen_port[[:space:]]*=[[:space:]]*[0-9]*/listen_port = $new_port/" /usr/local/bin/ws-proxy.py
        ufw allow $new_port/tcp comment 'WebSocket Proxy Port' 2>/dev/null
        systemctl restart ws-proxy
        echo -e "${GREEN}✅ Локальный порт изменен на $new_port и служба перезапущена.${NC}"

        # 1. Обновляем порт в базе данных
        python3 -c "import sqlite3; db=sqlite3.connect('/etc/UDPCustom/vpn.db'); db.execute('UPDATE nodes SET ws_port=?', ('$new_port',)); db.commit()"
        echo -e "${GREEN}✅ Порт в базе данных обновлен на $new_port.${NC}"

        # 2. Обходим все ноды и меняем порт там
        echo -e "${YELLOW}Обновление портов на нодах...${NC}"
        NODES=$(python3 -c "import sqlite3; db=sqlite3.connect('/etc/UDPCustom/vpn.db'); print('\n'.join(f'{r[0]}|{r[1]}' for r in db.execute('SELECT ip, ssh_port FROM nodes WHERE is_master=0').fetchall()))")
        
        if [ -n "$NODES" ]; then
            while IFS='|' read -r ip sport; do
                [ -z "$ip" ] && continue
                echo -n "  Нода $ip: "
                ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -p "$sport" root@"$ip"                     "sed -i 's/listen_port[[:space:]]*=[[:space:]]*[0-9]*/listen_port = $new_port/' /usr/local/bin/ws-proxy.py && ufw allow $new_port/tcp >/dev/null 2>&1 && systemctl restart ws-proxy" >/dev/null 2>&1
                if [ $? -eq 0 ]; then
                    echo -e "${GREEN}Успешно${NC}"
                else
                    echo -e "${RED}Ошибка SSH${NC}"
                fi
            done <<< "$NODES"
        else
            echo "  (нод не найдено)"
        fi
    else
        echo -e "${RED}Неверный формат порта.${NC}"
    fi
    read -p "Нажмите Enter для продолжения..."
}

menu_ws() {
    while true; do
        header
        local cur_port=$(get_ws_port)

        echo -e "${YELLOW}🕸️  МОДУЛЬ WEBSOCKET PROXY (ОБХОД DPI)${NC}"
        echo -e " WS Proxy : $(get_service_status ws-proxy)"
        echo -e " Порт     : ${GREEN}${cur_port} (TCP)${NC}"
        echo -e " UDPGW    : $(get_service_status udpgw)"
        echo ""
        echo -e " 1) ⚡  Установить / Запустить WebSocket Proxy"
        echo -e " 2) 🔄 Перезапустить"
        echo -e " 3) ⏸️  Остановить"
        echo -e " 4) ⚙️  Изменить порт WS"
        echo -e " 5) 🔒 Управление прокси"
        echo -e " 6) 📦 Управление payload"
        echo -e " 7) 📡 Управление UDPGW (порт 7300)"
        echo -e " 8) 🗑️  Удалить с сервера"
        echo -e " 9) 📦 Управление подписками (Домен, SSL)"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-9]: " ws_choice
        case $ws_choice in
            1) install_ws ;;
            2) systemctl restart ws-proxy; echo -e "${GREEN}Перезапущено.${NC}"; sleep 1 ;;
            3) systemctl stop ws-proxy; echo -e "${YELLOW}Остановлено.${NC}"; sleep 1 ;;
            4) change_ws_port ;;
            5) manage_proxy ;;
            6) manage_payload ;;
            7) declare -f menu_udpgw &>/dev/null && menu_udpgw || { echo -e "${RED}Модуль udp.sh не загружен${NC}"; read -p "Enter..."; } ;;
            8)
                local dp=$(get_ws_port)
                systemctl stop ws-proxy 2>/dev/null
                systemctl disable ws-proxy 2>/dev/null
                [[ "$dp" != "Не установлен" ]] && ufw delete allow $dp/tcp 2>/dev/null
                rm -f /etc/systemd/system/ws-proxy.service /usr/local/bin/ws-proxy.py
                echo -e "${GREEN}Удалено.${NC}"; sleep 1 ;;
            9) menu_subscriptions ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}


menu_subscriptions() {
    while true; do
        clear
        source /etc/UDPCustom/domain.conf 2>/dev/null || DOMAIN="не задан"
        
        echo -e "${CYAN}══════════════════════════════════════════════${NC}"
        echo -e "     ${YELLOW}УПРАВЛЕНИЕ ПОДПИСКАМИ И ДОМЕНОМ${NC}"
        echo -e "${CYAN}══════════════════════════════════════════════${NC}"
        echo -e " Текущий домен: ${GREEN}${DOMAIN}${NC}"
        
        # Проверка сертификата
        if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
            EXP=$(openssl x509 -enddate -noout -in "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" | cut -d= -f2)
            echo -e " SSL Сертификат: ${GREEN}Активен (до $EXP)${NC}"
        else
            echo -e " SSL Сертификат: ${RED}Отсутствует${NC}"
        fi
        echo -e "${CYAN}──────────────────────────────────────────────${NC}"
        echo -e " 1) 🌐 Изменить домен"
        echo -e " 2) 🔒 Выпустить/Обновить SSL сертификат"
        echo -e " 3) 🕸️ Ссылка для DarkTunnel"
        echo -e " 4) 🍏 Ссылка для NPV Tunnel"
        echo -e " 5) 🔄 Перезапустить сервис подписок"
        echo -e " 0) ⬅️ Назад"
        echo -e "${CYAN}──────────────────────────────────────────────${NC}"
        read -p "Выберите пункт [0-5]: " sub_choice
        
        case $sub_choice in
            1)
                read -p "Введите новый домен (например, de.cdnstore.shop): " new_dom
                if [ -n "$new_dom" ]; then
                    echo "DOMAIN=\"$new_dom\"" > /etc/UDPCustom/domain.conf
                    python3 -c "import sqlite3; db=sqlite3.connect('/etc/UDPCustom/vpn.db'); db.execute('UPDATE nodes SET host=? WHERE is_master=1', ('$new_dom',)); db.commit()"
                    systemctl restart npvt-sub.service
                    echo -e "${GREEN}✅ Домен изменен на $new_dom, сервис подписок перезапущен.${NC}"
                    echo -e "${YELLOW}⚠️ Не забудьте выпустить новый SSL сертификат (пункт 2)!${NC}"
                    read -p "Нажмите Enter..."
                fi
                ;;
            2)
                if [ "$DOMAIN" = "не задан" ]; then echo "Сначала задайте домен!"; sleep 2; continue; fi
                echo -e "${YELLOW}Выпуск сертификата для $DOMAIN...${NC}"
                echo -e "Останавливаю WS Proxy на 10 секунд для проверки домена..."
                systemctl stop ws-proxy
                certbot certonly --standalone -d "$DOMAIN" --non-interactive --agree-tos -m admin@$DOMAIN
                systemctl start ws-proxy
                echo -e "${GREEN}✅ Сертификат обновлен!${NC}"
                read -p "Нажмите Enter..."
                ;;
            3)
                read -p "Введите логин ключа (например, vip_arsen): " key_name
                # Проверяем наличие ключа в базе через Python
                check=$(cd /usr/local/bin && python3 -c "from bot_modules import db; print('OK' if (db.get_test_key('$key_name') or db.get_vip_key('$key_name')) else 'NO')" 2>/dev/null)
                if [ "$check" == "OK" ]; then
                    echo -e "\nВаша ссылка для DarkTunnel (ПК/Android):"
                    echo -e "${GREEN}https://$DOMAIN/sub_dark/$key_name${NC}"
                else
                    echo -e "\n${RED}❌ Ключ '$key_name' не найден в базе!${NC}"
                fi
                read -p "Нажмите Enter..."
                ;;
            4)
                read -p "Введите логин ключа (например, vip_arsen): " key_name
                # Проверяем наличие ключа в базе
                check=$(cd /usr/local/bin && python3 -c "from bot_modules import db; print('OK' if (db.get_test_key('$key_name') or db.get_vip_key('$key_name')) else 'NO')" 2>/dev/null)
                if [ "$check" == "OK" ]; then
                    echo -e "\nВаша ссылка для NPV Tunnel (iPhone):"
                    echo -e "${GREEN}https://$DOMAIN/sub/$key_name${NC}"
                else
                    echo -e "\n${RED}❌ Ключ '$key_name' не найден в базе!${NC}"
                fi
                read -p "Нажмите Enter..."
                ;;
            5)
                systemctl restart npvt-sub.service
                echo -e "${GREEN}✅ Сервис подписок перезапущен!${NC}"
                sleep 1
                ;;
            0) return ;;
            *) echo "Неверный выбор"; sleep 1 ;;
        esac
    done
}
