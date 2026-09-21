#!/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "Ошибка: запустите скрипт от root (sudo -i)"
  exit 1
fi

PANEL_DIR="/usr/local/share/vpn-panel"
REPO_URL="https://raw.githubusercontent.com/zotac85/vpn-panel/main"

echo -e "\033[0;36m==============================================\033[0m"
echo -e "        \033[1;33m⚡ VPN PANEL INSTALLER / UPDATER ⚡\033[0m"
echo -e "\033[0;36m==============================================\033[0m"

if [ -d "$PANEL_DIR" ] || [ -f "/usr/local/bin/vpn" ]; then
    echo -e "\033[1;33mОбнаружена ранее установленная панель.\033[0m"
    echo ""
    echo " 1) 🔄 Обновить скрипты и модули (базы и настройки сохранятся)"
    echo " 2) ⚙️ Переустановить полностью (сброс конфигурации)"
    echo " 0) 🚪 Отмена"
    echo ""
    read -p "Выберите действие [0-2]: " choice

    case $choice in
        1) echo -e "\n🔄 Обновление компонентов панели..." ;;
        2)
            echo -e "\n⚠️ Полная переустановка..."
            rm -rf "$PANEL_DIR"
            rm -f /usr/local/bin/vpn
            ;;
        *) echo -e "\n❌ Операция отменена."; exit 0 ;;
    esac
fi

mkdir -p "$PANEL_DIR/modules" /etc/UDPCustom/limits /etc/UDPCustom/traffic /etc/UDPCustom/traffic_limits
touch /etc/UDPCustom/users.db

# Откат старого костыля vpn-limit-shell
if [ -f "/etc/UDPCustom/users.db" ]; then
    while read -r u; do
        [ -z "$u" ] && continue
        if id "$u" &>/dev/null; then
            current_shell=$(getent passwd "$u" | cut -d: -f7)
            if [ "$current_shell" == "/usr/local/bin/vpn-limit-shell" ]; then
                chsh -s /bin/false "$u" 2>/dev/null
            fi
        fi
    done < "/etc/UDPCustom/users.db"
fi

# Скачивание модулей
echo -e "\n📥 Скачивание актуальных файлов с GitHub..."
curl -s -o "$PANEL_DIR/core.sh" "$REPO_URL/core.sh"
curl -s -o "$PANEL_DIR/modules/users.sh" "$REPO_URL/modules/users.sh"
curl -s -o "$PANEL_DIR/modules/masterdns.sh" "$REPO_URL/modules/masterdns.sh"
curl -s -o "$PANEL_DIR/modules/udp.sh" "$REPO_URL/modules/udp.sh"
curl -s -o "$PANEL_DIR/modules/ws.sh" "$REPO_URL/modules/ws.sh"
curl -s -o "$PANEL_DIR/modules/security.sh" "$REPO_URL/modules/security.sh"
curl -s -o "$PANEL_DIR/modules/traffic.sh" "$REPO_URL/modules/traffic.sh" 2>/dev/null
curl -s -o "$PANEL_DIR/modules/devicelimit.sh" "$REPO_URL/modules/devicelimit.sh" 2>/dev/null
curl -s -o "$PANEL_DIR/modules/banner.sh" "$REPO_URL/modules/banner.sh" 2>/dev/null

curl -s -o /usr/local/bin/vpn "$REPO_URL/vpn"
chmod +x /usr/local/bin/vpn

# ──────────────────────────────────────────────────────────────
# СХЕМА A: pam_limits (maxlogins для прямого SSH)
# ──────────────────────────────────────────────────────────────
if ! grep -q "pam_limits.so" /etc/pam.d/sshd 2>/dev/null; then
    echo "session required pam_limits.so" >> /etc/pam.d/sshd
    echo -e "\033[0;32m✅ pam_limits подключён к sshd.\033[0m"
else
    echo -e "\033[0;32m✅ pam_limits уже подключён.\033[0m"
fi

if [ -s /etc/UDPCustom/users.db ]; then
    while read -r u; do
        [ -z "$u" ] && continue
        id "$u" &>/dev/null || continue
        limit=3
        [ -f "/etc/UDPCustom/limits/$u" ] && limit=$(cat "/etc/UDPCustom/limits/$u")
        [[ "$limit" =~ ^[0-9]+$ ]] || limit=3
        sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
        sed -i "/^${u}[[:space:]]\+soft[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
        echo "${u} hard maxlogins ${limit}" >> /etc/security/limits.conf
    done < /etc/UDPCustom/users.db
    echo -e "\033[0;32m✅ maxlogins синхронизирован.\033[0m"
