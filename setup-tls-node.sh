#!/bin/bash
DOMAIN=$1

# 1. Устанавливаем Nginx, если его нет
if ! command -v nginx &> /dev/null; then
    apt update && apt install -y nginx
fi

# 2. Открываем порт 443 в фаерволе (если ufw установлен)
if command -v ufw &> /dev/null; then
    ufw allow 443/tcp > /dev/null 2>&1
    ufw allow 80/tcp > /dev/null 2>&1
fi

# 3. Создаем папку для сертификатов
mkdir -p /etc/nginx/ssl

# 4. Создаем конфиг Nginx
cat << INNEREOF > /etc/nginx/conf.d/tls-tunnel.conf
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $DOMAIN;

    ssl_certificate /etc/nginx/ssl/ruzone.crt;
    ssl_certificate_key /etc/nginx/ssl/ruzone.key;

    access_log off;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_buffering off;
        proxy_set_header Expect "";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
INNEREOF

# 5. Удаляем дефолтный конфиг и перезапускаем
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
