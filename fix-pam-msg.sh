#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Патч: красивое сообщение о превышении лимита устройств
# Убирает "pam_exec failed: exit code 1" и показывает
# своё сообщение клиенту через stdout.
# ──────────────────────────────────────────────────────────────

if [ "$EUID" -ne 0 ]; then
  echo "Ошибка: запустите от root (sudo -i)"
  exit 1
fi

echo -e "\033[0;36m==============================================\033[0m"
echo -e "     \033[1;33m🔧 ПАТЧ: Сообщение о лимите устройств\033[0m"
echo -e "\033[0;36m==============================================\033[0m"

# 1) Бэкап PAM
if [ ! -f /etc/pam.d/sshd.bak ]; then
    cp /etc/pam.d/sshd /etc/pam.d/sshd.bak
    echo -e "\033[0;32m✅ Бэкап PAM создан: /etc/pam.d/sshd.bak\033[0m"
fi

# 2) Перезаписываем скрипт с красивым выводом и без >&2
cat << 'PAM_EOF' > /usr/local/bin/check-device-limit-pam
#!/bin/bash
# ──────────────────────────────────────────────────────────────
# PAM-скрипт проверки лимита устройств для SSH (включая WS-туннели).
# Вызывается в account-фазе — ПОСЛЕ аутентификации пароля.
# ──────────────────────────────────────────────────────────────

USER="$PAM_USER"
LIMITS_DIR="/etc/UDPCustom/limits"
DB_USERS="/etc/UDPCustom/users.db"

# Root и пустой юзер — пропускаем
[ "$USER" == "root" ] && exit 0
[ -z "$USER" ] && exit 0

# Только наши юзеры
grep -q "^${USER}$" "$DB_USERS" 2>/dev/null || exit 0

# Читаем лимит
LIMIT=3
[ -f "$LIMITS_DIR/$USER" ] && LIMIT=$(cat "$LIMITS_DIR/$USER")
[[ "$LIMIT" =~ ^[0-9]+$ ]] || LIMIT=3
[ "$LIMIT" -le 0 ] && exit 0

get_ws_port() {
    if [ -f /usr/local/bin/ws-proxy.py ]; then
        awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py | tr -dc '0-9'
    fi
}

WS_P=$(get_ws_port)
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

# Превышение — отказываем с красивым сообщением
if [ "$COUNT" -ge "$LIMIT" ]; then
    echo ""
    echo "╔════════════════════════════════════════════╗"
    echo "║   ❌ ПРЕВЫШЕН ЛИМИТ УСТРОЙСТВ              ║"
    echo "╠════════════════════════════════════════════╣"
    printf "║  Разрешено устройств : %-20s ║\n" "$LIMIT"
    printf "║  Сейчас подключено   : %-20s ║\n" "$COUNT"
    echo "║  ⚠️  Отключите другое устройство.          ║"
    echo "╚════════════════════════════════════════════╝"
    echo ""
    exit 1
fi

exit 0
PAM_EOF

chmod +x /usr/local/bin/check-device-limit-pam
echo -e "\033[0;32m✅ Скрипт обновлён: /usr/local/bin/check-device-limit-pam\033[0m"

# 3) Проверяем, что скрипт не падает для root
if ! PAM_USER=root /usr/local/bin/check-device-limit-pam >/dev/null 2>&1; then
    echo -e "\033[0;31m⚠️  Скрипт падает для root — PAM НЕ трогаем!\033[0m"
    exit 1
fi
echo -e "\033[0;32m✅ Скрипт работает корректно.\033[0m"

# 4) Обновляем PAM — добавляем stdout
sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd 2>/dev/null

if grep -q "pam_nologin.so" /etc/pam.d/sshd; then
    sed -i '/pam_nologin.so/a account    required     pam_exec.so stdout /usr/local/bin/check-device-limit-pam' /etc/pam.d/sshd
elif grep -q "@include common-auth" /etc/pam.d/sshd; then
    sed -i '/@include common-auth/a account    required     pam_exec.so stdout /usr/local/bin/check-device-limit-pam' /etc/pam.d/sshd
else
    echo -e "\033[0;31m⚠️  Не найдена точка вставки — PAM не тронут!\033[0m"
    exit 1
fi

echo -e "\033[0;32m✅ PAM обновлён (pam_exec.so stdout)\033[0m"

# 5) Проверка целостности PAM
if ! grep -q "@include common-auth" /etc/pam.d/sshd || ! grep -q "@include common-account" /etc/pam.d/sshd; then
    echo -e "\033[0;31m⚠️  PAM повреждён! Откат...\033[0m"
    sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd
    exit 1
fi

# 6) Показываем что получилось
echo -e "\n\033[0;36m─── Текущая PAM-строка ───\033[0m"
grep -n "check-device-limit-pam" /etc/pam.d/sshd

# 7) Перезапуск sshd
echo -e "\n🔄 Перезапуск sshd..."
echo -e "\033[1;33m⚠️  Текущая SSH-сессия может оборваться.\033[0m"
sleep 2
systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null

echo -e "\n\033[0;32m🟢 Патч успешно применён!\033[0m"
echo -e "Теперь при превышении лимита клиент увидит красивое сообщение."
echo ""
echo -e "\033[0;33mЕсли SSH перестал пускать root — откат:\033[0m"
echo -e "  \033[1;37mcp /etc/pam.d/sshd.bak /etc/pam.d/sshd && systemctl restart ssh\033[0m"
