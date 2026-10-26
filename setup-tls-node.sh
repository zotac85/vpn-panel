#!/bin/bash
DOMAIN=$1
if ! command -v nginx &> /dev/null; then
    apt update && apt install -y nginx
fi
mkdir -p /etc/nginx/ssl
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
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
