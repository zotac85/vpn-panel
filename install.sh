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

# Проверяем, установлена ли панель ранее
if [ -d "$PANEL_DIR" ] || [ -f "/usr/local/bin/vpn" ]; then
    echo -e "\033[1;33mОбнаружена ранее установленная панель.\033[0m"
    echo ""
    echo " 1) 🔄 Обновить скрипты и модули (базы и настройки сохранятся)"
    echo " 2) ⚙️ Переустановить полностью (сброс конфигурации)"
    echo " 0) 🚪 Отмена"
    echo ""
    read -p "Выберите действие [0-2]: " choice

    case $choice in
        1)
            echo -e "\n🔄 Обновление компонентов панели..."
            ;;
        2)
            echo -e "\n⚠️ Полная переустановка..."
            rm -rf "$PANEL_DIR"
            rm -f /usr/local/bin/vpn
            ;;
        *)
            echo -e "\n❌ Операция отменена."
            exit 0
            ;;
    esac
fi

# Создаем необходимые папки и файлы, если их нет
mkdir -p "$PANEL_DIR/modules" /etc/UDPCustom/limits /etc/UDPCustom/traffic /etc/UDPCustom/traffic_limits
touch /etc/UDPCustom/users.db

# Откат старого костыля vpn-limit-shell (если остался)
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

# Скачивание ядра и модулей с GitHub
echo -e "\n📥 Скачивание актуальных файлов с GitHub..."
curl -s -o "$PANEL_DIR/core.sh" "$REPO_URL/core.sh"
curl -s -o "$PANEL_DIR/modules/users.sh" "$REPO_URL/modules/users.sh"
curl -s -o "$PANEL_DIR/modules/masterdns.sh" "$REPO_URL/modules/masterdns.sh"
curl -s -o "$PANEL_DIR/modules/udp.sh" "$REPO_URL/modules/udp.sh"
curl -s -o "$PANEL_DIR/modules/ws.sh" "$REPO_URL/modules/ws.sh"
curl -s -o "$PANEL_DIR/modules/security.sh" "$REPO_URL/modules/security.sh"
curl -s -o "$PANEL_DIR/modules/traffic.sh" "$REPO_URL/modules/traffic.sh" 2>/dev/null
curl -s -o "$PANEL_DIR/modules/devicelimit.sh" "$REPO_URL/modules/devicelimit.sh" 2>/dev/null

# Скачивание главного исполняемого файла (точки входа)
curl -s -o /usr/local/bin/vpn "$REPO_URL/vpn"
chmod +x /usr/local/bin/vpn

# ──────────────────────────────────────────────────────────────
# СХЕМА A: Подключаем pam_limits к sshd (для maxlogins)
# ──────────────────────────────────────────────────────────────
if ! grep -q "pam_limits.so" /etc/pam.d/sshd 2>/dev/null; then
    echo "session required pam_limits.so" >> /etc/pam.d/sshd
    echo -e "\033[0;32m✅ pam_limits подключён к sshd (maxlogins будет работать).\033[0m"
else
    echo -e "\033[0;32m✅ pam_limits уже подключён к sshd.\033[0m"
fi

# ──────────────────────────────────────────────────────────────
# СХЕМА A: Синхронизация maxlogins для УЖЕ существующих юзеров
# (на случай обновления панели, когда юзеры уже созданы)
# ──────────────────────────────────────────────────────────────
if [ -s /etc/UDPCustom/users.db ]; then
    while read -r u; do
        [ -z "$u" ] && continue
        id "$u" &>/dev/null || continue

        limit=3
        [ -f "/etc/UDPCustom/limits/$u" ] && limit=$(cat "/etc/UDPCustom/limits/$u")
        [[ "$limit" =~ ^[0-9]+$ ]] || limit=3

        # Чистим старые записи и добавляем новую
        sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
        sed -i "/^${u}[[:space:]]\+soft[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
        echo "${u} hard maxlogins ${limit}" >> /etc/security/limits.conf
    done < /etc/UDPCustom/users.db
    echo -e "\033[0;32m✅ maxlogins синхронизирован для всех пользователей.\033[0m"
fi

# ──────────────────────────────────────────────────────────────
# СХЕМА C: АВТОВКЛЮЧЕНИЕ КОНТРОЛЯ ЛИМИТОВ (устройства + трафик)
# Делаем напрямую, не через функции модулей — installer не source'ит их.
# ──────────────────────────────────────────────────────────────
echo -e "\n🛡️ Автовключение контроля лимитов..."

# 1) Контроль лимита устройств — cron раз в минуту (страховка для схемы A)
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

# 2) Мониторинг трафика — iptables-цепочка + cron раз в 5 минут
iptables -N VPN_TRAFFIC 2>/dev/null
iptables -C OUTPUT -j VPN_TRAFFIC 2>/dev/null || iptables -I OUTPUT -j VPN_TRAFFIC

# Добавляем правила-счётчики для существующих пользователей
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

# Перезапуск cron, чтобы подхватил новые задания
systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null

echo -e "\033[0;32m✅ Контроль лимитов включён автоматически (устройства + трафик).\033[0m"

echo -e "\n\033[0;32m🟢 Операция успешно завершена, Хозяин!\033[0m"
echo -e "Теперь для запуска панели просто введите в консоли: \033[1;33mvpn\033[0m"
