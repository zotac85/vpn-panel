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

echo -e "\033[0;32m✅  Конфиги бота настроены\033[0m"
