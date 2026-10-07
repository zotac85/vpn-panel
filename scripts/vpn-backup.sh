#!/bin/bash
# Автобэкап БД VPN-панели + отправка в Telegram

BACKUP_DIR="/root/backups"
SRC_DIR="/etc/UDPCustom"
KEEP_DAYS=14
TS=$(date +%F_%H%M)
SUPPORT_CONF="/etc/UDPCustom/support_bot.conf"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

DB_FILES="bot_issued.db support.db user_tg_map.db users.db verified_users.db vpn.db referrals.db referral_bonus.db"
CFG_FILES="bot.conf support_bot.conf autopost.conf admins.txt channels.txt support.txt ad.txt"
CFG_FILES="$CFG_FILES welcome.txt start.txt help.txt test_ready.txt test_issued.txt"
CFG_FILES="$CFG_FILES help_instruction.txt help_faq.txt help_darktunnel.txt help_httpcustom.txt"
CFG_FILES="$CFG_FILES help_video.txt help_whitedns.txt vip_buy.txt post.txt ref_post.txt"
CFG_FILES="$CFG_FILES faq_keywords.txt payload.txt proxies.txt rate.txt ssh_banner.txt"
CFG_FILES="$CFG_FILES whitedns_resolvers.txt whitedns_resolvers_de.txt whitedns_resolvers_fi.txt"
CFG_FILES="$CFG_FILES whitedns_resolvers_se.txt whitedns_servers.txt"
CFG_FILES="$CFG_FILES whitedns_settings_3g.txt whitedns_settings_adsl.txt whitedns_settings_wifi.txt"
COUNT=0
ERROR=0

backup_one() {
    src="$1"; dst="$2"
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
HOSTNAME=$(hostname)
MSG="💾 Автобэкап: ${HOSTNAME}
📦 backup_${TS}.tar.gz (${SIZE})
📁 Файлов: ${COUNT}, ошибок: ${ERROR}"
echo "$(date '+%F %T') $MSG"

# Отправка в Telegram (бот поддержки)
if [ -f "$SUPPORT_CONF" ]; then
    TG_TOKEN=$(grep -oP '(?<=BOT_TOKEN=")[^"]+' "$SUPPORT_CONF" | head -1)
    TG_ADMIN=$(grep -oP '(?<=ADMIN_ID=")[^"]+' "$SUPPORT_CONF" | head -1)
    if [ -n "$TG_TOKEN" ] && [ -n "$TG_ADMIN" ] && [ -f "backup_${TS}.tar.gz" ]; then
        curl -s -F "chat_id=${TG_ADMIN}" \
             -F "caption=${MSG}" \
             -F "document=@backup_${TS}.tar.gz" \
             "https://api.telegram.org/bot${TG_TOKEN}/sendDocument" > /dev/null 2>&1
    fi
fi
