install_tcp_brutal() {
    clear
    echo "=================================================="
    echo "        УСТАНОВКА TCP BRUTAL                      "
    echo "=================================================="
    KERNEL_MAJOR=$(uname -r | cut -d. -f1)
    KERNEL_MINOR=$(uname -r | cut -d. -f2)
    if [ "$KERNEL_MAJOR" -lt 5 ] || ([ "$KERNEL_MAJOR" -eq 5 ] && [ "$KERNEL_MINOR" -lt 10 ]); then
        echo "ОШИБКА: Требуется ядро Linux 5.10 или выше."
        read -p "Нажмите Enter..."
        return
    fi
    bash <(curl -fsSL https://tcp.hy2.sh/)
    if [ $? -eq 0 ]; then
        echo "Установка завершена успешно!"
        read -p "Введите IP клиента (или 0.0.0.0/0): " cip
        read -p "Введите скорость (Мбит/с): " spd
        if [[ -n "$cip" && -n "$spd" ]]; then
            if [[ "$cip" == */* ]]; then clean_ip="$cip"; else clean_ip="${cip}/32"; fi
            brutalctl add "$clean_ip" "$spd"
            echo "Правило добавлено!"
        fi
    fi
    read -p "Нажмите Enter..."
}

manage_tcp_brutal() {
    while true; do
        clear
        echo "=================================================="
        echo "        УПРАВЛЕНИЕ TCP BRUTAL                     "
        echo "=================================================="
        if ! command -v brutalctl &> /dev/null; then
            echo "TCP Brutal не установлен."
            read -p "Установить сейчас? (y/n): " inst
            if [[ "$inst" == "y" || "$inst" == "Y" ]]; then
                install_tcp_brutal
            fi
            return
        fi
        echo "1) Показать активные правила"
        echo "2) Добавить правило (IP + скорость)"
        echo "3) Удалить правило по IP"
        echo "4) Обновить TCP Brutal (установить заново)"
        echo "0) Назад"
        echo "--------------------------------------------------"
        read -p "Выберите пункт [0-4]: " b_choice
        case $b_choice in
            1)
                echo ""
                brutalctl list
                read -p "Нажмите Enter..."
                ;;
            2)
                read -p "Введите IP (или 0.0.0.0/0): " cip
                read -p "Введите скорость (Мбит/с): " spd
                if [[ -n "$cip" && -n "$spd" ]]; then
                    if [[ "$cip" == */* ]]; then clean_ip="$cip"; else clean_ip="${cip}/32"; fi
                    brutalctl add "$clean_ip" "$spd"
                    echo "Правило добавлено."
                fi
                read -p "Нажмите Enter..."
                ;;
            3)
                read -p "Введите IP для удаления: " cip
                if [[ -n "$cip" ]]; then
                    if [[ "$cip" == */* ]]; then clean_ip="$cip"; else clean_ip="${cip}/32"; fi
                    brutalctl del "$clean_ip"
                    echo "Правило удалено."
                fi
                read -p "Нажмите Enter..."
                ;;
            4)
                install_tcp_brutal
                ;;
            0) return ;;
        esac
    done
}
