#!/bin/bash
USER_NAME="$USER"
SUPPORT_FILE="/etc/UDPCustom/support.txt"
SUPPORT="@ArsenSupportBot"
if [ -f "$SUPPORT_FILE" ]; then
    _s=$(head -1 "$SUPPORT_FILE" 2>/dev/null | tr -d '[:space:]' | head -c 100)
    [ -n "$_s" ] && SUPPORT="$_s"
fi

NOW=$(date +%s)
EXP=0
[ -f "/etc/UDPCustom/expire_ts/$USER_NAME" ] && EXP=$(cat "/etc/UDPCustom/expire_ts/$USER_NAME")

echo ""
if [ "$EXP" -gt 0 ] && [ "$NOW" -gt "$EXP" ]; then
    echo "<h5><b><font color='#FF0000'>❌ СРОК ДЕЙСТВИЯ КЛЮЧА ИСТЁК</font></b></h5>"
    echo "<h6><font color='#FF4444'>Пожалуйста, продлите ключ в личном кабинете бота.</font></h6>"
else
    echo "<h5><b><font color='#FF0000'>❌ ТРАФИК ИСЧЕРПАН</font></b></h5>"
    echo "<h6><font color='#FF4444'>Пожалуйста, пополните баланс или купите новый ключ в боте.</font></h6>"
fi

echo "<h6>💬 Поддержка: @$SUPPORT</h6>"
echo ""

if [ -f /etc/UDPCustom/ssh_banner.txt ]; then
    cat /etc/UDPCustom/ssh_banner.txt
fi
echo ""
exit 1
