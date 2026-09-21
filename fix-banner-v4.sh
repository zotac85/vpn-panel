#!/bin/bash
# Патч v4: правильный баннер через sshd_config Banner + однострочный pam_exec

if [ "$EUID" -ne 0 ]; then echo "Запустите от root"; exit 1; fi

echo "🔧 Патч v4: чистим и настраиваем правильно..."

# 1) Бэкапы
[ ! -f /etc/pam.d/sshd.bak4 ] && cp /etc/pam.d/sshd /etc/pam.d/sshd.bak4
[ ! -f /etc/ssh/sshd_config.bak4 ] && cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak4

# 2) Чистим ВСЕ старые pam_exec с баннером
sed -i '/show-welcome/d' /etc/pam.d/sshd
sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd

# 3) Создаём Banner-файл (многострочный, работает через sshd)
cat << 'BANNER_EOF' > /etc/ssh/banner.txt

🚀 ArsenVipKeys Premium Server 🚀

❌ NO DDOS ❌
❌ NO HACKING ❌
❌ NO TORRENT ❌
❌ NO SPAMMING ❌
❌ NO CARDING ❌
👥 MAX LOGIN 2 DEVICE 👥
🚫 VIOLATE AUTO BANNED PERMANENT 🚫

💬 Support: t.me/ArsenGuro
📢 Channel: t.me/ArsenVipKeys

BANNER_EOF

# 4) Прописываем Banner в sshd_config
if grep -q "^Banner" /etc/ssh/sshd_config; then
    sed -i 's|^Banner.*|Banner /etc/ssh/banner.txt|' /etc/ssh/sshd_config
else
    echo "Banner /etc/ssh/banner.txt" >> /etc/ssh/sshd_config
fi

# 5) check-device-limit-pam — проверка лимита (одна строка при ошибке)
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
    echo "❌ ПРЕВЫШЕН ЛИМИТ УСТРОЙСТВ ($COUNT / $LIMIT). Отключите другое устройство."
    exit 1
fi
exit 0
LIMIT_EOF

chmod +x /usr/local/bin/check-device-limit-pam

# 6) Вставляем ТОЛЬКО check-device-limit-pam в PAM
if grep -q "pam_nologin.so" /etc/pam.d/sshd; then
    sed -i '/pam_nologin.so/a account    required     pam_exec.so stdout /usr/local/bin/check-device-limit-pam' /etc/pam.d/sshd
fi

# 7) Проверка PAM и Banner
echo ""
echo "📋 Проверка:"
echo "  check-device-limit-pam : $(grep -c 'check-device-limit-pam' /etc/pam.d/sshd) строк(и)"
echo "  show-welcome           : $(grep -c 'show-welcome' /etc/pam.d/sshd) строк(и)"
echo "  Banner в sshd_config   :"
grep "^Banner" /etc/ssh/sshd_config
echo ""

# 8) Тест
PAM_USER=root /usr/local/bin/check-device-limit-pam && echo "✅ Скрипт работает"

# 9) Перезапуск sshd
echo ""
echo "🔄 Перезапуск sshd..."
sleep 2
systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null

echo ""
echo "🟢 Патч v4 применён!"
echo ""
echo "Теперь:"
echo "  • Баннер придёт от sshd (с переносами)"
echo "  • Лимит проверяется отдельно"
echo ""
echo "Откат: cp /etc/ssh/sshd_config.bak4 /etc/ssh/sshd_config && cp /etc/pam.d/sshd.bak4 /etc/pam.d/sshd && systemctl restart ssh"
