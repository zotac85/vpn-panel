#!/bin/bash
# node-user.sh - управление SSH-юзерами и учёт трафика
# Работает на мастере и нодах

set -e
LOG="/var/log/node-user.log"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG" 2>/dev/null; }

[ "$(id -u)" -eq 0 ] || { echo "ERROR: запускать от root"; exit 1; }

is_our_user() { [[ "$1" == vip* || "$1" == test* ]]; }

get_uid() { id -u "$1" 2>/dev/null; }

chain_name() { echo "VPN_OUT_$1"; }

ensure_iptables() {
    local u="$1" uid="$2" chain
    chain=$(chain_name "$u")
    if ! iptables -L "$chain" -n &>/dev/null; then
        iptables -N "$chain"
        iptables -A "$chain" -j RETURN
    fi
    iptables -C OUTPUT -m owner --uid-owner "$uid" -j "$chain" 2>/dev/null || \
        iptables -I OUTPUT -m owner --uid-owner "$uid" -j "$chain"
}

remove_iptables() {
    local u="$1" uid="$2" chain
    chain=$(chain_name "$u")
    while iptables -D OUTPUT -m owner --uid-owner "$uid" -j "$chain" 2>/dev/null; do :; done
    iptables -F "$chain" 2>/dev/null || true
    iptables -X "$chain" 2>/dev/null || true
}

get_traffic() {
    local u="$1" chain
    chain=$(chain_name "$u")
    if iptables -L "$chain" -n &>/dev/null; then
        iptables -L "$chain" -v -x -n | awk '$1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ {sum += $2} END {print sum+0}'
    else
        echo 0
    fi
}

reset_traffic() {
    local u="$1" chain
    chain=$(chain_name "$u")
    iptables -Z "$chain" 2>/dev/null || true
}

cmd_add() {
    local user="$1" pass="$2" exp_ts="${3:-}"
    is_our_user "$user" || { echo "ERROR: имя должно начинаться с vip_ или test_"; exit 1; }
    [ -n "$pass" ] || { echo "ERROR: пустой пароль"; exit 1; }
    if id -u "$user" &>/dev/null; then
        echo "$user:$pass" | chpasswd
        usermod -s /bin/false "$user" 2>/dev/null || true
        echo "OK: пароль обновлён"
    else
        useradd -M -s /bin/false "$user"
        echo "$user:$pass" | chpasswd
        usermod -s /bin/false "$user" 2>/dev/null || true
        echo "OK: создан"
    fi
    local uid
    uid=$(get_uid "$user")
    ensure_iptables "$user" "$uid"
    # Save expiration timestamp if provided
    if [ -n "$exp_ts" ] && [[ "$exp_ts" =~ ^[0-9]+$ ]]; then
        mkdir -p /etc/UDPCustom/expire_ts
        echo "$exp_ts" > "/etc/UDPCustom/expire_ts/$user"
    fi
    # Инициализируем лимит устройств по умолчанию (если нет)
    mkdir -p /etc/UDPCustom/limits
    [ -f "/etc/UDPCustom/limits/$user" ] || echo "3" > "/etc/UDPCustom/limits/$user"
    log "ADD $user uid=$uid exp=$exp_ts"
}

cmd_setlimit() {
    local user="$1" limit="$2"
    is_our_user "$user" || { echo "ERROR: не наш юзер"; exit 1; }
    [[ "$limit" =~ ^[0-9]+$ ]] || { echo "ERROR: лимит должен быть числом"; exit 1; }
    mkdir -p /etc/UDPCustom/limits
    echo "$limit" > "/etc/UDPCustom/limits/$user"
    # Также обновляем limits.conf
    sed -i "/^${user}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null || true
    if [ "$limit" -gt 0 ]; then
        echo "${user} hard maxlogins ${limit}" >> /etc/security/limits.conf
    fi
    log "SETLIMIT $user = $limit"
    echo "OK: limit $user = $limit"
}

cmd_del() {
    local user="$1"
    is_our_user "$user" || { echo "ERROR: не наш юзер"; exit 1; }
    if id -u "$user" &>/dev/null; then
        local uid
        uid=$(get_uid "$user")
        pkill -KILL -u "$user" 2>/dev/null || true
        remove_iptables "$user" "$uid"
        userdel "$user" 2>/dev/null || true
        echo "OK: удалён"
        log "DEL $user"
    else
        echo "OK: не существует"
    fi
}