fi

# ──────────────────────────────────────────────────────────────
# СХЕМА B: pam_exec в ACCOUNT-фазе (лимит для WS-туннелей)
# ──────────────────────────────────────────────────────────────
echo -e "\n🔒 Настройка pam_exec (лимит устройств для WS-туннелей)..."

# Удаляем старые строки (show-welcome больше не нужен)
sed -i '/show-welcome/d' /etc/pam.d/sshd 2>/dev/null
sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd 2>/dev/null

cat << 'PAM_EOF' > /usr/local/bin/check-device-limit-pam
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
    echo "❌ ПРЕВЫШЕН ЛИМИТ УСТРОЙСТВ ($COUNT/$LIMIT). Отключите другое устройство."
    exit 1
fi
exit 0
PAM_EOF

chmod +x /usr/local/bin/check-device-limit-pam

echo -e "\n🔍 Проверка скрипта лимита..."
if ! PAM_USER=root /usr/local/bin/check-device-limit-pam >/dev/null 2>&1; then
    echo -e "\033[0;31m⚠️  Скрипт лимита падает — PAM НЕ трогаем!\033[0m"
else
    echo -e "\033[0;32m✅ Скрипт лимита работает.\033[0m"
    if grep -q "pam_nologin.so" /etc/pam.d/sshd; then
        sed -i '/pam_nologin.so/a account    required     pam_exec.so stdout /usr/local/bin/check-device-limit-pam' /etc/pam.d/sshd
        echo -e "\033[0;32m✅ pam_exec добавлен в account-фазу.\033[0m"
    fi
fi

# ──────────────────────────────────────────────────────────────
# БАННЕР (HTML через Banner в sshd_config)
# ──────────────────────────────────────────────────────────────
echo -e "\n🎨 Настройка баннера (HTML)..."

BANNER_FILE="/etc/bannerssh"

# Подключаем Banner к sshd_config
if ! grep -qE '^[[:space:]]*Banner' /etc/ssh/sshd_config; then
    echo "Banner $BANNER_FILE" >> /etc/ssh/sshd_config
    echo -e "\033[0;32m✅ Banner подключён к sshd_config.\033[0m"
else
    current=$(grep -E '^[[:space:]]*Banner' /etc/ssh/sshd_config | head -1 | awk '{print $2}')
    if [ "$current" != "$BANNER_FILE" ]; then
        sed -i "s|^[[:space:]]*Banner.*|Banner $BANNER_FILE|" /etc/ssh/sshd_config
        echo -e "\033[0;32m✅ Banner перенаправлен на $BANNER_FILE.\033[0m"
    else
        echo -e "\033[0;32m✅ Banner уже подключён.\033[0m"
    fi
fi

# Dropbear — если установлен
if [ -f /etc/default/dropbear ]; then
    if ! grep -q "DROPBEAR_BANNER" /etc/default/dropbear 2>/dev/null; then
        echo "DROPBEAR_BANNER=\"$BANNER_FILE\"" >> /etc/default/dropbear
        echo -e "\033[0;32m✅ DROPBEAR_BANNER подключён.\033[0m"
    fi
fi

# Создаём баннер (только если пустой)
if [ ! -s "$BANNER_FILE" ]; then
    cat > "$BANNER_FILE" << 'EOF'
<h4><font color='cyan'>🚀 ArsenVipKeys Premium Server 🚀</font></h4>
<h6><font color='red'>❌ NO DDOS ❌</font></h6>
<h6><font color='red'>❌ NO HACKING ❌</font></h6>
<h6><font color='red'>❌ NO TORRENT ❌</font></h6>
<h6><font color='red'>❌ NO SPAMMING ❌</font></h6>
<h6><font color='red'>❌ NO CARDING ❌</font></h6>
<h6><font color='#F535AA'>👥 MAX LOGIN 2 DEVICE 👥</font></h6>
<h6><font color='yellow'>🚫 VIOLATE AUTO BANNED PERMANENT 🚫</font></h6>
<h4><font color='green'>💬 Support: t.me/ArsenGuro</font></h4>
<h4><font color='cyan'>📢 Channel: t.me/ArsenVipKeys</font></h4>
EOF
    echo -e "\033[0;32m✅ Баннер по умолчанию создан.\033[0m"
