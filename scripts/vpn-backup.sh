#!/bin/bash
# Автобэкап БД VPN-панели

BACKUP_DIR="/root/backups"
SRC_DIR="/etc/UDPCustom"
KEEP_DAYS=14
TS=$(date +%F_%H%M)

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

DB_FILES="bot_issued.db support.db user_tg_map.db users.db verified_users.db vpn.db referrals.db referral_bonus.db"
CFG_FILES="bot.conf support_bot.conf autopost.conf channels.txt support.txt"
COUNT=0
ERROR=0

backup_one() {
    src="$1"; dst="$2"
    # Если это SQLite — безопасный backup через API
    if head -c 16 "$src" 2>/dev/null | grep -q "SQLite format 3"; then
        python3 -c "import sqlite3; s=sqlite3.connect('$src'); d=sqlite3.connect('$dst'); s.backup(d); d.close(); s.close()" 2>/dev/null && return 0 || return 1
    else
        cp "$src" "$dst" 2>/dev/null && return 0 || return 1
    fi
}

for f in $DB_FILES; do
    if [ -f "$SRC_DIR/$f" ]; then
        if backup_one "$SRC_DIR/$f" "$BACKUP_DIR/${f}.${TS}"; then
            COUNT=$((COUNT+1))
        else
            ERROR=$((ERROR+1))
        fi
    fi
done

for f in $CFG_FILES; do
    if [ -f "$SRC_DIR/$f" ]; then
        cp "$SRC_DIR/$f" "$BACKUP_DIR/${f}.${TS}" 2>/dev/null && COUNT=$((COUNT+1)) || ERROR=$((ERROR+1))
    fi
done

cd "$BACKUP_DIR" || exit 1
tar -czf "backup_${TS}.tar.gz" *.${TS} 2>/dev/null
rm -f *.${TS}

find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null

SIZE=$(du -h "backup_${TS}.tar.gz" 2>/dev/null | cut -f1)
echo "$(date '+%F %T') Бэкап: backup_${TS}.tar.gz (${SIZE}), файлов: ${COUNT}, ошибок: ${ERROR}"
