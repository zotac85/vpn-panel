#!/bin/bash
# install-node.sh - установка ТОЛЬКО ноды (SSH + WS + node-user.sh)
# Без панели, без ботов, без БД

set -e
REPO_URL="https://raw.githubusercontent.com/zotac85/vpn-panel/main"
GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[1;33m"; CYAN="\033[0;36m"; NC="\033[0m"

[ "$(id -u)" -eq 0 ] || { echo -e "${RED}Запускать от root${NC}"; exit 1; }

clear
echo -e "${CYAN}=================================================${NC}"
echo -e "${CYAN}      УСТАНОВКА НОДЫ (SSH + WS Proxy)${NC}"
echo -e "${CYAN}=================================================${NC}"
echo ""

# 1. Базовые пакеты
echo -e "${YELLOW}[1/6] Устанавливаю базовые пакеты...${NC}"
export DEBIAN_FRONTEND=noninteractive
apt update -y -qq
apt install -y -qq python3 ufw curl git ca-certificates >/dev/null 2>&1

# 2. Порты
echo ""
echo -e "${YELLOW}[2/6] Настройка портов${NC}"
read -p "WS-порт (Enter = 2052): " WS_PORT
WS_PORT=${WS_PORT:-2052}
[[ "$WS_PORT" =~ ^[0-9]+$ ]] && [ "$WS_PORT" -ge 1 ] && [ "$WS_PORT" -le 65535 ] || { echo -e "${RED}Неверный порт${NC}"; exit 1; }

read -p "SSH-порт (Enter = 22): " SSH_PORT
SSH_PORT=${SSH_PORT:-22}
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] && [ "$SSH_PORT" -ge 1 ] && [ "$SSH_PORT" -le 65535 ] || { echo -e "${RED}Неверный порт${NC}"; exit 1; }

# 3. WS Proxy
echo ""
echo -e "${YELLOW}[3/6] Устанавливаю WebSocket Proxy на порт $WS_PORT${NC}"
cat > /usr/local/bin/ws-proxy.py << PYEOF
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
                src.close(); dst.close()
        threading.Thread(target=forward, args=(client_socket, server_socket)).start()
        threading.Thread(target=forward, args=(server_socket, client_socket)).start()
    except:
        client_socket.close()
def main():
    listen_port = $WS_PORT
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', listen_port))
    server.listen(100)
    while True:
        client_socket, addr = server.accept()
        threading.Thread(target=handle_connection, args=(client_socket,)).start()
if __name__ == '__main__':
    main()
PYEOF
chmod +x /usr/local/bin/ws-proxy.py

cat > /etc/systemd/system/ws-proxy.service << 'SVCEOF'
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
SVCEOF
systemctl daemon-reload
systemctl enable ws-proxy >/dev/null 2>&1
systemctl restart ws-proxy

# 4. node-user.sh
echo ""
echo -e "${YELLOW}[4/6] Устанавливаю node-user.sh${NC}"
curl -sf -o /usr/local/bin/node-user.sh "$REPO_URL/scripts/node-user.sh"
chmod +x /usr/local/bin/node-user.sh
[ -x /usr/local/bin/node-user.sh ] || { echo -e "${RED}Не удалось скачать node-user.sh${NC}"; exit 1; }

# 5. UFW
echo ""
echo -e "${YELLOW}[5/6] Настраиваю firewall${NC}"
ufw --force reset >/dev/null 2>&1
ufw default deny incoming >/dev/null 2>&1
ufw default allow outgoing >/dev/null 2>&1
ufw allow $SSH_PORT/tcp comment 'SSH' >/dev/null 2>&1
ufw allow $WS_PORT/tcp comment 'WebSocket Proxy' >/dev/null 2>&1
ufw --force enable >/dev/null 2>&1

# 6. Итог
echo ""
echo -e "${YELLOW}[6/6] Готово${NC}"
echo -e "${CYAN}=================================================${NC}"
echo -e "${GREEN}✅  Нода установлена${NC}"
echo -e "${CYAN}=================================================${NC}"
echo ""
echo -e "  WS Proxy : ${GREEN}работает на порту $WS_PORT${NC}"
echo -e "  SSH      : порт $SSH_PORT"
echo -e "  User CLI : ${GREEN}node-user.sh${NC}"
echo ""
echo -e "${YELLOW}Проверка сервиса:${NC}"
systemctl is-active ws-proxy && echo -e "${GREEN}ws-proxy: active${NC}" || echo -e "${RED}ws-proxy: НЕ работает${NC}"
echo ""
echo -e "${YELLOW}IP этого сервера:${NC}"
hostname -I | awk '{print $1}'
echo ""
echo -e "${CYAN}=================================================${NC}"
echo -e "Управление юзерами:"
echo -e "  node-user.sh add <user> <pass>"
echo -e "  node-user.sh del <user>"
echo -e "  node-user.sh list"
echo -e "  node-user.sh traffic-all"
echo -e "${CYAN}=================================================${NC}"
