#!/bin/bash
# vpn-expiry-check.sh — блокировка юзеров с истёкшим сроком (cron каждую минуту)
TS_DIR="/etc/UDPCustom/expire_ts"
LOG="/var/log/vpn-expiry-check.log"
BLOCKED_CONF="/etc/ssh/sshd_config.d/blocked-users.conf"
BANNER_FILE="/etc/UDPCustom/expired_banner.txt"
NOW=$(date +%s)

[ -d "$TS_DIR" ] || exit 0

# Собираем список заблокированных сейчас
declare -A SHOULD_BLOCK

for ts_file in "$TS_DIR"/*; do
    [ -f "$ts_file" ] || continue
    user=$(basename "$ts_file")
    case "$user" in
        vip*|test*) ;;
        *) continue ;;
    esac
    exp=$(cat "$ts_file" 2>/dev/null)
    [[ "$exp" =~ ^[0-9]+$ ]] || continue
    # Юзера нет в системе — удаляем файл expire_ts
    if ! id -u "$user" &>/dev/null; then
        rm -f "$ts_file"
        continue
    fi
    shell=$(getent passwd "$user" | cut -d: -f7)

    # Проверяем статус пароля (P = active, L = locked)
    pwd_status=$(passwd -S "$user" 2>/dev/null | awk '{print $2}')

    if [ "$NOW" -gt "$exp" ]; then
        # Истёк — должен быть заблокирован
        SHOULD_BLOCK[$user]=1
        if [ "$shell" != "/usr/local/bin/vpn-nologin.sh" ] || [ "$pwd_status" != "L" ]; then
            usermod -L "$user" 2>/dev/null
            usermod -s /usr/local/bin/vpn-nologin.sh "$user" 2>/dev/null
            pkill -KILL -u "$user" 2>/dev/null
            echo "$(date '+%F %T') EXPIRED: $user (shell=$shell pwd=$pwd_status)" >> "$LOG"
        fi
    else
        # Активен — должен быть разблокирован, НО только если не заблокирован по трафику
        if [ "$shell" = "/usr/local/bin/vpn-nologin.sh" ] || [ "$shell" = "/usr/sbin/nologin" ] || [ "$pwd_status" = "L" ]; then
            # Проверяем: не в overlimit-users.conf?
            if grep -q "^Match User $user$" /etc/ssh/sshd_config.d/overlimit-users.conf 2>/dev/null; then
                # Заблокирован по трафику — не трогаем
                :
            else
                usermod -U "$user" 2>/dev/null
                usermod -s /bin/false "$user" 2>/dev/null
                echo "$(date '+%F %T') RESTORED: $user" >> "$LOG"
            fi
        fi
    fi
done

# Обновляем sshd_config.d/blocked-users.conf
# Генерируем баннер с поддержкой и каналом (кликабельные ссылки)
SUPPORT="ArsenSupportBot"
if [ -f /etc/UDPCustom/support.txt ]; then
    _s=$(head -1 /etc/UDPCustom/support.txt 2>/dev/null | tr -d '[:space:]@' | head -c 100)
    [ -n "$_s" ] && SUPPORT="$_s"
fi
CHANNEL="ArsenVipKeys"
if [ -f /etc/UDPCustom/channels.txt ]; then
    _ch=$(grep -v '^#' /etc/UDPCustom/channels.txt 2>/dev/null | head -1 | tr -d '[:space:]@' | head -c 100)
    [ -n "$_ch" ] && CHANNEL="$_ch"
fi
cat > "$BANNER_FILE" << BANEOF
<h5><b><font color='#FF0000'>❌  СРОК ДЕЙСТВИЯ КЛЮЧА ИСТЁК</font></b></h5>
<h5><b><font color='#FFFF00'>💬 Поддержка: <a href='https://t.me/$SUPPORT'>@$SUPPORT</a></font></b></h5>
<h5><b><font color='#00FF00'>📢 Канал: <a href='https://t.me/$CHANNEL'>@$CHANNEL</a></font></b></h5>
BANEOF
chmod 644 "$BANNER_FILE"

NEW_CONF=$(mktemp)
echo "# Автогенерируется vpn-expiry-check.sh" > "$NEW_CONF"
echo "# Юзеры с истёкшим сроком — SSH-туннель запрещён" >> "$NEW_CONF"
for u in "${!SHOULD_BLOCK[@]}"; do
    echo "" >> "$NEW_CONF"
    echo "Match User $u" >> "$NEW_CONF"
    echo "    ForceCommand /usr/local/bin/vpn-nologin.sh" >> "$NEW_CONF"
    echo "    AllowTcpForwarding no" >> "$NEW_CONF"
    echo "    PermitOpen none" >> "$NEW_CONF"
    echo "    Banner $BANNER_FILE" >> "$NEW_CONF"
done

# Применяем если изменилось
if ! diff -q "$NEW_CONF" "$BLOCKED_CONF" >/dev/null 2>&1; then
    mv "$NEW_CONF" "$BLOCKED_CONF"
    chmod 644 "$BLOCKED_CONF"
    if sshd -t 2>/dev/null; then
        systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
        echo "$(date '+%F %T') sshd reloaded (blocked-users.conf changed)" >> "$LOG"
    else
        echo "$(date '+%F %T') ERROR: sshd syntax!" >> "$LOG"
    fi
else
    rm -f "$NEW_CONF"
fi