else
    echo -e "\033[0;32m✅ Баннер уже настроен (не перезаписываем).\033[0m"
fi

# ──────────────────────────────────────────────────────────────
# СХЕМА C: Страховочный cron (устройства + трафик)
# ──────────────────────────────────────────────────────────────
echo -e "\n🛡️ Автовключение контроля лимитов..."

cat << 'CHK_EOF' > /usr/local/bin/vpn-limit-check.sh
#!/bin/bash
DB_USERS="/etc/UDPCustom/users.db"
LIMITS_DIR="/etc/UDPCustom/limits"
LOG_FILE="/var/log/vpn-limit-check.log"

get_ws_port() {
    if [ -f /usr/local/bin/ws-proxy.py ]; then
        awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py | tr -dc '0-9'
    fi
}

ws_p=$(get_ws_port)
filter="( sport = :22 or sport = :36712 or sport = :7300"
[[ "$ws_p" =~ ^[0-9]+$ ]] && filter="$filter or sport = :$ws_p"
filter="$filter )"

data=$(ss -H -tnp state established "$filter" 2>/dev/null)

declare -A CONN_USER CONN_PIDS CONN_TIME
idx=0
while IFS= read -r line; do
    [ -z "$line" ] && continue
    head="${line%%users:(*}"
    peer=$(echo "$head" | awk '{print $NF}')
    [[ "$peer" == *:* ]] || continue
    pids=$(echo "$line" | grep -oP 'pid=\K[0-9]+')
    [ -z "$pids" ] && continue
    u=""
    for p in $pids; do
        owner=$(ps -o user= -p "$p" 2>/dev/null | tr -d ' ')
        if [ -n "$owner" ] && [ "$owner" != "root" ]; then u="$owner"; break; fi
    done
    [ -z "$u" ] && continue
    reftime=0
    for p in $pids; do
        t=$(stat -c %Y "/proc/$p" 2>/dev/null)
        [ -n "$t" ] && { reftime=$t; break; }
    done
    CONN_USER[$idx]="$u"; CONN_PIDS[$idx]="$pids"; CONN_TIME[$idx]="$reftime"
    ((idx++))
done <<< "$data"

declare -A USER_INDICES
for ((i=0; i<idx; i++)); do
    u="${CONN_USER[$i]}"
    USER_INDICES[$u]="${USER_INDICES[$u]} $i"
done

