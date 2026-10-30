#!/bin/bash
# modules/trojan.sh - Управление Xray (Trojan)

menu_trojan() {
    while true; do
        clear
        local xray_status=$(systemctl is-active xray 2>/dev/null)
        local color="${RED}"
        [ "$xray_status" = "active" ] && color="${GREEN}"
        local xray_ver=$(xray version 2>/dev/null | head -1 | awk '{print $2}')

        echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
        echo -e "        ${YELLOW}🚀  УПРАВЛЕНИЕ TROJAN (XRAY)${NC}"
        echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
        echo ""
        echo -e " Статус сервиса Xray : ${color}${xray_status}${NC}"
        echo -e " Версия Xray         : ${GREEN}${xray_ver:-не установлен}${NC}"
        
        local cert_status="${RED}Нет${NC}"
        if [ -f "/etc/nginx/ssl/ruzone.crt" ]; then
            cert_status="${GREEN}Есть${NC}"
        fi
        echo -e " Сертификаты Cloudflare: ${cert_status}"
        echo ""
        echo -e " 1) 🟢 Установить / Обновить / Перенастроить"
        echo -e " 2) 🔴 Выключить Trojan"
        echo -e " 3) 🔑 Загрузить сертификаты (crt/key)"
        echo -e " 4) 🧪 Тестовая ссылка"
        echo -e " 5) 📜 Логи ошибок"
        echo -e " 6) 🧹 Очистить тестовых юзеров (оставить только из бота)"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-6]: " t_choice
        case "$t_choice" in
            1)
                echo ""
                # 1a. Сертификаты
                if [ ! -f "/etc/nginx/ssl/ruzone.crt" ] || [ ! -f "/etc/nginx/ssl/ruzone.key" ]; then
                    echo -e "${RED}❌  Нет сертификатов в /etc/nginx/ssl/. Сначала загрузите их (пункт 3).${NC}"
                    read -p "Enter..."; continue
                fi

                # 1b. Установка/обновление Xray
                local old_ver=$(xray version 2>/dev/null | head -1 | awk '{print $2}')
                echo -e "→ Устанавливаю/обновляю Xray (текущая: ${YELLOW}${old_ver:-нет}${NC})..."
                if ! bash -c "$(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install > /tmp/xray-install.log 2>&1; then
                    echo -e "${RED}❌  Ошибка установки Xray. Логи:${NC}"
                    tail -5 /tmp/xray-install.log | sed 's/^/  /'
                    read -p "Enter..."; continue
                fi
                local new_ver=$(xray version 2>/dev/null | head -1 | awk '{print $2}')
                echo -e "  ✓ Xray: ${old_ver:-?} → ${new_ver:-?}"

                # 1c. Сертификаты в Xray
                echo -e "→ Копирую сертификаты в Xray..."
                mkdir -p /usr/local/etc/xray/ssl
                cp /etc/nginx/ssl/ruzone.crt /usr/local/etc/xray/ssl/
                cp /etc/nginx/ssl/ruzone.key /usr/local/etc/xray/ssl/
                chown -R xray:xray /usr/local/etc/xray/ssl/ 2>/dev/null || true
                chmod 600 /usr/local/etc/xray/ssl/ruzone.key

                # 1d. Конфиг (только если нет)
                if [ ! -f "/usr/local/etc/xray/config.json" ]; then
                    echo -e "→ Создаю конфиг Xray..."
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

                # 1e. Nginx маршрут
                echo -e "→ Проверяю маршрут в Nginx..."
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

                # 1f. UFW + запуск
                ufw allow 8443/tcp > /dev/null 2>&1
                systemctl daemon-reload
                systemctl enable xray > /dev/null 2>&1
                systemctl restart xray

                if ! nginx -t >/dev/null 2>&1; then
                    echo -e "${RED}❌  nginx -t упал. Не перезапускаю.${NC}"
                    read -p "Enter..."; continue
                fi
                systemctl restart nginx

                # 1g. Итог
                if systemctl is-active --quiet xray; then
                    local cur_ver=$(xray version 2>/dev/null | head -1 | awk '{print $2}')
                    echo -e "${GREEN}✅  Готово. Xray v${cur_ver:-?} работает, Trojan включён.${NC}"
                else
                    echo -e "${RED}❌  Xray не запустился. journalctl -u xray -n 30${NC}"
                fi
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
            6)
                echo -e "\n${YELLOW}Внимание! Это удалит ВСЕХ юзеров из Xray.${NC}"
                echo -e "После этого запустите синхронизацию в боте, чтобы вернуть VIP-клиентов."
                read -p "Вы уверены? (y/n): " confirm
                if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
                    # Очищаем массив clients в JSON (ставим пустой массив)
                    python3 -c "
import json
with open('/usr/local/etc/xray/config.json', 'r') as f:
    cfg = json.load(f)
cfg['inbounds'][0]['settings']['clients'] = []
with open('/usr/local/etc/xray/config.json', 'w') as f:
    json.dump(cfg, f, indent=2)
"
                    systemctl restart xray
                    echo -e "${GREEN}✅ Все юзеры удалены! Xray перезапущен.${NC}"
                else
                    echo "Отменено."
                fi
                read -p "Enter..."
                ;;
            0) return ;;
            *) echo -e "${RED}Неверный выбор${NC}"; sleep 1 ;;
        esac
    done
}
