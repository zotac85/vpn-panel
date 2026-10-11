#!/bin/bash
# vpn-expiry-check.sh — блокировка юзеров с истёкшим сроком (cron каждую минуту)
TS_DIR="/etc/UDPCustom/expire_ts"
LOG="/var/log/vpn-expiry-check.log"
NOW=$(date +%s)

[ -d "$TS_DIR" ] || exit 0

for ts_file in "$TS_DIR"/*; do
    [ -f "$ts_file" ] || continue
    user=$(basename "$ts_file")
    # Нас интересуют только наши юзеры
    case "$user" in
        vip*|test*) ;;
        *) continue ;;
    esac

    exp=$(cat "$ts_file" 2>/dev/null)
    [[ "$exp" =~ ^[0-9]+$ ]] || continue

    # Получаем текущий shell
    shell=$(getent passwd "$user" | cut -d: -f7)

    if [ "$NOW" -gt "$exp" ]; then
        # Срок истёк — блокируем
        if [ "$shell" != "/usr/sbin/nologin" ]; then
            usermod -L "$user" 2>/dev/null
            usermod -s /usr/sbin/nologin "$user" 2>/dev/null
            pkill -KILL -u "$user" 2>/dev/null
            echo "$(date '+%F %T') EXPIRED: $user (exp=$exp)" >> "$LOG"
        fi
    else
        # Срок активен — разблокируем
        if [ "$shell" = "/usr/sbin/nologin" ]; then
            usermod -U "$user" 2>/dev/null
            usermod -s /bin/false "$user" 2>/dev/null
            echo "$(date '+%F %T') RESTORED: $user" >> "$LOG"
        fi
    fi
done