cmd_passwd() {
    local user="$1" pass="$2"
    id -u "$user" &>/dev/null || { echo "ERROR: юзер не найден"; exit 1; }
    [ -n "$pass" ] || { echo "ERROR: пустой пароль"; exit 1; }
    echo "$user:$pass" | chpasswd
    echo "OK: пароль изменён"
    log "PASSWD $user"
}

cmd_lock() {
    local user="$1"
    id -u "$user" &>/dev/null || { echo "ERROR: юзер не найден"; exit 1; }
    usermod -L "$user" 2>/dev/null
    usermod -s /usr/local/bin/vpn-nologin.sh "$user" 2>/dev/null
    pkill -KILL -u "$user" 2>/dev/null || true
    # Добавляем Match User в overlimit-users.conf
    local conf="/etc/ssh/sshd_config.d/overlimit-users.conf"
    mkdir -p /etc/ssh/sshd_config.d
    if ! grep -q "^Match User $user$" "$conf" 2>/dev/null; then
        {
            echo ""
            echo "Match User $user"
            echo "    ForceCommand /usr/local/bin/vpn-nologin.sh"
            echo "    AllowTcpForwarding no"
            echo "    PermitOpen none"
            echo "    Banner /etc/UDPCustom/overlimit_banner.txt"
        } >> "$conf"
        if sshd -t 2>/dev/null; then
            systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
        fi
    fi
    echo "OK: заблокирован"
}

cmd_unlock() {
    local user="$1"
    id -u "$user" &>/dev/null || { echo "ERROR: юзер не найден"; exit 1; }
    usermod -U "$user" 2>/dev/null
    usermod -s /bin/false "$user" 2>/dev/null
    # Убираем Match User из overlimit-users.conf
    local conf="/etc/ssh/sshd_config.d/overlimit-users.conf"
    if [ -f "$conf" ]; then
        # Удаляем блок: Match User <user> и следующие 4 строки
        python3 - "$user" << 'PYEOF2'
import sys, re
user = sys.argv[1]
with open('/etc/ssh/sshd_config.d/overlimit-users.conf') as f:
    content = f.read()
pattern = re.compile(r'\nMatch User ' + re.escape(user) + r'\n(?:    [^\n]*\n)+')
new = pattern.sub('\n', content)
with open('/etc/ssh/sshd_config.d/overlimit-users.conf', 'w') as f:
    f.write(new)
PYEOF2
        if sshd -t 2>/dev/null; then
            systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
        fi
    fi
    echo "OK: разблокирован"
}

cmd_list() {
    grep -E '^(vip_|test)' /etc/passwd | cut -d: -f1
}

cmd_traffic() {
    local user="$1"
    id -u "$user" &>/dev/null || { echo 0; exit 0; }
    get_traffic "$user"
}

cmd_traffic_all() {
    local first=1
    echo "{"
    while read -r name; do
        [ -z "$name" ] && continue
        local bytes
        bytes=$(get_traffic "$name")
        [ -z "$bytes" ] && bytes=0
        [ $first -eq 1 ] || echo ","
        printf '  "%s": %s' "$name" "$bytes"
        first=0
    done < <(cmd_list)
    echo ""
    echo "}"
}

cmd_reset_traffic() {
    local user="$1"
    id -u "$user" &>/dev/null || { echo "ERROR: юзер не найден"; exit 1; }
    reset_traffic "$user"
    echo "OK: счётчик сброшен"
}

cmd_reset_traffic_all() {
    while read -r name; do
        [ -z "$name" ] && continue
        reset_traffic "$name"
    done < <(cmd_list)
    echo "OK: все счётчики сброшены"
}

case "$1" in
    add)                shift; cmd_add "$@" ;;
    del)                shift; cmd_del "$@" ;;
    passwd)             shift; cmd_passwd "$@" ;;
    setlimit)           shift; cmd_setlimit "$@" ;;
    list)               cmd_list ;;
    traffic)            shift; cmd_traffic "$@" ;;
    traffic-all)        cmd_traffic_all ;;
    lock)               shift; cmd_lock "$@" ;;
    unlock)             shift; cmd_unlock "$@" ;;
    reset-traffic)      shift; cmd_reset_traffic "$@" ;;
    reset-traffic-all)  cmd_reset_traffic_all ;;
    *)
        echo "Usage: $0 {add|del|passwd|lock|unlock|list|traffic|traffic-all|reset-traffic|reset-traffic-all} ..."
        exit 1
        ;;
esac
exit 0
