#!/bin/bash
# Патч v2: чистим дубликаты в PAM + правильные переносы строк в баннере

if [ "$EUID" -ne 0 ]; then echo "Запустите от root"; exit 1; fi

echo "🔧 Патч баннера v2..."

# 1) Бэкап PAM
[ ! -f /etc/pam.d/sshd.bak2 ] && cp /etc/pam.d/sshd /etc/pam.d/sshd.bak2

# 2) Удаляем ВСЕ наши строки из PAM (дубликаты)
sed -i '/show-welcome/d' /etc/pam.d/sshd
sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd

# 3) Обновляем show-welcome с правильными переносами (\r\n)
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

# Вывод через printf с \r\n (CRLF) — обязательно для SSH Server Message
printf "\r\n"
printf "%s\r\n" "$TITLE"
printf "\r\n"
printf "%s\r\n" "$WELCOME"
printf "\r\n"
[ "$SHOW_USER" == "1" ] && printf "👤 Пользователь   : %s\r\n" "$USER"
[ "$SHOW_LIMIT" == "1" ] && printf "📱 Лимит устройств : %s\r\n" "$LIMIT"
[ "$SHOW_ONLINE" == "1" ] && printf "🔗 Сейчас онлайн   : %s\r\n" "$COUNT"
printf "\r\n"
[ -n "$LINE1" ] && printf "%s\r\n" "$LINE1"
[ -n "$LINE2" ] && printf "%s\r\n" "$LINE2"
[ -n "$LINE3" ] && printf "%s\r\n" "$LINE3"
printf "\r\n"
exit 0
SCRIPT_EOF

chmod +x /usr/local/bin/show-welcome

# 4) Обновляем check-device-limit-pam (тоже с \r\n для консистентности)
cat << 'LIMIT_EOF' > /usr/local/bin/check-device-limit-pam
#!/bin/bash
USER="$PAM_USER"
LIMITS_DIR="/etc/UDPCustom/limits"
DB_USERS="/etc/UDPCustom/users.db"

[ "$USER" == "root" ] && exit 0
[ -z "$USER" ] && exit 0
grep -q "^${USER}$" "$DB_USERS" 2>/dev/null || exit 0

LIMIT=3
[ -f "$LIMITS_DIR/$USER" ] && LIMIT=$(cat "$LIMITS_DIR/$USER")
[[ "$LIMIT" =~ ^[0-9]+$ ]] || LIMIT=3
[ "$LIMIT" -le 0 ] && exit 0

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

if [ "$COUNT" -ge "$LIMIT" ]; then
    printf "\r\n"
    printf "❌ ПРЕВЫШЕН ЛИМИТ УСТРОЙСТВ\r\n"
    printf "Разрешено устройств : %s\r\n" "$LIMIT"
    printf "Сейчас подключено   : %s\r\n" "$COUNT"
    printf "⚠️  Отключите другое устройство и попробуйте снова.\r\n"
    printf "\r\n"
    exit 1
fi
exit 0
LIMIT_EOF

chmod +x /usr/local/bin/check-device-limit-pam

# 5) Вставляем в PAM ровно по одной строке
# Сначала лимит, потом баннер — в account-фазе после pam_nologin
if grep -q "pam_nologin.so" /etc/pam.d/sshd; then
    sed -i '/pam_nologin.so/a account    required     pam_exec.so stdout /usr/local/bin/check-device-limit-pam' /etc/pam.d/sshd
    sed -i '/check-device-limit-pam/a account    required     pam_exec.so stdout /usr/local/bin/show-welcome' /etc/pam.d/sshd
fi

# 6) Проверка что в PAM ровно по одной строке
LIMIT_CNT=$(grep -c "check-device-limit-pam" /etc/pam.d/sshd)
WELCOME_CNT=$(grep -c "show-welcome" /etc/pam.d/sshd)
echo ""
echo "📋 Проверка PAM:"
echo "  check-device-limit-pam : $LIMIT_CNT строк(и)"
echo "  show-welcome           : $WELCOME_CNT строк(и)"
echo ""
grep -n "check-device-limit-pam\|show-welcome" /etc/pam.d/sshd

# 7) Проверка что root пропускается
PAM_USER=root /usr/local/bin/show-welcome && \
PAM_USER=root /usr/local/bin/check-device-limit-pam && \
echo "✅ Скрипты работают для root"

# 8) Перезапуск sshd
echo ""
echo "🔄 Перезапуск sshd..."
sleep 2
systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null

echo ""
echo "🟢 Патч v2 применён!"
echo ""
echo "Проверь через DarkTunnel — теперь:"
echo "  • Только ОДИН баннер"
echo "  • Строки переносятся правильно"
echo ""
echo "Откат если что: cp /etc/pam.d/sshd.bak2 /etc/pam.d/sshd && systemctl restart ssh"
