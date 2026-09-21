#!/bin/bash
# Патч: обновление баннера (эмодзи-стиль, без ANSI, с LINE3)

if [ "$EUID" -ne 0 ]; then
  echo "Запустите от root"
  exit 1
fi

echo "🎨 Обновление баннера..."

# Обновляем конфиг
cat << 'CONF_EOF' > /etc/UDPCustom/banner.conf
# Настройки баннера при подключении
ENABLED=1
USE_COLORS=0
SHOW_USER=1
SHOW_LIMIT=1
SHOW_ONLINE=1

TITLE="⚡ ArsenVipKeys VPN ⚡"
WELCOME="Добро пожаловать на защищённый сервер!"
LINE1="🌐 Быстро • Безопасно • Анонимно"
LINE2="💬 Поддержка: @ArsenGuro"
LINE3="📢 Канал: t.me/ArsenVipKeys"
CONF_EOF

# Обновляем show-welcome
cat << 'SCRIPT_EOF' > /usr/local/bin/show-welcome
#!/bin/bash
USER="$PAM_USER"
CONFIG="/etc/UDPCustom/banner.conf"

[ "$USER" == "root" ] && exit 0
[ -z "$USER" ] && exit 0
[ ! -f "$CONFIG" ] && exit 0
source "$CONFIG"
[ "$ENABLED" != "1" ] && exit 0

LIMITS_DIR="/etc/UDPCustom/limits"
LIMIT=3
[ -f "$LIMITS_DIR/$USER" ] && LIMIT=$(cat "$LIMITS_DIR/$USER")

WS_P=""
[ -f /usr/local/bin/ws-proxy.py ] && \
    WS_P=$(awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py | tr -dc '0-9')

FILTER="( sport = :22 or sport = :36712 or sport = :7300"
[[ "$WS_P" =~ ^[0-9]+$ ]] && FILTER="$FILTER or sport = :$WS_P"
FILTER="$FILTER )"

COUNT=0
while IFS= read -r line; do
    [ -z "$line" ] && continue
    pids=$(echo "$line" | grep -oP 'pid=\K[0-9]+' 2>/dev/null)
    [ -z "$pids" ] && continue
    for p in $pids; do
        owner=$(ps -o user= -p "$p" 2>/dev/null | tr -d ' ')
        if [ -n "$owner" ] && [ "$owner" != "root" ]; then
            [ "$owner" == "$USER" ] && COUNT=$((COUNT + 1))
            break
        fi
    done
done <<< "$(ss -H -tnp state established "$FILTER" 2>/dev/null)"

echo ""
echo "$TITLE"
echo ""
echo "$WELCOME"
echo ""
[ "$SHOW_USER" == "1" ] && echo "👤 Пользователь   : $USER"
[ "$SHOW_LIMIT" == "1" ] && echo "📱 Лимит устройств : $LIMIT"
[ "$SHOW_ONLINE" == "1" ] && echo "🔗 Сейчас онлайн   : $COUNT"
echo ""
[ -n "$LINE1" ] && echo "$LINE1"
[ -n "$LINE2" ] && echo "$LINE2"
[ -n "$LINE3" ] && echo "$LINE3"
echo ""
exit 0
SCRIPT_EOF

chmod +x /usr/local/bin/show-welcome

echo ""
echo "✅ Готово! Проверь баннер:"
echo "   PAM_USER=preview /usr/local/bin/show-welcome"
echo ""
echo "Или зайди через DarkTunnel — увидишь новое оформление."
