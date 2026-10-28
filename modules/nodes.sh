#!/bin/bash
# nodes.sh - управление нодами (мастер)

NODES_DB="/etc/UDPCustom/vpn.db"
SSH_KEY="/root/.ssh/id_ed25519"

_nodes_py() {
    python3 - "$@" << 'PYEOF_INNER'
import sqlite3, sys
db = sqlite3.connect('/etc/UDPCustom/vpn.db')
args = sys.argv[1:]
cmd = args[0] if args else 'list'

if cmd == 'list':
    rows = db.execute("SELECT id,name,host,ip,ssh_port,ws_port,is_master,is_active,status FROM nodes ORDER BY id").fetchall()
    for r in rows:
        print('|'.join(str(x) if x is not None else '' for x in r))
elif cmd == 'add':
    name, host, tls_host, ip, sport, wsport = args[1], args[2], args[3], args[4], int(args[5]), int(args[6])
    if not tls_host: tls_host = host
    existing = db.execute("SELECT id, name FROM nodes WHERE host=? OR ip=?", (host, ip)).fetchone()
    if existing:
        print(f"DUP:{existing[0]}:{existing[1]}")
    else:
        db.execute("INSERT INTO nodes (name,host,tls_host,ip,ssh_port,ws_port,ssh_user,is_master,is_active,status) VALUES (?,?,?,?,?,?,?,0,1,'unknown')",
                   (name,host,tls_host,ip,sport,wsport,'root'))
        db.commit()
        print('OK')
elif cmd == 'update':
    id_, name, host, tls_host, ip, sport, wsport = args[1], args[2], args[3], args[4], args[5], int(args[6]), int(args[7])
    if not tls_host: tls_host = host
    existing = db.execute("SELECT id, name FROM nodes WHERE (host=? OR ip=?) AND id!=?", (host, ip, id_)).fetchone()
    if existing:
        print(f"DUP:{existing[0]}:{existing[1]}")
    else:
        db.execute("UPDATE nodes SET name=?, host=?, tls_host=?, ip=?, ssh_port=?, ws_port=? WHERE id=?",
                   (name, host, tls_host, ip, sport, wsport, id_))
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
elif cmd == 'get_full':
    r = db.execute("SELECT name, host, tls_host, ip, ssh_port, ws_port FROM nodes WHERE id=?", (int(args[1]),)).fetchone()
    if r: print('|'.join(str(x) if x is not None else '' for x in r))
PYEOF_INNER
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
        echo -e "${CYAN}Генерируем SSH-ключ мастера...${NC}"
        mkdir -p /root/.ssh
        chmod 700 /root/.ssh
        ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "vpn-panel-master" >/dev/null 2>&1
        if [ ! -f "$SSH_KEY.pub" ]; then
            echo -e "${RED}Не удалось создать ключ${NC}"
            return 1
        fi
        echo -e "${GREEN}✅ Ключ создан: $SSH_KEY${NC}"
    fi
    echo "Введите пароль root@$ip (один раз):"
    cat "$SSH_KEY.pub" | ssh -o StrictHostKeyChecking=no -p "$sport" root@"$ip" \
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo KEY_ADDED"
}


_nodes_install_ws() {
    clear
    echo -e "${YELLOW}── Установка WS на ноду ──${NC}"
    echo ""
    while IFS='|' read -r id name host ip sport wsport is_master is_active status; do
        [ -z "$id" ] && continue
        [ "$is_master" = "1" ] && continue
        echo "  $id) $name ($ip)"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    
    # Защита от сброса порта в 0 или пустоту
    if [ -z "$wsport" ] || [ "$wsport" = "0" ]; then
        wsport=80
    fi
    echo ""
    echo -e "${CYAN}Устанавливаю WS на $name ($ip)...${NC}"
    echo -e "${YELLOW}Будут использованы порты: WS=$wsport, SSH=$sport${NC}"
    echo ""
    # Копируем свежий скрипт с мастера (обходим кэш GitHub)
    LOCAL_SCRIPT="/usr/local/share/vpn-panel/install-node.sh"
    if [ ! -f "$LOCAL_SCRIPT" ]; then
        LOCAL_SCRIPT="/root/vpn-panel-sync/install-node.sh"
    fi
    if [ ! -f "$LOCAL_SCRIPT" ]; then
        echo -e "${RED}Не найден install-node.sh ни в панели, ни в репо${NC}"
        read -p "Нажмите Enter..."
        return
    fi
    # Автоматически заливаем токен на ноду, если его там нет
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" \
        "[ -f /root/.vpn-panel.token ] || (echo '$(cat /root/.vpn-panel.token 2>/dev/null)' > /root/.vpn-panel.token && chmod 600 /root/.vpn-panel.token && echo '✅ Токен залит на ноду')" 2>/dev/null

    # Автоматически заливаем токен на ноду, если его там нет
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" \
        "[ -f /root/.vpn-panel.token ] || (echo '$(cat /root/.vpn-panel.token 2>/dev/null)' > /root/.vpn-panel.token && chmod 600 /root/.vpn-panel.token && echo '✅ Токен залит на ноду')" 2>/dev/null

    scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" \
        "$LOCAL_SCRIPT" root@"$ip":/tmp/inst.sh >/dev/null 2>&1
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" \
        "printf '%s\n%s\n' '$wsport' '$sport' | bash /tmp/inst.sh"
    echo ""
    read -p "Нажмите Enter..."
}


