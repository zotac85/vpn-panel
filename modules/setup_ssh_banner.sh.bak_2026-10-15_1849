#!/bin/bash
# ──────────────────────────────────────────────────────────────
# SSH-баннер при подключении в терминал
# Вызывается из install.sh
# ──────────────────────────────────────────────────────────────
echo -e "\n🎨 Настройка баннера..."
BANNER_FILE="/etc/UDPCustom/ssh_banner.txt"
TEMPLATE="/root/vpn-panel-sync/configs/ssh_banner.txt"
BOT_CONF="/etc/UDPCustom/bot.conf"

# Подключение Banner в sshd_config
if ! grep -qE '^[[:space:]]*Banner' /etc/ssh/sshd_config; then
    echo "Banner $BANNER_FILE" >> /etc/ssh/sshd_config
    echo -e "\033[0;32m✅  Banner подключён.\033[0m"
else
    current=$(grep -E '^[[:space:]]*Banner' /etc/ssh/sshd_config | head -1 | awk '{print $2}')
    [ "$current" != "$BANNER_FILE" ] && sed -i "s|^[[:space:]]*Banner.*|Banner $BANNER_FILE|" /etc/ssh/sshd_config
fi
if [ -f /etc/default/dropbear ]; then
    grep -q "DROPBEAR_BANNER" /etc/default/dropbear 2>/dev/null || \
        echo "DROPBEAR_BANNER=\"$BANNER_FILE\"" >> /etc/default/dropbear
fi

# Читаем локацию из bot.conf
LOCATION="🌍 Сервер"
if [ -f "$BOT_CONF" ]; then
    _loc=$(grep -E '^SERVER_LOCATION=' "$BOT_CONF" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')
    [ -n "$_loc" ] && LOCATION="$_loc"
fi

# Читаем devices из bot.conf
DEVICES="1"
if [ -f "$BOT_CONF" ]; then
    _dev=$(grep -E '^TEST_DEVICES=' "$BOT_CONF" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')
    [ -n "$_dev" ] && DEVICES="$_dev"
fi

# Читаем support (без @)
SUPPORT="support"
if [ -f /etc/UDPCustom/support.txt ]; then
    _s=$(head -1 /etc/UDPCustom/support.txt 2>/dev/null | tr -d '@ ' | head -c 100)
    [ -n "$_s" ] && SUPPORT="$_s"
fi

# Читаем основной канал (первая строка channels.txt, без @)
CHANNEL="ArsenVipKeys"
if [ -f /etc/UDPCustom/channels.txt ]; then
    _ch=$(head -1 /etc/UDPCustom/channels.txt 2>/dev/null | tr -d '@ ' | head -c 100)
    [ -n "$_ch" ] && CHANNEL="$_ch"
fi

# Обновляем из шаблона репы (если есть)
if [ -f "$TEMPLATE" ]; then
    # Подставляем {location}, {devices}, {support}, {channel}
    _new=$(sed -e "s|{location}|$LOCATION|g" -e "s|{devices}|$DEVICES|g" -e "s|{support}|$SUPPORT|g" -e "s|{channel}|$CHANNEL|g" "$TEMPLATE")
    # Сравниваем с текущим
    if [ -f "$BANNER_FILE" ]; then
        _cur=$(cat "$BANNER_FILE")
        if [ "$_new" != "$_cur" ]; then
            cp "$BANNER_FILE" "${BANNER_FILE}.bak_$(date +%F_%H%M)"
            echo "$_new" > "$BANNER_FILE"
            echo -e "\033[0;32m✅  Баннер обновлён (локация: $LOCATION).\033[0m"
        else
            echo -e "\033[0;32m✅  Баннер актуален.\033[0m"
        fi
    else
        echo "$_new" > "$BANNER_FILE"
        echo -e "\033[0;32m✅  Баннер создан (локация: $LOCATION).\033[0m"
    fi
else
    # Нет шаблона в репе — fallback (создаём только если пусто)
    if [ ! -s "$BANNER_FILE" ]; then
        cat > "$BANNER_FILE" << 'BANNER_DEF'
<h5><font color='cyan'>🚀 ArsenVipKeys — Премиум Сервер 🚀</font></h5>
<h6><font color='red'>❌  БЕЗ DDOS</font></h6>
<h6><font color='red'>❌  БЕЗ ВЗЛОМА</font></h6>
<h6><font color='red'>❌  БЕЗ ТОРРЕНТОВ</font></h6>
<h6><font color='red'>❌  БЕЗ СПАМА</font></h6>
<h6><font color='red'>❌  БЕЗ КАРДИНГА</font></h6>
<h6><font color='yellow'>🚫 НАРУШЕНИЕ = БАН НАВСЕГДА 🚫</font></h6>
<h5><font color='green'>💬 Поддержка: t.me/ArsenGuro</font></h5>
<h5><font color='cyan'>📢 Канал: t.me/ArsenVipKeys</font></h5>
<h6><font color='lime'>✅  ПОДКЛЮЧЕНО</font></h6>
BANNER_DEF
        echo -e "\033[0;32m✅  Баннер создан (fallback).\033[0m"
    else
        echo -e "\033[0;32m✅  Баннер уже настроен.\033[0m"
    fi
fi
