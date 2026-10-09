#!/bin/bash
# node-user.sh - управление SSH-юзерами и учёт трафика
# Работает на мастере и нодах

set -e
LOG="/var/log/node-user.log"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG" 2>/dev/null; }

[ "$(id -u)" -eq 0 ] || { echo "ERROR: запускать от root"; exit 1; }

is_our_user() { [[ "$1" == vip_* || "$1" == test_* ]]; }

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
    local user="$1" pass="$2"
    is_our_user "$user" || { echo "ERROR: имя должно начинаться с vip_ или test_"; exit 1; }
    [ -n "$pass" ] || { echo "ERROR: пустой пароль"; exit 1; }
    if id -u "$user" &>/dev/null; then
        echo "$user:$pass" | chpasswd
        echo "OK: пароль обновлён"
    else
        useradd -M -s /usr/sbin/nologin "$user" 2>/dev/null || \
            useradd -M -s /sbin/nologin "$user" 2>/dev/null || \
            useradd -M "$user"
        echo "$user:$pass" | chpasswd
        echo "OK: создан"
    fi
    local uid
    uid=$(get_uid "$user")
    ensure_iptables "$user" "$uid"
    log "ADD $user uid=$uid"
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

cmd_list() {
    grep -E '^(vip_|test_)' /etc/passwd | cut -d: -f1
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
    list)               cmd_list ;;
    traffic)            shift; cmd_traffic "$@" ;;
    traffic-all)        cmd_traffic_all ;;
    reset-traffic)      shift; cmd_reset_traffic "$@" ;;
    reset-traffic-all)  cmd_reset_traffic_all ;;
    *)
        echo "Usage: $0 {add|del|passwd|list|traffic|traffic-all|reset-traffic|reset-traffic-all} ..."
        exit 1
        ;;
esac
exit 0
