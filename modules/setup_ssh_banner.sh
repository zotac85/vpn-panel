#!/bin/bash
# ──────────────────────────────────────────────────────────────
# SSH-баннер при подключении в терминал
# Вызывается из install.sh
# ──────────────────────────────────────────────────────────────

echo -e "\n🎨 Настройка баннера..."

BANNER_FILE="/etc/bannerssh"

if ! grep -qE '^[[:space:]]*Banner' /etc/ssh/sshd_config; then
    echo "Banner $BANNER_FILE" >> /etc/ssh/sshd_config
    echo -e "\033[0;32m✅ Banner подключён.\033[0m"
else
    current=$(grep -E '^[[:space:]]*Banner' /etc/ssh/sshd_config | head -1 | awk '{print $2}')
    [ "$current" != "$BANNER_FILE" ] && sed -i "s|^[[:space:]]*Banner.*|Banner $BANNER_FILE|" /etc/ssh/sshd_config
fi

if [ -f /etc/default/dropbear ]; then
    grep -q "DROPBEAR_BANNER" /etc/default/dropbear 2>/dev/null || \
        echo "DROPBEAR_BANNER=\"$BANNER_FILE\"" >> /etc/default/dropbear
fi

if [ ! -s "$BANNER_FILE" ]; then
    cat > "$BANNER_FILE" << 'BANNER_EOF'
<h5><font color='cyan'>🚀 ArsenVipKeys — Премиум Сервер 🚀</font></h5>
<h6><font color='red'>❌ БЕЗ DDOS</font></h6>
<h6><font color='red'>❌ БЕЗ ВЗЛОМА</font></h6>
<h6><font color='red'>❌ БЕЗ ТОРРЕНТОВ</font></h6>
<h6><font color='red'>❌ БЕЗ СПАМА</font></h6>
<h6><font color='red'>❌ БЕЗ КАРДИНГА</font></h6>
<h6><font color='yellow'>🚫 НАРУШЕНИЕ = БАН НАВСЕГДА 🚫</font></h6>
<h5><font color='green'>💬 Поддержка: t.me/ArsenGuro</font></h5>
<h5><font color='cyan'>📢 Канал: t.me/ArsenVipKeys</font></h5>
<h6><font color='lime'>✅ ПОДКЛЮЧЕНО</font></h6>
BANNER_EOF
    echo -e "\033[0;32m✅ Баннер создан.\033[0m"
else
    echo -e "\033[0;32m✅ Баннер уже настроен.\033[0m"
fi
