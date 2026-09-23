#!/bin/bash
DB_USERS="/etc/UDPCustom/users.db"
LIMITS_DIR="/etc/UDPCustom/limits"
TRAFFIC_LIMITS_DIR="/etc/UDPCustom/traffic_limits"
TRAFFIC_DIR="/etc/UDPCustom/traffic"
LOG_FILE="/var/log/vpn-auto-cleanup.log"
[ ! -s "$DB_USERS" ] && exit 0
TODAY=$(date +%s)
TMP_DB=$(mktemp)
: > "$TMP_DB"
while read -r u; do
    [ -z "$u" ] && continue
    id "$u" &>/dev/null || continue
    exp_raw=$(chage -l "$u" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
    if [ "$exp_raw" == "never" ] || [ -z "$exp_raw" ]; then
        echo "$u" >> "$TMP_DB"
        continue
    fi
    # Приоритет: timestamp из expire_ts
    ts_file="/etc/UDPCustom/expire_ts/$u"
    if [ -f "$ts_file" ]; then
        exp_epoch=$(cat "$ts_file" 2>/dev/null)
    else
        exp_epoch=$(date -d "$exp_raw" +%s 2>/dev/null)
    fi
    [ -z "$exp_epoch" ] && { echo "$u" >> "$TMP_DB"; continue; }
    if [ "$exp_epoch" -ge "$TODAY" ]; then
        echo "$u" >> "$TMP_DB"
        continue
    fi
    uid=$(id -u "$u" 2>/dev/null)
    [ -n "$uid" ] && while iptables -D VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null; do :; done
    userdel -f "$u" 2>/dev/null
    rm -f "$LIMITS_DIR/$u" "$TRAFFIC_LIMITS_DIR/$u" "$TRAFFIC_DIR/$u" "/etc/UDPCustom/expire_ts/$u" 2>/dev/null
    sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
    sed -i "/^${u}[[:space:]]\+soft[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
    echo "$(date '+%Y-%m-%d %H:%M:%S') Удалён истёкший: $u (истёк $exp_raw)" >> "$LOG_FILE"
done < "$DB_USERS"
sort -u "$TMP_DB" | grep -v '^$' > "$DB_USERS" 2>/dev/null
rm -f "$TMP_DB"

# ─── Очистка bot_issued.db (старше 30 дней) ───
ISSUED_DB="/etc/UDPCustom/bot_issued.db"
if [ -f "$ISSUED_DB" ]; then
    THRESHOLD=$(( $(date +%s) - 30*86400 ))
    TMP=$(mktemp)
    KEPT=0
    REMOVED=0
    while IFS= read -r line; do
        TS=$(echo "$line" | cut -d'|' -f2)
        if [[ "$TS" =~ ^[0-9]+$ ]] && [ "$TS" -ge "$THRESHOLD" ]; then
            echo "$line" >> "$TMP"
            KEPT=$((KEPT+1))
        else
            REMOVED=$((REMOVED+1))
        fi
    done < "$ISSUED_DB"
    mv "$TMP" "$ISSUED_DB"
    echo "$(date '+%Y-%m-%d %H:%M:%S') bot_issued.db: удалено $REMOVED, оставлено $KEPT" >> "$LOG_FILE"
fi
