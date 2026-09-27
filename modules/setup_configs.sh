#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Создание конфигов бота: welcome.txt, start.txt, channels.txt, post.txt
# Вызывается из install.sh
# Аргумент $1: REPO_URL (raw github url)
# ──────────────────────────────────────────────────────────────

REPO_URL="${1:-https://raw.githubusercontent.com/zotac85/vpn-panel/main}"

# welcome.txt
if [ ! -f /etc/UDPCustom/welcome.txt ] || ! grep -q "channels_list" /etc/UDPCustom/welcome.txt 2>/dev/null; then
    [ -f /etc/UDPCustom/welcome.txt ] && cp /etc/UDPCustom/welcome.txt /etc/UDPCustom/welcome.txt.bak
    curl -sf -o /etc/UDPCustom/welcome.txt "$REPO_URL/configs/welcome.txt"
fi

# start.txt
if [ ! -f /etc/UDPCustom/start.txt ] || ! grep -q "sponsors_list" /etc/UDPCustom/start.txt 2>/dev/null; then
    [ -f /etc/UDPCustom/start.txt ] && cp /etc/UDPCustom/start.txt /etc/UDPCustom/start.txt.bak
    curl -sf -o /etc/UDPCustom/start.txt "$REPO_URL/configs/start.txt"
fi

# test_ready.txt — текст "тестовый ключ доступен"
if [ ! -f /etc/UDPCustom/test_ready.txt ] || ! grep -q "{hours}" /etc/UDPCustom/test_ready.txt 2>/dev/null; then
    [ -f /etc/UDPCustom/test_ready.txt ] && cp /etc/UDPCustom/test_ready.txt /etc/UDPCustom/test_ready.txt.bak
    curl -sf -o /etc/UDPCustom/test_ready.txt "$REPO_URL/configs/test_ready.txt"
fi

# test_issued.txt — текст "тестовый доступ готов"
if [ ! -f /etc/UDPCustom/test_issued.txt ] || ! grep -q "{username}" /etc/UDPCustom/test_issued.txt 2>/dev/null; then
    [ -f /etc/UDPCustom/test_issued.txt ] && cp /etc/UDPCustom/test_issued.txt /etc/UDPCustom/test_issued.txt.bak
    curl -sf -o /etc/UDPCustom/test_issued.txt "$REPO_URL/configs/test_issued.txt"
fi

# help.txt — главный экран /help
if [ ! -f /etc/UDPCustom/help.txt ] || ! grep -q "{primary}" /etc/UDPCustom/help.txt 2>/dev/null; then
    [ -f /etc/UDPCustom/help.txt ] && cp /etc/UDPCustom/help.txt /etc/UDPCustom/help.txt.bak
    curl -sf -o /etc/UDPCustom/help.txt "$REPO_URL/configs/help.txt"
fi

# help_instruction.txt — инструкция подключения
if [ ! -f /etc/UDPCustom/help_instruction.txt ]; then
    curl -sf -o /etc/UDPCustom/help_instruction.txt "$REPO_URL/configs/help_instruction.txt"
fi

# help_faq.txt — FAQ
if [ ! -f /etc/UDPCustom/help_faq.txt ]; then
    curl -sf -o /etc/UDPCustom/help_faq.txt "$REPO_URL/configs/help_faq.txt"
fi

# vip_buy.txt — экран "Купить VIP"
if [ ! -f /etc/UDPCustom/vip_buy.txt ] || ! grep -q "{tariffs}" /etc/UDPCustom/vip_buy.txt 2>/dev/null; then
    [ -f /etc/UDPCustom/vip_buy.txt ] && cp /etc/UDPCustom/vip_buy.txt /etc/UDPCustom/vip_buy.txt.bak
    curl -sf -o /etc/UDPCustom/vip_buy.txt "$REPO_URL/configs/vip_buy.txt"
fi

# channels.txt
if [ ! -f /etc/UDPCustom/channels.txt ] || [ ! -s /etc/UDPCustom/channels.txt ]; then
    [ -f /etc/UDPCustom/channels.txt ] && cp /etc/UDPCustom/channels.txt /etc/UDPCustom/channels.txt.bak
    curl -sf -o /etc/UDPCustom/channels.txt "$REPO_URL/configs/channels.txt"
fi

# post.txt
if [ ! -f /etc/UDPCustom/post.txt ] || ! grep -q "DarkTunnel" /etc/UDPCustom/post.txt 2>/dev/null; then
    [ -f /etc/UDPCustom/post.txt ] && cp /etc/UDPCustom/post.txt /etc/UDPCustom/post.txt.bak
    curl -sf -o /etc/UDPCustom/post.txt "$REPO_URL/configs/post.txt"
fi

# rate.txt — курс USDT → манат (для ручного пополнения TMCELL)
if [ ! -f /etc/UDPCustom/rate.txt ]; then
    echo "20" > /etc/UDPCustom/rate.txt
fi

# support.txt — контакт поддержки
if [ ! -f /etc/UDPCustom/support.txt ]; then
    echo "@ArsenGuro" > /etc/UDPCustom/support.txt
fi

echo -e "\033[0;32m✅  Конфиги бота настроены\033[0m"
