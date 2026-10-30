#!/bin/bash
# modules/trojan.sh - Управление Xray (Trojan)

menu_trojan() {
    while true; do
        clear
        local xray_status=$(systemctl is-active xray 2>/dev/null)
        local color="${RED}"
        [ "$xray_status" = "active" ] && color="${GREEN}"

        echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
        echo -e "        ${YELLOW}🚀  УПРАВЛЕНИЕ TROJAN (XRAY)${NC}"
        echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
        echo ""
        echo -e " Статус сервиса Xray : ${color}${xray_status}${NC}"
        
        local cert_status="${RED}Нет${NC}"
        if [ -f "/etc/nginx/ssl/ruzone.crt" ]; then
            cert_status="${GREEN}Есть${NC}"
        fi
        echo -e " Сертификаты Cloudflare: ${cert_status}"
        echo ""
        echo -e " 1) 🟢 Включить / Настроить Trojan"
        echo -e " 2) 🔴 Выключить Trojan"
        echo -e " 3) 🔑 Загрузить сертификаты (crt/key)"
        echo -e " 4) 🧪 Тестовая ссылка"
        echo -e " 5) 📜 Логи ошибок"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-5]: " t_choice
        case "$t_choice" in
            1)
                echo ""
                if [ ! -f "/etc/nginx/ssl/ruzone.crt" ]; then
                    echo -e "${RED}❌ Нет сертификатов в /etc/nginx/ssl/. Сначала загрузите их (пункт 3).${NC}"
                    read -p "Enter..."; continue
                fi
                
                echo -e "→ Копирую сертификаты в Xray..."
                mkdir -p /usr/local/etc/xray/ssl
                cp /etc/nginx/ssl/ruzone.crt /usr/local/etc/xray/ssl/
                cp /etc/nginx/ssl/ruzone.key /usr/local/etc/xray/ssl/
                chown -R xray:xray /usr/local/etc/xray/ssl/
                chmod 600 /usr/local/etc/xray/ssl/ruzone.key

                echo -e "→ Проверяю конфиг Xray..."
                if [ ! -f "/usr/local/etc/xray/config.json" ]; then
                    cat << 'XRAYCFG' > /usr/local/etc/xray/config.json
{
  "log": {"loglevel": "warning"},
  "inbounds": [
    {
      "port": 8443, "listen": "127.0.0.1", "protocol": "trojan",
      "settings": {"clients": [{"password": "test_password_123"}]},
      "streamSettings": {"network": "ws", "wsSettings": {"path": "/trojan-ws"}}
    }
  ],
  "outbounds": [{"protocol": "freedom"}]
}
XRAYCFG
                fi

                echo -e "→ Добавляю маршрут в Nginx..."
                if ! grep -q "location /trojan-ws" /etc/nginx/conf.d/tls-tunnel.conf 2>/dev/null; then
                    cat << 'NGINXCFG' >> /etc/nginx/conf.d/tls-tunnel.conf
    location /trojan-ws {
        proxy_pass http://127.0.0.1:8443;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_buffering off;
    }
NGINXCFG
                fi

                echo -e "→ Открываю порт 8443 в UFW..."
                ufw allow 8443/tcp > /dev/null 2>&1

                echo -e "→ Запускаю сервисы..."
                systemctl daemon-reload
                systemctl enable xray > /dev/null 2>&1
                systemctl restart xray
                nginx -t && systemctl restart nginx
                
                echo -e "${GREEN}✅ Trojan успешно включен и настроен!${NC}"
                read -p "Enter..."
                ;;
            2)
                echo -e "→ Останавливаю Xray..."
                systemctl stop xray
                systemctl disable xray > /dev/null 2>&1
                
                echo -e "→ Убираю маршрут из Nginx..."
                sed -i '/location \/trojan-ws {/,/}/d' /etc/nginx/conf.d/tls-tunnel.conf
                nginx -t && systemctl restart nginx
                
                echo -e "${GREEN}✅ Trojan выключен.${NC}"
                read -p "Enter..."
                ;;
            3)
                echo -e "${CYAN}Вставьте содержимое сертификата Cloudflare (.crt), затем нажмите Ctrl+D:${NC}"
                cat > /etc/nginx/ssl/ruzone.crt
                echo -e "${CYAN}Вставьте приватный ключ (.key), затем нажмите Ctrl+D:${NC}"
                cat > /etc/nginx/ssl/ruzone.key
                echo -e "${GREEN}✅ Сертификаты сохранены!${NC}"
                read -p "Enter..."
                ;;
            4)
                local pass=$(grep -o '"password": "[^"]*"' /usr/local/etc/xray/config.json 2>/dev/null | head -1 | awk -F'"' '{print $4}')
                if [ -n "$pass" ]; then
                    echo -e "\n🚀 <b>Тестовая ссылка:</b>"
                    echo -e "trojan://${pass}@104.18.0.3:443?security=tls&type=ws&path=/trojan-ws&host=de.ruzone27.shop&sni=ruzone27.shop#Test"
                else
                    echo "❌ Конфиг не найден или пуст."
                fi
                read -p "Enter..."
                ;;
            5)
                echo ""
                journalctl -u xray -n 20 --no-pager
                read -p "Enter..."
                ;;
            0) return ;;
            *) echo -e "${RED}Неверный выбор${NC}"; sleep 1 ;;
        esac
    done
}
