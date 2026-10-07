#!/bin/bash
# Восстановление VPN-панели из автобэкапа
# Использование: vpn-restore.sh <путь_к_архиву>
set -e

ARCHIVE="$1"
DEST="/etc/UDPCustom"
TMP="/tmp/vpn-restore-$$"

if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
    echo "❌ Укажи путь к архиву backup_*.tar.gz"
    echo "Пример: $0 /root/backup_2026-10-07_1324.tar.gz"
    exit 1
fi

echo "🗂  Архив : $ARCHIVE"
echo "📁 Цель  : $DEST"
echo ""

# Извлекаем список файлов
mkdir -p "$TMP"
tar xzf "$ARCHIVE" -C "$TMP"

COUNT=$(ls "$TMP" | wc -l)
echo "📦 Файлов в архиве: $COUNT"
echo ""
echo "Файлы:"
ls "$TMP" | sed 's/^/  - /'
echo ""
read -p "⚠️  Перезаписать файлы в $DEST? (y/n): " ans
[ "$ans" != "y" ] && { echo "Отменено"; rm -rf "$TMP"; exit 0; }

# Бэкап текущего состояния
SAFE="/root/pre-restore-$(date +%F_%H%M)"
mkdir -p "$SAFE"
cp -a "$DEST"/*.conf "$DEST"/*.txt "$DEST"/*.db "$SAFE/" 2>/dev/null || true
echo "💾 Бэкап текущего: $SAFE"
echo ""

# Раскладываем файлы (срезаем суффикс .YYYY-MM-DD_HHMM)
RESTORED=0
for f in "$TMP"/*; do
    name=$(basename "$f")
    base=$(echo "$name" | sed -E 's/\.20[0-9]{2}-[0-9]{2}-[0-9]{2}_[0-9]{4}$//')
    cp "$f" "$DEST/$base"
    chmod 600 "$DEST/$base"
    RESTORED=$((RESTORED+1))
done

rm -rf "$TMP"
echo ""
echo "✅ Восстановлено файлов: $RESTORED"
echo ""

# Перезапуск сервисов
read -p "🔄 Перезапустить vpn-tg-bot и support-bot? (y/n): " rans
if [ "$rans" = "y" ]; then
    systemctl restart vpn-tg-bot support-bot 2>/dev/null || true
    sleep 2
    echo "vpn-tg-bot : $(systemctl is-active vpn-tg-bot 2>/dev/null)"
    echo "support-bot: $(systemctl is-active support-bot 2>/dev/null)"
fi

echo ""
echo "🎉 Готово. Проверь логи:"
echo "   tail -20 /var/log/vpn-tg-bot.log"
