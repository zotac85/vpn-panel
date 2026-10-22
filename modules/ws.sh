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
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-8]: " ws_choice
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
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
