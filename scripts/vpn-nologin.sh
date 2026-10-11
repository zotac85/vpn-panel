#!/bin/bash
# vpn-nologin.sh — кастомный shell для заблокированных юзеров
SUPPORT_FILE="/etc/UDPCustom/support.txt"
SUPPORT="@ArsenSupportBot"
if [ -f "$SUPPORT_FILE" ]; then
    _s=$(head -1 "$SUPPORT_FILE" 2>/dev/null | tr -d '[:space:]' | head -c 100)
    [ -n "$_s" ] && SUPPORT="$_s"
fi
echo ""
echo "❌  СРОК ДЕЙСТВИЯ КЛЮЧА ИСТЁК"
echo "Обратись в поддержку: $SUPPORT"
echo ""
exit 1
