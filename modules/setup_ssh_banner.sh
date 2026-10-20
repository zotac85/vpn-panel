#!/bin/bash
# ──────────────────────────────────────────────────────────────
# SSH-баннер при подключении в терминал
# Вызывается из install.sh
# ──────────────────────────────────────────────────────────────
echo -e "\n🎨 Настройка баннера..."
BANNER_FILE="/etc/UDPCustom/ssh_banner.txt"
BOT_CONF="/etc/UDPCustom/bot.conf"
REPO_URL="https://raw.githubusercontent.com/zotac85/vpn-panel/main"
# Скачиваем свежий шаблон из GitHub (fallback — локальный репо-клон)
TEMPLATE="/tmp/ssh_banner_template.$$"
if ! curl -sf -o "$TEMPLATE" "$REPO_URL/configs/ssh_banner.txt"; then
    if [ -f /root/vpn-panel-sync/configs/ssh_banner.txt ]; then
        cp /root/vpn-panel-sync/configs/ssh_banner.txt "$TEMPLATE"
    fi
fi

# Включение Banner в sshd_config отключено (теперь показываем через PAM)
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

# Читаем основной бот (username через getMe)
MAIN_BOT="bot"
if [ -f "$BOT_CONF" ]; then
    _tok=$(grep -E '^BOT_TOKEN=' "$BOT_CONF" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')
    if [ -n "$_tok" ]; then
        _resp=$(curl -sf --max-time 10 "https://api.telegram.org/bot${_tok}/getMe" 2>/dev/null)
        if [ -n "$_resp" ]; then
            _u=$(echo "$_resp" | grep -oP '"username"\s*:\s*"\K[^"]+' | head -1)
            [ -n "$_u" ] && MAIN_BOT="$_u"
        fi
    fi
fi
# Обновляем из шаблона репы (если есть)
if [ -f "$TEMPLATE" ]; then
    # Подставляем {location}, {devices}, {support}, {channel}, {main_bot}
    _new=$(sed -e "s|{location}|$LOCATION|g" -e "s|{devices}|$DEVICES|g" -e "s|{support}|$SUPPORT|g" -e "s|{channel}|$CHANNEL|g" -e "s|{main_bot}|$MAIN_BOT|g" "$TEMPLATE")
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
        cat > "$BANNER_FILE" << BANNER_DEF
<h5><b><a href='https://t.me/${CHANNEL}'>📢 Канал: @${CHANNEL}</a></b></h5>
<h6><font color='#ADFF2F'>📍 Локация: ${LOCATION}</font></h6>

<h6><font color='#FF4444'>❌ DDOS · Взлом · Торренты · Спам</font></h6>
<h6><font color='#FFA500'>📱 ${DEVICES} устр.  ·  🚫 Нарушение = бан</font></h6>

<h6><b><a href='https://t.me/${SUPPORT}'>💬 Поддержка: @${SUPPORT}</a></b></h6>
<h6><b><a href='https://t.me/${MAIN_BOT}'>🤖 Бот: @${MAIN_BOT}</a></b></h6>
BANNER_DEF
        echo -e "\033[0;32m✅  Баннер создан (fallback).\033[0m"
    else
        echo -e "\033[0;32m✅  Баннер уже настроен.\033[0m"
    fi
fi
# Чистим временный файл
[ -f "$TEMPLATE" ] && rm -f "$TEMPLATE" 2>/dev/null || true