for u in "${!USER_INDICES[@]}"; do
    limit=3
    [ -f "$LIMITS_DIR/$u" ] && limit=$(cat "$LIMITS_DIR/$u")
    [[ "$limit" =~ ^[0-9]+$ ]] || limit=3
    [ "$limit" -le 0 ] && continue
    idxs=(${USER_INDICES[$u]}); count=${#idxs[@]}
    [ "$count" -le "$limit" ] && continue
    sorted_idxs=($(for i in "${idxs[@]}"; do echo "${CONN_TIME[$i]} $i"; done | sort -n | awk '{print $2}'))
    to_kill=$(( count - limit ))
    for ((k=count-to_kill; k<count; k++)); do
        conn_i=${sorted_idxs[$k]}
        for p in ${CONN_PIDS[$conn_i]}; do kill -9 "$p" 2>/dev/null; done
        echo "$(date '+%Y-%m-%d %H:%M:%S') Отключён лишний сеанс: user=$u count=$count limit=$limit" >> "$LOG_FILE"
    done
done
CHK_EOF
chmod +x /usr/local/bin/vpn-limit-check.sh
echo "* * * * * root /usr/local/bin/vpn-limit-check.sh" > /etc/cron.d/vpn-device-limit
chmod 644 /etc/cron.d/vpn-device-limit

iptables -N VPN_TRAFFIC 2>/dev/null
iptables -C OUTPUT -j VPN_TRAFFIC 2>/dev/null || iptables -I OUTPUT -j VPN_TRAFFIC

if [ -s /etc/UDPCustom/users.db ]; then
    while read -r u; do
        [ -z "$u" ] && continue
        id "$u" &>/dev/null || continue
        uid=$(id -u "$u" 2>/dev/null)
        [ -z "$uid" ] && continue
        iptables -C VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || \
        iptables -A VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN
    done < /etc/UDPCustom/users.db
fi

cat << 'CHK_EOF' > /usr/local/bin/vpn-traffic-check.sh
#!/bin/bash
TRAFFIC_DIR="/etc/UDPCustom/traffic"
TRAFFIC_LIMITS_DIR="/etc/UDPCustom/traffic_limits"
TRAFFIC_CHAIN="VPN_TRAFFIC"
DB_USERS="/etc/UDPCustom/users.db"

mkdir -p "$TRAFFIC_DIR"
iptables -L "$TRAFFIC_CHAIN" -n &>/dev/null || exit 0

while read -r u; do
    [ -z "$u" ] && continue
    uid=$(id -u "$u" 2>/dev/null) || continue
    cur=$(iptables -L "$TRAFFIC_CHAIN" -v -x -n 2>/dev/null | awk -v pat="UID match $uid\$" '$0 ~ pat {print $2}' | head -1)
    [ -z "$cur" ] && cur=0
    total_file="$TRAFFIC_DIR/$u"
    [ -f "$total_file" ] || echo 0 > "$total_file"
    prev_total=$(cat "$total_file")
    new_total=$((prev_total + cur))
    echo "$new_total" > "$total_file"
    iptables -D "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN 2>/dev/null
    iptables -A "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN
    limit_file="$TRAFFIC_LIMITS_DIR/$u"
    if [ -f "$limit_file" ]; then
        limit_bytes=$(cat "$limit_file")
        if [[ "$limit_bytes" =~ ^[0-9]+$ ]] && [ "$limit_bytes" -gt 0 ] && [ "$new_total" -ge "$limit_bytes" ]; then
            usermod -L "$u" 2>/dev/null
        fi
    fi
done < "$DB_USERS"
CHK_EOF
chmod +x /usr/local/bin/vpn-traffic-check.sh
echo "*/5 * * * * root /usr/local/bin/vpn-traffic-check.sh" > /etc/cron.d/vpn-traffic-check
chmod 644 /etc/cron.d/vpn-traffic-check

systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null

# ──────────────────────────────────────────────────────────────
# ФИНАЛЬНАЯ ПРОВЕРКА PAM
# ──────────────────────────────────────────────────────────────
echo -e "\n🔍 Финальная проверка конфигурации..."
PAM_OK=1

grep -q "@include common-auth" /etc/pam.d/sshd || { echo -e "\033[0;31m⚠️  @include common-auth отсутствует!\033[0m"; PAM_OK=0; }
grep -q "@include common-account" /etc/pam.d/sshd || { echo -e "\033[0;31m⚠️  @include common-account отсутствует!\033[0m"; PAM_OK=0; }

# Дубликаты pam_exec
for pat in "check-device-limit-pam" "show-welcome"; do
    cnt=$(grep -c "$pat" /etc/pam.d/sshd 2>/dev/null || echo 0)
    if [ "$cnt" -gt 1 ]; then
        echo -e "\033[0;33m⚠️  Дубликаты $pat — оставляем одну.\033[0m"
        first=1
        : > /tmp/sshd.clean
        while IFS= read -r line; do
            if echo "$line" | grep -q "$pat"; then
                [ "$first" -eq 1 ] && { first=0; echo "$line" >> /tmp/sshd.clean; }
            else
                echo "$line" >> /tmp/sshd.clean
            fi
        done < /etc/pam.d/sshd
        mv /tmp/sshd.clean /etc/pam.d/sshd
    fi
done

if [ "$PAM_OK" -eq 1 ]; then
    echo -e "\033[0;32m✅ PAM-конфигурация в порядке.\033[0m"
    echo -e "\n🔄 Перезапуск sshd..."
    sleep 2
    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
    [ -f /etc/default/dropbear ] && systemctl restart dropbear 2>/dev/null
else
    echo -e "\033[0;31m⚠️  PAM повреждён! Откат...\033[0m"
    sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd
    echo -e "\033[0;33mСтроки удалены. sshd НЕ перезапущен.\033[0m"
fi

echo -e "\033[0;32m✅ Контроль лимитов и баннер включены.\033[0m"

echo -e "\n\033[0;32m🟢 Операция успешно завершена, Хозяин!\033[0m"
echo -e "Теперь для запуска панели введите: \033[1;33mvpn\033[0m"
