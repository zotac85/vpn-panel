#!/bin/bash
# vpn-auto-cleanup.sh — удаляет истёкших + висячих юзеров (cron каждый час)
DB="/etc/UDPCustom/vpn.db"
DB_USERS="/etc/UDPCustom/users.db"
LIMITS_DIR="/etc/UDPCustom/limits"
TRAFFIC_LIMITS_DIR="/etc/UDPCustom/traffic_limits"
TRAFFIC_DIR="/etc/UDPCustom/traffic"
EXPIRE_DIR="/etc/UDPCustom/expire_ts"
PASSWORDS_DIR="/etc/UDPCustom/passwords"
LOG="/var/log/vpn-auto-cleanup.log"
NOW=$(date +%s)

[ -s "$DB_USERS" ] || exit 0

# Получаем список всех логинов из vpn.db
DB_KEYS_FILE=$(mktemp)
python3 - > "$DB_KEYS_FILE" << 'PY'
import sqlite3
db = sqlite3.connect('/etc/UDPCustom/vpn.db')
seen = set()
for tbl in ['test_keys', 'vip_keys']:
    for r in db.execute(f"SELECT login FROM {tbl}").fetchall():
        if r[0] and r[0] not in seen:
            seen.add(r[0])
            print(r[0])
PY

# Список нод для чистки
NODES_FILE=$(mktemp)
python3 - > "$NODES_FILE" << 'PY'
import sqlite3
db = sqlite3.connect('/etc/UDPCustom/vpn.db')
for r in db.execute("SELECT ip, ssh_port FROM nodes WHERE is_active=1 AND is_master=0").fetchall():
    print(f"{r[0]}|{r[1]}")
PY

# Удаление на нодах
delete_on_nodes() {
    local user="$1"
    while IFS='|' read -r ip port; do
        [ -z "$ip" ] && continue
        ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -p "$port" root@"$ip" "
            id -u '$user' &>/dev/null && userdel -f '$user' 2>/dev/null
            sed -i '/^$user\$/d' /etc/UDPCustom/users.db 2>/dev/null
            rm -f /etc/UDPCustom/limits/$user /etc/UDPCustom/traffic_limits/$user /etc/UDPCustom/traffic/$user /etc/UDPCustom/expire_ts/$user /etc/UDPCustom/passwords/$user 2>/dev/null
        " </dev/null 2>/dev/null
    done < "$NODES_FILE"
}

TMP_DB=$(mktemp)
: > "$TMP_DB"

while read -r u; do
    [ -z "$u" ] && continue
    id "$u" &>/dev/null || continue

    # Проверка 1: висячий (нет в vpn.db)
    if ! grep -q "^$u$" "$DB_KEYS_FILE"; then
        uid=$(id -u "$u" 2>/dev/null)
        [ -n "$uid" ] && while iptables -D VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null; do :; done
        userdel -f "$u" 2>/dev/null
        rm -f "$LIMITS_DIR/$u" "$TRAFFIC_LIMITS_DIR/$u" "$TRAFFIC_DIR/$u" "$EXPIRE_DIR/$u" "$PASSWORDS_DIR/$u" 2>/dev/null
        sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
        delete_on_nodes "$u"
        echo "$(date '+%F %T') Удалён висячий: $u" >> "$LOG"
        continue
    fi

    # Проверка 2: истёк по chage
    exp_raw=$(chage -l "$u" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
    if [ "$exp_raw" == "never" ] || [ -z "$exp_raw" ]; then
        echo "$u" >> "$TMP_DB"
        continue
    fi
    exp_epoch=$(date -d "$exp_raw" +%s 2>/dev/null)
    [ -z "$exp_epoch" ] && { echo "$u" >> "$TMP_DB"; continue; }
    if [ "$exp_epoch" -ge "$NOW" ]; then
        echo "$u" >> "$TMP_DB"
        continue
    fi
    # Истёк — удаляем
    uid=$(id -u "$u" 2>/dev/null)
    [ -n "$uid" ] && while iptables -D VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null; do :; done
    userdel -f "$u" 2>/dev/null
    rm -f "$LIMITS_DIR/$u" "$TRAFFIC_LIMITS_DIR/$u" "$TRAFFIC_DIR/$u" "$EXPIRE_DIR/$u" "$PASSWORDS_DIR/$u" 2>/dev/null
    sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
    delete_on_nodes "$u"
    echo "$(date '+%F %T') Удалён истёкший: $u (истёк $exp_raw)" >> "$LOG"
done < "$DB_USERS"

sort -u "$TMP_DB" | grep -v '^$' > "$DB_USERS"
rm -f "$TMP_DB" "$DB_KEYS_FILE" "$NODES_FILE"
