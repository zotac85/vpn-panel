#!/bin/bash
# nodes.sh - управление нодами (мастер)

NODES_DB="/etc/UDPCustom/vpn.db"
SSH_KEY="/root/.ssh/id_ed25519"

_nodes_py() {
    python3 - "$@" << 'PYEOF'
import sqlite3, sys
db = sqlite3.connect('/etc/UDPCustom/vpn.db')
args = sys.argv[1:]
cmd = args[0] if args else 'list'

if cmd == 'list':
    rows = db.execute("SELECT id,name,host,ip,ssh_port,ws_port,is_master,is_active,status FROM nodes ORDER BY id").fetchall()
    for r in rows:
        print('|'.join(str(x) if x is not None else '' for x in r))
elif cmd == 'add':
    name, host, ip, sport, wsport = args[1], args[2], args[3], int(args[4]), int(args[5])
    db.execute("INSERT INTO nodes (name,host,ip,ssh_port,ws_port,ssh_user,is_master,is_active,status) VALUES (?,?,?,?,?,?,0,1,'unknown')",
               (name,host,ip,sport,wsport,'root'))
    db.commit()
    print('OK')
elif cmd == 'del':
    db.execute("DELETE FROM nodes WHERE id=? AND is_master=0", (int(args[1]),))
    db.commit()
    print('OK')
elif cmd == 'set_status':
    db.execute("UPDATE nodes SET status=?, last_check=datetime('now') WHERE id=?", (args[1], int(args[2])))
    db.commit()
elif cmd == 'get':
    r = db.execute("SELECT name,host,ip,ssh_port,ws_port,ssh_user FROM nodes WHERE id=?", (int(args[1]),)).fetchone()
    if r: print('|'.join(str(x) for x in r))
PYEOF
}

_nodes_check() {
    local ip="$1" sport="$2"
    local start=$(date +%s%N)
    if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -p "$sport" root@"$ip" "echo OK" < /dev/null &>/dev/null; then
        local end=$(date +%s%N)
        echo "online:$(( (end - start) / 1000000 ))"
    else
        echo "offline:0"
    fi
}

_nodes_sync_key() {
    local ip="$1" sport="$2"
    if [ ! -f "$SSH_KEY.pub" ]; then
        echo "Нет ключа $SSH_KEY.pub. Сгенерируйте: ssh-keygen -t ed25519"
        return 1
    fi
    echo "Введите пароль root@$ip (один раз):"
    cat "$SSH_KEY.pub" | ssh -o StrictHostKeyChecking=no -p "$sport" root@"$ip" \
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo KEY_ADDED"
}

menu_nodes() {
    while true; do
        clear
        echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
        echo -e "        ${YELLOW}🌍  УПРАВЛЕНИЕ НОДАМИ${NC}"
        echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
        echo ""
        printf "  %-3s %-18s %-18s %-16s %-8s\n" "ID" "Имя" "Домен" "IP" "Статус"
        echo "  ────────────────────────────────────────────────────────────────"
        while IFS='|' read -r id name host ip sport wsport is_master is_active status; do
            [ -z "$id" ] && continue
            local mark="🌍"
            [ "$is_master" = "1" ] && mark="👑"
            local st_color="${NC}"
            case "$status" in
                online) st_color="${GREEN}" ;;
                offline) st_color="${RED}" ;;
                *) st_color="${YELLOW}" ;;
            esac
            printf "  %-3s %-18s %-18s %-16s ${st_color}%-8s${NC} %s\n" "$id" "$name" "$host" "$ip" "$status" "$mark"
        done < <(_nodes_py list)
        echo ""
        echo -e " 1) ➕ Добавить ноду"
        echo -e " 2) 🔍 Проверить все ноды (SSH)"
        echo -e " 3) 🗑️  Удалить ноду"
        echo -e " 4) 🔑 Закинуть SSH-ключ на ноду"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-4]: " n_choice
        case "$n_choice" in
            1) _nodes_add ;;
            2) _nodes_check_all ;;
            3) _nodes_del ;;
            4) _nodes_key ;;
            0) return ;;
        esac
    done
}

_nodes_add() {
    clear
    echo -e "${YELLOW}── Добавление ноды ──${NC}"
    read -p "Имя (например 'Латвия 🇱🇻'): " name
    [ -z "$name" ] && { echo "Отмена"; read -p "Enter..."; return; }
    read -p "Домен (lit.tip-ud.top): " host
    [ -z "$host" ] && { echo "Отмена"; read -p "Enter..."; return; }
    read -p "IP (46.8.70.249): " ip
    [ -z "$ip" ] && { echo "Отмена"; read -p "Enter..."; return; }
    read -p "SSH-порт (Enter=22): " sport
    sport=${sport:-22}
    read -p "WS-порт (Enter=2052): " wsport
    wsport=${wsport:-2052}
    _nodes_py add "$name" "$host" "$ip" "$sport" "$wsport"
    echo -e "${GREEN}✅ Нода добавлена${NC}"
    read -p "Нажмите Enter..."
}

_nodes_del() {
    clear
    echo -e "${YELLOW}── Удаление ноды ──${NC}"
    read -p "Введите ID ноды для удаления: " nid
    [ -z "$nid" ] && return
    _nodes_py del "$nid"
    echo -e "${GREEN}✅ Удалено (мастер удалить нельзя)${NC}"
    read -p "Нажмите Enter..."
}

_nodes_check_all() {
    clear
    echo -e "${YELLOW}── Проверка нод по SSH ──${NC}"
    while IFS='|' read -r id name host ip sport wsport is_master is_active status; do
        [ -z "$id" ] && continue
        [ "$is_master" = "1" ] && { echo "👑 $name — локально"; continue; }
        echo -n "  $name ($ip) — "
        res=$(_nodes_check "$ip" "$sport")
        st=${res%%:*}
        ms=${res##*:}
        if [ "$st" = "online" ]; then
            echo -e "${GREEN}🟢 online (${ms}ms)${NC}"
        else
            echo -e "${RED}🔴 offline${NC}"
        fi
        _nodes_py set_status "$st" "$id"
    done < <(_nodes_py list)
    echo ""
    read -p "Нажмите Enter..."
}

_nodes_key() {
    clear
    echo -e "${YELLOW}── Закинуть SSH-ключ мастера на ноду ──${NC}"
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    echo "Нода: $name ($ip:$sport)"
    _nodes_sync_key "$ip" "$sport"
    read -p "Нажмите Enter..."
}
