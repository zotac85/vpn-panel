#!/bin/bash
# masterdns.sh — управление MasterDnsVPN (мастер + ноды)

menu_masterdns() {
    while true; do
        clear
        header
        echo -e "${YELLOW}🌐 УПРАВЛЕНИЕ MASTERDNSVPN${NC}"
        echo -e " Статус мастера : $(get_service_status masterdnsvpn)"
        echo ""
        echo -e "${CYAN}─── Выбери сервер ───${NC}"
        echo ""
        echo -e " 1) 🖥️  МАСТЕР (локально)"
        echo ""

        declare -A NODES
        local idx=2
        local _node_list
        _node_list=$(python3 -c "
import sqlite3
for r in sqlite3.connect('/etc/UDPCustom/vpn.db').execute('SELECT id,name,ip,ssh_port FROM nodes WHERE is_active=1 AND is_master=0 ORDER BY id').fetchall():
    print(f'{r[0]}|{r[1]}|{r[2]}|{r[3]}')
")
        while IFS='|' read -r nid nname nip nsport; do
            [ -z "$nid" ] && continue
            local st
            st=$(ssh -o BatchMode=yes -o ConnectTimeout=3 -p "$nsport" root@"$nip" "systemctl is-active masterdnsvpn 2>/dev/null" < /dev/null 2>/dev/null)
            [ -z "$st" ] && st="недоступна"
            echo -e " $idx) 🌍 $nname ($nip) [$st]"
            NODES[$idx]="$nid|$nname|$nip|$nsport"
            idx=$((idx + 1))
        done <<< "$_node_list"

        echo ""
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите сервер [0-$((idx-1))]: " srv_choice
        [ "$srv_choice" = "0" ] && break

        if [ "$srv_choice" = "1" ]; then
            _mds_actions "МАСТЕР (локально)" "" "" 1
        elif [ -n "${NODES[$srv_choice]}" ]; then
            IFS='|' read -r nid nname nip nsport <<< "${NODES[$srv_choice]}"
            _mds_actions "$nname" "$nip" "$nsport" 0
        fi
    done
}

_mds_actions() {
    local target_name="$1" target_ip="$2" target_port="$3" is_master="$4"

    while true; do
        clear
        header
        echo -e "${YELLOW}🌐 MASTERDNSVPN — $target_name${NC}"
        if [ "$is_master" = "1" ]; then
            echo -e " Статус: $(get_service_status masterdnsvpn)"
        else
            local st=$(ssh -o BatchMode=yes -o ConnectTimeout=5 -p "$target_port" root@"$target_ip" "systemctl is-active masterdnsvpn 2>/dev/null" 2>/dev/null)
            [ -z "$st" ] && st="неизвестно"
            echo -e " Статус: $st"
        fi
        echo ""
        echo -e " 1) ⚡  Установить / Обновить"
        echo -e " 2) 🔄 Перезапустить"
        echo -e " 3) 🛑 Остановить"
        echo -e " 4) ⚙️  Редактировать конфиг"
        echo -e " 5) 🗑️  Удалить"
        echo -e " 0) ↩️  Назад"
        echo ""
        read -p "Действие [0-5]: " act

        case $act in
            1)
                if [ "$is_master" = "1" ]; then
                    bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh)
                else
                    echo -e "${CYAN}Открываю порт 53 на $target_name...${NC}"
                    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -p "$target_port" root@"$target_ip" \
                        "ufw allow 53/tcp comment 'DNS TCP' >/dev/null 2>&1; ufw allow 53/udp comment 'DNS UDP' >/dev/null 2>&1; echo OK"
                    echo ""
                    echo -e "${YELLOW}Сейчас запустится официальный установщик.${NC}"
                    echo -e "${YELLOW}Введи домен (например ff.26central.asia) когда спросит.${NC}"
                    echo ""
                    sleep 2
                    ssh -t -o StrictHostKeyChecking=no -p "$target_port" root@"$target_ip" \
                        "export TERM=xterm-256color; bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh)"
                fi
                read -p "Нажмите Enter..."
                ;;
            2)
                if [ "$is_master" = "1" ]; then
                    systemctl restart masterdnsvpn
                else
                    ssh -o BatchMode=yes -p "$target_port" root@"$target_ip" "systemctl restart masterdnsvpn"
                fi
                echo -e "${GREEN}Перезапущен${NC}"
                sleep 1
                ;;
            3)
                if [ "$is_master" = "1" ]; then
                    systemctl stop masterdnsvpn
                else
                    ssh -o BatchMode=yes -p "$target_port" root@"$target_ip" "systemctl stop masterdnsvpn"
                fi
                echo -e "${YELLOW}Остановлен${NC}"
                sleep 1
                ;;
            4)
                if [ "$is_master" = "1" ]; then
                    [ -f /root/server_config.toml ] && nano /root/server_config.toml || echo -e "${RED}Конфиг не найден${NC}"
                else
                    scp -o BatchMode=yes -P "$target_port" root@"$target_ip":/root/server_config.toml /tmp/node_mds_config.toml >/dev/null 2>&1
                    if [ -f /tmp/node_mds_config.toml ]; then
                        nano /tmp/node_mds_config.toml
                        read -p "Применить изменения на $target_name? (y/n): " ap
                        if [[ "$ap" =~ ^[Yy]$ ]]; then
                            scp -o BatchMode=yes -P "$target_port" /tmp/node_mds_config.toml root@"$target_ip":/root/server_config.toml >/dev/null 2>&1
                            ssh -o BatchMode=yes -p "$target_port" root@"$target_ip" "systemctl restart masterdnsvpn"
                            echo -e "${GREEN}Применено${NC}"
                        fi
                        rm -f /tmp/node_mds_config.toml
                    else
                        echo -e "${RED}Конфиг не найден на ноде${NC}"
                        sleep 2
                    fi
                fi
                ;;
            5)
                read -p "Точно удалить на $target_name? (y/n): " confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    if [ "$is_master" = "1" ]; then
                        systemctl stop masterdnsvpn 2>/dev/null
                        bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh) --uninstall
                    else
                        ssh -t -o StrictHostKeyChecking=no -p "$target_port" root@"$target_ip" \
                            "export TERM=xterm-256color; systemctl stop masterdnsvpn 2>/dev/null; bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh) --uninstall"
                    fi
                    echo -e "${GREEN}Удалено${NC}"
                fi
                sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор${NC}"; sleep 1 ;;
        esac
    done
}
