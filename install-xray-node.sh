#!/bin/bash
# install-xray-node.sh — установка Xray (Trojan WS) на ноду
# Usage: bash install-xray-node.sh <PASSWORD>
# PASSWORD должен совпадать с мастером (/usr/local/etc/xray/config.json)

set -e
PASS="${1:-}"
if [ -z "$PASS" ]; then
    echo "[xray-node] ERROR: password not provided"
    exit 1
fi

XRAY_PORT=8443
XRAY_PATH="/trojan-ws"
NGINX_CONF="/etc/nginx/conf.d/tls-tunnel.conf"

echo "[xray-node] Installing Xray..."

# 1. Установка Xray (официальный установщик)
if ! command -v xray >/dev/null 2>&1; then
    if ! bash -c "$(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install >/dev/null 2>&1; then
        echo "[xray-node] Official installer failed, trying apt..."
        apt-get update -y >/dev/null 2>&1
        apt-get install -y xray >/dev/null 2>&1 || {
            echo "[xray-node] ERROR: xray not installed"
            exit 1
        }
    fi
fi

# 2. Конфиг
mkdir -p /usr/local/etc/xray
cat > /usr/local/etc/xray/config.json << JSONEOF
{
  "log": { "loglevel": "warning" },
  "inbounds": [{
    "port": $XRAY_PORT,
    "listen": "127.0.0.1",
    "protocol": "trojan",
    "settings": { "clients": [{ "password": "$PASS" }] },
    "streamSettings": {
      "network": "ws",
      "wsSettings": { "path": "$XRAY_PATH" }
    }
  }],
  "outbounds": [{ "protocol": "freedom", "settings": {} }]
}
JSONEOF

# 3. Сервис
systemctl daemon-reload 2>/dev/null || true
systemctl enable xray >/dev/null 2>&1 || true
systemctl restart xray

# 4. Nginx location /trojan-ws
if [ ! -f "$NGINX_CONF" ]; then
    echo "[xray-node] WARN: $NGINX_CONF not found, trying sites-enabled/default"
    NGINX_CONF="/etc/nginx/sites-available/default"
fi

if ! grep -q "location /trojan-ws" "$NGINX_CONF" 2>/dev/null; then
    cp "$NGINX_CONF" "$NGINX_CONF.bak_xray_$(date +%F_%H%M%S)" 2>/dev/null || true
    python3 - "$NGINX_CONF" << 'PYEOF'
import sys
p = sys.argv[1]
with open(p, 'r') as f:
    s = f.read()
loc = '''
    location /trojan-ws {
        if ($http_upgrade != "websocket") { return 404; }
        proxy_redirect off;
        proxy_pass http://127.0.0.1:8443;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }
'''
idx = s.rfind('}')
if idx > 0:
    s = s[:idx] + loc + s[idx:]
    with open(p, 'w') as f:
        f.write(s)
    print("[xray-node] nginx location inserted")
else:
    print("[xray-node] ERROR: closing brace not found in nginx conf")
    sys.exit(1)
PYEOF
else
    echo "[xray-node] nginx location already present"
fi

# 5. Проверка + reload
if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx >/dev/null 2>&1 || systemctl restart nginx
else
    echo "[xray-node] ERROR: nginx config test failed"
    nginx -t
    exit 1
fi

# 6. Итог
if systemctl is-active --quiet xray && systemctl is-active --quiet nginx; then
    echo "[xray-node] OK: xray running on 127.0.0.1:$XRAY_PORT, nginx proxies $XRAY_PATH"
else
    echo "[xray-node] ERROR: service not active"
    exit 1
fi