_nodes_install_banner() {
    clear
    echo -e "${YELLOW}── Установка баннера на ноду ──${NC}"
    echo ""
    while IFS='|' read -r id name host ip sport wsport is_master is_active status; do
        [ -z "$id" ] && continue
        [ "$is_master" = "1" ] && continue
        echo "  $id) $name ($ip)"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    
    # Защита от сброса порта в 0 или пустоту
    if [ -z "$wsport" ] || [ "$wsport" = "0" ]; then
        wsport=80
    fi

    # Генерируем баннер из шаблона мастера, подменяя локацию
    BANNER_SRC="/etc/UDPCustom/ssh_banner.txt"
    [ ! -f "$BANNER_SRC" ] && { echo -e "${RED}Нет /etc/UDPCustom/ssh_banner.txt на мастере${NC}"; read -p "Enter..."; return; }

    # Заменяем "Локация: <старое>" на "Локация: <name>"
    TMP="/tmp/banner_${nid}.txt"
    sed -E "s|(📍 Локация: ).*|\1${name}</font></b></h6>|" "$BANNER_SRC" > "$TMP"

    echo ""
    echo -e "${CYAN}Копирую баннер на $name ($ip)...${NC}"

    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" "mkdir -p /etc/UDPCustom"
    scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" "$TMP" root@"$ip":/etc/UDPCustom/ssh_banner.txt >/dev/null 2>&1
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" "
        chmod 644 /etc/UDPCustom/ssh_banner.txt
        sed -i '/^Banner/d' /etc/ssh/sshd_config 2>/dev/null || true
        rm -f /etc/ssh/sshd_config.d/*banner* 2>/dev/null || true
        systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
        echo 'BANNER SET on '\$(hostname)
    " >/dev/null 2>&1
    rm -f "$TMP"
    echo -e "${GREEN}✅ Баннер установлен на $name${NC}"
    echo ""
    read -p "Нажмите Enter..."
}


_nodes_sync_all_users() {
    clear
    echo -e "${YELLOW}── Синхронизация всех юзеров на ноды ──${NC}"
    echo ""

    TMP_FILE="/tmp/_sync_users.$$"
    python3 - > "$TMP_FILE" << 'PYCODE'
import sqlite3, time
db = sqlite3.connect('/etc/UDPCustom/vpn.db')
now = int(time.time())
for tbl in ['test_keys', 'vip_keys']:
    for login, pwd, dev, exp in db.execute(f"SELECT login, password, devices, expires_at FROM {tbl} WHERE expires_at > ?", (now,)).fetchall():
        if login and pwd:
            print(f"{login}|{pwd}|{dev or 1}|{exp or 0}")
PYCODE

    TOTAL=$(wc -l < "$TMP_FILE")
    if [ "$TOTAL" -eq 0 ]; then
        echo -e "${YELLOW}Нет активных юзеров в БД${NC}"
        rm -f "$TMP_FILE"
        read -p "Нажмите Enter..."
        return
    fi

    echo -e "${CYAN}Активных юзеров в БД: $TOTAL${NC}"
    echo ""

    mapfile -t NODE_LINES < <(_nodes_py list | awk -F'|' '$7=="0"')
    if [ "${#NODE_LINES[@]}" -eq 0 ]; then
        echo -e "${YELLOW}Нет нод (кроме мастера)${NC}"
        rm -f "$TMP_FILE"
        read -p "Нажмите Enter..."
        return
    fi

    echo -e "${CYAN}Ноды для синхронизации:${NC}"
    for line in "${NODE_LINES[@]}"; do
        IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st <<< "$line"
        echo "  • $_name ($_ip)"
    done
    echo ""
    read -p "Начать синхронизацию? (y/n): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        rm -f "$TMP_FILE"
        return
    fi

    echo ""
    for line in "${NODE_LINES[@]}"; do
        IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st <<< "$line"
        echo -e "${CYAN}=== $_name ($_ip) ===${NC}"
        OK=0
        FAIL=0
        while IFS='|' read -r login pwd dev exp; do
            [ -z "$login" ] && continue
            RES=$(timeout 15s ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -p "$_sp" root@"$_ip" "node-user.sh add '$login' '$pwd' '$exp' && node-user.sh setlimit '$login' '$dev'" < /dev/null 2>/dev/null)
            if echo "$RES" | grep -q "OK"; then
                OK=$((OK+1))
            else
                FAIL=$((FAIL+1))
                echo -e "  ${RED}✗ $login: $RES${NC}"
            fi
            sleep 0.3
        done < "$TMP_FILE"
        echo -e "  ${GREEN}✓ Синхронизировано: $OK${NC}   ${RED}✗ Ошибок: $FAIL${NC}"
        echo ""
    done

    rm -f "$TMP_FILE"
    echo -e "${GREEN}✅ Синхронизация завершена${NC}"
    read -p "Нажмите Enter..."
}


_nodes_optimize() {
    clear
    echo -e "${YELLOW}── Оптимизация ноды ──${NC}"
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip)"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    if [ -z "$wsport" ] || [ "$wsport" = "0" ]; then wsport=80; fi

    echo ""
    echo -e "${CYAN}Выберите действие для $name ($ip):${NC}"
    echo -e " 1) ⚡ Полная оптимизация (BBR, UFW, Fail2ban, Буферы)"
    echo -e " 2) 🚦 Установить лимиты скорости (TC)"
    echo -e " 0) Назад"
    read -p "Действие [0-2]: " opt_type

    if [ "$opt_type" = "1" ]; then
        echo -e "${YELLOW}Будет применено:${NC}"
        echo " - Обновление пакетов (apt update + upgrade)"
        echo " - Установка UFW и Fail2ban"
        echo " - Включение TCP BBR (ускорение)"
        echo " - Тюнинг буферов (16MB)"
        echo " - Отключение IPv6 (с сохранением)"
        echo " - Создание Swap 1GB"
        echo " - Установка AdGuard DNS (блокировка рекламы)"
        echo " - Ускорение SSH (DNS/GSSAPI)"
        echo " - Настройка UFW (порты $sport, $wsport)"
        echo ""
        read -p "Продолжить? (y/n): " confirm
        [[ "$confirm" != "y" && "$confirm" != "Y" ]] && return
        echo -e "${CYAN}Применяю (может занять 1-2 минуты)...${NC}"
        REMOTE_CMD="export DEBIAN_FRONTEND=noninteractive; "
        REMOTE_CMD+="echo '--> Обновление пакетов (update & upgrade)...'; "
        REMOTE_CMD+="apt update -y > /dev/null 2>&1 && apt upgrade -y > /dev/null 2>&1 && apt install -y ufw fail2ban > /dev/null 2>&1 || echo 'ОШИБКА УСТАНОВКИ'; "
        REMOTE_CMD+="echo '--> Настройка AdGuard DNS...'; "
        REMOTE_CMD+="systemctl disable systemd-resolved --now > /dev/null 2>&1; "
        REMOTE_CMD+="rm -f /etc/resolv.conf; "
        REMOTE_CMD+="echo -e 'nameserver 94.140.14.14\nnameserver 94.140.15.15' > /etc/resolv.conf; "
        REMOTE_CMD+="chattr +i /etc/resolv.conf; "
        REMOTE_CMD+="echo '--> Включение TCP BBR и тюнинг буферов...'; "
        REMOTE_CMD+="sysctl -w net.core.default_qdisc=fq; "
        REMOTE_CMD+="sysctl -w net.ipv4.tcp_congestion_control=bbr; "
        REMOTE_CMD+="sysctl -w net.core.rmem_max=16777216; "
        REMOTE_CMD+="sysctl -w net.core.wmem_max=16777216; "
        REMOTE_CMD+="touch /etc/sysctl.conf; grep -q 'net.ipv4.tcp_congestion_control=bbr' /etc/sysctl.conf || echo 'net.ipv4.tcp_congestion_control=bbr' >> /etc/sysctl.conf; "
        REMOTE_CMD+="grep -q 'net.core.default_qdisc=fq' /etc/sysctl.conf || echo 'net.core.default_qdisc=fq' >> /etc/sysctl.conf; "
        REMOTE_CMD+="echo '--> Отключение IPv6...'; "
        REMOTE_CMD+="sysctl -w net.ipv6.conf.all.disable_ipv6=1 > /dev/null 2>&1; "
        REMOTE_CMD+="grep -q 'net.ipv6.conf.all.disable_ipv6=1' /etc/sysctl.conf || echo 'net.ipv6.conf.all.disable_ipv6=1' >> /etc/sysctl.conf; "
        REMOTE_CMD+="echo '--> Создание Swap 1GB...'; "
        REMOTE_CMD+="fallocate -l 1G /swapfile 2>/dev/null; chmod 600 /swapfile; mkswap /swapfile > /dev/null 2>&1; swapon /swapfile 2>/dev/null; "
        REMOTE_CMD+="grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab; "
        REMOTE_CMD+="echo '--> Настройка UFW...'; "
        REMOTE_CMD+="ufw --force reset > /dev/null 2>&1; "
        REMOTE_CMD+="ufw default deny incoming > /dev/null 2>&1; "
        REMOTE_CMD+="ufw default allow outgoing > /dev/null 2>&1; "
        REMOTE_CMD+="ufw allow $sport/tcp > /dev/null 2>&1; "
        REMOTE_CMD+="ufw allow $wsport/tcp > /dev/null 2>&1; "
        REMOTE_CMD+="ufw --force enable > /dev/null 2>&1; "
        REMOTE_CMD+="echo '--> Настройка Fail2ban...'; "
        REMOTE_CMD+="systemctl enable fail2ban > /dev/null 2>&1; systemctl restart fail2ban; "
        REMOTE_CMD+="echo '--> Ускорение SSH (DNS/GSSAPI)...'; "
        REMOTE_CMD+="grep -q 'UseDNS no' /etc/ssh/sshd_config || echo 'UseDNS no' >> /etc/ssh/sshd_config; "
        REMOTE_CMD+="grep -q 'GSSAPIAuthentication no' /etc/ssh/sshd_config || echo 'GSSAPIAuthentication no' >> /etc/ssh/sshd_config; "
        REMOTE_CMD+="systemctl restart ssh; "
        REMOTE_CMD+="echo '=== ГОТОВО ==='; "
        ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" "$REMOTE_CMD"
        echo -e "${GREEN}✅  Оптимизация завершена!${NC}"
        
elif [ "$opt_type" = "2" ]; then
        echo ""
        read -p "Введите лимит TCP (SSH/WS) в Мбит/с (0 - снять): " speed_tcp
        read -p "Введите лимит DNS (MasterDnsVPN) в Мбит/с (0 - снять): " speed_dns
        echo ""
        if [[ -n "$speed_tcp" || -n "$speed_dns" ]]; then
            echo -e "${CYAN}Применяю лимиты на ноде...${NC}"
            TC_CMD="IFACE=\$(ip -o -4 route show to default | awk '{print \$5}'); "
            TC_CMD+="tc qdisc del dev \$IFACE root 2>/dev/null; "
            if [[ "$speed_tcp" != "0" || "$speed_dns" != "0" ]]; then
                TC_CMD+="tc qdisc add dev \$IFACE root handle 1: htb default 30; "
                TC_CMD+="tc class add dev \$IFACE parent 1: classid 1:1 htb rate 1000mbit ceil 1000mbit quantum 1500; "
                if [[ "$speed_tcp" != "0" && -n "$speed_tcp" ]]; then
                    TC_CMD+="tc class add dev \$IFACE parent 1:1 classid 1:20 htb rate ${speed_tcp}mbit ceil ${speed_tcp}mbit; "
                    TC_CMD+="tc qdisc replace dev \$IFACE parent 1:20 handle 20: sfq perturb 10; "
                    TC_CMD+="tc filter add dev \$IFACE parent 1: protocol ip prio 2 u32 match ip protocol 6 0xff flowid 1:20; "
                fi
                if [[ "$speed_dns" != "0" && -n "$speed_dns" ]]; then
                    TC_CMD+="tc class add dev \$IFACE parent 1:1 classid 1:10 htb rate ${speed_dns}mbit ceil ${speed_dns}mbit; "
                    TC_CMD+="tc qdisc replace dev \$IFACE parent 1:10 handle 10: sfq perturb 10; "
                    TC_CMD+="tc filter add dev \$IFACE parent 1: protocol ip prio 1 u32 match ip dport 53 0xffff flowid 1:10; "
                    TC_CMD+="tc filter add dev \$IFACE parent 1: protocol ip prio 1 u32 match ip protocol 17 0xff match ip dport 53 0xffff flowid 1:10; "
                fi
            fi
            ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" "$TC_CMD"
            echo -e "${GREEN}✅ Лимиты на ноде обновлены!${NC}"
        fi
    fi
    read -p "Нажмите Enter..."
}


_nodes_reboot() {
    clear
    echo -e "${YELLOW}── Перезагрузка ноды ──${NC}"
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip)"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    
    # Защита от сброса порта в 0 или пустоту
    if [ -z "$wsport" ] || [ "$wsport" = "0" ]; then
        wsport=80
    fi

    echo ""
    read -p "Перезагрузить $name ($ip)? (y/n): " c
    [[ "$c" != "y" && "$c" != "Y" ]] && return

    echo ""
    echo -e "${CYAN}Отправляю reboot на $name...${NC}"
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" \
        "nohup reboot >/dev/null 2>&1 &" 2>/dev/null
    echo -e "${GREEN}✅ Команда reboot отправлена${NC}"
    echo "   Нода будет недоступна ~30-60 секунд"
    echo ""
    read -p "Нажмите Enter..."
}




_nodes_change_domain() {
    clear
    echo -e "${YELLOW}── Изменить домен ноды ──${NC}"
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip) — домен: $_host"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    
    # Защита от сброса порта в 0 или пустоту
    if [ -z "$wsport" ] || [ "$wsport" = "0" ]; then
        wsport=80
    fi
    echo ""
    echo -e "  Текущий домен: ${GREEN}$host${NC}"
    read -p "  Новый домен (без http://): " new_domain
    [ -z "$new_domain" ] && return

    # Валидация
    new_domain=$(echo "$new_domain" | sed 's|https\?://||; s|/.*||; s|:.*||' | tr -d ' ')
    if [ -z "$new_domain" ] || [[ "$new_domain" != *.* ]]; then
        echo -e "${RED}Неверный формат. Пример: new.domain.com${NC}"
        read -p "Enter..."
        return
    fi

    # Обновляем в БД мастера
    python3 -c "
import sqlite3
db = sqlite3.connect('/etc/UDPCustom/vpn.db')
db.execute(\"UPDATE nodes SET host='$new_domain' WHERE id=$nid\")
db.commit()
print('OK')
"

    echo ""
    echo -e "${GREEN}✅ Домен ноды обновлён: $new_domain${NC}"
    echo -e "${YELLOW}⚠️  Клиентам нужно пересоздать .dark для этой ноды${NC}"
    echo ""
    read -p "Нажмите Enter..."
}


_nodes_install_udpgw() {
    clear
    echo -e "${YELLOW}── Установка UDPGW на ноду ──${NC}"
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip)"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    
    # Защита от сброса порта в 0 или пустоту
    if [ -z "$wsport" ] || [ "$wsport" = "0" ]; then
        wsport=80
    fi

    echo ""
    echo -e "${CYAN}Устанавливаю UDPGW на $name ($ip)...${NC}"
    echo ""

    scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" \
        /usr/local/share/vpn-panel/install-udpgw-node.sh root@"$ip":/tmp/install-udpgw-node.sh >/dev/null 2>&1
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" \
        "chmod +x /tmp/install-udpgw-node.sh && bash /tmp/install-udpgw-node.sh"

    echo ""
    read -p "Нажмите Enter..."
}


_nodes_install_tls() {
    clear
    echo -e "${YELLOW}── Установка TLS (Nginx + Сертификаты) на ноду ──${NC}"
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip)"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    
    # Для TLS всегда берем домен из колонки tls_host
    TLS_DOMAIN=$(_nodes_py tls_host "$nid" 2>/dev/null)
    [ -z "$TLS_DOMAIN" ] && TLS_DOMAIN="$host"

    echo -e "${CYAN}Настраиваю TLS для $name ($TLS_DOMAIN)...${NC}"
    
    # 1. Создаем папку на ноде
    ssh -o StrictHostKeyChecking=no -o BatchMode=yes -p "$sport" root@"$ip" "mkdir -p /etc/nginx/ssl" 2>/dev/null
    
    # 2. Копируем сертификаты с мастера
    if [ -f /etc/nginx/ssl/ruzone.crt ]; then
        scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" /etc/nginx/ssl/ruzone.crt root@"$ip":/etc/nginx/ssl/ >/dev/null 2>&1
        scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" /etc/nginx/ssl/ruzone.key root@"$ip":/etc/nginx/ssl/ >/dev/null 2>&1
        echo -e "  ✓ Сертификаты скопированы"
    else
        echo -e "  ${RED}⚠️ На мастере нет /etc/nginx/ssl/ruzone.crt${NC}"
    fi
    
    # 3. Копируем и запускаем скрипт установки
    scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" /usr/local/share/vpn-panel/setup-tls-node.sh root@"$ip":/tmp/ >/dev/null 2>&1
    ssh -o StrictHostKeyChecking=no -o BatchMode=yes -p "$sport" root@"$ip" "chmod +x /tmp/setup-tls-node.sh && bash /tmp/setup-tls-node.sh $TLS_DOMAIN"
    
    echo -e "${GREEN}✅  TLS успешно установлен на $name${NC}"
    read -p "Нажмите Enter..."
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
        echo -e " 5) ⚙️  Установить WS на ноду"
        echo -e " 6) 🎨 Установить баннер на ноду"
        echo -e " 7) 🔄 Синхронизировать всех юзеров на ноды"
        echo -e " 8) ⚡ Оптимизировать ноду"
        echo -e " 9) 🔄 Перезагрузить ноду"
        echo -e " 10) 🌐 Изменить домен ноды"
        echo -e " 11) 📡 Установить UDPGW на ноду"
        echo -e " 12) ⚙️  Настройки мастера"
        echo -e " 13) 🔄 Обновить скрипты на нодах"
        echo -e " 14) 🔒 Установить TLS (Nginx) на ноду"
        echo -e " 15) 🚀 ПОДКЛЮЧИТЬ НОВУЮ НОДУ (Полный автомат)"
        echo -e " 16) ✏️  Редактировать ноду"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите действие [0-16]: " n_choice
        case "$n_choice" in
            1) _nodes_add ;;
            2) _nodes_check_all ;;
            3) _nodes_del ;;
            4) _nodes_key ;;
            5) _nodes_install_ws ;;
            6) _nodes_install_banner ;;
            7) _nodes_sync_all_users ;;
            8) _nodes_optimize ;;
            9) _nodes_reboot ;;
            10) _nodes_change_domain ;;
            11) _nodes_install_udpgw ;;
            12) _nodes_master_settings ;;
            13) _nodes_update_scripts ;;
            14) _nodes_install_tls ;;
            15) _nodes_auto_add ;;
            16) _nodes_edit ;;
            0) return ;;
        esac
    done
}

_nodes_update_scripts() {
    clear
    echo -e "${YELLOW}── Обновление скриптов на нодах ──${NC}"
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip)"
    done < <(_nodes_py list)
    echo "  all) Все ноды"
    echo ""
    read -p "Введите ID ноды (или all): " nid
    [ -z "$nid" ] && return

    echo ""
    echo -e "${CYAN}Копирую свежие скрипты...${NC}"
    echo ""

    # Получаем список нод для обновления
    local nodes_to_update=()
    if [ "$nid" = "all" ]; then
        while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
            [ -z "$_id" ] && continue
            [ "$_im" = "1" ] && continue
            nodes_to_update+=("$_id")
        done < <(_nodes_py list)
    else
        nodes_to_update=("$nid")
    fi

    if [ ${#nodes_to_update[@]} -eq 0 ]; then
        echo -e "${RED}Нет нод для обновления${NC}"
        read -p "Enter..."; return
    fi

    # Копируем файлы с мастера
    local src_node_user="/root/vpn-panel-sync/scripts/node-user.sh"
    local src_pam="/root/vpn-panel-sync/scripts/check-device-limit-pam"
    [ ! -f "$src_node_user" ] && { echo -e "${RED}Не найден $src_node_user${NC}"; read -p "Enter..."; return; }
    [ ! -f "$src_pam" ] && { echo -e "${RED}Не найден $src_pam${NC}"; read -p "Enter..."; return; }

    for id in "${nodes_to_update[@]}"; do
        local row=$(_nodes_py get "$id")
        [ -z "$row" ] && { echo -e "${RED}Нода $id не найдена${NC}"; continue; }
        IFS='|' read -r name host ip sport wsport suser <<< "$row"
    
    # Защита от сброса порта в 0 или пустоту
    if [ -z "$wsport" ] || [ "$wsport" = "0" ]; then
        wsport=80
    fi

        echo -e "${CYAN}→ Обновляю $name ($ip)...${NC}"

        # 1. Копируем node-user.sh
        scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" \
            "$src_node_user" root@"$ip":/usr/local/bin/node-user.sh >/dev/null 2>&1 \
            && echo "  ✓ node-user.sh" \
            || { echo -e "  ${RED}✗ node-user.sh${NC}"; continue; }

        # 2. Копируем check-device-limit-pam
        scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" \
            "$src_pam" root@"$ip":/usr/local/bin/check-device-limit-pam >/dev/null 2>&1 \
            && echo "  ✓ check-device-limit-pam" \
            || echo -e "  ${RED}✗ check-device-limit-pam${NC}"

        # 3. Настраиваем на ноде
        ssh -q -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=QUIET -p "$sport" root@"$ip" '
            chmod +x /usr/local/bin/node-user.sh /usr/local/bin/check-device-limit-pam
            mkdir -p /etc/UDPCustom/limits /etc/UDPCustom/expire_ts
            touch /var/log/vpn-device-limit.log
            chmod 666 /var/log/vpn-device-limit.log
            grep -q "ClientAliveInterval 30" /etc/ssh/sshd_config || echo "ClientAliveInterval 30" >> /etc/ssh/sshd_config
            grep -q "ClientAliveCountMax 2" /etc/ssh/sshd_config || echo "ClientAliveCountMax 2" >> /etc/ssh/sshd_config
            systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
            
            if ! grep -q "check-device-limit-pam" /etc/pam.d/sshd 2>/dev/null; then
                cp /etc/pam.d/sshd /etc/pam.d/sshd.bak_$(date +%F_%H%M) 2>/dev/null || true
                sed -i "/^account.*pam_nologin.so/a account    required     pam_exec.so quiet stdout /usr/local/bin/check-device-limit-pam" /etc/pam.d/sshd
            fi
            if sshd -t 2>/dev/null; then
                systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
                echo "  ✓ PAM настроен, sshd перезагружен"
            else
                echo "  ⚠️  ошибка PAM"
            fi
        ' 2>&1 | sed 's/^/  /'

        echo ""
    done

    echo -e "${GREEN}✅ Готово${NC}"
    echo ""
    read -p "Нажмите Enter..."
}
_nodes_master_settings() {
    local CONF="/etc/UDPCustom/bot.conf"
    local DOMAIN_FILE="/etc/vpn-domain"
    while true; do
        clear
        echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
        echo -e "        ${YELLOW}⚙️   НАСТРОЙКИ МАСТЕРА${NC}"
        echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
        echo ""
        local cur_dom=""
        [ -f "$DOMAIN_FILE" ] && cur_dom=$(cat "$DOMAIN_FILE" 2>/dev/null | tr -d '\n')
        local cur_loc=$(grep -E '^SERVER_LOCATION=' "$CONF" 2>/dev/null | head -1 | cut -d'=' -f2- | tr -d '"')
        echo -e " Домен   : ${GREEN}${cur_dom:-не задан}${NC}"
        echo -e " Локация : ${GREEN}${cur_loc:-не задана}${NC}"
        echo ""
        echo -e " 1) 🌐 Изменить домен мастера"
        echo -e " 2) 📍 Изменить локацию мастера"
        echo -e " 3) 🔄 Перезапустить WS на мастере"
        echo ""
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Выберите [0-3]: " mch
        case "$mch" in
            1)
                read -p "Новый домен (Enter — отмена): " nd
                [ -z "$nd" ] && continue
                echo "$nd" > "$DOMAIN_FILE"
                python3 -c "import sqlite3; db=sqlite3.connect('/etc/UDPCustom/vpn.db'); db.execute(\"UPDATE nodes SET host=? WHERE is_master=1\", ('$nd',)); db.commit()" 2>/dev/null
                echo -e "${GREEN}✅  Домен сохранён${NC}"
                sleep 1
                ;;
            2)
                read -p "Новая локация (например 'Германия 🇩🇪', Enter — отмена): " nl
                [ -z "$nl" ] && continue
                if grep -q "^SERVER_LOCATION=" "$CONF" 2>/dev/null; then
                    sed -i "s|^SERVER_LOCATION=.*|SERVER_LOCATION=\"$nl\"|" "$CONF"
                else
                    echo "SERVER_LOCATION=\"$nl\"" >> "$CONF"
                fi
                python3 -c "import sqlite3; db=sqlite3.connect('/etc/UDPCustom/vpn.db'); db.execute(\"UPDATE nodes SET name=? WHERE is_master=1\", ('$nl',)); db.commit()" 2>/dev/null
                systemctl restart vpn-tg-bot 2>/dev/null
                echo -e "${GREEN}✅  Локация сохранена, бот перезапущен${NC}"
                sleep 2
                ;;
            3)
                systemctl restart ws-proxy 2>/dev/null
                sleep 1
                systemctl is-active --quiet ws-proxy && echo -e "${GREEN}✅  WS перезапущен${NC}" || echo -e "${RED}❌  Ошибка${NC}"
                sleep 1
                ;;
            0) return ;;
            *) echo -e "${RED}Неверный выбор${NC}"; sleep 1 ;;
        esac
    done
}
_nodes_auto_add() {
    clear
    echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
    echo -e "        ${YELLOW}🚀  ПОЛНАЯ АВТОУСТАНОВКА НОВОЙ НОДЫ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
    echo ""
    while true; do
        read -p "Имя (например 'Германия 🇩🇪', 0 - отмена): " name
        [ "$name" = "0" ] && { echo "Отмена"; return; }
        if [ -z "$name" ]; then echo -e "${RED}❌ Имя не может быть пустым!${NC}"; else break; fi
    done
    # Убираем пробелы в имени, чтобы не сломать базу
    name=$(echo "$name" | tr ' ' '_')
    
    while true; do
        read -p "WS-Домен (напр. lv.cdnstore.shop, 0 - отмена): " host
        [ "$host" = "0" ] && { echo "Отмена"; return; }
        if [ -z "$host" ]; then echo -e "${RED}❌ WS-Домен не может быть пустым!${NC}"; else break; fi
    done

    while true; do
        read -p "TLS-Домен (напр. lv.ruzone27.shop, Enter = как WS): " tls_host
        [ -z "$tls_host" ] && tls_host="$host"
        break
    done
    
    while true; do
        read -p "IP адрес сервера (0 - отмена): " ip
        [ "$ip" = "0" ] && { echo "Отмена"; return; }
        if [ -z "$ip" ]; then echo -e "${RED}❌ IP не может быть пустым!${NC}"; else break; fi
    done
    
    read -p "SSH-порт (Enter=22): " sport
    sport=${sport:-22}
    
    read -p "WS-порт (Enter=80): " wsport
    wsport=${wsport:-80}

    echo ""
    echo -e "${YELLOW}── ПРОВЕРЬТЕ ДАННЫЕ ──${NC}"
    echo -e " Имя       : ${GREEN}$name${NC}"
    echo -e " WS-Домен  : ${GREEN}$host${NC}"
    echo -e " TLS-Домен : ${GREEN}$tls_host${NC}"
    echo -e " IP        : ${GREEN}$ip${NC}"
    echo -e " SSH порт  : ${GREEN}$sport${NC}"
    echo -e " WS порт   : ${GREEN}$wsport${NC}"
    echo ""
    read -p "Всё верно? Начинаем установку? (y/n): " confirm
    [[ "$confirm" != "y" && "$confirm" != "Y" ]] && return

    echo ""
    echo -e "${CYAN}[1/5] 📝 Добавляем ноду в базу данных...${NC}"
    res=$(_nodes_py add "$name" "$host" "$tls_host" "$ip" "$sport" "$wsport")
    if [[ "$res" == DUP:* ]]; then
        IFS=':' read -r _ dup_id dup_name <<< "$res"
        echo -e "${RED}❌ Ошибка: нода с таким доменом или IP уже есть! (ID: $dup_id, Имя: $dup_name)${NC}"
        read -p "Нажмите Enter..."
        return
    fi
    sleep 1

    echo -e "${CYAN}[2/5] 🔑 Копируем SSH-ключ (введите пароль от сервера, если попросит)...${NC}"
    _nodes_sync_key "$ip" "$sport"
    
    echo -e "${CYAN}[3/5] ⚙️  Устанавливаем WS-прокси на ноду...${NC}"
    LOCAL_SCRIPT="/usr/local/share/vpn-panel/install-node.sh"
    [ ! -f "$LOCAL_SCRIPT" ] && LOCAL_SCRIPT="/root/vpn-panel-sync/install-node.sh"
    
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" \
        "[ -f /root/.vpn-panel.token ] || (echo '$(cat /root/.vpn-panel.token 2>/dev/null)' > /root/.vpn-panel.token && chmod 600 /root/.vpn-panel.token)" 2>/dev/null
    scp -o StrictHostKeyChecking=no -o BatchMode=yes -P "$sport" "$LOCAL_SCRIPT" root@"$ip":/tmp/inst.sh >/dev/null 2>&1
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$sport" root@"$ip" "printf '%s\n%s\n' '$wsport' '$sport' | bash /tmp/inst.sh" 2>&1 | grep -E "✅|❌|Готово|Ошибка" || true

    echo -e "${CYAN}[4/5] 🔒 Устанавливаем Nginx и TLS...${NC}"
    ssh -o StrictHostKeyChecking=no -p "$sport" root@"$ip" "mkdir -p /etc/nginx/ssl" 2>/dev/null
    scp -o StrictHostKeyChecking=no -P "$sport" /etc/nginx/ssl/ruzone.crt root@"$ip":/etc/nginx/ssl/ >/dev/null 2>&1
    scp -o StrictHostKeyChecking=no -P "$sport" /etc/nginx/ssl/ruzone.key root@"$ip":/etc/nginx/ssl/ >/dev/null 2>&1
    scp -o StrictHostKeyChecking=no -P "$sport" /usr/local/share/vpn-panel/setup-tls-node.sh root@"$ip":/tmp/ >/dev/null 2>&1
    ssh -o StrictHostKeyChecking=no -p "$sport" root@"$ip" "bash /tmp/setup-tls-node.sh $tls_host" 2>&1 | grep -E "successful|✅|error" || true

    echo -e "${CYAN}[5/5] 🔄 Синхронизируем пользователей на новую ноду...${NC}"
    TMP_FILE="/tmp/_auto_sync.$$"
    python3 - > "$TMP_FILE" << 'PYCODE'
import sqlite3, time
db = sqlite3.connect('/etc/UDPCustom/vpn.db')
now = int(time.time())
for tbl in ['test_keys', 'vip_keys']:
    for login, pwd, dev, exp in db.execute(f"SELECT login, password, devices, expires_at FROM {tbl} WHERE expires_at > ?", (now,)).fetchall():
        if login and pwd: print(f"{login}|{pwd}|{dev or 1}|{exp or 0}")
PYCODE
    OK=0; FAIL=0
    while IFS='|' read -r login pwd dev exp; do
        [ -z "$login" ] && continue
        RES=$(timeout 15s ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p "$sport" root@"$ip" "node-user.sh add '$login' '$pwd' '$exp' && node-user.sh setlimit '$login' '$dev'" < /dev/null 2>/dev/null)
        if echo "$RES" | grep -q "OK"; then OK=$((OK+1)); else FAIL=$((FAIL+1)); fi
        sleep 0.2
    done < "$TMP_FILE"
    rm -f "$TMP_FILE"
    echo -e "      ${GREEN}✓ Синхронизировано: $OK${NC}   ${RED}✗ Ошибок: $FAIL${NC}"

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  ✅  НОДА $name УСПЕШНО ДОБАВЛЕНА И НАСТРОЕНА!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}  Не забудьте добавить А-записи в Cloudflare:${NC}"
    echo -e "  WS:  ${GREEN}$host${NC} -> $ip (Оранжевая тучка)"
    echo -e "  TLS: ${GREEN}$tls_host${NC} -> $ip (Оранжевая тучка)"
    echo ""
    read -p "Нажмите Enter для выхода..."
}
_nodes_edit() {
    clear
    echo -e "${YELLOW}── Редактирование ноды ──${NC}"
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip)"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get_full "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r cur_name cur_host cur_tls cur_ip cur_sport cur_wsport <<< "$row"
    echo ""
    echo -e "${CYAN}Текущие данные:${NC}"
    echo -e "  Имя       : ${GREEN}$cur_name${NC}"
    echo -e "  WS-домен  : ${GREEN}$cur_host${NC}"
    echo -e "  TLS-домен : ${GREEN}$cur_tls${NC}"
    echo -e "  IP        : ${GREEN}$cur_ip${NC}"
    echo -e "  SSH порт  : ${GREEN}$cur_sport${NC}"
    echo -e "  WS порт   : ${GREEN}$cur_wsport${NC}"
    echo ""
    echo -e "${YELLOW}Enter = оставить текущее значение.${NC}"
    read -p "Имя [$cur_name]: " name; name=${name:-$cur_name}
    read -p "WS-домен [$cur_host]: " host; host=${host:-$cur_host}
    read -p "TLS-домен [$cur_tls]: " tls_host; tls_host=${tls_host:-$cur_tls}
    read -p "IP [$cur_ip]: " ip; ip=${ip:-$cur_ip}
    read -p "SSH-порт [$cur_sport]: " sport; sport=${sport:-$cur_sport}
    read -p "WS-порт [$cur_wsport]: " wsport; wsport=${wsport:-$cur_wsport}
    result=$(_nodes_py update "$nid" "$name" "$host" "$tls_host" "$ip" "$sport" "$wsport")
    if [[ "$result" == DUP:* ]]; then
        IFS=':' read -r _ dup_id dup_name <<< "$result"
        echo ""
        echo -e "${RED}❌ Конфликт: домен или IP уже занят!${NC}"
        echo -e "${RED}   ID: $dup_id, Имя: $dup_name${NC}"
    elif [ "$result" = "OK" ]; then
        echo ""
        echo -e "${GREEN}✅  Нода обновлена!${NC}"
    else
        echo ""
        echo -e "${RED}❌ Ошибка: $result${NC}"
    fi
    read -p "Нажмите Enter..."
}
_nodes_add() {
    clear
    echo -e "${YELLOW}── Добавление ноды ──${NC}"
    read -p "Имя (например 'Латвия 🇱🇻'): " name
    [ -z "$name" ] && { echo "Отмена"; read -p "Enter..."; return; }
    read -p "WS-Домен (для 80 порта, напр. lv.cdnstore.shop): " host
    [ -z "$host" ] && { echo "Отмена"; read -p "Enter..."; return; }
    read -p "TLS-Домен (для 443 порта, напр. lv.ruzone27.shop): " tls_host
    [ -z "$tls_host" ] && tls_host="$host"
    read -p "IP (46.8.70.249): " ip
    [ -z "$ip" ] && { echo "Отмена"; read -p "Enter..."; return; }
    read -p "SSH-порт (Enter=22): " sport
    sport=${sport:-22}
    read -p "WS-порт (Enter=80): " wsport
    wsport=${wsport:-80}
    result=$(_nodes_py add "$name" "$host" "$tls_host" "$ip" "$sport" "$wsport")
    if [[ "$result" == DUP:* ]]; then
        IFS=':' read -r _ dup_id dup_name <<< "$result"
        echo ""
        echo -e "${RED}❌ Ошибка: нода с таким доменом или IP уже есть!${NC}"
        echo -e "${RED}   ID: $dup_id, Имя: $dup_name${NC}"
        echo -e "${YELLOW}   Удалите (п.3) или отредактируйте (п.16).${NC}"
    else
        echo -e "${GREEN}✅  Нода добавлена${NC}"
    fi
    read -p "Нажмите Enter..."
}
_nodes_del() {
    clear
    echo -e "${YELLOW}── Удаление ноды ──${NC}"
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip) [$_st]"
    done < <(_nodes_py list)
    echo ""
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
    echo ""
    while IFS='|' read -r _id _name _host _ip _sp _wp _im _ia _st; do
        [ -z "$_id" ] && continue
        [ "$_im" = "1" ] && continue
        echo "  $_id) $_name ($_ip)"
    done < <(_nodes_py list)
    echo ""
    read -p "Введите ID ноды: " nid
    [ -z "$nid" ] && return
    row=$(_nodes_py get "$nid")
    [ -z "$row" ] && { echo "Нода не найдена"; read -p "Enter..."; return; }
    IFS='|' read -r name host ip sport wsport suser <<< "$row"
    
    # Защита от сброса порта в 0 или пустоту
    if [ -z "$wsport" ] || [ "$wsport" = "0" ]; then
        wsport=80
    fi
    echo "Нода: $name ($ip:$sport)"
    _nodes_sync_key "$ip" "$sport"
    read -p "Нажмите Enter..."
}
