#!/bin/bash

menu_masterdns() {
    while true; do
        header
        echo -e "${YELLOW}🌐 УПРАВЛЕНИЕ MASTERDNSVPN${NC}"
        echo -e " Статус службы : $(get_service_status masterdnsvpn)"
        echo ""
        echo -e " 1) ⚡ Установить / Обновить MasterDnsVPN"
        echo -e " 2) 🔄 Перезапустить MasterDnsVPN"
        echo -e " 3) 🛑 Остановить MasterDnsVPN"
        echo -e " 4) ⚙️  Редактировать конфигурацию (/root/server_config.toml)"
        echo -e " 5) 🗑️  Удалить MasterDnsVPN"
        echo -e " 0) ↩️  Назад в главное меню"
        echo ""
        read -p "Выберите действие [0-5]: " mds_choice
        case $mds_choice in
            1)
                bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh)
                read -p "Нажмите Enter..."
                ;;
            2)
                systemctl restart masterdnsvpn
                echo -e "${GREEN}MasterDnsVPN перезапущен!${NC}"
                sleep 1
                ;;
            3)
                systemctl stop masterdnsvpn
                echo -e "${YELLOW}MasterDnsVPN остановлен!${NC}"
                sleep 1
                ;;
            4)
                if [ -f /root/server_config.toml ]; then
                    nano /root/server_config.toml
                else
                    echo -e "${RED}Файл /root/server_config.toml не найден!${NC}"
                    sleep 2
                fi
                ;;
            5)
                read -p "Точно удалить MasterDnsVPN? (y/n): " confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    systemctl stop masterdnsvpn 2>/dev/null
                    bash <(curl -Ls https://raw.githubusercontent.com/masterking32/MasterDnsVPN/main/server_linux_install.sh) --uninstall
                    echo -e "${GREEN}Удалено.${NC}"
                fi
                sleep 1
                ;;
            0) break ;;
            *) echo -e "${RED}Неверный выбор.${NC}"; sleep 1 ;;
        esac
    done
}
